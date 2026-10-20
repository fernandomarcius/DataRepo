"""Materialized-view lifecycle + scheduled refresh (pg_cron).

Front-end-created Saved Views (rows in `_system_reports`, each backed by a
generated SQL view) can be toggled into a PostgreSQL MATERIALIZED VIEW with a
periodic REFRESH scheduled via pg_cron. Conversion is in-place (same name):
the regular view is replaced by a materialized view of the same name.

The expensive populate runs off the request thread, building under a temporary
name and atomically swapping, so `SELECT * FROM <view>` keeps working until the
new data is ready. Metadata (schedule, cron job, last refresh, status) lives in
`_system_materialized_views`, keyed by view_name so it survives renames.

DDL that embeds user SQL is run through a raw DBAPI cursor (no parameters), to
avoid SQLAlchemy/psycopg2 interpreting literal '%' in the query as a format
marker -- same reasoning as db.execute_readonly_query.
"""
import json
import re
import threading

from db import engine, execute_query, LOCAL_SCHEMA
from services.view_service import get_dependent_views

# Slugified view names only (matches report_service._slugify output).
MV_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')
# Generous timeout for the populate/refresh: these FDW-backed views take ~2min.
BUILD_STATEMENT_TIMEOUT_MS = 600000
WEEKDAYS = {0, 1, 2, 3, 4, 5, 6}


class RefreshInProgress(Exception):
    """Raised when a refresh/build is already running for the view."""


def _validate_name(name):
    if not name or not MV_NAME_RE.fullmatch(name) or name.startswith('_'):
        raise ValueError(f"Invalid view name: {name!r}")
    return name


def _jobname(view_name):
    return f"refresh_mv_{view_name}"


def _tmp_name(view_name):
    return f"{view_name}_mvtmp"


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _run_sql_raw(statements, timeout_ms=None):
    """Run statements on a raw cursor (no %-interpolation), committed atomically."""
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        try:
            if timeout_ms:
                cur.execute(f"SET statement_timeout = {int(timeout_ms)}")
            for stmt in statements:
                cur.execute(stmt)
            raw.commit()
        finally:
            cur.close()
    finally:
        raw.close()


def build_cron_expression(preset):
    """Translate a friendly preset into a 5-field cron expression. Validates input."""
    if not isinstance(preset, dict):
        raise ValueError("A agenda (schedule) é obrigatória.")
    ptype = preset.get('type')
    if ptype == 'hourly':
        return "0 * * * *"
    if ptype == 'every_n_hours':
        try:
            n = int(preset.get('interval'))
        except (TypeError, ValueError):
            raise ValueError("Intervalo de horas inválido.")
        if not (1 <= n <= 23):
            raise ValueError("Intervalo deve ser entre 1 e 23 horas.")
        return f"0 */{n} * * *"
    if ptype == 'every_n_days':
        try:
            days = int(preset.get('day_interval'))
            times = int(preset.get('times_per_day'))
        except (TypeError, ValueError):
            raise ValueError("Intervalo de dias / vezes ao dia inválido.")
        if not (1 <= days <= 31):
            raise ValueError("Intervalo deve ser entre 1 e 31 dias.")
        if not (1 <= times <= 24):
            raise ValueError("Vezes ao dia deve ser entre 1 e 24.")
        # Spread the daily runs evenly across the 24h and emit an hour list.
        hours = sorted({int(round(i * 24 / times)) % 24 for i in range(times)})
        hours_str = ",".join(str(h) for h in hours)
        return f"0 {hours_str} */{days} * *"
    if ptype in ('daily', 'weekly', 'weekdays'):
        match = re.fullmatch(r'(\d{2}):(\d{2})', str(preset.get('time') or ''))
        if not match:
            raise ValueError("Horário deve estar no formato HH:MM.")
        hh, mm = int(match.group(1)), int(match.group(2))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            raise ValueError("Horário fora do intervalo válido.")
        if ptype == 'daily':
            return f"{mm} {hh} * * *"
        if ptype == 'weekly':
            weekday = preset.get('weekday')
            if weekday not in WEEKDAYS:
                raise ValueError("Dia da semana deve ser 0-6 (domingo=0).")
            return f"{mm} {hh} * * {weekday}"
        # weekdays: specific days of the week (e.g. Monday + Thursday)
        days = preset.get('weekdays')
        if not isinstance(days, list) or not days:
            raise ValueError("Selecione ao menos um dia da semana.")
        try:
            norm = sorted({int(d) for d in days})
        except (TypeError, ValueError):
            raise ValueError("Dias da semana inválidos.")
        if any(d not in WEEKDAYS for d in norm):
            raise ValueError("Dia da semana deve ser 0-6 (domingo=0).")
        return f"{mm} {hh} * * {','.join(str(d) for d in norm)}"
    raise ValueError(f"Tipo de agenda desconhecido: {ptype!r}")


def is_materialized(view_name):
    rows = execute_query(
        f"SELECT 1 AS m FROM pg_matviews WHERE schemaname = '{LOCAL_SCHEMA}' AND matviewname = :n",
        {"n": view_name},
    )
    return bool(rows)


def get_materialization(view_name):
    rows = execute_query(
        """
        SELECT view_name, refresh_cron, preset, last_refreshed_at,
               last_status, last_error, created_by, created_at, updated_at
        FROM _system_materialized_views WHERE view_name = :n
        """,
        {"n": view_name},
    )
    return rows[0] if rows else None


def get_all_materializations():
    """Map view_name -> metadata, for enriching the reports list in one query."""
    rows = execute_query(
        """
        SELECT view_name, refresh_cron, preset, last_refreshed_at, last_status, last_error
        FROM _system_materialized_views
        """
    )
    return {r['view_name']: r for r in (rows or [])}


# ---------------------------------------------------------------------------
# pg_cron scheduling
# ---------------------------------------------------------------------------

def schedule_refresh(view_name, cron_expr):
    """(Re)schedule the recurring REFRESH. Named-job form is idempotent. Returns jobid."""
    _validate_name(view_name)
    command = f'REFRESH MATERIALIZED VIEW {LOCAL_SCHEMA}."{view_name}"'
    rows = execute_query(
        "SELECT cron.schedule(:job, :sched, :cmd) AS jobid",
        {"job": _jobname(view_name), "sched": cron_expr, "cmd": command},
    )
    return rows[0]['jobid'] if rows else None


def unschedule_refresh(view_name):
    """Remove the cron job. Idempotent: unscheduling a missing job is a no-op."""
    try:
        execute_query("SELECT cron.unschedule(:job)", {"job": _jobname(view_name)})
    except Exception as e:
        print(f"unschedule_refresh({view_name}) no-op: {e}")


# ---------------------------------------------------------------------------
# Metadata writers
# ---------------------------------------------------------------------------

def _upsert_building(view_name, report_id, cron_expr, preset, created_by):
    execute_query(
        """
        INSERT INTO _system_materialized_views
            (view_name, report_id, refresh_cron, preset, last_status, created_by, updated_at)
        VALUES (:vn, :rid, :cron, CAST(:preset AS JSONB), 'building', :by, CURRENT_TIMESTAMP)
        ON CONFLICT (view_name) DO UPDATE SET
            report_id   = COALESCE(EXCLUDED.report_id, _system_materialized_views.report_id),
            refresh_cron = EXCLUDED.refresh_cron,
            preset      = EXCLUDED.preset,
            last_status = 'building',
            last_error  = NULL,
            created_by  = EXCLUDED.created_by,
            updated_at  = CURRENT_TIMESTAMP
        """,
        {"vn": view_name, "rid": report_id, "cron": cron_expr,
         "preset": json.dumps(preset), "by": created_by},
    )


def _set_status(view_name, status, error=None, touch_refreshed=False, jobid=None):
    execute_query(
        f"""
        UPDATE _system_materialized_views
        SET last_status = :status,
            last_error  = :err,
            {"last_refreshed_at = CURRENT_TIMESTAMP," if touch_refreshed else ""}
            {"cron_jobid = :jid, cron_jobname = :jn," if jobid is not None else ""}
            updated_at = CURRENT_TIMESTAMP
        WHERE view_name = :vn
        """,
        {"status": status, "err": (str(error)[:1000] if error else None),
         "vn": view_name,
         **({"jid": jobid, "jn": _jobname(view_name)} if jobid is not None else {})},
    )


# ---------------------------------------------------------------------------
# Toggle ON: materialize
# ---------------------------------------------------------------------------

def materialize_view(view_name, sql_query, preset, created_by, report_id=None, replace=False):
    """Convert a regular view into a materialized view (in-place) + schedule refresh.

    Returns immediately; the heavy populate runs in a background thread. Reads of
    <view_name> keep working until the new data is swapped in. With replace=True
    the view is already materialized (re-materialize on edit): the guard is
    skipped and the swap drops the existing matview.
    """
    _validate_name(view_name)
    if not replace and is_materialized(view_name):
        return {"status": "already_materialized", "view_name": view_name}
    deps = get_dependent_views(view_name)
    if deps:
        raise ValueError(
            "Não é possível materializar: existem views dependentes: " + ", ".join(deps)
        )
    cron_expr = build_cron_expression(preset)  # validate BEFORE any DDL

    # Clear any orphan temp matview left by a previously interrupted build.
    try:
        _run_sql_raw([f'DROP MATERIALIZED VIEW IF EXISTS "{_tmp_name(view_name)}"'])
    except Exception as e:
        print(f"orphan cleanup for {view_name} failed: {e}")

    _upsert_building(view_name, report_id, cron_expr, preset, created_by)
    threading.Thread(
        target=_do_build_and_swap,
        args=(view_name, sql_query, cron_expr),
        daemon=True,
    ).start()
    return {"status": "building", "view_name": view_name, "cron": cron_expr}


def _do_build_and_swap(view_name, sql_query, cron_expr):
    tmp = _tmp_name(view_name)
    clean_sql = (sql_query or "").strip().rstrip(';')
    try:
        # 1. Heavy build under temp name; <view_name> is still the old view.
        _run_sql_raw(
            [f'CREATE MATERIALIZED VIEW "{tmp}" AS {clean_sql} WITH DATA'],
            timeout_ms=BUILD_STATEMENT_TIMEOUT_MS,
        )
        # 2. Atomic swap (single transaction). Drop whichever form currently holds
        #    the name (regular view on first materialize, matview on re-materialize).
        #    No CASCADE: dependents were refused / would surface an error.
        _run_sql_raw([
            f'DROP VIEW IF EXISTS "{view_name}"',
            f'DROP MATERIALIZED VIEW IF EXISTS "{view_name}"',
            f'ALTER MATERIALIZED VIEW "{tmp}" RENAME TO "{view_name}"',
        ])
        # 3. Schedule recurring refresh.
        jobid = schedule_refresh(view_name, cron_expr)
        # 4. Mark ready.
        _set_status(view_name, 'ok', touch_refreshed=True, jobid=jobid)
    except Exception as e:
        try:
            _run_sql_raw([f'DROP MATERIALIZED VIEW IF EXISTS "{tmp}"'])
        except Exception:
            pass
        _set_status(view_name, 'error', error=e)
        print(f"materialize {view_name} failed: {e}")


# ---------------------------------------------------------------------------
# Toggle OFF: un-materialize
# ---------------------------------------------------------------------------

def unmaterialize_view(view_name, sql_query):
    """Revert a materialized view back to a regular view and drop its schedule."""
    _validate_name(view_name)
    unschedule_refresh(view_name)
    clean_sql = (sql_query or "").strip().rstrip(';')
    _run_sql_raw([
        f'DROP MATERIALIZED VIEW IF EXISTS "{view_name}"',
        f'CREATE OR REPLACE VIEW "{view_name}" AS {clean_sql}',
    ])
    execute_query("DELETE FROM _system_materialized_views WHERE view_name = :vn", {"vn": view_name})
    return {"status": "reverted", "view_name": view_name}


# ---------------------------------------------------------------------------
# Manual refresh
# ---------------------------------------------------------------------------

def refresh_now(view_name):
    _validate_name(view_name)
    if not is_materialized(view_name):
        raise ValueError("A view não está materializada.")
    meta = get_materialization(view_name)
    if meta and meta.get('last_status') in ('building', 'refreshing'):
        raise RefreshInProgress("Já existe uma atualização em andamento.")
    _set_status(view_name, 'refreshing')
    threading.Thread(target=_do_refresh, args=(view_name,), daemon=True).start()
    return {"status": "refreshing", "view_name": view_name}


def _do_refresh(view_name):
    try:
        _run_sql_raw(
            [f'REFRESH MATERIALIZED VIEW {LOCAL_SCHEMA}."{view_name}"'],
            timeout_ms=BUILD_STATEMENT_TIMEOUT_MS,
        )
        _set_status(view_name, 'ok', touch_refreshed=True)
    except Exception as e:
        _set_status(view_name, 'error', error=e)
        print(f"refresh {view_name} failed: {e}")


# ---------------------------------------------------------------------------
# Rename + delete hooks (called from data_object_service / report_service)
# ---------------------------------------------------------------------------

def rename_materialization(old_name, new_name):
    """After a matview is renamed at the DDL level, move its schedule + metadata."""
    _validate_name(new_name)
    meta = get_materialization(old_name)
    if not meta:
        return
    unschedule_refresh(old_name)
    jobid = schedule_refresh(new_name, meta['refresh_cron']) if meta.get('refresh_cron') else None
    execute_query(
        """
        UPDATE _system_materialized_views
        SET view_name = :new, cron_jobid = :jid, cron_jobname = :jn, updated_at = CURRENT_TIMESTAMP
        WHERE view_name = :old
        """,
        {"new": new_name, "old": old_name, "jid": jobid, "jn": _jobname(new_name)},
    )


def drop_materialization_metadata(view_name):
    """Unschedule cron and remove the metadata row (the DROP of the object is done by caller)."""
    unschedule_refresh(view_name)
    execute_query("DELETE FROM _system_materialized_views WHERE view_name = :vn", {"vn": view_name})


# ---------------------------------------------------------------------------
# Startup reconciliation
# ---------------------------------------------------------------------------

def reconcile_on_startup():
    """Heal state after a restart: fix interrupted builds, re-assert cron jobs, drop orphans."""
    rows = execute_query(
        "SELECT view_name, refresh_cron, last_status FROM _system_materialized_views"
    )
    for r in (rows or []):
        view_name = r['view_name']
        materialized = is_materialized(view_name)
        if r['last_status'] in ('building', 'refreshing'):
            if materialized:
                _set_status(view_name, 'ok')
            else:
                _set_status(view_name, 'error', error='Interrompido antes de concluir.')
        if materialized and r['refresh_cron']:
            try:
                schedule_refresh(view_name, r['refresh_cron'])
            except Exception as e:
                print(f"reconcile schedule {view_name} failed: {e}")
        try:
            _run_sql_raw([f'DROP MATERIALIZED VIEW IF EXISTS "{_tmp_name(view_name)}"'])
        except Exception:
            pass

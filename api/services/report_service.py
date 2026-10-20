from db import execute_query, LOCAL_SCHEMA
import re
from kit.sql_guard import validate_readonly_sql
from services import materialized_view_service as mv


def _slugify(text):
    text = text.lower()
    slug = re.sub(r'[^a-z0-9_]', '_', text)
    slug = re.sub(r'_+', '_', slug).strip('_')  # Clean duplicate underscores
    if not slug or slug[0].isdigit():
        slug = f"v_{slug}"
    return slug


def _get_view_name(name):
    # User requested same name as report. We slugify for safety.
    return _slugify(name)


def _check_unique_name(name, exclude_id=None):
    query = "SELECT COUNT(*) FROM _system_reports WHERE LOWER(name) = LOWER(:name)"
    params = {"name": name}
    if exclude_id:
        query += " AND id != :id"
        params["id"] = exclude_id

    result = execute_query(query, params)
    return result[0]['count'] == 0 if result else True


def get_all_reports():
    reports = execute_query("SELECT * FROM _system_reports ORDER BY created_at DESC")
    # Enrich with view_name + materialization state (single metadata query).
    if reports:
        mat_map = mv.get_all_materializations()
        for r in reports:
            view_name = _get_view_name(r['name'])
            r['view_name'] = view_name
            materialization = mat_map.get(view_name)
            r['is_materialized'] = materialization is not None
            r['materialization'] = materialization
    return reports


def create_report(name, description, sql_query):
    if not _check_unique_name(name):
        raise ValueError("A view with this name already exists.")
    sql_query = validate_readonly_sql(sql_query)

    query = """
    INSERT INTO _system_reports (name, description, sql_query)
    VALUES (:name, :description, :sql_query)
    RETURNING id, name, description, sql_query, created_at
    """
    params = {"name": name, "description": description, "sql_query": sql_query}
    result = execute_query(query, params)

    if result:
        report = result[0]
        # Create actual DB view
        view_name = _get_view_name(report['name'])
        try:
            # We must remove the trailing semicolon for CREATE VIEW AS (...)
            clean_sql = sql_query.strip().rstrip(';')
            create_view_sql = f"CREATE OR REPLACE VIEW {view_name} AS {clean_sql}"
            execute_query(create_view_sql)
            report['view_name'] = view_name
        except Exception as e:
            print(f"Failed to create DB view {view_name}: {e}")
            # If view creation fails, we might want to rollback report creation,
            # but for now we proceed. Ideally we'd use a transaction.

        return report
    return None


def delete_report(report_id):
    # Get report first to know name
    report = get_report(report_id)
    if report:
        view_name = _get_view_name(report['name'])
        if mv.is_materialized(view_name):
            # Tear down the schedule and drop the materialized view. The metadata
            # row is also removed via the ON DELETE CASCADE below, but we clear the
            # cron job explicitly here.
            mv.unschedule_refresh(view_name)
            execute_query(f'DROP MATERIALIZED VIEW IF EXISTS "{view_name}"')
        else:
            execute_query(f"DROP VIEW IF EXISTS {view_name}")

    query = "DELETE FROM _system_reports WHERE id = :id RETURNING id"
    result = execute_query(query, {"id": report_id})
    return result[0] if result else None


def get_report(report_id):
    query = "SELECT * FROM _system_reports WHERE id = :id"
    result = execute_query(query, {"id": report_id})
    if result:
        report = result[0]
        report['view_name'] = _get_view_name(report['name'])
        return report
    return None


def sync_report_name_for_view_rename(old_view_name, new_view_name):
    """Update the saved report name when its generated DB view is renamed elsewhere."""
    reports = execute_query("SELECT id, name, description, sql_query, created_at FROM _system_reports")
    if not reports:
        return None

    matching_report = next(
        (report for report in reports if _get_view_name(report["name"]) == old_view_name),
        None,
    )
    if not matching_report:
        return None

    if not _check_unique_name(new_view_name, exclude_id=matching_report["id"]):
        raise ValueError("A view with this name already exists.")

    query = """
    UPDATE _system_reports
    SET name = :new_name
    WHERE id = :id
    RETURNING id, name, description, sql_query, created_at
    """
    result = execute_query(query, {"id": matching_report["id"], "new_name": new_view_name})
    if result:
        report = result[0]
        report["view_name"] = _get_view_name(report["name"])
        return report
    return None


def _all_dependents_ordered(view_name):
    """All views/materialized views depending (transitively) on view_name.

    Returned in dependency order (a dependency appears before the objects that
    depend on it), each as {name, relkind, definition}. Includes matviews
    (relkind 'm'), which get_dependent_views() omits.
    """
    seen = {}
    order = []
    frontier = [view_name]
    while frontier:
        current = frontier.pop(0)
        rows = execute_query(
            """
            SELECT DISTINCT dep.relname AS name, dep.relkind AS relkind
            FROM pg_depend d
            JOIN pg_rewrite r ON d.objid = r.oid
            JOIN pg_class dep ON r.ev_class = dep.oid
            JOIN pg_class src ON d.refobjid = src.oid
            JOIN pg_namespace n ON dep.relnamespace = n.oid
            WHERE src.relname = :src AND dep.relname <> :src
              AND n.nspname = :schema AND dep.relkind IN ('v', 'm')
            """,
            {"src": current, "schema": LOCAL_SCHEMA},
        )
        for row in (rows or []):
            if row['name'] not in seen:
                seen[row['name']] = row['relkind']
                order.append(row['name'])
                frontier.append(row['name'])
    result = []
    for nm in order:
        ddef = execute_query("SELECT pg_get_viewdef(:n, true) AS def", {"n": nm})
        result.append({"name": nm, "relkind": seen[nm],
                       "definition": (ddef[0]['def'] if ddef else '').strip().rstrip(';')})
    return result


def _recreate_view_with_dependents(view_name, clean_sql):
    """Recreate a view whose column set changed, preserving dependents.

    Drops the view CASCADE (taking its dependents with it) and recreates it with
    the new SQL plus every dependent. Regular-view dependents are recreated
    atomically in the same transaction; materialized-view dependents are rebuilt
    in the background (with their schedule re-registered) so the request stays fast.
    """
    deps = _all_dependents_ordered(view_name)

    mat_info = {}
    statements = [
        f'DROP VIEW IF EXISTS "{view_name}" CASCADE',
        f'CREATE VIEW "{view_name}" AS {clean_sql}',
    ]
    for dep in deps:
        if dep['relkind'] == 'm':
            meta = mv.get_materialization(dep['name']) or {}
            rid = execute_query(
                "SELECT report_id FROM _system_materialized_views WHERE view_name = :v",
                {"v": dep['name']},
            )
            mat_info[dep['name']] = {
                "preset": meta.get('preset'),
                "created_by": meta.get('created_by'),
                "report_id": rid[0]['report_id'] if rid else None,
                "definition": dep['definition'],
            }
            mv.unschedule_refresh(dep['name'])
        else:
            statements.append(f'CREATE VIEW "{dep["name"]}" AS {dep["definition"]}')

    # Atomic: if the new SQL is invalid, the whole thing rolls back (nothing lost).
    mv._run_sql_raw(statements)

    # Rebuild materialized dependents off the request thread.
    for nm, info in mat_info.items():
        if info.get('preset'):
            mv.materialize_view(nm, info['definition'], info['preset'],
                                info.get('created_by'), report_id=info.get('report_id'))
        else:
            mv._run_sql_raw([f'CREATE MATERIALIZED VIEW "{nm}" AS {info["definition"]}'])


def update_report(report_id, name, description, sql_query):
    if not _check_unique_name(name, exclude_id=report_id):
        raise ValueError("A view with this name already exists.")
    sql_query = validate_readonly_sql(sql_query)

    # Get old report to know its current view + whether it is materialized.
    old_report = get_report(report_id)
    was_materialized = False
    old_view_name = None
    old_preset = None
    old_created_by = None
    if old_report:
        old_view_name = _get_view_name(old_report['name'])
        if mv.is_materialized(old_view_name):
            was_materialized = True
            meta = mv.get_materialization(old_view_name)
            old_preset = (meta or {}).get('preset')
            old_created_by = (meta or {}).get('created_by')
        # NOTE: do NOT pre-drop the regular view here. A blunt DROP fails when
        # other objects (views or materialized views) depend on it. The view is
        # updated in place below with CREATE OR REPLACE VIEW, preserving dependents.

    query = """
    UPDATE _system_reports
    SET name = :name, description = :description, sql_query = :sql_query
    WHERE id = :id
    RETURNING id, name, description, sql_query, created_at
    """
    params = {"id": report_id, "name": name, "description": description, "sql_query": sql_query}
    result = execute_query(query, params)

    if result:
        report = result[0]
        view_name = _get_view_name(report['name'])
        report['view_name'] = view_name
        if was_materialized:
            # Stay materialized across the edit: rebuild the matview (under the
            # possibly-new name) with the new SQL and re-schedule. The build runs
            # in the background and keeps the old matview readable until swap.
            try:
                mv.materialize_view(view_name, sql_query, old_preset, old_created_by,
                                    report_id=report_id, replace=True)
                if view_name != old_view_name:
                    # Drop the now-orphan old matview + its schedule/metadata.
                    mv.unschedule_refresh(old_view_name)
                    execute_query(f'DROP MATERIALIZED VIEW IF EXISTS "{old_view_name}"')
                    execute_query(
                        "DELETE FROM _system_materialized_views WHERE view_name = :vn",
                        {"vn": old_view_name},
                    )
            except Exception as e:
                print(f"Failed to re-materialize view {view_name}: {e}")
        else:
            clean_sql = sql_query.strip().rstrip(';')
            if view_name != old_view_name and old_view_name:
                # Renamed: remove the old view and create under the new name.
                execute_query(f"DROP VIEW IF EXISTS {old_view_name}")
                execute_query(f"CREATE VIEW {view_name} AS {clean_sql}")
            else:
                # Same name: replace in place WITHOUT dropping so dependents are
                # preserved (fast path; works when the column set is unchanged).
                try:
                    execute_query(f"CREATE OR REPLACE VIEW {view_name} AS {clean_sql}")
                except Exception:
                    # Column set changed -> CREATE OR REPLACE is not allowed.
                    # Recreate the view and all dependents (regular + materialized).
                    # Errors propagate so the API surfaces a real failure instead of
                    # silently keeping the old definition.
                    _recreate_view_with_dependents(view_name, clean_sql)

        return report
    return None

import os
import re
import tempfile

import camelot
import pandas as pd

_DATE_RE = re.compile(r'^\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}')
_NUMBER_RE = re.compile(r'^[\d.,\-+]+$')


def _make_unique_columns(headers):
    seen = {}
    out = []
    for i, h in enumerate(headers):
        name = str(h).strip()
        if not name:
            name = f'col_{i + 1}'
        if name in seen:
            seen[name] += 1
            out.append(f'{name}_{seen[name]}')
        else:
            seen[name] = 0
            out.append(name)
    return out


def _generic_columns(n):
    return [f'col_{i + 1}' for i in range(n)]


def _looks_like_header(row) -> bool:
    """Best-effort check: does this row look like real column labels?

    A clean header has every cell filled, unique values, and no cells that
    look like data (dates, numbers, or very long strings). When this returns
    False the caller should fall back to generic col_N names and keep the
    row as data so the user can clean up downstream in SQL/views.
    """
    cells = [str(c).strip() for c in row]
    if not cells or any(not c for c in cells):
        return False
    if len(set(cells)) != len(cells):
        return False
    for c in cells:
        if _DATE_RE.match(c) or _NUMBER_RE.match(c):
            return False
        if len(c) > 60:
            return False
    return True


def _strip_object_cells(df: pd.DataFrame) -> pd.DataFrame:
    for i, dtype in enumerate(df.dtypes):
        if dtype == object:
            df.iloc[:, i] = df.iloc[:, i].astype(str).str.strip()
    return df


def _extract_from_path(path: str) -> pd.DataFrame:
    tables = camelot.read_pdf(path, pages='all', flavor='lattice')
    if len(tables) == 0:
        tables = camelot.read_pdf(path, pages='all', flavor='stream')
    if len(tables) == 0:
        raise ValueError(
            "Nenhuma tabela encontrada no PDF. "
            "Verifique se o PDF contém tabelas estruturadas com texto (não imagem escaneada)."
        )

    raw_frames = [t.df.copy() for t in tables if not t.df.empty]
    if not raw_frames:
        raise ValueError("Nenhuma tabela com dados encontrada no PDF.")

    same_width = len({f.shape[1] for f in raw_frames}) == 1
    first = raw_frames[0]
    use_real_header = len(first) >= 1 and _looks_like_header(first.iloc[0])

    if use_real_header:
        columns = _make_unique_columns(first.iloc[0].tolist())
        header_signature = [str(c).strip() for c in first.iloc[0].tolist()]
    else:
        # No reliable header — caller asked for generic col_N so that data
        # (including what camelot picked up as metadata rows) can be cleaned
        # up via SQL/views afterward.
        columns = _generic_columns(first.shape[1])
        header_signature = None

    out_frames = []
    for df in raw_frames:
        df = df.copy()
        if same_width:
            df.columns = columns
            if header_signature is not None and len(df) > 0:
                row_sig = [str(c).strip() for c in df.iloc[0].tolist()]
                if row_sig == header_signature:
                    df = df.drop(index=df.index[0]).reset_index(drop=True)
        else:
            # Fallback: per-table generic columns when shapes differ.
            df.columns = _generic_columns(df.shape[1])
        if df.empty:
            continue
        df = _strip_object_cells(df)
        out_frames.append(df)

    if not out_frames:
        raise ValueError("Nenhuma tabela com dados encontrada no PDF.")

    if len(out_frames) == 1:
        return out_frames[0]
    return pd.concat(out_frames, ignore_index=True)


def extract_tables_from_pdf(file_storage) -> pd.DataFrame:
    tmp_fd, tmp_path = tempfile.mkstemp(suffix='.pdf')
    try:
        os.close(tmp_fd)
        file_storage.save(tmp_path)
        return _extract_from_path(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def extract_tables_from_pdf_path(file_path: str) -> pd.DataFrame:
    return _extract_from_path(file_path)

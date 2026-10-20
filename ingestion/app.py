"""ingestion — upload e parsing de arquivos (Excel, CSV, PDF) para tabelas.

Workload separado por perfil: CPU e memoria de pandas/camelot/OpenCV, imagem
com ghostscript, uploads de ate 100 MB. Cria tabelas de dados e escreve
`_column_aliases` (nome original longo -> coluna fisica). O schema dessas tabelas
de sistema e das demais vive nas migrations do api; renomear/apagar tabelas e
responsabilidade do api. Eventos de auditoria vao para o api
(POST /internal/v1/events).
"""
import json
import os
import shutil
import tempfile

from flask import jsonify, request

from kit.audit_client import log_event
from kit.auth import require_permission
from kit.web import create_app
from services.data_service import (
    ColumnCountMismatchError,
    ColumnNameMismatchError,
    IncompatibleHeaderModeError,
    OversizedColumnError,
    append_excel,
    insert_row,
    inspect_file_headers,
    upload_excel,
)
from services.mapper_service import analyze_file_structure

app = create_app(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max upload size


@app.route('/api/v1/map-file', methods=['POST'])
@require_permission('can_upload')
def map_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    # Diretorio temporario exclusivo e so o basename do nome enviado: o monolito
    # gravava em f"/tmp/{file.filename}", e um nome com "../" escrevia fora de
    # /tmp — inclusive sobre o codigo em /app, que pertence ao usuario do processo.
    # O nome original e mantido porque analyze_file_structure deriva dele a
    # extensao e o nome sugerido da tabela.
    temp_dir = tempfile.mkdtemp(prefix="map-file-")
    try:
        temp_path = os.path.join(temp_dir, os.path.basename(file.filename))
        file.save(temp_path)

        schema = analyze_file_structure(temp_path)

        log_event("ANALYZE", "file", file.filename, metadata={"filename": file.filename})

        return jsonify(schema), 200
    except Exception as e:
        log_event(
            "ANALYZE", "file", file.filename if file else None,
            status="failed",
            error=str(e),
            metadata={"filename": file.filename if file else None},
        )
        return jsonify({"error": str(e)}), 500
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _parse_column_renames(raw):
    """Parse a JSON object string from form data into a {str: str} dict. Returns
    an empty dict for missing/empty input."""
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        raise ValueError("column_renames deve ser um objeto JSON válido.")
    if not isinstance(parsed, dict):
        raise ValueError("column_renames deve ser um objeto JSON (chave→valor).")
    return {str(k): str(v) for k, v in parsed.items()}


@app.route('/api/v1/inspect-headers', methods=['POST'])
@require_permission('can_upload')
def inspect_headers():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    header_mode = request.form.get('header_mode', 'generic')
    table_name = request.form.get('table_name') or None
    try:
        result = inspect_file_headers(file, header_mode=header_mode, table_name=table_name)
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/upload', methods=['POST'])
@require_permission('can_upload')
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    table_name = request.form.get('table_name')
    header_mode = request.form.get('header_mode', 'generic')
    try:
        column_renames = _parse_column_renames(request.form.get('column_renames'))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        result = upload_excel(file, table_name, header_mode=header_mode, column_renames=column_renames)
        log_event(
            "UPLOAD", "table", result.get("table_name"),
            metadata={
                "filename": file.filename,
                "rows": result.get("rows"),
                "table_name": result.get("table_name"),
                "header_mode": header_mode,
                "column_renames": column_renames or None,
            },
        )
        return jsonify(result), 200
    except OversizedColumnError as e:
        log_event(
            "UPLOAD", "table", table_name,
            status="rejected",
            error=str(e),
            metadata={"filename": file.filename, "header_mode": header_mode, "oversized": e.oversized},
        )
        return jsonify({"error": str(e), "oversized": e.oversized}), 422
    except Exception as e:
        log_event(
            "UPLOAD", "table", table_name,
            status="failed",
            error=str(e),
            metadata={"filename": file.filename, "header_mode": header_mode},
        )
        return jsonify({"error": str(e)}), 500


@app.route('/api/v1/tables/<table_name>/data', methods=['POST'])
@require_permission('can_upload')
def insert_data(table_name):
    try:
        # Check if it's a file upload
        if 'file' in request.files:
            file = request.files['file']
            if file.filename == '':
                return jsonify({"error": "No selected file"}), 400

            header_mode = request.form.get('header_mode', 'generic')
            try:
                column_renames = _parse_column_renames(request.form.get('column_renames'))
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            try:
                result = append_excel(file, table_name, header_mode=header_mode, column_renames=column_renames)
            except OversizedColumnError as e:
                log_event(
                    "INSERT", "table_row", table_name,
                    status="rejected",
                    error=str(e),
                    metadata={
                        "filename": file.filename,
                        "header_mode": header_mode,
                        "oversized": e.oversized,
                    },
                )
                return jsonify({"error": str(e), "oversized": e.oversized, "table_name": table_name}), 422
            except ColumnCountMismatchError as e:
                log_event(
                    "INSERT", "table_row", table_name,
                    status="rejected",
                    error=str(e),
                    metadata={
                        "filename": file.filename,
                        "file_columns": e.file_count,
                        "table_columns": e.table_count,
                        "header_mode": header_mode,
                    },
                )
                return jsonify({
                    "error": str(e),
                    "file_columns": e.file_count,
                    "table_columns": e.table_count,
                    "table_name": table_name,
                }), 422
            except ColumnNameMismatchError as e:
                log_event(
                    "INSERT", "table_row", table_name,
                    status="rejected",
                    error=str(e),
                    metadata={
                        "filename": file.filename,
                        "missing_in_table": e.missing_in_table,
                        "missing_in_file": e.missing_in_file,
                        "header_mode": header_mode,
                    },
                )
                return jsonify({
                    "error": str(e),
                    "missing_in_table": e.missing_in_table,
                    "missing_in_file": e.missing_in_file,
                    "table_name": table_name,
                }), 422
            except IncompatibleHeaderModeError as e:
                log_event(
                    "INSERT", "table_row", table_name,
                    status="rejected",
                    error=str(e),
                    metadata={
                        "filename": file.filename,
                        "chosen_mode": e.chosen_mode,
                        "table_shape": e.table_shape,
                    },
                )
                return jsonify({
                    "error": str(e),
                    "chosen_mode": e.chosen_mode,
                    "table_shape": e.table_shape,
                    "table_name": table_name,
                }), 422
            log_event(
                "INSERT", "table_row", table_name,
                metadata={
                    "filename": file.filename,
                    "rows": result.get("rows"),
                    "table_name": table_name,
                    "header_mode": header_mode,
                },
            )
            return jsonify(result), 200

        # Otherwise assume JSON data
        data = (request.get_json(silent=True) or {}).get('data')
        if data:
            result = insert_row(table_name, data)
            log_event("INSERT", "table_row", table_name, after=data)
            return jsonify(result), 200

        return jsonify({"error": "No file or data provided"}), 400

    except Exception as e:
        log_event(
            "INSERT", "table_row", table_name,
            status="failed",
            error=str(e),
        )
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # nosemgrep: avoid_app_run_with_bad_host -- caminho de dev local apenas; producao usa gunicorn
    app.run(host='0.0.0.0', port=5000, debug=os.getenv('FLASK_DEBUG') == '1')

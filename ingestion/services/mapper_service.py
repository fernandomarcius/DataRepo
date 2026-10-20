import pandas as pd
import os
import re
from services.pdf_parser import extract_tables_from_pdf_path


def analyze_file_structure(file_path):
    """
    Reads the file and infers schema using pandas dtypes.
    """
    try:
        # Read first few rows to infer types
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path, nrows=100)
        elif file_path.endswith('.pdf'):
            df = extract_tables_from_pdf_path(file_path).head(100)
        else:
            df = pd.read_excel(file_path, nrows=100)

        # Infer table name from filename
        filename = os.path.basename(file_path)
        table_name = os.path.splitext(filename)[0]
        # Clean table name (snake_case)
        table_name = re.sub(r'[^a-zA-Z0-9]', '_', table_name).lower()

        columns = []
        for col in df.columns:
            dtype = df[col].dtype
            sql_type = "VARCHAR"

            if pd.api.types.is_integer_dtype(dtype):
                sql_type = "INTEGER"
            elif pd.api.types.is_float_dtype(dtype):
                sql_type = "FLOAT"
            elif pd.api.types.is_bool_dtype(dtype):
                sql_type = "BOOLEAN"
            elif pd.api.types.is_datetime64_any_dtype(dtype):
                sql_type = "TIMESTAMP"

            columns.append({
                "name": col,
                "type": sql_type,
                "description": f"Column {col}"
            })

        return {
            "table_name": table_name,
            "description": f"Imported from {filename}",
            "columns": columns
        }

    except Exception as e:
        raise Exception(f"Mapper failed: {str(e)}")

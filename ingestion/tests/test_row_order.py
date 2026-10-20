"""Unit tests for the file row-order column (ordem_arquivo)."""
import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")

sys.modules.setdefault(
    "db",
    MagicMock(engine=MagicMock(), execute_query=MagicMock(return_value=[]), LOCAL_SCHEMA="public"),
)

_DATA_SERVICE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services", "data_service.py"
)


def _load_real_modules():
    """Load the real pandas and data_service, bypassing other tests' sys.modules mocks.

    test_audit installs MagicMocks at sys.modules["pandas"], ["pytz"], ["sqlalchemy"]
    and ["services.data_service"] during collection, so a plain import here would
    assert against mocks (and pandas._libs.tslibs fails outright on a mocked pytz).

    Those mocks are installed with setdefault, i.e. "use the real module when it is
    installed" — so the real ones are left in sys.modules afterwards. Only the
    services.data_service mock is put back, since test_audit asserts against it.
    """
    dependency_mocks = ("pandas", "pytz", "sqlalchemy", "sqlalchemy.exc")
    for name in dependency_mocks:
        if isinstance(sys.modules.get(name), MagicMock):
            del sys.modules[name]
    saved_data_service = sys.modules.pop("services.data_service", None)
    try:
        import pandas as real_pandas
    except ImportError:  # pandas genuinely unavailable — skip instead of failing
        return None, None
    try:
        spec = importlib.util.spec_from_file_location("_real_data_service", _DATA_SERVICE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return real_pandas, module
    finally:
        if saved_data_service is not None:
            sys.modules["services.data_service"] = saved_data_service


pd, data_service = _load_real_modules()

requires_pandas = unittest.skipIf(data_service is None, "pandas is not installed")  # skip -- pandas nao instalado

if data_service is not None:
    ROW_ORDER_COLUMN = data_service.ROW_ORDER_COLUMN
    SYSTEM_COLUMNS = data_service.SYSTEM_COLUMNS
    TIMESTAMP_COLUMN = data_service.TIMESTAMP_COLUMN
    _apply_row_order = data_service._apply_row_order
    _column_type_for = data_service._column_type_for
    _serialize_dataframe_as_text = data_service._serialize_dataframe_as_text


@requires_pandas
class TestRowOrderColumnType(unittest.TestCase):
    def test_row_order_column_is_numeric(self):
        """A TEXT row-order column would sort lexicographically ("10" before "2")."""
        self.assertEqual(_column_type_for(ROW_ORDER_COLUMN), "BIGINT")

    def test_timestamp_column_keeps_its_type(self):
        self.assertEqual(_column_type_for(TIMESTAMP_COLUMN), "TIMESTAMP")

    def test_data_columns_are_text(self):
        self.assertEqual(_column_type_for("qualquer_coluna"), "TEXT")

    def test_system_columns_cover_both_generated_columns(self):
        self.assertEqual(set(SYSTEM_COLUMNS), {TIMESTAMP_COLUMN, ROW_ORDER_COLUMN})


@requires_pandas
class TestApplyRowOrder(unittest.TestCase):
    def test_numbers_rows_from_one(self):
        df = _apply_row_order(pd.DataFrame({"a": [10, 20, 30]}), start=1)
        self.assertEqual(list(df[ROW_ORDER_COLUMN]), [1, 2, 3])

    def test_continues_from_given_start(self):
        df = _apply_row_order(pd.DataFrame({"a": [1, 2]}), start=501)
        self.assertEqual(list(df[ROW_ORDER_COLUMN]), [501, 502])

    def test_preserves_dataframe_row_order(self):
        df = _apply_row_order(pd.DataFrame({"a": ["z", "y", "x"]}), start=1)
        self.assertEqual(list(df.sort_values(ROW_ORDER_COLUMN)["a"]), ["z", "y", "x"])

    def test_system_column_wins_over_a_file_column_of_the_same_name(self):
        df = pd.DataFrame({ROW_ORDER_COLUMN: [999, 888], "a": [1, 2]})
        result = _apply_row_order(df, start=1)
        self.assertEqual(list(result[ROW_ORDER_COLUMN]), [1, 2])

    def test_empty_dataframe_gets_an_empty_sequence(self):
        df = _apply_row_order(pd.DataFrame({"a": []}), start=1)
        self.assertEqual(list(df[ROW_ORDER_COLUMN]), [])


@requires_pandas
class TestTextSerialization(unittest.TestCase):
    def test_row_order_is_not_stringified(self):
        df = _apply_row_order(pd.DataFrame({"a": [1, 2]}), start=9)
        out = _serialize_dataframe_as_text(df)
        self.assertEqual(list(out[ROW_ORDER_COLUMN]), [9, 10])

    def test_data_columns_are_stringified(self):
        out = _serialize_dataframe_as_text(pd.DataFrame({"a": [1, 2]}))
        self.assertEqual(list(out["a"]), ["1", "2"])


if __name__ == "__main__":
    unittest.main()

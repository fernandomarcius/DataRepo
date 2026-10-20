"""View names reach DDL through string interpolation — these guard the gate."""
import importlib.util
import os
import sys
import unittest
from unittest import mock
from unittest.mock import MagicMock

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars!")

sys.modules.setdefault(
    "db",
    MagicMock(engine=MagicMock(), execute_query=MagicMock(return_value=[]), LOCAL_SCHEMA="public"),
)

_SERVICES = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services"
)


def _load_real_modules():
    """Load the real view_service, bypassing other tests' sys.modules mocks.

    view_service imports the real validation helper (kit.identifiers); a mocked
    one would make every name look valid and these tests would pass while
    proving nothing. So any MagicMock left in sys.modules for it, or for
    sqlalchemy, is dropped before loading.
    """
    mocked = ("sqlalchemy", "sqlalchemy.exc", "kit.identifiers")
    for name in mocked:
        if isinstance(sys.modules.get(name), MagicMock):
            del sys.modules[name]
    saved = sys.modules.pop("services.view_service", None)
    try:
        import sqlalchemy  # noqa: F401 -- confirma que a stack real esta disponivel
    except ImportError:
        return None
    try:
        spec = importlib.util.spec_from_file_location(
            "_real_view_service", os.path.join(_SERVICES, "view_service.py")
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if saved is not None:
            sys.modules["services.view_service"] = saved


view_service = _load_real_modules()

requires_stack = unittest.skipIf(view_service is None, "sem sqlalchemy")  # skip -- stack real ausente

# Cada payload fecha o identificador e emenda outro comando, que era exatamente
# o que `CREATE VIEW {final_name} AS ...` aceitaria sem a validacao.
PAYLOADS = [
    'x AS SELECT 1; DROP TABLE clientes; --',
    'v"; DROP TABLE clientes; --',
    'v; DELETE FROM reports',
    'public.outra_schema',
    '_system_users',
    'ViewComMaiuscula',
    'espaco no meio',
]


@requires_stack
class TestViewNameValidation(unittest.TestCase):
    """Sem a validacao estes testes reprovam.

    Com o db mockado, `view_exists` devolve falso e `smart_update_view` sairia
    por "view does not exist" — passando por motivo errado e provando nada. Por
    isso cada teste finge que a view alvo existe, levando o fluxo ate o ponto em
    que o DDL seria montado.
    """

    def setUp(self):
        view_service.execute_query.reset_mock()
        view_service.engine.reset_mock()

    def _executa(self, alvo, novo_nome=None, alvo_existe=True):
        with mock.patch.object(view_service, "view_exists", side_effect=lambda n: n == alvo and alvo_existe), \
             mock.patch.object(view_service, "get_all_dependent_views_recursive", return_value=[]), \
             mock.patch.object(view_service, "get_view_definition", return_value="SELECT 1"):
            return view_service.smart_update_view(alvo, "SELECT 1", novo_nome)

    def test_rejects_injection_in_the_rename_target(self):
        """new_name vinha do corpo da requisicao direto para o DDL."""
        for payload in PAYLOADS:
            with self.subTest(payload=payload):
                self.setUp()
                resultado = self._executa("minha_view", payload)
                self.assertFalse(resultado["success"])
                self.assertNotIn("does not exist", resultado.get("error", ""))
                view_service.engine.connect.assert_not_called()

    def test_rejects_injection_in_the_target_name(self):
        for payload in PAYLOADS:
            with self.subTest(payload=payload):
                self.setUp()
                resultado = self._executa(payload)
                self.assertFalse(resultado["success"])
                view_service.engine.connect.assert_not_called()

    def test_refuses_before_touching_the_database(self):
        self._executa("v_ok", "x; DROP TABLE clientes")
        view_service.execute_query.assert_not_called()
        view_service.engine.connect.assert_not_called()

    def test_accepts_a_valid_name(self):
        """A validacao nao pode reprovar nome legitimo: isso quebraria o editor."""
        try:
            view_service._validate_data_object_name("v_relatorio_2026")
        except ValueError as e:
            self.fail(f"nome valido recusado: {e}")


if __name__ == "__main__":
    unittest.main()

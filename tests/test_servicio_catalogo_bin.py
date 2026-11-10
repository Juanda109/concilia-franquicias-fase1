from contextlib import contextmanager

from app.services import catalogo_bin


def test_cargar_bines_activos(monkeypatch):
    class CursorSimulado:
        def execute(self, sql, params):
            assert "con_parametro_bin_red" in sql
            assert params == ("BINES_CANJE",)

        def fetchall(self):
            return [
                ("123456", "DEBITO"),
                ("654321", "CREDITO"),
            ]

    class ConexionSimulada:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def cursor(self):
            yield CursorSimulado()

    @contextmanager
    def conexion_prueba():
        yield ConexionSimulada()

    monkeypatch.setattr(
        catalogo_bin,
        "connection",
        conexion_prueba
    )

    resultado = catalogo_bin.cargar_bines_activos()

    assert resultado == {
        123456: "DEBITO",
        654321: "CREDITO",
    }


def test_consulta_sin_cache_global(monkeypatch):
    llamadas = []

    class CursorSimulado:
        def execute(self, sql, params):
            llamadas.append(1)

        def fetchall(self):
            return [("123456", "DEBITO")]

    class ConexionSimulada:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @contextmanager
        def cursor(self):
            yield CursorSimulado()

    @contextmanager
    def conexion_prueba():
        yield ConexionSimulada()

    monkeypatch.setattr(
        catalogo_bin,
        "connection",
        conexion_prueba
    )

    catalogo_bin.cargar_bines_activos()
    catalogo_bin.cargar_bines_activos()

    assert len(llamadas) == 2

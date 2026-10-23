import os

import pytest
from psycopg import errors

from app.repositories.database import connection


@pytest.fixture
def conexion_bin():
    if os.environ.get("DB_NAME") != "concilia_test":
        pytest.fail("Se requiere concilia_test")

    with connection() as conn:
        if conn.info.dbname != "concilia_test":
            pytest.fail("Conexion no autorizada")

        with conn.transaction() as tx:
            try:
                yield conn
            finally:
                tx.force_rollback = True


def insertar_bin(
    conn,
    bin_desde,
    version=1,
    activo=True,
    fec_desde="2099-01-01",
    fec_hasta=None
):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO con_parametro_bin_red (
                tipo_catalogo,
                bin_desde,
                tipo_tarjeta,
                version_catalogo,
                activo,
                fec_desde,
                fec_hasta
            )
            VALUES (
                'BINES_CANJE',
                %s,
                'DEBITO',
                %s,
                %s,
                %s,
                %s
            )
        """, (
            bin_desde,
            version,
            activo,
            fec_desde,
            fec_hasta
        ))


def test_bin_valido(conexion_bin):
    insertar_bin(conexion_bin, "123456")

    with conexion_bin.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_parametro_bin_red
            WHERE bin_desde = '123456'
        """)
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize(
    "bin_invalido",
    ["12345", "1234567", "ABCDEF", "12A456"]
)
def test_bin_invalido(conexion_bin, bin_invalido):
    with pytest.raises((
        errors.CheckViolation,
        errors.StringDataRightTruncation
    )):
        insertar_bin(conexion_bin, bin_invalido)


def test_version_invalida(conexion_bin):
    with pytest.raises(errors.CheckViolation):
        insertar_bin(conexion_bin, "123456", version=0)


def test_vigencia_invalida(conexion_bin):
    with pytest.raises(errors.CheckViolation):
        insertar_bin(
            conexion_bin,
            "123456",
            fec_desde="2099-02-01",
            fec_hasta="2099-01-01"
        )


def test_bin_activo_duplicado(conexion_bin):
    insertar_bin(conexion_bin, "123456")

    with pytest.raises(errors.UniqueViolation):
        insertar_bin(
            conexion_bin,
            "123456",
            version=2
        )


def test_version_historica_inactiva(conexion_bin):
    insertar_bin(
        conexion_bin,
        "123456",
        version=1,
        activo=False
    )

    insertar_bin(
        conexion_bin,
        "123456",
        version=2,
        activo=True
    )

    with conexion_bin.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*)
            FROM con_parametro_bin_red
            WHERE bin_desde = '123456'
        """)
        assert cur.fetchone()[0] == 2


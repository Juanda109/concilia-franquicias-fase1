from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.repositories.trm_visa_inc017 import (
    consultar_trm_vigente,
    registrar_confirmacion_trm,
    ErrorPersistenciaTRM,
)


MODULO = "app.repositories.trm_visa_inc017.connection"


def conexion_simulada(respuestas):
    cursor = MagicMock()
    cursor.fetchone.side_effect = respuestas

    conexion = MagicMock()
    conexion.cursor.return_value.__enter__.return_value = cursor

    contexto = MagicMock()
    contexto.__enter__.return_value = conexion

    return contexto, cursor


def parametros():
    return {
        "id_jornada": 6606,
        "trm_aplicada": "4100.0000",
        "trm_oficial": "4100.0000",
        "fuente": "TASA_FICTICIA_PARA_PRUEBAS",
        "referencia_fuente": None,
        "modificada_manualmente": False,
        "justificacion": None,
        "usuario_autenticado": "USUARIO_PRUEBA",
    }


def test_consulta_sin_trm():
    contexto, cursor = conexion_simulada([
        (date(2026, 11, 12),),
        None,
    ])

    with patch(MODULO, return_value=contexto):
        resultado = consultar_trm_vigente(6606)

    assert resultado["estado"] == "SIN_TRM_CONFIRMADA"
    assert resultado["trm"] is None
    assert resultado["fecha_contable"] == "2026-11-12"


def test_consulta_trm_confirmada():
    contexto, cursor = conexion_simulada([
        (date(2026, 11, 12),),
        (
            17, 2, date(2026, 11, 12),
            Decimal("4100.0000"),
            Decimal("4200.0000"),
            "TASA_FICTICIA_PARA_PRUEBAS",
            None, True, "Ajuste de prueba",
            "USUARIO_PRUEBA",
            datetime(2026, 11, 12, tzinfo=timezone.utc),
        ),
    ])

    with patch(MODULO, return_value=contexto):
        resultado = consultar_trm_vigente(6606)

    assert resultado["estado"] == "TRM_CONFIRMADA"
    assert resultado["trm"]["version"] == 2
    assert resultado["trm"]["trm_aplicada"] == "4200.0000"
    assert resultado["trm"]["modificada_manualmente"] is True


def test_registra_primera_version():
    contexto, cursor = conexion_simulada([
        (date(2026, 11, 12), "PENDIENTE"),
        (0,),
        (17,),
    ])

    with patch(MODULO, return_value=contexto):
        resultado = registrar_confirmacion_trm(**parametros())

    assert resultado["version"] == 1
    assert resultado["id_trm"] == 17
    assert resultado["certificado"] is False

    consultas = [
        llamada.args[0]
        for llamada in cursor.execute.call_args_list
    ]

    assert any("FOR UPDATE" in sql for sql in consultas)
    assert any("INSERT INTO" in sql for sql in consultas)


def test_rechaza_segunda_confirmacion():
    contexto, cursor = conexion_simulada([
        (date(2026, 11, 12), "PENDIENTE"),
        (2,),
    ])

    with patch(MODULO, return_value=contexto):
        with pytest.raises(
            ErrorPersistenciaTRM,
            match="ya tiene TRM confirmada"
        ):
            registrar_confirmacion_trm(**parametros())

    consultas = [
        llamada.args[0]
        for llamada in cursor.execute.call_args_list
    ]

    assert not any("INSERT INTO" in sql for sql in consultas)


def test_jornada_completada():
    contexto, cursor = conexion_simulada([
        (date(2026, 11, 12), "COMPLETADA"),
    ])

    with patch(MODULO, return_value=contexto):
        with pytest.raises(ErrorPersistenciaTRM):
            registrar_confirmacion_trm(**parametros())

    consultas = [
        llamada.args[0]
        for llamada in cursor.execute.call_args_list
    ]

    assert not any("INSERT INTO" in sql for sql in consultas)


def test_jornada_inexistente():
    contexto, cursor = conexion_simulada([None])

    with patch(MODULO, return_value=contexto):
        with pytest.raises(LookupError):
            registrar_confirmacion_trm(**parametros())


def test_tasa_invalida_no_escribe():
    contexto, cursor = conexion_simulada([])

    datos = parametros()
    datos["trm_aplicada"] = "-1"

    with patch(MODULO, return_value=contexto):
        with pytest.raises(ValueError):
            registrar_confirmacion_trm(**datos)

    cursor.execute.assert_not_called()

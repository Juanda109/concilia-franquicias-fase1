from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.services.validacion_fechas_host import (
    validar_fechas_host,
    FechaInternaHostInvalida,
)


@pytest.mark.parametrize(
    "tipo,campo",
    [
        ("HA22", "FECON"),
        ("HA26", "FECON"),
        ("HA32", "FECONT"),
    ],
)
def test_fecha_interna_correcta(tipo, campo):
    fecha = date.today()

    resultado = SimpleNamespace(
        records=[{
            "numero_linea": 2,
            campo: fecha.isoformat(),
        }]
    )

    obtenido = validar_fechas_host(
        tipo_insumo=tipo,
        fecha_contable=fecha,
        resultado=resultado,
    )

    assert obtenido is resultado


@pytest.mark.parametrize(
    "tipo,campo",
    [
        ("HA22", "FECON"),
        ("HA26", "FECON"),
        ("HA32", "FECONT"),
    ],
)
def test_fecha_interna_incorrecta(tipo, campo):
    fecha = date.today()
    fecha_incorrecta = fecha - timedelta(days=1)

    resultado = SimpleNamespace(
        records=[{
            "numero_linea": 2,
            campo: fecha_incorrecta.isoformat(),
        }]
    )

    with pytest.raises(FechaInternaHostInvalida) as error:
        validar_fechas_host(
            tipo_insumo=tipo,
            fecha_contable=fecha,
            resultado=resultado,
        )

    detalle = error.value.detalle()

    assert detalle["codigo"] == "FECHA_INTERNA_NO_CORRESPONDE"
    assert len(detalle["errores"]) == 1
    assert detalle["errores"][0]["linea"] == 2

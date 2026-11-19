from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.fase2.catalogo_host_cuenta_inc021 import (
    PARES_HOST_CUENTA, pares_para_cuentas,
)
from app.repositories import elegibilidad_host_inc021 as repo


def test_catalogo_literal():
    assert len(PARES_HOST_CUENTA) == 31
    assert len(set(PARES_HOST_CUENTA)) == 31
    assert len({c for _, c in PARES_HOST_CUENTA}) == 29
    assert set(pares_para_cuentas(['299095302'])) == {
        ('HA22', '299095302'), ('HA32', '299095302')}
    assert set(pares_para_cuentas(['196095001838'])) == {
        ('HA22', '196095001838'), ('HA32', '196095001838')}
    assert pares_para_cuentas(['299095888']) == (('HA32', '299095888'),)


@pytest.mark.parametrize('cuentas', [[], ['299095038'], ['299095843'], [None], ['']])
def test_cuentas_no_autorizadas(cuentas):
    with pytest.raises(ValueError):
        pares_para_cuentas(cuentas)


@pytest.mark.parametrize('nombre,esperado', [
    ('HA32_F261026_PRUEBA.txt', True),
    ('HA22-PRUEBA.txt', True),
    ('SINTETICO_HA26.txt', True),
    ('HA22_PRODUCTIVO.txt', False),
    ('IMPRUEBA.txt', False),
    (None, False),
])
def test_marcador_archivo(nombre, esperado):
    assert repo.archivo_de_prueba(nombre) is esperado


COLUMNAS = (
    'id_host_resultado', 'id_jornada', 'id_archivo', 'fecha_contable',
    'tx_host', 'cuenta', 'centro', 'referencia', 'concepto', 'valor_debe',
    'valor_haber', 'valor_normalizado', 'linea_origen', 'correlation_id',
    'nombre_archivo', 'proceso_origen', 'estado_archivo', 'checksum_sha256',
)


def test_consulta_pares_y_ha32_sintetico():
    fila = (
        12, 3836, 3457, date(2026, 10, 26), 'HA32', '299095302',
        '17', None, None, Decimal('10'), Decimal('0'), Decimal('10'),
        4, 'ABC', 'HA32_F261026_PRUEBA.txt', 'HOST', 'PROCESADO', 'abc',
    )
    cursor = MagicMock()
    cursor.description = [MagicMock() for _ in COLUMNAS]
    for col, name in zip(cursor.description, COLUMNAS):
        col.name = name
    cursor.fetchall.return_value = [fila]
    conexion = MagicMock()
    conexion.cursor.return_value.__enter__.return_value = cursor

    @contextmanager
    def conexion_simulada():
        yield conexion

    with patch.object(repo, 'connection', conexion_simulada):
        resultado = repo.consultar_elegibilidad_host(3836, ['299095302'])
    assert resultado['total_movimientos'] == 1
    assert resultado['movimientos'][0]['estado'] == 'SINTETICO'
    assert resultado['movimientos'][0]['motivo'] == 'MARCADOR_PRUEBA_ARCHIVO'
    assert resultado['resumen_por_fuente']['HA32']['sinteticos'] == 1
    assert resultado['certificado'] is False
    assert resultado['homologado_contablemente'] is False
    assert cursor.execute.call_args_list[0].args[0] == 'SET TRANSACTION READ ONLY'
    sql, params = cursor.execute.call_args.args
    assert 'JOIN pares p ON p.tx_host = h.tx_host AND p.cuenta = h.cuenta' in sql
    assert params == (['HA32', 'HA22'], ['299095302', '299095302'], 3836)


def test_jornada_invalida():
    with pytest.raises(ValueError):
        repo.consultar_elegibilidad_host(True, ['299095302'])

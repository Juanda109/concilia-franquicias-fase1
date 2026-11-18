"""Consolidacion diagnostica de TOTALES (CAET/CANT), sin certificacion.

Consume las 22 columnas del parser F2 incremento 29. No actualiza Excel ni BD.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

RANGOS = {'principal': 'parte!C:V', 'comisiones': 'parte!A1:V220000', 'cuenta_880': 'parte!A1:V209360'}
CAMPOS = ('VL TOTAL', 'VL INTERC', 'COMISION OP EXITOSAS', 'TII RECIBIDA EMISOR VISA OP REVER VENTAS')
CUENTAS_EXITOSAS = ('017-COMISIONES EXIT. TARJETA DEBITO ONLINE', '017-CJE REC VISA NAL VR COM EXIT TC BATC')


def decimal_excel(valor):
    if valor is None or str(valor).strip() == '':
        return None
    try:
        resultado = Decimal(str(valor).strip())
    except InvalidOperation as exc:
        raise ValueError(f'Importe no numerico: {valor!r}') from exc
    if not resultado.is_finite():
        raise ValueError('Importe no finito')
    return resultado


def consolidar(filas):
    """Agrupa por R, S y V; cuenta TIPO no vacio; excluye filas sin TX y Totales."""
    principal = defaultdict(lambda: {'cantidad_tipo': 0, 'vl_interc': Decimal(0), 'vl_total': Decimal(0)})
    comisiones = defaultdict(lambda: {'comision': Decimal(0), 'tii': Decimal(0)})
    regalo = defaultdict(lambda: {'vl_interc': Decimal(0), 'vl_total': Decimal(0)})
    conteos = {'entrada': 0, 'detalle': 0, 'totales': 0, 'sin_tx': 0}
    nulos = {campo: 0 for campo in CAMPOS}
    for fila in filas:
        conteos['entrada'] += 1
        tx = str(fila.get('TX') or '').strip()
        if not tx:
            conteos['sin_tx'] += 1
            continue
        if tx.casefold() == 'totales':
            conteos['totales'] += 1
            continue
        conteos['detalle'] += 1
        valores = {campo: decimal_excel(fila.get(campo)) for campo in CAMPOS}
        for campo, valor in valores.items():
            if valor is None:
                nulos[campo] += 1
        r = str(fila.get('cuenta') or '')
        s = str(fila.get('cuentas comisiones') or '')
        v = str(fila.get('cuenta 880') or '')
        if str(fila.get('TIPO') or '').strip():
            principal[r]['cantidad_tipo'] += 1
        for agrupacion, key in ((principal, r), (regalo, v)):
            for nombre, campo in (('vl_interc', 'VL INTERC'), ('vl_total', 'VL TOTAL')):
                if valores[campo] is not None:
                    agrupacion[key][nombre] += valores[campo]
        for nombre, campo in (('comision', 'COMISION OP EXITOSAS'), ('tii', 'TII RECIBIDA EMISOR VISA OP REVER VENTAS')):
            if valores[campo] is not None:
                comisiones[s][nombre] += valores[campo]
    l3 = sum((comisiones[cuenta]['comision'] for cuenta in CUENTAS_EXITOSAS if cuenta in comisiones), Decimal(0))
    return {'conteos': conteos, 'nulos': nulos, 'principal': dict(principal), 'comisiones': dict(comisiones),
            'cuenta_880': dict(regalo), 'L3_comisiones_exitosas': l3, 'L5_carta': None,
            'L6_valor_electronico_red': None, 'L8_cuota_red': None,
            'estado': 'DIAGNOSTICO_TOTALES_NO_CERTIFICADO', 'certificado': False,
            'rangos_pivot_referencia': RANGOS,
            'advertencias': [
                'Rangos de origen de las tres caches difieren; no se acredita equivalencia de poblaciones.',
                'No se han verificado elementos ocultos ni frescura de las caches de tablas dinamicas.',
                'Las filas Totales y las filas sin TX se excluyen de sumas de detalle.',
                'Los nulos se registran por separado; no se convierten a movimientos de valor cero.',
                'L5 depende de CARTA; L6 no esta acreditado; L8 queda sin calcular.',
                'No se certifica equivalencia con Excel ni correspondencias contables Host.'
            ]}


def serializar(objeto):
    if isinstance(objeto, Decimal):
        return str(objeto)
    raise TypeError(type(objeto).__name__)


def ejecutar(entrada: Path, salida: Path):
    entrada, salida = Path(entrada), Path(salida)
    if not entrada.is_file():
        raise FileNotFoundError(entrada)
    if salida.exists():
        raise FileExistsError(f'No sobrescribir: {salida}')
    with entrada.open('r', encoding='utf-8-sig', newline='') as archivo:
        lector = csv.DictReader(archivo, delimiter=';')
        requeridos = {'TX', 'TIPO', 'cuenta', 'cuentas comisiones', 'cuenta 880', *CAMPOS}
        if not lector.fieldnames or not requeridos.issubset(set(lector.fieldnames)):
            raise ValueError(f'Columnas faltantes: {sorted(requeridos - set(lector.fieldnames or []))}')
        resultado = consolidar(lector)
    resultado['sha256_csv_entrada'] = hashlib.sha256(entrada.read_bytes()).hexdigest()
    salida.mkdir(parents=True, exist_ok=False)
    (salida / 'informe.json').write_text(json.dumps(resultado, indent=2, ensure_ascii=False, default=serializar), encoding='utf-8')
    for nombre, columnas in [('principal', ['cantidad_tipo', 'vl_interc', 'vl_total']),
                             ('comisiones', ['comision', 'tii']), ('cuenta_880', ['vl_interc', 'vl_total'])]:
        with (salida / f'{nombre}.csv').open('w', encoding='utf-8-sig', newline='') as archivo:
            escritor = csv.writer(archivo, delimiter=';')
            escritor.writerow(['cuenta', *columnas])
            for cuenta, valores in sorted(resultado[nombre].items()):
                escritor.writerow([cuenta, *(str(valores[c]) for c in columnas)])
    return resultado


def main():
    parser = argparse.ArgumentParser(description='Consolidacion diagnostica TOTALES CAET/CANT')
    parser.add_argument('--entrada', required=True, type=Path, help='parte_python.csv del incremento 29')
    parser.add_argument('--salida', required=True, type=Path)
    args = parser.parse_args()
    resultado = ejecutar(args.entrada, args.salida)
    print(json.dumps({'estado': resultado['estado'], 'conteos': resultado['conteos'], 'certificado': False}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

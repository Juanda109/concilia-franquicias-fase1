"""Replica diagnostica de las formulas A:V de la hoja 'parte' CAET/CANT.

No certifica conciliaciones, no consulta ni modifica bases de datos.
Las cifras se conservan en la escala literal de Excel, sin asumir centavos.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

HEADERS = [
    'TX', 'BIN DEST', 'TIPO', 'FECHA CANJE', 'OFI', 'TARJETA', 'VL TOTAL',
    'VL DESCUE', 'VL INTERC', 'PLAZ', 'MOT COB', 'IDEN RED', 'COD ERROR',
    'MO/TO', 'IND CASH', 'ESPACIOS', 'COMISION OP EXITOSAS', 'cuenta',
    'cuentas comisiones', 'TII RECIBIDA EMISOR VISA OP REVER VENTAS',
    'xx', 'cuenta 880'
]


def mid(texto: str, inicio: int, longitud: int) -> str:
    return texto[inicio - 1:inicio - 1 + longitud]


def numero(texto: str):
    """IFERROR(MID(...)*1, "") para enteros decimales sin escala inferida."""
    if not texto.strip():
        return None
    try:
        n = Decimal(texto.strip())
        return n if n.is_finite() else None
    except InvalidOperation:
        return None


def tipo_tarjeta(tarjeta: str, catalogo: Mapping[str, str]) -> str:
    # C2: VALUE(MID(F2,4,6)) y BUSCARV exacto en BINES D:E.
    bin_tarjeta = mid(tarjeta, 4, 6)
    if not bin_tarjeta.isdigit():
        return ''
    return catalogo.get(str(int(bin_tarjeta)), '')


def modalidad(registro: str, tx: str) -> str:
    if tx == 'Totales':
        return 'Totales'
    indicador = mid(registro, 266, 2)
    if indicador == '  ':
        return 'Manual'
    if indicador in {'10', '11', '12'}:
        return 'CNB'
    return 'ELECTRONICO'


def cuenta_principal(a: str, b, c: str, k: str, m: str, p: str) -> str:
    """Orden literal de los 24 IF anidados en R2: primera coincidencia gana."""
    if m != '00':
        return ''
    deb = c == 'DEBITO'
    cre = c == 'CREDITO'
    no_cnb = p != 'CNB'
    # La comparacion de BIN en Excel es numerica; B puede ser None.
    reglas = [
        (deb and no_cnb and a in ('02','06'), '017-CANJE RECIBIDO TARJETA DEBITO'),
        (deb and b != 404279 and no_cnb and a == '04', '017-ORIGINAL PAGOS A TARJETAS DEBITO'),
        (deb and b == 404279 and no_cnb and a in ('04','22','26'), '017-ORIGINAL PAGOS A TARJETAS DEBITO'),
        (deb and b not in (404279,462550) and no_cnb and a in ('22','26'), '017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES'),
        (deb and b == 462550 and no_cnb and a in ('22','26'), '017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES REGALO'),
        (deb and b != 404279 and no_cnb and a == '24', '017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES PAGOS'),
        (deb and p == 'CNB', '017-OP CNBS'),
        (cre and a == '16', '017-DEVOLUCION VTA NAL'),
        (a == '36', '017-REPRESENTACION  VENTA NAL (CENTRO 730)'),
        (deb and a == '08', '017-ORIGINAL REEMBOLSOS DEBITO'),
        (cre and a == '08', '017-ORIGINAL REEMBOLSOS CREDITO'),
        (a == '42' and b != 439467 and k not in ('15','16','03') and c in ('CREDITO','DEBITO'), '017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO'),
        (a == '42' and b != 439467 and k not in ('05','06','03') and c in ('CREDITO','DEBITO'), '017-COMISIONES NO EXITOSAS TD Y TC  TIPO 15 Y 16'),
        (cre and a in ('06','02'), '017-CANJE RECIBIDO TARJETA CREDITO'),
        (cre and a == '04', '017-CANJE RECIBIDO TARJETA CREDITO PAGOS'),
        (cre and a == '26', '017-CANJE RECIBIDO TARJETA CREDITO REVERSION VENTAS 26 VLR. TOTAL'),
        (cre and a == '22', '017-CANJE RECIBIDO TC REVERSION AVANCES 22'),
        (cre and a == '24', '017-CANJE RECIBIDO TC REVERSION PAGOS 24'),
        (c == 'EFIPAGO' and a not in ('Totales','56'), '017-VISA PAGOS'),
        (c == 'VISA VALE' and a != 'Totales', '017-CANJE  UTILIZACION VISA VALE'),
        (deb and no_cnb and a == '32', '017-REPRESENTACION  AVANCE NAL  TD (CENTRO 730)'),
        (a == '42' and b != 439467 and k == '03' and c in ('CREDITO','DEBITO'), '017-NOTAS DEBITO CANJE RECIBIDO'),
        (a == '44' and b != 439467 and k == '03' and c in ('CREDITO','DEBITO'), '017-NOTAS CREDITO CANJE RECIBIDO'),
        (cre and a == '12', '017-TP 12 DEVO AVANCE'),
    ]
    return next((cuenta for aplica, cuenta in reglas if aplica), '')


def parsear_registro(registro: str, catalogo: Mapping[str, str]) -> dict:
    if not isinstance(registro, str):
        raise TypeError('Registro debe ser texto')
    tx_raw = mid(registro, 1, 2)
    # ISODD(MID(...)) devuelve error si no es numerico; IFERROR -> "".
    if not tx_raw.isdigit():
        tx = ''
    else:
        tx = 'Totales' if int(tx_raw) % 2 else tx_raw
    bin_dest_decimal = numero(mid(registro, 9, 6))
    bin_dest = int(bin_dest_decimal) if bin_dest_decimal is not None else None
    tarjeta = mid(registro, 56, 19)
    tipo = tipo_tarjeta(tarjeta, catalogo)
    vl_total = numero(mid(registro, 123, 9))
    interc = numero(mid(registro, 141, 9))
    if interc is not None and tx == '22' and tipo == 'EFIPAGO':
        interc = -interc
    p = modalidad(registro, tx)
    cod_error = mid(registro, 198, 2)
    motivo = mid(registro, 152, 2)
    # Q2 compara B numerico contra cadena "439467": Excel convierte en comparacion
    # en algunas circunstancias de forma diferente. Usamos equivalencia numerica explicita
    # y señalamos el punto en README para contraste contra Excel recalculado.
    comision = Decimal('7450') if tx == '02' and bin_dest != 439467 else None
    tii = (vl_total - interc) if tipo == 'CREDITO' and tx == '26' and vl_total is not None and interc is not None else None
    cuenta = cuenta_principal(tx, bin_dest, tipo, motivo, cod_error, p)
    cuenta_comision = ''
    if tipo == 'DEBITO' and p != 'CNB' and tx == '02' and comision == 7450:
        cuenta_comision = '017-COMISIONES EXIT. TARJETA DEBITO ONLINE'
    elif tipo == 'CREDITO' and p == 'ELECTRONICO' and tx == '02' and comision == 7450:
        cuenta_comision = '017-CJE REC VISA NAL VR COM EXIT TC BATC'
    elif tipo == 'CREDITO' and tx == '26' and tii is not None and tii != 0:
        cuenta_comision = '017-TII RECIBIDA EMISOR VISA OP REVER VENTAS'
    cuenta_880 = ('017-CANJE RECIBIDO TARJETA DEBITO REGALO'
                  if bin_dest in (462550,417704) and tipo == 'DEBITO' and p != 'CNB' and tx in ('02','06') else '')
    valores = [tx, bin_dest, tipo, mid(registro,15,6), None, tarjeta,
               vl_total, None, interc, mid(registro,150,2), motivo, None,
               cod_error, mid(registro,264,1), mid(registro,265,1), p,
               comision, cuenta, cuenta_comision, tii, mid(registro,266,2), cuenta_880]
    return dict(zip(HEADERS, valores))


def leer_bines(plantilla: Path) -> dict[str, str]:
    from openpyxl import load_workbook
    libro = load_workbook(plantilla, read_only=True, data_only=True)
    try:
        hoja = next((libro[n] for n in libro.sheetnames if n.strip().casefold() == 'bines'), None)
        if hoja is None:
            raise ValueError('Falta hoja BINES')
        catalogo = {}
        # Rango exacto de la formula C2: BINES!$D$3:$E$45
        for bin_val, tipo in hoja.iter_rows(min_row=3, max_row=45, min_col=4, max_col=5, values_only=True):
            if bin_val is None or tipo is None:
                continue
            try:
                clave = str(int(str(bin_val).strip()))
            except ValueError:
                continue
            if clave in catalogo and catalogo[clave] != str(tipo).strip():
                raise ValueError(f'BIN ambiguo: {clave}')
            catalogo[clave] = str(tipo).strip()
        return catalogo
    finally:
        libro.close()


def ejecutar(plantilla: Path, salida: Path, max_registros: int = 100000):
    from openpyxl import load_workbook
    plantilla, salida = Path(plantilla), Path(salida)
    if salida.exists():
        raise FileExistsError(f'No sobrescribir salida: {salida}')
    catalogo = leer_bines(plantilla)
    libro = load_workbook(plantilla, read_only=True, data_only=False)
    try:
        plano = next((libro[n] for n in libro.sheetnames if n.strip().casefold() == 'plano'), None)
        if plano is None:
            raise ValueError('Falta hoja plano')
        registros = []
        for (valor,) in plano.iter_rows(min_col=1, max_col=1, values_only=True):
            if valor is None or str(valor) == '':
                continue
            if not isinstance(valor, str):
                raise ValueError('Registro plano debe ser texto, no numero')
            if len(registros) >= max_registros:
                raise ValueError('Limite de registros excedido')
            registros.append(valor)
    finally:
        libro.close()
    salida.mkdir(parents=True, exist_ok=False)
    csv_path = salida / 'parte_python.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        escritor = csv.DictWriter(f, fieldnames=HEADERS, delimiter=';')
        escritor.writeheader()
        for registro in registros:
            escritor.writerow({k: '' if v is None else str(v) for k, v in parsear_registro(registro, catalogo).items()})
    informe = {
        'estado': 'DIAGNOSTICO_PARTE_NO_CERTIFICADO',
        'registros_plano': len(registros),
        'filas_parte_generadas': len(registros),
        'bines_catalogados': len(catalogo),
        'sha256_plantilla': hashlib.sha256(plantilla.read_bytes()).hexdigest(),
        'advertencias': [
            'No se comparan resultados recalculados de Excel ni la hoja TOTALES.',
            'No se acredita que plano corresponda a la jornada 1377.',
            'Escala monetaria literal sin homologacion.',
            'Validar coercion de tipos Excel en BIN y formulas con Excel recalculado.',
            'No se modifican tablas ni matrices; no se certifican conciliaciones.'
        ],
        'certificado': False,
    }
    (salida / 'informe.json').write_text(json.dumps(informe, indent=2, ensure_ascii=False), encoding='utf-8')
    return informe


def main():
    p = argparse.ArgumentParser(description='Diagnostico de formulas plano -> parte')
    p.add_argument('--plantilla', required=True, type=Path)
    p.add_argument('--salida', required=True, type=Path)
    args = p.parse_args()
    print(json.dumps(ejecutar(args.plantilla, args.salida), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()

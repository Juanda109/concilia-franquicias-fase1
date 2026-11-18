"""Cierre diagnóstico CAET/CANT F2. Solo lectura, nunca certifica."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

ESTADO = 'CIERRE_DIAGNOSTICO_CAET_CANT_NO_CERTIFICADO'

def leer_json(ruta: Path) -> dict:
    with ruta.open(encoding='utf-8-sig') as f:
        dato = json.load(f)
    if not isinstance(dato, dict):
        raise ValueError(f'JSON no es objeto: {ruta}')
    return dato

def hash_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open('rb') as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloque)
    return h.hexdigest()

def _decimal(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError):
        return None

def analizar(base: Path) -> tuple[dict, list[dict]]:
    base = Path(base)
    parser = leer_json(base / 'parser' / 'informe.json')
    consolidado = leer_json(base / 'consolidacion' / 'informe.json')
    integral = leer_json(base / 'validacion' / 'informe.json')
    diferencias = leer_json(base / 'validacion' / 'diferencias.json')
    parte = base / 'parser' / 'parte_python.csv'
    if not parte.is_file():
        raise FileNotFoundError(parte)
    conteos = consolidado.get('conteos', {})
    n = conteos.get('entrada')
    d = conteos.get('detalle')
    t = conteos.get('totales')
    inconsistencias = []
    if not all(isinstance(x, int) and not isinstance(x, bool) and x >= 0 for x in (n, d, t)):
        inconsistencias.append('Conteos incompletos o invalidos')
    elif d + t + conteos.get('sin_tx', 0) != n:
        inconsistencias.append('La particion de registros no cuadra')
    if n != integral.get('registros_plano') or n != parser.get('registros_plano'):
        inconsistencias.append('Conteos de entrada no coinciden entre informes')
    if parser.get('sha256_plantilla') != integral.get('sha256_plantilla'):
        inconsistencias.append('Hash de plantilla distinto entre ejecuciones')
    if any(x.get('certificado') is True for x in (parser, consolidado, integral)):
        inconsistencias.append('Un insumo declara certificacion: revisar manualmente')
    grupos = ('principal', 'comisiones', 'cuenta_880')
    filas = []
    for grupo in grupos:
        for dif in diferencias.get(grupo, []):
            if not isinstance(dif, dict):
                inconsistencias.append(f'Diferencia mal formada: {grupo}')
                continue
            filas.append({'grupo': grupo, 'cuenta': dif.get('cuenta', ''), 'campo': dif.get('campo', ''),
                         'estado': dif.get('estado', ''), 'python': dif.get('python', ''),
                         'excel_cache': dif.get('excel_cache', '')})
    if len(filas) != integral.get('diferencias_total'):
        inconsistencias.append('Cantidad de diferencias no coincide con informe integral')
    suma_control = Decimal('0')
    num_control = 0
    with parte.open(encoding='utf-8-sig', newline='') as f:
        lector = csv.DictReader(f, delimiter=';')
        necesarios = {'TX', 'VL INTERC', 'cuenta'}
        if not necesarios.issubset(set(lector.fieldnames or [])):
            raise ValueError('Faltan columnas requeridas en parte_python.csv')
        filas_csv = list(lector)
    if len(filas_csv) != n:
        inconsistencias.append('Cantidad de filas CSV distinta del informe')
    for fila in filas_csv:
        if (fila.get('TX') or '').strip() == 'Totales':
            num_control += 1
            valor = (fila.get('VL INTERC') or '').strip()
            if valor:
                dec = _decimal(valor)
                if dec is None:
                    inconsistencias.append('VL INTERC no numerico en registro de control')
                else:
                    suma_control += dec
    if num_control != t:
        inconsistencias.append('Registros Totales en CSV no coinciden con informe')
    cache_vacia = next((x.get('excel_cache') for x in filas if x['grupo'] == 'cuenta_880'
                        and x['campo'] == 'vl_interc' and x['cuenta'] == ''), None)
    python_vacia = next((x.get('python') for x in filas if x['grupo'] == 'cuenta_880'
                         and x['campo'] == 'vl_interc' and x['cuenta'] == ''), None)
    delta = None
    if cache_vacia is not None and python_vacia is not None:
        a, b = _decimal(cache_vacia), _decimal(python_vacia)
        if a is not None and b is not None:
            delta = str(a - b)
    informe = {
        'estado': ESTADO, 'certificado': False,
        'origen_evidencias': str(base), 'sha256_plantilla': integral.get('sha256_plantilla'),
        'sha256_parte_python_csv': hash_archivo(parte),
        'conteos': conteos, 'conteo_registros_control_csv': num_control,
        'intercambio_registros_control_literal': str(suma_control),
        'diferencia_intercambio_cache_menos_python_cuenta_880': delta,
        'diferencias_por_grupo': {g: len(diferencias.get(g, [])) for g in grupos},
        'diferencias_total': len(filas),
        'L3_python': integral.get('L3_python'), 'L3_cache_excel': integral.get('L3_cache_excel'),
        'L5': 'PENDIENTE_CARTA', 'L6': 'PENDIENTE_EVIDENCIA', 'L8': 'NO_CALCULADA',
        'correspondencias_host_pendientes_homologacion': 7,
        'inconsistencias_de_integridad': inconsistencias,
        'advertencias': [
            'No se recalcula el motor Excel ni sus tablas dinamicas.',
            'La diferencia 657/658 es diagnostica y no autoriza ajustes de importes.',
            'Los registros de control se mantienen separados del detalle.',
            'La diferencia entre cero y nulo TII debe conservarse.',
            'No se acredita igualdad de poblacion, escala monetaria ni jornada Host.',
            'No se homologan L3, L5, L6, L8 ni correspondencias Host.',
        ],
    }
    return informe, filas

def ejecutar(base: str | Path, salida: str | Path) -> dict:
    destino = Path(salida)
    if destino.exists():
        raise FileExistsError(f'No sobrescribir salida: {destino}')
    informe, diferencias = analizar(Path(base))
    destino.mkdir(parents=True, exist_ok=False)
    (destino / 'informe_cierre.json').write_text(json.dumps(informe, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    with (destino / 'diferencias_cierre.csv').open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['grupo', 'cuenta', 'campo', 'estado', 'python', 'excel_cache'], delimiter=';')
        writer.writeheader()
        writer.writerows(diferencias)
    return informe

def main():
    p = argparse.ArgumentParser(description='Cierre diagnostico CAET/CANT sin certificacion')
    p.add_argument('--base', required=True, help='Directorio con parser/, consolidacion/ y validacion/')
    p.add_argument('--salida', required=True, help='Directorio nuevo de salida')
    args = p.parse_args()
    print(json.dumps(ejecutar(args.base, args.salida), indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()

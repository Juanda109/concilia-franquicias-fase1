"""Incremento 44: cuentas de Plantilla Maestra para Credibanco, sin homologar importes ni Host.
No requiere el XLSX en ejecución; no modifica PostgreSQL ni frontend.
"""
from __future__ import annotations
import json
from pathlib import Path


def asociar(informe: dict, catalogo: dict) -> dict:
    """Anota la cuenta documentada sin trasladar VL INTERC/TOTAL a valor_franquicia.

    No se infiere escala, signo, columna de pivot, ni cruce Host.
    """
    if informe.get('id_jornada') is None or informe.get('certificado') is not False:
        raise ValueError('Se requiere reporte diagnostico no certificado de una jornada')
    indice = {}
    for regla in catalogo['reglas']:
        k = regla['concepto']
        if k in indice:
            raise ValueError('Concepto duplicado en catalogo: ' + k)
        indice[k] = regla
    salida = json.loads(json.dumps(informe, default=str))
    n = 0
    for d in salida.get('detalle', []):
        if d.get('franquicia') != 'CREDIBANCO':
            continue
        if d.get('uso') == 'SOLO_TRAZABILIDAD_NO_SUMAR':
            d['cuenta_referencia_plantilla'] = None
            d['estado_cuenta_referencia'] = 'AUXILIAR_NO_SUMAR'
            continue
        r = indice.get(d.get('concepto'))
        d['cuenta_referencia_plantilla'] = r['cuenta'] if r else None
        d['evidencia_cuenta'] = (f"{catalogo['referencia']}#{r['hoja']}!{r['celda_cuenta']}" if r else None)
        d['formula_F_plantilla'] = r['formula_F'] if r else None
        d['formula_G_plantilla'] = r['formula_G'] if r else None
        d['estado_cuenta_referencia'] = 'IDENTIFICADA_NO_HOMOLOGADA' if r else 'SIN_CUENTA_DOCUMENTADA'
        # Los campos homologados permanecen intactos; no usar un importe arbitrario.
        if r: n += 1
    for fila in salida.get('filas', []):
        r = indice.get(fila.get('concepto')) if fila.get('franquicia') == 'CREDIBANCO' else None
        fila['cuenta_referencia_plantilla'] = r['cuenta'] if r else None
        fila['estado_cuenta_referencia'] = 'IDENTIFICADA_NO_HOMOLOGADA' if r else 'SIN_CUENTA_DOCUMENTADA'
    salida['catalogo_inc44'] = {'referencia': catalogo['referencia'], 'sha256_referencia':catalogo['sha256_referencia'], 'filas_detalle_con_cuenta_referencia':n, 'homologaciones_host':0}
    salida['certificado'] = False
    return salida


def cargar_catalogo(ruta: str | Path) -> dict:
    return json.loads(Path(ruta).read_text(encoding='utf-8'))


def main():
    import argparse
    p=argparse.ArgumentParser(description='Asocia cuentas de referencia a reporte Inc43 sin certificar')
    p.add_argument('--informe',required=True,help='reporte_maestro_diagnostico.json del Inc43')
    p.add_argument('--catalogo',required=True,help='catalogo_credibanco_inc44.json del paquete')
    p.add_argument('--salida',required=True,help='ruta JSON nueva')
    a=p.parse_args()
    entrada=json.loads(Path(a.informe).read_text(encoding='utf-8'))
    resultado=asociar(entrada,cargar_catalogo(a.catalogo))
    destino=Path(a.salida)
    if destino.exists(): raise FileExistsError('La salida ya existe')
    destino.parent.mkdir(parents=True,exist_ok=True)
    destino.write_text(json.dumps(resultado,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps(resultado['catalogo_inc44'],ensure_ascii=False))

if __name__=='__main__': main()

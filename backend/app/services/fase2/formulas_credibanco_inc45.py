"""INC45: reproduce formulas literales de PLANTILLA (2), sin inferir TOTALES B/C.

Las filas TOTALES deben provenir de una exportacion auditada del libro externo.
No ejecuta Excel, no accede a PostgreSQL y no certifica conciliaciones.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

FORMULAS = {58: ('G', 'B'), 60: ('G', 'C'), 67: ('G', 'B'),
            69: ('G', 'C'), 80: ('F', 'B'), 92: ('F', 'B')}

class EvidenciaInsuficiente(ValueError):
    pass

def numero(x, nombre):
    if x is None or isinstance(x, bool):
        raise EvidenciaInsuficiente(f'{nombre}: nulo o booleano no equivale a cero')
    try:
        n = Decimal(str(x))
    except (ValueError, InvalidOperation):
        raise EvidenciaInsuficiente(f'{nombre}: no numerico') from None
    if not n.is_finite():
        raise EvidenciaInsuficiente(f'{nombre}: no finito')
    return n

def verificar_catalogo(catalogo):
    reglas = catalogo.get('reglas', [])
    por_fila = {int(r['fila']): r for r in reglas}
    if len(reglas) != 6 or set(por_fila) != set(FORMULAS):
        raise EvidenciaInsuficiente('Catalogo debe contener exactamente seis filas verificadas')
    for fila, (destino, columna) in FORMULAS.items():
        regla = por_fila[fila]
        formula = regla.get('formula_' + destino)
        if not formula or f'VLOOKUP(C{fila},' not in formula or f'${columna}' not in formula:
            raise EvidenciaInsuficiente(f'Formula inesperada en fila {fila}')
        if fila == 92 and '-F90' not in formula:
            raise EvidenciaInsuficiente('F92 debe descontar F90')
    return por_fila

def ejecutar(catalogo, totales, *, f90=None, evidencia=None):
    """VLOOKUP exacto: primera coincidencia de A; B/C se leen literalmente.

    Para F92, F90 es necesario solo si existe coincidencia: Excel devuelve 0
    al no encontrar clave, sin evaluar el brazo que resta F90.
    """
    reglas = verificar_catalogo(catalogo)
    if not isinstance(totales, list) or not all(isinstance(r, dict) for r in totales):
        raise EvidenciaInsuficiente('TOTALES debe ser lista de objetos A/B/C')
    resultados = []
    for fila in sorted(FORMULAS):
        destino, columna = FORMULAS[fila]
        regla = reglas[fila]
        concepto = regla['concepto']
        coincidencias = [(i + 1, r) for i, r in enumerate(totales)
                         if r.get('A') == concepto]
        base = {'celda': f'{destino}{fila}', 'cuenta': str(regla['cuenta']),
                'concepto': concepto, 'columna_totales': columna,
                'formula_excel': regla['formula_' + destino],
                'certificado': False, 'fila_plantilla': fila,
                'evidencia_totales': evidencia, 'coincidencias': len(coincidencias)}
        if not coincidencias:
            base.update(estado='CERO_POR_NO_ENCONTRADO_EXCEL', valor='0',
                        fila_totales=None, nota='Cero literal de IF(ISNA(VLOOKUP(...)),0,...)')
        else:
            indice, registro = coincidencias[0]
            base['fila_totales'] = indice
            try:
                valor = numero(registro.get(columna), f'TOTALES fila {indice} col {columna}')
                if fila == 92:
                    valor -= numero(f90, 'F90')
                base.update(estado='CALCULADO_DESDE_TOTALES_NO_HOMOLOGADO', valor=str(valor))
            except EvidenciaInsuficiente as exc:
                base.update(estado='PENDIENTE_DATO', valor=None, motivo=str(exc))
            if len(coincidencias) > 1:
                base['advertencia'] = 'VLOOKUP toma la primera coincidencia; revisar duplicados'
        resultados.append(base)
    return {'estado': 'DIAGNOSTICO_SIN_EQUIVALENCIA_PG_HOST', 'certificado': False,
            'resultados': resultados,
            'advertencias': ['TOTALES B/C no homologadas a campos PostgreSQL',
                            'No ejecutar cruce Host ni publicar Valor Franquicia',
                            'Los ceros por busqueda fallida no prueban ausencia de movimientos']}

def main():
    p = argparse.ArgumentParser(description='INC45: formulas Credibanco de Plantilla Maestra')
    p.add_argument('--catalogo', required=True)
    p.add_argument('--totales', required=True, help='JSON lista de filas con A, B, C del TOTALES externo')
    p.add_argument('--salida', required=True, help='Directorio nuevo')
    p.add_argument('--f90', help='Valor acreditado de F90; en la plantilla aportada F90 es 0')
    args = p.parse_args()
    salida = Path(args.salida)
    if salida.exists():
        p.error('El directorio de salida ya existe')
    catbytes = Path(args.catalogo).read_bytes()
    totbytes = Path(args.totales).read_bytes()
    catalogo = json.loads(catbytes.decode('utf-8-sig'))
    totales = json.loads(totbytes.decode('utf-8-sig'))
    informe = ejecutar(catalogo, totales, f90=args.f90,
                       evidencia={'archivo': Path(args.totales).name,
                                  'sha256': hashlib.sha256(totbytes).hexdigest()})
    informe['sha256_catalogo'] = hashlib.sha256(catbytes).hexdigest()
    salida.mkdir(parents=True, exist_ok=False)
    (salida / 'informe_inc45.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'estado': informe['estado'], 'reglas': len(informe['resultados']),
                      'certificado': False}, ensure_ascii=False))

if __name__ == '__main__':
    main()

"""Adaptador de lectura INC46 -> contrato maestro INC39. No certifica cruces Host."""
import json
from pathlib import Path
from app.services.fase2.cierre_totales_credibanco_inc46 import cerrar, leer_detalle
from app.services.fase2.contrato_maestro_inc39 import COLUMNAS, validar_fila

CATALOGO = Path(__file__).resolve().parents[4] / 'catalogo_credibanco_inc44.json'


def construir_respuesta(informe):
    filas=[]
    detalle=[]
    totales_por_concepto = {str(t.get('A')): t for t in informe.get('totales', [])}
    for f in informe['formulas']:
        fila=dict.fromkeys(COLUMNAS)
        fila.update(franquicia='CREDIBANCO', cuenta=str(f['cuenta']),
                    concepto=f['concepto'], estado_conciliacion='PENDIENTE_HOMOLOGACION',
                    accion='Detalle')
        validar_fila(fila)
        filas.append(fila)
        total = totales_por_concepto.get(str(f['concepto']))
        detalle.append({'cantidad_operaciones': total.get('B') if total else None,
                        'vl_interc': total.get('C') if total else None,
                        'vl_total': total.get('D') if total else None,
                        'archivos_origen': total.get('archivos', []) if total else [],
                        'lineas_origen': total.get('lineas_origen', []) if total else [],
                        'origen_agregado': 'TOTALES_INC46_NO_HOMOLOGADO' if total else 'SIN_AGREGADO',
                        'cuenta': str(f['cuenta']), 'concepto': f['concepto'],
                        'celda': f['celda'], 'columna_totales': f.get('columna_totales'),
                        'unidad': f.get('unidad'), 'valor_diagnostico': f.get('valor_proyectado'),
                        'valor_formula_final': f.get('valor_formula_final'),
                        'estado': f.get('estado'), 'certificado': False})
    return {'id_jornada': informe['id_jornada'], 'origen': informe['origen'],
            'columnas': list(COLUMNAS), 'filas': filas, 'detalle': detalle,
            'totales_diagnosticos': informe['totales'],
            'indicadores': {'cruces':0,'conciliados':0,'diferencias':0,'incorporados_maestro':0},
            'certificado':False,'estado':'DIAGNOSTICO_CREDIBANCO_NO_HOMOLOGADO',
            'advertencias':informe['advertencias']}


def consultar(jornada, catalogo_path=None):
    catalogo=json.loads(Path(catalogo_path or CATALOGO).read_text(encoding='utf-8-sig'))
    return construir_respuesta(cerrar(leer_detalle(jornada),catalogo,jornada))

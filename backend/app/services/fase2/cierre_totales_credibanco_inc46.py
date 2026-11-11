"""Cierre tecnico Inc46: tabla dinamica principal y formulas, no conciliacion Host.
Referencia: ESTRUCTURA CANJE ELECTRONICO Y MANUAL CORTO_OK.xlsx, TOTALES!A4:D10.
No requiere Excel en operacion, no escribe PostgreSQL.
"""
import argparse
import hashlib
import json
from pathlib import Path
from app.services.fase2.totales_credibanco_inc46_fix import construir_totales, proyectar_a_formulas


def leer_detalle(jornada):
    from app.repositories.database import connection
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute('''SELECT d.id_archivo,d.linea_origen,d.tipo_archivo,d.cuenta,d.tipo,
                           d.vl_interc,d.vl_total
                           FROM con_canje_detalle d
                           WHERE d.tipo_archivo IN ('CAET','CANT')
                           AND EXISTS (SELECT 1 FROM con_insumo_esperado i
                                       WHERE i.id_archivo=d.id_archivo AND i.id_jornada=%s)
                           ORDER BY d.id_archivo,d.linea_origen''',(jornada,))
            nombres=[c.name for c in cur.description]
            return [dict(zip(nombres,r)) for r in cur.fetchall()]


def cerrar(detalles,catalogo,jornada):
    totales=construir_totales(detalles)
    formulas=proyectar_a_formulas(totales,catalogo)
    for r in formulas:
        # El valor calculado de B es una cantidad, nunca dinero.
        r['valor_franquicia']=None
        r['certificado']=False
        r['estado_conciliacion']='PENDIENTE_HOMOLOGACION_HOST'
        if r['celda']=='F92':
            r['estado']='PENDIENTE_VALIDACION_F90'
            r['valor_formula_final']=None
        else:
            r['valor_formula_final']=r['valor_proyectado']
    return {'id_jornada':jornada,'origen':'PG_CAET_CANT_INC46_CIERRE_TECNICO',
            'registros':len(detalles),'totales':totales,'formulas':formulas,
            'certificado':False,'estado':'CIERRE_TECNICO_NO_HOMOLOGADO',
            'advertencias':['La hoja TOTALES de la muestra Excel no acredita igualdad de jornada ni filtros operativos.',
              'F90 es 0 literal en Plantilla Maestra(10).xlsx, PLANTILLA (2)!F90; requiere verificar vigencia por jornada.',
              'B es COUNT(TIPO), C es SUM(VL INTERC), D es SUM(VL TOTAL) para pivot principal.',
              'No se publica Valor Franquicia ni se realizan cruces Host.']}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--jornada',type=int,required=True)
    p.add_argument('--catalogo',default='catalogo_credibanco_inc44.json')
    p.add_argument('--salida',required=True)
    a=p.parse_args()
    destino=Path(a.salida)
    if destino.exists():p.error('Salida ya existe')
    catalogo=json.loads(Path(a.catalogo).read_text(encoding='utf-8-sig'))
    informe=cerrar(leer_detalle(a.jornada),catalogo,a.jornada)
    contenido=json.dumps(informe,ensure_ascii=False,indent=2)
    destino.mkdir(parents=True)
    (destino/'cierre_inc46.json').write_text(contenido,encoding='utf-8')
    (destino/'sha256_cierre.txt').write_text(hashlib.sha256(contenido.encode()).hexdigest()+'\n')
    print(json.dumps({'jornada':a.jornada,'registros':informe['registros'],
      'conceptos':len(informe['totales']),'formulas':len(informe['formulas']),
      'certificado':False}))

if __name__=='__main__':main()

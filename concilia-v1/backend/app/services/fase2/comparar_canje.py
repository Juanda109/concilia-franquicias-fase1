"""Diagnostico no destructivo CAET/CANT contra valores TOTALES Excel.
No afirma equivalencia hasta verificar identidad de los insumos.
"""
import argparse
import csv
import json
import os
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

REFERENCIA = {
 '017-CANJE RECIBIDO TARJETA CREDITO': (3, 880000, 880000),
 '017-CANJE RECIBIDO TARJETA DEBITO REVERSIONES': (6, 2860000, 2860000),
 '017-REPRESENTACION  VENTA NAL (CENTRO 730)': (4, 2207341, 2208421),
 '017-COMISIONES NO EXITOSAS TD Y TC IMPUTABLES BANCO': (27, 231714, 231714),
 '': (17, 657, 0),
}
TOTAL_EXCEL = {'cantidad':57, 'intercambio':6179712, 'valor':6180135, 'comisiones':22350}

def dec(value):
 if value is None or str(value).strip() == '': return Decimal(0)
 try: return Decimal(str(value))
 except InvalidOperation: raise ValueError('Importe no numerico')

def resumen(rows):
 groups=defaultdict(lambda: {'cantidad':0,'intercambio':Decimal(0),'valor':Decimal(0),'comisiones':Decimal(0)})
 for row in rows:
  cuenta=str(row.get('cuenta') or '')
  g=groups[cuenta]
  g['cantidad']+=1
  g['intercambio']+=dec(row.get('vl_interc'))
  g['valor']+=dec(row.get('vl_total'))
  g['comisiones']+=dec(row.get('comision_op_exitosas'))
 return groups

def cargar_bd(ids):
 if os.environ.get('DB_NAME') != 'concilia_test':
  raise SystemExit('ABORTADO: DB_NAME debe ser concilia_test para esta lectura')
 import psycopg
 cfg=dict(host=os.environ['DB_HOST'],port=int(os.environ['DB_PORT']),dbname='concilia_test',user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],connect_timeout=5)
 with psycopg.connect(**cfg) as conn:
  with conn.cursor() as cur:
   cur.execute('BEGIN READ ONLY')
   cur.execute("SET LOCAL statement_timeout='15s'")
   cur.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=%s AND table_name=%s',('public','con_canje_detalle'))
   cols={r[0] for r in cur.fetchall()}
   needed={'id_archivo','cuenta','vl_interc','vl_total','comision_op_exitosas'}
   missing=sorted(needed-cols)
   if missing: raise RuntimeError('Columnas necesarias ausentes: '+', '.join(missing)+'; se requiere mapeo F2, no usar resultados legados')
   cur.execute('''SELECT a.id_archivo,a.tipo_archivo,a.fecha_contable,a.estado,i.estado,j.id_jornada
                  FROM public.con_archivo_carga a
                  JOIN public.con_insumo_esperado i ON i.id_archivo=a.id_archivo
                  JOIN public.con_jornada j ON j.id_jornada=i.id_jornada
                  WHERE a.id_archivo=ANY(%s) ORDER BY a.id_archivo''',(ids,))
   metadata=cur.fetchall()
   if len(metadata)!=len(set(ids)) or any(m[1] not in ('CAET','CANT') or m[3]!='PROCESADO' or m[4]!='PROCESADO' for m in metadata):
    raise RuntimeError('Archivos inexistentes, no CAET/CANT o no PROCESADOS')
   if len({m[2] for m in metadata})!=1 or len({m[5] for m in metadata})!=1:
    raise RuntimeError('Los archivos deben corresponder a una misma fecha y jornada')
   cur.execute('''SELECT id_archivo,cuenta,vl_interc,vl_total,comision_op_exitosas
                  FROM public.con_canje_detalle WHERE id_archivo=ANY(%s)''',(ids,))
   data=[dict(zip(('id_archivo','cuenta','vl_interc','vl_total','comision_op_exitosas'),r)) for r in cur.fetchall()]
   conn.rollback()
 return metadata,data

def run(args):
 output=Path(args.salida)
 if output.exists(): raise SystemExit('ABORTADO: salida existente; no sobrescribir')
 output.mkdir(parents=True)
 reporte={'referencia_excel':TOTAL_EXCEL,'ids_archivos':args.ids,'comparacion_certificada':False,
          'advertencia':'No se ha acreditado que los archivos elegidos sean los mismos que alimentaron el Excel. La cuenta almacenada puede proceder de clasificacion historica F1; no equivale a recalculo F2.'}
 if args.ids:
  try:
   metadata,rows=cargar_bd(args.ids)
   reporte['archivos']=[{'id_archivo':m[0],'tipo':m[1],'fecha':str(m[2]),'jornada':m[5]} for m in metadata]
   groups=resumen(rows)
   with (output/'diferencias.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.writer(f,delimiter=';');w.writerow(['cuenta','cantidad_excel','cantidad_bd','delta_cantidad','interc_excel','interc_bd','delta_interc','valor_excel','valor_bd','delta_valor'])
    for cuenta in sorted(set(REFERENCIA)|set(groups)):
     n,i,v=REFERENCIA.get(cuenta,(0,0,0)); g=groups.get(cuenta,{'cantidad':0,'intercambio':Decimal(0),'valor':Decimal(0)})
     w.writerow([cuenta,n,g['cantidad'],g['cantidad']-n,i,str(g['intercambio']),str(g['intercambio']-i),v,str(g['valor']),str(g['valor']-v)])
   reporte['filas_bd']=len(rows)
   reporte['total_bd']={'cantidad':len(rows),'intercambio':str(sum((g['intercambio'] for g in groups.values()),Decimal(0))),'valor':str(sum((g['valor'] for g in groups.values()),Decimal(0))),'comisiones':str(sum((g['comisiones'] for g in groups.values()),Decimal(0)))}
   reporte['estado']='COMPARACION_DIAGNOSTICA_NO_CERTIFICADA'
  except Exception as e:
   reporte['estado']='BLOQUEADO';reporte['error']=str(e)
 else:
  reporte['estado']='SIN_ARCHIVOS';reporte['accion']='Proporcione --ids con archivos CAET/CANT PROCESADOS de la jornada de referencia'
 (output/'informe.json').write_text(json.dumps(reporte,ensure_ascii=False,indent=2),encoding='utf-8')
 print('ESTADO:',reporte['estado']);print('INFORME:',output/'informe.json')
 if reporte.get('error'):print('MOTIVO:',reporte['error'])
 return 0 if reporte['estado']!='BLOQUEADO' else 2

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--ids',type=int,nargs='*',default=[]);p.add_argument('--salida',required=True)
 raise SystemExit(run(p.parse_args()))

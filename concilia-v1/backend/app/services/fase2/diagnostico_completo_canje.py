"""Concilia F2 incremento 07: diagnostico NO certificado, exclusivamente lectura."""
import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED = {'id_archivo','linea_origen'}
CANDIDATES = {
    'tx': ('tx','tx_original','tipo_transaccion'),
    'bin_dest': ('bin_dest','bin_destino'),
    'tipo': ('tipo','tipo_tarjeta'),
    'canal': ('espacios','canal'),
    'cod_error': ('cod_error','codigo_error'),
    'mot_cob': ('mot_cob','motivo_cobro'),
    'cuenta_historica': ('cuenta','cuenta_contable'),
    'cuenta_comision': ('cuentas_comisiones','cuenta_comision'),
    'cuenta_880': ('cuenta_880',),
    'valor': ('vl_total','valor_total'),
    'intercambio': ('vl_interc','valor_intercambio'),
    'comision': ('comision_op_exitosas',),
    'tii': ('tii_recibida_emisor_visa_op_rever_ventas',),
}

def decimal_or_none(v):
    if v is None or str(v).strip() == '':
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None

def select_columns(available):
    if not REQUIRED <= set(available):
        raise ValueError('con_canje_detalle carece de id_archivo o linea_origen')
    return {key: next((x for x in names if x in available), None) for key,names in CANDIDATES.items()}

def normalize_row(raw, mapping):
    row = {'id_archivo':raw['id_archivo'], 'linea_origen':raw['linea_origen']}
    for key, col in mapping.items():
        row[key] = raw.get(col) if col else None
    return row

def classify(row):
    """Evalua todas las reglas disponibles en clasificacion_canje (incremento 02)."""
    from app.services.fase2.clasificacion_canje import clasificar_cuenta
    def norm(key):
        value = row.get(key)
        return '' if value is None else str(value).strip()
    # TX es codigo, no numero; preservar ceros iniciales.
    tx = norm('tx').zfill(2) if norm('tx').isdigit() else norm('tx')
    bin_dest = norm('bin_dest')
    if bin_dest.isdigit(): bin_dest = bin_dest.zfill(6)
    tipo = norm('tipo').upper()
    canal = norm('canal').upper()
    cod_error = norm('cod_error')
    mot_cob = norm('mot_cob')
    if not all((tx, tipo, cod_error)):
        return None, None, 'DATOS_INSUFICIENTES'
    resultado = clasificar_cuenta(cod_error=cod_error, tipo=tipo, canal=canal,
                                 tx=tx, bin_dest=bin_dest, mot_cob=mot_cob)
    if resultado.motivo == 'CLASIFICADO':
        return resultado.cuenta, resultado.regla_id, 'EVALUADA'
    if resultado.motivo == 'COD_ERROR_NO_APLICABLE':
        return '', 'F2-COD-ERROR', 'EVALUADA'
    if resultado.motivo == 'SIN_REGLA_FUNCIONAL':
        return '', 'F2-SIN-REGLA', 'EVALUADA_SIN_REGLA'
    return None, None, 'DATOS_INSUFICIENTES'

def analyze(rows):
    result=[]
    counts=Counter()
    sums=defaultdict(lambda: {'cantidad':0,'valor':Decimal(0),'intercambio':Decimal(0),'comision':Decimal(0)})
    for row in rows:
        expected,rule,coverage=classify(row)
        historical=str(row.get('cuenta_historica') or '')
        status=('NO_EVALUADA' if coverage=='DATOS_INSUFICIENTES' else 'SIN_REGLA_F2' if coverage=='EVALUADA_SIN_REGLA' else 'COINCIDE' if historical==expected else 'DIFIERE')
        counts[status]+=1
        item=dict(row, cuenta_recalculada=expected, id_regla=rule, cobertura=coverage, resultado_comparacion=status)
        result.append(item)
        key=historical
        agg=sums[key]; agg['cantidad']+=1
        for field in ('valor','intercambio','comision'):
            v=decimal_or_none(row.get(field))
            if v is not None: agg[field]+=v
    return result,counts,sums

def write_csv(path,rows,fields):
    with path.open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields,delimiter=';',extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow({k: '' if row.get(k) is None else str(row[k]) for k in fields})

def run(ids,output,connection_factory=None):
    if os.environ.get('DB_NAME') != 'concilia_test':
        raise RuntimeError('ABORTADO: DB_NAME debe ser concilia_test')
    if len(ids)!=2 or len(set(ids))!=2 or any(x<=0 for x in ids):
        raise ValueError('Se requieren dos ID distintos y positivos')
    if output.exists():
        raise FileExistsError('La carpeta de salida ya existe; no sobrescribir')
    if connection_factory is None:
        import psycopg
        connection_factory=psycopg.connect
    params=dict(host=os.environ['DB_HOST'],port=int(os.environ['DB_PORT']),dbname='concilia_test',user=os.environ['DB_USER'],password=os.environ['DB_PASSWORD'],connect_timeout=5)
    with connection_factory(**params) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute("SET LOCAL statement_timeout = '30s'")
            cur.execute('''SELECT a.id_archivo,a.tipo_archivo,a.fecha_contable,a.estado,i.estado,j.id_jornada
                           FROM public.con_archivo_carga a
                           JOIN public.con_insumo_esperado i ON i.id_archivo=a.id_archivo
                           JOIN public.con_jornada j ON j.id_jornada=i.id_jornada
                           WHERE a.id_archivo=ANY(%s)''',(ids,))
            metadata=cur.fetchall()
            if len(metadata)!=2 or {r[1] for r in metadata}!={'CAET','CANT'} or len({r[5] for r in metadata})!=1 or len({str(r[2]) for r in metadata})!=1 or any(r[3]!='PROCESADO' or r[4]!='PROCESADO' for r in metadata):
                raise RuntimeError('Archivos no son CAET/CANT procesados de la misma jornada')
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='con_canje_detalle'")
            available={r[0] for r in cur.fetchall()}
            mapping=select_columns(available)
            selected=['id_archivo','linea_origen'] + sorted({v for v in mapping.values() if v})
            # Identificadores SQL derivados solo de information_schema; no entradas de usuario.
            cur.execute('SELECT '+','.join('"'+c+'"' for c in selected)+' FROM public.con_canje_detalle WHERE id_archivo=ANY(%s) ORDER BY id_archivo,linea_origen',(ids,))
            raw=[dict(zip(selected,r)) for r in cur.fetchall()]
    rows=[normalize_row(r,mapping) for r in raw]
    detail,counts,sums=analyze(rows)
    output.mkdir(parents=True,exist_ok=False)
    fields=['id_archivo','linea_origen','tx','bin_dest','tipo','canal','cod_error','mot_cob','cuenta_historica','cuenta_recalculada','id_regla','cobertura','resultado_comparacion','valor','intercambio','comision','tii','cuenta_comision','cuenta_880']
    write_csv(output/'movimientos.csv',detail,fields)
    summary=[{'cuenta':k,**{a:str(v) for a,v in d.items()}} for k,d in sorted(sums.items())]
    write_csv(output/'resumen_cuentas.csv',summary,['cuenta','cantidad','valor','intercambio','comision'])
    report={'estado':'DIAGNOSTICO_F2_COMPLETO_NO_CERTIFICADO','ids_archivos':ids,'jornada':metadata[0][5], 'fecha':str(metadata[0][2]),'filas':len(rows),'conteo_resultados':dict(counts),'columnas_disponibles':sorted(available),'mapeo_columnas':mapping,'campos_ausentes':[k for k,v in mapping.items() if v is None], 'advertencias':['Clasificacion completa de cuenta principal segun incremento 02; comisiones y regalo requieren contraste separado.','No se acredita equivalencia de poblacion con plantilla Excel.','Importes de origen sin ajuste de escala: cotejar con formato de fuente.','La ausencia de columna de comision no equivale a comision cero.']}
    (output/'informe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--ids',nargs=2,type=int,required=True)
    p.add_argument('--salida',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.ids,a.salida),ensure_ascii=False,indent=2))
if __name__=='__main__': main()

"""Extractor F1 de evidencia auxiliar de Carta Credibanco, no monetario.

Alcance: CAI0160A (referencia oral KAI160), contenedor BAI 483A y BAI0485A.
Separa VSS dentro de BAI 483A SIN descartar la evidencia requerida por
operaciones. No presume equivalencia KAI/CAI o BY/BAI; no suma montos.
Procesa XLSX original incluso cuando su extension fisica es .bin.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from zipfile import is_zipfile

from openpyxl import load_workbook

VERSION = 'V69.1'
MEETING_DOC = 'https://docs.google.com/document/d/1JyT1s6PWit0iwpvVYbMw287XMzE7JwZCrPFi8zv4zRE/edit'
FAMILIAS = {
    'CAI160A': {'familia': 'CANJE_ENVIADO_160', 'referencia_meet': 'KAI 160', 'codigo': 'CAI0160A'},
    'CAI0160A': {'familia': 'CANJE_ENVIADO_160', 'referencia_meet': 'KAI 160', 'codigo': 'CAI0160A'},
    'KAI160': {'familia': 'CANJE_ENVIADO_160', 'referencia_meet': 'KAI 160', 'codigo': 'KAI160'},
    'KAI160A': {'familia': 'CANJE_ENVIADO_160', 'referencia_meet': 'KAI 160', 'codigo': 'KAI160A'},
    'BAI483A': {'familia': 'CANJE_INTERNACIONAL_483', 'referencia_meet': 'B 483', 'codigo': 'NO_CONFIRMADO_POR_CABECERA'},
    'BY483': {'familia': 'CANJE_INTERNACIONAL_483', 'referencia_meet': 'B 483', 'codigo': 'BY483'},
    'BY483A': {'familia': 'CANJE_INTERNACIONAL_483', 'referencia_meet': 'B 483', 'codigo': 'BY483A'},
    'BAI485A': {'familia': 'CANJE_INTERNACIONAL_485', 'referencia_meet': 'B 485', 'codigo': 'BAI0485A'},
    'BAI0485A': {'familia': 'CANJE_INTERNACIONAL_485', 'referencia_meet': 'B 485', 'codigo': 'BAI0485A'},
    'BY485': {'familia': 'CANJE_INTERNACIONAL_485', 'referencia_meet': 'B 485', 'codigo': 'BY485'},
    'BY485A': {'familia': 'CANJE_INTERNACIONAL_485', 'referencia_meet': 'B 485', 'codigo': 'BY485A'},
}
NECESARIAS = ('CANJE_ENVIADO_160', 'CANJE_INTERNACIONAL_483', 'CANJE_INTERNACIONAL_485')
RE_PAG = re.compile(r'\bP[AÁ]G(?:INA|E)?\s*:?\s*(\d{1,6})\b', re.I)
RE_VSS = re.compile(r'REPORT\s+ID\s*:\s*(VSS[- ]?\d+)\b', re.I)
RE_HEADER_160 = re.compile(r'(?<![A-Z0-9])0?(?:CAI\s*0?160A|KAI\s*0?160A?)\b', re.I)
RE_HEADER_485 = re.compile(r'(?<![A-Z0-9])0?(?:BAI\s*0?485A|BY\s*0?485A?)\b', re.I)
RE_HEADER_483 = re.compile(r'(?<![A-Z0-9])0?(?:BAI\s*0?483A|BY\s*0?483A?)\b', re.I)
RE_FORM_FEED = re.compile(r'(?:^\s*(?:_x000C_|\x0c))|(?:FECHA\s+DE\s+IMPRESI[OÓ]N\s*:)', re.I)
RE_TX = re.compile(r'^\s*(\d{2,3})\s{2,}([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ \-./]{2,45})(?=\s{2,}|$)', re.I)
RE_NUMERIC_DATE = re.compile(r'(20\d{2})\s*[/\-]\s*(\d{1,2})\s*[/\-]\s*(\d{1,2})')
RE_DMY_DATE = re.compile(r'(?<![\d/])(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})(?![\d/])')
RE_ENG_DATE = re.compile(r'(\d{2})(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)(\d{2})', re.I)
RE_SPANISH_DATE = re.compile(r'([A-ZÁÉÍÓÚÑ]+)\s+(\d{1,2})\s*/\s*(\d{2,4})', re.I)
MESES = {'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,'JULIO':7,'AGOSTO':8,'SEPTIEMBRE':9,'SETIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12}
ENG = {m:i for i,m in enumerate(('JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'),1)}
CAMPO_FECHA = {
    'fecha_impresion': re.compile(r'FECHA\s+DE\s+IMPRESI[OÓ]N\s*:\s*', re.I),
    'fecha_proceso': re.compile(r'(?:FECHA\s+DE\s+PROCESO|PROC\s+DATE)\s*:\s*', re.I),
    'fecha_canje': re.compile(r'FECHA\s+DEL\s+CANJE\s*:?\s*', re.I),
    'fecha_sistema': re.compile(r'FECHA\s+DEL\s+SISTEMA\s*:?\s*', re.I),
    'fecha_reporte': re.compile(r'REPORT\s+DATE\s*:\s*', re.I),
    'fecha_outclear': re.compile(r'FECHA\s+(?:DEL\s+)?OUTCLEAR\s*:?\s*', re.I),
}
FECHAS_OPERATIVAS = ('fecha_proceso','fecha_canje','fecha_sistema','fecha_reporte','fecha_outclear')
CAMPOS_PAGINAS = ('nombre_hoja','familia','codigo_cabecera','estado_identidad','referencia_meet','pagina_logica',
                  'pagina_impresa','linea_inicio','linea_fin','filas_con_texto','filas_candidatas',
                  'fecha_impresion','fecha_proceso','fecha_canje','fecha_sistema','fecha_reporte',
                  'fecha_outclear','estado_fecha','codigo_vss','huella_sha256','habilitado_f2_monetario')
CAMPOS_LINEAS = ('nombre_hoja','familia','pagina_logica','numero_linea','tipo_linea',
                 'codigo_transaccion_literal','codigo_vss','huella_sha256','habilitado_f2_monetario')


def _hash_file(path:Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024), b''):h.update(b)
    return h.hexdigest()


def _nombre_norm(nombre:str) -> str:
    return re.sub(r'[^A-Z0-9]','',nombre.upper())


def _fecha_valida(y:int,m:int,d:int) -> str|None:
    try:return date(y,m,d).isoformat()
    except ValueError:return None


def _parse_date(s:str) -> str|None:
    for regex in (RE_NUMERIC_DATE, RE_DMY_DATE, RE_ENG_DATE, RE_SPANISH_DATE):
        match=regex.search(s)
        if match is None:continue
        a,b,c=match.groups()
        if regex is RE_NUMERIC_DATE:year,month,day=int(a),int(b),int(c)
        elif regex is RE_DMY_DATE:
            day,month,year=int(a),int(b),int(c)
            if year<100:year+=2000
        elif regex is RE_ENG_DATE:day,month,year=int(a),ENG[b.upper()],2000+int(c)
        else:
            if a.upper() not in MESES:continue
            day,month,year=int(b),MESES[a.upper()],int(c)
            if year<100:year+=2000
        res=_fecha_valida(year,month,day)
        # El formato identificado no puede reinterpretarse en otro orden
        # cuando su fecha es imposible (ej. 2026/02/31).
        return res
    return None


def _datos_fecha(lines:list[tuple[int,str]]) -> dict:
    values={k:None for k in CAMPO_FECHA}
    # Los campos de cabecera se extraen solo en las primeras 10 filas no vacias.
    for _,line in lines[:10]:
        for k,rx in CAMPO_FECHA.items():
            m=rx.search(line)
            if m:
                d=_parse_date(line[m.end():m.end()+65])
                if d and values[k] is None:values[k]=d
    return values


def _estado_fecha(fechas:dict, esperada:str|None)->str:
    if not esperada:return 'SIN_FECHA_OBJETIVO'
    vals=[v for k,v in fechas.items() if k in FECHAS_OPERATIVAS and v]
    if not vals:return 'SIN_FECHA_OPERATIVA'
    if all(x==esperada for x in vals):return 'COINCIDE'
    if any(x==esperada for x in vals):return 'MIXTA'
    return 'DIFIERE'


def _clasificar_linea(linea:str, familia:str)->tuple[str,str|None]:
    up=linea.upper().strip()
    if RE_FORM_FEED.search(linea) or RE_VSS.search(linea) or RE_HEADER_160.search(linea) or RE_HEADER_485.search(linea):
        return 'CABECERA_REPORTE',None
    if any(x.search(linea) for x in CAMPO_FECHA.values()) or 'REPORTING FOR' in up:
        return 'METADATO_FECHA_ENTIDAD',None
    if '*** END OF VSS-' in up:return 'FIN_REPORTE',None
    if 'T O T A L E S' in up or re.search(r'\bTOTAL(?:ES)?\b',up) or 'VALOR EN $' in up:
        return 'CONTROL_O_TOTAL_PENDIENTE_HOMOLOGACION',None
    if familia=='CANJE_ENVIADO_160':
        m=RE_TX.match(linea)
        if m:
            codigo=m.group(1)
            if codigo in {'99','099'}:return 'CONTROL_O_TOTAL_PENDIENTE_HOMOLOGACION',None
            return 'CODIGO_TRANSACCION_CANDIDATO',codigo
    if 'CREDITO' in up and 'DEBITO' in up:return 'ENCABEZADO_COLUMNAS',None
    if up in {'-','--','1','/','*'} or set(up)<=set('-_ =*'):
        return 'PRESENTACION',None
    return 'CUERPO_ORIGEN_NO_HOMOLOGADO',None


def _segmentar_hoja(ws)->list[list[tuple[int,str]]]:
    ws.reset_dimensions()
    paginas=[];pagina=[]
    for numero,(celda,) in enumerate(ws.iter_rows(min_col=1,max_col=1,values_only=True),1):
        if celda is None:continue
        linea=str(celda)
        if not linea.strip():continue
        if pagina and RE_FORM_FEED.search(linea):
            paginas.append(pagina)
            pagina=[]
        pagina.append((numero,linea))
    if pagina:paginas.append(pagina)
    return paginas


def _identidad(pagina:list[tuple[int,str]],familia:str)->tuple[str|None,str|None,str]:
    prefijo=' '.join(line[:250] for _,line in pagina[:8])
    vss=RE_VSS.search(prefijo)
    codigo_vss=vss.group(1).upper().replace(' ','-') if vss else None
    if familia=='CANJE_ENVIADO_160':
        m=RE_HEADER_160.search(prefijo)
        if m:
            return ('CAI0160A' if m.group().upper().strip().lstrip('0').startswith('CAI') else 'KAI160',None,'CODIGO_160_LEIDO_EN_CABECERA')
        return None,None,'IDENTIDAD_160_NO_ACREDITADA_EN_CABECERA'
    if familia=='CANJE_INTERNACIONAL_485':
        m=RE_HEADER_485.search(prefijo)
        if m:
            return ('BAI0485A' if m.group().upper().strip().lstrip('0').startswith('BAI') else 'BY485',None,'CODIGO_485_LEIDO_EN_CABECERA')
        return None,None,'IDENTIDAD_485_NO_ACREDITADA_EN_CABECERA'
    if familia=='CANJE_INTERNACIONAL_483':
        m=RE_HEADER_483.search(prefijo)
        if m:return ('BAI0483A' if m.group().upper().strip().lstrip('0').startswith('BAI') else 'BY483',codigo_vss,'CODIGO_483_LEIDO_EN_CABECERA')
        if codigo_vss:return (codigo_vss,codigo_vss,'VSS_EMBEBIDO_CONTENEDOR_BAI483_NO_EQUIVALE_BY483')
        return None,None,'REPORTE_SIN_CODIGO_EXPLICITO'
    return None,None,'FUERA_ALCANCE'


def _huella(pagina:list[tuple[int,str]])->str:
    h=hashlib.sha256()
    for i,l in pagina:
        h.update(str(i).encode('ascii'));h.update(b':');h.update(l.encode('utf-8'));h.update(b'\n')
    return h.hexdigest()


def extraer(ruta:Path,fecha_contable:str|None=None,*,metadatos:dict|None=None)->dict:
    ruta=Path(ruta).resolve()
    if not ruta.is_file():raise FileNotFoundError('Carta original no encontrada')
    if not is_zipfile(ruta):raise ValueError('Carta no contiene XLSX ZIP valido')
    if fecha_contable:fecha_contable=date.fromisoformat(fecha_contable).isoformat()
    sha=_hash_file(ruta)
    registrado=str((metadatos or {}).get('checksum_registrado') or '').strip().lower()
    if registrado and registrado!=sha:raise ValueError('Checksum original no coincide con metadata; extracción bloqueada')
    paginas=[];lineas=[];hojas=[];familias_vistas=set();alertas=[]
    with ruta.open('rb') as fh:
        wb=load_workbook(fh,data_only=True,read_only=True)
        try:
            for ws in wb:
                nombre=_nombre_norm(ws.title)
                if nombre not in FAMILIAS:continue
                info=FAMILIAS[nombre]
                familia=info['familia'];familias_vistas.add(familia)
                segmentos=_segmentar_hoja(ws)
                hueso={'nombre_hoja':ws.title,'familia':familia,'referencia_meet':info['referencia_meet'],
                       'codigo_guia_nombre_hoja':info['codigo'], 'paginas':len(segmentos),
                       'lineas_con_texto':sum(len(p) for p in segmentos),'certificado':False}
                hojas.append(hueso)
                for pnum,bloque in enumerate(segmentos,1):
                    codigo,codigo_vss,estado_id=_identidad(bloque,familia)
                    fechas=_datos_fecha(bloque)
                    estado=_estado_fecha(fechas,fecha_contable)
                    pag_int=None
                    for _,texto in bloque[:3]:
                        p=RE_PAG.search(texto)
                        if p:pag_int=p.group(1);break
                    clase=Counter()
                    for numero,texto in bloque:
                        tipo,tx=_clasificar_linea(texto,familia)
                        clase[tipo]+=1
                        lineas.append({'nombre_hoja':ws.title,'familia':familia,
                          'pagina_logica':pnum,'numero_linea':numero,'tipo_linea':tipo,
                          'codigo_transaccion_literal':tx,'codigo_vss':codigo_vss,
                          'huella_sha256':hashlib.sha256(texto.encode('utf-8')).hexdigest(),
                          'habilitado_f2_monetario':False})
                    row={'nombre_hoja':ws.title,'familia':familia,'referencia_meet':info['referencia_meet'],
                         'codigo_cabecera':codigo,'estado_identidad':estado_id,'pagina_logica':pnum,
                         'pagina_impresa':pag_int,'linea_inicio':bloque[0][0],'linea_fin':bloque[-1][0],
                         'filas_con_texto':len(bloque),'filas_candidatas':clase['CODIGO_TRANSACCION_CANDIDATO'],
                         **fechas,'estado_fecha':estado,'codigo_vss':codigo_vss,'tipos_de_linea':dict(clase),
                         'huella_sha256':_huella(bloque),'habilitado_f2_monetario':False}
                    paginas.append(row)
                    if estado in ('DIFIERE','MIXTA'):
                        alertas.append({'tipo':'FECHA_AUXILIAR_NO_COINCIDE', 'hoja':ws.title,
                                        'pagina':pnum,'fechas_operativas':{k:v for k,v in fechas.items() if k in FECHAS_OPERATIVAS and v}})
                    if 'NO_ACREDITADA' in estado_id or estado_id=='REPORTE_SIN_CODIGO_EXPLICITO':
                        alertas.append({'tipo':'CABECERA_AUXILIAR_SIN_CODIGO_EXPLICITO','hoja':ws.title,'pagina':pnum})
        finally:wb.close()
    for familia in NECESARIAS:
        if familia not in familias_vistas:alertas.append({'tipo':'FAMILIA_AUXILIAR_NO_PRESENTE','familia':familia})
    cnt=Counter(x['familia'] for x in paginas)
    for familia in NECESARIAS:
        if sum(1 for p in paginas if p['familia']==familia and p['estado_identidad'].startswith('CODIGO_'))==0 and familia!='CANJE_INTERNACIONAL_483':
            alertas.append({'tipo':'NINGUNA_CABECERA_EXPLICITA','familia':familia})
    # Nunca validar automáticamente equivalencias orales KAI/CAI, BY/BAI.
    return {'tipo':'CARTA_COMPENSACION','version':VERSION,'estado':'EXTRACCION_F1_EVIDENCIA_AUXILIAR_SIN_PERSISTIR',
            'archivo':ruta.name,'sha256_original':sha,'integridad':('COINCIDE' if registrado else 'NO_VERIFICADA_CON_BD'),
            'fecha_contable_objetivo':fecha_contable,'metadatos_jornada':metadatos or {},
            'reunion':{'fecha':'2026-11-03','fuente':MEETING_DOC,'minutos':'01:18:12-01:26:24',
                       'requisito':'Extraer KAI160, B483, B485; no homologar nombres fisicos automaticamente'},
            'resumen':{'hojas_objetivo':len(hojas),'paginas':len(paginas),'lineas_evidencia':len(lineas),
                       'paginas_por_familia':dict(cnt),'lineas_tx_candidatas':sum(p['filas_candidatas'] for p in paginas),
                       'paginas_fecha_difiere':sum(p['estado_fecha']=='DIFIERE' for p in paginas),
                       'paginas_fecha_mixta':sum(p['estado_fecha']=='MIXTA' for p in paginas)},
            'hojas':hojas,'paginas':paginas,'lineas':lineas,'alertas':alertas,
            'restricciones':{'sin_homologacion_KAI_CAI':True,'sin_homologacion_BY_BAI':True,
              'BAI483_contiene_reportes_VSS':True,'VSS_es_evidencia_requerida_no_suma_Carta':True,
              'F1_0224_0228_no_modificado':True,'importes_habilitados':False,'l6':None,
              'f2_habilitada':False,'certificacion':False},'certificado':False}


def _guardar_csv(path:Path,datos:list[dict],columnas:tuple[str,...]):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        wr=csv.DictWriter(f,fieldnames=columnas,extrasaction='ignore',delimiter=';')
        wr.writeheader()
        for row in datos:
            wr.writerow({c:row.get(c) for c in columnas})


def guardar(r:dict,dirpath:Path)->list[Path]:
    dirpath=Path(dirpath)
    dirpath.mkdir(parents=True,exist_ok=True)
    paths=[dirpath/'credibanco_carta_auxiliar_v69.json',
           dirpath/'credibanco_carta_auxiliar_paginas_v69.csv',
           dirpath/'credibanco_carta_auxiliar_lineas_v69.csv',
           dirpath/'credibanco_carta_auxiliar_alertas_v69.csv']
    resumen={k:v for k,v in r.items() if k not in ('lineas','paginas')}
    paths[0].write_text(json.dumps(resumen,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    _guardar_csv(paths[1],r['paginas'],CAMPOS_PAGINAS)
    _guardar_csv(paths[2],r['lineas'],CAMPOS_LINEAS)
    _guardar_csv(paths[3],r['alertas'],('tipo','familia','hoja','pagina','fechas_operativas'))
    return paths


def main():
    ap=argparse.ArgumentParser(description='Credibanco F1 - extraer evidencia auxiliar, sin DB escritura')
    origin=ap.add_mutually_exclusive_group(required=True)
    origin.add_argument('--archivo',type=Path)
    origin.add_argument('--jornada',type=int)
    ap.add_argument('--fecha-contable')
    ap.add_argument('--salida-dir',type=Path,required=True)
    args=ap.parse_args()
    if args.jornada:
        from auditar_cobertura_carta_credibanco import datos_de_jornada
        src,fecha,meta=datos_de_jornada(args.jornada)
        if meta['estado_f1_y_fecha']!='VALIDOS':raise RuntimeError('Estado Carta/fecha en BD no acreditados')
    else:src,fecha,meta=args.archivo,args.fecha_contable,None
    resultado=extraer(src,fecha,metadatos=meta)
    paths=guardar(resultado,args.salida_dir)
    print(json.dumps({'jornada':args.jornada,'version':VERSION,'estado':resultado['estado'],
        'integridad':resultado['integridad'],'resumen':resultado['resumen'],
        'alertas_total':len(resultado['alertas']),
        'primeras_alertas':resultado['alertas'][:12],
        'salidas':[str(p) for p in paths],'certificado':False},ensure_ascii=False,indent=2))


if __name__=='__main__':main()

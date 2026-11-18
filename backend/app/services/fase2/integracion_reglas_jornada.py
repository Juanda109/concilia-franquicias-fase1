"""Incremento 38: orquestador F2 por jornada, sin BD ni homologacion.

Contrato explicito: solo insumos acreditados y vinculados a archivo/jornada.
Los calculos del incremento 37 siguen siendo no certificados.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
from decimal import Decimal
from typing import Mapping
from app.services.fase2.reglas_plantilla_maestra import calcular, InsumoPendiente
from app.services.fase2.consolidacion_totales_canje import consolidar, CAMPOS

REGLAS = ('PM37-O15','PM37-P15','PM37-O26','PM37-P26','PM37-M29',
          'PM37-P29','PM37-G38','PM37-G39','PM37-G41','PM37-F42','PM37-G42')

def _validar_id(x, nombre):
    if isinstance(x,bool) or not isinstance(x,int) or x <= 0:
        raise ValueError(f'{nombre} debe ser entero positivo')
    return x

def _serializar(v):
    if isinstance(v,Decimal): return str(v)
    raise TypeError(type(v).__name__)

def procesar(payload: Mapping, parte_filas=None):
    jornada=_validar_id(payload.get('id_jornada'),'id_jornada')
    if not isinstance(payload.get('fecha_contable'),str) or len(payload['fecha_contable'])!=10:
        raise ValueError('fecha_contable obligatoria en formato AAAA-MM-DD')
    from datetime import date
    date.fromisoformat(payload['fecha_contable'])
    insumos=payload.get('insumos',[])
    if not isinstance(insumos,list): raise ValueError('insumos debe ser lista')
    vistos=set(); resultados=[]
    for item in insumos:
        if not isinstance(item,dict): raise ValueError('insumo invalido')
        archivo=_validar_id(item.get('id_archivo'),'id_archivo')
        if archivo in vistos: raise ValueError('id_archivo duplicado')
        vistos.add(archivo)
        if item.get('id_jornada') != jornada: raise ValueError('archivo de otra jornada')
        tipo=item.get('tipo_insumo')
        if tipo not in ('CAET','CANT','CARTA_COMPENSACION'):
            raise ValueError('tipo_insumo no permitido')
        reglas=item.get('reglas',[])
        if not isinstance(reglas,list): raise ValueError('reglas debe ser lista')
        if len(reglas)!=len(set(reglas)): raise ValueError('reglas duplicadas')
        for regla in reglas:
            if regla not in REGLAS: raise ValueError('regla no autorizada')
            # Solo la CARTA puede proveer filas de carta; celdas se suministran
            # explicitamente y no se infieren desde totales CAET/CANT.
            celdas=item.get('celdas') or {}
            carta=item.get('carta') if tipo=='CARTA_COMPENSACION' else None
            if not isinstance(celdas,dict): raise ValueError('celdas debe ser objeto')
            if carta is not None and not isinstance(carta,list): raise ValueError('carta debe ser lista')
            try:
                res=calcular(regla,celdas,carta)
                registro={'regla':res.regla,'cuenta':res.cuenta,'celda':res.celda,
                          'formula_excel':res.formula_excel,'valor':str(res.valor),
                          'estado':res.estado,'certificado':False,'motivo':None}
            except InsumoPendiente as exc:
                registro={'regla':regla,'cuenta':None,'celda':None,
                          'formula_excel':None,'valor':None,
                          'estado':'INSUMO_PENDIENTE','certificado':False,'motivo':str(exc)}
            resultados.append({'id_jornada':jornada,'id_archivo':archivo,
                               'tipo_insumo':tipo,'correlation_id':item.get('correlation_id'),**registro})
    salida={'id_jornada':jornada,'fecha_contable':payload['fecha_contable'],
            'origen':'ENTRADA_EXPLICITA_DIAGNOSTICA','certificado':False,
            'resultados':resultados,'cruces':[],
            'advertencias':['No hay correspondencias Host homologadas.',
                            'No persistir ni presentar como conciliado.',
                            'Los valores provienen de entradas explicitas, no de una lectura automatica de PostgreSQL.']}
    if parte_filas is not None:
        detalle=consolidar(parte_filas)
        salida['diagnostico_caet_cant']={'conteos':detalle['conteos'],
          'L3_comisiones_exitosas':str(detalle['L3_comisiones_exitosas']),
          'estado':detalle['estado'],'certificado':False,
          'advertencia':'Sin correspondencia acreditada entre filas parte y archivos de la jornada.'}
    return salida

def ejecutar(entrada:Path, salida:Path, parte_csv:Path|None=None):
    entrada,salida=Path(entrada),Path(salida)
    if salida.exists(): raise FileExistsError(salida)
    payload=json.loads(entrada.read_text(encoding='utf-8-sig'))
    filas=None
    if parte_csv is not None:
        with Path(parte_csv).open(encoding='utf-8-sig',newline='') as f:
            lector=csv.DictReader(f,delimiter=';')
            requeridos={'TX','TIPO','cuenta','cuentas comisiones','cuenta 880',*CAMPOS}
            if not lector.fieldnames or not requeridos.issubset(lector.fieldnames):
                raise ValueError('Columnas parte incompletas')
            filas=list(lector)
    resultado=procesar(payload,filas)
    resultado['sha256_entrada']=hashlib.sha256(entrada.read_bytes()).hexdigest()
    if parte_csv is not None:
        resultado['sha256_parte_csv']=hashlib.sha256(Path(parte_csv).read_bytes()).hexdigest()
    salida.mkdir(parents=True,exist_ok=False)
    (salida/'informe.json').write_text(json.dumps(resultado,ensure_ascii=False,indent=2,default=_serializar),encoding='utf-8')
    return resultado

def main():
    p=argparse.ArgumentParser(description='Diagnostico F2 por jornada sin SQL')
    p.add_argument('--entrada',required=True,type=Path)
    p.add_argument('--salida',required=True,type=Path)
    p.add_argument('--parte-csv',type=Path)
    a=p.parse_args(); r=ejecutar(a.entrada,a.salida,a.parte_csv)
    print(json.dumps({'id_jornada':r['id_jornada'],'resultados':len(r['resultados']),
                      'certificado':False,'salida':str(a.salida)},ensure_ascii=False))
if __name__=='__main__': main()

"""INC46: puente controlado entre Inc41 y las formulas Inc45.
No presupone equivalencia de TOTALES B/C con vl_interc/vl_total.
No cambia el reporte operativo ni realiza escrituras SQL.
"""
from __future__ import annotations
import argparse, hashlib, json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from app.services.fase2.formulas_credibanco_inc45 import ejecutar as formulas, verificar_catalogo

CAMPOS = {'vl_interc', 'vl_total'}

class MapeoNoAcreditado(ValueError):
    pass

def _decimal(v):
    if v is None or isinstance(v, bool): raise MapeoNoAcreditado('Importe ausente')
    try: n=Decimal(str(v))
    except (ValueError, InvalidOperation): raise MapeoNoAcreditado('Importe no numerico') from None
    if not n.is_finite(): raise MapeoNoAcreditado('Importe no finito')
    return n

def construir(informe41, catalogo, mapeos=(), *, f90=None):
    """Mapeos explícitos: concepto, insumo, columna_totales, campo_pg, evidencia.
    No es posible poblar simultáneamente B/C de una misma clave con insumos distintos
    sin una regla de consolidación; se rechazan combinaciones ambiguas.
    """
    verificar_catalogo(catalogo)
    if informe41.get('origen') != 'POSTGRESQL_SOLO_LECTURA' or informe41.get('certificado') is not False:
        raise MapeoNoAcreditado('Se requiere informe Inc41 diagnostico')
    if not isinstance(mapeos, (list, tuple)): raise MapeoNoAcreditado('Mapeos deben ser lista')
    grupos=[r for r in informe41.get('resultados',[]) if r.get('familia')=='principal']
    permitidos={(r.get('concepto_literal',r.get('concepto')), r['insumo']) for r in grupos}
    claves={r['concepto'] for r in catalogo['reglas']}
    indice={}; pendientes=[]; procedencia=[]
    for m in mapeos:
        if not isinstance(m,dict): raise MapeoNoAcreditado('Mapeo invalido')
        concepto=m.get('concepto'); insumo=m.get('insumo'); columna=m.get('columna_totales'); campo=m.get('campo_pg')
        evidencia=m.get('evidencia')
        if concepto not in claves or (concepto,insumo) not in permitidos or columna not in ('B','C') or campo not in CAMPOS:
            raise MapeoNoAcreditado('Mapeo fuera de alcance o campo no autorizado')
        if not isinstance(evidencia,str) or not evidencia.strip(): raise MapeoNoAcreditado('Falta evidencia documental')
        llave=(concepto,columna)
        if llave in indice: raise MapeoNoAcreditado('Columna TOTALES duplicada o ambigua')
        candidatos=[r for r in grupos if r.get('concepto_literal',r.get('concepto'))==concepto and r['insumo']==insumo]
        if len(candidatos)!=1: raise MapeoNoAcreditado('Origen ambiguo por concepto e insumo')
        grupo=candidatos[0]; valor=grupo['importes'].get(campo)
        if valor is None: raise MapeoNoAcreditado('Campo de importe ausente')
        valor=_decimal(valor)
        indice[llave]=str(valor)
        procedencia.append({'concepto':concepto,'insumo':insumo,'columna':columna,'campo':campo,
            'valor':str(valor),'id_archivo':grupo['id_archivo'], 'lineas_origen':grupo['lineas_origen'],
            'evidencia':evidencia,'estado':'MAPEO_DECLARADO_NO_CERTIFICADO'})
    filas=[]
    for concepto in dict.fromkeys(r['concepto'] for r in catalogo['reglas']):
        cols={col:indice.get((concepto,col)) for col in ('B','C')}
        if not any(v is not None for v in cols.values()):
            pendientes.append({'concepto':concepto,'motivo':'SIN_MAPEO_ACREDITADO'})
        filas.append({'A':concepto, **cols})
    resultado=formulas(catalogo,filas,f90=f90,evidencia={'tipo':'PROYECCION_INC46_NO_HOMOLOGADA'})
    # Inc45 traduce ausencia de coincidencia a cero; aquí las claves están presentes,
    # pero B/C sin equivalencia permanecen nulas y producen PENDIENTE_DATO.
    resultado.update(id_jornada=informe41['id_jornada'],origen='INC41_INC45_PUENTE_CONTROLADO',
        mapeos=procedencia,pendientes=pendientes,certificado=False,
        advertencias=resultado['advertencias']+['Mapeos declarados requieren validacion funcional; no publicar en Valor Franquicia',
        'No se deducen columnas B/C ni se aplican cruces HA22/HA26/HA32'])
    return resultado

def main():
    p=argparse.ArgumentParser(description='INC46: puente controlado Credibanco, solo lectura')
    p.add_argument('--jornada',type=int,required=True);p.add_argument('--catalogo',required=True)
    p.add_argument('--mapeos',help='JSON opcional: mapeos documentados (sin este archivo no hay equivalencias)')
    p.add_argument('--f90',help='Valor F90 acreditado, opcional')
    p.add_argument('--salida',required=True)
    a=p.parse_args(); destino=Path(a.salida)
    if destino.exists():p.error('La salida ya existe')
    from app.services.fase2.calculo_canje_pg_inc41 import leer_pg
    catalogo=json.loads(Path(a.catalogo).read_text(encoding='utf-8-sig'))
    mapeos=json.loads(Path(a.mapeos).read_text(encoding='utf-8-sig')) if a.mapeos else []
    informe=construir(leer_pg(a.jornada),catalogo,mapeos,f90=a.f90)
    texto=json.dumps(informe,ensure_ascii=False,indent=2)
    destino.mkdir(parents=True,exist_ok=False)
    (destino/'informe_inc46.json').write_text(texto,encoding='utf-8')
    (destino/'sha256_informe.txt').write_text(hashlib.sha256(texto.encode()).hexdigest()+'\n',encoding='utf-8')
    print(json.dumps({'jornada':a.jornada,'formulas':len(informe['resultados']),
        'mapeos':len(informe['mapeos']),'certificado':False},ensure_ascii=False))

if __name__=='__main__':main()

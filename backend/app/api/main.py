import re,uuid
from dataclasses import asdict
from pathlib import Path
from fastapi import FastAPI,HTTPException,Query,Header
from app.core.config import settings
from app.repositories.database import connection
from app.repositories.insumo import InsumoRepository
from app.repositories.jornada import JornadaRepository
from app.repositories.archivo import ArchivoRepository as ArchivoRepo
from app.ingestion.orchestrator import IngestionOrchestrator
app=FastAPI(title="Concilia Franquicias Fase 1",version="1.0.0")

FECHA_EN_NOMBRE=re.compile(r"_F(\d{2})(\d{2})(\d{2})(?:\D|$)",re.IGNORECASE)

def _fecha_en_nombre(nombre_archivo:str)->str|None:
    """Extrae la fecha contable embebida en archivos Host con convención _F<AAMMDD>
    (p.ej. DESCARHA22_F260914.TXT -> 2026-09-14). Devuelve None si el nombre no la trae."""
    m=FECHA_EN_NOMBRE.search(nombre_archivo)
    if not m: return None
    aa,mm,dd=m.groups()
    return f"20{aa}-{mm}-{dd}"

def _buscar_en_ruta_estatica(tipo_insumo:str,patron_archivo:str|None,fecha_contable:str)->Path|None:
    base=Path(settings.incoming_dir)
    if not base.exists(): return None
    patron=(patron_archivo or f"*{tipo_insumo}*").replace("%%ODATE",fecha_contable.replace("-",""))
    candidatos=[p for p in base.glob(patron) if p.is_file()]
    if not candidatos: return None
    candidatos.sort(key=lambda p:p.stat().st_mtime,reverse=True)
    return candidatos[0]

@app.get("/api/v1/jornadas/actual")
def jornada_actual():
 with connection() as c:
  row=c.execute("SELECT ID_JORNADA,FECHA_CONTABLE,ESTADO,ARCHIVOS_ESPERADOS,ARCHIVOS_RECIBIDOS,ARCHIVOS_PROCESADOS,ARCHIVOS_PENDIENTES,TOTAL_REGISTROS,PORCENTAJE_AVANCE FROM CON_JORNADA ORDER BY FECHA_CONTABLE DESC LIMIT 1").fetchone()
  if not row: raise HTTPException(204)
  keys=["idJornada","fechaContable","estado","archivosEsperados","archivosRecibidos","archivosProcesados","archivosPendientes","totalRegistros","porcentajeAvance"]
  return dict(zip(keys,row))

@app.get("/api/v1/archivos")
def archivos(fechaContable:str=Query(...)):
 with connection() as c:
  rows=c.execute("""SELECT a.ID_ARCHIVO,i.FUENTE,i.TIPO_INSUMO,a.NOMBRE_ARCHIVO,a.TOTAL_REGISTROS,a.ESTADO_RECEPCION,a.ESTADO_VALIDACION,a.ESTADO_PROCESAMIENTO,a.ESTADO_CARGA,a.ESTADO_DISPONIBILIDAD,a.DISPONIBLE
 FROM CON_JORNADA j JOIN CON_ARCHIVO_CARGA a ON a.ID_JORNADA=j.ID_JORNADA JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO WHERE j.FECHA_CONTABLE=%s ORDER BY i.ORDEN_VISUAL""",(fechaContable,)).fetchall()
  if not rows: raise HTTPException(204)
  keys=["idArchivo","fuente","tipoInsumo","nombreArchivo","totalRegistros","estadoRecepcion","estadoValidacion","estadoProcesamiento","estadoCarga","estadoDisponibilidad","disponible"]
  return {"fechaContable":fechaContable,"totalEsperados":12,"items":[dict(zip(keys,x)) for x in rows]}

@app.get("/api/v1/archivos/{id_archivo}")
def archivo(id_archivo:int):
 with connection() as c:
  row=c.execute("SELECT ID_ARCHIVO,NOMBRE_ARCHIVO,TOTAL_REGISTROS,ESTADO_RECEPCION,ESTADO_VALIDACION,ESTADO_PROCESAMIENTO,ESTADO_CARGA,ESTADO_DISPONIBILIDAD,DISPONIBLE,CORRELATION_ID FROM CON_ARCHIVO_CARGA WHERE ID_ARCHIVO=%s",(id_archivo,)).fetchone()
  if not row: raise HTTPException(404,"ARCHIVO_NO_ENCONTRADO")
  return dict(zip(["idArchivo","nombreArchivo","totalRegistros","estadoRecepcion","estadoValidacion","estadoProcesamiento","estadoCarga","estadoDisponibilidad","disponible","correlationId"],row))

@app.get('/health')
def health():
    return {'status':'UP'}

@app.get('/api/v1/archivos/{id_archivo}/contenido')
def contenido(id_archivo:int,page:int=0,size:int=30):
    if page < 0 or size < 1 or size > 100:
        raise HTTPException(400,'PAGINACION_INVALIDA')
    from app.repositories.content import ContentRepository
    with connection() as c:
        row=c.execute('''SELECT a.DISPONIBLE,i.TIPO_INSUMO FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO WHERE a.ID_ARCHIVO=%s''',(id_archivo,)).fetchone()
        if not row: raise HTTPException(404,'ARCHIVO_NO_ENCONTRADO')
        if not row[0]: raise HTTPException(409,'ARCHIVO_NO_DISPONIBLE')
        items,total=ContentRepository(c).page(row[1],id_archivo,page,size)
        return {'idArchivo':id_archivo,'tipoInsumo':row[1],'page':page,'size':size,'total':total,'items':items}

@app.post('/api/v1/archivos')
def procesar_archivo(fechaContable:str=Query(...),tipoInsumo:str=Query(...),
                      x_correlation_id:str|None=Header(None,alias='X-Correlation-Id')):
    """Procesa un insumo ya depositado en la ruta estática (INCOMING_DIR), emulando
    la llegada real vía Control-M -> Hub Linux -> SFTP -> MinIO/OKD. No recibe el
    archivo por HTTP: lo localiza por el PATRON_ARCHIVO configurado en CON_INSUMO_ESPERADO."""
    correlation_id=x_correlation_id or str(uuid.uuid4())
    with connection() as c:
        insumo=InsumoRepository(c).get_by_tipo(tipoInsumo)
        if insumo is None: raise HTTPException(404,'INSUMO_NO_ENCONTRADO')
        source=_buscar_en_ruta_estatica(tipoInsumo,insumo['patron_archivo'],fechaContable)
        if source is None: raise HTTPException(404,'ARCHIVO_NO_ENCONTRADO_EN_RUTA')
        fecha_archivo=_fecha_en_nombre(source.name)
        if fecha_archivo and fecha_archivo!=fechaContable:
            raise HTTPException(409,f'FECHA_NO_COINCIDE_CON_ARCHIVO: el archivo {source.name} corresponde a {fecha_archivo}, no a {fechaContable}')

        id_jornada=JornadaRepository(c).get_or_create(fechaContable)
        id_archivo=ArchivoRepo(c).get_or_create(id_jornada,insumo['id_insumo'],source.name,correlation_id)
        try:
            result=IngestionOrchestrator(c).execute(id_archivo,tipoInsumo,source,correlation_id)
        except KeyError:
            raise HTTPException(400,'PARSER_NO_IMPLEMENTADO')

        row=c.execute("""SELECT ID_ARCHIVO,NOMBRE_ARCHIVO,TOTAL_REGISTROS,ESTADO_RECEPCION,ESTADO_VALIDACION,
 ESTADO_PROCESAMIENTO,ESTADO_CARGA,ESTADO_DISPONIBILIDAD,DISPONIBLE,CORRELATION_ID
 FROM CON_ARCHIVO_CARGA WHERE ID_ARCHIVO=%s""",(id_archivo,)).fetchone()
        keys=["idArchivo","nombreArchivo","totalRegistros","estadoRecepcion","estadoValidacion",
              "estadoProcesamiento","estadoCarga","estadoDisponibilidad","disponible","correlationId"]
        return {**dict(zip(keys,row)),
                "rutaOrigen":str(source),
                "registrosInsertados":len(result.records) if not result.errors else 0,
                "errores":[asdict(e) for e in result.errors],
                "controles":result.controls}

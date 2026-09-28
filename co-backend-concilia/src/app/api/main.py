import re,uuid
from fastapi import FastAPI,HTTPException,Query,Header,UploadFile,File,Form,BackgroundTasks
from app.repositories.database import connection
from app.repositories.insumo import InsumoRepository
from app.repositories.jornada import JornadaRepository
from app.repositories.archivo import ArchivoRepository as ArchivoRepo
from app.clients import minio_client
from app.clients.parseo_client import parsear
app=FastAPI(title="Concilia Franquicias Fase 1 - Back",version="1.0.0")

FECHA_EN_NOMBRE=re.compile(r"_F(\d{2})(\d{2})(\d{2})(?:\D|$)",re.IGNORECASE)

def _fecha_en_nombre(nombre_archivo:str)->str|None:
    """Extrae la fecha contable embebida en archivos Host con convención _F<AAMMDD>
    (p.ej. DESCARHA22_F260914.TXT -> 2026-09-14). Devuelve None si el nombre no la trae."""
    m=FECHA_EN_NOMBRE.search(nombre_archivo)
    if not m: return None
    aa,mm,dd=m.groups()
    return f"20{aa}-{mm}-{dd}"

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
  rows=c.execute("""SELECT a.ID_ARCHIVO,i.FUENTE,i.TIPO_INSUMO,a.NOMBRE_ARCHIVO,a.TOTAL_REGISTROS,a.REGISTROS_PROCESADOS,
 COALESCE(a.ESTADO_RECEPCION,'No recibido'),COALESCE(a.ESTADO_PROCESAMIENTO,'Pendiente')
 FROM CON_INSUMO_ESPERADO i
 LEFT JOIN CON_JORNADA j ON j.FECHA_CONTABLE=%s
 LEFT JOIN CON_ARCHIVO_CARGA a ON a.ID_INSUMO=i.ID_INSUMO AND a.ID_JORNADA=j.ID_JORNADA
 WHERE i.ACTIVO ORDER BY i.ORDEN_VISUAL""",(fechaContable,)).fetchall()
  if not rows: raise HTTPException(204)
  keys=["idArchivo","fuente","tipoInsumo","nombreArchivo","totalRegistros","registrosProcesados","estadoRecepcion","estadoProcesamiento"]
  return {"fechaContable":fechaContable,"totalEsperados":len(rows),"items":[dict(zip(keys,x)) for x in rows]}

@app.get("/api/v1/jornadas/fechas")
def jornadas_fechas(limit:int=20):
 with connection() as c:
  rows=c.execute("SELECT FECHA_CONTABLE,ESTADO FROM CON_JORNADA ORDER BY FECHA_CONTABLE DESC LIMIT %s",(limit,)).fetchall()
  return {"items":[{"fechaContable":str(f),"estado":e} for f,e in rows]}

@app.get("/api/v1/archivos/{id_archivo}")
def archivo(id_archivo:int):
 with connection() as c:
  row=c.execute("SELECT ID_ARCHIVO,NOMBRE_ARCHIVO,TOTAL_REGISTROS,REGISTROS_PROCESADOS,ESTADO_RECEPCION,ESTADO_PROCESAMIENTO,CORRELATION_ID,MOTIVO_ESTADO FROM CON_ARCHIVO_CARGA WHERE ID_ARCHIVO=%s",(id_archivo,)).fetchone()
  if not row: raise HTTPException(404,"ARCHIVO_NO_ENCONTRADO")
  return dict(zip(["idArchivo","nombreArchivo","totalRegistros","registrosProcesados","estadoRecepcion","estadoProcesamiento","correlationId","motivoEstado"],row))

@app.get('/health')
def health():
    return {'status':'UP'}

@app.get('/api/v1/archivos/{id_archivo}/contenido')
def contenido(id_archivo:int,page:int=0,size:int=30):
    if page < 0 or size < 1 or size > 100:
        raise HTTPException(400,'PAGINACION_INVALIDA')
    from app.repositories.content import ContentRepository
    with connection() as c:
        row=c.execute('''SELECT a.ESTADO_PROCESAMIENTO,i.TIPO_INSUMO FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO WHERE a.ID_ARCHIVO=%s''',(id_archivo,)).fetchone()
        if not row: raise HTTPException(404,'ARCHIVO_NO_ENCONTRADO')
        # "Procesando" se permite a propósito: deja ver en vivo lo que ya se
        # insertó (DELETE+INSERT incremental en parseo) mientras el archivo
        # sigue cargando, no solo cuando ya terminó.
        if row[0] not in ('Procesado','Procesando'): raise HTTPException(409,'ARCHIVO_NO_DISPONIBLE')
        items,total=ContentRepository(c).page(row[1],id_archivo,page,size)
        return {'idArchivo':id_archivo,'tipoInsumo':row[1],'page':page,'size':size,'total':total,'items':items}

def _procesar_en_segundo_plano(id_archivo:int,tipo_insumo:str,minio_key:str,correlation_id:str):
    """El parseo puede tardar minutos en archivos grandes (inserta registro a
    registro); parseo va marcando ESTADO_PROCESAMIENTO/REGISTROS_PROCESADOS por
    su cuenta a medida que avanza (ver ParseoOrchestrator), y el front hace
    polling de GET /api/v1/archivos/{id} en vez de esperar esta llamada.
    Solo hay que cubrir aquí el caso en que parseo ni siquiera llega a tocar la
    fila (no alcanzable, o tipo de insumo no soportado) — ahí queda "Pendiente"
    para siempre si no se marca error desde este lado."""
    try:
        parsear(id_archivo,tipo_insumo,minio_key,correlation_id)
    except HTTPException as exc:
        with connection() as c:
            ArchivoRepo(c).update_state(id_archivo,'ESTADO_PROCESAMIENTO','Error',str(exc.detail))

@app.post('/api/v1/archivos')
def cargar_archivo(background_tasks:BackgroundTasks,fechaContable:str=Form(...),tipoInsumo:str=Form(...),file:UploadFile=File(...),
                    x_correlation_id:str|None=Header(None,alias='X-Correlation-Id')):
    """Recibe el archivo, lo guarda en MinIO (respaldo/trazabilidad) y delega el
    parseo + carga a la API de parseo (servicio independiente) en segundo plano:
    la respuesta no espera a que termine, el front sigue el avance con
    GET /api/v1/archivos/{id}."""
    correlation_id=x_correlation_id or str(uuid.uuid4())
    with connection() as c:
        insumo=InsumoRepository(c).get_by_tipo(tipoInsumo)
        if insumo is None: raise HTTPException(404,'INSUMO_NO_ENCONTRADO')
        nombre_archivo=file.filename or f'{tipoInsumo}.dat'
        fecha_archivo=_fecha_en_nombre(nombre_archivo)
        if fecha_archivo and fecha_archivo!=fechaContable:
            raise HTTPException(409,f'FECHA_NO_COINCIDE_CON_ARCHIVO: el archivo {nombre_archivo} corresponde a {fecha_archivo}, no a {fechaContable}')

        id_jornada=JornadaRepository(c).get_or_create(fechaContable)
        id_archivo=ArchivoRepo(c).get_or_create(id_jornada,insumo['id_insumo'],nombre_archivo,correlation_id)

    minio_key=f"{fechaContable}/{tipoInsumo}/{id_archivo}_{nombre_archivo}"
    minio_client.subir(minio_key,file.file.read())

    background_tasks.add_task(_procesar_en_segundo_plano,id_archivo,tipoInsumo,minio_key,correlation_id)

    with connection() as c:
        row=c.execute("""SELECT ID_ARCHIVO,NOMBRE_ARCHIVO,TOTAL_REGISTROS,REGISTROS_PROCESADOS,ESTADO_RECEPCION,
 ESTADO_PROCESAMIENTO,CORRELATION_ID
 FROM CON_ARCHIVO_CARGA WHERE ID_ARCHIVO=%s""",(id_archivo,)).fetchone()
    keys=["idArchivo","nombreArchivo","totalRegistros","registrosProcesados","estadoRecepcion",
          "estadoProcesamiento","correlationId"]
    return dict(zip(keys,row))

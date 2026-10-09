import math,re,uuid
from datetime import date
from fastapi import FastAPI,HTTPException,Header,UploadFile,File,Form,BackgroundTasks
from app.core.fechas import derivar_fechas_contables
from app.repositories.database import connection
from app.repositories.jornada import JornadaRepository
from app.repositories.archivo import ArchivoRepository as ArchivoRepo
from app.repositories.content import ContentRepository
from app.clients import minio_client
from app.clients.parseo_client import parsear
app=FastAPI(title="Concilia Franquicias Fase 1 - Back",version="2.4.0")

FECHA_EN_NOMBRE=re.compile(r"_F(\d{2})(\d{2})(\d{2})(?:\D|$)",re.IGNORECASE)

def _fecha_en_nombre(nombre_archivo:str)->str|None:
    """Extrae la fecha contable embebida en archivos Host con convención _F<AAMMDD>
    (p.ej. DESCARHA22_F260914.TXT -> 2026-09-14). Devuelve None si el nombre no la trae."""
    m=FECHA_EN_NOMBRE.search(nombre_archivo)
    if not m: return None
    aa,mm,dd=m.groups()
    return f"20{aa}-{mm}-{dd}"

ESTADO_RECEPCION_MAP={"Recibido":"RECIBIDO","No recibido":"NO_RECIBIDO","Rechazado":"RECHAZADO"}
ESTADO_PROCESAMIENTO_MAP={"Pendiente":"PENDIENTE","Procesando":"PROCESANDO","Procesado":"PROCESADO","Error":"ERROR"}

def _insumo_contrato(i:dict)->dict:
    return {**i,"estadoRecepcion":ESTADO_RECEPCION_MAP.get(i["estadoRecepcion"],"ESPERADO"),
            "estadoProcesamiento":ESTADO_PROCESAMIENTO_MAP.get(i["estadoProcesamiento"],"PENDIENTE")}

def _estado_jornada(insumos:list[dict])->str:
    """insumos ya en los enums del contrato (ver _insumo_contrato)."""
    if any(i["estadoProcesamiento"]=="ERROR" for i in insumos): return "ERROR"
    esperados=len(insumos)
    procesados=sum(1 for i in insumos if i["estadoProcesamiento"]=="PROCESADO")
    if esperados and procesados>=esperados: return "COMPLETA"
    if any(i["estadoProcesamiento"]=="PROCESANDO" for i in insumos): return "EN_PROCESO"
    recibidos=sum(1 for i in insumos if i["estadoRecepcion"]=="RECIBIDO")
    if recibidos>0: return "CON_NOVEDAD"
    return "PENDIENTE"

@app.get('/health')
def health():
    return {'status':'UP'}

@app.get("/api/v1/jornadas")
def jornadas(fechaConciliacion:str):
    try: fecha=date.fromisoformat(fechaConciliacion)
    except ValueError: raise HTTPException(400,'FECHA_INVALIDA')
    fechas=sorted(derivar_fechas_contables(fecha))
    items=[]
    with connection() as c:
        for fc in fechas:
            id_jornada=JornadaRepository(c).get_or_create(fc)
            ArchivoRepo(c).ensure_insumos(id_jornada)
            insumos=[_insumo_contrato(i) for i in ArchivoRepo(c).listar_insumos(id_jornada)]
            items.append({"idJornada":id_jornada,"fechaContable":fc.isoformat(),"estado":_estado_jornada(insumos)})
    if not items: raise HTTPException(204)
    return {"fechaConciliacion":fechaConciliacion,"jornadas":items}

@app.get("/api/v1/jornadas/{id_jornada}")
def jornada_detalle(id_jornada:int):
    with connection() as c:
        resumen=JornadaRepository(c).resumen(id_jornada)
        if not resumen: raise HTTPException(404,'JORNADA_NO_ENCONTRADA')
        _,fecha_contable=resumen
        insumos=[_insumo_contrato(i) for i in ArchivoRepo(c).listar_insumos(id_jornada)]
    return {
        "idJornada":id_jornada,"fechaContable":fecha_contable.isoformat(),"estado":_estado_jornada(insumos),
        "archivosEsperados":len(insumos),
        "archivosRecibidos":sum(1 for i in insumos if i["estadoRecepcion"]=="RECIBIDO"),
        "archivosProcesados":sum(1 for i in insumos if i["estadoProcesamiento"]=="PROCESADO"),
        "archivosConError":sum(1 for i in insumos if i["estadoProcesamiento"]=="ERROR"),
        "insumos":insumos,
    }

@app.get('/api/v1/archivos/{id_archivo}/contenido')
def contenido(id_archivo:int,page:int=0,pageSize:int=30):
    if page<0 or pageSize<1 or pageSize>100:
        raise HTTPException(400,'PAGINACION_INVALIDA')
    with connection() as c:
        row=c.execute('''SELECT a.ESTADO_RECEPCION,a.ESTADO_PROCESAMIENTO,a.NOMBRE_ARCHIVO,a.CORRELATION_ID,i.TIPO_INSUMO
 FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO WHERE a.ID_ARCHIVO=%s''',(id_archivo,)).fetchone()
        if not row: raise HTTPException(404,'ARCHIVO_NO_ENCONTRADO')
        estado_recepcion,estado_procesamiento,nombre_archivo,correlation_id,tipo_insumo=row
        # "Procesando" se permite a propósito: deja ver en vivo lo que ya se
        # insertó (DELETE+INSERT incremental en parseo) mientras el archivo
        # sigue cargando, no solo cuando ya terminó.
        if estado_procesamiento not in ('Procesado','Procesando'): raise HTTPException(409,'ARCHIVO_NO_DISPONIBLE')
        items,total,headers=ContentRepository(c).page(tipo_insumo,id_archivo,page,pageSize)
    return {
        'idArchivo':id_archivo,'tipoInsumo':tipo_insumo,'nombreArchivo':nombre_archivo,
        'estadoRecepcion':ESTADO_RECEPCION_MAP.get(estado_recepcion,'ESPERADO'),
        'estadoProcesamiento':ESTADO_PROCESAMIENTO_MAP.get(estado_procesamiento,'PENDIENTE'),
        'correlationId':correlation_id,'headers':headers,'items':items,
        'pagination':{'page':page,'pageSize':pageSize,'totalItems':total,'totalPages':math.ceil(total/pageSize) if total else 0},
    }

def _procesar_en_segundo_plano(id_archivo:int,tipo_insumo:str,minio_key:str,correlation_id:str):
    """El parseo puede tardar minutos en archivos grandes (inserta registro a
    registro); parseo va marcando ESTADO_PROCESAMIENTO/REGISTROS_PROCESADOS por
    su cuenta a medida que avanza (ver ParseoOrchestrator), y el front hace
    polling de GET /api/v1/jornadas/{idJornada} en vez de esperar esta llamada.
    Hay que cubrir dos casos en que parseo no deja la fila en un estado final:
    (1) ni siquiera llega a tocarla (no alcanzable, tipo no soportado) -> acá
    llega como HTTPException; (2) responde 200 pero con un error interno que
    ocurrió DESPUÉS de marcar "Procesando" y ANTES de la actualización final
    (ver orchestrator.py) -> el cuerpo trae estadoProcesamiento="Error" pero
    la fila se queda en "Procesando" si no se revisa esto explícitamente."""
    try:
        resultado=parsear(id_archivo,tipo_insumo,minio_key,correlation_id)
        if resultado.get('estadoProcesamiento')=='Error':
            motivo='; '.join(e.get('mensaje','') for e in resultado.get('errores',[])) or 'Error de procesamiento'
            with connection() as c:
                ArchivoRepo(c).update_state(id_archivo,'ESTADO_PROCESAMIENTO','Error',motivo)
    except HTTPException as exc:
        with connection() as c:
            ArchivoRepo(c).update_state(id_archivo,'ESTADO_PROCESAMIENTO','Error',str(exc.detail))

@app.post('/api/v1/jornadas/{id_jornada}/archivos')
def cargar_archivo_original(id_jornada:int,background_tasks:BackgroundTasks,idArchivo:int=Form(...),archivo:UploadFile=File(...),
                             x_correlation_id:str|None=Header(None,alias='X-Correlation-Id')):
    """Carga manual del archivo original esperado (CARGAR_ARCHIVO_ORIGINAL):
    idArchivo identifica el insumo esperado -placeholder ya creado al resolver
    la jornada, ver ArchivoRepository.ensure_insumos- dentro de idJornada."""
    with connection() as c:
        resumen=JornadaRepository(c).resumen(id_jornada)
        if not resumen: raise HTTPException(404,'JORNADA_NO_ENCONTRADA')
        _,fecha_contable=resumen
        tipo_insumo,correlation_id_actual,error=ArchivoRepo(c).obtener_para_carga(idArchivo,id_jornada)
        if error=='ARCHIVO_NO_ENCONTRADO' or error=='ARCHIVO_NO_PERTENECE_A_JORNADA': raise HTTPException(404,error)
        if error=='CARGA_NO_PERMITIDA': raise HTTPException(409,error)

        nombre_archivo=archivo.filename or f'{tipo_insumo}.dat'
        fecha_archivo=_fecha_en_nombre(nombre_archivo)
        fecha_contable_iso=fecha_contable.isoformat()
        if fecha_archivo and fecha_archivo!=fecha_contable_iso:
            raise HTTPException(409,f'FECHA_NO_COINCIDE_CON_ARCHIVO: el archivo {nombre_archivo} corresponde a {fecha_archivo}, no a {fecha_contable_iso}')

        correlation_id=x_correlation_id or correlation_id_actual
        ArchivoRepo(c).marcar_recibido(idArchivo,nombre_archivo,correlation_id)

    minio_key=f"{fecha_contable_iso}/{tipo_insumo}/{idArchivo}_{nombre_archivo}"
    minio_client.subir(minio_key,archivo.file.read())

    background_tasks.add_task(_procesar_en_segundo_plano,idArchivo,tipo_insumo,minio_key,correlation_id)

    return {
        "idSolicitud":str(uuid.uuid4()),"idJornada":id_jornada,"idArchivo":idArchivo,
        "estado":"ACEPTADO","mensaje":"Archivo original aceptado para procesamiento.",
    }

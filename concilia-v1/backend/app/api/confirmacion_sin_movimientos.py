"""Confirmacion auditable de insumos sin movimientos persistibles."""
from fastapi import APIRouter, HTTPException, Path, BackgroundTasks
from pydantic import BaseModel, Field
from psycopg import OperationalError
from app.repositories.database import connection
from app.services.procesamiento_automatico import procesar_jornada_si_lista

router = APIRouter(prefix="/api/v1/archivos", tags=["Confirmacion sin movimientos"])

class Confirmacion(BaseModel):
    usuario: str = Field(min_length=2, max_length=100)
    motivo: str = Field(min_length=5, max_length=500)

@router.post("/{id_archivo}/confirmar-sin-movimientos")
def confirmar_sin_movimientos(datos: Confirmacion, background_tasks: BackgroundTasks,
                              id_archivo: int = Path(gt=0)):
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout = '5s'")
                cur.execute("""SELECT i.id_jornada,i.id_insumo_esperado,i.estado,
                                      a.total_registros,j.estado,a.correlation_id
                               FROM con_insumo_esperado i
                               JOIN con_archivo_carga a ON a.id_archivo=i.id_archivo
                               JOIN con_jornada j ON j.id_jornada=i.id_jornada
                               WHERE a.id_archivo=%s FOR UPDATE OF i,j""",(id_archivo,))
                fila=cur.fetchone()
                if fila is None: raise HTTPException(404,"Archivo no asociado")
                jornada,insumo,estado,total,estado_jornada,corr=fila
                if estado_jornada=='COMPLETADA': raise HTTPException(409,"Jornada completada")
                if estado!='RECIBIDO' or total!=0:
                    raise HTTPException(409,"Solo archivos recibidos con cero registros persistibles")
                cur.execute("SELECT 1 FROM con_confirmacion_sin_movimientos WHERE id_archivo=%s",(id_archivo,))
                existe=cur.fetchone() is not None
                if not existe:
                    cur.execute("""INSERT INTO con_confirmacion_sin_movimientos
                                   (id_archivo,id_jornada,id_insumo_esperado,usuario,motivo,correlation_id)
                                   VALUES (%s,%s,%s,%s,%s,%s)""",
                                (id_archivo,jornada,insumo,datos.usuario,datos.motivo,corr))
                    cur.execute("""INSERT INTO con_trazabilidad
                                   (id_archivo,id_jornada,correlation_id,tipo_evento,componente,detalle)
                                   VALUES (%s,%s,%s,'SIN_MOVIMIENTOS_CONFIRMADO','CONFIRMACION_API',%s)""",
                                (id_archivo,jornada,corr,
                                 'Usuario: '+datos.usuario+'; motivo: '+datos.motivo))
        background_tasks.add_task(procesar_jornada_si_lista,jornada)
        return {'id_archivo':id_archivo,'confirmado':True,'idempotente':existe}
    except OperationalError as exc:
        raise HTTPException(503,'Base de datos no disponible') from exc

@router.get('/confirmaciones/jornada/{id_jornada}')
def consultar_confirmaciones(id_jornada: int = Path(gt=0)):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION READ ONLY')
            cur.execute("""SELECT c.id_archivo FROM con_confirmacion_sin_movimientos c
                           JOIN con_insumo_esperado i ON i.id_archivo=c.id_archivo
                           WHERE i.id_jornada=%s""",(id_jornada,))
            return {'ids_archivos':[r[0] for r in cur.fetchall()]}

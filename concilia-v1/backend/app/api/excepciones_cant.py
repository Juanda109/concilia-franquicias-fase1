"""Consultas de excepciones CANT; no modifica estados ni registros."""
from fastapi import APIRouter, HTTPException, Query
from app.repositories.database import connection

router = APIRouter(prefix="/api/v1/archivos", tags=["Excepciones CANT"])

@router.get("/{id_archivo}/excepciones-cant")
def consultar_excepciones_cant(id_archivo: int, page: int = Query(1, ge=1), pageSize: int = Query(20, ge=1, le=200)):
    if id_archivo <= 0:
        raise HTTPException(status_code=422, detail="ID de archivo invalido")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""SELECT tipo_archivo, total_registros FROM public.con_archivo_carga WHERE id_archivo=%s""", (id_archivo,))
            archivo=cur.fetchone()
            if not archivo or archivo[0] != 'CANT':
                raise HTTPException(status_code=404, detail="Archivo CANT no encontrado")
            cur.execute("""SELECT COUNT(*) FROM public.con_franquicia_resultado WHERE id_archivo=%s""", (id_archivo,))
            normalizados=cur.fetchone()[0]
            cur.execute("""SELECT COUNT(*) FROM public.con_cant_excepcion_cuenta WHERE id_archivo=%s""", (id_archivo,))
            total=cur.fetchone()[0]
            cur.execute("""SELECT cuenta, motivo, COUNT(*) AS cantidad
                FROM public.con_cant_excepcion_cuenta WHERE id_archivo=%s
                GROUP BY cuenta,motivo ORDER BY cantidad DESC, cuenta""", (id_archivo,))
            cuentas=[{'cuenta':r[0], 'motivo':r[1], 'cantidad':r[2]} for r in cur.fetchall()]
            cur.execute("""SELECT linea_origen,cuenta,motivo,correlation_id,fec_registro
                FROM public.con_cant_excepcion_cuenta WHERE id_archivo=%s
                ORDER BY linea_origen LIMIT %s OFFSET %s""", (id_archivo,pageSize,(page-1)*pageSize))
            detalles=[{'linea_origen':r[0],'cuenta':r[1],'motivo':r[2],
                'correlation_id':r[3],'fec_registro':r[4].isoformat() if r[4] else None} for r in cur.fetchall()]
    return {'id_archivo':id_archivo,'registros_recibidos':archivo[1],
            'normalizados':normalizados,'excepciones':total,
            'estado_funcional':'REVISION_FUNCIONAL' if total else None,
            'motivo':'CUENTAS_SIN_REGLA' if total else None,
            'cuentas':cuentas,'page':page,'pageSize':pageSize,'total':total,'detalle':detalles}

@router.get("/excepciones-cant/jornada/{id_jornada}")
def resumen_excepciones_cant_jornada(id_jornada: int):
    if id_jornada <= 0:
        raise HTTPException(status_code=422, detail="Jornada invalida")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("""SELECT a.id_archivo, COUNT(e.id_excepcion), a.total_registros
                FROM public.con_insumo_esperado i
                JOIN public.con_archivo_carga a ON a.id_archivo=i.id_archivo
                LEFT JOIN public.con_cant_excepcion_cuenta e ON e.id_archivo=a.id_archivo
                WHERE i.id_jornada=%s AND i.tipo_insumo='CANT'
                GROUP BY a.id_archivo,a.total_registros""",(id_jornada,))
            filas=cur.fetchall()
            resultado=[]
            for archivo,excepciones,recibidos in filas:
                cur.execute("SELECT COUNT(*) FROM public.con_franquicia_resultado WHERE id_archivo=%s",(archivo,))
                normalizados=cur.fetchone()[0]
                resultado.append({'id_archivo':archivo,'recibidos':recibidos,'normalizados':normalizados,
                    'excepciones':excepciones,'estado_funcional':'REVISION_FUNCIONAL' if excepciones else None,
                    'motivo':'CUENTAS_SIN_REGLA' if excepciones else None})
    return {'id_jornada':id_jornada,'archivos':resultado}

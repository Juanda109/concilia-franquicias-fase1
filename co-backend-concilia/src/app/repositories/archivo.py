import uuid


def _acciones_permitidas(estado_recepcion, estado_procesamiento):
    acciones = []
    # También se puede "ver detalle" en Error/Rechazado: ahí no hay contenido
    # tabular, pero la vista de detalle muestra el motivo guardado (ver
    # GET /archivos/{id}/contenido, que para estos casos responde el motivo
    # en vez de filas).
    if estado_procesamiento in ('Procesando', 'Procesado', 'Error') or estado_recepcion == 'Rechazado':
        acciones.append('VER_CONTENIDO')
    # Permite cargar de nuevo si nunca llegó, si se rechazó al subir (nombre o
    # fecha no coincide), o si llegó pero el procesamiento terminó en error
    # (reintento) - nunca mientras está procesando, para no pisar un parseo
    # en curso.
    if estado_procesamiento != 'Procesando' and (
            estado_recepcion in ('No recibido', 'Rechazado') or estado_procesamiento == 'Error'):
        acciones.append('CARGAR_ARCHIVO_ORIGINAL')
    # Solo hay algo que borrar si se intentó cargar algo (aceptado o
    # rechazado) - nunca mientras está procesando, para no borrar bajo un
    # parseo en curso.
    if estado_procesamiento != 'Procesando' and estado_recepcion != 'No recibido':
        acciones.append('ELIMINAR_ARCHIVO')
    return acciones


class ArchivoRepository:
    def __init__(self, conn):
        self.conn = conn

    def update_state(self, id_archivo, field, value, motivo=None):
        allowed = {"ESTADO_RECEPCION", "ESTADO_PROCESAMIENTO"}
        if field not in allowed:
            raise ValueError(field)
        self.conn.execute(
            f"UPDATE CON_ARCHIVO_CARGA SET {field}=%s,MOTIVO_ESTADO=%s,"
            f"FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s",
            (value, motivo, id_archivo))

    def get_or_create(self, id_jornada, id_insumo, nombre_archivo, correlation_id):
        row = self.conn.execute(
            "SELECT ID_ARCHIVO FROM CON_ARCHIVO_CARGA WHERE ID_JORNADA=%s AND ID_INSUMO=%s",
            (id_jornada, id_insumo)).fetchone()
        if row:
            return row[0]
        row = self.conn.execute("""INSERT INTO CON_ARCHIVO_CARGA
 (ID_JORNADA,ID_INSUMO,NOMBRE_ARCHIVO,ESTADO_RECEPCION,ESTADO_PROCESAMIENTO,CORRELATION_ID)
 VALUES (%s,%s,%s,'Recibido','Pendiente',%s) RETURNING ID_ARCHIVO""",
            (id_jornada, id_insumo, nombre_archivo, correlation_id)).fetchone()
        return row[0]

    def ensure_insumos(self, id_jornada):
        """Pre-crea una fila CON_ARCHIVO_CARGA (placeholder, sin archivo) por cada
        insumo activo que todavía no tenga fila en esta jornada, para que todo
        insumo tenga un idArchivo estable desde que se resuelve la jornada,
        exista o no archivo físico recibido."""
        faltantes = self.conn.execute("""SELECT i.ID_INSUMO FROM CON_INSUMO_ESPERADO i
 WHERE i.ACTIVO AND NOT EXISTS (SELECT 1 FROM CON_ARCHIVO_CARGA a WHERE a.ID_JORNADA=%s AND a.ID_INSUMO=i.ID_INSUMO)""",
            (id_jornada,)).fetchall()
        for (id_insumo,) in faltantes:
            self.conn.execute("""INSERT INTO CON_ARCHIVO_CARGA
 (ID_JORNADA,ID_INSUMO,ESTADO_RECEPCION,ESTADO_PROCESAMIENTO,CORRELATION_ID)
 VALUES (%s,%s,'No recibido','Pendiente',%s)""",
                (id_jornada, id_insumo, str(uuid.uuid4())))

    def listar_insumos(self, id_jornada):
        rows = self.conn.execute("""SELECT a.ID_ARCHIVO,i.FUENTE,i.TIPO_INSUMO,a.NOMBRE_ARCHIVO,a.TOTAL_REGISTROS,
 a.ESTADO_RECEPCION,a.ESTADO_PROCESAMIENTO
 FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO
 WHERE a.ID_JORNADA=%s ORDER BY i.ORDEN_VISUAL""", (id_jornada,)).fetchall()
        insumos = []
        for (id_archivo, fuente, tipo_insumo, nombre_archivo, total_registros,
                estado_recepcion, estado_procesamiento) in rows:
            insumos.append({
                "idArchivo": id_archivo,
                "fuente": fuente,
                "tipoInsumo": tipo_insumo,
                "nombreArchivo": nombre_archivo,
                "totalRegistros": total_registros,
                "estadoRecepcion": estado_recepcion,
                "estadoProcesamiento": estado_procesamiento,
                "accionesPermitidas": _acciones_permitidas(estado_recepcion, estado_procesamiento),
            })
        return insumos

    def obtener_para_carga(self, id_archivo, id_jornada):
        row = self.conn.execute(
            """SELECT a.ID_JORNADA,a.ESTADO_RECEPCION,a.ESTADO_PROCESAMIENTO,a.CORRELATION_ID,i.TIPO_INSUMO
 FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO WHERE a.ID_ARCHIVO=%s""",
            (id_archivo,)).fetchone()
        if not row:
            return None, None, None, 'ARCHIVO_NO_ENCONTRADO'
        id_jornada_real, estado_recepcion, estado_procesamiento, correlation_id, tipo_insumo = row
        if id_jornada_real != id_jornada:
            return None, None, None, 'ARCHIVO_NO_PERTENECE_A_JORNADA'
        if 'CARGAR_ARCHIVO_ORIGINAL' not in _acciones_permitidas(estado_recepcion, estado_procesamiento):
            return None, None, None, 'CARGA_NO_PERMITIDA'
        return tipo_insumo, correlation_id, estado_recepcion, None

    def obtener_para_eliminar(self, id_archivo):
        row = self.conn.execute(
            """SELECT a.ID_JORNADA,a.ESTADO_RECEPCION,a.ESTADO_PROCESAMIENTO,a.NOMBRE_ARCHIVO,a.CORRELATION_ID,i.TIPO_INSUMO
 FROM CON_ARCHIVO_CARGA a JOIN CON_INSUMO_ESPERADO i ON i.ID_INSUMO=a.ID_INSUMO WHERE a.ID_ARCHIVO=%s""",
            (id_archivo,)).fetchone()
        if not row:
            return None, 'ARCHIVO_NO_ENCONTRADO'
        id_jornada, estado_recepcion, estado_procesamiento, nombre_archivo, correlation_id, tipo_insumo = row
        if 'ELIMINAR_ARCHIVO' not in _acciones_permitidas(estado_recepcion, estado_procesamiento):
            return None, 'ELIMINACION_NO_PERMITIDA'
        return {
            "idJornada": id_jornada, "tipoInsumo": tipo_insumo, "nombreArchivo": nombre_archivo,
            "estadoRecepcion": estado_recepcion, "correlationId": correlation_id,
        }, None

    def eliminar_carga(self, id_archivo):
        """Vuelve la fila al mismo estado "placeholder" que deja ensure_insumos
        para un insumo nunca cargado, para poder subir el archivo de cero."""
        self.conn.execute("""UPDATE CON_ARCHIVO_CARGA SET NOMBRE_ARCHIVO=NULL,ESTADO_RECEPCION='No recibido',
 ESTADO_PROCESAMIENTO='Pendiente',TOTAL_REGISTROS=NULL,REGISTROS_PROCESADOS=0,MOTIVO_ESTADO=NULL,
 FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s""",
            (id_archivo,))

    def marcar_rechazado(self, id_archivo, nombre_archivo, motivo):
        """Carga rechazada antes de aceptarse (nombre/fecha no coincide con lo
        esperado) - se guarda el nombre intentado y el motivo para que quede
        visible en la tabla (ver /archivos/{id}/errores), no solo en el modal
        que se muestra en el momento del rechazo. También marca
        ESTADO_PROCESAMIENTO='Error' -no solo ESTADO_RECEPCION- para que
        _estado_jornada() (que solo mira estadoProcesamiento) refleje el
        problema a nivel de jornada, no solo en la fila del insumo."""
        self.conn.execute("""UPDATE CON_ARCHIVO_CARGA SET NOMBRE_ARCHIVO=%s,ESTADO_RECEPCION='Rechazado',
 ESTADO_PROCESAMIENTO='Error',MOTIVO_ESTADO=%s,FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s""",
            (nombre_archivo, motivo, id_archivo))

    def marcar_recibido(self, id_archivo, nombre_archivo, correlation_id):
        # Limpia totales/motivo de un intento anterior (reintento tras error): sin
        # esto, la barra de progreso arrancaria mostrando los numeros del intento
        # viejo hasta que parseo vuelva a llamar set_total/set_progreso.
        self.conn.execute("""UPDATE CON_ARCHIVO_CARGA SET NOMBRE_ARCHIVO=%s,ESTADO_RECEPCION='Recibido',
 TOTAL_REGISTROS=NULL,REGISTROS_PROCESADOS=0,MOTIVO_ESTADO=NULL,
 CORRELATION_ID=%s,FECHA_CAMBIO_ESTADO=CURRENT_TIMESTAMP WHERE ID_ARCHIVO=%s""",
            (nombre_archivo, correlation_id, id_archivo))

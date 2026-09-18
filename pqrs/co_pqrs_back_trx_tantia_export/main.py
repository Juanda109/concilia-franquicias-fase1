#!/usr/bin/env python3
r"""
Co-PQRS Back TRX Tantia Export

CronJob de dias habiles (16:00 America/Bogota) que consolida las transacciones
con DEVOLUCION AUTOMATICA del dia (paso 2.4.0.1.20 del flujo "Transaccion no
reconocida") desde el indice durable de OpenSearch ``trx-no-reconocida-cases``
y genera el CSV para el RPA de Tantia.

Especificacion vigente (2026-08-21), reemplaza el Excel anterior:
  - Formato : CSV separado por ";" con encabezado.
  - Nombre  : ``DDMMAAAANotificaciones.csv``.
  - Ruta    : <RUTA_PROCESO>/ficheros_rpa
              dev  \\82.250.88.90\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs
              prod \\co.igrupobbva\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs
  - Corte   : 16:00, unicamente dias habiles.
  - Granularidad: UNA FILA POR TRANSACCION que llego al abono automatico. Si el
    cliente reporto 3 transacciones y las 3 llegaron, se escriben 3 filas.
  - El fichero se genera todos los dias habiles aunque no haya transacciones
    (queda con solo el encabezado): su ausencia seria ambigua para Tantia.

Congruente con el patron de co_pqrs_back_conversation_extractor:
opensearchpy (scroll) + pandas, con dedup incremental por transaccion
(client_id + statementId + movementId).
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

import pandas as pd
from dotenv import load_dotenv
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import ConnectionError as OSConnectionError
from opensearchpy.exceptions import NotFoundError as OSNotFoundError


# ============================================================================
# ORDEN EXACTO DE COLUMNAS DEL CSV DE TANTIA — NO reordenar.
#
# Especificacion 2026-08-21: REEMPLAZA el layout Excel de 21 columnas del AS400.
# Se emite UNA FILA POR TRANSACCION que llego al abono automatico (si el cliente
# reporto 3 transacciones y las 3 llegaron, salen 3 filas).
#
# Origen de cada campo:
#   - ASO detalle (operations): numero_extracto, numero_operacion, fecha_compra,
#     valor_compra, valor_intereses, codigo_autorizacion.
#   - Postgres (ada_info_detail): nombre_titular, documento_cliente,
#     tipo_producto, referencia_altamira, correo_notificacion.
#   - Flujo: fecha_recepcion, numero_producto, id_reclamo.
#   - Vacios por definicion (los llena el RPA/Tantia): id_referencia,
#     estado_abono, Habilitador, estado_notificacion, Observaciones.
# ============================================================================
TANTIA_COLUMNS: list[str] = [
    "fecha_recepcion",
    "numero_producto",
    "numero_extracto",
    "numero_operacion",
    "fecha_compra",
    "nombre_titular",
    "documento_cliente",
    "tipo_producto",
    "valor_compra",
    "valor_intereses",
    "valor_total_abonado",
    "referencia_altamira",
    "codigo_autorizacion",
    "id_reclamo",
    "id_referencia",
    "correo_notificacion",
    "estado_abono",
    "Habilitador",
    "estado_notificacion",
    "Observaciones",
    # Columna 21, agregada al FINAL a proposito: las 20 anteriores conservan su
    # posicion, asi que el RPA que lea por indice no se descoloca. Distingue de
    # que flujo viene cada fila ahora que el fichero atiende a mas de uno.
    "tipo_de_notificacion",
]

# Columnas tecnicas de deduplicacion: NO son parte del layout entregado, se
# escriben al final para que el append diario no repita una transaccion.
DEDUP_COLUMNS: list[str] = ["_dedup_key", "_conversation_id"]

# Sufijo del fichero diario: DDMMAAAA + este sufijo.
#
# Antes era "TxrNoReconocida.csv". El fichero dejo de ser exclusivo de ese flujo
# -- ahora consolida todas las notificaciones -- y el nombre lo refleja. El
# formato de la fecha no cambia: 07092026Notificaciones.csv.
CSV_SUFFIX = "Notificaciones.csv"

# Valor de `tipo_de_notificacion` cuando la ficha no lo trae. Las fichas
# escritas antes de que existiera el campo son todas de transaccion no
# reconocida, que era el unico flujo que alimentaba el indice.
DEFAULT_NOTIFICATION_TYPE = "trx_no_reconocida"

# Ceros de relleno a la izquierda que trae `personal_id` en Postgres y que el
# CSV NO debe llevar.
_DOCUMENTO_PAD = 5


# Respaldo de tipo_producto cuando Postgres no trae `product_desc`.
_TIPO_PRODUCTO = {
    "TDC": "Tarjeta de Crédito",
    "TARJETA DE CREDITO": "Tarjeta de Crédito",
    "PASIVO": "Cuenta de Ahorros",
    "CUENTA DE AHORROS": "Cuenta de Ahorros",
}


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="[%(asctime)s] %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


_BOGOTA_OFFSET = timezone(timedelta(hours=-5))


@dataclass
class Settings:
    opensearch_url: str
    opensearch_user: str
    opensearch_password: str
    opensearch_verify_certs: bool = False
    trx_cases_index: str = "trx-no-reconocida-cases"
    opensearch_batch_size: int = 500
    opensearch_scroll_keepalive: str = "2m"
    ruta_proceso: str = "/mnt/ada_data"
    # Subcarpeta acordada con Tantia dentro del recurso de red.
    tantia_folder_name: str = "ficheros_rpa"
    # CSV separado por ";" con encabezado (acuerdo 2026-08-21).
    csv_delimiter: str = ";"
    # utf-8-sig: el BOM hace que Excel/RPA en Windows respeten los acentos.
    csv_encoding: str = "utf-8-sig"
    # Festivos colombianos (YYYY-MM-DD, separados por coma): el cron solo filtra
    # lunes-viernes, los festivos se excluyen aqui.
    festivos: frozenset[str] = frozenset()
    # Hora de corte (America/Bogota). El fichero de hoy cubre desde el corte
    # del dia habil ANTERIOR hasta el corte de hoy.
    hora_corte: int = 16
    # Tope de dias habiles hacia atras al buscar el corte anterior (proteccion
    # ante un puente largo o una lista de festivos mal cargada).
    max_dias_atras: int = 10
    # Rutas de campos del detalle del ASO (operations) — CONFIGURABLES por
    # variable: lista de candidatos por comas, admite rutas anidadas con punto.
    # Asi, si el ASO real cambia un nombre, se ajusta en el configmap.
    campo_codigo_autorizacion: str = (
        "responseOperati,process.responseOperati,codigo_autorizacion,authorizationCode"
    )
    # `interest` es el nombre exacto que devuelve el ASO real.
    campo_interes: str = "interest,interes,valor_intereses"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            opensearch_url=os.getenv("OPENSEARCH_URL", "https://localhost:9200"),
            opensearch_user=os.getenv("OPENSEARCH_USER", "admin"),
            opensearch_password=os.getenv("OPENSEARCH_PASSWORD", ""),
            opensearch_verify_certs=os.getenv("OPENSEARCH_VERIFY_CERTS", "false").lower() == "true",
            trx_cases_index=os.getenv("TRX_CASES_INDEX", "trx-no-reconocida-cases"),
            opensearch_batch_size=int(os.getenv("OPENSEARCH_BATCH_SIZE", "500")),
            opensearch_scroll_keepalive=os.getenv("OPENSEARCH_SCROLL_KEEPALIVE", "2m"),
            ruta_proceso=os.getenv("RUTA_PROCESO", "/mnt/ada_data"),
            tantia_folder_name=os.getenv("TANTIA_FOLDER_NAME", "ficheros_rpa"),
            csv_delimiter=os.getenv("CSV_DELIMITER", ";"),
            csv_encoding=os.getenv("CSV_ENCODING", "utf-8-sig"),
            festivos=frozenset(
                dia.strip()
                for dia in (os.getenv("FESTIVOS", "") or "").split(",")
                if dia.strip()
            ),
            hora_corte=int(os.getenv("HORA_CORTE", "16")),
            max_dias_atras=int(os.getenv("MAX_DIAS_ATRAS", "10")),
            campo_codigo_autorizacion=os.getenv(
                # responseOperati PRIMERO: es el campo que trae el codigo segun
                # el contrato del ASO real.
                "CAMPO_CODIGO_AUTORIZACION",
                "responseOperati,process.responseOperati,codigo_autorizacion,authorizationCode",
            ),
            campo_interes=os.getenv("CAMPO_INTERES", "interest,interes,valor_intereses"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def create_opensearch_client(settings: Settings) -> OpenSearch:
    from urllib.parse import urlparse

    parsed = urlparse(settings.opensearch_url)
    use_ssl = parsed.scheme == "https"
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if use_ssl else 9200)
    return OpenSearch(
        hosts=[{"host": host, "port": port}],
        http_auth=(settings.opensearch_user, settings.opensearch_password),
        use_ssl=use_ssl,
        verify_certs=settings.opensearch_verify_certs,
        ssl_show_warn=False,
        connection_class=RequestsHttpConnection,
        http_compress=True,
        timeout=30,
    )


def corte_anterior(reference_date: date, settings: Settings) -> date:
    """Dia habil anterior a `reference_date` (salta fines de semana y festivos).

    El lunes devuelve el viernes, asi que el fichero del lunes cubre el viernes
    despues del corte, el sabado, el domingo y el lunes hasta el corte.
    """

    dia = reference_date - timedelta(days=1)
    for _ in range(settings.max_dias_atras):
        if es_dia_habil(dia, settings):
            return dia
        dia -= timedelta(days=1)
    # Sin dia habil en el tope: se cae a 24h para no dejar la ventana abierta.
    return reference_date - timedelta(days=1)


def ventana_de_corte(reference_date: date, settings: Settings) -> tuple[str, str]:
    """Rango UTC entre el corte anterior y el corte de hoy.

    Ejemplo con corte a las 16:00:
      martes  -> [lunes 16:00, martes 16:00)
      lunes   -> [viernes 16:00, lunes 16:00)   <- cubre el fin de semana

    Lo posterior al corte de hoy NO entra: sale en el fichero del proximo dia
    habil. Asi cada transaccion se entrega exactamente una vez.
    """

    desde = corte_anterior(reference_date, settings)
    inicio = datetime(
        desde.year, desde.month, desde.day, settings.hora_corte, 0, 0, tzinfo=_BOGOTA_OFFSET
    )
    fin = datetime(
        reference_date.year, reference_date.month, reference_date.day,
        settings.hora_corte, 0, 0, tzinfo=_BOGOTA_OFFSET,
    )
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (
        inicio.astimezone(timezone.utc).strftime(fmt),
        fin.astimezone(timezone.utc).strftime(fmt),
    )


def build_window_query(gte: str, lt: str) -> dict:
    """Casos actualizados dentro de la ventana de corte."""

    return {"bool": {"filter": [{"range": {"updated_at": {"gte": gte, "lt": lt}}}]}}


def scroll_hits(client: OpenSearch, settings: Settings, query: dict) -> Iterator[dict[str, Any]]:
    response = client.search(
        index=settings.trx_cases_index,
        body={"query": query, "sort": ["_doc"]},
        size=settings.opensearch_batch_size,
        scroll=settings.opensearch_scroll_keepalive,
    )
    scroll_id = response.get("_scroll_id")
    try:
        while True:
            hits = response.get("hits", {}).get("hits", [])
            if not hits:
                break
            yield from hits
            if not scroll_id:
                break
            response = client.scroll(scroll_id=scroll_id, scroll=settings.opensearch_scroll_keepalive)
            scroll_id = response.get("_scroll_id", scroll_id)
    finally:
        if scroll_id:
            try:
                client.clear_scroll(scroll_id=scroll_id)
            except Exception:
                pass


def is_devolucion_case(source: dict[str, Any]) -> bool:
    """El caso aplica al CSV si termino en devolucion automatica (completed_report)."""
    outcome = str(source.get("outcome") or "").strip().lower()
    milestones = source.get("milestones") or []
    return outcome == "devolucion" and "completed_report" in milestones


def _dget(detalle: dict, *keys: str) -> str:
    """Primer candidato no vacio del detalle del ASO.

    Cada candidato puede ser una clave simple (``interest``) o una RUTA ANIDADA
    con puntos (``amountOperation.amount``, ``process.responseOperati``). Antes
    solo soportaba claves simples y una llamada como
    ``_dget(detalle, "amountOperation", "amount")`` devolvia el diccionario
    completo convertido a texto, que luego no se podia interpretar como importe.
    Las rutas con punto tambien sirven en las variables configurables.
    """

    for key in keys:
        val: Any = detalle
        for parte in str(key).split("."):
            if not isinstance(val, dict):
                val = None
                break
            val = val.get(parte)
        if val not in (None, "") and not isinstance(val, (dict, list)):
            return str(val)
    return ""


def _split(csv: str) -> list[str]:
    """Convierte 'a,b,c' (variable configurable) en ['a','b','c']."""
    return [p.strip() for p in str(csv or "").split(",") if p.strip()]


def _solo_fecha(valor: Any) -> str:
    """Normaliza una fecha a DD/MM/AAAA.

    Acepta ``2026-08-06`` (ASO/`dateOper`), ``2026-08-06T14:00:00Z`` (timestamps
    del indice) y ya-formateadas ``06/08/2026``. Si no reconoce el formato
    devuelve el valor tal cual: es mejor que Tantia vea el dato crudo que un
    vacio silencioso.
    """

    texto = str(valor or "").strip()
    if not texto:
        return ""
    base = texto.replace("T", " ").split(" ")[0]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(base, formato).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return texto


def _documento_sin_ceros(personal_id: Any) -> str:
    """Documento del titular sin los ceros de relleno a la izquierda.

    Postgres guarda `personal_id` con 5 ceros de relleno. Se quitan solo esos:
    si el documento trajera menos ceros, se limpian los que haya, y nunca se
    devuelve vacio para un documento que era todo ceros.
    """

    texto = str(personal_id or "").strip()
    if not texto:
        return ""
    sin_ceros = texto[_DOCUMENTO_PAD:] if texto[:_DOCUMENTO_PAD] == "0" * _DOCUMENTO_PAD else texto.lstrip("0")
    return sin_ceros or texto


def _a_numero(valor: Any) -> float:
    """Convierte importes del ASO a numero (llegan como int, float o texto)."""

    if valor is None or valor == "":
        return 0.0
    try:
        return float(str(valor).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _formato_importe(valor: float) -> str:
    """Importe sin separador de miles. Entero cuando no tiene decimales.

    Se evita la notacion con coma porque el CSV va separado por ``;`` y un
    importe con coma decimal es ambiguo para el RPA.
    """

    if float(valor).is_integer():
        return str(int(valor))
    return f"{valor:.2f}"


def _numero_producto(tantia: dict[str, Any], item: dict[str, Any]) -> str:
    """Numero de producto segun el origen.

    TDC  -> tarjeta de 16 digitos obtenida del Financial (`trx_card_id`).
    PASIVO -> `contract_id` de la cuenta.
    """

    origin = str(item.get("origin_flag") or tantia.get("origin_flag") or "").strip().upper()
    tarjeta = str(item.get("numero_tarjeta") or tantia.get("numero_tarjeta") or "").strip()
    contrato = str(item.get("contrato") or tantia.get("contrato") or "").strip()
    if origin == "TDC":
        return tarjeta or contrato
    return contrato or tarjeta


def _tipo_producto(tantia: dict[str, Any], item: dict[str, Any]) -> str:
    """Descripcion del producto (`product_desc` de Postgres).

    Si Postgres no la trajo, se deriva del origen para no entregarle a Tantia
    una celda vacia (que no distingue "no hay dato" de "no aplica").
    """

    desc = str(item.get("tipo_producto") or tantia.get("tipo_producto") or "").strip()
    if desc:
        return desc
    origin = str(item.get("origin_flag") or tantia.get("origin_flag") or "").strip().upper()
    return _TIPO_PRODUCTO.get(origin, "")


def _client_id_sin_prefijo(source: dict[str, Any]) -> str:
    """Numero de cliente PELADO, sin el prefijo del tipo de notificacion.

    El id del documento en OpenSearch lleva el tipo delante
    (``doble_cobro_13083558``) para que dos flujos no se pisen la ficha del
    mismo cliente. Ese prefijo es INTERNO del indice: a Tantia va solo el
    numero.

    En la practica el campo ``client_id`` ya viene pelado y se usa tal cual; el
    despojo solo actua sobre el respaldo por ``_id``, que unicamente entra en
    juego con fichas sin ese campo.
    """

    cid = str(source.get("client_id") or "").strip()
    if cid:
        return cid

    doc_id = str(source.get("_id") or "").strip()
    tipo = str(source.get("tipo_de_notificacion") or "").strip()
    prefijo = f"{tipo}_"
    if tipo and doc_id.startswith(prefijo):
        return doc_id[len(prefijo):]
    return doc_id


def build_tantia_rows(source: dict[str, Any], settings: Settings) -> list[dict[str, Any]]:
    """Construye UNA FILA POR TRANSACCION reportada del caso.

    El agente acumula cada transaccion que llego al abono automatico en
    ``trx_case_state_snapshot.tantia_items``. Si ese acumulado no existe (casos
    anteriores al cambio), se cae a ``tantia``, que guarda la ultima
    transaccion, para no perder el caso.
    """

    snapshot = source.get("trx_case_state_snapshot") or {}
    tantia = snapshot.get("tantia") or {}
    items = snapshot.get("tantia_items")
    if not isinstance(items, list) or not items:
        items = [tantia] if tantia else []

    conversation_id = str(source.get("conversation_id") or "")
    client_id = _client_id_sin_prefijo(source)
    tipo_de_notificacion = (
        str(source.get("tipo_de_notificacion") or "").strip()
        or DEFAULT_NOTIFICATION_TYPE
    )

    rows: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        detalle = item.get("detalle") or {}
        statement = detalle.get("statementDetail") or {}
        statement_id = str(statement.get("statementId") or "").strip()
        movement_id = str(statement.get("movementId") or "").strip()

        valor_compra = _a_numero(_dget(detalle, "amountOperation.amount", "amount"))
        valor_intereses = _a_numero(_dget(detalle, *_split(settings.campo_interes)))

        # referencia_altamira: customer_id de Postgres (codigo Altamira).
        referencia = str(item.get("customer_id") or tantia.get("customer_id") or client_id).strip()
        fecha_recepcion = _solo_fecha(
            item.get("fecha_recepcion") or tantia.get("fecha_recepcion") or source.get("updated_at")
        )

        rows.append(
            {
                "fecha_recepcion": fecha_recepcion,
                "numero_producto": _numero_producto(tantia, item),
                "numero_extracto": statement_id,
                "numero_operacion": movement_id,
                "fecha_compra": _solo_fecha(
                    _dget(detalle, "dateOper") or item.get("fecha_trx")
                ),
                "nombre_titular": str(item.get("customer_name") or tantia.get("customer_name") or "").strip(),
                "documento_cliente": _documento_sin_ceros(
                    item.get("personal_id") or tantia.get("personal_id")
                ),
                "tipo_producto": _tipo_producto(tantia, item),
                "valor_compra": _formato_importe(valor_compra),
                "valor_intereses": _formato_importe(valor_intereses),
                "valor_total_abonado": _formato_importe(valor_compra + valor_intereses),
                "referencia_altamira": referencia,
                "codigo_autorizacion": str(
                    _dget(detalle, *_split(settings.campo_codigo_autorizacion)) or ""
                ).strip(),
                # id_reclamo: codigoaltamira_fecha (customer_id + fecha de recepcion).
                "id_reclamo": f"{referencia}_{fecha_recepcion}" if referencia else "",
                "id_referencia": "",
                "correo_notificacion": str(item.get("customer_mail") or tantia.get("customer_mail") or "").strip(),
                "estado_abono": "",
                "Habilitador": "",
                "estado_notificacion": "",
                "Observaciones": "",
                "tipo_de_notificacion": tipo_de_notificacion,
                # Dedup por TRANSACCION (antes era por caso): un mismo cliente
                # puede aportar varias filas el mismo dia.
                "_dedup_key": f"{client_id}|{statement_id}|{movement_id}"
                if (statement_id or movement_id)
                else f"{client_id}|{item.get('tx_id') or ''}",
                "_conversation_id": conversation_id,
            }
        )
    return rows


def validate_output_folder(settings: Settings, logger: logging.Logger) -> Path:
    r"""Carpeta destino: <ruta_proceso>/<subcarpeta>.

    En produccion apunta al recurso de red de Tantia
    (\\co.igrupobbva\tx\RECEPCION_HOST\XC\STG\automatizacion_pqrs) y en
    desarrollo a \\82.250.88.90\tx\... El montaje lo resuelve el volumen del
    pod; aqui solo se valida y se crea la subcarpeta ficheros_rpa.
    """

    folder = Path(settings.ruta_proceso) / settings.tantia_folder_name
    folder.mkdir(parents=True, exist_ok=True)
    logger.info("Carpeta destino validada: %s", folder)
    return folder


def csv_path_for(folder: Path, target_date: date) -> Path:
    """Ruta del CSV del dia: ``DDMMAAAANotificaciones.csv``."""

    return folder / f"{target_date.strftime('%d%m%Y')}{CSV_SUFFIX}"


def load_existing_keys(csv_path: Path, settings: Settings, logger: logging.Logger) -> set[str]:
    """Claves de dedup ya presentes en el CSV del dia (por TRANSACCION)."""

    if not csv_path.exists():
        return set()
    try:
        df = pd.read_csv(
            csv_path,
            sep=settings.csv_delimiter,
            dtype=str,
            encoding=settings.csv_encoding,
            usecols=["_dedup_key"],
        )
        return set(df["_dedup_key"].dropna().astype(str).unique())
    except ValueError:
        # CSV sin la columna tecnica (creado a mano o por una version anterior).
        logger.warning("El CSV %s no tiene _dedup_key; no se puede deduplicar", csv_path)
        return set()
    except Exception as exc:
        logger.warning("No se pudo leer _dedup_key de %s: %s", csv_path, exc)
        return set()


def save_or_append_csv(
    csv_path: Path,
    rows: list[dict[str, Any]],
    settings: Settings,
    logger: logging.Logger,
) -> None:
    """Escribe o hace APPEND al CSV del dia.

    El fichero se genera TODOS los dias habiles aunque no haya transacciones: en
    ese caso queda solo con el encabezado. Tantia espera el fichero cada dia, y
    un fichero vacio es una respuesta valida ("hoy no hubo abonos"); su ausencia
    seria ambigua (¿no hubo, o fallo el proceso?).
    """

    columns = TANTIA_COLUMNS + DEDUP_COLUMNS
    existe = csv_path.exists()

    if not rows:
        # El fichero se entrega SIEMPRE, tenga datos o no: es un fichero de CORTE.
        # Tantia espera uno por cada dia habil, y un fichero con solo encabezado
        # significa "en esta ventana no hubo abonos". Su ausencia seria ambigua
        # (¿no hubo, o fallo el proceso?).
        #
        # Si ya existe porque una corrida anterior del mismo dia si tuvo datos, se
        # CONSERVA intacto: nunca se truncan filas ya entregadas.
        if existe:
            logger.info(
                "Sin transacciones nuevas; se conserva el %s ya generado", csv_path.name
            )
            return
        pd.DataFrame(columns=columns).to_csv(
            csv_path,
            sep=settings.csv_delimiter,
            index=False,
            encoding=settings.csv_encoding,
            lineterminator="\r\n",
        )
        logger.info("CSV de corte generado sin transacciones: %s", csv_path.name)
        return

    df_new = pd.DataFrame(rows).reindex(columns=columns)
    df_new.to_csv(
        csv_path,
        sep=settings.csv_delimiter,
        index=False,
        # APPEND real: sin encabezado si el fichero ya existe.
        header=not existe,
        mode="a" if existe else "w",
        encoding=settings.csv_encoding,
        lineterminator="\r\n",
    )
    logger.info(
        "CSV %s: %d transaccion(es) %s",
        csv_path.name,
        len(df_new),
        "anadida(s)" if existe else "escrita(s) con encabezado",
    )


@lru_cache(maxsize=8)
def _festivos_colombia(anio: int) -> frozenset[str]:
    """Festivos nacionales de Colombia del anio, en ISO (``YYYY-MM-DD``).

    Se calculan con la libreria ``holidays``, que ya implementa la Ley Emiliani
    (traslado al lunes siguiente) y los festivos ligados a la Pascua.

    Se prefirio la libreria a calcularlos a mano por una razon concreta: al
    escribir el algoritmo en esta misma sesion se omitio uno de los 19 festivos
    de 2026 (Nuestra Senora del Rosario de Chiquinquira, 9 de julio, trasladado
    al lunes 13). Un error asi pasa desapercibido hasta que el corte de un dia
    sale mal.

    Si la libreria no estuviera disponible en la imagen, se degrada a "sin
    festivos" y se avisa: es preferible generar un fichero de mas que romper el
    job.
    """

    try:
        import holidays
    except ImportError:  # pragma: no cover - depende del entorno
        logging.getLogger(__name__).warning(
            "La libreria 'holidays' no esta instalada: solo se excluiran fines "
            "de semana y la lista manual FESTIVOS"
        )
        return frozenset()
    return frozenset(d.isoformat() for d in holidays.country_holidays("CO", years=[anio]))


def es_dia_habil(target_date: date, settings: Settings) -> bool:
    """Dia habil = lunes a viernes, sin festivo nacional ni exclusion manual.

    Tres filtros, en orden:
      1. Fin de semana.
      2. Festivo nacional colombiano (calculado, ver ``_festivos_colombia``).
      3. Lista manual ``FESTIVOS``, para dias no laborales que NO son festivos
         nacionales (un cierre bancario, un dia civico). Complementa el calculo,
         no lo reemplaza.
    """

    if target_date.weekday() >= 5:
        return False
    iso = target_date.isoformat()
    if iso in _festivos_colombia(target_date.year):
        return False
    return iso not in settings.festivos


def main() -> int:
    load_dotenv()
    settings = Settings.from_env()
    logger = setup_logging(settings.log_level)

    logger.info("=" * 70)
    logger.info("Co-PQRS Back TRX Tantia Export (CSV por transaccion)")
    logger.info(
        "Indice durable: %s | Carpeta: %s/%s",
        settings.trx_cases_index,
        settings.ruta_proceso,
        settings.tantia_folder_name,
    )
    logger.info("=" * 70)

    try:
        reference_date = datetime.now(_BOGOTA_OFFSET).date()

        # Solo dias habiles: si el cron llegara a disparar en fin de semana o en
        # un festivo configurado, no se genera fichero.
        if not es_dia_habil(reference_date, settings):
            logger.info(
                "%s no es dia habil (fin de semana o festivo): no se genera CSV",
                reference_date.isoformat(),
            )
            return 0

        output_folder = validate_output_folder(settings, logger)
        client = create_opensearch_client(settings)
        client.info()

        total_new = 0
        total_skipped = 0

        # VENTANA DE CORTE.
        #
        # El fichero de hoy cubre desde el corte del dia habil ANTERIOR hasta el
        # corte de hoy. El lunes eso incluye el viernes despues del corte, el
        # sabado y el domingo, asi que nada se pierde y nada se entrega dos veces.
        gte, lt = ventana_de_corte(reference_date, settings)
        csv_hoy = csv_path_for(output_folder, reference_date)

        # Dedup solo contra el fichero de HOY: la ventana ya garantiza que no se
        # solapa con cortes anteriores. Protege el caso de re-ejecutar el job.
        existing_keys = load_existing_keys(csv_hoy, settings, logger)
        logger.info(
            "Ventana de corte: %s -> %s | corte anterior: %s | ya en el fichero: %d",
            gte,
            lt,
            corte_anterior(reference_date, settings).isoformat(),
            len(existing_keys),
        )

        rows: list[dict[str, Any]] = []
        try:
            for hit in scroll_hits(client, settings, build_window_query(gte, lt)):
                source = hit.get("_source", {})
                source.setdefault("_id", hit.get("_id", ""))
                if not is_devolucion_case(source):
                    continue
                # Una fila por TRANSACCION del caso, no por caso.
                for row in build_tantia_rows(source, settings):
                    dedup_key = str(row.get("_dedup_key") or "")
                    if dedup_key and dedup_key in existing_keys:
                        total_skipped += 1
                        continue
                    rows.append(row)
                    if dedup_key:
                        existing_keys.add(dedup_key)
        except OSNotFoundError:
            # El indice lo crea el AGENTE en la primera devolucion automatica.
            # Que no exista NO es un error: significa que no hay abonos. El
            # fichero de corte se entrega igual, vacio.
            logger.info(
                "El indice '%s' aun no existe (ningun caso registrado todavia)",
                settings.trx_cases_index,
            )
        except OSConnectionError as exc:
            # OJO: aqui SI hubo un fallo. No se entrega un fichero vacio, porque
            # diria "no hubo abonos" cuando en realidad no se pudo consultar.
            logger.error("Error de conexion con OpenSearch: %s", exc)
            raise

        save_or_append_csv(csv_hoy, rows, settings, logger)
        total_new += len(rows)

        logger.info("=" * 70)
        logger.info(
            "Transacciones escritas: %d | Duplicadas omitidas: %d", total_new, total_skipped
        )
        logger.info("=" * 70)
        return 0
    except Exception as exc:
        logger.error("Error fatal: %s", exc, exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

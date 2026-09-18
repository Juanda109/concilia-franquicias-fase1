"""Reglas puras del flujo TXNR sobre respuestas ASO ya parseadas (dicts).

Sin I/O ni estado global: reciben el JSON del ASO (misma forma que el simulador)
y los parámetros configurables, y devuelven decisiones. Fácilmente unit-testeable.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def _parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    return None


def recurrencia_por_subject(
    issues: list[dict[str, Any]],
    *,
    subjects_txnr: tuple[str, ...],
    now: datetime | None = None,
    months: int = 6,
    max_solicitudes: int = 3,
) -> dict[str, Any]:
    """Recurrencia por asunto: cuenta los issues TXNR dentro de la ventana.

    ``has_recurrence`` es True cuando el cliente ya alcanzo el tope de solicitudes
    permitidas en la ventana (politica IT4.6: 3 en 6 meses). Con ``max_solicitudes=1``
    se recupera el comportamiento anterior, que desviaba al primer caso previo.
    """
    reference = now or datetime.utcnow()
    threshold = reference - timedelta(days=months * 30)
    matched = 0
    recent = 0
    for issue in issues or []:
        if not isinstance(issue, dict):
            continue
        subject = str(issue.get("subject") or "").strip().casefold()
        if not any(s in subject for s in subjects_txnr):
            continue
        matched += 1
        created = _parse_iso(str(issue.get("creationDate") or ""))
        if created is not None and created >= threshold:
            recent += 1
    tope = max(1, int(max_solicitudes))
    return {
        "has_recurrence": recent >= tope,
        "matched_total": matched,
        "recent_total": recent,
        "max_solicitudes": tope,
    }


def extraer_card_id(
    fo_json: dict[str, Any],
    *,
    match_value: str,
    match_field: str = "number",
    card_number_path: str = "id",
) -> str | None:
    """Ubica la tarjeta en financial-overview y devuelve su card_id (PAN).

    Estrategia por defecto (configurable): match por `number` == últimos-4
    (`match_value`) o por `id` que termine en esos dígitos; devuelve `card_number_path`.
    """
    data = (fo_json or {}).get("data") or {}
    contracts = data.get("contracts") or []
    mv = str(match_value or "").strip()
    for contract in contracts:
        if not isinstance(contract, dict):
            continue
        if str(contract.get("productType") or "").upper() not in {"CARD", "CARDS", ""}:
            # priorizar tarjetas; si no hay productType, se evalúa igual
            if contract.get("productType"):
                continue
        field_val = str(contract.get(match_field) or "").strip()
        id_val = str(contract.get("id") or "").strip()
        if mv and (field_val == mv or (id_val and id_val.endswith(mv))):
            # Contrato localizado: ANTES de devolver el id, preferir el PAN de
            # formats[] -- en el ASO real el id es un token que operations
            # rechaza (H-1); esta era la TERCERA copia de la asuncion "el id
            # ES el PAN" (el resolvedor de PAN del agente pisaba los productos
            # correctos con el token que salia de aqui, 31/08).
            pan_fmt = _fo_pan_del_contrato(contract)
            if pan_fmt:
                return pan_fmt
            return str(contract.get(card_number_path) or id_val).strip() or None

        # ---------------------------------------------------------
        # 2. Buscar el PAN en formats[].number
        # ---------------------------------------------------------
        formats = contract.get("formats") or []

        for fmt in formats:
            if not isinstance(fmt, dict):
                continue

            number = str(
                fmt.get("number") or ""
            ).strip()

            number_type = str(
                (fmt.get("numberType") or {}).get("id") or ""
            ).strip().upper()

            if not number:
                continue

            # Si tenemos últimos 4, buscamos allí.
            if mv and number.endswith(mv):
                if not number_type or number_type == "PAN":
                    return number

        # ---------------------------------------------------------
        # 3. Como último recurso, el id del contrato si termina
        #    en los últimos 4.
        # ---------------------------------------------------------
        if mv and id_val.endswith(mv):
            return id_val

    return None


def parse_movimientos_operations(operations_json: dict[str, Any]) -> list[dict[str, Any]]:
    """Normaliza los movimientos de ``/cards/v2/operations`` para el listado.

    Sustituye a ``parse_movimientos`` (que leia ``/cards/v2/cards/{id}/transactions``,
    endpoint retirado tras devolver 500 de forma sistematica).

    Mantiene el MISMO contrato que consumia el agente -- ``id``, ``descripcion``,
    ``valor``, ``fecha``, ``status`` -- y agrega el detalle de la operacion, que
    antes exigia una segunda llamada: ``operations`` ya trae todo el dia con
    detalle, asi que el paso 2.4.0.1.9 puede mostrarlo sin consultar de nuevo.

    Tolerante con los nombres de campo: el ASO real y el simulador difieren en
    algunos, y un movimiento con un campo ausente se muestra igual en vez de
    desaparecer del listado.
    """

    result: list[dict[str, Any]] = []
    for block in (operations_json or {}).get("data") or []:
        if not isinstance(block, dict):
            continue
        for op in block.get("operations") or []:
            if not isinstance(op, dict):
                continue

            monto = op.get("amountOperation") or {}
            try:
                valor = abs(float(str(monto.get("amount")).replace(",", "")))
            except (TypeError, ValueError):
                valor = None

            # Descripcion para el CLIENTE (Fabian, 27/08): en el ASO real
            # descProvision trae un ESTADO ("ACEPTADA") y placeOperation un
            # codigo ("ASCR") -- el nombre del comercio viaja en el 5o bloque
            # de observations ("...|051 05|EDS COMBUS LLANOS |..."). Jessica
            # garantiza que el patron de bloques se mantiene, asi que el
            # comercio es la fuente PRIMARIA y la cascada vieja queda de
            # respaldo para payloads sin bloques (p. ej. fixtures antiguos).
            comercio = ""
            bloques_obs = str(op.get("observations") or "").split("|")
            if len(bloques_obs) >= 5:
                comercio = bloques_obs[4].strip()
            descripcion = (
                comercio
                or str(
                    op.get("descProvision")
                    or op.get("placeOperation")
                    or op.get("concept")
                    or ""
                ).strip()
                or "Sin descripcion"
            )

            statement = op.get("statementDetail") or {}
            result.append(
                {
                    # --- contrato que ya consumia el agente ---
                    "id": op.get("id"),
                    "descripcion": descripcion,
                    "valor": valor,
                    "fecha": str(op.get("dateOper") or op.get("operationDate") or "")[:10],
                    "status": str(
                        op.get("responseOperati")
                        or op.get("observation_desc")
                        or ""
                    ).strip(),
                    # --- detalle que ahora se muestra en 2.4.0.1.9 ---
                    "hora": str(op.get("hourOperation") or "").strip(),
                    "establecimiento": str(op.get("placeOperation") or "").strip(),
                    "moneda": str(monto.get("currency") or "").strip(),
                    "intereses": op.get("interest"),
                    "numero_extracto": str(statement.get("statementId") or "").strip(),
                    "numero_operacion": str(statement.get("movementId") or "").strip(),
                    "observaciones": str(op.get("observations") or "").strip(),
                    "fecha_reverso": str(op.get("dateReverse") or "").strip(),
                }
            )
    return result


def filtrar_por_rango(
    movimientos: list[dict[str, Any]],
    *,
    monto_min: float | None,
    monto_max: float | None,
) -> tuple[list[dict[str, Any]], int]:
    """Aplica el rango de valor elegido por el cliente en 2.4.0.1.6.

    Devuelve ``(dentro_del_rango, cuantos_quedaron_fuera)``.

    El filtro se hace AQUI y no en el ASO: ``operations`` no acepta filtros de
    importe (``transactions`` si los aceptaba). La ventaja es que el conteo de
    "fuera de rango" sale de la MISMA respuesta; antes hacia falta una segunda
    llamada al ASO para saber si el dia tenia compras que el filtro descarto.

    Ese conteo importa: quien busca su compra de 750.000 no puede recibir el
    mismo "no encontramos compras" que quien no tiene ninguna.
    """

    if monto_min is None and monto_max is None:
        return list(movimientos), 0

    dentro: list[dict[str, Any]] = []
    fuera = 0
    for mov in movimientos:
        valor = mov.get("valor")
        if valor is None:
            # Sin importe no se puede excluir con criterio: se conserva.
            dentro.append(mov)
            continue
        if monto_min is not None and valor < float(monto_min):
            fuera += 1
            continue
        if monto_max is not None and valor > float(monto_max):
            fuera += 1
            continue
        dentro.append(mov)
    return dentro, fuera


def extraer_detalle(
    operations_json: dict[str, Any],
    *,
    tx_id: str,
    tx_op_id_field: str = "id",
) -> dict[str, Any] | None:
    """Busca la operación cuyo `tx_op_id_field` == tx_id dentro de data[].operations[]."""
    target = str(tx_id or "").strip()
    for block in (operations_json or {}).get("data") or []:
        if not isinstance(block, dict):
            continue
        for op in block.get("operations") or []:
            if isinstance(op, dict) and str(op.get(tx_op_id_field) or "").strip() == target:
                return op
    return None


def clasificar_investigacion(
    detalle: dict[str, Any],
    *,
    origin_flag: str,
    eci_path: str = "eci",
    ecard_path: str = "eCard",
    response_oper_path: str = "responseOperati",
    eci_chargeback_set: frozenset[str] = frozenset({"0", "1", "2", "3", "7"}),
) -> dict[str, Any]:
    """Clasifica el desenlace de la investigación a partir del detalle de la operación."""
    detalle = detalle or {}
    eci_raw = detalle.get(eci_path)
    eci = str(eci_raw).strip() if eci_raw is not None else ""
    ecard = detalle.get(ecard_path)
    response = str(detalle.get(response_oper_path) or "").strip()
    response_cf = response.casefold()
    observations = str(detalle.get("observations") or "").strip()
    observation_desc = str(detalle.get("observation_desc") or "").strip()
    obs_prefix = observations[:2]
    eci_allowed = set(eci_chargeback_set)
    pendiente_tdc = (
        str(origin_flag or "").strip().upper() == "TDC"
        and "pendiente" in observations.casefold()
    )
    compra_presencial = False

    bloques_obs = observations.split("|")
    if len(bloques_obs) >= 4:
        # Tomamos el 4to bloque (índice 3), limpiamos espacios y sacamos los primeros 2 caracteres
        cuarto_bloque = bloques_obs[3].strip()
        dos_primeras_letras = cuarto_bloque[:2]

        if dos_primeras_letras in ("10", "01"):
            compra_presencial = True

    if compra_presencial:
        resultado = "presencial"           # 2.4.0.1.19.1
    elif (
        obs_prefix in {"01", "02", "03", "04"}
        and "aceptada" in observation_desc.casefold()
    ):
        resultado = "reversado"            # 2.4.0.1.19.2
    elif (eci == "") or (eci not in eci_allowed):
        resultado = "pqr"                  # 2.4.0.1.19.pqr
    else:
        resultado = "devolucion"           # 2.4.0.1.20

    return {
        "pendiente_tdc": pendiente_tdc,
        "eci": eci,
        "ecard": ecard,
        "reversado": resultado == "reversado",
        "response": response,
        "observations": observations,
        "observation_desc": observation_desc,
        "resultado": resultado,
    }


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"true", "1", "t", "yes", "y"}


def filtrar_productos(
    rows: list[dict[str, Any]],
    *,
    origins: frozenset[str] = frozenset({"TDC"}),
    estados_validos: frozenset[str] = frozenset({"ACTIVO"}),
    card_types: frozenset[str] = frozenset({"D", "M"}),
) -> list[dict[str, Any]]:
    """Filtra productos de `ada_info_detail` para TXNR (paso 2.4.0.1.4).

    CRITERIO DE FABIAN (diagrama, 24/08) -- los cuatro en cadena:
    ``origin_flag=TDC`` -> ``contract_status_type_desc=ACTIVO`` ->
    ``card_type`` en {D, M} -> ``card_flag`` verdadero. Sustituye al criterio
    previo (21/08) que aceptaba tambien PASIVO y VIGENTE: la Postgres real
    trae ACTIVO, y los seeds de dev se realinearon a ese valor; las filas
    PASIVO / card_type=P de los seeds quedan como casos negativos.
    Las comparaciones son en mayusculas y sin espacios ("Activo", " m " entran).

    La dirección del cliente se extrae de la primera fila que tenga alguna de las
    columnas candidatas (los nombres pueden variar seg\xfan la versión del parquet).
    """
    _ADDRESS_COLUMNS = (
        "customer_address",
        "address_description",
        "cust_address_desc",
        "street_address",
        "direccion",
    )

    def _extract_address(row: dict[str, Any]) -> str:
        for col in _ADDRESS_COLUMNS:
            val = str(row.get(col) or "").strip()
            if val:
                return val
        return ""

    # Toma la dirección de la primera fila disponible (dato por cliente, no contrato).
    customer_address = ""
    for row in rows or []:
        if isinstance(row, dict):
            customer_address = _extract_address(row)
            if customer_address:
                break

    result: list[dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        estado = str(row.get("contract_status_type_desc") or "").strip().upper()
        origin = str(row.get("origin_flag") or "").strip().upper()
        if estados_validos and estado not in {v.upper() for v in estados_validos}:
            continue
        if origins and origin not in {o.upper() for o in origins}:
            continue
        ctype = str(row.get("card_type") or "").strip().upper()
        if card_types and ctype not in {c.upper() for c in card_types}:
            continue
        if not _is_truthy(row.get("card_flag")):
            continue
        contract_id = str(row.get("contract_id") or "").strip()
        last_four = str(
            row.get("last_four_pan_id")
            or (contract_id[-4:] if len(contract_id) >= 4 else contract_id)
        ).strip()
        result.append(
            {
                "contract_id": contract_id,
                "last_four": last_four,
                "product_desc": str(row.get("product_desc") or row.get("commercial_product_desc") or "Producto").strip(),
                "origin_flag": origin,
                "card_brand": str(row.get("card_brand") or "").strip().upper(),
                "customer_address": customer_address,
                # Datos del titular que consume el CSV de Tantia (nombre_titular,
                # documento_cliente y correo_notificacion). Vienen en la misma
                # fila de ada_info_detail, asi que no hay consulta extra.
                #
                # `customer_name` se toma TAL CUAL: no se concatenan
                # first_last_name/second_last_name porque en los datos reales
                # customer_name ya puede incluir apellidos y se duplicaban
                # ("CLIENTE BLOQUEOS" + "BLOQUEOS PRUEBA").
                "customer_name": str(row.get("customer_name") or "").strip(),
                "personal_id": str(row.get("personal_id") or "").strip(),
                "customer_mail": str(
                    row.get("customer_mail") or row.get("customer_email") or ""
                ).strip(),
                "customer_id": str(row.get("customer_id") or "").strip(),
            }
        )
    return result


# --- Productos desde el financial-overview (roadmap PO, 24/08) ---------------
#
# Decision de Fabian sobre el rombo "Se validan los productos del cliente":
# se salta la Consulta ADA (Postgres) y el portafolio se valida directamente
# con el financial-overview (que ya se pide con SOLO customer.id y trae todos
# los contratos). Traduccion del criterio de filtrado al vocabulario del FO:
#
#   origin_flag=TDC                    ->  productType == "CARD"
#   contract_status_type_desc=ACTIVO   ->  status.id en {OPERATIVE, ACTIVATED, ACTIVE}
#   card_type en {D, M}                ->  subProductType.id en {DEBIT_CARD, CREDIT_CARD}
#   card_flag=true                     ->  indicador BLOCKABLE activo (si viene)
#
# Verificado contra el JSON real de Nicolas (tests/fixtures/
# financial_overview_real_nicolas.json): 8 contratos -> 2 tarjetas.

_FO_ESTADOS_VALIDOS = frozenset({"OPERATIVE", "ACTIVATED", "ACTIVE"})
_FO_SUBTIPOS_TARJETA = {
    "DEBIT_CARD": "TARJETA_DEBITO",
    "CREDIT_CARD": "TARJETA_CREDITO",
}
_FO_FRANQUICIAS = ("VISA", "MASTER")


def _fo_franquicia(nombre_producto: str) -> str:
    plano = str(nombre_producto or "").upper()
    for marca in _FO_FRANQUICIAS:
        if marca in plano:
            return marca
    return ""


# BIN -> franquicia (H1, 24/08). El nombre del producto no siempre delata la
# marca ("TARJETA AQUA"), y una marca desconocida heredaba el trato VISA en el
# agente: 180 dias, el plazo MAS LARGO por defecto -- justo la familia de
# defectos vetada (dato inventado). El primer digito del PAN es la fuente
# fiable: 4 = VISA; 5 y 2 = MASTERCARD (la serie 2 existe desde 2017). El
# nombre queda como respaldo para PANes enmascarados o ausentes.
_FO_BIN_FRANQUICIA = {"4": "VISA", "5": "MASTER", "2": "MASTER"}


def _fo_franquicia_por_bin(pan: str) -> str:
    digitos = "".join(ch for ch in str(pan or "") if ch.isdigit())
    if len(digitos) < 8:
        # un PAN real tiene >= 8 digitos; menos que eso es una mascara o un
        # identificador que no es PAN -- no se adivina la marca con el
        return ""
    return _FO_BIN_FRANQUICIA.get(digitos[0], "")


def _fo_es_bloqueable(detail: dict[str, Any]) -> bool:
    """True salvo que el indicador BLOCKABLE venga explicitamente inactivo."""
    for ind in (detail or {}).get("indicators") or []:
        if str((ind or {}).get("id") or "").strip().upper() == "BLOCKABLE":
            return bool(ind.get("isActive"))
    return True


def _es_pan(valor: Any) -> bool:
    """True si ``valor`` parece un PAN real: solo digitos, longitud 13-19.

    Descarta tokens (DEV: no son digitos), numeros enmascarados
    (``****1106``) y ultimos-4 sueltos. Es la validacion que hace robusta la
    eleccion del PAN sin importar en que campo lo ponga cada entorno.
    """

    v = str(valor or "").strip()
    return v.isdigit() and 13 <= len(v) <= 19


def _fo_pan_del_contrato(c: dict[str, Any]) -> str:
    """PAN real del contrato, tolerante a la forma de CADA entorno.

    El PAN vive en sitios distintos segun el ambiente y NO se confia
    ciegamente en ninguno: se toma el primer valor que sea un PAN de verdad
    (``_es_pan``).

    - DEV: ``contracts[].id`` es un TOKEN (no valida) y el PAN esta en
      ``formats[].number`` (valida) -> se toma formats.
    - PRD: no hay ``formats`` y ``contracts[].id`` ES el PAN (valida) -> se
      toma el id (peticion de Fabian 02/09: en PRD el id manda).

    Orden: (1) formats[].number si es PAN, (2) contracts[].id si es PAN,
    (3) ultimo recurso no-validado -- formats y luego id -- para no romper
    fixtures atipicos, trazando que se degrado.
    """

    for fmt in c.get("formats") or []:
        if not isinstance(fmt, dict):
            continue
        numero = str(fmt.get("number") or "").strip()
        tipo = str(((fmt.get("numberType") or {}).get("id")) or "").strip().upper()
        if _es_pan(numero) and (not tipo or tipo == "PAN"):
            return numero

    id_contrato = str(c.get("id") or "").strip()
    if _es_pan(id_contrato):
        return id_contrato

    # Ni formats ni id son un PAN limpio (forma atipica, no vista en DEV ni
    # PRD): ultimo recurso para no dejar el producto sin identificador. Se
    # prefiere el id (identificador del contrato) sobre un formats que aqui
    # solo puede ser un valor enmascarado o de display.
    if id_contrato:
        return id_contrato
    for fmt in c.get("formats") or []:
        if isinstance(fmt, dict):
            numero = str(fmt.get("number") or "").strip()
            if numero:
                return numero
    return ""


def paginar_movimientos(
    movimientos: list[dict[str, Any]],
    *,
    page: int = 1,
    page_size: int = 5,
) -> dict[str, Any]:
    """Rebana una lista de movimientos ya filtrada en una pagina (sabor A).

    Puro: sin I/O. El servicio hace un fetch unico (cacheado) al ASO y rebana
    aqui. Acota page a [1, total_pages]; total_pages minimo 1 aunque no haya
    movimientos. has_prev/has_next se derivan de la pagina efectiva.
    """

    size = page_size if page_size and page_size > 0 else 5
    total = len(movimientos)
    total_pages = max(1, -(-total // size))  # ceil
    try:
        pagina = int(page)
    except (TypeError, ValueError):
        pagina = 1
    if pagina < 1:
        pagina = 1
    if pagina > total_pages:
        pagina = total_pages
    inicio = (pagina - 1) * size
    tramo = movimientos[inicio:inicio + size]
    return {
        "page": pagina,
        "page_size": size,
        "total": total,
        "total_pages": total_pages,
        "has_prev": pagina > 1,
        "has_next": pagina < total_pages,
        "movimientos": tramo,
    }


def productos_desde_fo(fo: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Array de productos TXNR a partir del financial-overview completo.

    Devuelve la misma forma que ``filtrar_productos`` (la de ADA) para que el
    selector del agente no cambie: contract_id / last_four / product_desc /
    origin_flag / card_brand / customer_address; y anade los campos nuevos del
    roadmap: tipo, sub_product_type, estado, bloqueable, moneda.

    v3 (24/08): el array YA NO lleva ``customer_address`` -- el FO no trae
    direccion y el campo iba siempre vacio. El agente lo lee con .get()
    tolerante y su mensaje .17.2 degrada al copy generico; cuando exista la
    fuente real (servicio de datos de la NET del roadmap) se reintroduce.
    """

    contratos = ((fo or {}).get("data") or {}).get("contracts")
    if contratos is None:
        contratos = (fo or {}).get("contracts") or []

    result: list[dict[str, Any]] = []
    for c in contratos:
        if not isinstance(c, dict):
            continue
        if str(c.get("productType") or "").strip().upper() != "CARD":
            continue
        subtipo = str(((c.get("subProductType") or {}).get("id")) or "").strip().upper()
        tipo = _FO_SUBTIPOS_TARJETA.get(subtipo)
        if tipo is None:
            continue
        estado = str(((c.get("status") or {}).get("id")) or "").strip().upper()
        detail = c.get("detail") or {}
        estado_detalle = str(((detail.get("status") or {}).get("id")) or "").strip().upper()
        if estado not in _FO_ESTADOS_VALIDOS and estado_detalle not in _FO_ESTADOS_VALIDOS:
            continue
        if not _fo_es_bloqueable(detail):
            continue
        numero = str(c.get("number") or "").strip()
        nombre = str(((c.get("product") or {}).get("name")) or "").strip()
        pan = _fo_pan_del_contrato(c) or str(c.get("id") or "").strip()
        monedas = c.get("currencies") or []
        moneda = str((monedas[0] or {}).get("currency") or "").strip() if monedas else ""
        result.append(
            {
                # v4 (Fabian, 24/08) + fix 31/08: card_id ES el PAN -- que en
                # el ASO real NO vive en c.id (eso es un token que operations
                # rechaza, H-1) sino en formats[].number. origin_flag retirado.
                "card_id": pan,
                "last_four": numero[-4:] if len(numero) >= 4 else numero,
                "product_desc": nombre or tipo.replace("_", " ").title(),
                "card_brand": _fo_franquicia_por_bin(pan) or _fo_franquicia(nombre),
                # agreement_contract: en la practica solo lo traen las DEBITO
                # (en el JSON de Nicolas venia anonimizado como token; el API
                # real entrega un numero de 20 digitos -- se captura tal cual,
                # sin validar formato, hasta verlo con data real).
                "agreement_contract": str(detail.get("agreementContract") or "").strip(),
                "tipo": tipo,
                "sub_product_type": subtipo,
                "numero_type": str(((c.get("numberType") or {}).get("id")) or "").strip().upper(),
                "estado": estado or estado_detalle,
                "bloqueable": True,
                "moneda": moneda,
            }
        )
    return result

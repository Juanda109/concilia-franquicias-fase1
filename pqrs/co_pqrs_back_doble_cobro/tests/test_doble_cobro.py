"""Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from domain.doble_cobro.business_days import (
    business_days_between,
    holidays,
    is_business_day,
)
from domain.doble_cobro.duplicate_finder import (
    filter_by_amount,
    find_duplicate_groups,
    normalize_merchant,
)
from infrastructure.entrypoint.fastapi_app import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Días hábiles
# ---------------------------------------------------------------------------


def test_colombia_tiene_dieciocho_festivos():
    assert len(holidays(2026)) == 18


@pytest.mark.parametrize(
    "festivo",
    [
        date(2026, 1, 1),  # Año Nuevo
        date(2026, 1, 12),  # Reyes trasladado (el 6 cae martes)
        date(2026, 4, 3),  # Viernes Santo
        date(2026, 6, 8),  # Corpus Christi trasladado
        date(2026, 12, 25),  # Navidad
    ],
)
def test_festivos_no_son_habiles(festivo):
    assert not is_business_day(festivo)


def test_fin_de_semana_no_es_habil():
    assert not is_business_day(date(2026, 9, 5))  # sábado
    assert not is_business_day(date(2026, 9, 6))  # domingo
    assert is_business_day(date(2026, 9, 4))  # viernes


def test_conteo_de_habiles_salta_festivos_y_fines_de_semana():
    # Del jueves 30/07 al viernes 07/08: el 07/08 es festivo (Boyacá).
    assert business_days_between(date(2026, 7, 30), date(2026, 8, 7)) == 5


def test_fecha_futura_no_acumula_habiles():
    """Una fecha futura nunca debe aparentar haber cumplido el plazo."""

    assert business_days_between(date(2026, 9, 10), date(2026, 9, 4)) == 0



# ---------------------------------------------------------------------------
# Detección de duplicados
# ---------------------------------------------------------------------------


def _movement(movement_id, merchant, amount, hour, minute, day=20):
    return {
        "id": movement_id,
        "merchant": merchant,
        "amount": amount,
        "timestamp": datetime(2026, 8, day, hour, minute),
        "date": date(2026, 8, day).isoformat(),
    }


def test_normalize_merchant_ignora_tildes_y_puntuacion():
    assert normalize_merchant("Eds  Combús-Llanos") == normalize_merchant(
        "EDS COMBUS LLANOS"
    )


def test_filtro_por_monto_aplica_tolerancia():
    movements = [
        _movement("A", "X", 145000, 10, 0),
        _movement("B", "X", 150000, 10, 0),
    ]
    encontrados = filter_by_amount(movements, target_amount=146500, tolerance=2000)
    assert [m["id"] for m in encontrados] == ["A"]


def test_agrupa_mismo_comercio_mismo_monto_mismo_dia():
    movements = [
        _movement("A", "SUPERMERCADO LA 14", 145000, 10, 15),
        _movement("B", "Supermercado La 14", 145000, 10, 19),
    ]
    grupos = find_duplicate_groups(movements)
    assert len(grupos) == 1
    assert grupos[0]["movement_ids"] == ["A", "B"]
    assert grupos[0]["count"] == 2


def test_agrupa_aunque_pasen_horas_entre_los_cobros():
    """La hora no interviene: el comercio puede reprocesar el cobro mucho después."""

    movements = [
        _movement("A", "SUPERMERCADO LA 14", 145000, 10, 15),
        _movement("B", "SUPERMERCADO LA 14", 145000, 19, 40),
    ]
    grupos = find_duplicate_groups(movements)
    assert len(grupos) == 1
    assert grupos[0]["count"] == 2


def test_no_agrupa_fechas_distintas():
    movements = [
        _movement("A", "SUPERMERCADO LA 14", 145000, 10, 15, day=20),
        _movement("B", "SUPERMERCADO LA 14", 145000, 10, 15, day=21),
    ]
    assert find_duplicate_groups(movements) == []


def test_no_agrupa_distinto_comercio():
    movements = [
        _movement("A", "COMERCIO UNO", 145000, 10, 15),
        _movement("B", "COMERCIO DOS", 145000, 10, 17),
    ]
    assert find_duplicate_groups(movements) == []


def test_no_agrupa_montos_distintos_aunque_esten_cerca():
    """Al agrupar el monto debe ser idéntico: la tolerancia es solo de búsqueda."""

    movements = [
        _movement("A", "COMERCIO UNO", 145000, 10, 15),
        _movement("B", "COMERCIO UNO", 146000, 10, 17),
    ]
    assert find_duplicate_groups(movements) == []


def test_agrupa_sin_hora_si_hay_fecha():
    """``hourOperation`` puede faltar en el ASO real; la fecha basta."""

    movements = [
        {"id": "A", "merchant": "COMERCIO UNO", "amount": 145000,
         "timestamp": None, "date": "2026-08-20"},
        {"id": "B", "merchant": "COMERCIO UNO", "amount": 145000,
         "timestamp": None, "date": "2026-08-20"},
    ]
    grupos = find_duplicate_groups(movements)
    assert len(grupos) == 1
    assert grupos[0]["first_seen"] == ""


def test_descarta_movimientos_sin_fecha():
    movements = [
        {"id": "A", "merchant": "COMERCIO UNO", "amount": 145000,
         "timestamp": None, "date": ""},
        {"id": "B", "merchant": "COMERCIO UNO", "amount": 145000,
         "timestamp": None, "date": ""},
    ]
    assert find_duplicate_groups(movements) == []


# ---------------------------------------------------------------------------
# Contrato HTTP
# ---------------------------------------------------------------------------


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_vigencia_dentro_de_la_ventana_de_conciliacion():
    hoy = date.today().strftime("%d/%m/%Y")
    response = client.post(
        "/v0/doble-cobro/validar-vigencia",
        json={"transaction_date": hoy, "product_type": "ACCOUNT"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "settlement_pending"
    assert response.json()["data"]["settlement_days"] == 7


@pytest.mark.parametrize("product_type", ["ACCOUNT", "CARD"])
def test_vigencia_usa_siete_dias_para_todos_los_productos(product_type):
    """Cuentas y tarjetas débito comparten la misma ventana de conciliación."""

    hoy = date.today().strftime("%d/%m/%Y")
    response = client.post(
        "/v0/doble-cobro/validar-vigencia",
        json={"transaction_date": hoy, "product_type": product_type, "card_brand": "VISA"},
    )
    assert response.json()["data"]["settlement_days"] == 7


def _fecha_con_habiles(transcurridos: int) -> str:
    """Fecha pasada con exactamente ``transcurridos`` dias habiles hasta hoy."""

    hoy = date.today()
    dia = hoy
    while business_days_between(dia, hoy) < transcurridos:
        dia -= timedelta(days=1)
    return dia.strftime("%d/%m/%Y")


def _vigencia(fecha: str, product_type: str = "CARD", card_brand: str = "") -> dict:
    response = client.post(
        "/v0/doble-cobro/validar-vigencia",
        json={
            "transaction_date": fecha,
            "product_type": product_type,
            "card_brand": card_brand,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


@pytest.mark.parametrize("product_type", ["ACCOUNT", "CARD"])
def test_conciliacion_se_cumple_al_septimo_dia_habil(product_type):
    """El limite son 7 dias habiles: al sexto aun no se reclama, al septimo si.

    Cuentas de ahorro y tarjetas debito comparten la misma ventana, asi que
    el producto no cambia el resultado.
    """

    sexto = _vigencia(_fecha_con_habiles(6), product_type, "VISA")
    assert sexto["outcome"] == "settlement_pending"
    assert sexto["elapsed_business_days"] == 6

    septimo = _vigencia(_fecha_con_habiles(7), product_type, "VISA")
    assert septimo["outcome"] != "settlement_pending"
    assert septimo["elapsed_business_days"] == 7


def _hace_dias(dias: int) -> str:
    return (date.today() - timedelta(days=dias)).strftime("%d/%m/%Y")


# A 180 dias la fecha SIEMPRE sigue dentro de los 6 meses (el semestre mas
# corto del calendario son 181 dias), asi que quien decide es la franquicia.
# Por eso el limite se prueba justo ahi: VISA todavia admite y MASTER ya no.
@pytest.mark.parametrize(
    "card_brand, vigencia_esperada",
    [("VISA", 180), ("MASTER", 120), ("MASTERCARD", 120)],
)
def test_vigencia_de_franquicia_en_compras_nacionales(card_brand, vigencia_esperada):
    """VISA reclama hasta 180 dias y MASTER hasta 120, sin distinguir ambito."""

    dentro = _vigencia(_hace_dias(vigencia_esperada), "CARD", card_brand)
    assert dentro["outcome"] == "ok"

    fuera = _vigencia(_hace_dias(vigencia_esperada + 1), "CARD", card_brand)
    assert fuera["outcome"] == "franchise_expired"
    assert fuera["franchise_days"] == vigencia_esperada


@pytest.mark.parametrize("card_brand", ["AMEX", "DINERS", ""])
def test_marca_no_reconocida_recibe_el_plazo_mas_largo(card_brand):
    """AMEX, Diners o un dato incompleto reciben los 180 dias de VISA.

    Se prefiere admitir la reclamacion y que negocio la revise, antes que
    rechazarla por una marca que el ASO no supo clasificar.
    """

    assert _vigencia(_hace_dias(180), "CARD", card_brand)["outcome"] == "ok"
    fuera = _vigencia(_hace_dias(181), "CARD", card_brand)
    assert fuera["outcome"] == "franchise_expired"
    assert fuera["franchise_days"] == 180


def test_la_franquicia_no_aplica_a_las_cuentas():
    """Una cuenta no tiene marca: a los 181 dias sigue siendo reclamable."""

    data = _vigencia(_hace_dias(181), "ACCOUNT", "")
    assert data["outcome"] == "ok"
    assert "franchise_days" not in data


def test_vigencia_rechaza_mas_de_seis_meses():
    response = client.post(
        "/v0/doble-cobro/validar-vigencia",
        json={"transaction_date": "01/01/2020", "product_type": "ACCOUNT"},
    )
    assert response.json()["data"]["outcome"] == "report_window_expired"


def test_vigencia_con_fecha_ilegible():
    response = client.post(
        "/v0/doble-cobro/validar-vigencia",
        json={"transaction_date": "no es fecha", "product_type": "ACCOUNT"},
    )
    assert response.json()["status"] == "error"



# ---------------------------------------------------------------------------
# Formatos de fecha (capa C3): lo que el cliente escribe vs lo que se acepta
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    ["28/08/2026", "2026-08-28", "28-08-2026"],
)
def test_parse_date_acepta_los_formatos_del_chat(raw):
    from application.doble_cobro.analysis_service import parse_date

    assert parse_date(raw) == date(2026, 8, 28)


@pytest.mark.parametrize(
    "raw",
    [
        "ayer",                  # lenguaje natural: el canal no lo interpreta
        "28 de agosto de 2026",  # fecha escrita
        "28/08/26",              # anio de dos digitos
        "08/28/2026",            # formato gringo (mes 28 no existe)
        "",
    ],
)
def test_parse_date_rechaza_lo_demas_y_el_gate_cae_a_revision(raw):
    """Una fecha no interpretable termina en outcome=error: el agente la
    manda a revision a fondo (fail-closed), nunca la adivina."""

    from application.doble_cobro.analysis_service import parse_date

    assert parse_date(raw) is None

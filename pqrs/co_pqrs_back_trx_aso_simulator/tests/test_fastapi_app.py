from fastapi.testclient import TestClient

from infrastructure.entrypoint.fastapi_app import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_granting_ticket_returns_tsec_header() -> None:
    r = client.post("/TechArchitecture/co/grantingTicket/V02", json={})
    assert r.status_code == 200
    assert r.headers.get("tsec") == "SIMULATED-TSEC-TOKEN"


def test_salesforce_recurrence_for_client_a() -> None:
    r = client.get("/salesforce-issue-tracker/v0/issues", params={"targetUserId": "01-1013634958"})
    assert r.status_code == 200
    issues = r.json()["data"]
    # El simulador devuelve TODOS los issues del cliente; el filtro subject+<=6m
    # lo aplica el cliente ASO (F2). Debe existir al menos un subject TXNR.
    assert len(issues) == 3
    assert any("no reconoce" in i["subject"].lower() for i in issues)
    assert all(i["issuer"]["identityDocument"]["documentNumber"] == "1013634958" for i in issues)


def test_salesforce_unknown_returns_empty() -> None:
    r = client.get("/salesforce-issue-tracker/v0/issues", params={"targetUserId": "01-9999999999"})
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_financial_overview_returns_card() -> None:
    r = client.get(
        "/financial-overview/v0/financial-overview",
        params={"customer.id": "1013634960", "contracts.productType": "CARDS"},
    )
    assert r.status_code == 200
    contracts = r.json()["data"]["contracts"]
    assert contracts[0]["id"] == "4912680517940060"
    assert contracts[0]["number"] == "0060"


def test_transactions_returns_movements_and_filters_by_range() -> None:
    # sin filtros: 3 movimientos
    r = client.get("/cards/v2/cards/4912680517940060/transactions")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 3
    # filtro por rango 35000-500000 y EXPENSE: siguen los 3 (89990,120000,250000)
    r2 = client.get(
        "/cards/v2/cards/4912680517940060/transactions",
        params={
            "operationAmount.fromAmount": 35000,
            "operationAmount.toAmount": 500000,
            "moneyFlow.id": "EXPENSE",
            "operationAmount.id": "CONTRACT_AMOUNT",
        },
    )
    assert r2.status_code == 200
    assert len(r2.json()["data"]) == 3
    # rango que excluye el de 250000
    r3 = client.get(
        "/cards/v2/cards/4912680517940060/transactions",
        params={"operationAmount.fromAmount": 35000, "operationAmount.toAmount": 130000},
    )
    ids = {m["id"] for m in r3.json()["data"]}
    assert ids == {"TXC01", "TXC02"}


def test_transactions_empty_for_client_i() -> None:
    r = client.get("/cards/v2/cards/4912680517940066/transactions")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_operations_detail_match_by_id() -> None:
    r = client.get(
        "/cards/v2/operations",
        params={"operationDate": "20260806", "cardId": "4912680517940060", "pageSize": 100, "paginationKey": 1},
    )
    assert r.status_code == 200
    ops = r.json()["data"][0]["operations"]
    assert ops[0]["id"] == "TXC01"
    assert ops[0]["eci"] == "5"
    assert ops[0]["eCard"] is True


def test_activations_ok() -> None:
    """El PATCH de apagado (bloqueo temporal) no exige el reto."""

    r = client.patch("/cards/v1/cards/4912680517940060/activations", json={"root": []})
    assert r.status_code == 200


def test_operations_sin_cabeceras_exige_subir_de_nivel() -> None:
    """Paso 1 del reto: 403 con la cabecera authenticationtype."""

    r = client.post("/cards/v2/operations", json={"card": {"cardId": "4912680517940060"}})
    assert r.status_code == 403
    assert r.headers.get("authenticationtype") == "241"


def test_operations_con_datos_envia_el_push() -> None:
    """Paso 2: 401 con challenge y state en las cabeceras."""

    r = client.post(
        "/cards/v2/operations",
        json={"card": {"cardId": "4912680517940060"}},
        headers={"authenticationtype": "241",
                 "authenticationdata": "deviceId=BB-04-X,profileId=CC1,channel=12000035"},
    )
    assert r.status_code == 401
    assert r.headers.get("authenticationChallenge")
    assert r.headers.get("authenticationstate")


def test_operations_con_estado_ejecuta() -> None:
    """Paso 3: 201 SOLO con el reto aprobado (el simulador guarda estado)."""

    # Paso 2: crea el reto (queda pending).
    client.post(
        "/cards/v2/operations",
        json={"card": {"cardId": "4912680517940060"}},
        headers={"authenticationtype": "241",
                 "authenticationdata": "deviceId=BB-04-X,profileId=CC1,channel=12000035"},
    )
    # Sin aprobar, el paso 3 se niega: defensa contra bloqueos no autorizados.
    r = client.post(
        "/cards/v2/operations",
        json={"card": {"cardId": "4912680517940060"}},
        headers={"authenticationtype": "241",
                 "authenticationstate": "sim-state-0060",
                 "authenticationdata": "deviceId=BB-04-X,profileId=CC1,channel=12000035"},
    )
    assert r.status_code == 403
    # Aprobacion externa (accion del cliente en su app) y reintento: ejecuta.
    r = client.post("/security/v0/order-chanel/sim-0060-challenge/approve")
    assert r.status_code == 200
    r = client.post(
        "/cards/v2/operations",
        json={"card": {"cardId": "4912680517940060"}},
        headers={"authenticationtype": "241",
                 "authenticationstate": "sim-state-0060",
                 "authenticationdata": "deviceId=BB-04-X,profileId=CC1,channel=12000035"},
    )
    assert r.status_code == 201


def test_expire_cierra_el_reto() -> None:
    """[expire] pending -> expired; un reto terminal no se puede caducar."""

    client.post(
        "/cards/v2/operations",
        json={"card": {"cardId": "4912680517940061"}},
        headers={"authenticationtype": "241",
                 "authenticationdata": "deviceId=BB-04-X,profileId=CC1,channel=12000035"},
    )
    r = client.post("/security/v0/order-chanel/sim-0061-challenge/expire")
    assert r.status_code == 200
    r = client.get("/security/v0/order-chanel/sim-0061-challenge")
    assert r.json()["data"]["status"]["id"] == "expired"


def test_user_status_devuelve_dispositivo_activo() -> None:
    r = client.get("/security/v0/user-status", params={"profileId": "CC000001216963398"})
    assert r.status_code == 200
    dispositivos = r.json()["data"]
    assert dispositivos[0]["device"]["softToken"]["status"]["id"] == "ACTIVE"


def test_user_status_sin_dispositivo_activo() -> None:
    """Un profileId terminado en 0000 permite probar ese camino."""

    r = client.get("/security/v0/user-status", params={"profileId": "CC0000"})
    assert r.json()["data"][0]["device"]["softToken"]["status"]["id"] == "BLOCKED"


def test_order_channel_acepta() -> None:
    r = client.get("/security/v0/order-chanel/sim-0060-challenge")
    assert r.status_code == 200
    assert r.json()["data"]["status"]["id"] in {"pending", "accepted"}

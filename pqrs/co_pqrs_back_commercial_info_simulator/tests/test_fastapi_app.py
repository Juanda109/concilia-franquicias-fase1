from fastapi.testclient import TestClient

from infrastructure.entrypoint.fastapi_app import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_commercial_information_exact_match() -> None:
    response = client.get(
        "/risks/v0/commercial-information",
        params={
            "identityDocument.documentType": "01",
            "identityDocument.documentNumber": "000001069759414",
            "customer.lastName": "gutierrez",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["customer"]["identityDocument"]["documentNumber"] == "000001069759414"


def test_commercial_information_non_exact_match_returns_default() -> None:
    response = client.get(
        "/risks/v0/commercial-information",
        params={
            "identityDocument.documentType": "99",
            "identityDocument.documentNumber": "000001095724710",
            "customer.lastName": "AGUDELO",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "data": "central risk data for customer doesn't exist on local server"
    }


def test_commercial_information_matches_without_last_name() -> None:
    response = client.get(
        "/risks/v0/commercial-information",
        params={
            "identityDocument.documentType": "01",
            "identityDocument.documentNumber": "000001095724710",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["customer"]["identityDocument"]["documentNumber"] == "000001095724710"


def test_commercial_information_default_fallback() -> None:
    response = client.get(
        "/risks/v0/commercial-information",
        params={
            "identityDocument.documentType": "01",
            "identityDocument.documentNumber": "111111111111111",
            "customer.lastName": "desconocido",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "data": "central risk data for customer doesn't exist on local server"
    }


def test_commercial_information_requires_expected_query_params() -> None:
    response = client.get("/risks/v0/commercial-information")
    assert response.status_code == 422

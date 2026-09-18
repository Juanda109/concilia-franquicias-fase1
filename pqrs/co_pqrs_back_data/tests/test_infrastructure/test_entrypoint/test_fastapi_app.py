import unittest

from fastapi.testclient import TestClient

from infrastructure.entrypoint.api.dependencies import get_opensearch_client
from infrastructure.entrypoint.fastapi_app import app


class FakeOpenSearchClient:
    async def update_client_control_data(
        self,
        *,
        customer_id: str,
        workflow: str,
        data: dict,
    ) -> None:
        return None


class FastApiAppTests(unittest.TestCase):
    def setUp(self) -> None:
        app.dependency_overrides[get_opensearch_client] = lambda: FakeOpenSearchClient()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health_check_returns_ok(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_consultar_accepts_request_for_background_processing(self) -> None:
        response = self.client.post(
            "/consultar",
            params={"customer_id": "56780000", "workflow": "cuenta_embargada"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "processing"})

    def test_consultar_accepts_request_even_when_background_customer_does_not_exist(
        self,
    ) -> None:
        response = self.client.post(
            "/consultar",
            params={"customer_id": "no-existe", "workflow": "cuenta_embargada"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "processing"})

    def test_centrales_no_autorizo_accepts_request_for_background_processing(
        self,
    ) -> None:
        response = self.client.post(
            "/centrales_no_autorizo",
            params={"customer_id": "56780000", "workflow": "cuenta_embargada"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "processing"})

    def test_notificacion_centrales_accepts_request_for_background_processing(
        self,
    ) -> None:
        response = self.client.post(
            "/notificacion_centrales",
            params={"customer_id": "56780000", "workflow": "cuenta_embargada"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "processing"})

    def test_request_validation_returns_406(self) -> None:
        response = self.client.post("/consultar")

        self.assertEqual(response.status_code, 406)
        self.assertIn("detail", response.json())

    def test_openapi_documents_406_instead_of_422(self) -> None:
        schema = app.openapi()
        responses = schema["paths"]["/consultar"]["post"]["responses"]

        self.assertIn("406", responses)
        self.assertNotIn("422", responses)


if __name__ == "__main__":
    unittest.main()

import sys
import types
import unittest

from fastapi.testclient import TestClient

fake_strands_module = types.ModuleType("strands")


class _FakeAgent:
    def __init__(self, *args, **kwargs) -> None:
        pass


fake_strands_module.Agent = _FakeAgent
sys.modules.setdefault("strands", fake_strands_module)

from infrastructure.entrypoint.fastapi_app import app


class FastApiValidationResponseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_start_now_requires_user_id(self) -> None:
        response = self.client.post(
            "/start",
            json={"conversation_id": "03966512_20260506"},
        )

        self.assertEqual(response.status_code, 406)
        self.assertIn("detail", response.json())

    def test_request_validation_returns_406(self) -> None:
        response = self.client.post(
            "/chat",
            json={"conversation_id": "03966512_20260506"},
        )

        self.assertEqual(response.status_code, 406)
        self.assertIn("detail", response.json())

    def test_openapi_documents_406_instead_of_422(self) -> None:
        schema = app.openapi()
        responses = schema["paths"]["/chat"]["post"]["responses"]

        self.assertIn("406", responses)
        self.assertNotIn("422", responses)

    def test_openapi_documents_message_shape_for_start_and_chat(self) -> None:
        schema = app.openapi()
        start_response = schema["components"]["schemas"]["StartResponse"]
        chat_response = schema["components"]["schemas"]["ChatResponse"]
        start_message = schema["components"]["schemas"]["StartMessageEnvelope"]
        chat_message = schema["components"]["schemas"]["ChatMessageEnvelope"]
        start_content = schema["components"]["schemas"]["StartMessageContent"]
        chat_content = schema["components"]["schemas"]["ChatMessageContent"]

        self.assertIn("status", start_response["properties"])
        self.assertIn("status", chat_response["properties"])
        self.assertEqual(
            start_response["properties"]["message"]["$ref"],
            "#/components/schemas/StartMessageEnvelope",
        )
        self.assertEqual(
            chat_response["properties"]["message"]["$ref"],
            "#/components/schemas/ChatMessageEnvelope",
        )
        self.assertIn("input_type", start_message["properties"])
        self.assertIn("input_type", chat_message["properties"])
        self.assertIn("label", start_content["properties"])
        # /start es idempotente y REANUDA: al volver a una sesion parada en un
        # paso de opciones tiene que devolverlas, o el cliente ve la pregunta
        # sin botones. En el saludo inicial la lista va vacia.
        self.assertIn("options", start_content["properties"])
        self.assertIn("label", chat_content["properties"])
        self.assertIn("options", chat_content["properties"])

    def test_openapi_documents_polling_and_input_type_enum_without_confirm(self) -> None:
        schema = app.openapi()

        self.assertIn("/polling", schema["paths"])
        self.assertIn("/polling/{conversation_id}", schema["paths"])
        self.assertNotIn(
            "confirm",
            schema["components"]["schemas"]["ChatMessageEnvelope"]["properties"][
                "input_type"
            ]["enum"],
        )
        self.assertNotIn(
            "confirm",
            schema["components"]["schemas"]["StartMessageEnvelope"]["properties"][
                "input_type"
            ]["enum"],
        )


if __name__ == "__main__":
    unittest.main()


class StartResumeKeepsOptionsTests(unittest.TestCase):
    """POST /start sobre una sesion en curso devuelve los botones del paso.

    Sin esto, recargar el front (o pulsar 'Iniciar conversacion') en un paso de
    opciones dejaba al cliente viendo la pregunta sin nada que pulsar: el
    sintoma reportado en el paso del Formulario PQR.
    """

    def test_start_envelope_admite_opciones(self) -> None:
        from infrastructure.entrypoint.api.router.v0.model.chat_models import (
            ChatMessageOption,
            StartMessageContent,
        )

        contenido = StartMessageContent(
            label="Completa el formulario a continuacion.",
            options=[ChatMessageOption(key="pqr", label="Formulario PQR")],
        )
        self.assertEqual(len(contenido.options), 1)
        self.assertEqual(contenido.options[0].key, "pqr")

    def test_saludo_inicial_sigue_sin_opciones(self) -> None:
        from infrastructure.entrypoint.api.router.v0.model.chat_models import (
            StartMessageContent,
        )

        self.assertEqual(StartMessageContent(label="Hola").options, [])

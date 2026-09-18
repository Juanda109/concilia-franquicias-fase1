"""Tests de la FASE 2 del flujo 3 (notificación): análisis del producto elegido.

Reglas: adelanto de nómina → 17 (aunque haya extracto); sin extracto → 17;
con extracto → 16 (fecha DD/MM/AAAA + correo anon) + envío del correo con PDF.
"""

import unittest
from unittest.mock import patch

import pandas as pd

from application.customer import consultar_service
from application.customer.consultar_service import build_notificacion_producto_data


class _FakeClientSinExtracto:
    def request_aso(self, path, accept="application/json"):
        return {"data": []}


class _FakeClientConExtracto:
    def request_aso(self, path, accept="application/json"):
        if path.rstrip("/").endswith("financial-statements"):
            return {"data": [{"id": "EXT1", "cutOffDate": "2026-04-01"}]}

    def request_aso_pdf(self, path):
        return b"%PDF-1.4 fake-pdf-bytes"


def _df(**overrides):
    row = {
        "customer_id": "999",
        "key_id": "123",
        "contract_id": "00130009000100000019",
        "commercial_product_desc": "TARJETA",
        "customer_name": "PABLO",
        "customer_mail": "pablo@correo.com",
        "adelanto_nomina_flag": "false",
    }
    row.update(overrides)
    return pd.DataFrame([row])


class NotificacionProductoTests(unittest.TestCase):
    def test_adelanto_nomina_va_a_pqrs_17_aunque_haya_extracto(self) -> None:
        data = build_notificacion_producto_data(
            customer_identity_df=_df(adelanto_nomina_flag="true"),
            key_id="123",
            commercial_info_client=_FakeClientConExtracto(),
        )
        self.assertEqual(data["id_msg"], 17)
        self.assertEqual(data["caso"], "adelanto de nomina")

    def test_sin_extracto_va_a_pqrs_17(self) -> None:
        data = build_notificacion_producto_data(
            customer_identity_df=_df(),
            key_id="123",
            commercial_info_client=_FakeClientSinExtracto(),
        )
        self.assertEqual(data["id_msg"], 17)

    def test_con_extracto_msg16_fecha_correo_y_envia_correo(self) -> None:
        with patch.object(
            consultar_service, "enviar_correo_extracto", return_value=True
        ) as mock_mail:
            data = build_notificacion_producto_data(
                customer_identity_df=_df(),
                key_id="123",
                commercial_info_client=_FakeClientConExtracto(),
            )
        self.assertEqual(data["id_msg"], 16)
        self.assertEqual(data["fecha"], "01/04/2026")
        self.assertEqual(data["correo"], "pab****@correo.com")
        mock_mail.assert_called_once()
        kwargs = mock_mail.call_args.kwargs
        self.assertEqual(kwargs["correo"], "pablo@correo.com")  # correo REAL, no anon
        self.assertTrue(kwargs["adjunto_base64"])  # PDF adjunto presente

    def test_producto_no_encontrado_va_a_17(self) -> None:
        data = build_notificacion_producto_data(
            customer_identity_df=_df(),
            key_id="999999",
            commercial_info_client=_FakeClientSinExtracto(),
        )
        self.assertEqual(data["id_msg"], 17)

    def test_obtener_pdf_extracto_usa_paths_configurables(self) -> None:
        # Verifica que los paths de extracto salen de settings (configmap), no quemados.
        from application.customer.consultar_service import obtener_pdf_extracto

        class _Settings:
            extracto_prestamos_listado = "/custom/{contract_id}/fs"
            extracto_prestamos_pdf = "/custom/{contract_id}/fs/{id_extracto}"

        class _Client:
            def __init__(self) -> None:
                self.settings = _Settings()
                self.paths: list[str] = []

            def request_aso(self, path, accept="application/json"):
                self.paths.append(path)
                if path.endswith("/fs"):
                    return {"data": [{"id": "E1", "cutOffDate": "2026-04-01"}]}

            def request_aso_pdf(self, path):
                self.paths.append(path)
                return b"%PDF-1.4"

        client = _Client()
        pdf, fecha = obtener_pdf_extracto("ABC", client)
        self.assertEqual(fecha, "2026-04-01")
        self.assertIn("/custom/ABC/fs", client.paths)
        self.assertIn("/custom/ABC/fs/E1", client.paths)


if __name__ == "__main__":
    unittest.main()

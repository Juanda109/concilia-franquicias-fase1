import unittest
from unittest.mock import patch

import pandas as pd
from pandas import DataFrame

from application.customer.consultar_service import (
    _normalize_key_id,
    build_notificacion_centrales_data,
    build_notificacion_producto_data,
    build_centrales_no_autorizo_data,
    build_consultar_data,
    build_data_from_customer_df_and_centrales,
    consultar_customer,
    notificacion_centrales_customer,
    read_json_centrales,
)
from domain.customer.models import CustomerIdentity
from infrastructure.entrypoint.api.errors.exceptions import CustomerNotFoundError


class StubIdentityRepository:
    def __init__(self) -> None:
        self.identity = CustomerIdentity(
            customer_id="56780000",
            personal_id="000001069759414",
            personal_type="01",
            customer_name="PABLO EDUARDO MOSQUERA GUTIERREZ",
        )

    def read_customer_identity_df(self, customer_id: str | None = None) -> DataFrame:
        customer_identity_df = pd.DataFrame(
            [
                {
                    "customer_id": self.identity.customer_id,
                    "personal_id": self.identity.personal_id,
                    "personal_type": self.identity.personal_type,
                    "adelanto_nomina_flag": "false",
                    "key_id": "123",
                }
            ]
        )

        if customer_id is None or customer_id == self.identity.customer_id:
            return customer_identity_df

        return customer_identity_df.iloc[0:0]

    def find_by_customer_id_in_df(
        self,
        *,
        customer_id: str,
        customer_identity_df: DataFrame,
    ) -> CustomerIdentity | None:
        if not customer_identity_df.empty and customer_id == self.identity.customer_id:
            return self.identity

        return None


class StubCommercialInfoClient:
    def get_commercial_info(self, identity: CustomerIdentity) -> dict:
        return {
            "data": {
                "customer": {
                    "fullname": "PABLO EDUARDO MOSQUERA GUTIERREZ",
                    "identityDocument": {
                        "documentNumber": identity.personal_id,
                        "documentType": {"description": identity.personal_type},
                    },
                },
                "history": {
                    "score": [
                        {
                            "creditScore": 473,
                        }
                    ],
                    "obligations": [
                        {
                            "number": "123",
                            "financialInstitutionInformation": {
                                "name": "BBVA COLOMBIA",
                            },
                            "classificationStatus": {"id": "MORA"},
                            "behaviorLiabilities": [],
                        }
                    ],
                },
                "thirdPartyResponse": {
                    "id": "02",
                    "name": "CONSULTA EXITOSA",
                },
            }
        }

class StubEmbargoRepository:
    def __init__(
        self,
        records: list[dict[str, str]] | None = None,
        fail: bool = False,
    ) -> None:
        self.records = records or []
        self.fail = fail
        self.calls = 0

    def read_embargo_join_by_contract_id(
        self,
        *,
        contract_id: str,
    ) -> list[dict[str, str]]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("embargo read failed")
        return list(self.records)

class ConsultarServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalize_key_id_casts_to_string_and_trims_outer_zeroes(
        self,
    ) -> None:
        self.assertEqual(_normalize_key_id("011800"), "118")
        self.assertEqual(_normalize_key_id(118), "118")
        self.assertEqual(_normalize_key_id(0), "0")
        self.assertEqual(_normalize_key_id("0000"), "0")
        self.assertEqual(_normalize_key_id("4350-CAB-000100200"), "4350-CAB-000100200")

    async def test_consultar_customer_returns_selected_data_from_commercial_info(
        self,
    ) -> None:
        data = await consultar_customer(
            customer_id=" 56780000 ",
            identity_repository=StubIdentityRepository(),
            commercial_info_client=StubCommercialInfoClient(),
        )

        self.assertEqual(data["fullname"], "PABLO EDUARDO MOSQUERA GUTIERREZ")
        self.assertEqual(data["document_number"], "000001069759414")
        self.assertEqual(data["document_type"], "01")
        self.assertEqual(data["credit_score"], 473)

    async def test_consultar_customer_raises_when_customer_id_does_not_exist(self) -> None:
        with self.assertRaises(CustomerNotFoundError):
            await consultar_customer(
                customer_id="no-existe",
                identity_repository=StubIdentityRepository(),
                commercial_info_client=StubCommercialInfoClient(),
            )

    async def test_consultar_customer_propagates_when_dem_repository_fails(self) -> None:
        embargo_repo = StubEmbargoRepository(fail=True)
        identity_repository = StubIdentityRepository()
        customer_identity_df = identity_repository.read_customer_identity_df()
        customer_identity_df.loc[0, "origin_flag"] = "PASIVE"
        customer_identity_df.loc[0, "contract_id"] = "00131234567890"
        identity_repository.read_customer_identity_df = lambda customer_id=None: customer_identity_df
        with self.assertRaisesRegex(RuntimeError, "embargo read failed"):
            await consultar_customer(
                customer_id="56780000",
                identity_repository=identity_repository,
                commercial_info_client=StubCommercialInfoClient(),
                embargo_repository=embargo_repo,
            )
        self.assertEqual(embargo_repo.calls, 1)

    async def test_notificacion_centrales_returns_validaciones_por_producto(self) -> None:
        # FASE 1 del flujo 3: /notificacion_centrales ahora devuelve validaciones
        # por producto (mismo formato que /consultar) para poder listar.
        data = await notificacion_centrales_customer(
            customer_id="56780000",
            identity_repository=StubIdentityRepository(),
            commercial_info_client=StubCommercialInfoClient(),
        )

        self.assertIn("validaciones", data)
        self.assertIsInstance(data["validaciones"], list)
        self.assertTrue(
            any(v.get("key_id") == "123" for v in data["validaciones"])
        )

    async def test_build_notificacion_centrales_data_is_the_business_editing_point(
        self,
    ) -> None:
        centrales_data = {"123": {"activo_mora": "mora"}}
        customer_identity_df = pd.DataFrame(
            [
                {
                    "customer_id": "56780000",
                    "key_id": "123",
                    "commercial_product_desc": "TARJETA",
                    "adelanto_nomina_flag": "false",
                }
            ]
        )

        data = build_notificacion_centrales_data(
            centrales_data=centrales_data,
            customer_identity_df=customer_identity_df,
        )

        self.assertEqual(
            data,
            {
                "caso": "no extracto",
                "id_msg": 17,
            },
        )

    async def test_build_notificacion_producto_data_matches_key_id_with_outer_zeroes(
        self,
    ) -> None:
        customer_identity_df = pd.DataFrame(
            [
                {
                    "key_id": "011800",
                    "adelanto_nomina_flag": "false",
                    "contract_id": "contract-1",
                }
            ]
        )

        with patch(
            "application.customer.consultar_service.obtener_pdf_extracto",
            return_value=(None, None),
        ):
            data = build_notificacion_producto_data(
                customer_identity_df=customer_identity_df,
                key_id=118,
            )

        self.assertEqual(data, {"caso": "no extracto", "id_msg": 17})

    async def test_build_data_from_customer_df_and_centrales_is_the_editing_point(
        self,
    ) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "personal_id": "000001069759414",
                        "personal_type": "01",
                        "key_id": "123",
                        "commercial_product_desc": "CUENTA DE AHORROS",
                        "default_flag": "t",
                        "default_days_number": "2",
                    },
                    {
                        "customer_id": "otro-cliente",
                        "personal_id": "999",
                        "personal_type": "01",
                        "key_id": "999",
                        "default_flag": "t",
                    }
                ]
            ),
            centrales_data={123: [{"activo_mora": 2}]},
            customer_id="56780000",
        )

        self.assertEqual(len(data["validaciones"]), 1)
        self.assertEqual(data["validaciones"][0]["key_id"], "123")
        self.assertEqual(
            data["validaciones"][0]["commercial_product_desc"],
            "CUENTA DE AHORROS",
        )
        self.assertEqual(
            data["validaciones"][0]["hallazgos"],
            [
                {
                    "tipo": "activo_mora",
                    "id_msg": 4,
                    "valor": {
                        "tipo_producto": "",
                        "motivo_reporte": "mora en tu obligación",
                        "dias_mora": "2",
                    },
                }
            ],
        )

    async def test_build_data_from_customer_df_and_centrales_matches_key_id_with_outer_zeroes(
        self,
    ) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "011800",
                        "commercial_product_desc": "CUENTA DE AHORROS",
                    }
                ]
            ),
            centrales_data={118: {"activo_mora": 2}},
            customer_id="56780000",
        )

        self.assertEqual(len(data["validaciones"]), 1)
        self.assertEqual(data["validaciones"][0]["key_id"], "011800")
        self.assertEqual(data["validaciones"][0]["hallazgos"][0]["tipo"], "activo_mora")

    async def test_build_data_from_customer_df_and_centrales_uses_vector_for_gt_120(
        self,
    ) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "personal_id": "000001069759414",
                        "personal_type": "01",
                        "key_id": "123",
                        "default_flag": "t",
                        "default_days_number": "60",
                        "commercial_product_desc": "CARTERA BANCARIA",
                    }
                ]
            ),
            centrales_data={
                123: {
                    "activo_mora": {
                        "behavior_vector": [
                            "-", "-", "-", "-", "-", "-", "-", "-",
                            "-", "-", "-", "-", "-", "-", "-", "N",
                            "N", "N", "1", "2", "3", "4", "5", "6",
                        ],
                        "mora_months": 6,
                        "dias_mora": 180,
                        "max_level": 6,
                    }
                }
            },
            customer_id="56780000",
        )

        self.assertEqual(data["validaciones"][0]["hallazgos"][0]["id_msg"], 20)
        self.assertEqual(
            data["validaciones"][0]["hallazgos"][0]["valor"]["mora_months"],
            6,
        )
        self.assertEqual(
            data["validaciones"][0]["hallazgos"][0]["valor"]["behavior_vector"][-1],
            "6",
        )

    async def test_embargo_in_bbva_and_centrales_returns_only_id_msg_12(self) -> None:
        """DEM A y centrales activas producen id_msg=12, sin blocking_type."""

        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "123",
                        "origin_flag": "PASIVE",
                        "blocking_type": "0",
                        "contract_id": "00131234567890",
                    }
                ]
            ),
            centrales_data={123: {"pasivo": "embargado"}},
            customer_id="56780000",
            embargo_repository=StubEmbargoRepository(
                [
                    {
                        "emb_juzgado": "JUZGADO 5 CIVIL",
                        "emb_imp_total": "2500000",
                        "emb_nro_ofic": "OF-2026-001",
                        "emb_fecha_ofic": "2026-02-20",
                        "dem_estado": "A",
                    },
                    {
                        "emb_juzgado": "JUZGADO 9 CIVIL",
                        "emb_imp_total": "1000000",
                        "emb_nro_ofic": "OF-2025-001",
                        "emb_fecha_ofic": "2025-02-20",
                        "dem_estado": "D",
                    }
                ]
            ),
        )

        hallazgos = data["validaciones"][0]["hallazgos"]
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["id_msg"], 12)
        self.assertEqual(hallazgos[0]["tipo"], "embargada")
        self.assertEqual(hallazgos[0]["valor"][0]["nombre_entidad"], "JUZGADO 5 CIVIL")
        self.assertEqual(hallazgos[0]["valor"][0]["numero_oficio"], "OF-2026-001")
        self.assertEqual(hallazgos[0]["valor"][0]["fecha_oficio"], "2026-02-20")
        self.assertEqual(hallazgos[0]["valor"][0]["valor_pago"], "2500000")
        self.assertEqual(len(hallazgos[0]["valor"]), 1)
        # El bug original tambien agregaba un hallazgo espurio id_msg=9 "sin embargo".
        self.assertNotIn(9, [hallazgo["id_msg"] for hallazgo in hallazgos])

    async def test_centrales_acemb_and_inemb_are_normalized_as_embargo(self) -> None:
        for central_status in ("ACEMB", "INEMB"):
            with self.subTest(central_status=central_status):
                centrales_data = read_json_centrales(
                    {
                        "data": {
                            "creditHistory": {
                                "obligations": [
                                    {
                                        "number": "123",
                                        "financialInstitutionInformation": {
                                            "name": "BBVA COLOMBIA"
                                        },
                                        "classificationStatus": {"id": central_status},
                                    }
                                ]
                            }
                        }
                    }
                )

                self.assertEqual(centrales_data["123"]["pasivo"], "embargado")

    async def test_dem_empty_with_central_embargo_returns_id_msg_13(self) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "123",
                        "origin_flag": "PASIVE",
                        "blocking_type": "0",
                        "contract_id": "00131234567890",
                    }
                ]
            ),
            centrales_data={123: {"pasivo": "embargado"}},
            customer_id="56780000",
            embargo_repository=StubEmbargoRepository(),
        )

        hallazgos = data["validaciones"][0]["hallazgos"]
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["id_msg"], 13)

    async def test_dem_no_concluyente_without_central_returns_id_msg_1(self) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "123",
                        "origin_flag": "PASIVE",
                        "contract_id": "00131234567890",
                    }
                ]
            ),
            centrales_data={},
            customer_id="56780000",
            embargo_repository=StubEmbargoRepository([{"dem_estado": ""}]),
        )

        hallazgos = data["validaciones"][0]["hallazgos"]
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["id_msg"], 1)
        self.assertEqual(hallazgos[0]["valor"], "Status Actualizado, sin embargo")
        self.assertEqual(data["validaciones"][0]["origin_flag"], "PASIVE")

    async def test_dem_embargo_without_central_returns_id_msg_13(self) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "123",
                        "origin_flag": "PASIVE",
                        "blocking_type": "P",
                        "contract_id": "00131234567890",
                    }
                ]
            ),
            centrales_data={},
            customer_id="56780000",
            embargo_repository=StubEmbargoRepository(
                [
                    {
                        "emb_juzgado": "JUZGADO 5 CIVIL",
                        "emb_imp_total": "2500000",
                        "emb_nro_ofic": "OF-2026-001",
                        "emb_fecha_ofic": "2026-02-20",
                        "dem_estado": "A",
                    }
                ]
            ),
        )

        hallazgo = data["validaciones"][0]["hallazgos"][0]
        self.assertEqual(hallazgo["id_msg"], 13)

    async def test_embargo_case_24_lifted_in_dem_returns_id_msg_11(self) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "123",
                        "origin_flag": "PASIVE",
                        "blocking_type": "P",
                        "contract_id": "00131234567890",
                        "contract_status_type_desc": "ACTIVO",
                    }
                ]
            ),
            centrales_data={},
            customer_id="56780000",
            embargo_repository=StubEmbargoRepository(
                [
                    {
                        "emb_juzgado": "JUZGADO 12 CIVIL",
                        "emb_imp_total": "2500000",
                        "emb_nro_ofic": "OF-2026-001",
                        "emb_fecha_ofic": "2026-02-20",
                        "dem_estado": "D",
                        "dem_timest_umo": "2026-03-01",
                    },
                    {
                        "emb_juzgado": "JUZGADO 15 CIVIL",
                        "emb_imp_total": "3000000",
                        "emb_nro_ofic": "OF-2026-002",
                        "emb_fecha_ofic": "2026-03-10",
                        "dem_estado": "D",
                        "dem_timest_umo": "2026-04-01",
                    }
                ]
            ),
        )

        hallazgo = data["validaciones"][0]["hallazgos"][0]
        self.assertEqual(hallazgo["id_msg"], 11)
        self.assertEqual(hallazgo["tipo"], "Cuenta Desembargada")
        self.assertEqual(len(hallazgo["valor"]), 2)
        self.assertEqual(hallazgo["valor"][0]["fecha_desembargo"], "2026-03-01")
        self.assertEqual(hallazgo["valor"][1]["fecha_desembargo"], "2026-04-01")
        self.assertEqual(hallazgo["valor"][0]["status"], "ACTIVO")

    async def test_dem_desembargo_with_central_embargo_returns_id_msg_13(self) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "123",
                        "origin_flag": "PASIVE",
                        "blocking_type": "P",
                        "contract_id": "00131234567890",
                    }
                ]
            ),
            centrales_data={123: {"pasivo": "embargado"}},
            customer_id="56780000",
            embargo_repository=StubEmbargoRepository(
                [
                    {"dem_estado": "D", "dem_timest_umo": "2026-03-01"},
                    {"dem_estado": "D", "dem_timest_umo": "2026-04-01"},
                ]
            ),
        )

        hallazgo = data["validaciones"][0]["hallazgos"][0]
        self.assertEqual(hallazgo["id_msg"], 13)

    async def test_dem_no_concluyente_without_central_returns_id_msg_1_even_with_blocking_type(self) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "key_id": "123",
                        "origin_flag": "PASIVE",
                        "blocking_type": "P",
                        "contract_id": "00131234567890",
                    }
                ]
            ),
            centrales_data={},
            customer_id="56780000",
            embargo_repository=StubEmbargoRepository(
                [
                    {
                        "emb_juzgado": "",
                        "dem_estado": "",
                    }
                ]
            ),
        )

        hallazgo = data["validaciones"][0]["hallazgos"][0]
        self.assertEqual(hallazgo["id_msg"], 1)
        self.assertEqual(hallazgo["valor"], "Status Actualizado, sin embargo")

    async def test_build_data_matches_customer_id_without_left_zeroes(self) -> None:
        data = build_data_from_customer_df_and_centrales(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "01232829",
                        "key_id": "58",
                    }
                ]
            ),
            centrales_data={},
            customer_id="1232829",
        )

        self.assertEqual(len(data["validaciones"]), 1)
        self.assertEqual(data["validaciones"][0]["key_id"], "58")
        self.assertEqual(
            data["validaciones"][0]["commercial_product_desc"],
            "Producto financiero",
        )

    async def test_build_consultar_data_uses_table_and_json_mapping(self) -> None:
        data = build_consultar_data(
            commercial_info_response={
                "data": {
                    "customer": {
                        "fullname": "Ada",
                        "identityDocument": {
                            "documentNumber": "123",
                            "documentType": {"description": "CC"},
                        },
                    },
                    "history": {"score": [{"creditScore": 800}]},
                    "thirdPartyResponse": {"name": "OK"},
                }
            },
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "personal_id": "123",
                        "personal_type": "CC",
                        "key_id": "123",
                        "default_flag": "t",
                    },
                    {
                        "customer_id": "otro-cliente",
                        "personal_id": "999",
                        "personal_type": "CC",
                        "key_id": "999",
                        "default_flag": "t",
                    }
                ]
            ),
            customer_id="56780000",
        )

        self.assertEqual(data["fullname"], "Ada")
        self.assertEqual(data["document_number"], "123")
        self.assertEqual(data["document_type"], "CC")
        self.assertEqual(data["credit_score"], 800)
        self.assertIn("validaciones", data["hallazgos"])

    async def test_build_centrales_no_autorizo_data_returns_false(self) -> None:
        data = build_centrales_no_autorizo_data(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "account_status_type_desc": "CANCELADO",
                    }
                ]
            ),
            customer_id="56780000",
        )

        self.assertEqual(data, {"bandera": "false", "id_msg": 15, "tipo": ""})

    async def test_build_centrales_no_autorizo_data_returns_true_with_date(self) -> None:
        data = build_centrales_no_autorizo_data(
            customer_identity_df=pd.DataFrame(
                [
                    {
                        "customer_id": "56780000",
                        "account_status_type_desc": "ACTIVO",
                        "commercial_product_desc": "CUENTA DE AHORROS",
                        "contract_register_date": "2024-01-10",
                        "contract_id": "1111000011112222",
                    },
                    {
                        "customer_id": "56780000",
                        "account_status_type_desc": "ACTIVO",
                        "commercial_product_desc": "TARJETA DE CREDITO",
                        "contract_register_date": "2026-05-21",
                        "contract_id": "9999888877776666",
                    },
                ]
            ),
            customer_id="56780000",
        )

        self.assertEqual(
            data,
            {
                "bandera": "true",
                "id_msg": 14,
                "tipo": "TARJETA DE CREDITO",
                "fecha": "2026-05-21",
                "contract_id_last4": "6666",
            },
        )


if __name__ == "__main__":
    unittest.main()


class GetCustomerDisplayNameTests(unittest.TestCase):
    def _repo(self, rows):
        class _FakeRepo:
            def read_customer_identity_df(self, customer_id=None):
                return pd.DataFrame(rows)

        return _FakeRepo()

    def test_returns_given_names_without_surnames(self) -> None:
        from application.customer.consultar_service import get_customer_display_name

        repo = self._repo(
            [
                {
                    "customer_id": "07893963",
                    "personal_id": "x",
                    "personal_type": "1",
                    "customer_name": "JUAN DAVID MARIN SALAZAR",
                    "first_last_name": "MARIN",
                    "second_last_name": "SALAZAR",
                }
            ]
        )
        self.assertEqual(
            get_customer_display_name(customer_id="07893963", identity_repository=repo),
            "Juan David",
        )

    def test_returns_empty_when_no_rows(self) -> None:
        from application.customer.consultar_service import get_customer_display_name

        repo = self._repo([])
        self.assertEqual(
            get_customer_display_name(customer_id="x", identity_repository=repo), ""
        )

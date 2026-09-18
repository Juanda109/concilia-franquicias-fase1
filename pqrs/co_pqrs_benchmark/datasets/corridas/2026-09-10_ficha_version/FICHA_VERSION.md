# Ficha de versión · f35bc58 (feature/PQRSllmops)

Generada 2026-09-10T13:33:55+00:00 por `scripts/build_release_card.py`. Árbol limpio.

## Imágenes declaradas en el IaC

| Servicio | Tag | Manifiesto |
|---|---|---|
| co_pqrs_authorization | `test_v1.0.0` | IaC/backend/co_pqrs_authorization/03-deployment.yaml |
| co_pqrs_back_agent | `test_v1.0.6` | IaC/backend/co_pqrs_back_agent/03-deployment.yaml |
| co_pqrs_back_commercial_info_simulator | `v1` | IaC/backend/co_pqrs_back_commercial_info_simulator/01-deployment.yaml |
| co_pqrs_back_conversation_extractor | `v1` | IaC/backend/co_pqrs_back_conversation_extractor/00-cronjob.yaml |
| co_pqrs_back_data | `test_v1.0.2` | IaC/backend/co_pqrs_back_data/01-deployment.yaml |
| co_pqrs_back_doble_cobro | `test_v1.0.0` | IaC/backend/co_pqrs_back_doble_cobro/03-deployment.yaml |
| co_pqrs_back_error_handler | `v1` | IaC/backend/co_pqrs_back_error_handler/01-deployment.yaml |
| co_pqrs_back_load_ada_data | `v2` | IaC/backend/co_pqrs_back_load_ada_data/00-cronjob.yaml |
| co_pqrs_back_load_seizures_data | `v1` | IaC/backend/co_pqrs_back_load_seizures_data/00-cronjob.yaml |
| co_pqrs_back_maintenance | `v1` | IaC/backend/co_pqrs_back_maintenance/01-deployment.yaml |
| co_pqrs_back_report | `v1` | IaC/backend/co_pqrs_back_report/01-cronjob.yaml |
| co_pqrs_back_trx_aso_simulator | `test_v1.0.5` | IaC/backend/co_pqrs_back_trx_aso_simulator/01-deployment.yaml |
| co_pqrs_back_trx_noreconocida | `test_v1.0.6` | IaC/backend/co_pqrs_back_trx_noreconocida/03-deployment.yaml |
| co_pqrs_back_trx_tantia_export | `v1` | IaC/backend/co_pqrs_back_trx_tantia_export/00-cronjob.yaml |
| co_pqrs_benchmark | `v8` | IaC/backend/co_pqrs_benchmark/01-cronjob.yaml |
| co_pqrs_front_test | `v1` | IaC/frontend/co_pqrs_front_test/01-deployment.yaml |

## Configuración del agente (ConfigMap de dev)

| Variable | Valor |
|---|---|
| `LLM_MODEL` | `agentepqrs-llm-live-test-gpt56-terra` |
| `LLM_EMBEDDINGS` | `agentepqrs-llm-live-emebed-3-large` |
| `GUARDRAIL_JUDGE_ENABLED` | `true` |
| `TRX_FLOW_ENABLED` | `true` |
| `LLM_CLOSURE_ENABLED` | `false` |
| `MAX_DAILY_SESSIONS` | `1000` |
| `MAX_DAILY_CATEGORY_INTERACTIONS` | `1000` |
| `RABBITMQ_ENABLED` | `true` |

## Conocimiento y guardrails (lo que el modelo sabe y lo que lo filtra)

| Pieza | SHA-256 (16) | Último cambio |
|---|---|---|
| catalogo_ruteo | `20286dee05514a5f` | 0a0da5e 2026-09-07 |
| prompt_ruteo | `440f68b75c4fbc3f` | 4e9602d 2026-08-20 |
| mensajes_generales | `a74cb8d112922ad7` | 2d2fbe8 2026-09-03 |
| pasos_compartidos | `4498d793af888979` | 963d2be 2026-06-16 |
| flujo_trx_no_reconocida | `e159905801059a19` | 3600120 2026-09-03 |
| flujo_doble_cobro | `560cb288c5a262a0` | ecfa2d8 2026-09-08 |
| guardrail_input_screen | `53552e0e41032805` | 61b065b 2026-08-21 |
| guardrail_judge | `589e8bb5a325cc2b` | 53124ac 2026-08-20 |
| guardrail_scope | `e8af6affda4343ce` | 9e7b366 2026-06-16 |

## Datasets de evaluación

| Dataset | Casos | SHA-256 (16) | Último cambio |
|---|---|---|---|
| adversarial_routing.json | 60 | `669420cf9d0ddde8` | c63f049 2026-09-09 |
| bypass_flows.json | 20 | `5b4a9ada1ce01c42` | c63f049 2026-09-09 |
| canario_rutas_criticas.json | 8 | `2661a27e7a6a3883` | d56f074 2026-09-07 |
| doble_cobro_routing.json | 28 | `85bdee306c260d7f` | a4f0297 2026-09-05 |
| grounding.json | 23 | `90f6c5388ce25e36` | 77a30f7 2026-09-09 |
| trx_no_reconocida_routing.json | 36 | `b48e169b030c7e6a` | 3b6c69a 2026-09-09 |

## Alertas y cadencias

- `CANARIO_PRECISION_THRESHOLD` = `90`
- `ALERT_LOOKBACK` = `24h`
- `RUTA_CAIDA_LOOKBACK` = `70m`
- `RUTA_CAIDA_MIN_CORRIDAS` = `2`
- `ALERT_RECIPIENTS` = `fabianandres.figueroa@bbva.com`
- benchmark: `0 3 * * * (suspendido)`
- canario: `*/30 7-20 * * *`

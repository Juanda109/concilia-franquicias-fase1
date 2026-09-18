# Inventario de tests por control KYNS IT

> Generado por `scripts/build_test_inventory.py` desde las suites. Cada test aparece con la primera
> línea de su docstring (o la de su clase o módulo) y los controles que evidencia según su fichero.
> Un test sin control asignado es cobertura funcional general.

## Resumen

| Servicio | Tests | Con control asignado | Cómo se corre |
|---|---|---|---|
| co_pqrs_back_agent | 597 | 390 | `cd co_pqrs_back_agent && RABBITMQ_ENABLED=false uv run pytest -q` |
| co_pqrs_benchmark | 51 | 51 | `cd co_pqrs_benchmark && uv run --python 3.14 --with pyyaml --with pytest --with-requirements requirements.txt pytest -q` |
| co_pqrs_back_trx_noreconocida | 168 | 26 | `cd co_pqrs_back_trx_noreconocida && uv run pytest -q` |
| co_pqrs_back_doble_cobro | 38 | 13 | `cd co_pqrs_back_doble_cobro && uv run pytest -q` |
| co_pqrs_back_data | 63 | 9 | `cd co_pqrs_back_data && uv run pytest -q` |
| co_pqrs_back_error_handler | 24 | 9 | `cd co_pqrs_back_error_handler && uv sync --extra test && uv run pytest -q` |

## Tests por control

### IT1.2 · 154 tests en 9 ficheros

- `co_pqrs_back_agent/tests/test_application/test_centrales_routing_gate.py`
- `co_pqrs_back_agent/tests/test_application/test_chat_service.py`
- `co_pqrs_back_agent/tests/test_application/test_metrics_events.py`
- `co_pqrs_back_agent/tests/test_application/test_pqrs_no_ruteo.py`
- `co_pqrs_back_agent/tests/test_application/test_qa_routing_cases.py`
- `co_pqrs_benchmark/tests/test_dataset_configmap.py`
- `co_pqrs_benchmark/tests/test_dataset_trx_no_reconocida.py`
- `co_pqrs_benchmark/tests/test_events.py`
- `co_pqrs_benchmark/tests/test_job_events.py`

### IT1.3 · 6 tests en 1 ficheros

- `co_pqrs_benchmark/tests/test_grounding.py`

### IT1.4 · 42 tests en 5 ficheros

- `co_pqrs_back_agent/src/guardrail/tests/test_input_screen.py`
- `co_pqrs_back_agent/src/guardrail/tests/test_judge.py`
- `co_pqrs_back_agent/src/guardrail/tests/test_scope.py`
- `co_pqrs_back_trx_noreconocida/tests/test_application/test_no_mock_guardrail.py`
- `co_pqrs_benchmark/tests/test_adversarial.py`

### IT1.6 · 5 tests en 1 ficheros

- `co_pqrs_benchmark/tests/test_release_card.py`

### IT2.2 · 5 tests en 1 ficheros

- `co_pqrs_benchmark/tests/test_release_card.py`

### IT2.3 · 65 tests en 4 ficheros

- `co_pqrs_back_agent/tests/test_application/test_event_source.py`
- `co_pqrs_back_agent/tests/test_application/test_metrics_events.py`
- `co_pqrs_benchmark/tests/test_events.py`
- `co_pqrs_benchmark/tests/test_job_events.py`

### IT2.6 · 11 tests en 1 ficheros

- `co_pqrs_back_agent/tests/test_application/test_trx_canary_gate.py`

### IT3.2 · 50 tests en 6 ficheros

- `co_pqrs_back_data/tests/test_infrastructure/test_commercial_info_trace_masking.py`
- `co_pqrs_back_data/tests/test_infrastructure/test_persistence/test_commercial_info_trace.py`
- `co_pqrs_back_doble_cobro/tests/test_aso_client.py`
- `co_pqrs_back_error_handler/tests/test_trace_sanitizer.py`
- `co_pqrs_back_trx_noreconocida/tests/test_infrastructure/test_aso_client_trazas_sin_secretos.py`
- `co_pqrs_back_trx_noreconocida/tests/test_infrastructure/test_aso_debug.py`

### IT3.3 · 10 tests en 1 ficheros

- `co_pqrs_back_agent/tests/test_application/test_integridad_financiera.py`

### IT3.4 · 12 tests en 1 ficheros

- `co_pqrs_benchmark/tests/test_adversarial.py`

### IT3.5 · 42 tests en 5 ficheros

- `co_pqrs_back_agent/src/guardrail/tests/test_input_screen.py`
- `co_pqrs_back_agent/src/guardrail/tests/test_judge.py`
- `co_pqrs_back_agent/src/guardrail/tests/test_scope.py`
- `co_pqrs_back_trx_noreconocida/tests/test_application/test_no_mock_guardrail.py`
- `co_pqrs_benchmark/tests/test_adversarial.py`

### IT3.6 · 50 tests en 6 ficheros

- `co_pqrs_back_data/tests/test_infrastructure/test_commercial_info_trace_masking.py`
- `co_pqrs_back_data/tests/test_infrastructure/test_persistence/test_commercial_info_trace.py`
- `co_pqrs_back_doble_cobro/tests/test_aso_client.py`
- `co_pqrs_back_error_handler/tests/test_trace_sanitizer.py`
- `co_pqrs_back_trx_noreconocida/tests/test_infrastructure/test_aso_client_trazas_sin_secretos.py`
- `co_pqrs_back_trx_noreconocida/tests/test_infrastructure/test_aso_debug.py`

### IT3.7 · 50 tests en 6 ficheros

- `co_pqrs_back_data/tests/test_infrastructure/test_commercial_info_trace_masking.py`
- `co_pqrs_back_data/tests/test_infrastructure/test_persistence/test_commercial_info_trace.py`
- `co_pqrs_back_doble_cobro/tests/test_aso_client.py`
- `co_pqrs_back_error_handler/tests/test_trace_sanitizer.py`
- `co_pqrs_back_trx_noreconocida/tests/test_infrastructure/test_aso_client_trazas_sin_secretos.py`
- `co_pqrs_back_trx_noreconocida/tests/test_infrastructure/test_aso_debug.py`

### IT4.2 · 155 tests en 8 ficheros

- `co_pqrs_back_agent/tests/test_application/test_doble_cobro_flow.py`
- `co_pqrs_back_agent/tests/test_application/test_product_options.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_autorizacion_fase4.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_flow.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_orchestration.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_state.py`
- `co_pqrs_back_agent/tests/test_application/test_workflow_actions.py`
- `co_pqrs_back_agent/tests/test_domain/test_workflow/test_catalogo_capacidades.py`

### IT4.3 · 12 tests en 1 ficheros

- `co_pqrs_benchmark/tests/test_adversarial.py`

### IT4.4 · 69 tests en 3 ficheros

- `co_pqrs_back_agent/tests/test_application/test_doble_cobro_flow.py`
- `co_pqrs_back_agent/tests/test_application/test_hardening.py`
- `co_pqrs_back_agent/tests/test_application/test_integridad_financiera.py`

### IT4.5 · 190 tests en 8 ficheros

- `co_pqrs_back_agent/tests/test_application/test_chat_service.py`
- `co_pqrs_back_agent/tests/test_application/test_doble_cobro_flow.py`
- `co_pqrs_back_agent/tests/test_application/test_hardening.py`
- `co_pqrs_back_agent/tests/test_application/test_integridad_financiera.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_autorizacion_fase4.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_flow.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_orchestration.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_state.py`

### IT4.6 · 25 tests en 2 ficheros

- `co_pqrs_back_agent/tests/test_application/test_category_cap_flow.py`
- `co_pqrs_back_agent/tests/test_domain/test_workflow/test_limit_category.py`

### IT4.7 · 118 tests en 6 ficheros

- `co_pqrs_back_agent/tests/test_application/test_event_source.py`
- `co_pqrs_back_agent/tests/test_application/test_metrics_events.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_autorizacion_fase4.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_flow.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_orchestration.py`
- `co_pqrs_back_agent/tests/test_application/test_trx_state.py`

## Detalle

### co_pqrs_back_agent

| Fichero | Test | Qué demuestra | Controles |
|---|---|---|---|
| src/guardrail/tests/test_input_screen.py | `ScreenUserInputTests::test_normal_banking_question_passes` | Tests Fase 2: filtro deterministico de entrada. | IT1.4, IT3.5 |
| src/guardrail/tests/test_input_screen.py | `ScreenUserInputTests::test_empty_input_is_blocked` | Tests Fase 2: filtro deterministico de entrada. | IT1.4, IT3.5 |
| src/guardrail/tests/test_input_screen.py | `ScreenUserInputTests::test_too_long_input_is_blocked` | Tests Fase 2: filtro deterministico de entrada. | IT1.4, IT3.5 |
| src/guardrail/tests/test_input_screen.py | `ScreenUserInputTests::test_prompt_injection_is_blocked` | Tests Fase 2: filtro deterministico de entrada. | IT1.4, IT3.5 |
| src/guardrail/tests/test_input_screen.py | `ScreenUserInputTests::test_actua_como_is_blocked` | Tests Fase 2: filtro deterministico de entrada. | IT1.4, IT3.5 |
| src/guardrail/tests/test_input_screen.py | `ThirdPartyDataRequestTests::test_third_party_request_returns_specific_privacy_message` | Rechazo controlado y acotado de solicitudes de datos de terceros. | IT1.4, IT3.5 |
| src/guardrail/tests/test_input_screen.py | `ThirdPartyDataRequestTests::test_clear_third_party_variants_are_detected` | Rechazo controlado y acotado de solicitudes de datos de terceros. | IT1.4, IT3.5 |
| src/guardrail/tests/test_input_screen.py | `ThirdPartyDataRequestTests::test_own_account_questions_are_not_flagged` | Rechazo controlado y acotado de solicitudes de datos de terceros. | IT1.4, IT3.5 |
| src/guardrail/tests/test_judge.py | `VerdictToBlockTests::test_in_scope_allows` | Tests Fase 3: LLM-as-judge (piezas puras y no-op cuando esta desactivado). | IT1.4, IT3.5 |
| src/guardrail/tests/test_judge.py | `VerdictToBlockTests::test_out_of_scope_blocks` | Tests Fase 3: LLM-as-judge (piezas puras y no-op cuando esta desactivado). | IT1.4, IT3.5 |
| src/guardrail/tests/test_judge.py | `VerdictToBlockTests::test_out_of_scope_message_comes_from_pool` | Tests Fase 3: LLM-as-judge (piezas puras y no-op cuando esta desactivado). | IT1.4, IT3.5 |
| src/guardrail/tests/test_judge.py | `JudgeEnabledTests::test_enabled_true` | Tests Fase 3: LLM-as-judge (piezas puras y no-op cuando esta desactivado). | IT1.4, IT3.5 |
| src/guardrail/tests/test_judge.py | `JudgeEnabledTests::test_disabled_false` | Tests Fase 3: LLM-as-judge (piezas puras y no-op cuando esta desactivado). | IT1.4, IT3.5 |
| src/guardrail/tests/test_judge.py | `JudgeDisabledNoOpTests::test_disabled_returns_none` | Tests Fase 3: LLM-as-judge (piezas puras y no-op cuando esta desactivado). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `AcceptsRoutingTests::test_high_confidence_match_is_accepted` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `AcceptsRoutingTests::test_medium_confidence_match_is_accepted` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `AcceptsRoutingTests::test_low_confidence_match_is_rejected` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `AcceptsRoutingTests::test_none_confidence_match_is_rejected` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `AcceptsRoutingTests::test_not_match_is_rejected` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `AcceptsRoutingTests::test_empty_workflow_is_rejected` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `ScopePromptTests::test_suffix_enforces_out_of_scope_behavior` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `ScopePromptTests::test_suffix_forbids_forcing_faq_for_off_topic` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| src/guardrail/tests/test_scope.py | `ScopePromptTests::test_threshold_default` | Tests Fase 1: umbral de scope del routing (inyectando decisiones). | IT1.4, IT3.5 |
| tests/test_application/test_category_cap_flow.py | `CategoryCapTests::test_under_cap_proceeds` | Per-CASE daily cap (limit key = workflow). Centrales is skipped here and | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CategoryCapTests::test_centrales_is_skipped_at_start` | Per-CASE daily cap (limit key = workflow). Centrales is skipped here and | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CategoryCapTests::test_case_cap_reached_shows_warning_with_label` | Per-CASE daily cap (limit key = workflow). Centrales is skipped here and | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CategoryCapTests::test_case_cap_uses_option_label_fallback` | Per-CASE daily cap (limit key = workflow). Centrales is skipped here and | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CategoryCapTests::test_only_that_case_blocked_others_free` | Per-CASE daily cap (limit key = workflow). Centrales is skipped here and | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CategoryCapTests::test_trx_case_capped_shows_warning` | Per-CASE daily cap (limit key = workflow). Centrales is skipped here and | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CategoryCapTests::test_no_control_store_proceeds` | Per-CASE daily cap (limit key = workflow). Centrales is skipped here and | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CentralesSubflowCapTests::test_subflow_under_cap_records_and_proceeds` | Per-SUB-FLOW daily cap for centrales de riesgo (key | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CentralesSubflowCapTests::test_subflow_cap_reached_resets_and_warns` | Per-SUB-FLOW daily cap for centrales de riesgo (key | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CentralesSubflowCapTests::test_only_that_subflow_blocked_others_free` | Per-SUB-FLOW daily cap for centrales de riesgo (key | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `CentralesSubflowCapTests::test_no_control_store_proceeds` | Per-SUB-FLOW daily cap for centrales de riesgo (key | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `RepeatFlowYesShortCircuitTests::test_yes_continues_when_under_recheck_budget` | Tests for Layer B: per-category daily cap + repeat-flow re-checks. | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `RepeatFlowYesShortCircuitTests::test_yes_always_continues` | Tests for Layer B: per-category daily cap + repeat-flow re-checks. | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `RepeatFlowYesShortCircuitTests::test_no_declines_closes_session` | Tests for Layer B: per-category daily cap + repeat-flow re-checks. | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `ArchitectureADecoupleTests::test_consultation_terminal_returns_to_start_and_keeps_session_open` | Architecture A: a /chat turn never ends the session; a consultation | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `ArchitectureADecoupleTests::test_limit_terminated_close_is_not_reopened` | Architecture A: a /chat turn never ends the session; a consultation | IT4.6 |
| tests/test_application/test_category_cap_flow.py | `ArchitectureADecoupleTests::test_turn_on_closed_session_returns_cached_message_without_llm` | Architecture A: a /chat turn never ends the session; a consultation | IT4.6 |
| tests/test_application/test_centrales_not_verified.py | `NotVerifiedTerminalActionsTests::test_all_products_central_risk_no_backdata` | Regression guard: centrales terminal actions must NOT reassure when the | - |
| tests/test_application/test_centrales_not_verified.py | `NotVerifiedTerminalActionsTests::test_consulta_sin_permiso_no_backdata` | Regression guard: centrales terminal actions must NOT reassure when the | - |
| tests/test_application/test_centrales_not_verified.py | `NotVerifiedTerminalActionsTests::test_notificacion_centrales_no_backdata` | Regression guard: centrales terminal actions must NOT reassure when the | - |
| tests/test_application/test_centrales_routing_gate.py | `CentralesRoutingGateTests::test_explicit_centrales_cases_are_detected` | Tests del keyword-gate de centrales (acote minimo). | IT1.2 |
| tests/test_application/test_centrales_routing_gate.py | `CentralesRoutingGateTests::test_generic_report_terms_no_longer_trigger` | Tests del keyword-gate de centrales (acote minimo). | IT1.2 |
| tests/test_application/test_centrales_routing_gate.py | `CentralesRoutingGateTests::test_transaction_block_and_freeze_are_not_centrales` | Tests del keyword-gate de centrales (acote minimo). | IT1.2 |
| tests/test_application/test_centrales_routing_gate.py | `CentralesRoutingGateTests::test_unrelated_and_empty_are_not_detected` | Tests del keyword-gate de centrales (acote minimo). | IT1.2 |
| tests/test_application/test_centrales_routing_gate.py | `CentralesEntryHintTests::test_explicit_anchors_auto_enter` | El auto-entry al sub-flujo de centrales SOLO con ancla explicita. | IT1.2 |
| tests/test_application/test_centrales_routing_gate.py | `CentralesEntryHintTests::test_bare_terms_do_not_auto_enter` | El auto-entry al sub-flujo de centrales SOLO con ancla explicita. | IT1.2 |
| tests/test_application/test_centrales_routing_gate.py | `CentralesEntryHintTests::test_other_workflows_never_get_hint` | El auto-entry al sub-flujo de centrales SOLO con ancla explicita. | IT1.2 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_start_returns_configured_greeting_without_user_message` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_start_greets_with_given_name_from_postgres` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_start_first_session_records_daily_counter` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_start_when_active_session_exists_resumes_idempotently` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_start_reopens_when_previous_session_is_closed` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_start_opens_even_past_daily_session_limit` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_start_without_control_store_skips_limit` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_prefetch_back_data_clears_stale_result_and_polls_for_fresh_data` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_first_chat_message_routes_with_agent_then_keeps_yaml_flow` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_pure_greeting_returns_welcome_without_invoking_agent` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_greeting_with_intent_still_routes_with_agent` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_chat_turn_can_continue_in_background_and_block_parallel_turns` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_guide_shortcut_enters_selected_branch_without_skipping_intro` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_embargo_context_enters_risk_branch_intro_before_follow_up_steps` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_central_risk_terminal_message_skips_agent_and_keeps_default_response` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_sold_portfolio_terminal_message_keeps_yaml_response` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_end_closes_active_conversation_and_notifies_callback` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_end_callback_url_template_is_resolved_with_conversation_id` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ChatServiceFlowTests::test_end_returns_already_closed_conversation_without_persisting_changes` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ExtractGivenNamesTests::test_strips_both_surnames_and_titlecases` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ExtractGivenNamesTests::test_single_surname` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `ExtractGivenNamesTests::test_empty_or_only_surnames_returns_empty` |  | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `AmbiguityConfirmationTests::test_low_confidence_asks_natural_confirmation` | Punto 2: candidato ambiguo (confidence=low) -> confirmación '¿Te refieres a ...?'. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `AmbiguityConfirmationTests::test_low_confidence_continuar_enters_flow` | Punto 2: candidato ambiguo (confidence=low) -> confirmación '¿Te refieres a ...?'. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `AmbiguityConfirmationTests::test_low_confidence_salir_goes_to_pqrs_form` | Punto 2: candidato ambiguo (confidence=low) -> confirmación '¿Te refieres a ...?'. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `GreetingResilienceTests::test_elongated_greeting_returns_welcome_without_agent` | Saludos simples y complejos deben re-saludar (no caer al formulario). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `GreetingResilienceTests::test_buena_tarde_returns_welcome_without_agent` | Saludos simples y complejos deben re-saludar (no caer al formulario). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `GreetingResilienceTests::test_greeting_at_satisfaction_check_resets_and_welcomes` | Saludos simples y complejos deben re-saludar (no caer al formulario). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `GreetingResilienceTests::test_elongated_greeting_plus_intent_still_routes` | Saludos simples y complejos deben re-saludar (no caer al formulario). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `IsBarePqrsRequestTests::test_bare_meta_requests_are_detected` | Detector determinista de meta-peticiones 'peladas' de PQR (sin causal). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `IsBarePqrsRequestTests::test_requests_with_causal_are_not_bare` | Detector determinista de meta-peticiones 'peladas' de PQR (sin causal). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `IsBarePqrsRequestTests::test_non_pqr_and_form_failure_messages_are_not_bare` | Detector determinista de meta-peticiones 'peladas' de PQR (sin causal). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `BarePqrsClarificationFlowTests::test_bare_formulario_pqr_asks_for_reason_post_router` | Flujo de dos pasos: pide el causal y re-rutea; nunca pisa un match. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `BarePqrsClarificationFlowTests::test_continue_moves_to_reason_prompt_without_new_routing` | Flujo de dos pasos: pide el causal y re-rutea; nunca pisa un match. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `BarePqrsClarificationFlowTests::test_reason_reroutes_when_it_maps_to_a_workflow` | Flujo de dos pasos: pide el causal y re-rutea; nunca pisa un match. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `BarePqrsClarificationFlowTests::test_repeated_bare_reinvites_indefinitely` | Flujo de dos pasos: pide el causal y re-rutea; nunca pisa un match. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `BarePqrsClarificationFlowTests::test_router_match_is_never_overridden_by_clarification` | Flujo de dos pasos: pide el causal y re-rutea; nunca pisa un match. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `BarePqrsClarificationFlowTests::test_pqr_with_causal_in_same_message_is_not_clarified` | Flujo de dos pasos: pide el causal y re-rutea; nunca pisa un match. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `TrxLoopTests::test_si_siguiente_advances_to_next_transaction` | Bucle 'una transacción a la vez' del flujo TXNR (Árbol 1). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `TrxLoopTests::test_last_transaction_does_not_advance` | Bucle 'una transacción a la vez' del flujo TXNR (Árbol 1). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `TrxLoopTests::test_handler_ignores_other_workflows` | Bucle 'una transacción a la vez' del flujo TXNR (Árbol 1). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `TrxVigenciaRoutingTests::test_vencida_routes_to_date_exit` | Ruteo del gate 2.4.0.1.8 (vigencia offline por franquicia/fecha). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `TrxVigenciaRoutingTests::test_vigente_without_movements_routes_to_return` | Ruteo del gate 2.4.0.1.8 (vigencia offline por franquicia/fecha). | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `TrxRecurrenceRoutingTests::test_recurrence_redirects_to_dedicated_pqr_step` | Ruteo del paso 2.4.0.1 segun la recurrencia detectada por back_trx. | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `TrxRecurrenceRoutingTests::test_no_recurrence_salta_directo_a_cantidad` | Validacion silenciosa (ajuste 13/08): sin recurrencia, el gate | IT1.2, IT4.5 |
| tests/test_application/test_chat_service.py | `GuardrailBlockStatusTests::test_third_party_block_normalizes_running_to_active` | Un bloqueo del guardrail debe finalizar el turno como Active (no Running). | IT1.2, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroEngineTests::test_entry_step_offers_three_families` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroEngineTests::test_credit_card_goes_to_pqr_form_and_satisfaction` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroEngineTests::test_terminal_steps_are_terminal` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroEngineTests::test_approved_terminals_no_longer_exist` | El bot no gestiona estados: no puede decir que un caso fue aprobado. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroEngineTests::test_transaction_selector_is_multi_select_with_paging_and_report` | 3.4.0.6: seleccion multiple, paginar, reportar o no encontrar. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroEngineTests::test_no_procede_never_promises_a_credit` | El terminal por defecto no puede contener promesa de abono. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `ParseAmountTests::test_variants_reach_the_same_amount` | El YAML pide "solo numeros"; el cliente escribe con $ y puntos igual. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `ParseAmountTests::test_unparseable_input_is_zero_not_crash` | El YAML pide "solo numeros"; el cliente escribe con $ y puntos igual. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_products_found_stay_on_selector` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_no_products_reroutes_to_pqr` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_validity_ok_advances_to_amount` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_settlement_pending_terminates_with_dynamic_days` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_expired_windows_reroute_to_pqr` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_validity_service_down_fails_closed_to_pqr` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_previous_report_no_longer_blocks_the_flow` | Ajuste del 8-sep: con reporte previo se continua igual a los grupos. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_report_from_other_flow_is_not_read_as_doble_cobro` | La ficha de TXNR del mismo cliente no se confunde con la de doble cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_clean_client_chains_into_group_search` | Sin reporte previo, el mismo turno encadena la busqueda de grupos. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_store_unreadable_fails_open_into_group_search` | Sin lectura de la ficha no se bloquea al cliente. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_no_groups_reroutes_to_pqr` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_every_movement_in_range_is_offered` | Se ofrecen TODOS los movimientos del rango, no solo los sobrantes. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_a_lone_charge_is_still_offered` | Un cargo suelto se muestra igual, no se descarta por adelantado. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_transaction_click_toggles_selection_on_and_off` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_unknown_transaction_click_is_ignored` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_more_movements_pages_forward_and_stops_at_the_last_page` | Dos paginas justas: un clic avanza a la 1 y el segundo no pasa de ahi. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_changed_query_refetches_groups_and_resets_selection` | Si el cliente cambia el monto, se vuelve a buscar y la seleccion se descarta. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_register_without_selection_returns_to_groups_with_warning` | Golden paths del flujo doble_cobro. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_register_writes_only_the_selected_transactions_and_confirms_pending` | Marcadas las dos parejas (m-1/m-2 y m-8/m-9): m-7 queda sin reportar. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_register_replaces_a_previous_report_of_the_same_transaction` | Ajuste del 8-sep: mismo producto + fecha + monto se sobreescribe, el resto se conserva. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_register_does_not_touch_the_trx_case_of_the_same_client` | Los dos flujos comparten indice: el prefijo del id evita pisarse. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_register_with_an_invalid_selection_never_promises_a_credit` | Una seleccion que no corresponde a ninguna transaccion no reporta nada. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_register_write_failure_fails_closed` | Si la ficha no se pudo escribir, nunca se promete abono. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_unreadable_case_after_write_fails_closed` | Escrito pero ilegible al releer: nunca se promete abono. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroGateTests::test_registered_case_is_exportable_to_tantia` | DEUDA (8-sep): el CronJob co_pqrs_back_trx_tantia_export solo exporta fichas con | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_the_first_page_is_full_and_shows_the_pager` | El paso 3.4.0.6 no avanza: cada clic alterna una casilla o pagina. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_click_toggles_the_box_on_and_off` | El paso 3.4.0.6 no avanza: cada clic alterna una casilla o pagina. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_selection_survives_pagination` | El paso 3.4.0.6 no avanza: cada clic alterna una casilla o pagina. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_report_button_carries_the_count` | El conteo va en la etiqueta: es lo unico que ve el front. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_only_the_final_actions_leave_the_step` | El paso 3.4.0.6 no avanza: cada clic alterna una casilla o pagina. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_not_found_goes_to_the_pqr_form` | El paso 3.4.0.6 no avanza: cada clic alterna una casilla o pagina. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_a_box_or_a_page_is_flagged_as_a_repaint` | La marca del turno: repintar la tarjeta en vez de encolar otra. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_leaving_the_step_is_not_a_repaint` | El paso 3.4.0.6 no avanza: cada clic alterna una casilla o pagina. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `DobleCobroMultiSelectTests::test_an_unmatched_option_is_not_a_repaint` | Sin opcion valida no se pisa la tarjeta: el aviso es un turno normal. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `SingleSelectorCardTests::test_a_click_repaints_the_card_instead_of_adding_one` | El selector es UNA tarjeta que se repinta, no un mensaje por clic. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `SingleSelectorCardTests::test_the_click_is_not_left_behind_in_the_index` | El clic se guarda por durabilidad antes de saber que era; se retira. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `SingleSelectorCardTests::test_a_real_turn_still_appends_both_messages` | Sin la marca no cambia nada: choice/text/date/number siguen igual. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `SingleSelectorCardTests::test_a_repaint_adds_up_the_tokens_of_the_card` | Repintar no puede borrar el consumo del turno que genero la tarjeta. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_doble_cobro_flow.py | `SingleSelectorCardTests::test_a_repaint_without_a_previous_card_falls_back_to_appending` | Sin tarjeta previa no hay nada que pisar: se agrega, no se pierde. | IT4.2, IT4.4, IT4.5 |
| tests/test_application/test_error_audit.py | `ErrorAuditTests::test_exception_report_noop_without_url` | Tests for the centralized error auditing module. | - |
| tests/test_application/test_error_audit.py | `ErrorAuditTests::test_exception_report_includes_traceback_and_type` | Tests for the centralized error auditing module. | - |
| tests/test_application/test_error_audit.py | `ErrorAuditTests::test_http_error_report_fields` | Tests for the centralized error auditing module. | - |
| tests/test_application/test_error_audit.py | `ErrorAuditTests::test_http_error_report_noop_without_url` | Tests for the centralized error auditing module. | - |
| tests/test_application/test_error_handler_client.py | `ReportAgentErrorTests::test_posts_expected_payload` | Tests for the fire-and-forget error reporting to the error-handler service. | - |
| tests/test_application/test_error_handler_client.py | `ReportAgentErrorTests::test_swallows_errors` | Tests for the fire-and-forget error reporting to the error-handler service. | - |
| tests/test_application/test_error_handler_client.py | `ScheduleErrorReportTests::test_no_url_is_noop` | Tests for the fire-and-forget error reporting to the error-handler service. | - |
| tests/test_application/test_error_handler_client.py | `ScheduleErrorReportTests::test_schedules_report_when_url_configured` | Tests for the fire-and-forget error reporting to the error-handler service. | - |
| tests/test_application/test_event_publisher.py | `EventPublisherTests::test_publish_sends_json_with_routing_key` | Tests for the RabbitMQ event publisher and the fire-and-forget emitter. | - |
| tests/test_application/test_event_publisher.py | `EventPublisherTests::test_publish_swallows_errors_and_resets` | Tests for the RabbitMQ event publisher and the fire-and-forget emitter. | - |
| tests/test_application/test_event_publisher.py | `EmitEventTests::test_emit_is_noop_when_disabled` | Tests for the RabbitMQ event publisher and the fire-and-forget emitter. | - |
| tests/test_application/test_event_publisher.py | `EmitEventTests::test_emit_schedules_publish_when_enabled` | Tests for the RabbitMQ event publisher and the fire-and-forget emitter. | - |
| tests/test_application/test_event_publisher.py | `EventBuilderTests::test_build_turn_event` | Tests for the RabbitMQ event publisher and the fire-and-forget emitter. | - |
| tests/test_application/test_event_publisher.py | `EventBuilderTests::test_build_closed_event` | Tests for the RabbitMQ event publisher and the fire-and-forget emitter. | - |
| tests/test_application/test_event_source.py | `EventSourceHelperTests::test_live_when_no_mark_and_no_context` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventSourceHelperTests::test_benchmark_when_marked` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventSourceHelperTests::test_live_when_conversation_is_none` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventSourceHelperTests::test_fallback_to_active_benchmark_context` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventSourceHelperTests::test_mark_is_idempotent` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventPayloadSourceTests::test_every_event_type_carries_source_live` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventPayloadSourceTests::test_every_event_type_carries_source_benchmark_when_marked` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventPayloadSourceTests::test_error_event_without_conversation_defaults_to_live` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `EventPayloadSourceTests::test_existing_fields_are_untouched` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `MarkPersistenceTests::test_reroute_reset_preserves_the_mark` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `MarkPersistenceTests::test_reroute_reset_keeps_live_conversation_unmarked` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `MarkPersistenceTests::test_mark_survives_opensearch_serialization_roundtrip` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartMarksConversationTests::test_start_with_benchmark_mode_marks_and_persists` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartMarksConversationTests::test_start_without_benchmark_mode_is_live` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartMarksConversationTests::test_start_falls_back_to_active_benchmark_context` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartMarksConversationTests::test_idempotent_start_marks_resumed_session` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartMarksConversationTests::test_end_without_header_emits_closed_with_benchmark_source` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartMarksConversationTests::test_end_of_live_conversation_emits_closed_with_live_source` | Tests for the ``source`` field on the analytics events (``benchmark`` / ``live``). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartRouteHeaderTests::test_header_present_forwards_benchmark_mode_true` | ``POST /start`` reads ``X-Benchmark-Mode`` and forwards ``benchmark_mode``. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `StartRouteHeaderTests::test_header_absent_forwards_benchmark_mode_false` | ``POST /start`` reads ``X-Benchmark-Mode`` and forwards ``benchmark_mode``. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `MarkIsNotBusinessDataTests::test_marked_conversation_has_no_resolved_guide_data` | La marca es un metadato: no cuenta como dato resuelto ni llega al LLM. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `MarkIsNotBusinessDataTests::test_business_captured_data_drops_the_mark_only` | La marca es un metadato: no cuenta como dato resuelto ni llega al LLM. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `MarkIsNotBusinessDataTests::test_local_summary_never_shows_the_mark_to_the_client` | La marca es un metadato: no cuenta como dato resuelto ni llega al LLM. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `FinalStepHeaderTests::test_final_step_recorded_when_capture_is_active` | El paso final viaja en X-Benchmark-Data para los datasets de bypass. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `FinalStepHeaderTests::test_final_step_is_noop_without_capture` | El paso final viaja en X-Benchmark-Data para los datasets de bypass. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `FinalStepHeaderTests::test_in_flow_turn_emits_header_with_zero_routing_time` | Un turno sin ruteo (dentro del flujo) tambien sale en la cabecera. | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `ResponseSourceHeaderTests::test_final_step_header_reports_the_model_when_it_wrote_the_text` | La cabecera del benchmark dice quien redacto el ultimo texto (grounding). | IT2.3, IT4.7 |
| tests/test_application/test_event_source.py | `ResponseSourceHeaderTests::test_approved_yaml_text_has_an_empty_response_source` | La cabecera del benchmark dice quien redacto el ultimo texto (grounding). | IT2.3, IT4.7 |
| tests/test_application/test_hardening.py | `IsRunningStuckTests::test_stuck_when_running_past_threshold` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `IsRunningStuckTests::test_not_stuck_when_recent` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `IsRunningStuckTests::test_not_stuck_when_no_running_since` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `IsRunningStuckTests::test_not_stuck_when_not_running` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `IsRunningStuckTests::test_naive_running_since_is_tolerated` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `WatchdogSnapshotTests::test_snapshot_recovers_stuck_running` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `WatchdogSnapshotTests::test_snapshot_leaves_recent_running` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `TurnHardCapTests::test_turn_exceeding_cap_finalizes_as_error` | Tests for the chat hardening: RUNNING watchdog + background turn hard cap. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `TurnClearsRunningTests::test_sin_match_sale_de_running` | Un turno que termina no puede dejar la conversacion en RUNNING. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `TurnClearsRunningTests::test_no_pisa_un_cierre_por_limite` | Una sesion cerrada por limite diario tiene que seguir cerrada. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `TurnClearsRunningTests::test_una_consulta_terminada_reabre_la_sesion` | Architecture A: al acabar una consulta se vuelve al inicio, no se cierra. | IT4.4, IT4.5 |
| tests/test_application/test_hardening.py | `TurnClearsRunningTests::test_no_pisa_un_error` | Un turno que termina no puede dejar la conversacion en RUNNING. | IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `TantiaAccumulationTests::test_same_transaction_twice_is_one_row` | IT 4.4: doble envio / reintento del paso de abono no duplica la fila. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `TantiaAccumulationTests::test_a_different_transaction_is_added` | IT 4.4: doble envio / reintento del paso de abono no duplica la fila. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `TantiaAccumulationTests::test_fingerprint_prefers_the_aso_identity_over_date_and_amount` | IT 4.4: doble envio / reintento del paso de abono no duplica la fila. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `DurableCaseIdempotencyTests::test_milestone_twice_keeps_one_document_and_one_milestone` | IT 4.4: la ficha del caso es una por cliente y flujo; un hito repetido no se duplica. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `DurableCaseIdempotencyTests::test_document_id_isolates_flows_without_renaming_the_historic_one` | IT 4.4: la ficha del caso es una por cliente y flujo; un hito repetido no se duplica. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `BlockReexecutionLockTests::test_lock_is_read_from_the_durable_record` | IT 4.5: accion ejecutada con fallo posterior -> el reintento no vuelve a bloquear. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `BlockReexecutionLockTests::test_lock_fails_open_when_the_record_cannot_be_read` | IT 4.5: accion ejecutada con fallo posterior -> el reintento no vuelve a bloquear. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `SingleTurnPerConversationTests::test_second_turn_while_running_is_ignored` | IT 4.4: dos envios concurrentes -> el segundo no arranca un turno paralelo. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `ConversationIsolationTests::test_conversation_id_is_derived_from_the_customer` | IT 3: el id de conversacion nace del cliente; dos clientes nunca comparten ficha. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_integridad_financiera.py | `ConversationIsolationTests::test_customer_id_is_taken_from_the_conversation_not_from_the_caller` | IT 3: el id de conversacion nace del cliente; dos clientes nunca comparten ficha. | IT3.3, IT4.4, IT4.5 |
| tests/test_application/test_metrics_events.py | `TurnEventFieldsTests::test_llm_used_true_when_tokens` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `TurnEventFieldsTests::test_llm_used_false_when_no_tokens` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `TurnEventFieldsTests::test_guardrail_blocked_flag` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `TurnEventFieldsTests::test_guardrail_blocked_default_false` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `TurnEventFieldsTests::test_routing_outcome_passthrough` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `TurnEventFieldsTests::test_subflow_key_only_for_centrales` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `TurnEventFieldsTests::test_subflow_key_none_for_other_workflows` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `ResolutionTests::test_limit_closed` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `ResolutionTests::test_resolved` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `ResolutionTests::test_not_resolved` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `ResolutionTests::test_abandoned` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `ResolutionTests::test_closed_default` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `ResolutionTests::test_closed_event_includes_resolution` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `CapReachedEventTests::test_case_scope_shape` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_metrics_events.py | `CapReachedEventTests::test_centrales_subflow_scope_shape` | Tests for the new analytics fields/events on the metrics pipeline: | IT1.2, IT2.3, IT4.7 |
| tests/test_application/test_permanencia_centrales.py | `test_add_months_to_date_positive` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_add_months_to_date_negative` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_add_months_to_date_leap_year` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_calculate_permanencia_end_short_mora` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_calculate_permanencia_end_long_mora_capped` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_calculate_permanencia_end_invalid_date` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_build_mora_negative_report_message_max_level_5_capped` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_build_mora_negative_report_message_max_level_4_no_castigo` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_render_structured_message_aliases_for_id_4` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_extract_latest_mora_profile_uses_most_recent_block` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_extract_latest_mora_profile_ignores_restructured_only_symbols` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_extract_current_mora_profile_requires_trailing_delinquency_block` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_cross_validate_mora_requires_real_delinquency_symbols` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_selected_product_skips_id_msg_dispatch_for_activo_mora_and_renders_permanencia` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_selected_product_generic_id_msg_with_obligation_vector_gt_120_uses_permanencia` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_selected_product_generic_id_msg_without_obligation_uses_id_4_for_le_120` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_selected_product_uses_back_data_vector_for_gt_120_without_obligation` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_selected_product_vector_with_trailing_c_routes_to_permanencia` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_find_obligation_by_key_id_matches_composite_product_id` |  | - |
| tests/test_application/test_permanencia_centrales.py | `test_selected_product_with_composite_product_id_enriches_obligation_and_uses_permanencia` |  | - |
| tests/test_application/test_pqrs_no_ruteo.py | `PqrsNoRuteoTests::test_internal_workflow_is_loaded_with_shared_steps` | Flujo interno pqrs_no_ruteo: pregunta del banco sin ruteo -> formulario PQRS. | IT1.2 |
| tests/test_application/test_pqrs_no_ruteo.py | `PqrsNoRuteoTests::test_entry_step_renders_unified_pqrs_text_and_pqr_option` | Flujo interno pqrs_no_ruteo: pregunta del banco sin ruteo -> formulario PQRS. | IT1.2 |
| tests/test_application/test_pqrs_no_ruteo.py | `PqrsNoRuteoTests::test_pqr_button_routes_to_satisfaction_check` | Flujo interno pqrs_no_ruteo: pregunta del banco sin ruteo -> formulario PQRS. | IT1.2 |
| tests/test_application/test_product_options.py | `BuildChoiceOptionsTests::test_truncates_to_number_of_found_products` | Tests for dynamic product-option rendering and the no-products routing. | IT4.2 |
| tests/test_application/test_product_options.py | `BuildChoiceOptionsTests::test_single_found_product_returns_one_option` | Tests for dynamic product-option rendering and the no-products routing. | IT4.2 |
| tests/test_application/test_product_options.py | `BuildChoiceOptionsTests::test_seven_found_products_returns_seven_options` | Tests for dynamic product-option rendering and the no-products routing. | IT4.2 |
| tests/test_application/test_product_options.py | `BuildChoiceOptionsTests::test_empty_override_returns_no_options` | Tests for dynamic product-option rendering and the no-products routing. | IT4.2 |
| tests/test_application/test_product_options.py | `BuildChoiceOptionsTests::test_no_override_keeps_all_static_options` | Tests for dynamic product-option rendering and the no-products routing. | IT4.2 |
| tests/test_application/test_product_options.py | `NoProductsRoutingTests::test_no_validaciones_routes_to_satisfaction_check` | Tests for dynamic product-option rendering and the no-products routing. | IT4.2 |
| tests/test_application/test_product_options.py | `NoProductsRoutingTests::test_products_found_keeps_selector_step` | Tests for dynamic product-option rendering and the no-products routing. | IT4.2 |
| tests/test_application/test_product_options.py | `Last4ContratoTests::test_prefiere_el_contrato_sobre_el_key_id` | Guarda de los 4 digitos que ve el cliente. | IT4.2 |
| tests/test_application/test_product_options.py | `Last4ContratoTests::test_cae_al_key_id_cuando_no_hay_contrato` | Guarda de los 4 digitos que ve el cliente. | IT4.2 |
| tests/test_application/test_product_options.py | `Last4ContratoTests::test_ningun_punto_de_centrales_corta_el_key_id` | Ningun sitio de centrales debe volver a cortar product_id/key_id. | IT4.2 |
| tests/test_application/test_qa_routing_cases.py | `GuardrailBankingSignalsTests::test_real_cdt_complaint_is_never_blocked` | El caso exacto que fallo en produccion. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `GuardrailBankingSignalsTests::test_banking_messages_survive_a_wrong_verdict` | El juez de alcance no puede echar a un cliente con un problema real. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `GuardrailBankingSignalsTests::test_accent_insensitive_signals` | El juez de alcance no puede echar a un cliente con un problema real. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `GuardrailBankingSignalsTests::test_amounts_are_a_signal_on_their_own` | El juez de alcance no puede echar a un cliente con un problema real. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `GuardrailBankingSignalsTests::test_off_topic_is_still_blocked` | El juez de alcance no puede echar a un cliente con un problema real. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `GuardrailBankingSignalsTests::test_in_scope_verdict_never_blocks` | El juez de alcance no puede echar a un cliente con un problema real. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `FuzzyFalsePositiveTests::test_content_words_are_not_greetings` | Regresion: la similitud convertia palabras de contenido en saludos. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `FuzzyFalsePositiveTests::test_greeting_typos_still_work` | Regresion: la similitud convertia palabras de contenido en saludos. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `FuzzyFalsePositiveTests::test_greeting_with_content_is_not_a_greeting` | Regresion: la similitud convertia palabras de contenido en saludos. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `BarePqrsRequestTests::test_possessive_pattern` | Meta-peticion sin causal -> se pregunta el motivo, no se tira el formulario. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `BarePqrsRequestTests::test_filing_verbs_still_work` | Meta-peticion sin causal -> se pregunta el motivo, no se tira el formulario. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `BarePqrsRequestTests::test_concrete_reason_goes_to_the_router` | Con causal concreto NO se pregunta el motivo: se rutea. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `UnintelligibleInputTests::test_symbols_and_digits_only` | Entrada sin ninguna palabra interpretable. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `UnintelligibleInputTests::test_short_but_meaningful_is_not_caught` | La longitud NO es el criterio: hay terminos cortos legitimos. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `UnintelligibleInputTests::test_known_alphanumeric_terms_are_protected` | Entrada sin ninguna palabra interpretable. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `UnintelligibleInputTests::test_banking_signal_disables_the_gate` | Entrada sin ninguna palabra interpretable. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_message_is_always_the_fixed_catalog_text` | El LLM NO redacta el mensaje que ve el cliente. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_helper_does_not_receive_the_routing_decision` | Blindaje: la firma no acepta la decision del LLM. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_llm_clarification_message_is_never_used` | Aunque el router lo entregue, no debe aparecer ante el cliente. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_streak_counts_per_conversation` | Estado en captured_data: seguro con usuarios concurrentes. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_first_no_match_still_has_a_retry` | 1er no-match -> pedir aclaracion; 2do consecutivo -> formulario. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_second_no_match_exhausts_the_retry` | 1er no-match -> pedir aclaracion; 2do consecutivo -> formulario. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_reset_clears_the_counter` | 1er no-match -> pedir aclaracion; 2do consecutivo -> formulario. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `ClarificationRetryTests::test_corrupt_counter_is_tolerated` | 1er no-match -> pedir aclaracion; 2do consecutivo -> formulario. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `QaReportedCasesTests::test_greeting_cases_are_answered_with_a_welcome` | Los casos de QA, con el destino que YA no debe ser el formulario directo. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `QaReportedCasesTests::test_gibberish_case_asks_for_clarification` | Los casos de QA, con el destino que YA no debe ser el formulario directo. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `QaReportedCasesTests::test_bare_complaint_asks_for_the_reason` | Los casos de QA, con el destino que YA no debe ser el formulario directo. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `QaReportedCasesTests::test_cases_with_content_reach_the_router_and_keep_a_retry` | Estos dependen del LLM, pero ya no mueren en el primer intento. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `QaReportedCasesTests::test_banking_cases_are_also_protected_from_the_guardrail` | Doble red: si ademas el juez se equivoca, no los puede bloquear. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `QaReportedCasesTests::test_language_request_has_no_banking_signal` | Limite conocido y documentado de la red del guardrail. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `RetryMessageCopyTests::test_retry_pool_is_configured` | El mensaje de reintento debe PEDIR mas detalle, no rechazar el tema. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `RetryMessageCopyTests::test_retry_messages_never_reject_the_topic` | Regresion de copy: el pool viejo decia "ese tema no lo manejo". | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `RetryMessageCopyTests::test_retry_messages_ask_a_question` | El mensaje de reintento debe PEDIR mas detalle, no rechazar el tema. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `RetryMessageCopyTests::test_fallback_cascade` | El mensaje de reintento debe PEDIR mas detalle, no rechazar el tema. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `InjectionFalsePositiveTests::test_real_cdt_complaint_passes_the_input_screen` | El filtro determinista no puede expulsar clientes reales. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `InjectionFalsePositiveTests::test_the_verb_dan_is_not_a_jailbreak` | "dan" es el verbo "dar" en tercera persona, no la sigla DAN. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `InjectionFalsePositiveTests::test_conversational_corrections_are_not_injection` | "olvida lo anterior" es una correccion normal, no un ataque. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `InjectionFalsePositiveTests::test_actua_como_needs_a_persona_object` | El filtro determinista no puede expulsar clientes reales. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `InjectionFalsePositiveTests::test_real_injections_are_still_blocked` | La precision no debilita la defensa. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `InjectionFalsePositiveTests::test_invalid_input_gets_its_own_message` | Un mensaje vacio o muy largo no es un tema "fuera de alcance". | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `InjectionFalsePositiveTests::test_third_party_request_still_blocked` | El filtro determinista no puede expulsar clientes reales. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `NoLlmTextReachesTheClientTests::test_confirmation_message_has_no_llm_parameters` | build_workflow_confirmation_message ya no acepta texto del LLM. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `NoLlmTextReachesTheClientTests::test_confirmation_message_uses_catalog_hints` | Decision de negocio: el cliente solo ve mensajes aprobados. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `NoLlmTextReachesTheClientTests::test_dead_llm_message_builder_is_gone` | _build_default_routing_message concatenaba el rationale del LLM. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `NoLlmTextReachesTheClientTests::test_llm_closure_is_off_by_default` | Decision de negocio: el cliente solo ve mensajes aprobados. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `TantiaItemsAccumulationTests::test_three_transactions_survive_the_per_tx_reset` | Una entrada por transaccion que llega al abono automatico. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `TantiaItemsAccumulationTests::test_reentry_does_not_duplicate_a_row` | Un reintento del paso de abono no puede generar una fila extra. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `TantiaItemsAccumulationTests::test_fingerprint_uses_statement_and_movement` | Una entrada por transaccion que llega al abono automatico. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `TantiaItemsAccumulationTests::test_fingerprint_falls_back_to_tx_id` | Si el ASO no trajo statementDetail, se usa el id del movimiento. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `TantiaItemsAccumulationTests::test_different_transactions_are_not_deduplicated` | Una entrada por transaccion que llega al abono automatico. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `TantiaItemsAccumulationTests::test_state_is_per_conversation` | Sin estado global de proceso: seguro con usuarios concurrentes. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `SelectoresSinDuplicarTests::test_el_mensaje_de_productos_es_una_sola_frase` | El mensaje NO repite lo que ya está en los botones (2026-08-25). | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `SelectoresSinDuplicarTests::test_el_mensaje_de_productos_no_lista_los_productos` | El mensaje NO repite lo que ya está en los botones (2026-08-25). | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `SelectoresSinDuplicarTests::test_los_productos_si_estan_en_los_botones` | Se quitó del mensaje, no del flujo: el cliente debe poder elegir. | IT1.2 |
| tests/test_application/test_qa_routing_cases.py | `SelectoresSinDuplicarTests::test_sirve_para_cualquier_cantidad_de_productos` | El mensaje NO repite lo que ya está en los botones (2026-08-25). | IT1.2 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_accepted` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_rejected` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_expired` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_pending` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_pending_con_plazo_local_vencido` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_servicio_caido_degrada_a_via_directa` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_sin_registro_usa_via_directa` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_autorizacion_fase4.py | `Fase4MapeoTests::test_sin_url_configurada_usa_via_directa` | Fase 4: el gate lee el estado desde co_pqrs_authorization, con fallback. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_canary_gate.py | `PortonCerradoTests::test_op4_no_entra_al_flujo_va_al_formulario` | TRX_FLOW_ENABLED=false y sin token -> siempre formulario. | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `PortonCerradoTests::test_ningun_paso_del_flujo_es_alcanzable` | TRX_FLOW_ENABLED=false y sin token -> siempre formulario. | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `PortonCerradoTests::test_el_menu_sigue_visible` | TRX_FLOW_ENABLED=false y sin token -> siempre formulario. | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `PortonCerradoTests::test_el_nodo_del_formulario_existe_y_ofrece_pqr` | TRX_FLOW_ENABLED=false y sin token -> siempre formulario. | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `TokenDePilotoTests::test_token_valido_habilita_el_flujo_en_esa_conversacion` | Porton de despliegue del flujo TXNR (piloto en produccion). | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `TokenDePilotoTests::test_reconoce_el_token_exacto` | Porton de despliegue del flujo TXNR (piloto en produccion). | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `TokenDePilotoTests::test_token_incorrecto_no_habilita` | Porton de despliegue del flujo TXNR (piloto en produccion). | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `TokenDePilotoTests::test_sin_token_configurado_nada_habilita` | Porton de despliegue del flujo TXNR (piloto en produccion). | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `KillSwitchTests::test_flag_true_abre_el_flujo_a_todos` | Porton de despliegue del flujo TXNR (piloto en produccion). | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `KillSwitchTests::test_default_es_cerrado` | Porton de despliegue del flujo TXNR (piloto en produccion). | IT2.6 |
| tests/test_application/test_trx_canary_gate.py | `KillSwitchTests::test_valores_aceptados_del_flag` | Porton de despliegue del flujo TXNR (piloto en produccion). | IT2.6 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_entry_step_has_four_events` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_options_1_2_3_offer_pqrs_form_and_route_to_satisfaction` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_option_4_enters_recurrence_step` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_recurrence_redirect_step_shows_dedicated_message` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_count_to_onebyone_to_confirmation` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_more_than_three_routes_to_pqr` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_confirmation_yes_goes_to_products_gate` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_confirmation_finalizar_goes_to_satisfaction` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_confirmacion_permite_volver_al_listado` | 2.4.0.1.11 ofrece volver al selector (2.4.0.1.9) si el cliente eligio | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_value_in_range_goes_to_date_and_out_of_range_to_pqr` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_block_routing_is_semantic` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `TrxFlowTests::test_full_happy_path_loops_back_to_confirmation` | Routing a nivel de workflow_engine (los ACTION auto-route se prueban en chat_service). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_visa_179_pasa` | Fronteras exactas de la ventana de contracargo (VISA 180 / MASTER 120). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_visa_180_exactos_pasan` | El limite es inclusivo: la comparacion es `dias > limite`. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_visa_181_vence` | Fronteras exactas de la ventana de contracargo (VISA 180 / MASTER 120). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_master_119_pasa` | Fronteras exactas de la ventana de contracargo (VISA 180 / MASTER 120). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_master_120_exactos_pasan` | Fronteras exactas de la ventana de contracargo (VISA 180 / MASTER 120). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_master_121_vence` | Fronteras exactas de la ventana de contracargo (VISA 180 / MASTER 120). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_banda_diferencial_150_dias` | El caso que ensena la diferencia: mismo dia, distinta marca. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_master_se_reconoce_por_subcadena` | Fronteras exactas de la ventana de contracargo (VISA 180 / MASTER 120). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `VigenciaFronterasTests::test_marca_desconocida_recibe_hoy_el_plazo_largo` | Documenta el hueco abierto: lo que no dice MASTER cae en el else. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `MensajesDinamicosDegradacionTests::test_selector_sin_last_four_no_expone_el_contrato` | Con el dato ausente, ningun mensaje dinamico expone un crudo. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `MensajesDinamicosDegradacionTests::test_selector_usa_last_four_y_no_el_identificador` | Con el dato ausente, ningun mensaje dinamico expone un crudo. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `MensajesDinamicosDegradacionTests::test_fecha_iso_se_muestra_en_ddmmaaaa` | Con el dato ausente, ningun mensaje dinamico expone un crudo. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `MensajesDinamicosDegradacionTests::test_fecha_en_otro_formato_se_deja_intacta` | No se inventa una conversion sobre algo que no es ISO. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `FechasAceptadasTests::test_formatos_aceptados` | Tolerante al recibir, estricto al pedir (peticion de negocio 18/08). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `FechasAceptadasTests::test_el_dia_va_primero_no_hay_ambiguedad` | Tolerante al recibir, estricto al pedir (peticion de negocio 18/08). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `FechasAceptadasTests::test_fecha_futura_se_rechaza` | Una compra no puede ser de manana: antes se aceptaba y el cliente | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `FechasAceptadasTests::test_hoy_se_acepta` | Tolerante al recibir, estricto al pedir (peticion de negocio 18/08). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `FechasAceptadasTests::test_basura_se_rechaza` | Tolerante al recibir, estricto al pedir (peticion de negocio 18/08). | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `UltimosCuatroDesdeFinancialOverviewTests::test_el_pan_reescribe_los_ultimos_cuatro` | Los 4 digitos que ve el cliente son los del PAN, no los del contrato. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `UltimosCuatroDesdeFinancialOverviewTests::test_sin_pan_se_conserva_el_dato_de_ada` | Fail-open: si financial-overview no responde, mejor el dato de ADA | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `UltimosCuatroDesdeFinancialOverviewTests::test_el_selector_nunca_muestra_el_contrato` | Los 4 digitos que ve el cliente son los del PAN, no los del contrato. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `SelectorDeMovimientosTests::test_pagina_uno_muestra_cinco_y_ver_mas` | Selector de movimientos (04/09): el servicio pagina y el agente PINTA. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `SelectorDeMovimientosTests::test_pagina_intermedia_lleva_anterior_y_ver_mas` | Selector de movimientos (04/09): el servicio pagina y el agente PINTA. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `SelectorDeMovimientosTests::test_ultima_pagina_con_anterior_sin_ver_mas` | Selector de movimientos (04/09): el servicio pagina y el agente PINTA. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `SelectorDeMovimientosTests::test_seleccion_posicional_mapea_al_id_de_la_pagina` | Selector de movimientos (04/09): el servicio pagina y el agente PINTA. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `SelectorDeMovimientosTests::test_la_salida_existe_con_cualquier_pagina` | Selector de movimientos (04/09): el servicio pagina y el agente PINTA. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_flow.py | `SelectorDeMovimientosTests::test_pagina_unica_no_menciona_tramo_ni_navegacion` | Selector de movimientos (04/09): el servicio pagina y el agente PINTA. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxPendienteGateTests::test_pendiente_tdc_routes_to_exit` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxPendienteGateTests::test_not_pendiente_routes_to_investigar` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxValidacionesGateTests::test_presencial` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxValidacionesGateTests::test_reversado` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxValidacionesGateTests::test_pqr` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxValidacionesGateTests::test_devolucion` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxValidacionesGateTests::test_unknown_defaults_to_devolucion` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxLoopGateTests::test_last_tx_closes` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxLoopGateTests::test_single_tx_skips_close_message` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxLoopGateTests::test_pending_tx_keeps_loop_node` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxVigenciaTests::test_old_date_visa_vencida` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxVigenciaTests::test_today_is_vigente` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxVigenciaTests::test_invalid_date_not_vencida` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxLoopHandlerTests::test_si_siguiente_advances_index_and_resets` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxLoopHandlerTests::test_confirm_data_step_initializes_index_once` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxProductosGateTests::test_not_found_va_al_exit` | Gate 2.4.0.1.4: sin productos de Postgres NUNCA hay mocks; se sale por el exit. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxProductosGateTests::test_error_de_db_va_al_error_sin_mocks` | Gate 2.4.0.1.4: sin productos de Postgres NUNCA hay mocks; se sale por el exit. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxProductosGateTests::test_back_trx_sin_respuesta_va_al_error_no_al_exit` | Gate 2.4.0.1.4: sin productos de Postgres NUNCA hay mocks; se sale por el exit. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxProductosGateTests::test_con_productos_reales_va_al_selector` | Gate 2.4.0.1.4: sin productos de Postgres NUNCA hay mocks; se sale por el exit. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxProductosGateTests::test_nunca_aparecen_mocks_4979_4567` | Gate 2.4.0.1.4: sin productos de Postgres NUNCA hay mocks; se sale por el exit. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxNavegacionPaginasGateTests::test_ver_mas_pide_la_pagina_siguiente_y_reencamina` | Gate 2.4.0.1.9.nav (04/09): pide la pagina al servicio y reencamina a .9. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxNavegacionPaginasGateTests::test_anterior_pide_la_pagina_previa` | Gate 2.4.0.1.9.nav (04/09): pide la pagina al servicio y reencamina a .9. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxNavegacionPaginasGateTests::test_no_pasa_de_la_ultima_pagina` | Gate 2.4.0.1.9.nav (04/09): pide la pagina al servicio y reencamina a .9. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_orchestration.py | `TrxNavegacionPaginasGateTests::test_fallo_al_navegar_conserva_pagina_y_vuelve_al_selector` | Gate 2.4.0.1.9.nav (04/09): pide la pagina al servicio y reencamina a .9. | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_state.py | `TrxStateTests::test_get_crea_estado_vacio` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_state.py | `TrxStateTests::test_update_merge` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_state.py | `TrxStateTests::test_reset_per_tx_conserva_globales` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_trx_state.py | `TrxStateTests::test_snapshot_es_copia` |  | IT4.2, IT4.5, IT4.7 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_notificacion_fase1_sin_reporte_muestra_mensaje_generico` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_notificacion_fase1_con_reporte_lista_productos` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_notificacion_producto_renders_msg16_without_optional_fields` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_notificacion_producto_replaces_optional_fields_when_present` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_notificacion_producto_supports_nested_payload_shape` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_notificacion_producto_rejects_unexpected_message_ids` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_execute_workflow_action_dispatches_notification_handler` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_consulta_sin_permiso_supports_flat_payload_with_id_msg_14` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_consulta_sin_permiso_flat_payload_does_not_fallback_to_id_15` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_id_msg_12_renders_valor_pago_without_placeholder` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_id_msg_11_renders_every_lifted_embargo` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_trx_product_selector_builds_dynamic_options` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_trx_movements_render_as_single_select_buttons` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_trx_movement_confirmation_shows_selected_detail` |  | IT4.2 |
| tests/test_application/test_workflow_actions.py | `WorkflowActionsTests::test_trx_no_movements_offers_pqrs` |  | IT4.2 |
| tests/test_domain/test_catalog_negatives.py | `CatalogBlockNegativesTests::test_centrales_no_usar_excludes_product_block` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `CatalogBlockNegativesTests::test_centrales_contraejemplos_include_block_and_salary` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `CatalogBlockNegativesTests::test_centrales_no_usar_excludes_transaction_and_scopes_desembargo` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `CatalogBlockNegativesTests::test_centrales_examples_include_desembargo` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `CatalogBlockNegativesTests::test_centrales_contraejemplos_include_freeze_and_certification` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `CatalogBlockNegativesTests::test_embargada_no_usar_excludes_full_product_block` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `RoutingPromptFewShotTests::test_has_greeting_and_block_few_shots` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `RoutingPromptFewShotTests::test_greeting_few_shot_uses_canonical_welcome` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `RoutingPromptFewShotTests::test_has_freeze_and_embargo_state_few_shots` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_catalog_negatives.py | `RoutingPromptFewShotTests::test_output_rules_prioritize_action_over_theme` | Regresion de contenido del catalogo de ruteo (negativos de bloqueo y few_shots). | - |
| tests/test_domain/test_conversation_models.py | `ConversationMaintenanceFieldsTests::test_deserializes_document_touched_by_maintenance` | Tests for Conversation tolerance of maintenance-written fields. | - |
| tests/test_domain/test_conversation_models.py | `ConversationMaintenanceFieldsTests::test_round_trips_maintenance_fields_on_dump` | Tests for Conversation tolerance of maintenance-written fields. | - |
| tests/test_domain/test_conversation_models.py | `ConversationMaintenanceFieldsTests::test_document_without_maintenance_fields_still_valid` | Tests for Conversation tolerance of maintenance-written fields. | - |
| tests/test_domain/test_conversation_models.py | `ConversationMaintenanceFieldsTests::test_truly_unknown_field_is_still_rejected` | Tests for Conversation tolerance of maintenance-written fields. | - |
| tests/test_domain/test_style_lint.py | `CheckTextTests::test_clean_tuteo_passes` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CheckTextTests::test_usted_pronoun_is_flagged` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CheckTextTests::test_usted_imperative_is_flagged` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CheckTextTests::test_usted_possessive_is_flagged` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CheckTextTests::test_third_person_subjunctive_is_not_usted` | "que un equipo revise tu caso" es subjuntivo, no usted. | - |
| tests/test_domain/test_style_lint.py | `CheckTextTests::test_mixed_tone_still_flags_the_usted_half` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CheckPromiseTests::test_promise_allowed_in_confirmation_terminals` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CheckPromiseTests::test_promise_outside_confirmation_is_flagged` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CheckPromiseTests::test_neutral_text_never_flags` | Lint de estilo (capa C4): tuteo consistente y promesas controladas. | - |
| tests/test_domain/test_style_lint.py | `CorpusGateTests::test_all_workflow_copy_is_clean` | Gate de regresion: todo el copy visible tutea y no promete de mas. | - |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_every_yaml_action_is_in_the_allowlist` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_every_class_is_known_and_effect_actions_are_few` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_effect_actions_never_start_a_flow` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_all_paths_to_effect_actions_cross_their_gates` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_code_never_jumps_directly_into_an_effect_step` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_refund_only_after_the_customer_confirms_and_the_rules_pass` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_blocks_require_app_authorization_step` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_catalogo_capacidades.py | `test_published_catalog_is_up_to_date` | Contrato del catalogo de capacidades (KYNS IT 4). | IT4.2 |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelMatchingTests::test_casa_por_la_etiqueta_visible` | Tests for matching a choice option by the label the customer actually sees. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelMatchingTests::test_ignora_acentos_y_mayusculas` | Tests for matching a choice option by the label the customer actually sees. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelMatchingTests::test_la_key_sigue_funcionando` | La UI manda la key; no puede dejar de valer. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelMatchingTests::test_la_etiqueta_del_yaml_sigue_funcionando` | Tests for matching a choice option by the label the customer actually sees. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelMatchingTests::test_una_etiqueta_ajena_no_casa` | Tests for matching a choice option by the label the customer actually sees. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelMatchingTests::test_sin_etiquetas_dinamicas_se_comporta_como_antes` | Tests for matching a choice option by the label the customer actually sees. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelReadingTests::test_sin_dato` | El lector no puede romper el turno por un dato mal guardado. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelReadingTests::test_json_ilegible` | El lector no puede romper el turno por un dato mal guardado. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelReadingTests::test_json_que_no_es_lista` | El lector no puede romper el turno por un dato mal guardado. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionLabelReadingTests::test_lista_valida` | El lector no puede romper el turno por un dato mal guardado. | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionKeysRoutingTests::test_no_encuentro_desplazado_rutea_a_su_destino` | Paginacion (03/09): el destino lo manda la key DINAMICA cuando coincide | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionKeysRoutingTests::test_movimiento_absoluto_conserva_su_key` | Paginacion (03/09): el destino lo manda la key DINAMICA cuando coincide | - |
| tests/test_domain/test_workflow/test_dynamic_option_labels.py | `DynamicOptionKeysRoutingTests::test_por_numero_tambien_lleva_la_key_absoluta` | Paginacion (03/09): el destino lo manda la key DINAMICA cuando coincide | - |
| tests/test_domain/test_workflow/test_general_messages.py | `GeneralMessagesLoaderTests::test_loads_new_formal_limit_messages` | Tests for the shared general message catalog loader. | - |
| tests/test_domain/test_workflow/test_general_messages.py | `GeneralMessagesLoaderTests::test_existing_repeated_flow_messages_are_preserved` | Tests for the shared general message catalog loader. | - |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitCategoryMappingTests::test_centrales_group_maps_to_centrales` | Tests for the data-driven daily-interaction limit category mapping. | IT4.6 |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitCategoryMappingTests::test_faq_workflow_maps_to_general` | Tests for the data-driven daily-interaction limit category mapping. | IT4.6 |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitCategoryMappingTests::test_guia_rapida_workflow_maps_to_general` | Tests for the data-driven daily-interaction limit category mapping. | IT4.6 |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitCategoryMappingTests::test_hazlo_tu_mismo_workflow_maps_to_general` | Tests for the data-driven daily-interaction limit category mapping. | IT4.6 |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitCategoryMappingTests::test_unknown_workflow_falls_back_to_general` | Tests for the data-driven daily-interaction limit category mapping. | IT4.6 |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitKeyPerCaseTests::test_key_is_the_workflow_name` | The per-CASE limit key is the workflow itself (not the shared group | IT4.6 |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitKeyPerCaseTests::test_two_cases_of_same_group_have_distinct_keys` | The per-CASE limit key is the workflow itself (not the shared group | IT4.6 |
| tests/test_domain/test_workflow/test_limit_category.py | `LimitKeyPerCaseTests::test_unknown_workflow_falls_back` | The per-CASE limit key is the workflow itself (not the shared group | IT4.6 |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingCatalogTests::test_catalog_has_all_workflows` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingCatalogTests::test_trx_no_reconocida_group_and_limit_category` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingCatalogTests::test_new_disambiguation_fields_are_populated` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingCatalogTests::test_centrales_examples_cover_removal_intent` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingCatalogTests::test_datacredito_removal_is_not_a_paz_y_salvo_example` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingCatalogTests::test_contraejemplos_reference_existing_workflows` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingCatalogTests::test_every_group_has_routing_criteria` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingPromptBuilderTests::test_system_prompt_has_persona_and_fewshots` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingPromptBuilderTests::test_system_prompt_drops_buggy_hardcoded_line` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_domain/test_workflow/test_routing_catalog.py | `RoutingPromptBuilderTests::test_user_prompt_includes_groups_workflows_and_negatives` | Routing catalog and data-driven routing prompt tests (LLM-free). | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `EscrituraAntigua::test_recurrente_de_agosto_perdia_el_sobre` | El fallo tal y como ocurria. Documenta por que hubo que cambiarlo. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `EscrituraAntigua::test_sin_historial_del_workflow_usaba_el_mes_de_la_ultima_visita` | El fallo tal y como ocurria. Documenta por que hubo que cambiarlo. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `EscrituraAntigua::test_documento_inexistente_daba_404` | El fallo tal y como ocurria. Documenta por que hubo que cambiarlo. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C2EscrituraEnElMesEnCurso::test_recurrente_de_agosto` | El sobre cae siempre donde el agente lo busca. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C2EscrituraEnElMesEnCurso::test_sin_historial_del_workflow` | El sobre cae siempre donde el agente lo busca. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C2EscrituraEnElMesEnCurso::test_no_pisa_el_contador_del_mes_en_curso` | El sobre convive con ``count``/``label`` que escribe el agente. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C4LimitacionDocumentoInexistente::test_documento_inexistente_falla` | Limitacion CONOCIDA: si el documento no existe, la escritura falla. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C4LimitacionDocumentoInexistente::test_con_documento_existente_funciona` | Limitacion CONOCIDA: si el documento no existe, la escritura falla. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C3LecturaToleranteAlMes::test_acepta_el_sobre_de_otro_mes_si_el_run_id_casa` | El agente acepta otro mes SOLO con el run_id correcto. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C3LecturaToleranteAlMes::test_rechaza_el_sobre_de_otro_mes_con_run_id_distinto` | El agente acepta otro mes SOLO con el run_id correcto. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C3LecturaToleranteAlMes::test_sin_run_id_esperado_no_amplia_la_busqueda` | La seguridad depende del run_id: sin el, no se mira otro mes. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C3LecturaToleranteAlMes::test_el_mes_en_curso_tiene_prioridad` | El agente acepta otro mes SOLO con el run_id correcto. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C5LimpiezaEfectiva::test_anula_data_y_run_id_pese_al_merge_recursivo` | La limpieza previa al disparo tiene que borrar de verdad. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `C5LimpiezaEfectiva::test_tras_limpiar_el_lector_no_sirve_el_dato_viejo` | La limpieza previa al disparo tiene que borrar de verdad. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `F0Diagnostico::test_resume_los_meses_y_los_estados` | La traza de timeout tiene que permitir diagnosticar sin entrar a produccion. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `F0Diagnostico::test_no_filtra_datos_de_negocio` | La traza de timeout tiene que permitir diagnosticar sin entrar a produccion. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `F0Diagnostico::test_documento_inexistente` | La traza de timeout tiene que permitir diagnosticar sin entrar a produccion. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `GuardasDelScriptPainless::test_no_vuelve_el_bucle_de_meses` | Si el painless vuelve a cambiar, estas pruebas avisan. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `GuardasDelScriptPainless::test_no_vuelve_la_rama_de_last_interaction_at` | Si el painless vuelve a cambiar, estas pruebas avisan. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `GuardasDelScriptPainless::test_escribe_en_el_periodo_recibido` | Si el painless vuelve a cambiar, estas pruebas avisan. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `GuardasDelScriptPainless::test_no_declara_scripted_upsert` | C4 se revirtio el 02/09: en produccion daba 400 en TODAS las escrituras. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `GuardasDelScriptPainless::test_la_traza_de_error_lleva_el_cuerpo` | El 400 dejo la traza sin motivo; el cuerpo tiene que viajar en ella. | - |
| tests/test_infrastructure/test_control_table_month_bucket.py | `GuardasDelScriptPainless::test_el_mes_destino_viaja_en_la_traza` | Si el painless vuelve a cambiar, estas pruebas avisan. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `TemplateProtegeElEsquema::test_las_ramas_por_fecha_no_se_indexan` | El molde con el que nace un indice nuevo no puede repetir el fallo. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `TemplateProtegeElEsquema::test_ninguna_rama_por_fecha_queda_con_enabled_true` | 'enabled: true' sin 'dynamic: false' era el estado que fallo. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `TemplateProtegeElEsquema::test_declara_un_techo_de_campos_holgado` | El molde con el que nace un indice nuevo no puede repetir el fallo. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `TemplateProtegeElEsquema::test_los_data_blob_siguen_desactivados` | La proteccion de los 'data' es anterior y no debe perderse. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `TemplateProtegeElEsquema::test_el_desplegable_de_saneo_existe` | El template solo cubre indices nuevos; uno existente se sanea aparte. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `FalloDeEscrituraDejaTraza::test_emite_traza_con_el_cuerpo_del_error` | El motivo del fallo tiene que salir del pod y llegar a la auditoria. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `FalloDeEscrituraDejaTraza::test_funciona_sin_respuesta_http` | Un fallo de red no trae respuesta: la traza se emite igual. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `FalloDeEscrituraDejaTraza::test_nunca_propaga_una_excepcion` | Fail-open: la observabilidad no puede tumbar el turno del cliente. | - |
| tests/test_infrastructure/test_control_table_schema_guards.py | `FalloDeEscrituraDejaTraza::test_los_cuatro_puntos_de_fallo_estan_cableados` | Si aparece un quinto punto que se traga el fallo, esto avisa. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxDailySessionsConfigTests::test_defaults_to_three_when_unset` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxDailySessionsConfigTests::test_reads_override_from_environment` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxDailySessionsConfigTests::test_invalid_value_falls_back_to_default` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxDailySessionsConfigTests::test_non_positive_value_falls_back_to_default` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxDailyCategoryInteractionsConfigTests::test_defaults_to_three_when_unset` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxDailyCategoryInteractionsConfigTests::test_reads_override_from_environment` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxDailyCategoryInteractionsConfigTests::test_invalid_value_falls_back_to_default` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxRepeatRechecksConfigTests::test_defaults_to_three_when_unset` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxRepeatRechecksConfigTests::test_reads_override_from_environment` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `MaxRepeatRechecksConfigTests::test_non_positive_value_falls_back_to_default` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `EndConversationCallbackUrlConfigTests::test_returns_none_when_unset` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_core/test_config.py | `EndConversationCallbackUrlConfigTests::test_reads_maintenance_url_from_environment` | Unit tests for environment configuration loaders. | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiValidationResponseTests::test_start_now_requires_user_id` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiValidationResponseTests::test_request_validation_returns_406` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiValidationResponseTests::test_openapi_documents_406_instead_of_422` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiValidationResponseTests::test_openapi_documents_message_shape_for_start_and_chat` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiValidationResponseTests::test_openapi_documents_polling_and_input_type_enum_without_confirm` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `StartResumeKeepsOptionsTests::test_start_envelope_admite_opciones` | POST /start sobre una sesion en curso devuelve los botones del paso. | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `StartResumeKeepsOptionsTests::test_saludo_inicial_sigue_sin_opciones` | POST /start sobre una sesion en curso devuelve los botones del paso. | - |
| tests/test_infrastructure/test_entrypoint/test_input_hardening.py | `ContentMaxLengthTests::test_chat_content_within_limit_ok` | Tests for input hardening: 1000-char cap, friendly message, log excerpt. | - |
| tests/test_infrastructure/test_entrypoint/test_input_hardening.py | `ContentMaxLengthTests::test_chat_content_over_limit_rejected` | Tests for input hardening: 1000-char cap, friendly message, log excerpt. | - |
| tests/test_infrastructure/test_entrypoint/test_input_hardening.py | `ContentMaxLengthTests::test_start_content_over_limit_rejected` | Tests for input hardening: 1000-char cap, friendly message, log excerpt. | - |
| tests/test_infrastructure/test_entrypoint/test_input_hardening.py | `TooLongDetectionTests::test_handler_detects_content_too_long` | Tests for input hardening: 1000-char cap, friendly message, log excerpt. | - |
| tests/test_infrastructure/test_entrypoint/test_input_hardening.py | `TooLongDetectionTests::test_handler_ignores_other_validation_errors` | Tests for input hardening: 1000-char cap, friendly message, log excerpt. | - |
| tests/test_infrastructure/test_entrypoint/test_input_hardening.py | `SafeExcerptTests::test_truncates_to_limit_and_strips_newlines` | Tests for input hardening: 1000-char cap, friendly message, log excerpt. | - |
| tests/test_infrastructure/test_entrypoint/test_input_hardening.py | `SafeExcerptTests::test_handles_none_and_empty` | Tests for input hardening: 1000-char cap, friendly message, log excerpt. | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `MiddlewareAuditTests::test_error_response_is_audited` | Tests for the global HTTP middleware error auditing (E2E coverage). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `MiddlewareAuditTests::test_success_is_not_audited` | Tests for the global HTTP middleware error auditing (E2E coverage). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `MiddlewareAuditTests::test_validation_406_is_skipped_by_middleware` | Tests for the global HTTP middleware error auditing (E2E coverage). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `MiddlewareAuditTests::test_unhandled_exception_is_audited_and_reraised` | Tests for the global HTTP middleware error auditing (E2E coverage). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `MiddlewareAuditTests::test_excluded_path_not_audited` | Tests for the global HTTP middleware error auditing (E2E coverage). | - |
| tests/test_infrastructure/test_entrypoint/test_pqr_form_button.py | `PqrFormButtonTests::test_signal_emits_pqr_button_and_no_link` | El formulario PQRS se envía como botón {key:"pqr", label:"Formulario PQR"}. | - |
| tests/test_infrastructure/test_entrypoint/test_pqr_form_button.py | `PqrFormButtonTests::test_signal_resolves_choice_input_type` | El formulario PQRS se envía como botón {key:"pqr", label:"Formulario PQR"}. | - |
| tests/test_infrastructure/test_entrypoint/test_pqr_form_button.py | `PqrFormButtonTests::test_pqr_selection_routes_to_satisfaction` | El formulario PQRS se envía como botón {key:"pqr", label:"Formulario PQR"}. | - |
| tests/test_infrastructure/test_entrypoint/test_pqrs_not_button.py | `PqrsNotButtonTests::test_pqrs_form_option_is_not_a_button` | Item 4: the PQRS form must NOT be rendered as a button, only inline in text. | - |
| tests/test_infrastructure/test_genai/test_llm/test_fallback_routing.py | `FallbackRoutingTests::test_pure_greeting_returns_warm_welcome_not_cold_error` | Tests del ruteo local de respaldo (cuando el LLM remoto no esta disponible). | - |
| tests/test_infrastructure/test_genai/test_llm/test_fallback_routing.py | `FallbackRoutingTests::test_greeting_phrase_returns_warm_welcome` | Tests del ruteo local de respaldo (cuando el LLM remoto no esta disponible). | - |
| tests/test_infrastructure/test_genai/test_llm/test_fallback_routing.py | `FallbackRoutingTests::test_off_topic_returns_warm_scope_message_not_match` | Tests del ruteo local de respaldo (cuando el LLM remoto no esta disponible). | - |
| tests/test_infrastructure/test_genai/test_llm/test_fallback_routing.py | `FallbackRoutingTests::test_clear_request_still_matches_workflow` | Tests del ruteo local de respaldo (cuando el LLM remoto no esta disponible). | - |
| tests/test_infrastructure/test_persistence/test_authorization_client.py | `AuthorizationClientTests::test_registrar_devuelve_el_cuerpo` | Adapter Agent -> Authorization (punto 15 del pliego): fail-open y contrato. | - |
| tests/test_infrastructure/test_persistence/test_authorization_client.py | `AuthorizationClientTests::test_registrar_fail_open` | Adapter Agent -> Authorization (punto 15 del pliego): fail-open y contrato. | - |
| tests/test_infrastructure/test_persistence/test_authorization_client.py | `AuthorizationClientTests::test_consultar_devuelve_estado` | Adapter Agent -> Authorization (punto 15 del pliego): fail-open y contrato. | - |
| tests/test_infrastructure/test_persistence/test_authorization_client.py | `AuthorizationClientTests::test_sin_base_url_no_llama` | Adapter Agent -> Authorization (punto 15 del pliego): fail-open y contrato. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `WorkflowEnvelopeTests::test_envelope_ok_returns_data` | Tests for the back-data freshness envelope (status + run_id) on the agent side. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `WorkflowEnvelopeTests::test_envelope_error_has_no_data` | Tests for the back-data freshness envelope (status + run_id) on the agent side. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `WorkflowEnvelopeTests::test_clear_sets_pending_and_drops_data_and_run_id` | Tests for the back-data freshness envelope (status + run_id) on the agent side. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `PollFreshnessTests::test_ok_with_matching_run_id_returns_ok` | Tests for the back-data freshness envelope (status + run_id) on the agent side. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `PollFreshnessTests::test_error_envelope_returns_error` | Tests for the back-data freshness envelope (status + run_id) on the agent side. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `PollFreshnessTests::test_stale_run_id_is_rejected_as_timeout` | Tests for the back-data freshness envelope (status + run_id) on the agent side. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `TimeoutLlevaDiagnosticoTests::test_el_timeout_emite_el_diagnostico` | Fase 0: el timeout tiene que dejar el diagnostico EN LA TRAZA. | - |
| tests/test_infrastructure/test_persistence/test_back_data_envelope.py | `TimeoutLlevaDiagnosticoTests::test_si_el_diagnostico_falla_el_turno_no_se_rompe` | Fail-open: la observabilidad nunca puede tumbar el turno. | - |
| tests/test_infrastructure/test_persistence/test_back_data_trace.py | `BackDataClientTraceTests::test_customer_name_success_emits_ok_trace` | Tests for trace emission in the agent -> back_data client. | - |
| tests/test_infrastructure/test_persistence/test_back_data_trace.py | `BackDataClientTraceTests::test_customer_name_failure_emits_error_trace_and_fails_open` | Tests for trace emission in the agent -> back_data client. | - |
| tests/test_infrastructure/test_persistence/test_back_data_trace.py | `BackDataClientTraceTests::test_trigger_consultar_emits_ok_trace` | Tests for trace emission in the agent -> back_data client. | - |
| tests/test_infrastructure/test_persistence/test_back_data_trace.py | `BackDataClientTraceTests::test_trigger_failure_emits_error_trace_and_swallows` | Tests for trace emission in the agent -> back_data client. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `CategoryCounterTests::test_category_count_increments` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `CategoryCounterTests::test_categories_are_isolated` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `CategoryCounterTests::test_category_count_isolated_per_day` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `CategoryCounterTests::test_last_flow_label_stored_per_category` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `CategoryCounterTests::test_missing_record_returns_zero_and_none` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `CategoryCounterTests::test_category_recording_does_not_touch_daily_sessions` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `RecheckCounterTests::test_recheck_increments` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `RecheckCounterTests::test_recheck_isolated_per_day` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_category_counters.py | `RecheckCounterTests::test_missing_record_returns_zero` | Unit tests for per-category daily counters and recheck counters. | - |
| tests/test_infrastructure/test_persistence/test_control_table_store.py | `DailySessionCounterTests::test_first_session_start_sets_count_to_one` | Unit tests for the daily session counter in ControlTableStore. | - |
| tests/test_infrastructure/test_persistence/test_control_table_store.py | `DailySessionCounterTests::test_successive_starts_increment_same_day` | Unit tests for the daily session counter in ControlTableStore. | - |
| tests/test_infrastructure/test_persistence/test_control_table_store.py | `DailySessionCounterTests::test_counter_resets_on_a_new_day` | Unit tests for the daily session counter in ControlTableStore. | - |
| tests/test_infrastructure/test_persistence/test_control_table_store.py | `DailySessionCounterTests::test_missing_record_returns_zero` | Unit tests for the daily session counter in ControlTableStore. | - |
| tests/test_infrastructure/test_persistence/test_control_table_store.py | `DailySessionCounterTests::test_expired_record_is_not_counted` | Unit tests for the daily session counter in ControlTableStore. | - |
| tests/test_infrastructure/test_persistence/test_maintenance_client.py | `ResolveArchiveUrlTests::test_templated_url_is_filled_with_conversation_id` | Unit tests for the maintenance archive HTTP client. | - |
| tests/test_infrastructure/test_persistence/test_maintenance_client.py | `ResolveArchiveUrlTests::test_plain_base_url_appends_end_path` | Unit tests for the maintenance archive HTTP client. | - |
| tests/test_infrastructure/test_persistence/test_maintenance_client.py | `TriggerArchiveConversationTests::test_posts_to_resolved_maintenance_url` | Unit tests for the maintenance archive HTTP client. | - |
| tests/test_infrastructure/test_persistence/test_maintenance_client.py | `TriggerArchiveConversationTests::test_errors_are_swallowed` | Unit tests for the maintenance archive HTTP client. | - |
| tests/test_infrastructure/test_persistence/test_trx_case_store.py | `TrxCaseStoreTests::test_record_entered_op4_agrega_entry` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_case_store.py | `TrxCaseStoreTests::test_bot_recurrence_fuera_de_ventana_no_cuenta` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_case_store.py | `TrxCaseStoreTests::test_milestones_no_se_duplican_y_guarda_snapshot` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_case_store.py | `TrxCaseStoreTests::test_get_case_sin_ttl` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `TrxClientTests::test_consultar_trx_returns_body_on_success` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `TrxClientTests::test_consultar_productos_activos_returns_body_on_success` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `TrxClientTests::test_consultar_trx_fail_open_returns_none` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `TrxClientTests::test_analizar_fail_open_returns_none` |  | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `EstadoRetoNormalizacionTests::test_sobre_ok_con_pending_no_es_aceptado` | El sobre del servicio TXNR trae status="ok" (resultado del REQUEST): | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `EstadoRetoNormalizacionTests::test_sobre_ok_sin_estado_pero_pendiente_es_pending` | El sobre del servicio TXNR trae status="ok" (resultado del REQUEST): | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `EstadoRetoNormalizacionTests::test_sobre_ok_aceptado_true_es_accepted` | El sobre del servicio TXNR trae status="ok" (resultado del REQUEST): | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `EstadoRetoNormalizacionTests::test_forma_cruda_del_aso_sigue_funcionando` | El sobre del servicio TXNR trae status="ok" (resultado del REQUEST): | - |
| tests/test_infrastructure/test_persistence/test_trx_client.py | `EstadoRetoNormalizacionTests::test_rechazado_y_expirado_del_servicio` | El sobre del servicio TXNR trae status="ok" (resultado del REQUEST): | - |
| tests/test_request_log_capture.py | `RequestLogCaptureTests::test_capture_masks_pii_and_counts_lines` | Tests for the per-request full log capturer (buffer + masking + caps). | - |
| tests/test_request_log_capture.py | `RequestLogCaptureTests::test_line_cap_marks_truncated` | Tests for the per-request full log capturer (buffer + masking + caps). | - |
| tests/test_request_log_capture.py | `RequestLogCaptureTests::test_disabled_is_noop` | Tests for the per-request full log capturer (buffer + masking + caps). | - |

### co_pqrs_benchmark

| Fichero | Test | Qué demuestra | Controles |
|---|---|---|---|
| tests/test_adversarial.py | `test_legacy_case_behaves_like_before` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_blocked_or_derived_are_both_accepted` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_pending_outcome_can_be_accepted` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_other_outcome_counts_as_matched_when_flow_was_entered` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_forbidden_workflow_fails_even_if_otherwise_accepted` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_forbidden_step_fails_as_step` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_leak_is_detected_in_any_turn_and_in_option_labels` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_leak_is_case_insensitive_and_beats_a_correct_routing` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_leak_has_priority_over_step_and_step_over_workflow` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_case_with_only_prohibitions_passes_when_none_is_violated` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_shipped_adversarial_datasets_validate_clean` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_adversarial.py | `test_adversarial_dataset_covers_the_six_control_categories` | Evaluacion de los datasets adversariales y de bypass (sin agente ni LLM). | IT1.4, IT3.4, IT3.5, IT4.3 |
| tests/test_dataset_configmap.py | `test_configmap_matches_every_dataset` | El ConfigMap del dataset en IaC debe ser copia exacta del dataset versionado. | IT1.2 |
| tests/test_dataset_configmap.py | `test_configmap_file_is_up_to_date` | El ConfigMap del dataset en IaC debe ser copia exacta del dataset versionado. | IT1.2 |
| tests/test_dataset_trx_no_reconocida.py | `test_dataset_validates_clean_and_has_enough_cases` | El dataset de ruteo de trx_no_reconocida esta bien formado y cubre sus vecinos. | IT1.2 |
| tests/test_dataset_trx_no_reconocida.py | `test_every_declared_neighbour_has_a_boundary_case` | El dataset de ruteo de trx_no_reconocida esta bien formado y cubre sus vecinos. | IT1.2 |
| tests/test_dataset_trx_no_reconocida.py | `test_sanity_cases_are_literal_catalog_examples` | El dataset de ruteo de trx_no_reconocida esta bien formado y cubre sus vecinos. | IT1.2 |
| tests/test_dataset_trx_no_reconocida.py | `test_disambiguation_cases_carry_a_follow_up` | El dataset de ruteo de trx_no_reconocida esta bien formado y cubre sus vecinos. | IT1.2 |
| tests/test_events.py | `test_flow_from_source` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_run_context_defaults_and_run_id` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_run_context_honours_run_name_and_source` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_case_event_has_exact_contract_fields` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_case_event_fail_kind` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_case_event_unresolved_has_null_fail_kind` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_case_event_rejects_unknown_fail_kind` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_run_event_has_exact_contract_fields` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_run_event_timestamp_defaults_to_now` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_run_event_empty_run` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_effective_url_matches_agent_format` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_publish_connection_refused_does_not_raise` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_publish_disabled_is_inert` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_exchange_declaration_and_message_match_agent` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_publish_failure_resets_connection_and_retries` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_events.py | `test_benchmark_source_is_validated` | Un typo en el manifiesto no puede producir eventos que nadie vea. | IT1.2, IT2.3 |
| tests/test_events.py | `test_breaker_resets_after_a_successful_publish` | Mapeo NDJSON -> benchmark.case, resumen -> benchmark.run, y publicador fail-open. | IT1.2, IT2.3 |
| tests/test_grounding.py | `test_new_kinds_are_registered` | Grounding: lo que el bot dice tiene que salir de su fuente, y lo que la fuente exige tiene que estar. | IT1.3 |
| tests/test_grounding.py | `test_greeting_is_part_of_what_is_checked` | Grounding: lo que el bot dice tiene que salir de su fuente, y lo que la fuente exige tiene que estar. | IT1.3 |
| tests/test_grounding.py | `test_invented_beats_step_and_grounding_comes_after_routing` | Grounding: lo que el bot dice tiene que salir de su fuente, y lo que la fuente exige tiene que estar. | IT1.3 |
| tests/test_grounding.py | `test_leak_still_has_the_highest_priority` | Grounding: lo que el bot dice tiene que salir de su fuente, y lo que la fuente exige tiene que estar. | IT1.3 |
| tests/test_grounding.py | `test_prohibitions_only_case_still_needs_the_required_content` | Grounding: lo que el bot dice tiene que salir de su fuente, y lo que la fuente exige tiene que estar. | IT1.3 |
| tests/test_grounding.py | `test_shipped_grounding_dataset_validates_and_covers_the_four_points` | Grounding: lo que el bot dice tiene que salir de su fuente, y lo que la fuente exige tiene que estar. | IT1.3 |
| tests/test_job_events.py | `test_case_events_mirror_ndjson_and_evaluation` | El job publica benchmark.case con la MISMA evaluacion que su precision, | IT1.2, IT2.3 |
| tests/test_job_events.py | `test_job_survives_unreachable_rabbitmq` | El job publica benchmark.case con la MISMA evaluacion que su precision, | IT1.2, IT2.3 |
| tests/test_job_events.py | `test_publisher_none_keeps_legacy_behaviour` | El job publica benchmark.case con la MISMA evaluacion que su precision, | IT1.2, IT2.3 |
| tests/test_job_events.py | `test_benchmark_header_on_start_chat_and_end` | El job publica benchmark.case con la MISMA evaluacion que su precision, | IT1.2, IT2.3 |
| tests/test_job_events.py | `test_end_failure_does_not_break_case` | El job publica benchmark.case con la MISMA evaluacion que su precision, | IT1.2, IT2.3 |
| tests/test_release_card.py | `test_card_has_every_block_and_the_core_services` | La ficha de version reune imagenes, configuracion, conocimiento y datasets del repo. | IT1.6, IT2.2 |
| tests/test_release_card.py | `test_card_reads_model_and_gates_from_the_dev_configmap` | La ficha de version reune imagenes, configuracion, conocimiento y datasets del repo. | IT1.6, IT2.2 |
| tests/test_release_card.py | `test_card_fingerprints_knowledge_and_datasets` | La ficha de version reune imagenes, configuracion, conocimiento y datasets del repo. | IT1.6, IT2.2 |
| tests/test_release_card.py | `test_render_is_markdown_with_the_commit_in_the_title` | La ficha de version reune imagenes, configuracion, conocimiento y datasets del repo. | IT1.6, IT2.2 |
| tests/test_release_card.py | `test_card_reads_the_real_suspend_flag_not_a_comment` | La ficha de version reune imagenes, configuracion, conocimiento y datasets del repo. | IT1.6, IT2.2 |

### co_pqrs_back_trx_noreconocida

| Fichero | Test | Qué demuestra | Controles |
|---|---|---|---|
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_movimientos_visa_dentro_de_vigencia_lista` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_movimientos_fecha_vencida_visa` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_movimientos_sin_datos_en_la_fecha` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_movimientos_fecha_invalida` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_valor_menor_a_35000_redirige_pqr` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_valor_en_rango_aprobado` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_valor_mayor_a_500000_redirige_pqr` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_recurrencia_mock_file_tiene_default` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_recurrencia_reciente_redirige_pqr` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_recurrencia_antigua_no_redirige` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service.py | `TrxFase1Tests::test_recurrencia_sin_subject_txnr_no_redirige` | Fase 1: movimientos mock por producto+fecha, vigencia y regla de valor. | - |
| tests/test_application/test_analysis_service_fo.py | `test_fo_ok_devuelve_las_tarjetas_del_json_real` | Rama TRX_PRODUCTS_SOURCE=fo de consultar_productos_activos (F2, 24/08). | - |
| tests/test_application/test_analysis_service_fo.py | `test_fo_caido_es_fail_closed` | Rama TRX_PRODUCTS_SOURCE=fo de consultar_productos_activos (F2, 24/08). | - |
| tests/test_application/test_analysis_service_fo.py | `test_fo_sin_tarjetas_es_not_found` | Rama TRX_PRODUCTS_SOURCE=fo de consultar_productos_activos (F2, 24/08). | - |
| tests/test_application/test_analysis_service_fo.py | `test_solo_fo_no_toca_postgres_y_sin_direccion` | solo-FO v3 (24/08): Postgres NO se consulta y customer_address ya no | - |
| tests/test_application/test_analysis_service_fo.py | `test_el_defecto_de_configuracion_es_fo` | Sin variable de entorno, la fuente es fo (solo-FO). | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaTests::test_recurrencia_subject_reciente` |  | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaTests::test_recurrencia_solo_antiguo_no_dispara` |  | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaTests::test_recurrencia_sin_subject_txnr` |  | - |
| tests/test_application/test_aso_rules.py | `CardIdTests::test_extraer_card_id_por_ultimos4` |  | - |
| tests/test_application/test_aso_rules.py | `CardIdTests::test_extraer_card_id_no_match` |  | - |
| tests/test_application/test_aso_rules.py | `MovimientosTests::test_parse_desde_operations` | Listado de movimientos desde /cards/v2/operations (cambio 2026-08-25). | - |
| tests/test_application/test_aso_rules.py | `MovimientosTests::test_incluye_el_detalle_para_mostrarlo` | 2.4.0.1.9 muestra el detalle: debe venir en el mismo listado. | - |
| tests/test_application/test_aso_rules.py | `MovimientosTests::test_payload_vacio` | Listado de movimientos desde /cards/v2/operations (cambio 2026-08-25). | - |
| tests/test_application/test_aso_rules.py | `MovimientosTests::test_tolera_campos_ausentes` | Un movimiento incompleto se muestra, no desaparece del listado. | - |
| tests/test_application/test_aso_rules.py | `FiltroDeRangoTests::test_filtra_por_rango` | El filtro de importe se aplica en nuestro codigo: operations no lo acepta. | - |
| tests/test_application/test_aso_rules.py | `FiltroDeRangoTests::test_cuenta_los_que_quedan_fuera` | Quien busca su compra de 750.000 no puede recibir "no hay compras". | - |
| tests/test_application/test_aso_rules.py | `FiltroDeRangoTests::test_sin_rango_devuelve_todo` | El filtro de importe se aplica en nuestro codigo: operations no lo acepta. | - |
| tests/test_application/test_aso_rules.py | `FiltroDeRangoTests::test_movimiento_sin_importe_se_conserva` | Sin importe no se puede excluir con criterio. | - |
| tests/test_application/test_aso_rules.py | `DetalleYClasificacionTests::test_detalle_match_por_id` |  | - |
| tests/test_application/test_aso_rules.py | `DetalleYClasificacionTests::test_clasificacion_devolucion` |  | - |
| tests/test_application/test_aso_rules.py | `DetalleYClasificacionTests::test_clasificacion_pqr_eci_no_permitido` |  | - |
| tests/test_application/test_aso_rules.py | `DetalleYClasificacionTests::test_clasificacion_presencial_eci_9` |  | - |
| tests/test_application/test_aso_rules.py | `DetalleYClasificacionTests::test_clasificacion_reversado` |  | - |
| tests/test_application/test_aso_rules.py | `DetalleYClasificacionTests::test_clasificacion_pqr_eci_vacio` |  | - |
| tests/test_application/test_aso_rules.py | `DetalleYClasificacionTests::test_pendiente_tdc` |  | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_filtra_por_estado_origin_y_card_flag` |  | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_sin_productos_validos` |  | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_acepta_estado_activo` | El valor real de produccion. | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_vigente_ya_no_entra` | Criterio 24/08: solo ACTIVO. VIGENTE era un artefacto de los seeds. | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_estado_es_insensible_a_mayusculas_y_espacios` |  | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_card_type_d_y_m_entran_p_y_a_no` | Cuarto eslabon de la cadena: card_type en {D, M}. | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_pasivo_ya_no_entra` | Criterio 24/08: solo origin_flag=TDC (las cuentas quedan fuera). | - |
| tests/test_application/test_aso_rules.py | `ProductosTests::test_otros_estados_siguen_excluidos` |  | - |
| tests/test_application/test_aso_rules.py | `ClientesPruebaRealTests::test_98787954_devolucion` | Clientes de prueba reales del usuario: verifica desenlace por card_id/last4. | - |
| tests/test_application/test_aso_rules.py | `ClientesPruebaRealTests::test_10482895_presencial` | Clientes de prueba reales del usuario: verifica desenlace por card_id/last4. | - |
| tests/test_application/test_aso_rules.py | `ClientesPruebaRealTests::test_eci_contracargables_del_tablero` | El tablero fija: contracargables 0,1,2,3,7 -> devolucion. | - |
| tests/test_application/test_aso_rules.py | `ClientesPruebaRealTests::test_01576905_devolucion` | ECI 1 es contracargable -> devolucion automatica. | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaViaAsoTests::test_fuente_aso_consulta_la_costura` | TRX_SALESFORCE_SOURCE=aso consulta la costura; si falla, cae al mock local. | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaViaAsoTests::test_costura_caida_cae_al_mock_local_sin_romper` | TRX_SALESFORCE_SOURCE=aso consulta la costura; si falla, cae al mock local. | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaViaAsoTests::test_sin_identidad_en_postgres_no_toca_la_costura_y_avisa` | TRX_SALESFORCE_SOURCE=aso consulta la costura; si falla, cae al mock local. | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaViaAsoTests::test_fuente_mock_no_toca_la_costura` | TRX_SALESFORCE_SOURCE=aso consulta la costura; si falla, cae al mock local. | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaViaAsoTests::test_tsec_reportado_es_el_que_se_uso` | tsec_requested tiene que reflejar el ticket REAL de la llamada. | - |
| tests/test_application/test_aso_rules.py | `RecurrenciaViaAsoTests::test_sin_tsec_el_campo_sigue_en_false` | TRX_SALESFORCE_SOURCE=aso consulta la costura; si falla, cae al mock local. | - |
| tests/test_application/test_aso_rules.py | `CacheOperacionesTests::test_misma_tarjeta_y_fecha_llama_una_sola_vez` | El detalle del dia se pide una vez, no una por movimiento elegido. | - |
| tests/test_application/test_aso_rules.py | `CacheOperacionesTests::test_otra_fecha_vuelve_a_consultar` | El detalle del dia se pide una vez, no una por movimiento elegido. | - |
| tests/test_application/test_aso_rules.py | `CacheOperacionesTests::test_otra_tarjeta_vuelve_a_consultar` | El detalle del dia se pide una vez, no una por movimiento elegido. | - |
| tests/test_application/test_aso_rules.py | `CacheOperacionesTests::test_una_respuesta_vacia_del_aso_no_se_cachea` | None es fallo, no dato: cachearlo perpetuaria una caida transitoria. | - |
| tests/test_application/test_aso_rules.py | `ExtraerCardIdPrefiereFormatsTests::test_match_por_number_devuelve_el_pan_de_formats` | Fix 31/08 (tercera copia de la asuncion 'el id ES el PAN'): al localizar | - |
| tests/test_application/test_aso_rules.py | `ExtraerCardIdPrefiereFormatsTests::test_sin_formats_devuelve_el_id_como_antes` | Fix 31/08 (tercera copia de la asuncion 'el id ES el PAN'): al localizar | - |
| tests/test_application/test_descripcion_comercio.py | `test_payload_real_muestra_el_comercio` | Descripcion del listado = el COMERCIO, no el estado (Fabian, 27/08). | - |
| tests/test_application/test_descripcion_comercio.py | `test_sin_bloques_cae_a_la_cascada_clasica` | Descripcion del listado = el COMERCIO, no el estado (Fabian, 27/08). | - |
| tests/test_application/test_descripcion_comercio.py | `test_bloque_de_comercio_vacio_tambien_cae_al_respaldo` | Descripcion del listado = el COMERCIO, no el estado (Fabian, 27/08). | - |
| tests/test_application/test_descripcion_comercio.py | `test_observaciones_crudas_se_conservan_para_la_clasificacion` | Descripcion del listado = el COMERCIO, no el estado (Fabian, 27/08). | - |
| tests/test_application/test_no_mock_guardrail.py | `ProductosSinFallbackMockTests::test_postgres_sin_filas_devuelve_not_found_sin_mocks` | Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados. | IT1.4, IT3.5 |
| tests/test_application/test_no_mock_guardrail.py | `ProductosSinFallbackMockTests::test_postgres_error_devuelve_error_no_not_found` | Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados. | IT1.4, IT3.5 |
| tests/test_application/test_no_mock_guardrail.py | `ProductosSinFallbackMockTests::test_nunca_aparecen_las_tarjetas_mock_4979_4567` | Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados. | IT1.4, IT3.5 |
| tests/test_application/test_no_mock_guardrail.py | `ProductosSinFallbackMockTests::test_postgres_con_filas_reales_las_devuelve` | Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados. | IT1.4, IT3.5 |
| tests/test_application/test_no_mock_guardrail.py | `ProductosSinFallbackMockTests::test_source_mock_con_mocks_deshabilitados_da_error` | Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados. | IT1.4, IT3.5 |
| tests/test_application/test_no_mock_guardrail.py | `RecurrenciaRealTests::test_usa_aso_real_no_el_mock` | Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados. | IT1.4, IT3.5 |
| tests/test_application/test_no_mock_guardrail.py | `RecurrenciaRealTests::test_aso_caido_devuelve_error_no_asume_sin_recurrencia` | Guardrail: con Postgres/ASO REALES nunca se devuelven datos mockeados. | IT1.4, IT3.5 |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_primera_pagina_llena` |  | - |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_pagina_intermedia` |  | - |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_ultima_pagina_parcial` |  | - |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_page_sobre_total_se_acota_a_la_ultima` |  | - |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_page_menor_que_uno_se_acota_a_uno` |  | - |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_dia_vacio` |  | - |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_page_size_invalido_cae_a_cinco` |  | - |
| tests/test_application/test_paginar_movimientos.py | `PaginarMovimientosTests::test_setenta_movimientos_catorce_paginas` |  | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_json_real_de_nicolas_da_sus_dos_tarjetas` | Productos TXNR desde el financial-overview (roadmap PO, 24/08). | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_debito_y_credito_bien_clasificadas` | Productos TXNR desde el financial-overview (roadmap PO, 24/08). | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_franquicia_derivada_del_nombre` | Productos TXNR desde el financial-overview (roadmap PO, 24/08). | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_cuentas_prestamos_y_fondos_quedan_fuera` | El fixture trae ACCOUNT/LOAN/INVESTMENT_FUND: ninguno pasa. | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_contrato_del_selector_v4` | v4 (Fabian 24/08): card_id (es el PAN), sin origin_flag ni | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_agreement_contract_solo_lo_trae_la_debito` | En el JSON real de Nicolas: la DEBITO trae agreementContract (vino | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_last_four_sale_de_number_pan` | Productos TXNR desde el financial-overview (roadmap PO, 24/08). | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_tarjeta_no_operativa_queda_fuera` | Productos TXNR desde el financial-overview (roadmap PO, 24/08). | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_indicador_blockable_inactivo_excluye` | Productos TXNR desde el financial-overview (roadmap PO, 24/08). | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_fo_vacio_o_none_da_lista_vacia` | Productos TXNR desde el financial-overview (roadmap PO, 24/08). | - |
| tests/test_application/test_productos_desde_fo.py | `ProductosDesdeFoTests::test_acepta_forma_con_data_contracts` | El fixture es la raiz; el aso_client podria envolver en data. | - |
| tests/test_application/test_productos_desde_fo.py | `FranquiciaPorBinTests::test_bin_4_es_visa_aunque_el_nombre_no_lo_diga` | H1 (24/08): la franquicia sale del primer digito del PAN; el nombre es | - |
| tests/test_application/test_productos_desde_fo.py | `FranquiciaPorBinTests::test_bin_5_es_master` | H1 (24/08): la franquicia sale del primer digito del PAN; el nombre es | - |
| tests/test_application/test_productos_desde_fo.py | `FranquiciaPorBinTests::test_bin_2_es_master_serie_2017` | H1 (24/08): la franquicia sale del primer digito del PAN; el nombre es | - |
| tests/test_application/test_productos_desde_fo.py | `FranquiciaPorBinTests::test_bin_gana_al_nombre_cuando_contradicen` | El PAN es la fuente fiable; el nombre comercial puede mentir. | - |
| tests/test_application/test_productos_desde_fo.py | `FranquiciaPorBinTests::test_pan_enmascarado_cae_al_nombre` | El JSON de Nicolas venia con '********': respaldo por nombre. | - |
| tests/test_application/test_productos_desde_fo.py | `FranquiciaPorBinTests::test_sin_pan_ni_nombre_reconocible_queda_vacia` | Nada de adivinar: vacia, y el consumidor decide (hoy el agente | - |
| tests/test_application/test_productos_desde_fo.py | `FranquiciaPorBinTests::test_las_tarjetas_reales_de_nicolas_siguen_visa` | H1 (24/08): la franquicia sale del primer digito del PAN; el nombre es | - |
| tests/test_application/test_productos_desde_fo.py | `PanDesdeFormatsTests::test_card_id_es_el_pan_de_formats` | Fix H-1 (31/08): con la forma REAL del ASO de DEV, card_id es el PAN de | - |
| tests/test_application/test_productos_desde_fo.py | `PanDesdeFormatsTests::test_franquicia_por_bin_revive_con_el_pan` | Fix H-1 (31/08): con la forma REAL del ASO de DEV, card_id es el PAN de | - |
| tests/test_application/test_productos_desde_fo.py | `PanDesdeFormatsTests::test_sin_formats_cae_al_id_como_antes` | Fix H-1 (31/08): con la forma REAL del ASO de DEV, card_id es el PAN de | - |
| tests/test_application/test_productos_desde_fo.py | `PanDesdeFormatsTests::test_formats_sin_pan_no_inventa` | Fix H-1 (31/08): con la forma REAL del ASO de DEV, card_id es el PAN de | - |
| tests/test_application/test_productos_desde_fo.py | `PanValidadoRobustoTests::test_prd_id_es_el_pan_sin_formats` | Fix 02/09 (peticion de Fabian): no confiar ciegamente en formats. | - |
| tests/test_application/test_productos_desde_fo.py | `PanValidadoRobustoTests::test_dev_token_en_id_pan_en_formats` | Fix 02/09 (peticion de Fabian): no confiar ciegamente en formats. | - |
| tests/test_application/test_productos_desde_fo.py | `PanValidadoRobustoTests::test_formats_enmascarado_cae_al_id_pan` | Fix 02/09 (peticion de Fabian): no confiar ciegamente en formats. | - |
| tests/test_application/test_productos_desde_fo.py | `PanValidadoRobustoTests::test_formats_con_ultimos4_cae_al_id_pan` | Fix 02/09 (peticion de Fabian): no confiar ciegamente en formats. | - |
| tests/test_infrastructure/test_aso_client_204.py | `test_204_sin_cuerpo_es_dict_vacio_sin_excepcion` | Semantica del rework: {} = "sin datos" (NO None = fallo). | - |
| tests/test_infrastructure/test_aso_client_204.py | `test_200_con_cuerpo_vacio_tambien_es_dict_vacio` | Manejo del 204/2xx sin cuerpo del ASO (incidente DEV 25/08 + rework 26/08). | - |
| tests/test_infrastructure/test_aso_client_204.py | `test_200_con_json_sigue_funcionando` | Manejo del 204/2xx sin cuerpo del ASO (incidente DEV 25/08 + rework 26/08). | - |
| tests/test_infrastructure/test_aso_client_204.py | `test_tsec_en_cabecera_como_siempre` | Manejo del 204/2xx sin cuerpo del ASO (incidente DEV 25/08 + rework 26/08). | - |
| tests/test_infrastructure/test_aso_client_204.py | `test_tsec_en_el_cuerpo_como_centrales` | El granting de dev puede devolver el ticket en el cuerpo (la | - |
| tests/test_infrastructure/test_aso_client_204.py | `test_cabecera_gana_al_cuerpo` | Manejo del 204/2xx sin cuerpo del ASO (incidente DEV 25/08 + rework 26/08). | - |
| tests/test_infrastructure/test_aso_client_fo_respaldo.py | `test_solo_customer_id_aunque_llegue_contrato` | El contract_id de los llamadores NO viaja al ASO. | - |
| tests/test_infrastructure/test_aso_client_fo_respaldo.py | `test_solo_customer_id_sin_contrato` | financial-overview: SOLO ``customer.id`` (decision de Fabian, 24/08). | - |
| tests/test_infrastructure/test_aso_client_fo_respaldo.py | `test_sin_filtro_cards` | Tampoco viaja contracts.productType=CARDS (se trae TODO el financial). | - |
| tests/test_infrastructure/test_aso_client_fo_respaldo.py | `test_fallo_sigue_fail_closed` | Si la unica llamada falla -> None: el .4.error honesto se conserva. | - |
| tests/test_infrastructure/test_aso_client_operations_paginado.py | `OperationsPaginadoTests::test_acumula_las_tres_paginas` | operations() debe recorrer TODAS las paginas del ASO y acumularlas: un dia | - |
| tests/test_infrastructure/test_aso_client_operations_paginado.py | `OperationsPaginadoTests::test_una_sola_pagina_no_pide_mas` | operations() debe recorrer TODAS las paginas del ASO y acumularlas: un dia | - |
| tests/test_infrastructure/test_aso_client_operations_paginado.py | `OperationsPaginadoTests::test_fallo_a_mitad_devuelve_lo_acumulado` | operations() debe recorrer TODAS las paginas del ASO y acumularlas: un dia | - |
| tests/test_infrastructure/test_aso_client_trazas_sin_secretos.py | `test_granting_password_is_masked_even_with_the_old_full_flag` | Ninguna credencial ni PAN en claro en lo que el cliente del ASO manda a las trazas. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_client_trazas_sin_secretos.py | `test_tsec_never_leaves_the_emitter_even_with_the_old_full_flag` | Ninguna credencial ni PAN en claro en lo que el cliente del ASO manda a las trazas. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_client_trazas_sin_secretos.py | `test_request_debug_strips_tsec_header_and_masks_password` | Ninguna credencial ni PAN en claro en lo que el cliente del ASO manda a las trazas. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_client_trazas_sin_secretos.py | `test_full_body_in_e2e_debug_is_masked` | Ninguna credencial ni PAN en claro en lo que el cliente del ASO manda a las trazas. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `TsecDebugTests::test_reports_when_the_token_was_not_sent` | Hoy una llamada sin tsec sale SIN autenticar y hay que verlo. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `TsecDebugTests::test_fingerprint_lets_you_compare_tokens_without_exposing_them` | Debug completo de las llamadas ASO (peticion + respuesta). | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `TsecDebugTests::test_suffix_shows_the_base64_padding` | El '==' final era la sospecha: el sufijo permite verificarlo. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `TsecDebugTests::test_full_value_never_appears_even_with_the_old_flag` | KYNS IT 3: el TSEC completo ya no sale a las trazas bajo ningun flag. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `TsecDebugTests::test_same_token_produces_the_same_fingerprint` | Asi se comprueba que el ASO 2 recibio el token del grantingTicket. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `RequestDebugTests::test_get_records_method_url_params_and_headers` | Debug completo de las llamadas ASO (peticion + respuesta). | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `RequestDebugTests::test_full_url_includes_the_query_string` | Para poder reproducir la llamada exacta con curl. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `RequestDebugTests::test_tsec_is_not_left_inside_the_plain_headers` | Se extrae para tratarlo aparte, no se duplica en `headers`. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `RequestDebugTests::test_post_body_is_recorded` | Debug completo de las llamadas ASO (peticion + respuesta). | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `PasswordMaskingTests::test_password_is_masked_by_default` | La contrasena del grantingTicket es una credencial PERMANENTE. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `PasswordMaskingTests::test_the_rest_of_the_payload_survives` | La contrasena del grantingTicket es una credencial PERMANENTE. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `PasswordMaskingTests::test_original_payload_is_not_mutated` | La contrasena del grantingTicket es una credencial PERMANENTE. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `PasswordMaskingTests::test_password_is_masked_even_with_the_old_full_flag` | KYNS IT 3: la contrasena del granting nunca viaja en claro a la traza. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `ChainIdTests::test_each_client_has_its_own_chain_id` | Correlaciona el grantingTicket con los ASO que usaron ese token. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_aso_debug.py | `ChainIdTests::test_chain_id_is_stable_within_a_client` | Correlaciona el grantingTicket con los ASO que usaron ese token. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_health_check_returns_ok` |  | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina.py | `MovimientosPaginaTests::test_primera_pagina` |  | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina.py | `MovimientosPaginaTests::test_ultima_pagina` |  | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina.py | `MovimientosPaginaTests::test_fallo_aso_es_fail_closed` |  | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina.py | `MovimientosPaginaTests::test_dia_vacio_no_es_error` |  | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina.py | `MovimientosPaginaTests::test_page_cero_rechazado_por_validacion` |  | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina_e2e.py | `MovimientosPaginaE2ETests::test_setenta_movimientos_catorce_paginas` | Fase 3: integracion del endpoint paginado sobre el fixture real de 70 | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina_e2e.py | `MovimientosPaginaE2ETests::test_ultima_pagina` | Fase 3: integracion del endpoint paginado sobre el fixture real de 70 | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina_e2e.py | `MovimientosPaginaE2ETests::test_paginas_no_se_solapan_y_los_id_son_estables` | Fase 3: integracion del endpoint paginado sobre el fixture real de 70 | - |
| tests/test_infrastructure/test_entrypoint/test_movimientos_pagina_e2e.py | `MovimientosPaginaE2ETests::test_ida_y_vuelta_devuelve_los_mismos_id` | Fase 3: integracion del endpoint paginado sobre el fixture real de 70 | - |
| tests/test_infrastructure/test_subida_nivel.py | `UserStatusTests::test_toma_el_primer_dispositivo_activo` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `UserStatusTests::test_dispositivo_bloqueado_no_sirve` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `SubidaNivelTests::test_camino_feliz_envia_el_push` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `SubidaNivelTests::test_sin_dispositivo_no_intenta_el_reto` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `SubidaNivelTests::test_tipo_de_autenticacion_inesperado_corta` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `SubidaNivelTests::test_authentication_data_del_push` | Paso 3: sin authenticationstate y con los campos fijos del contrato. | - |
| tests/test_infrastructure/test_subida_nivel.py | `SubidaNivelTests::test_limpia_sufijos_del_challenge` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `SubidaNivelTests::test_limpia_dos_puntos_del_challenge_como_contingencia` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `EstadoAutorizacionTests::test_aceptado` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `EstadoAutorizacionTests::test_approved_tambien_es_aceptado` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `EstadoAutorizacionTests::test_pendiente_consulta_una_sola_vez` | Sin sondeo interno: una consulta por peticion, aunque pidan mas. | - |
| tests/test_infrastructure/test_subida_nivel.py | `EstadoAutorizacionTests::test_el_sondeo_esta_acotado` | No puede exceder el presupuesto de 10 s del agente. | - |
| tests/test_infrastructure/test_subida_nivel.py | `TemporalNoCancelaTests::test_temporal_nunca_llama_a_operations` | El bloqueo temporal NUNCA debe ejecutar el POST que cancela la tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `TemporalNoCancelaTests::test_temporal_ignora_la_autorizacion_si_llega` | Aunque le pasen el reto, el temporal sigue siendo un PATCH. | - |
| tests/test_infrastructure/test_subida_nivel.py | `PermanenteExigeAutorizacionTests::test_con_autorizacion_ejecuta` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `PermanenteExigeAutorizacionTests::test_sin_autorizacion_no_toca_el_aso` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `PermanenteExigeAutorizacionTests::test_cliente_rechaza_devuelve_400` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `PermanenteExigeAutorizacionTests::test_authentication_data_del_paso_final` | Paso 5: el estado viaja en header y los datos empiezan con deviceId. | - |
| tests/test_infrastructure/test_subida_nivel.py | `TipoInvalidoTests::test_tipo_desconocido_no_hace_nada` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `TxnrIdentityEndpointTests::test_identity_by_card_expone_solo_la_identidad_necesaria` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |
| tests/test_infrastructure/test_subida_nivel.py | `TxnrIdentityEndpointTests::test_customer_address_se_resuelve_fuera_del_event_loop` | Subida de nivel: notificacion push previa al bloqueo de tarjeta. | - |

### co_pqrs_back_doble_cobro

| Fichero | Test | Qué demuestra | Controles |
|---|---|---|---|
| tests/test_aso_client.py | `AsoSettingsTests::test_verify_ssl_is_read_from_the_environment` | El ASO real usa certificado corporativo: hay que poder desactivarlo. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoSettingsTests::test_verify_ssl_defaults_to_true` | Sin configurar se verifica: desactivarlo tiene que ser deliberado. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoSettingsTests::test_timeout_is_read_from_the_environment` | Configuracion del cliente ASO y manejo del TSEC. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoSettingsTests::test_a_broken_timeout_falls_back_instead_of_crashing` | Configuracion del cliente ASO y manejo del TSEC. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoSettingsTests::test_the_client_applies_both_to_its_http_client` | Que las settings existan no basta: tienen que llegar a httpx. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoBaseUrlTests::test_source_real_uses_the_real_url` | Configuracion del cliente ASO y manejo del TSEC. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoBaseUrlTests::test_source_simulator_uses_the_simulator_url` | Configuracion del cliente ASO y manejo del TSEC. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoBaseUrlTests::test_the_manual_override_wins_over_the_switch` | Documenta la trampa: con DC_ASO_BASE_URL puesta, ASO_SOURCE no hace nada. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `TsecDebugTests::test_a_missing_tsec_says_the_request_goes_unauthenticated` | Configuracion del cliente ASO y manejo del TSEC. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `TsecDebugTests::test_the_fingerprint_never_leaks_the_token` | Configuracion del cliente ASO y manejo del TSEC. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `TsecDebugTests::test_the_full_token_never_appears_even_behind_the_old_flag` | KYNS IT 3: la huella basta para correlacionar; el token completo no se persiste. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `AsoRequestTraceTests::test_a_request_without_tsec_is_still_traced` | Sin token es justo cuando hace falta la traza, y era la que faltaba. | IT3.2, IT3.6, IT3.7 |
| tests/test_aso_client.py | `TsecFailureTests::test_a_failed_granting_ticket_returns_empty_and_never_raises` | El fail-open es deliberado, pero deja rastro en el log. | IT3.2, IT3.6, IT3.7 |
| tests/test_doble_cobro.py | `test_colombia_tiene_dieciocho_festivos` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_festivos_no_son_habiles` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_fin_de_semana_no_es_habil` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_conteo_de_habiles_salta_festivos_y_fines_de_semana` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_fecha_futura_no_acumula_habiles` | Una fecha futura nunca debe aparentar haber cumplido el plazo. | - |
| tests/test_doble_cobro.py | `test_normalize_merchant_ignora_tildes_y_puntuacion` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_filtro_por_monto_aplica_tolerancia` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_agrupa_mismo_comercio_mismo_monto_mismo_dia` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_agrupa_aunque_pasen_horas_entre_los_cobros` | La hora no interviene: el comercio puede reprocesar el cobro mucho después. | - |
| tests/test_doble_cobro.py | `test_no_agrupa_fechas_distintas` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_no_agrupa_distinto_comercio` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_no_agrupa_montos_distintos_aunque_esten_cerca` | Al agrupar el monto debe ser idéntico: la tolerancia es solo de búsqueda. | - |
| tests/test_doble_cobro.py | `test_agrupa_sin_hora_si_hay_fecha` | ``hourOperation`` puede faltar en el ASO real; la fecha basta. | - |
| tests/test_doble_cobro.py | `test_descarta_movimientos_sin_fecha` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_health_check` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_vigencia_dentro_de_la_ventana_de_conciliacion` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_vigencia_usa_siete_dias_para_todos_los_productos` | Cuentas y tarjetas débito comparten la misma ventana de conciliación. | - |
| tests/test_doble_cobro.py | `test_conciliacion_se_cumple_al_septimo_dia_habil` | El limite son 7 dias habiles: al sexto aun no se reclama, al septimo si. | - |
| tests/test_doble_cobro.py | `test_vigencia_de_franquicia_en_compras_nacionales` | VISA reclama hasta 180 dias y MASTER hasta 120, sin distinguir ambito. | - |
| tests/test_doble_cobro.py | `test_marca_no_reconocida_recibe_el_plazo_mas_largo` | AMEX, Diners o un dato incompleto reciben los 180 dias de VISA. | - |
| tests/test_doble_cobro.py | `test_la_franquicia_no_aplica_a_las_cuentas` | Una cuenta no tiene marca: a los 181 dias sigue siendo reclamable. | - |
| tests/test_doble_cobro.py | `test_vigencia_rechaza_mas_de_seis_meses` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_vigencia_con_fecha_ilegible` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_parse_date_acepta_los_formatos_del_chat` | Pruebas del flujo doble_cobro: reglas de negocio y contrato HTTP. | - |
| tests/test_doble_cobro.py | `test_parse_date_rechaza_lo_demas_y_el_gate_cae_a_revision` | Una fecha no interpretable termina en outcome=error: el agente la | - |

### co_pqrs_back_data

| Fichero | Test | Qué demuestra | Controles |
|---|---|---|---|
| tests/test_application/test_back_data_error_envelope.py | `ErrorEnvelopeTests::test_aso_error_writes_error_envelope_without_data` | Tests: back_data ALWAYS records a control-table envelope, incl. on ASO error. | - |
| tests/test_application/test_back_data_error_envelope.py | `ErrorEnvelopeTests::test_dem_error_writes_error_envelope_without_no_embargo_data` | Tests: back_data ALWAYS records a control-table envelope, incl. on ASO error. | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_normalize_key_id_casts_to_string_and_trims_outer_zeroes` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_consultar_customer_returns_selected_data_from_commercial_info` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_consultar_customer_raises_when_customer_id_does_not_exist` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_consultar_customer_propagates_when_dem_repository_fails` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_notificacion_centrales_returns_validaciones_por_producto` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_notificacion_centrales_data_is_the_business_editing_point` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_notificacion_producto_data_matches_key_id_with_outer_zeroes` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_data_from_customer_df_and_centrales_is_the_editing_point` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_data_from_customer_df_and_centrales_matches_key_id_with_outer_zeroes` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_data_from_customer_df_and_centrales_uses_vector_for_gt_120` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_embargo_in_bbva_and_centrales_returns_only_id_msg_12` | DEM A y centrales activas producen id_msg=12, sin blocking_type. | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_centrales_acemb_and_inemb_are_normalized_as_embargo` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_dem_empty_with_central_embargo_returns_id_msg_13` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_dem_no_concluyente_without_central_returns_id_msg_1` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_dem_embargo_without_central_returns_id_msg_13` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_embargo_case_24_lifted_in_dem_returns_id_msg_11` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_dem_desembargo_with_central_embargo_returns_id_msg_13` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_dem_no_concluyente_without_central_returns_id_msg_1_even_with_blocking_type` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_data_matches_customer_id_without_left_zeroes` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_consultar_data_uses_table_and_json_mapping` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_centrales_no_autorizo_data_returns_false` |  | - |
| tests/test_application/test_consultar_service.py | `ConsultarServiceTests::test_build_centrales_no_autorizo_data_returns_true_with_date` |  | - |
| tests/test_application/test_consultar_service.py | `GetCustomerDisplayNameTests::test_returns_given_names_without_surnames` |  | - |
| tests/test_application/test_consultar_service.py | `GetCustomerDisplayNameTests::test_returns_empty_when_no_rows` |  | - |
| tests/test_application/test_env_flags.py | `E2EFlagFromEnvFileTests::test_reads_true_from_env_constants_without_os_getenv` | Guard: E2E_DEBUG_TRACE must be read from the .env constants (load_env_constants), | - |
| tests/test_application/test_env_flags.py | `E2EFlagFromEnvFileTests::test_reads_false_from_env_constants` | Guard: E2E_DEBUG_TRACE must be read from the .env constants (load_env_constants), | - |
| tests/test_application/test_env_flags.py | `E2EFlagFromEnvFileTests::test_missing_defaults_false` | Guard: E2E_DEBUG_TRACE must be read from the .env constants (load_env_constants), | - |
| tests/test_application/test_hoja5_castigo_mora.py | `test_hoja5_activo_castigo_mora_id_msg` | Matriz de comportamiento esperado (Hoja 5 - E2E CENTRALES DE RIESGO). | - |
| tests/test_application/test_notificacion_producto.py | `NotificacionProductoTests::test_adelanto_nomina_va_a_pqrs_17_aunque_haya_extracto` | Tests de la FASE 2 del flujo 3 (notificación): análisis del producto elegido. | - |
| tests/test_application/test_notificacion_producto.py | `NotificacionProductoTests::test_sin_extracto_va_a_pqrs_17` | Tests de la FASE 2 del flujo 3 (notificación): análisis del producto elegido. | - |
| tests/test_application/test_notificacion_producto.py | `NotificacionProductoTests::test_con_extracto_msg16_fecha_correo_y_envia_correo` | Tests de la FASE 2 del flujo 3 (notificación): análisis del producto elegido. | - |
| tests/test_application/test_notificacion_producto.py | `NotificacionProductoTests::test_producto_no_encontrado_va_a_17` | Tests de la FASE 2 del flujo 3 (notificación): análisis del producto elegido. | - |
| tests/test_application/test_notificacion_producto.py | `NotificacionProductoTests::test_obtener_pdf_extracto_usa_paths_configurables` | Tests de la FASE 2 del flujo 3 (notificación): análisis del producto elegido. | - |
| tests/test_infrastructure/test_commercial_info_trace_masking.py | `test_mask_text_hides_pan_and_emails_but_keeps_ids` | El volcado de depuracion del ASO en back_data sale enmascarado (KYNS IT 3). | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_commercial_info_trace_masking.py | `test_safe_headers_drop_credentials` | El volcado de depuracion del ASO en back_data sale enmascarado (KYNS IT 3). | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_commercial_info_trace_masking.py | `test_mask_text_keeps_bank_contract_numbers` | El volcado de depuracion del ASO en back_data sale enmascarado (KYNS IT 3). | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_entrypoint/test_consultar_router.py | `CustomerNameRouteTests::test_returns_the_customer_name_after_a_successful_lookup` | Regression tests for the back-data routes that remain after TXNR decoupling. | - |
| tests/test_infrastructure/test_entrypoint/test_consultar_router.py | `CustomerNameRouteTests::test_fails_open_when_the_lookup_raises` | Regression tests for the back-data routes that remain after TXNR decoupling. | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_health_check_returns_ok` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_consultar_accepts_request_for_background_processing` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_consultar_accepts_request_even_when_background_customer_does_not_exist` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_centrales_no_autorizo_accepts_request_for_background_processing` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_notificacion_centrales_accepts_request_for_background_processing` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_request_validation_returns_406` |  | - |
| tests/test_infrastructure/test_entrypoint/test_fastapi_app.py | `FastApiAppTests::test_openapi_documents_406_instead_of_422` |  | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `BackDataMiddlewareAuditTests::test_error_response_audited` | Tests for back_data error auditing (middleware + scheduler). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `BackDataMiddlewareAuditTests::test_success_not_audited` | Tests for back_data error auditing (middleware + scheduler). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `BackDataMiddlewareAuditTests::test_406_skipped` | Tests for back_data error auditing (middleware + scheduler). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `BackDataMiddlewareAuditTests::test_exception_audited_and_reraised` | Tests for back_data error auditing (middleware + scheduler). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `BackDataAuditSchedulerTests::test_noop_without_url` | Tests for back_data error auditing (middleware + scheduler). | - |
| tests/test_infrastructure/test_entrypoint/test_middleware_audit.py | `BackDataAuditSchedulerTests::test_schedules_with_component` | Tests for back_data error auditing (middleware + scheduler). | - |
| tests/test_infrastructure/test_observability/test_trace_audit.py | `ScheduleTraceEventTests::test_noop_when_error_handler_url_unset` | Unit tests for the fire-and-forget trace emitter (schedule_trace_event). | - |
| tests/test_infrastructure/test_observability/test_trace_audit.py | `ScheduleTraceEventTests::test_posts_expected_payload_when_url_set` | Unit tests for the fire-and-forget trace emitter (schedule_trace_event). | - |
| tests/test_infrastructure/test_observability/test_trace_audit.py | `ScheduleTraceEventTests::test_error_outcome_carries_error_fields` | Unit tests for the fire-and-forget trace emitter (schedule_trace_event). | - |
| tests/test_infrastructure/test_observability/test_trace_audit.py | `ScheduleTraceEventTests::test_never_raises_even_if_config_fails` | Unit tests for the fire-and-forget trace emitter (schedule_trace_event). | - |
| tests/test_infrastructure/test_persistence/test_commercial_info_trace.py | `CommercialInfoTraceTests::test_success_emits_ok_traces_and_masks_document` | Tests for ASO client enrichment: structured logs + trace emission. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_persistence/test_commercial_info_trace.py | `CommercialInfoTraceTests::test_overview_http_error_emits_error_trace_and_raises` | Tests for ASO client enrichment: structured logs + trace emission. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_persistence/test_commercial_info_trace.py | `CommercialInfoTraceTests::test_masking_helper` | Tests for ASO client enrichment: structured logs + trace emission. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_persistence/test_commercial_info_trace.py | `CommercialInfoTraceTests::test_pdf_request_omits_content_type_and_accepts_pdf` | Tests for ASO client enrichment: structured logs + trace emission. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_persistence/test_commercial_info_trace.py | `CommercialInfoTraceTests::test_pdf_request_retries_only_after_406` | Tests for ASO client enrichment: structured logs + trace emission. | IT3.2, IT3.6, IT3.7 |
| tests/test_infrastructure/test_persistence/test_commercial_info_trace.py | `CommercialInfoTraceTests::test_pdf_request_rejects_non_document_success_response` | Tests for ASO client enrichment: structured logs + trace emission. | IT3.2, IT3.6, IT3.7 |

### co_pqrs_back_error_handler

| Fichero | Test | Qué demuestra | Controles |
|---|---|---|---|
| tests/test_application/test_error_report/test_error_report_service.py | `GenerateErrorReportTests::test_generate_error_report_exports_report_with_analytics` | Validate analytics and file export behavior. | - |
| tests/test_enrichment_resilience.py | `EnrichmentFailureResilienceTests::test_report_written_to_minio_when_opensearch_down` | Resilience test: a report is still written when OpenSearch enrichment fails. | - |
| tests/test_enrichment_resilience.py | `EnrichmentFailureResilienceTests::test_report_without_conversation_id_for_non_conversation_service` | Resilience test: a report is still written when OpenSearch enrichment fails. | - |
| tests/test_minio_storage.py | `MinioSettingsTests::test_defaults_disabled` | Tests for the MinIO object-storage backend of the error handler. | - |
| tests/test_minio_storage.py | `MinioSettingsTests::test_enabled_from_env` | Tests for the MinIO object-storage backend of the error handler. | - |
| tests/test_minio_storage.py | `ObjectStoreTests::test_write_json_and_idempotency` | Tests for the MinIO object-storage backend of the error handler. | - |
| tests/test_minio_storage.py | `ObjectStoreTests::test_requires_bucket` | Tests for the MinIO object-storage backend of the error handler. | - |
| tests/test_minio_storage.py | `WriterMinioTests::test_write_report_to_minio` | Tests for the MinIO object-storage backend of the error handler. | - |
| tests/test_request_log.py | `RequestLogWriterTests::test_write_request_log_to_minio_separate_prefix` | Tests for the per-request full log sink (writer + service). | - |
| tests/test_request_log.py | `RequestLogWriterTests::test_customer_derived_from_conversation_when_missing` | Tests for the per-request full log sink (writer + service). | - |
| tests/test_trace_event.py | `TraceEventWriterTests::test_write_aso_ok_to_minio` | Tests for the E2E trace-event sink (writer + service). | - |
| tests/test_trace_event.py | `TraceEventWriterTests::test_write_error_event_to_minio` | Tests for the E2E trace-event sink (writer + service). | - |
| tests/test_trace_sanitizer.py | `MaskTextTests::test_pan_keeps_last_four_with_or_without_separators` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `MaskTextTests::test_pan_inside_url_and_json_text` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `MaskTextTests::test_identifiers_that_are_not_cards_are_kept` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `MaskTextTests::test_emails_are_hidden` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `SanitizeValueTests::test_secret_keys_are_redacted_whatever_the_casing` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `SanitizeValueTests::test_holder_names_become_initials` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `SanitizeValueTests::test_pan_nested_in_lists_and_strings` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `SanitizeValueTests::test_non_string_leaves_are_untouched` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer.py | `SanitizeTraceEventTests::test_top_level_identifiers_survive_but_payloads_are_cleaned` | La ultima barrera: ningun dato sensible se persiste, venga como venga del emisor. | IT3.2, IT3.6, IT3.7 |
| tests/test_trace_sanitizer_contracts.py | `test_contract_numbers_survive_even_when_they_pass_luhn` | Regla de PAN del sanitizador: oculta tarjetas, no números de contrato del banco. | - |
| tests/test_trace_sanitizer_contracts.py | `test_real_card_shapes_are_still_masked` | Regla de PAN del sanitizador: oculta tarjetas, no números de contrato del banco. | - |
| tests/test_trace_sanitizer_contracts.py | `test_trace_event_keeps_the_contract_and_hides_the_card` | Regla de PAN del sanitizador: oculta tarjetas, no números de contrato del banco. | - |

# Триаж падающих тестов (baseline после D0)

Прогон на свежем тестовом стеке: фаза 1 (`pytest tests/ -n 8 -m "not integration and not network and not agent_build_release"`) → фаза 2 (`--lf -n 1`).
Стабильно падают **123** теста (`tests/lastfailed_baseline.json`), проходят 9076. Починка — вне рамок плана доделывания; здесь только классификация по корневым причинам.

## Классы причин

- **108** — infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом)
- **4** — контракт: расхождение ожиданий теста и текущего API
- **4** — контракт: runtime требует active company в контексте теста
- **2** — infra: capability-gateway — контекст исполнения без env
- **1** — флак: identity WS=REST при фоновых изменениях между вызовами
- **1** — контракт: namespace теста не зарегистрирован в shared NamespaceRepository (realtime 400)
- **1** — infra: цепочка flows→guest A2A (ферма недоступна)
- **1** — infra: guest_runtime/docker/CDP недоступны в тесте
- **1** — infra: внешние SERP-провайдеры отключены в тестовом стеке

Доминирующая причина одна: фикстуры `mock_context`/`test_context` строят `Context` с `test_user` в компании `system`, а peer-сервисы (secrets, realtime, flows, office, capability-gateway) при применении signed `X-Platform-Context-*` проверяют членство по roster/FGA и отвечают 403; capability-gateway поверх этого отдаёт 500 после трёх ретраев. Починка — на стороне фикстур (D7): системный тестовый пользователь обязан быть членом `system` тем же путём, что и `ensure_system_admin_membership`.

## По тестам

| Тест | Класс |
|---|---|
| `tests/capabilities/test_crm_capabilities.py::test_crm_capabilities_cover_every_client_method` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/capabilities/test_db_capabilities.py::test_db_capabilities_in_manifest` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/capabilities/test_documents_capabilities.py::test_documents_capabilities_in_manifest` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/capabilities/test_rag_capabilities.py::test_rag_capabilities_cover_every_client_method` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/capabilities/test_sync_capabilities.py::test_sync_capabilities_cover_every_client_method` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/capabilities/test_wiki_capabilities.py::test_wiki_capabilities_in_manifest` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/capabilities/test_worktracker_capabilities.py::test_worktracker_capabilities_cover_client_methods` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/clients/test_capability_gateway_client.py::test_capability_gateway_client_get_documentation` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/events/test_platform_events_bus.py::test_domain_event_has_no_delivery` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/events/test_platform_events_bus.py::test_group_consumer_receives_and_acks` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/events/test_platform_events_bus.py::test_publish_to_users_delivers_one_stream_entry` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/files/test_file_extract_contract_e2e.py::test_file_extract_persist_writes_fileref[docx]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/files/test_file_extract_contract_e2e.py::test_file_extract_persist_writes_fileref[pdf_scan]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/files/test_file_extract_contract_e2e.py::test_file_extract_persist_writes_fileref[pdf_text]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/files/test_file_extract_contract_e2e.py::test_file_extract_persist_writes_fileref[png]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/files/test_file_extract_contract_e2e.py::test_file_extract_persist_writes_fileref[pptx]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/push/test_push_service.py::TestNotifyUserIntegration::test_notify_user_sends_push_when_offline` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/core/test_asgi_internal_sig.py::test_asgi_internal_headers_survive_jwt_secret_monkeypatch` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/crm/e2e/test_10_daily_summary.py::TestDailySummary::test_summary_rebuild_triggered_after_note_delete` | контракт: расхождение ожиданий теста и текущего API |
| `tests/crm/e2e/test_21_analysis_draft_pipeline.py::TestAnalysisDraftApplyPartialFailureCompensation::test_compensation_deletes_partial_creates_on_row_failure` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/crm/e2e/test_21_analysis_draft_pipeline.py::TestAnalysisDraftPipeline::test_apply_twice_second_call_fails_without_draft` | контракт: расхождение ожиданий теста и текущего API |
| `tests/crm/test_amocrm_tasks_import.py::test_amocrm_import_tasks_upsert_and_relationships` | контракт: namespace теста не зарегистрирован в shared NamespaceRepository (realtime 400) |
| `tests/flows/api/test_hitl_conversation_commands.py::test_hitl_conversation_get_rest_match_op` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_commands.py::test_hitl_conversation_send_forbidden_rest_match_op` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_commands.py::test_hitl_conversation_send_rest_match_op` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_operator_message_http_forbidden_for_queue_outsider` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_operator_message_http_idempotent` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_single_reply_complete_http_requires_resolution` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_single_reply_operator_ask_http_rejected` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_takeover_complete_http_allows_empty_resolution` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_takeover_operator_message_http_appends_without_resume` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_takeover_operator_message_http_with_file_ids` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/api/test_hitl_conversation_http.py::test_terminal_hitl_rejects_send_and_second_complete` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/channels/test_hitl_takeover_user_submit.py::test_a2a_user_message_appends_during_hitl_takeover` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/channels/test_hitl_takeover_user_submit.py::test_ui_action_appends_during_hitl_takeover` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_basic_execution` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_input_mapping_sources[input_mapping0-state_extra0-sum-20]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_input_mapping_sources[input_mapping1-state_extra1-sum-300]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_input_mapping_sources[input_mapping2-state_extra2-sum-15]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_input_mapping_sources[input_mapping3-state_extra3-sum-50]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_mixed_mapping` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_preserves_existing_state` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNode::test_tool_node_scalar_result_goes_to_result_field` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[defaults-def run(x=10, y=20, state=None):\n    return {"result": x + y}-input_mapping0-state_extra0-30]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[dict-result-def run(config=None, key="default", state=None):\n    if config is None:\n        config = {}\n    return {"value": config[key]}-input_mapping7-state_extra7-found]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[explicit-values-def run(x=10, y=20, state=None):\n    return {"result": x + y}-input_mapping1-state_extra1-20]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[list-result-def run(items=None, prefix="Item", state=None):\n    if items is None:\n        items = []\n    return {"formatted": [f"{prefix}: {item}" for item in items]}-input_mapping6-state_extra6-expected6]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[message-result-def run(greeting="Hello", name="World", state=None):\n    return {"message": f"{greeting}, {name}!"}-input_mapping5-state_extra5-Hello, \u0418\u0432\u0430\u043d!]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[partial-defaults-def run(x=10, y=20, z=30, state=None):\n    return {"result": x + y + z}-input_mapping2-state_extra2-55]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[state-and-var-values-def run(x=10, y=20, z=30, multiplier=1, state=None):\n    return {"result": (x + y + z) * multiplier}-input_mapping4-state_extra4-120]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCodeNodeNamedArguments::test_named_arguments[state-values-def run(x=10, y=20, state=None):\n    return {"result": x + y}-input_mapping3-state_extra3-20]` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCreateNodeTool::test_create_node_inline_tool` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestCreateNodeTool::test_create_node_inline_tool_with_mapping` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestInlineCodeNode::test_inline_tool_basic` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestInlineCodeNode::test_inline_tool_with_state_access` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/agent/test_tool_node.py::TestInlineCodeNode::test_inline_tool_with_var_mapping` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/services/test_services.py::TestFlowFactory::test_create_flow_saves_to_db` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/services/test_services.py::TestFlowFactory::test_flow_factory_resolves_variables` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/services/test_services.py::TestFlowFactory::test_flow_factory_unresolved_var_is_none` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/services/test_services.py::TestFlowFactory::test_get_flow_from_db` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/tasks/test_tasks.py::TestProcessAgentTaskResume::test_process_flow_task_resumes_flow` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/variables/test_variables.py::TestVariablesService::test_resolve_dict_with_vars` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/variables/test_variables.py::TestVariablesService::test_resolve_list` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/variables/test_variables.py::TestVariablesService::test_resolve_missing_var_raises_error` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/variables/test_variables.py::TestVariablesService::test_resolve_nested_dict` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/variables/test_variables.py::TestVariablesService::test_resolve_preserves_non_var_strings` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/variables/test_variables.py::TestVariablesService::test_resolve_simple_value` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/core/variables/test_variables.py::TestVariablesService::test_resolve_var_reference` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_code_agent_e2e.py::test_llm_node_then_code_agent` | infra: цепочка flows→guest A2A (ферма недоступна) |
| `tests/flows/e2e/test_documents_tools_e2e.py::test_agent_edits_uploaded_docx_with_documents_tools` | контракт: runtime требует active company в контексте теста |
| `tests/flows/e2e/test_documents_tools_e2e.py::test_agent_updates_uploaded_xlsx_with_documents_tool` | контракт: runtime требует active company в контексте теста |
| `tests/flows/e2e/test_embed_stream.py::test_embed_route_preflight_allows_configured_origin` | контракт: расхождение ожиданий теста и текущего API |
| `tests/flows/e2e/test_embed_stream.py::test_embed_route_preflight_denies_unconfigured_origin` | контракт: расхождение ожиданий теста и текущего API |
| `tests/flows/e2e/test_employee_inbox.py::test_work_item_assigned_enqueues_with_write_back` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_employee_inbox.py::test_work_item_assigned_enqueues_without_request_context` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_evaluation_lab_api.py::TestEvaluationLabAPI::test_pending_run_jobs_are_durable_and_taskiq_gated` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_evaluation_lab_api.py::TestEvaluationLabAPI::test_scheduler_gate_and_monitor_tasks_use_real_taskiq_contexts` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_evaluation_lab_api.py::TestEvaluationLabAPI::test_worker_task_contracts_use_real_taskiq_contexts` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestInterruptE2E::test_interrupt_path_correctness` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestInterruptE2E::test_multiple_interrupts_preserve_history` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestInterruptE2E::test_nested_states_preserved_through_resume` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestInterruptE2E::test_simple_ask_user_interrupt` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestInterruptE2E::test_subagent_interrupt_and_resume` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestSubflowInterruptE2E::test_subflow_code_node_interrupt` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestSubflowInterruptE2E::test_subflow_code_node_resume_answer_reaches_node` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestSubflowInterruptE2E::test_subflow_llm_node_ask_user_interrupt` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestSubflowInterruptE2E::test_subflow_llm_node_resume_answer_in_messages` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_interrupt_e2e.py::TestSubflowInterruptE2E::test_subflow_multiple_interrupts_answers_accumulate` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_e2e.py::TestVariablesE2E::test_current_date_variable_from_metadata_with_var_reference` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_e2e.py::TestVariablesE2E::test_var_reference_in_json_metadata_recursive_resolution` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_e2e.py::TestVariablesE2E::test_var_reference_in_metadata_recursive_resolution` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_e2e.py::TestVariablesE2E::test_var_reference_in_nested_json_metadata_recursive_resolution` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_branch_variables_replace_mode` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_demo_seed_resolves_company_name` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_example_graph_greeting_uses_scoped_variables` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_expression_signature_resolves` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_scoped_greeting_by_namespace` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_scoped_user_tier_by_user_id` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_secret_keys_audit_list` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_variables_scenarios_e2e.py::test_shared_secret_in_flow_variables` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/flows/e2e/test_viz_tools_e2e.py::test_agent_create_viz_office_roundtrip_and_export` | контракт: runtime требует active company в контексте теста |
| `tests/flows/e2e/test_viz_tools_e2e.py::test_agent_create_viz_rejects_invalid_args` | контракт: runtime требует active company в контексте теста |
| `tests/guest_runtime/test_docker_slots.py::test_docker_build_and_cli_invoke` | infra: capability-gateway — контекст исполнения без env |
| `tests/guest_runtime/test_docker_slots.py::test_docker_build_and_node_cli_invoke` | infra: capability-gateway — контекст исполнения без env |
| `tests/guest_runtime/test_docker_slots.py::test_docker_farm_rebuild_and_ensure_lease` | infra: guest_runtime/docker/CDP недоступны в тесте |
| `tests/observability/test_flows_runtime_metrics.py::test_flow_react_completed_emitted_after_llm_node` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/observability/test_flows_runtime_metrics.py::test_tool_call_finished_emitted_for_builtin_tool` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/rag/test_pgvector_scanned_pdf_indexing.py::test_pgvector_indexes_scanned_pdf_with_hybrid_ocr` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/rag/test_rag_document_status_event.py::test_publish_rag_document_status_updated_on_stream` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/realtime/test_flows_commands.py::test_flows_op_ws_rest_identical[flows/evaluation/monitor_cycles_run_active_requested]` | флак: identity WS=REST при фоновых изменениях между вызовами |
| `tests/realtime/test_presence.py::test_presence_offline_then_online_then_offline` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/search/integration/test_platform_index_search_e2e.py::test_auto_falls_back_when_index_empty` | infra: внешние SERP-провайдеры отключены в тестовом стеке |
| `tests/sync/api/test_notification_skip_rules_e2e.py::test_notify_user_delivered_when_recipient_offline` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_notification_skip_rules_e2e.py::test_notify_user_skipped_when_channel_muted` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_sync_calls_e2e.py::test_call_accept_changes_status_active_and_publishes_accepted` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_sync_calls_e2e.py::test_call_admin_transfer_only_admin_can_change` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_sync_calls_e2e.py::test_call_decline_publishes_declined_to_initiator` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_sync_calls_e2e.py::test_call_hangup_by_last_participant_writes_call_boundary_ended` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_sync_calls_e2e.py::test_call_invite_publishes_incoming_to_other_member` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_sync_calls_e2e.py::test_call_invite_writes_call_boundary_started_to_feed` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/api/test_sync_calls_e2e.py::test_call_signal_forwards_to_target_user_only` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/test_ws_presence.py::test_company_members_is_online_from_centrifugo` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |
| `tests/sync/test_ws_presence.py::test_sync_ws_presence_online_after_centrifugo_connect` | infra: фикстура контекста — test_user ∉ company system (проверка membership internal headers peer-сервисом) |

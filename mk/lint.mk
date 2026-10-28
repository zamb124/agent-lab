.PHONY: lint lint-ts lint-file _lint-py

PYTHON_CHECK_PATHS ?= apps core
RUFF_CHECK_ARGS ?= $(PYTHON_CHECK_PATHS)
BASEDPYRIGHT_CHECK_ARGS ?= --level warning --warnings $(PYTHON_CHECK_PATHS)
LINT_PATH_GOALS := $(filter-out lint lint-ts,$(filter %/%,$(MAKECMDGOALS)) $(filter %.py,$(MAKECMDGOALS)) $(filter %.js,$(MAKECMDGOALS)) $(filter %.ts,$(MAKECMDGOALS)))

lint:
	@set -e; \
	if [ -n "$(LINT_PATH_GOALS)" ]; then \
		for lint_target in $(LINT_PATH_GOALS); do \
			$(MAKE) --no-print-directory lint-file FILE="$$lint_target"; \
		done; \
	else \
		$(MAKE) --no-print-directory _lint-py lint-ts; \
		echo "lint: OK"; \
	fi

lint-ts:
	@echo "=== lint-ts: typecheck (tsc) ==="
	@npx tsc -p tsconfig.json
	@echo "=== lint-ts: events/ui canon ==="
	@$(MAKE) --no-print-directory check-events-canon
	@echo "=== lint-ts: ui kit docs canon ==="
	@uv run python scripts/check_ui_kit_docs.py
	@echo "=== lint-ts: field canon ==="
	@$(MAKE) --no-print-directory check-field-canon
	@echo "=== lint-ts: ui kit canon (ratchet) ==="
	@uv run python scripts/check_ui_kit_canon.py
	@echo "=== lint-ts: logging canon ==="
	@$(MAKE) --no-print-directory check-logging

_lint-py:
	@echo "=== lint: ruff ==="
	uv run ruff check $(RUFF_CHECK_ARGS)
	@echo "=== lint: strict agent architecture ==="
	uv run python scripts/check_strict_agent_architecture.py
	@echo "=== lint: wider repo strictness ==="
	uv run python scripts/audit_wider_repo_strictness.py
	@echo "=== lint: files canon ==="
	uv run python scripts/check_files_canon.py
	uv run python scripts/check_object_store_canon.py
	@bash scripts/check_files_ui_canon.sh
	@echo "=== lint: tool tags taxonomy ==="
	uv run python scripts/check_tool_tags.py
	@echo "=== lint: tool contracts ==="
	uv run python scripts/check_tool_contracts.py
	@echo "=== lint: no binding_id ==="
	uv run python scripts/check_office_file_id_canon.py
	@echo "=== lint: cross-service imports ==="
	uv run python scripts/check_cross_service_imports.py
	@echo "=== lint: command owners have catalogs ==="
	uv run python scripts/check_command_owner_catalogs.py
	@echo "=== lint: REST handlers call op_* ==="
	uv run python scripts/check_rest_handlers_call_ops.py
	@echo "=== lint: billing span canon ==="
	uv run python scripts/check_billing_span_canon.py
	@echo "=== lint: conf.json secrets ==="
	uv run python scripts/check_conf_secrets.py
	@echo "=== lint: conf.json keys declared ==="
	uv run python scripts/check_conf_keys_declared.py
	@echo "=== lint: repo hygiene ==="
	uv run python scripts/check_repo_hygiene.py
	@echo "=== lint: ratchet counts ==="
	uv run python scripts/check_ratchet_counts.py
	@echo "=== lint: dependency injection canon ==="
	uv run python scripts/check_dependency_injection_canon.py
	@echo "=== lint: backend error i18n ==="
	uv run python scripts/check_backend_error_i18n.py

	@echo "=== lint: mcp branding bundle ==="
	uv run python scripts/check_mcp_branding_bundle.py
	@echo "=== lint: platform brand hardcode ==="
	uv run python scripts/check_platform_brand_hardcode.py
	@echo "=== lint: authz canon ==="
	uv run python scripts/check_authz_canon.py
	@echo "=== lint: authz dual-write ==="
	uv run python scripts/check_authz_dual_write.py
	@echo "=== lint: authz backfill completeness ==="
	uv run python scripts/check_authz_backfill_completeness.py
	@echo "=== lint: authz model tests ==="
	uv run python scripts/check_authz_model.py
	@echo "=== lint: basedpyright ==="
	uv run basedpyright $(BASEDPYRIGHT_CHECK_ARGS)
	@echo "=== lint: local imports ==="
	uv run python analyze_imports.py
	@echo "=== lint: agent e2e coverage gate ==="
	uv run python scripts/check_agent_e2e_coverage.py
	@echo "=== lint: agent goose tool contract ==="
	uv run python scripts/check_agent_goose_tool_contract.py
	@echo "=== lint: agent e2e no monkeypatch ==="
	uv run python scripts/check_agent_test_no_monkeypatch.py
	@echo "=== lint: variables legacy grep ==="
	@bash scripts/check_variables_legacy.sh
	@echo "=== lint: sync file upload op ==="
	uv run python scripts/check_sync_file_upload_op.py
	@echo "=== lint: sync company directory ops ==="
	uv run python scripts/check_sync_company_directory_ops.py
	@echo "=== lint: sync call link ops ==="
	uv run python scripts/check_sync_call_link_ops.py
	@echo "=== lint: sync call session ops ==="
	uv run python scripts/check_sync_call_session_ops.py
	@echo "=== lint: sync call lifecycle ops ==="
	uv run python scripts/check_sync_call_lifecycle_ops.py
	@echo "=== lint: sync call recording ops ==="
	uv run python scripts/check_sync_call_recording_ops.py
	@echo "=== lint: sync thread and git ops ==="
	uv run python scripts/check_sync_thread_git_ops.py
	@echo "=== lint: sync message send ==="
	uv run python scripts/check_sync_message_send.py
	@echo "=== lint: sync message ops ==="
	uv run python scripts/check_sync_message_ops.py
	@echo "=== lint: no service components.py ==="
	uv run python scripts/check_no_service_components.py
	@echo "=== lint: crm entity type model files ==="
	uv run python scripts/check_crm_entity_type_model_files.py
	@echo "=== lint: ai model files ==="
	uv run python scripts/check_ai_model_files.py
	@echo "=== lint: datasource model files ==="
	uv run python scripts/check_datasource_model_files.py
	@echo "=== lint: evaluation lab model files ==="
	uv run python scripts/check_evaluation_lab_model_files.py
	@echo "=== lint: crm namespace template model files ==="
	uv run python scripts/check_crm_namespace_template_model_files.py
	@echo "=== lint: rag model files ==="
	uv run python scripts/check_rag_model_files.py
	@echo "=== lint: secrets model files ==="
	uv run python scripts/check_secrets_model_files.py
	@echo "=== lint: sync message model files ==="
	uv run python scripts/check_sync_message_model_files.py
	@echo "=== lint: a2a projection model files ==="
	uv run python scripts/check_a2a_projection_model_files.py
	@echo "=== lint: durable model files ==="
	uv run python scripts/check_durable_model_files.py
	@echo "=== lint: identity model files ==="
	uv run python scripts/check_identity_model_files.py
	@echo "=== lint: crawl model files ==="
	uv run python scripts/check_crawl_model_files.py
	@echo "=== lint: mail model files ==="
	uv run python scripts/check_mail_model_files.py
	@echo "=== lint: worktracker model files ==="
	uv run python scripts/check_worktracker_model_files.py
	@echo "=== lint: office model files ==="
	uv run python scripts/check_office_model_files.py
	@echo "=== lint: wiki model files ==="
	uv run python scripts/check_wiki_model_files.py
	@echo "=== lint: sync channel ops ==="
	uv run python scripts/check_sync_channel_ops.py
	@echo "=== lint: flows src clients ==="
	uv run python scripts/check_flows_src_clients.py
	@echo "=== lint: stock service queries ==="
	uv run python scripts/check_stock_service_queries.py
	@echo "=== lint: migration files canon ==="
	uv run python scripts/check_migration_files_canon.py
	@echo "=== lint: redis ttl canon ==="
	uv run python scripts/check_redis_ttl_canon.py
	@echo "=== lint: taskiq canon ==="
	uv run python scripts/check_taskiq_canon.py

lint-file:
	@test -n "$(FILE)" || (echo "usage: make lint FILE=<path>  или  make lint <path>" >&2; exit 1)
	@test -e "$(FILE)" || (echo "lint: path not found: $(FILE)" >&2; exit 1)
	@case "$(FILE)" in \
		*.py) \
			echo "=== lint-file: ruff ==="; \
			uv run ruff check "$(FILE)"; \
			echo "=== lint-file: basedpyright ==="; \
			uv run basedpyright --level warning --warnings "$(FILE)"; \
			;; \
		*.js|*.ts) \
			$(MAKE) --no-print-directory lint-ts; \
			;; \
		*) \
			echo "lint: unsupported file type: $(FILE)" >&2; \
			echo "lint: поддерживаются .py, .js и .ts; полная проверка — make lint" >&2; \
			exit 1; \
			;; \
	esac

# Пути после lint: make lint apps/search/db/models.py
$(LINT_PATH_GOALS):
	@:

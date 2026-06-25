.PHONY: lint lint-ts lint-file _lint-py

PYTHON_CHECK_PATHS ?= apps core
RUFF_CHECK_ARGS ?= $(PYTHON_CHECK_PATHS)
BASEDPYRIGHT_CHECK_ARGS ?= --level warning --warnings $(PYTHON_CHECK_PATHS)
LINT_PATH_GOALS := $(filter-out lint lint-ts,$(filter %/%,$(MAKECMDGOALS)) $(filter %.py,$(MAKECMDGOALS)) $(filter %.js,$(MAKECMDGOALS)))

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
	@echo "=== lint-ts: events/ui canon ==="
	@$(MAKE) --no-print-directory check-events-canon
	@echo "=== lint-ts: field canon ==="
	@$(MAKE) --no-print-directory check-field-canon
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
	@bash scripts/check_files_ui_canon.sh
	@echo "=== lint: mcp branding bundle ==="
	uv run python scripts/check_mcp_branding_bundle.py
	@echo "=== lint: basedpyright ==="
	uv run basedpyright $(BASEDPYRIGHT_CHECK_ARGS)
	@echo "=== lint: local imports ==="
	uv run python analyze_imports.py

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
		*.js) \
			$(MAKE) --no-print-directory lint-ts; \
			;; \
		*) \
			echo "lint: unsupported file type: $(FILE)" >&2; \
			echo "lint: поддерживаются .py и .js; полная проверка — make lint" >&2; \
			exit 1; \
			;; \
	esac

# Пути после lint: make lint apps/search/db/models.py
$(LINT_PATH_GOALS):
	@:

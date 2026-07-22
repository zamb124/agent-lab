.PHONY: app kill-ports

# Все локальные сервисы (ключи SERVICES в scripts/run.py) через mprocs —
# один TUI, логи смотришь по выбранному процессу (j/k).
# Требует: brew install mprocs. Конфиг: mprocs.yaml.
# Granian: --reload для HTTP (кроме provider_litserve/browser). APP_RELOAD=0 — без reload.
# Остановка: q в mprocs (или Ctrl+C). APP_KILL=1 — освободить порты перед стартом.
# Исключение: make app ex flows_worker  (ex | x, затем имя; либо APP_EXCLUDE=…; либо make -- app --ex …).
APP_MAK_EX_FLAGS := ex x --ex --exclude -e --kill
APP_MAK_SVC := flows frontend crm rag sync worktracker office scheduler-api secrets browser search \
	provider_litserve voice capability_gateway code_runner_python code_runner_node code_runner_go \
	code_runner_csharp flows_worker rag_worker search_worker sync_worker crm_worker idle_worker scheduler
ifneq (,$(findstring app,$(MAKECMDGOALS)))
APP_MAK_EXTRAS := $(filter-out app,$(MAKECMDGOALS))
APP_MAK_NOOP := $(filter $(APP_MAK_EX_FLAGS) $(APP_MAK_SVC),$(APP_MAK_EXTRAS))
ifneq (,$(APP_MAK_NOOP))
define _app_mk_noop
$1: ; @:
endef
$(foreach t,$(APP_MAK_NOOP),$(eval $(call _app_mk_noop,$(t))))
.PHONY: $(APP_MAK_NOOP)
endif
endif

# APP_EXCLUDE=… — тот же эффект (через запятую), можно совмещать с make app --ex …
app: runtime-bootstrap
	@command -v mprocs >/dev/null 2>&1 || { echo "mprocs не найден. Установи: brew install mprocs"; exit 1; }
	@APP_EXCLUDE="$(APP_EXCLUDE)" uv run python scripts/run.py from-make $(MAKECMDGOALS) $(if $(filter 1,$(APP_KILL)),--from-make-kill,)

# Только освободить порты HTTP-сервисов (без запуска).
kill-ports:
	uv run python scripts/run.py kill-ports

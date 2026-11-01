.PHONY: app kill-ports

# Все локальные сервисы (ключи SERVICES в scripts/dev/run.py) через mprocs —
# один TUI, логи смотришь по выбранному процессу (j/k).
# Требует: brew install mprocs. Конфиг: mprocs.yaml.
# Granian: --reload для HTTP (кроме provider_litserve/browser). APP_RELOAD=0 — без reload.
# Остановка: q в mprocs (или Ctrl+C) — дочерний процесс mprocs = сам сервис
# (exec-цепочка без sh/uv): stop/restart добивает сервис вместе с его worker'ами.
# Сироты прошлых запусков (порты + taskiq/granian-процессы) зачищаются при каждом старте.
# Исключение: make app ex flows_worker  (ex | x, затем имя; либо APP_EXCLUDE=…; либо make -- app --ex …).
APP_MAK_EX_FLAGS := ex x --ex --exclude -e --kill
APP_MAK_SVC := ui_watch flows frontend crm rag sync worktracker office scheduler-api secrets wiki stock guest_runtime browser search \
	provider_litserve voice capability_gateway code_runner_python code_runner_node code_runner_go \
	code_runner_csharp flows_worker rag_worker search_worker sync_worker crm_worker crm_summary_worker idle_worker scheduler
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
app: runtime-bootstrap ui-build
	@command -v mprocs >/dev/null 2>&1 || { echo "mprocs не найден. Установи: brew install mprocs"; exit 1; }
	@APP_EXCLUDE="$(APP_EXCLUDE)" uv run python -m scripts.dev.run from-make $(MAKECMDGOALS) $(if $(filter 1,$(APP_KILL)),--from-make-kill,)

# Только зачистка сирот: порты HTTP-сервисов + процессы прошлых запусков (без запуска).
kill-ports:
	uv run python -m scripts.dev.run kill-ports

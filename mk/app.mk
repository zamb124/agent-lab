.PHONY: app kill-ports

# Все локальные сервисы (flows, frontend, crm, rag, sync, provider_litserve, workers, scheduler) одной командой.
# Uvicorn: --reload. TaskIQ worker без --reload (стабильнее в режиме all). Остановка: Ctrl+C.
# APP_KILL=1 — перед стартом завершить процессы на портах HTTP-сервисов (8001-8006 и 8014), см. scripts/run.py kill-ports.
# Исключение: make app ex flows_worker  (коротко, работает везде; ex | x, затем имя, можно повторять).
#   Либо: make -- app --ex flows_worker  (системный make в macOS иначе принимает --ex за свой флаг).
#   Либо: make app --exclude NAME  (если цель --exclude не конфликтует с make).
# Список имён: ключи SERVICES в scripts/run.py.
APP_MAK_EX_FLAGS := ex x --ex --exclude -e --kill
APP_MAK_SVC := flows frontend crm rag sync office scheduler-api browser provider_litserve \
	flows_worker rag_worker sync_worker crm_worker idle_worker scheduler
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
app:
	@APP_EXCLUDE="$(APP_EXCLUDE)" uv run python scripts/run.py from-make $(MAKECMDGOALS) $(if $(filter 1,$(APP_KILL)),--from-make-kill,)

# Только освободить порты 8001-8006 (без запуска сервисов).
kill-ports:
	uv run python scripts/run.py kill-ports

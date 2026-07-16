# ============================================================================
# Поиск по коду — два движка (Docker Compose)
# ============================================================================
# make zed-search           поднять весь стек в Compose + wire Zed/Cursor + primary index
#                           (Ollama + Milvus + CBM+proxy + claude-context+proxy)
# make zed-search-check     health-check Compose (exit 0/1 + WARN)
# make zed-search-update    пересобрать образы CBM/claude-context + restart
# make zed-search-reindex   HTTP reindex обоих движков через mcp-proxy
# make zed-search-status    docker compose ps + ping
# make zed-search-down      docker compose down
# make zed-search-logs      логи compose (опц. SERVICE=cbm)
# make zed-search-test      интеграционные тесты
# make zed-search-sync-caila-models  Caila → Zed settings
#
# Legacy (redirect → compose):
#   zed-search-watch* / zed-search-cbm-daemon* — больше не канон

.PHONY: zed-search zed_search zed-search-check zed-search-update zed-search-test zed-search-status \
        zed-search-down zed-search-logs zed-search-watch zed-search-watch-install \
        zed-search-watch-uninstall zed-search-reindex zed-search-sync-caila-models \
        zed-search-cbm-daemon zed-search-cbm-daemon-uninstall

COMPOSE_SH := bash scripts/zed_search/compose.sh
ZED_SEARCH_SERVICE ?=

zed-search:
	@$(COMPOSE_SH) up

zed_search: zed-search

zed-search-check:
	@bash scripts/zed_search/healthcheck.sh

zed-search-update:
	@$(COMPOSE_SH) update

zed-search-reindex:
	@$(COMPOSE_SH) reindex

zed-search-status:
	@$(COMPOSE_SH) status

zed-search-down:
	@$(COMPOSE_SH) down

zed-search-logs:
	@if [ -n "$(ZED_SEARCH_SERVICE)" ]; then \
		$(COMPOSE_SH) logs "$(ZED_SEARCH_SERVICE)"; \
	else \
		$(COMPOSE_SH) logs; \
	fi

zed-search-test:
	@echo "[zed-search] Запуск интеграционных тестов..."
	@.venv/bin/python3 -m pytest tests/zed_search/test_zed_search.py -c tests/zed_search/pytest.ini --timeout=300

# Legacy aliases → Compose
zed-search-watch zed-search-watch-install zed-search-cbm-daemon:
	@echo "[zed-search] legacy target '$@' → Compose-канон"
	@$(COMPOSE_SH) up --no-index

zed-search-watch-uninstall zed-search-cbm-daemon-uninstall:
	@echo "[zed-search] legacy uninstall '$@' → stop-legacy + compose down не трогаем стек"
	@$(COMPOSE_SH) stop-legacy

zed-search-sync-caila-models:
	@python3 scripts/zed_search/sync_caila_models.py

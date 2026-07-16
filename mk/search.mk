# ============================================================================
# Семантический поиск по коду — claude-context MCP (Ollama + Milvus + watcher)
# ============================================================================
# make zed-search                  полная настройка: бэкенд + первичная индексация (авто)
# make zed-search-check            health-check + проверка версии MCP (агент зовёт при старте)
# make zed-search-update           обновить MCP-пакет до свежей версии из npm
# make zed-search-test             интеграционные тесты (поиск, переиндексация, healthcheck)
# make zed-search-status           статус всех компонентов
# make zed-search-down             остановить Milvus
# make zed-search-logs              логи Milvus
# make zed-search-watch            запустить watcher переиндексации (foreground, для отладки)
# make zed-search-watch-install    установить launchd-агент (автозапуск при логине)
# make zed-search-watch-uninstall  убрать launchd-агент
# make zed-search-reindex          первичная/принудительная переиндексация (через MCP)

.PHONY: zed-search zed_search zed-search-check zed-search-update zed-search-test zed-search-status \
        zed-search-down zed-search-logs zed-search-watch zed-search-watch-install \
        zed-search-watch-uninstall zed-search-reindex

CLAUDE_CONTEXT_DIR ?= $(HOME)/.local/share/claude-context-milvus
CLAUDE_CONTEXT_COMPOSE ?= $(CLAUDE_CONTEXT_DIR)/docker-compose.yml
CLAUDE_CONTEXT_TRIGGER ?= $(HOME)/.context/.sync-trigger
WATCH_LABEL ?= com.claude-context-watch
WATCH_PLIST ?= $(HOME)/Library/LaunchAgents/$(WATCH_LABEL).plist

# Полная настройка: бэкенд (Ollama + Milvus + fswatch) + launchd-watcher +
# первичная индексация кодовой базы через MCP. Идемпотентно.
zed-search:
	@bash scripts/zed_search/setup.sh
	@echo "[zed-search] Установка launchd-агента автоиндексации..."
	@$(MAKE) --no-print-directory zed-search-watch-install
	@echo ""
	@echo "[zed-search] Запуск первичной индексации кодовой базы..."
	@python3 scripts/zed_search/index.py "$(CURDIR)"
	@bash scripts/zed_search/linear.sh
	@echo ""
	@echo "[zed-search] ✅ Готово. Бэкенд + индекс + watcher настроены."
	@echo "[zed-search] Проверка здоровья: make zed-search-check"
	@echo "[zed-search] Обновление MCP:    make zed-search-update"

# Health-check всех компонентов. Возвращает non-zero, если MCP сломан.
# Агент Zed должен вызывать это при старте (см. .cursor/rules/claude-context.mdc).
zed-search-check:
	@bash scripts/zed_search/healthcheck.sh

# Интеграционные тесты zed-search (поиск, переиндексация, healthcheck).
# Тесты, требующие Ollama+Milvus, скипаются если стек недоступен.
zed-search-test:
	@echo "[zed-search] Запуск интеграционных тестов..."
	@.venv/bin/python3 -m pytest tests/zed_search/test_zed_search.py -c tests/zed_search/pytest.ini --timeout=300

# Обновление MCP-пакета до свежей версии из npm.
# Очищает кеш npx -> при следующем запуске Zed скачает актуальную версию.
zed-search-update:
	@echo "[zed-search] Проверка версии claude-context MCP..."
	@installed=$$(find ~/.npm/_npx -name "package.json" -path "*claude-context-mcp*" 2>/dev/null \
		| head -1 | xargs python3 -c "import sys,json; print(json.load(sys.stdin).get('version','?'))" 2>/dev/null) ; \
	latest=$$(npm view @zilliz/claude-context-mcp version 2>/dev/null || echo "?") ; \
	if [ -z "$$installed" ]; then \
		echo "[zed-search] Кеш пуст — обновление уже применено или не был установлен." ; \
		echo "[zed-search] Перезапусти Zed — скачается v$$latest." ; \
	elif [ "$$installed" = "$$latest" ]; then \
		echo "[zed-search] ✅ Версия v$$installed актуальна." ; \
	else \
		echo "[zed-search] Установлена v$$installed, в npm v$$latest — обновляю..." ; \
		rm -rf ~/.npm/_npx/*/node_modules/@zilliz/claude-context-mcp ; \
		echo "[zed-search] ✅ Кеш очищен. Перезапусти Zed — скачается v$$latest." ; \
	fi

# Алиас (make zed_search == make zed-search)
zed_search: zed-search

zed-search-status:
	@echo "[zed-search] Ollama:  $$(curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && echo OK || echo FAIL)"
	@echo "[zed-search] Milvus:  $$(docker inspect --format '{{.State.Health.Status}}' milvus-standalone 2>/dev/null || echo stopped)"
	@echo "[zed-search] fswatch: $$(command -v fswatch >/dev/null 2>&1 && echo OK || echo missing)"

# Остановить Milvus (compose down + fallback по именам контейнеров).
zed-search-down:
	@echo "[zed-search] Остановка Milvus..."
	@if [ -f "$(CLAUDE_CONTEXT_COMPOSE)" ]; then \
		docker compose -f "$(CLAUDE_CONTEXT_COMPOSE)" down 2>/dev/null || true; \
	fi
	@docker stop milvus-standalone milvus-minio milvus-etcd 2>/dev/null || true
	@echo "[zed-search] Milvus остановлен"

zed-search-logs:
	@docker logs -f milvus-standalone

# Watcher в foreground: при изменении файлов «трогает» триггер -> инкрементальная переиндексация.
zed-search-watch:
	@./scripts/zed_search/watch.sh "$(CURDIR)"

# Установить launchd-агент: watcher стартует при логине и перезапускается при падении.
zed-search-watch-install:
	@echo "[zed-search] Установка launchd-агента watcher-а..."
	@mkdir -p "$$(dirname "$(WATCH_PLIST)")"
	@printf '%s\n' \
		'<?xml version="1.0" encoding="UTF-8"?>' \
		'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
		'<plist version="1.0">' \
		'<dict>' \
		'    <key>Label</key>' \
		'    <string>$(WATCH_LABEL)</string>' \
		'    <key>ProgramArguments</key>' \
		'    <array>' \
		'        <string>$(CURDIR)/scripts/zed_search/watch.sh</string>' \
		'    </array>' \
		'    <key>RunAtLoad</key>' \
		'    <true/>' \
		'    <key>KeepAlive</key>' \
		'    <true/>' \
		'    <key>StandardOutPath</key>' \
		'    <string>/tmp/claude-context-watch.log</string>' \
		'    <key>StandardErrorPath</key>' \
		'    <string>/tmp/claude-context-watch.err.log</string>' \
		'    <key>WorkingDirectory</key>' \
		'    <string>$(CURDIR)</string>' \
		'</dict>' \
		'</plist>' > "$(WATCH_PLIST)"
	@launchctl unload "$(WATCH_PLIST)" 2>/dev/null || true
	@launchctl load "$(WATCH_PLIST)"
	@echo "[zed-search] launchd-агент установлен: $(WATCH_PLIST)"
	@echo "[zed-search] Логи: tail -f /tmp/claude-context-watch.log"

zed-search-watch-uninstall:
	@echo "[zed-search] Удаление launchd-агента watcher-а..."
	@launchctl unload "$(WATCH_PLIST)" 2>/dev/null || true
	@rm -f "$(WATCH_PLIST)"
	@echo "[zed-search] launchd-агент удалён"

# Первичная / принудительная переиндексация через MCP (index_codebase).
# Touch триггер-файла только для инкремента; для полного перестроения — через MCP.
zed-search-reindex:
	@echo "[zed-search] Запуск переиндексации через MCP..."
	@python3 scripts/zed_search/index.py "$(CURDIR)"
	@echo "[zed-search] ✅ Переиндексация завершена."

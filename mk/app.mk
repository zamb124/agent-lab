.PHONY: app app-up app-down app-logs app-restart app-build kill-ports

# Все локальные сервисы (flows, frontend, crm, rag, sync, provider_litserve, workers, scheduler) одной командой.
# Uvicorn: --reload. TaskIQ worker без --reload (стабильнее в режиме all). Остановка: Ctrl+C.
# APP_KILL=1 — перед стартом завершить процессы на портах HTTP-сервисов (8001–8006 и 8014), см. scripts/run.py kill-ports.
app:
	uv run python scripts/run.py all $(if $(filter 1,$(APP_KILL)),--kill,)

# Только освободить порты 8001–8006 (без запуска сервисов).
kill-ports:
	uv run python scripts/run.py kill-ports

app-up:
	docker-compose up -d app

app-down:
	docker-compose stop app

app-logs:
	docker-compose logs -f app

app-restart:
	docker-compose restart app

app-build:
	docker-compose build app


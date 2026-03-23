.PHONY: app app-up app-down app-logs app-restart app-build

# Все локальные сервисы (flows, frontend, crm, rag, sync, workers, scheduler) одной командой.
# Uvicorn: --reload. TaskIQ worker без --reload (стабильнее в режиме all). Остановка: Ctrl+C.
app:
	uv run python scripts/run.py all

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


# Миграции: python -m scripts.db_migrate
# Сервисы: shared | flows | crm | sync | rag | office | worktracker | secrets | tracing | search | wiki | realtime
.PHONY: migrate migrate-new

migrate:
	uv run python -m scripts.db_migrate upgrade

# make migrate-new            — все базы
# make migrate-new s=flows    — одна база
migrate-new:
	uv run python -m scripts.db_migrate makemigrations $(if $(s),--service $(s),)

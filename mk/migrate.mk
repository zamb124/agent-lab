# Миграции: единая точка — python -m scripts.db_migrate <команда>
# Сервисы: shared | flows | crm | sync | rag | office
.PHONY: migrate migrate-new migrate-empty migrate-downgrade migrate-downgrade-to migrate-history migrate-current migrate-heads

migrate:
	uv run python -m scripts.db_migrate upgrade

# make migrate-new m="описание" s=shared  (или flows, crm, sync, rag, office)
migrate-new:
	uv run python -m scripts.db_migrate revision -m "$(m)" --service $(s) --autogenerate

migrate-empty:
	uv run python -m scripts.db_migrate revision -m "$(m)" --service $(s) --empty

migrate-downgrade:
	uv run python -m scripts.db_migrate downgrade --service $(s)

migrate-downgrade-to:
	uv run python -m scripts.db_migrate downgrade --service $(s) $(rev)

migrate-history:
	uv run python -m scripts.db_migrate history --service $(s)

migrate-current:
	uv run python -m scripts.db_migrate current --service $(s)

migrate-heads:
	uv run python -m scripts.db_migrate heads --service $(s)

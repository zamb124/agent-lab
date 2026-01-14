# Команды для работы с миграциями Alembic
.PHONY: migrate migrate-new migrate-empty migrate-downgrade migrate-downgrade-to migrate-history migrate-current migrate-heads migrate-sql

# Применить все pending миграции
migrate:
	uv run alembic -c migrations/alembic.ini upgrade head

# Создать новую миграцию с autogenerate
# Использование: make migrate-new m="add_users_table"
migrate-new:
	uv run alembic -c migrations/alembic.ini revision --autogenerate -m "$(m)"

# Создать пустую миграцию (без autogenerate)
# Использование: make migrate-empty m="custom_migration"
migrate-empty:
	uv run alembic -c migrations/alembic.ini revision -m "$(m)"

# Откатить последнюю миграцию
migrate-downgrade:
	uv run alembic -c migrations/alembic.ini downgrade -1

# Откатить до конкретной ревизии
# Использование: make migrate-downgrade-to rev="abc123"
migrate-downgrade-to:
	uv run alembic -c migrations/alembic.ini downgrade $(rev)

# Показать историю миграций
migrate-history:
	uv run alembic -c migrations/alembic.ini history

# Показать текущую версию БД
migrate-current:
	uv run alembic -c migrations/alembic.ini current

# Показать pending миграции (heads)
migrate-heads:
	uv run alembic -c migrations/alembic.ini heads

# Сгенерировать SQL для миграции (offline mode)
migrate-sql:
	uv run alembic -c migrations/alembic.ini upgrade head --sql

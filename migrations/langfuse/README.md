# Миграции Langfuse

Этот каталог содержит миграции для инициализации баз данных Langfuse.

## Структура

```
langfuse/
├── clickhouse/          # Миграции для ClickHouse
│   ├── 001_create_database.sql
│   ├── 002_create_user.sql
│   └── 003_grant_permissions.sql
├── postgresql/          # Миграции для PostgreSQL
│   ├── 001_create_role.sql
│   ├── 002_create_database.sql
│   └── 003_grant_permissions.sql
└── README.md
```

## Порядок выполнения

### ClickHouse
1. `001_create_database.sql` - Создание базы данных langfuse
2. `002_create_user.sql` - Создание пользователя langfuse
3. `003_grant_permissions.sql` - Предоставление прав пользователю

### PostgreSQL
1. `001_create_role.sql` - Создание роли langfuse
2. `002_create_database.sql` - Создание базы данных langfuse
3. `003_grant_permissions.sql` - Предоставление прав роли

## Использование

Миграции должны выполняться в указанном порядке для каждой базы данных отдельно.

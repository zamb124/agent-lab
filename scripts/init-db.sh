#!/bin/bash
set -e

echo "Создание баз данных agents_db, shared_db и crm_db..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE agents_db;
    CREATE DATABASE shared_db;
    CREATE DATABASE crm_db;
    GRANT ALL PRIVILEGES ON DATABASE agents_db TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE shared_db TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE crm_db TO $POSTGRES_USER;
EOSQL

echo "Базы данных созданы успешно!"


#!/bin/bash
set -e

echo "Создание баз данных agents_db и shared_db..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE agents_db;
    CREATE DATABASE shared_db;
    GRANT ALL PRIVILEGES ON DATABASE agents_db TO $POSTGRES_USER;
    GRANT ALL PRIVILEGES ON DATABASE shared_db TO $POSTGRES_USER;
EOSQL

echo "Базы данных созданы успешно!"


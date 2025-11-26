#!/bin/bash
set -e

SSH_USER="zambas124"
SSH_HOST="46.21.244.79"
REMOTE_DIR="/opt/agents-lab"

SSH_OPTS="-o ConnectTimeout=30 -o ConnectionAttempts=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3"
SSH_CMD="ssh $SSH_OPTS -l $SSH_USER $SSH_HOST"
SCP_CMD="scp $SSH_OPTS"

PROD_DB_HOST="rc1b-gsgkmvrv04yanye2.mdb.yandexcloud.net:6432"
PROD_AGENTS_DB="postgresql+asyncpg://agent_user:agent_password@${PROD_DB_HOST}/agents_db"
PROD_SHARED_DB="postgresql+asyncpg://agent_user:agent_password@${PROD_DB_HOST}/shared_db"

LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "=== Deploy Agent Lab ==="
echo "Server: $SSH_USER@$SSH_HOST"
echo "Remote dir: $REMOTE_DIR"
echo ""

echo "[1/7] Git pull на сервере..."
$SSH_CMD "cd $REMOTE_DIR && git fetch origin && git reset --hard origin/main"
sleep 3

echo "[2/7] Подготовка конфигов..."
TMP_DIR=$(mktemp -d)

cp "$LOCAL_DIR/conf.json" "$TMP_DIR/conf.json"
cp "$LOCAL_DIR/apps/agents/conf.json" "$TMP_DIR/agents_conf.json"
cp "$LOCAL_DIR/apps/frontend/conf.json" "$TMP_DIR/frontend_conf.json"

# Замена URL баз данных
sed -i.bak "s|postgresql+asyncpg://[^\"]*agents_db|$PROD_AGENTS_DB|g" "$TMP_DIR/conf.json"
sed -i.bak "s|postgresql+asyncpg://[^\"]*shared_db|$PROD_SHARED_DB|g" "$TMP_DIR/conf.json"

sed -i.bak "s|postgresql+asyncpg://[^\"]*agents_db|$PROD_AGENTS_DB|g" "$TMP_DIR/agents_conf.json"
sed -i.bak "s|postgresql+asyncpg://[^\"]*shared_db|$PROD_SHARED_DB|g" "$TMP_DIR/agents_conf.json"

sed -i.bak "s|postgresql+asyncpg://[^\"]*agents_db|$PROD_AGENTS_DB|g" "$TMP_DIR/frontend_conf.json"
sed -i.bak "s|postgresql+asyncpg://[^\"]*shared_db|$PROD_SHARED_DB|g" "$TMP_DIR/frontend_conf.json"

# Замена env на production
sed -i.bak 's|"env": "local"|"env": "production"|g' "$TMP_DIR/conf.json"
sed -i.bak 's|"env": "local"|"env": "production"|g' "$TMP_DIR/agents_conf.json"
sed -i.bak 's|"env": "local"|"env": "production"|g' "$TMP_DIR/frontend_conf.json"

# Замена domain на agents-lab.ru
sed -i.bak 's|"domain": "localhost"|"domain": "agents-lab.ru"|g' "$TMP_DIR/conf.json"
sed -i.bak 's|"domain": "localhost"|"domain": "agents-lab.ru"|g' "$TMP_DIR/agents_conf.json"
sed -i.bak 's|"domain": "localhost"|"domain": "agents-lab.ru"|g' "$TMP_DIR/frontend_conf.json"

rm -f "$TMP_DIR"/*.bak

echo "[3/7] Копирование конфигов на сервер..."
sleep 2
$SCP_CMD "$TMP_DIR/conf.json" "$SSH_USER@$SSH_HOST:$REMOTE_DIR/conf.json"
sleep 2
$SCP_CMD "$TMP_DIR/agents_conf.json" "$SSH_USER@$SSH_HOST:$REMOTE_DIR/apps/agents/conf.json"
sleep 2
$SCP_CMD "$TMP_DIR/frontend_conf.json" "$SSH_USER@$SSH_HOST:$REMOTE_DIR/apps/frontend/conf.json"
sleep 2

rm -rf "$TMP_DIR"

echo "[4/7] Проверка nginx конфига..."
$SCP_CMD "$LOCAL_DIR/deploy/nginx.conf" "$SSH_USER@$SSH_HOST:/tmp/nginx.conf"
sleep 2
$SSH_CMD "sudo cp /tmp/nginx.conf /etc/nginx/sites-available/agents-lab.conf && sudo nginx -t"
sleep 2

echo "[5/7] Проверка SSL сертификатов..."
$SSH_CMD "sudo ls -la /etc/letsencrypt/live/agents-lab.ru-0001/ | head -5"
sleep 2

echo "[6/7] Перезапуск сервисов..."
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose down && sudo docker compose up -d --build"

echo "[7/7] Проверка сервисов..."
sleep 20

echo "Checking agents service (8001)..."
$SSH_CMD "curl -sf http://localhost:8001/health || echo 'FAIL: agents'"
sleep 2

echo "Checking frontend service (8002)..."
$SSH_CMD "curl -sf http://localhost:8002/health || echo 'FAIL: frontend'"
sleep 2

echo "Reloading nginx..."
$SSH_CMD "sudo systemctl reload nginx"

echo ""
echo "=== Deploy завершен ==="
echo "Agents: https://agents-lab.ru/api/v1/health"
echo "Frontend: https://agents-lab.ru/health"


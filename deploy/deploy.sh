#!/bin/bash
set -e

# === КОНФИГУРАЦИЯ ===
SSH_USER="zambas124"
SSH_HOST="46.21.244.79"
REMOTE_DIR="/opt/agents-lab"

# Список поддерживаемых доменов (должен совпадать с SUPPORTED_DOMAINS в core/utils/domain.py)
DOMAINS=("humanitec.ru" "agents-lab.ru")
PRIMARY_DOMAIN="humanitec.ru"

SSH_OPTS="-o ConnectTimeout=30 -o ConnectionAttempts=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3"
SSH_CMD="ssh $SSH_OPTS -l $SSH_USER $SSH_HOST"
SCP_CMD="scp $SSH_OPTS"

LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# === ФУНКЦИИ ===

# Проверка и получение SSL сертификата для домена
check_ssl_cert() {
    local domain=$1
    local cert_dir_wildcard="/etc/letsencrypt/live/${domain}-0001"
    local cert_dir_basic="/etc/letsencrypt/live/${domain}"
    
    echo "Checking SSL for ${domain}..."
    
    # Проверяем wildcard сертификат (предпочтительно)
    if $SSH_CMD "sudo test -d ${cert_dir_wildcard}"; then
        echo "  SSL for ${domain} (wildcard): OK"
        return 0
    fi
    
    # Проверяем базовый сертификат
    if $SSH_CMD "sudo test -d ${cert_dir_basic}"; then
        echo "  SSL for ${domain} (basic): OK"
        echo "  WARNING: Wildcard cert missing - subdomains may show SSL warnings"
        return 0
    fi
    
    # Сертификат не найден - предлагаем получить
    echo ""
    echo "  SSL for ${domain}: NOT FOUND"
    echo ""
    echo "  Для поддоменов (*.${domain}) нужен wildcard сертификат."
    echo "  Wildcard требует DNS challenge (добавление TXT записи)."
    echo ""
    read -p "  Хотите получить wildcard сертификат для ${domain}? (y/n): " answer
    
    if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
        obtain_wildcard_cert "$domain"
    else
        echo "  Пропускаем получение сертификата для ${domain}"
        echo "  WARNING: HTTPS для ${domain} и поддоменов не будет работать!"
    fi
}

# Получение wildcard сертификата через DNS challenge
obtain_wildcard_cert() {
    local domain=$1
    
    echo ""
    echo "=== Получение wildcard сертификата для ${domain} ==="
    echo ""
    echo "ИНСТРУКЦИЯ:"
    echo "1. Сейчас certbot покажет TXT запись которую нужно добавить в DNS"
    echo "2. Зайдите в панель управления DNS вашего регистратора"
    echo "3. Добавьте TXT запись:"
    echo "   - Имя: _acme-challenge"
    echo "   - Тип: TXT"
    echo "   - Значение: (то что покажет certbot)"
    echo "4. Подождите 1-2 минуты пока DNS обновится"
    echo "5. Нажмите Enter в certbot для продолжения"
    echo ""
    read -p "Нажмите Enter чтобы начать..."
    
    # Запускаем certbot в интерактивном режиме
    $SSH_CMD -t "sudo certbot certonly --manual --preferred-challenges dns -d '${domain}' -d '*.${domain}'"
    
    # Проверяем что сертификат получен
    if $SSH_CMD "sudo test -d /etc/letsencrypt/live/${domain}-0001"; then
        echo ""
        echo "  Wildcard сертификат для ${domain} успешно получен!"
    elif $SSH_CMD "sudo test -d /etc/letsencrypt/live/${domain}"; then
        echo ""
        echo "  Сертификат для ${domain} получен (возможно без wildcard)"
    else
        echo ""
        echo "  ОШИБКА: Не удалось получить сертификат для ${domain}"
        echo "  Проверьте логи: /var/log/letsencrypt/letsencrypt.log"
    fi
}

# === ОСНОВНОЙ СКРИПТ ===

echo "=== Deploy Humanitec ==="
echo "Server: $SSH_USER@$SSH_HOST"
echo "Remote dir: $REMOTE_DIR"
echo "Domains: ${DOMAINS[*]}"
echo ""

echo "[1/7] Git pull на сервере..."
$SSH_CMD "cd $REMOTE_DIR && git fetch origin && git reset --hard origin/main"
sleep 3

echo "[2/7] Остановка и очистка старых Docker образов..."
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose down || true"
$SSH_CMD "sudo docker image prune -af"
$SSH_CMD "sudo docker builder prune -af"
sleep 2

echo "[3/7] Проверка SSL сертификатов..."
for domain in "${DOMAINS[@]}"; do
    check_ssl_cert "$domain"
done
sleep 2

echo "[4/7] Проверка nginx конфига..."
$SCP_CMD "$LOCAL_DIR/deploy/nginx.conf" "$SSH_USER@$SSH_HOST:/tmp/nginx.conf"
sleep 2
$SSH_CMD "sudo cp /tmp/nginx.conf /etc/nginx/sites-available/humanitec.conf && sudo rm -f /etc/nginx/sites-enabled/agents-lab.ru /etc/nginx/sites-enabled/agents-lab.conf /etc/nginx/sites-enabled/humanitec.conf && sudo ln -s /etc/nginx/sites-available/humanitec.conf /etc/nginx/sites-enabled/humanitec.conf && sudo nginx -t"
sleep 2

echo "[5/7] Загрузка и запуск сервисов..."
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose pull"
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose up -d"

echo "[6/7] Проверка сервисов..."
sleep 20

echo "Checking agents service (8001)..."
$SSH_CMD "curl -sf http://localhost:8001/health || echo 'FAIL: agents'"
sleep 2

echo "Checking frontend service (8002)..."
$SSH_CMD "curl -sf http://localhost:8002/health || echo 'FAIL: frontend'"
sleep 2

echo "Checking crm service (8003)..."
$SSH_CMD "curl -sf http://localhost:8003/health || echo 'FAIL: crm'"
sleep 2

echo "Checking redis service..."
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose ps redis --format '{{.Status}}' | grep -q 'Up' && echo 'OK: redis running' || echo 'FAIL: redis'"
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose exec -T redis redis-cli ping || echo 'FAIL: redis not responding'"
sleep 2

echo "Checking taskiq-worker..."
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose ps taskiq-worker --format '{{.Status}}' | grep -q 'Up' && echo 'OK: taskiq-worker running' || echo 'FAIL: taskiq-worker'"
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose logs taskiq-worker --tail=5"
sleep 2

echo "Checking taskiq-scheduler..."
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose ps taskiq-scheduler --format '{{.Status}}' | grep -q 'Up' && echo 'OK: taskiq-scheduler running' || echo 'FAIL: taskiq-scheduler'"
sleep 2

echo "Checking chroma service (8100)..."
$SSH_CMD "cd $REMOTE_DIR && sudo docker compose ps chroma --format '{{.Status}}' | grep -q 'Up' && echo 'OK: chroma running' || echo 'FAIL: chroma'"
$SSH_CMD "curl -sf http://localhost:8100/api/v2/heartbeat || echo 'FAIL: chroma API not responding'"
sleep 2

echo "[7/7] Reloading nginx..."
$SSH_CMD "sudo systemctl reload nginx"

echo ""
echo "=== Deploy завершен ==="
echo "Primary: https://${PRIMARY_DOMAIN}"
echo "Agents API: https://${PRIMARY_DOMAIN}/agents/api/v1/health"
echo "CRM API: https://${PRIMARY_DOMAIN}/crm/api/v1/health"
echo "Frontend: https://${PRIMARY_DOMAIN}/health"
for domain in "${DOMAINS[@]}"; do
    if [[ "$domain" != "$PRIMARY_DOMAIN" ]]; then
        echo "Alt domain: https://${domain}"
    fi
done
echo "Worker logs: docker compose logs taskiq-worker"

  #!/bin/bash
set -e

# === КОНФИГУРАЦИЯ ===
SSH_USER="zambas124"
SSH_HOST="46.21.244.79"
REMOTE_DIR="/opt/agents-lab"
PRIMARY_DOMAIN="humanitec.ru"

SSH_OPTS="-o ConnectTimeout=30 -o ConnectionAttempts=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3"
SSH_CMD="ssh $SSH_OPTS -l $SSH_USER $SSH_HOST"
SCP_CMD="scp $SSH_OPTS"

LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# === ФУНКЦИИ ===

install_dependencies() {
    log_info "Проверка и установка зависимостей..."
    
    # Docker
    if ! $SSH_CMD "command -v docker &> /dev/null"; then
        log_info "Установка Docker..."
        $SSH_CMD "curl -fsSL https://get.docker.com | sudo sh"
        $SSH_CMD "sudo usermod -aG docker $SSH_USER"
        log_success "Docker установлен"
    else
        log_success "Docker уже установлен"
    fi
    
    # Docker Compose (plugin)
    if ! $SSH_CMD "docker compose version &> /dev/null"; then
        log_info "Установка Docker Compose..."
        $SSH_CMD "sudo apt-get update && sudo apt-get install -y docker-compose-plugin"
        log_success "Docker Compose установлен"
    else
        log_success "Docker Compose уже установлен"
    fi
    
    # Nginx
    if ! $SSH_CMD "command -v nginx &> /dev/null"; then
        log_info "Установка Nginx..."
        $SSH_CMD "sudo apt-get update && sudo apt-get install -y nginx"
        $SSH_CMD "sudo systemctl enable nginx"
        log_success "Nginx установлен"
    else
        log_success "Nginx уже установлен"
    fi
    
    # Certbot
    if ! $SSH_CMD "command -v certbot &> /dev/null"; then
        log_info "Установка Certbot..."
        $SSH_CMD "sudo apt-get update && sudo apt-get install -y certbot python3-certbot-nginx"
        log_success "Certbot установлен"
    else
        log_success "Certbot уже установлен"
    fi
    
    # Curl (для healthchecks)
    $SSH_CMD "command -v curl &> /dev/null || sudo apt-get install -y curl" 2>/dev/null || true
}

check_ssl_cert() {
    local domain=$1
    local cert_dir_wildcard="/etc/letsencrypt/live/${domain}-0001"
    local cert_dir_basic="/etc/letsencrypt/live/${domain}"
    
    log_info "Проверка SSL для ${domain}..."
    
    # Проверяем wildcard сертификат
    if $SSH_CMD "sudo test -d ${cert_dir_wildcard}"; then
        log_success "SSL для ${domain} (wildcard): OK"
        return 0
    fi
    
    # Проверяем базовый сертификат
    if $SSH_CMD "sudo test -d ${cert_dir_basic}"; then
        log_success "SSL для ${domain} (basic): OK"
        log_warn "Wildcard сертификат отсутствует - субдомены могут показывать предупреждения SSL"
        return 0
    fi
    
    # Сертификат не найден
    echo ""
    log_warn "SSL для ${domain}: НЕ НАЙДЕН"
    echo ""
    echo "  Для субдоменов (*.${domain}) нужен wildcard сертификат."
    echo "  Wildcard требует DNS challenge (добавление TXT записи)."
    echo ""
    read -p "  Получить wildcard сертификат для ${domain}? (y/n): " answer
    
    if [[ "$answer" == "y" || "$answer" == "Y" ]]; then
        obtain_wildcard_cert "$domain"
    else
        log_warn "Пропускаем получение сертификата. HTTPS может не работать!"
    fi
}

obtain_wildcard_cert() {
    local domain=$1
    
    echo ""
    log_info "=== Получение wildcard сертификата для ${domain} ==="
    echo ""
    echo "ИНСТРУКЦИЯ:"
    echo "1. Certbot покажет TXT запись которую нужно добавить в DNS"
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
    
    # Проверяем результат
    if $SSH_CMD "sudo test -d /etc/letsencrypt/live/${domain}-0001"; then
        log_success "Wildcard сертификат для ${domain} успешно получен!"
    elif $SSH_CMD "sudo test -d /etc/letsencrypt/live/${domain}"; then
        log_success "Сертификат для ${domain} получен (возможно без wildcard)"
    else
        log_error "Не удалось получить сертификат для ${domain}"
        log_info "Проверьте логи: /var/log/letsencrypt/letsencrypt.log"
    fi
}

setup_nginx() {
    log_info "Настройка Nginx..."
    
    # Копируем конфиг
    $SCP_CMD "$LOCAL_DIR/deploy/nginx.conf" "$SSH_USER@$SSH_HOST:/tmp/nginx.conf"
    
    # Устанавливаем конфиг
    $SSH_CMD "sudo cp /tmp/nginx.conf /etc/nginx/sites-available/humanitec.conf"
    
    # Удаляем старые симлинки
    $SSH_CMD "sudo rm -f /etc/nginx/sites-enabled/agents-lab.ru /etc/nginx/sites-enabled/agents-lab.conf /etc/nginx/sites-enabled/humanitec.conf /etc/nginx/sites-enabled/default"
    
    # Создаем симлинк
    $SSH_CMD "sudo ln -sf /etc/nginx/sites-available/humanitec.conf /etc/nginx/sites-enabled/humanitec.conf"
    
    # Проверяем синтаксис
    if $SSH_CMD "sudo nginx -t"; then
        log_success "Nginx конфиг валиден"
        $SSH_CMD "sudo systemctl reload nginx"
        log_success "Nginx перезагружен"
    else
        log_error "Ошибка в конфиге Nginx!"
        exit 1
    fi
}

deploy_docker() {
    log_info "Деплой Docker сервисов..."
    
    # Остановка старых контейнеров
    log_info "Остановка старых контейнеров..."
    $SSH_CMD "cd $REMOTE_DIR && sudo docker compose -f docker-compose-prod.yaml down || true"
    
    # Очистка старых образов
    log_info "Очистка старых образов..."
    $SSH_CMD "sudo docker image prune -af" || true
    $SSH_CMD "sudo docker builder prune -af" || true
    
    # Сборка образов
    log_info "Сборка Docker образов..."
    $SSH_CMD "cd $REMOTE_DIR && sudo docker compose -f docker-compose-prod.yaml build"
    log_success "Образы собраны"
    
    # Запуск сервисов
    log_info "Запуск Docker сервисов..."
    $SSH_CMD "cd $REMOTE_DIR && sudo docker compose -f docker-compose-prod.yaml up -d"
    
    log_success "Docker сервисы запущены"
}

healthcheck_service() {
    local name=$1
    local url=$2
    local max_attempts=${3:-30}
    local attempt=1
    
    echo -n "  Проверка $name... "
    
    while [ $attempt -le $max_attempts ]; do
        if $SSH_CMD "curl -sf $url" &>/dev/null; then
            echo -e "${GREEN}OK${NC}"
            return 0
        fi
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo -e "${RED}FAIL${NC}"
    return 1
}

healthcheck_container() {
    local name=$1
    local container=$2
    
    echo -n "  Проверка $name... "
    
    if $SSH_CMD "cd $REMOTE_DIR && sudo docker compose -f docker-compose-prod.yaml ps $container --format '{{.Status}}'" 2>/dev/null | grep -q 'Up'; then
        echo -e "${GREEN}OK${NC}"
        return 0
    fi
    
    echo -e "${RED}FAIL${NC}"
    return 1
}

run_healthchecks() {
    log_info "Проверка здоровья сервисов..."
    
    # Ждем запуска
    log_info "Ожидание запуска сервисов (30 сек)..."
    sleep 30
    
    local failed=0
    
    # HTTP сервисы
    healthcheck_service "agents (8001)" "http://localhost:8001/health" || failed=1
    healthcheck_service "frontend (8002)" "http://localhost:8002/health" || failed=1
    healthcheck_service "crm (8003)" "http://localhost:8003/health" || failed=1
    healthcheck_service "rag (8004)" "http://localhost:8004/health" || failed=1
    # pgvector использует PostgreSQL, отдельный healthcheck не нужен
    
    # Контейнеры без HTTP
    healthcheck_container "redis" "redis" || failed=1
    healthcheck_container "postgres" "postgres" || failed=1
    healthcheck_container "worker" "worker" || failed=1
    healthcheck_container "scheduler" "scheduler" || failed=1
    healthcheck_container "rag-worker" "rag-worker" || failed=1
    
    if [ $failed -eq 1 ]; then
        log_error "Некоторые сервисы не прошли проверку!"
        log_info "Просмотр логов: ssh $SSH_USER@$SSH_HOST 'cd $REMOTE_DIR && sudo docker compose -f docker-compose-prod.yaml logs <service>'"
        return 1
    fi
    
    log_success "Все сервисы работают!"
}

# === ОСНОВНОЙ СКРИПТ ===

echo ""
echo "============================================="
echo "       DEPLOY HUMANITEC PLATFORM"
echo "============================================="
echo ""
echo "Server: $SSH_USER@$SSH_HOST"
echo "Remote dir: $REMOTE_DIR"
echo "Domain: $PRIMARY_DOMAIN"
echo ""

# [1] Установка зависимостей
echo ""
echo "[1/7] Установка зависимостей..."
echo "---------------------------------------------"
install_dependencies

# [2] Git pull
echo ""
echo "[2/7] Git pull..."
echo "---------------------------------------------"
log_info "Получение последних изменений..."
$SSH_CMD "cd $REMOTE_DIR && git fetch origin && git reset --hard origin/main"
log_success "Код обновлен"

# [3] Копирование конфигов с секретами
echo ""
echo "[3/7] Копирование конфигов..."
echo "---------------------------------------------"
if [ -f "$LOCAL_DIR/conf.local.json" ]; then
    log_info "Копирование conf.local.json (секреты)..."
    $SCP_CMD "$LOCAL_DIR/conf.local.json" "$SSH_USER@$SSH_HOST:$REMOTE_DIR/conf.local.json"
    log_success "conf.local.json скопирован"
    
    # Проверяем наличие VAPID ключей для PWA Push Notifications
    if grep -q '"vapid_public_key"' "$LOCAL_DIR/conf.local.json"; then
        log_success "VAPID ключи для Push Notifications: OK"
    else
        log_warn "VAPID ключи не найдены в conf.local.json!"
        log_info "Push уведомления не будут работать без VAPID ключей"
        log_info "Сгенерируйте ключи: python scripts/generate_vapid_keys.py"
    fi
else
    log_warn "conf.local.json не найден локально!"
    log_error "Секреты (auth, llm, push) не будут работать!"
fi

# [4] SSL сертификаты
echo ""
echo "[4/7] SSL сертификаты..."
echo "---------------------------------------------"
check_ssl_cert "$PRIMARY_DOMAIN"

# [5] Настройка Nginx
echo ""
echo "[5/7] Настройка Nginx..."
echo "---------------------------------------------"
setup_nginx

# [6] Docker Compose
echo ""
echo "[6/7] Docker Compose (build & up)..."
echo "---------------------------------------------"
deploy_docker

# [7] Healthchecks
echo ""
echo "[7/7] Проверка здоровья..."
echo "---------------------------------------------"
run_healthchecks

# Итог
echo ""
echo "============================================="
echo "       DEPLOY ЗАВЕРШЕН"
echo "============================================="
echo ""
echo "Сайт:       https://${PRIMARY_DOMAIN}"
echo "Agents API: https://${PRIMARY_DOMAIN}/agents/api/v1/health"
echo "CRM API:    https://${PRIMARY_DOMAIN}/crm/api/v1/health"
echo "Frontend:   https://${PRIMARY_DOMAIN}/health"
echo ""
echo "Логи:       ssh $SSH_USER@$SSH_HOST 'cd $REMOTE_DIR && sudo docker compose -f docker-compose-prod.yaml logs -f'"
echo ""

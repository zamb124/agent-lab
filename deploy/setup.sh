#!/bin/bash

# Скрипт развертывания платформы agents-lab в облаке
set -e

echo "🚀 Начинаем развертывание agents-lab платформы..."

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для логирования
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Проверка что скрипт запущен от root
if [[ $EUID -ne 0 ]]; then
   error "Этот скрипт должен быть запущен от root (используйте sudo)"
   exit 1
fi

# 1. Обновление системы
log "Обновляем систему..."
apt update && apt upgrade -y

# 2. Установка необходимых пакетов
log "Устанавливаем необходимые пакеты..."
apt install -y curl wget git nginx certbot python3-certbot-nginx ufw

# 3. Установка Docker
log "Устанавливаем Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    usermod -aG docker $SUDO_USER
    rm get-docker.sh
else
    log "Docker уже установлен"
fi

# 4. Установка Docker Compose
log "Устанавливаем Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
else
    log "Docker Compose уже установлен"
fi

# 5. Настройка firewall
log "Настраиваем firewall..."
ufw --force enable
ufw allow ssh
ufw allow 'Nginx Full'
ufw allow 80
ufw allow 443

# 6. Создание директории для проекта
log "Создаем директорию проекта..."
PROJECT_DIR="/opt/agents-lab"
mkdir -p $PROJECT_DIR
cd $PROJECT_DIR

# 7. Клонирование репозитория
log "Клонируем репозиторий..."
if [ ! -d ".git" ]; then
    git clone https://github.com/zamb124/agent-lab.git .
else
    log "Репозиторий уже клонирован, обновляем..."
    git pull origin main
fi

# 8. Копирование конфигурации nginx
log "Настраиваем nginx..."
cp deploy/nginx.conf /etc/nginx/sites-available/agents-lab.ru
ln -sf /etc/nginx/sites-available/agents-lab.ru /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# 9. Тестирование конфигурации nginx
log "Тестируем конфигурацию nginx..."
nginx -t

log "✅ Базовая настройка сервера завершена!"
log "📋 Следующие шаги:"
log "1. Создайте файл conf.json с вашими настройками"
log "2. Создайте файл .env с паролем базы данных: POSTGRES_PASSWORD=ваш_пароль"
log "3. Получите SSL сертификат: certbot --nginx -d agents-lab.ru"
log "4. Запустите сервисы: docker-compose -f deploy/docker-compose.prod.yml up -d"

echo -e "${GREEN}🎉 Настройка завершена! Сервер готов к развертыванию.${NC}"

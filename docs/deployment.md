# Развертывание agents-lab в облаке

Пошаговое руководство по развертыванию платформы agents-lab на облачном сервере.

## Предварительные требования

- Облачный сервер с Ubuntu 20.04/22.04
- Домен agents-lab.ru, настроенный на IP сервера
- SSH доступ к серверу с правами sudo

## Быстрое развертывание

### 1. Подготовка сервера

Подключитесь к серверу по SSH и выполните:

```bash
# Скачиваем и запускаем скрипт установки
wget https://raw.githubusercontent.com/zamb124/agent-lab/main/deploy/setup.sh
chmod +x setup.sh
sudo ./setup.sh
```

### 2. Настройка конфигурации

Создайте конфигурационный файл:

```bash
cd /opt/agents-lab
sudo nano conf.json
```

Пример содержимого conf.json:
```json
{
  "database": {
    "url": "postgresql://agents_lab_user:PASSWORD@localhost:5432/agents_lab"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 8001
  },
  "auth": {
    "secret_key": "your-secret-key-here"
  }
}
```

### 3. Настройка переменных окружения

```bash
# Создаем файл с переменными окружения
sudo nano .env
```

Содержимое .env:
```
POSTGRES_PASSWORD=your-secure-password-here
```

### 4. Получение SSL сертификата

```bash
sudo certbot --nginx -d agents-lab.ru
```

### 5. Запуск сервисов

```bash
sudo docker-compose -f deploy/docker-compose.prod.yml up -d
```

### 6. Проверка статуса

```bash
# Проверяем статус контейнеров
sudo docker-compose -f deploy/docker-compose.prod.yml ps

# Проверяем логи
sudo docker-compose -f deploy/docker-compose.prod.yml logs -f app
```

## Управление сервисом

### Остановка сервисов
```bash
sudo docker-compose -f deploy/docker-compose.prod.yml down
```

### Перезапуск сервисов
```bash
sudo docker-compose -f deploy/docker-compose.prod.yml restart
```

### Обновление кода
```bash
cd /opt/agents-lab
git pull origin main
sudo docker-compose -f deploy/docker-compose.prod.yml build app
sudo docker-compose -f deploy/docker-compose.prod.yml up -d
```

### Просмотр логов
```bash
# Логи приложения
sudo docker-compose -f deploy/docker-compose.prod.yml logs -f app

# Логи базы данных
sudo docker-compose -f deploy/docker-compose.prod.yml logs -f postgres

# Логи nginx
sudo tail -f /var/log/nginx/agents-lab.access.log
sudo tail -f /var/log/nginx/agents-lab.error.log
```

## Мониторинг

### Проверка работоспособности
```bash
# Проверка ответа сервиса
curl -I https://agents-lab.ru

# Проверка статуса nginx
sudo systemctl status nginx

# Проверка статуса контейнеров
sudo docker ps
```

### Резервное копирование базы данных
```bash
# Создание бэкапа
sudo docker exec agents-lab-postgres pg_dump -U agents_lab_user agents_lab > backup_$(date +%Y%m%d_%H%M%S).sql

# Восстановление из бэкапа
sudo docker exec -i agents-lab-postgres psql -U agents_lab_user agents_lab < backup.sql
```

## Устранение неполадок

### Проблемы с SSL
```bash
# Обновление сертификата
sudo certbot renew

# Проверка конфигурации nginx
sudo nginx -t
sudo systemctl reload nginx
```

### Проблемы с Docker
```bash
# Пересборка контейнеров
sudo docker-compose -f deploy/docker-compose.prod.yml build --no-cache
sudo docker-compose -f deploy/docker-compose.prod.yml up -d
```

### Проблемы с базой данных
```bash
# Подключение к базе данных
sudo docker exec -it agents-lab-postgres psql -U agents_lab_user agents_lab

# Просмотр логов PostgreSQL
sudo docker-compose -f deploy/docker-compose.prod.yml logs postgres
```

## Безопасность

- Регулярно обновляйте систему: `sudo apt update && sudo apt upgrade`
- Обновляйте Docker образы: `sudo docker-compose pull`
- Проверяйте логи на подозрительную активность
- Используйте сильные пароли для базы данных
- Настройте автоматическое обновление SSL сертификатов

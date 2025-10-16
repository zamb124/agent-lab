# Подключение платформ

Этот гайд научит вас подключать ботов к различным платформам: Telegram, WhatsApp, веб-сайтам и API. После подключения бот сможет общаться с пользователями в выбранных каналах.

## 🌐 Обзор платформ

### Доступные платформы

| Платформа | Тип | Сложность | Стоимость |
|-----------|-----|-----------|----------|
| **Telegram** | Messenger | ⭐⭐ | Бесплатно |
| **WhatsApp** | Messenger | ⭐⭐⭐ | Бесплатно* |
| **Web Chat** | Website | ⭐ | Бесплатно |
| **API** | Integration | ⭐⭐⭐⭐ | Pay-as-you-go |

!!! info "*WhatsApp Business API"
    Требует регистрации в Meta Business, но не платит Meta напрямую.

### Когда использовать каждую платформу

#### Telegram
✅ **Для начала работы**  
✅ **Быстрая настройка**  
✅ **Тестирование и разработка**  
✅ **Сообщества и группы**  

#### WhatsApp
✅ **Бизнес-коммуникации**  
✅ **Высокая вовлеченность**  
✅ **Официальные каналы**  
✅ **B2C и B2B**  

#### Web Chat
✅ **Корпоративные сайты**  
✅ **SaaS платформы**  
✅ **Поддержка на сайте**  
✅ **Лидогенерация**  

#### API
✅ **Интеграция с CRM**  
✅ **Внутренние системы**  
✅ **Автоматизация процессов**  
✅ **Программные клиенты**  

## 📱 Telegram

Самая простая платформа для начала работы.

### Шаг 1: Создание бота в Telegram

#### 1.1 Запуск BotFather

Откройте Telegram и найдите **@BotFather**:

![BotFather в Telegram](img/telegram_botfather.png)

#### 1.2 Создание нового бота

1. Отправьте команду **`/newbot`**
2. Введите **имя бота** (например, "Мой помощник")
3. Введите **username** (должен заканчиваться на `bot`)

!!! warning "Username правила"
    - Только латинские буквы, цифры, подчеркивания
    - От 5 до 32 символов
    - Должен быть уникальным
    - Пример: `mycompany_support_bot`

#### 1.3 Получение токена

BotFather отправит сообщение с **токеном**:

![Токен от BotFather](img/telegram_token.png)

**Пример токена:**
```
123456789:ABCdefGHIjklMNOpqrsTUVwxyz123456789
```

!!! danger "Сохраните токен!"
    Токен - это пароль бота. Не делитесь им и храните в безопасности.

### Шаг 2: Настройка в Agent Lab

#### 2.1 Открываем настройки бота

1. Перейдите в **"Боты"**
2. Кликните на нужного бота
3. Найдите раздел **"Платформы"**

![Раздел платформ](img/platforms_section.png)

#### 2.2 Включаем Telegram

1. **Найдите блок Telegram**
2. **Поставьте галочку** "Включено"
3. **Вставьте токен** в поле
4. **Нажмите "Сохранить"**

![Настройка Telegram в Agent Lab](img/platform_telegram_setup.png)

### Шаг 3: Тестирование

#### 3.1 Проверка статуса

После сохранения статус должен измениться на **"Подключено"**:

![Статус подключения](img/platform_status_connected.png)

#### 3.2 Тестовый диалог

1. Откройте Telegram
2. Найдите вашего бота по username
3. Отправьте сообщение **`/start`**

![Тест бота в Telegram](img/telegram_test_bot.png)

!!! success "Готово!"
    Если бот ответил - поздравляем! Telegram настроен.

### Дополнительные настройки

#### Команды бота

Создайте меню команд через BotFather:

1. Отправьте **`/setcommands`** BotFather'у
2. Выберите вашего бота
3. Отправьте список команд:

```
/start - Начать работу
/help - Помощь
/support - Связаться с поддержкой
```

#### Описание бота

Улучшите описание для пользователей:

1. **`/setdescription`** - основное описание
2. **`/setabouttext`** - краткое описание

#### Webhook vs Long Polling

Agent Lab использует **Long Polling** - не нужно настраивать webhook URL.

### Устранение проблем

#### Бот не отвечает

**Проверьте:**
- ✅ Токен введен правильно
- ✅ Бот включен в настройках
- ✅ Нет опечаток в токене

#### Ошибка "Invalid token"

**Решения:**
- 🔄 Получите новый токен у BotFather
- 👀 Проверьте на лишние пробелы
- 🔒 Убедитесь, что токен не скомпрометирован

#### Бот отвечает, но медленно

**Оптимизации:**
- ⚡ Выберите быструю модель ИИ
- 📝 Сократите промпт
- 🔧 Настройте таймауты

## 💬 WhatsApp Business

Профессиональная платформа для бизнес-коммуникаций.

### Шаг 1: Регистрация в Meta Business

#### 1.1 Создание Business аккаунта

1. Перейдите на [business.facebook.com](https://business.facebook.com)
2. Создайте **Business аккаунт**
3. Подтвердите email и телефон

#### 1.2 Регистрация приложения

1. Перейдите в [developers.facebook.com](https://developers.facebook.com)
2. Нажмите **"Create App"**
3. Выберите **"Business"**
4. Укажите название приложения

![Создание приложения Meta](img/whatsapp_meta_app.png)

#### 1.3 Добавление WhatsApp

1. В приложении нажмите **"Add Product"**
2. Найдите **"WhatsApp"**
3. Нажмите **"Set Up"**

### Шаг 2: Настройка WhatsApp

#### 2.1 Получение Phone Number ID

После настройки WhatsApp вы получите:

- **Phone Number ID** - уникальный ID номера
- **Access Token** - токен для API
- **Webhook URL** - для получения сообщений

![WhatsApp настройки](img/whatsapp_credentials.png)

#### 2.2 Настройка номера телефона

1. В разделе WhatsApp добавьте **номер телефона**
2. Подтвердите владение номером через SMS
3. Получите **Phone Number ID**

!!! warning "Требования к номеру"
    - Номер должен быть рабочим
    - Не использовать для личных сообщений
    - Рекомендуется виртуальный номер

### Шаг 3: Настройка Webhook

#### 3.1 В Meta Developers

1. Перейдите в **"Webhooks"**
2. Нажмите **"Add Callback URL"**
3. Введите URL webhook'а:

```
https://{company_subdomain}.agents-lab.ru/api/v1/webhook/whatsapp/{bot_id}
```

4. Укажите **Verify Token** (придумайте пароль)

![Настройка webhook](img/whatsapp_webhook_setup.png)

#### 3.2 Подписка на события

Подпишитесь на события:
- ✅ `messages` - входящие сообщения
- ✅ `message_deliveries` - статус доставки
- ✅ `message_reads` - прочтение сообщений

### Шаг 4: Настройка в Agent Lab

#### 4.1 Ввод данных

1. В настройках бота найдите **WhatsApp**
2. Включите платформу
3. Введите данные:

- **Phone Number ID**
- **Access Token**
- **Verify Token** (тот же, что в Meta)

![WhatsApp в Agent Lab](img/platform_whatsapp_setup.png)

#### 4.2 Сохранение

Нажмите **"Сохранить"** - бот подключится автоматически.

### Шаг 5: Тестирование

#### 5.1 Проверка статуса

Статус должен стать **"Подключено"**:

![Статус WhatsApp](img/whatsapp_status_connected.png)

#### 5.2 Отправка тестового сообщения

1. Отправьте сообщение на настроенный номер
2. Должно прийти автоматическое приветствие

!!! success "Важно!"
    WhatsApp может проверять сообщения 1-2 минуты при первом подключении.

### Продвинутые возможности

#### Шаблонные сообщения

Для маркетинговых рассылок:

1. Создайте шаблон в Meta Business Manager
2. Одобрите шаблон (может занять до 24 часов)
3. Используйте в Agent Lab через API

#### Медиа-файлы

Бот поддерживает:
- 📷 **Изображения** - JPG, PNG
- 📹 **Видео** - MP4, до 16MB
- 📄 **Документы** - PDF, DOC, etc.
- 🎵 **Аудио** - MP3, OGG

### Устранение проблем

#### Webhook не работает

**Проверьте:**
- ✅ URL webhook'а правильный
- ✅ HTTPS включен
- ✅ Verify Token совпадает
- ✅ Сертификат SSL валидный

#### Сообщения не приходят

**Решения:**
- 🔄 Переподключите webhook
- 📱 Проверьте номер телефона
- 🔑 Обновите Access Token

#### Ошибка авторизации

**Проверьте:**
- ✅ Access Token не истек
- ✅ Phone Number ID правильный
- ✅ Приложение не заблокировано Meta

## 🌐 Web Chat виджет

Встраиваемый чат для вашего сайта.

### Шаг 1: Включение виджета

#### 1.1 В настройках бота

1. Найдите **"Web Chat"**
2. Поставьте галочку **"Включено"**
3. Нажмите **"Сохранить"**

![Включение Web Chat](img/platform_webchat_enable.png)

#### 1.2 Получение кода

После сохранения появится код для вставки:

![Код Web Chat виджета](img/webchat_code.png)

### Шаг 2: Установка на сайт

#### 2.1 HTML код

Вставьте код перед закрывающим `</body>`:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Мой сайт</title>
</head>
<body>
    <!-- Контент сайта -->
    
    <!-- Agent Lab Chat Widget -->
    <script>
        window.agentLabConfig = {
            botId: 'your_bot_id',
            apiUrl: 'https://{company_subdomain}.agents-lab.ru'
        };
    </script>
    <script src="https://{company_subdomain}.agents-lab.ru/static/chat-widget.js"></script>
</body>
</html>
```

#### 2.2 Конфигурация

Настройте виджет через `window.agentLabConfig`:

```javascript
window.agentLabConfig = {
    botId: 'your_bot_id',           // ID вашего бота
    apiUrl: 'https://{company_subdomain}.agents-lab.ru', // URL Agent Lab
    theme: 'light',                 // light/dark/auto
    position: 'bottom-right',       // bottom-right/bottom-left
    language: 'ru',                 // язык интерфейса
    welcomeMessage: 'Привет! Чем могу помочь?', // приветствие
    avatar: '/img/avatar.png',      // аватар бота
    brandColor: '#007bff'           // цвет бренда
};
```

### Шаг 3: Кастомизация

#### 3.1 CSS стили

Переопределите стили виджета:

```css
/* Кастомные стили для чата */
.agentlab-chat-widget {
    --primary-color: #007bff;
    --font-family: 'Roboto', sans-serif;
}

.agentlab-chat-button {
    background: linear-gradient(45deg, #007bff, #0056b3);
}
```

#### 3.2 JavaScript API

Управляйте виджетом программно:

```javascript
// Открыть чат
window.AgentLabChat.open();

// Закрыть чат
window.AgentLabChat.close();

// Отправить сообщение
window.AgentLabChat.sendMessage('Привет!');

// Проверить статус
const isOpen = window.AgentLabChat.isOpen();
```

### Шаг 4: Тестирование

#### 4.1 Локальное тестирование

1. Откройте HTML файл локально
2. Проверьте загрузку виджета
3. Тестируйте отправку сообщений

#### 4.2 На сервере

1. Загрузите файлы на сервер
2. Проверьте HTTPS
3. Тестируйте в разных браузерах

### Дополнительные возможности

#### Интеграция с CRM

Автоматическая передача данных о посетителях:

```javascript
window.agentLabConfig = {
    // ... другие настройки
    userData: {
        name: 'Иван Иванов',
        email: 'ivan@example.com',
        company: 'ООО Рога и Копыта'
    }
};
```

#### Аналитика

Отслеживание взаимодействия:

```javascript
window.agentLabConfig = {
    analytics: {
        googleAnalytics: 'GA_TRACKING_ID',
        yandexMetrika: 'YM_COUNTER_ID'
    }
};
```

## 🔌 API интеграция

Прямой доступ к боту через REST API.

### Базовое использование

#### Отправка сообщения

```bash
curl -X POST https://{company_subdomain}.agents-lab.ru/api/v1/flow/{bot_id}/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "Привет!",
    "user_id": "user123",
    "metadata": {
      "source": "website",
      "user_agent": "Mozilla/5.0..."
    }
  }'
```

#### Получение истории

```bash
curl -X GET https://{company_subdomain}.agents-lab.ru/api/v1/flow/{bot_id}/history \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Аутентификация

#### Получение токена

```bash
curl -X POST https://{company_subdomain}.agents-lab.ru/auth/token \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_username",
    "password": "your_password"
  }'
```

### Webhook для входящих сообщений

Настройте webhook для получения ответов бота:

```javascript
// Пример сервера на Node.js
const express = require('express');
const app = express();

app.post('/webhook/agentlab', (req, res) => {
    const { message, user_id, bot_id } = req.body;
    
    // Обработать сообщение от бота
    console.log(`Бот ${bot_id} ответил пользователю ${user_id}: ${message}`);
    
    res.sendStatus(200);
});

app.listen(3000);
```

### Интеграция с CRM

#### AmoCRM

```javascript
// Создание сделки при новом лиде
const response = await fetch('/api/v1/flow/sales-bot/invoke', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
    },
    body: JSON.stringify({
        message: `Новый лид: ${userName} из ${city}`,
        user_id: userId,
        metadata: {
            source: 'website_form',
            create_deal: true
        }
    })
});
```

### Мониторинг и отладка

#### Логирование запросов

```javascript
// Логирование всех API вызовов
const originalFetch = window.fetch;
window.fetch = function(...args) {
    console.log('API Request:', args);
    return originalFetch.apply(this, args);
};
```

#### Обработка ошибок

```javascript
try {
    const response = await fetch('/api/v1/flow/bot/invoke', {
        // ... настройки
    });
    
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    // Обработать успешный ответ
    
} catch (error) {
    console.error('Ошибка API:', error);
    // Показать пользователю сообщение об ошибке
}
```

## 📊 Мониторинг платформ

### Общий дашборд

В разделе **"Боты"** отслеживайте статус всех платформ:

![Статус платформ](img/platforms_status_dashboard.png)

### Аналитика по платформам

В разделе **"История"** фильтруйте по платформе:

![Аналитика платформ](img/platforms_analytics.png)

### Уведомления

Настройте оповещения о проблемах:

- 🔴 **Платформа отключена**
- 🟡 **Высокая нагрузка**
- 🟠 **Ошибки в ответах**

## 🚨 Устранение неисправностей

### Общие проблемы

#### Бот не подключается

**Проверьте:**
- ✅ Токены и ключи актуальны
- ✅ URL и порты доступны
- ✅ Сертификаты SSL валидны
- ✅ Квоты не превышены

#### Медленные ответы

**Решения:**
- ⚡ Выберите быструю модель ИИ
- 📝 Оптимизируйте промпты
- 🔧 Настройте кэширование
- 📊 Масштабируйте инфраструктуру

#### Сообщения теряются

**Диагностика:**
- 📋 Проверьте логи платформы
- 🔍 Проверьте webhook'и
- 📊 Мониторьте нагрузку
- 🔄 Перезапустите интеграции

### Специфические проблемы

#### Telegram
- **Блокировка** - проверьте правила Telegram
- **Лимиты** - 30 сообщений/секунду
- **Медиа** - ограничения на размер файлов

#### WhatsApp
- **Качество номера** - Meta проверяет номера
- **Шаблоны** - одобрение занимает время
- **Стоимость** - зависит от региона

#### Web Chat
- **CORS** - настройте заголовки
- **HTTPS** - обязателен для продакшена
- **Блокировщики** - проверьте CSP политики

## 💰 Стоимость использования

### Бесплатные лимиты

| Платформа | Лимит | Период |
|-----------|-------|--------|
| Telegram | 1000 сообщений | Месяц |
| WhatsApp | 250 сообщений | День |
| Web Chat | Неограничено | - |
| API | 10000 запросов | Месяц |

### Платные тарифы

- **Telegram**: +0.01₽ за сообщение после лимита
- **WhatsApp**: +0.05₽ за сообщение (Meta + Agent Lab)
- **Web Chat**: Бесплатно
- **API**: +0.001₽ за запрос

### Оптимизация расходов

1. **Кэширование** ответов
2. **Ограничение частоты** запросов
3. **Использование лимитов**
4. **Мониторинг** расходов

---

**Подключение платформ - ключ к успеху вашего бота!** 🚀📱

[Создание ботов](bots_creation.md) | [Биллинг](billing.md) | [Устранение проблем](troubleshooting.md)
# Платформы и интеграции

Agent Lab поддерживает множество платформ для развертывания ваших ботов. Каждая платформа имеет свои особенности и возможности.

## Поддерживаемые платформы

- **Telegram** - мессенджер с широкой аудиторией
- **WhatsApp** - бизнес-мессенджер
- **Web Chat** - виджет для сайта
- **AmoCRM** - интеграция с CRM
- **API** - прямой REST API доступ

## Telegram

### Возможности

- Текстовые сообщения
- Изображения и файлы
- Голосовые сообщения (распознавание речи)
- Кнопки и inline клавиатуры
- Команды (слеш-команды)
- Группы и каналы

### Настройка

**Шаг 1: Создание бота**

1. Напишите [@BotFather](https://t.me/botfather) в Telegram
2. Отправьте `/newbot`
3. Укажите название бота
4. Укажите username (должен заканчиваться на `_bot`)
5. Получите токен

**Шаг 2: Настройка в Agent Lab**

1. Откройте настройки вашего бота
2. В разделе "Платформы" включите Telegram
3. Вставьте токен
4. Нажмите "Сохранить"

**Шаг 3: Тестирование**

1. Найдите вашего бота в Telegram по username
2. Отправьте `/start`
3. Начните диалог

### Особенности

**Long Polling**
Agent Lab использует long polling режим - не требуется настройка webhook и SSL сертификата.

**Команды**
Добавьте команды через BotFather:
```
/start - Начать диалог
/help - Получить помощь
/reset - Сбросить контекст
```

**Файлы**
Бот может принимать и отправлять:
- Изображения (до 10MB)
- Документы (до 50MB)
- Голосовые сообщения (автоматическое распознавание)

## WhatsApp

### Возможности

- Текстовые сообщения
- Изображения и видео
- Документы
- Аудио сообщения
- Шаблонные сообщения (для первого контакта)
- Кнопки quick reply

### Настройка

**Шаг 1: Регистрация в Meta**

1. Создайте аккаунт Meta Business Suite
2. Создайте приложение WhatsApp Business
3. Настройте номер телефона

**Шаг 2: Получение токенов**

1. В настройках приложения найдите:
   - **Phone Number ID**
   - **Access Token** (permanent token)
2. Создайте **Webhook Verify Token** (произвольная строка)

**Шаг 3: Настройка в Agent Lab**

1. Откройте настройки бота
2. Включите WhatsApp
3. Укажите:
   - Phone Number ID
   - Access Token
   - Verify Token
4. Сохраните

**Шаг 4: Настройка Webhook в Meta**

1. В настройках WhatsApp Business найдите "Webhooks"
2. Нажмите "Edit"
3. Укажите:
   - **URL**: `https://your-domain.com/api/v1/webhook/whatsapp/company:YOUR_COMPANY_ID:flow:YOUR_FLOW_ID`
   - **Verify Token**: тот же, что в Agent Lab
4. Подпишитесь на события:
   - `messages`
   - `message_status`
5. Проверьте подключение

### Особенности

**Шаблонные сообщения**
Для первого контакта с пользователем требуется утвержденный шаблон. Создайте шаблоны в Meta Business Suite.

**Ограничения**
- Первым может писать только пользователь или используйте шаблон
- Окно для ответа - 24 часа после последнего сообщения пользователя
- Лимиты на отправку в зависимости от tier аккаунта

**Медиафайлы**
Поддерживаемые форматы:
- Изображения: JPEG, PNG (до 5MB)
- Видео: MP4 (до 16MB)
- Аудио: AAC, MP3, OGG (до 16MB)
- Документы: PDF, DOC, DOCX, XLS, XLSX (до 100MB)

## Web Chat

### Возможности

- Встраиваемый виджет на любой сайт
- Кастомизация дизайна
- Сохранение истории
- Уведомления
- Поддержка файлов
- Голосовой ввод

### Настройка

**Шаг 1: Включение Web Chat**

1. В настройках бота включите Web Chat
2. Скопируйте код виджета

**Шаг 2: Установка на сайт**

Вставьте код перед закрывающим тегом `</body>`:

```html
<script>
  window.agentLabConfig = {
    botId: 'YOUR_BOT_ID',
    apiUrl: 'https://your-domain.com',
    // Опциональные настройки
    position: 'bottom-right', // или 'bottom-left'
    theme: {
      primaryColor: '#4F46E5',
      headerText: 'Поддержка',
      placeholderText: 'Введите сообщение...'
    }
  };
</script>
<script src="https://your-domain.com/static/chat-widget.js"></script>
```

**Шаг 3: Тестирование**

Откройте ваш сайт - виджет появится в указанном углу.

### Кастомизация

**Цвета и стили:**
```javascript
theme: {
  primaryColor: '#4F46E5',      // Основной цвет
  secondaryColor: '#9333EA',    // Дополнительный цвет
  textColor: '#1F2937',         // Цвет текста
  backgroundColor: '#FFFFFF',    // Фон виджета
  headerColor: '#4F46E5',       // Цвет шапки
  userMessageColor: '#4F46E5',  // Цвет сообщений пользователя
  botMessageColor: '#F3F4F6'    // Цвет сообщений бота
}
```

**Тексты:**
```javascript
texts: {
  headerText: 'Чат с поддержкой',
  placeholderText: 'Напишите ваш вопрос...',
  sendButtonText: 'Отправить',
  fileUploadText: 'Прикрепить файл',
  offlineText: 'Мы сейчас offline, но ответим позже'
}
```

**Позиционирование:**
```javascript
position: 'bottom-right',  // bottom-right, bottom-left
offset: {
  bottom: '20px',
  right: '20px'
}
```

### Особенности

**Анонимные сессии**
По умолчанию каждый посетитель получает уникальный ID. Для привязки к вашим пользователям:

```javascript
agentLabConfig.userId = 'your-user-id';
```

**События**
Отслеживайте события виджета:

```javascript
window.addEventListener('agentlab:ready', () => {
  console.log('Виджет загружен');
});

window.addEventListener('agentlab:message:sent', (event) => {
  console.log('Отправлено:', event.detail.message);
});

window.addEventListener('agentlab:message:received', (event) => {
  console.log('Получено:', event.detail.message);
});
```

## AmoCRM

### Возможности

- Создание лидов и сделок
- Обновление контактов
- Поиск по базе
- Отправка сообщений в чаты AmoCRM
- Автоматизация продаж
- Интеграция с воронками

### Настройка

**Шаг 1: Создание интеграции**

1. В AmoCRM перейдите в "Настройки" → "Интеграции"
2. Нажмите "Создать интеграцию"
3. Заполните данные:
   - Название: Agent Lab
   - Redirect URL: `https://your-domain.com/api/amocrm/callback`
4. Получите:
   - **Integration ID**
   - **Secret Key**

**Шаг 2: Настройка в Agent Lab**

1. В настройках бота включите AmoCRM
2. Укажите:
   - **Subdomain** - ваш поддомен AmoCRM
   - **Integration ID**
   - **Secret Key**
3. Нажмите "Авторизовать"
4. Предоставьте доступ в открывшемся окне AmoCRM

**Шаг 3: Настройка виджета**

1. В AmoCRM установите виджет Agent Lab
2. Настройте отображение в карточках сделок/контактов

### Использование

**Инструменты для агентов:**

Ваши агенты могут использовать специальные инструменты для работы с AmoCRM:

- `create_lead` - создать лид
- `create_contact` - создать контакт
- `update_contact` - обновить контакт
- `search_contacts` - поиск контактов
- `create_note` - добавить примечание
- `send_message` - отправить сообщение в чат

**Пример использования в агенте:**

```
Ты - бот для обработки заявок.

Когда пользователь оставляет заявку:
1. Собери информацию: имя, телефон, email
2. Создай лид в AmoCRM с помощью create_lead
3. Добавь примечание с деталями
4. Сообщи пользователю о создании заявки
```

### Особенности

**Обработка чатов**
Бот может отвечать на сообщения в чатах AmoCRM автоматически или передавать менеджеру.

**Воронки и этапы**
При создании сделок указывайте ID воронки и этапа для автоматического распределения.

**Задачи**
Создавайте задачи для менеджеров автоматически при определенных условиях.

## API

### Возможности

- Полный программный доступ к боту
- Синхронный и асинхронный режимы
- Webhooks для событий
- Streaming ответов
- Управление сессиями

### Использование

**Базовый запрос:**

```bash
curl -X POST https://your-domain.com/api/v1/flow/{flow_id}/invoke \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет, бот!",
    "user_id": "user_12345",
    "session_id": "session_67890"
  }'
```

**Ответ:**

```json
{
  "message": "Привет! Чем могу помочь?",
  "session_id": "session_67890",
  "metadata": {
    "tokens_used": 45,
    "execution_time": 1.2
  }
}
```

**С контекстом:**

```bash
curl -X POST https://your-domain.com/api/v1/flow/{flow_id}/invoke \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Какая у меня заявка?",
    "user_id": "user_12345",
    "session_id": "session_67890",
    "context": {
      "order_id": "12345",
      "customer_name": "Иван Иванов"
    }
  }'
```

**Streaming:**

```bash
curl -X POST https://your-domain.com/api/v1/flow/{flow_id}/stream \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Расскажи длинную историю",
    "user_id": "user_12345"
  }'
```

Ответ будет приходить частями (Server-Sent Events).

### Webhooks

Настройте webhook для получения уведомлений о событиях:

**События:**
- `message.received` - получено сообщение
- `message.sent` - отправлено сообщение
- `session.started` - начата сессия
- `session.ended` - завершена сессия
- `error.occurred` - произошла ошибка

**Настройка:**

```bash
curl -X POST https://your-domain.com/api/v1/webhooks \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.com/webhook",
    "events": ["message.received", "message.sent"],
    "secret": "your-webhook-secret"
  }'
```

### Аутентификация

**API Token:**

1. Перейдите в раздел "Ключи и Переменные"
2. Создайте API ключ
3. Скопируйте токен
4. Используйте в заголовке `Authorization: Bearer YOUR_TOKEN`

**OAuth 2.0:**

Для интеграций с внешними сервисами доступен OAuth 2.0 flow.

## Сравнение платформ

| Возможность | Telegram | WhatsApp | Web Chat | AmoCRM | API |
|-------------|----------|----------|----------|---------|-----|
| Текст | ✅ | ✅ | ✅ | ✅ | ✅ |
| Изображения | ✅ | ✅ | ✅ | ✅ | ✅ |
| Голос | ✅ | ✅ | ✅ | ❌ | ✅ |
| Файлы | ✅ | ✅ | ✅ | ✅ | ✅ |
| Кнопки | ✅ | ✅ | ✅ | ❌ | ✅ |
| Streaming | ❌ | ❌ | ✅ | ❌ | ✅ |
| Webhooks | Auto | ✅ | ❌ | ✅ | ✅ |
| Кастомизация | ❌ | ❌ | ✅ | ✅ | ✅ |
| Setup сложность | Легко | Средне | Легко | Сложно | Средне |

## Многоплатформенность

Один бот может работать на всех платформах одновременно:

1. Создайте бота
2. Включите нужные платформы
3. Настройте каждую платформу
4. Бот будет отвечать везде с единым контекстом

**Единый контекст:**
Если пользователь начал диалог в Telegram и продолжил в Web Chat - контекст сохранится (при совпадении user_id).


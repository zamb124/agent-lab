# AmoCRM Client - Документация API v4

## 🎯 Быстрый старт

```python
from app.clients.amo_crm_integration import register_subdomain, get_amocrm_client

# 1. Регистрация токена (один раз при старте)
register_subdomain("mycompany", "your_access_token")

# 2. Получение клиента
client = get_amocrm_client(subdomain="mycompany")

# 3. Работа с API
leads = await client.get_leads(limit=10)
```

---

## 📚 Основные группы методов

### 📌 Сделки (Leads)
```python
# Получение
leads = await client.get_leads(limit=50, query="iPhone")
lead = await client.get_lead(lead_id=123, with_param="contacts")

# Создание
result = await client.create_lead({"name": "Новая сделка", "price": 50000})

# Обновление
await client.update_lead(lead_id=123, {"price": 60000})

# Complex (с привязкой контактов/компаний)
await client.create_leads_complex([{
    "name": "Сделка",
    "_embedded": {
        "contacts": [{"id": 456}]
    }
}])
```

### 👤 Контакты (Contacts)
```python
# Получение
contacts = await client.get_contacts(limit=50)
contact = await client.get_contact(contact_id=123)

# Создание
await client.create_contact({
    "name": "Иван Иванов",
    "custom_fields_values": [
        {"field_id": 123, "values": [{"value": "+79991234567"}]}
    ]
})

# Обновление
await client.update_contact(contact_id=123, {"name": "Иван Петров"})
```

### 🏢 Компании (Companies)
```python
companies = await client.get_companies()
company = await client.get_company(company_id=50)
await client.create_company({"name": "ООО Рога и Копыта"})
await client.update_company(company_id=50, {"name": "ООО Новое название"})
```

### 💰 Покупатели (Customers)
```python
customers = await client.get_customers()
await client.create_customer({"name": "VIP Клиент"})

# Транзакции
transactions = await client.get_customer_transactions(customer_id=60)
await client.create_customer_transaction(customer_id=60, {
    "price": 15000,
    "comment": "Покупка товара"
})

# Сегменты
segments = await client.get_customer_segments()
```

### ✅ Задачи (Tasks)
```python
# Создание
await client.create_task({
    "text": "Перезвонить клиенту",
    "complete_till": 1735689600,
    "entity_id": 123,
    "entity_type": "leads"
})

# Завершение
await client.complete_task(task_id=456, result_text="Клиент согласился")
```

### 🗂️ Каталоги (Catalogs)
```python
catalogs = await client.get_catalogs()
elements = await client.get_catalog_elements(catalog_id=1)

await client.create_catalog_element(catalog_id=1, {
    "name": "iPhone 15 Pro",
    "custom_fields_values": [...]
})
```

### 🔄 Воронки (Pipelines)
```python
pipelines = await client.get_pipelines()
pipeline = await client.get_pipeline(pipeline_id=1)
statuses = await client.get_pipeline_statuses(pipeline_id=1)
```

### 🔗 Связи сущностей
```python
# Привязка контакта к сделке
await client.link_entities("leads", 123, [
    {"to_entity_id": 456, "to_entity_type": "contacts"}
])

# Получение связей
links = await client.get_entity_links("leads", 123)

# Отвязка
await client.unlink_entities("leads", 123, [
    {"to_entity_id": 456, "to_entity_type": "contacts"}
])
```

### 📝 Примечания (Notes)
```python
notes = await client.get_notes("leads", entity_id=123)

await client.create_note(
    entity_type="leads",
    entity_id=123,
    note_type="common",
    text="Клиент попросил перезвонить"
)
```

### 📥 Неразобранное (Unsorted)
```python
unsorted = await client.get_unsorted(filter_category="forms")

# Принять заявку
await client.accept_unsorted(unsorted_id="abc123", user_id=1, status_id=100)

# Отклонить
await client.decline_unsorted(unsorted_id="abc123", user_id=1)

# Привязать к существующей сделке
await client.link_unsorted(unsorted_id="abc123", {
    "link": {"entity_id": 123, "entity_type": "leads"}
})
```

### 🪝 Вебхуки (Webhooks)
```python
webhooks = await client.get_webhooks()

await client.create_webhook(
    destination="https://myapp.com/webhook",
    settings=["add_lead", "update_lead", "add_contact"]
)

await client.delete_webhook(webhook_id=1)
```

### 💬 Беседы (Talks)
```python
talks = await client.get_talks(filter_is_in_work=True)
talk = await client.get_talk_by_id(talk_id=2000)
await client.close_talk(talk_id=2000, force_close=True)
```

### 🔧 Дополнительно
```python
# Кастомные поля
fields = await client.get_custom_fields("leads")

# Звонки
await client.create_call({
    "phone": "+79991234567",
    "duration": 120,
    "direction": "outbound"
})

# Источники, роли, виджеты
sources = await client.get_sources()
roles = await client.get_roles()
widgets = await client.get_widgets()

# Короткие ссылки
result = await client.create_short_link("https://example.com/long/url")

# Пользователи и аккаунт
users = await client.get_users(with_amojo_id=True)
account = await client.get_account_info(with_amojo_id=True)
```

---

## 💬 Chat API

```python
from app.clients.amo_crm_integration import get_amocrm_chat_client

chat_client = get_amocrm_chat_client(
    channel_id="your-channel-id",
    secret_key="your-secret-key"
)

# Подключение канала (один раз!)
result = await chat_client.connect_channel(
    account_id="amojo-account-id",
    title="Мой канал"
)

# Отправка сообщения
await chat_client.send_message(
    conversation_id="conv-123",
    user_id="user-456",
    user_name="Клиент",
    text="Здравствуйте!",
    user_profile={"phone": "+79991234567"}
)
```

---

## 📖 Полный пример

```python
from app.clients.amo_crm_integration import register_subdomain, get_amocrm_client

# Регистрация
register_subdomain("mycompany", "token")
client = get_amocrm_client(subdomain="mycompany")

# 1. Создаем контакт
contact_result = await client.create_contact({
    "name": "Иван Иванов",
    "custom_fields_values": [
        {"field_id": 123, "values": [{"value": "+79991234567"}]}
    ]
})
contact_id = contact_result["_embedded"]["contacts"][0]["id"]

# 2. Создаем сделку
lead_result = await client.create_lead({
    "name": "Продажа iPhone",
    "price": 120000
})
lead_id = lead_result["_embedded"]["leads"][0]["id"]

# 3. Привязываем контакт к сделке
await client.link_entities("leads", lead_id, [
    {"to_entity_id": contact_id, "to_entity_type": "contacts"}
])

# 4. Создаем задачу
await client.create_task({
    "text": "Отправить КП",
    "complete_till": 1735689600,
    "entity_id": lead_id,
    "entity_type": "leads"
})

# 5. Добавляем примечание
await client.create_note(
    entity_type="leads",
    entity_id=lead_id,
    note_type="common",
    text="Клиент заинтересован"
)
```

---

## ⚠️ Важно

- **Singleton**: клиенты кешируются и переиспользуются
- **204 = ошибка**: статус 204 No Content выбрасывает HTTPStatusError
- **Rate limit**: ~7 запросов/сек
- **Пагинация**: макс 250 элементов на страницу (100 для events/tasks)

---

## 🔗 Ссылки

- [AmoCRM API v4](https://www.amocrm.ru/developers/content/crm_platform/api-reference)
- [OAuth 2.0](https://www.amocrm.ru/developers/content/oauth/step-by-step)
- [Chat API](https://www.amocrm.ru/developers/content/chats/chat-api-reference)
- [Webhooks](https://www.amocrm.ru/developers/content/crm_platform/webhooks)

# CRM Service - Архитектура V2 (Чистая)

## Обзор

CRM Service - сервис для управления сущностями (entities), заметками, задачами, контактами и связями между ними.

**ПОЛНЫЙ РЕФАКТОРИНГ:** Без обратной совместимости, все с нуля.

---

## Ключевые принципы

### 1. Единая модель CRMEntity

**ВСЕ сущности** - это `CRMEntity`:
- `entity_type`: базовый тип (note, task, contact, organization)
- `entity_subtype`: подтип для note (meeting, call, webinar_notes)
- **БЕЗ** `linked_entity_ids` - все связи через PostgreSQL!

### 2. Иерархия типов с промптами

**EntityType (PostgreSQL):**
```
EntityType (ВСЕ с company_id!)
├── note (parent=None, is_system=true, prompt)
│   ├── meeting (parent="note", prompt)
│   ├── call (parent="note", prompt)
│   └── webinar_notes (кастомный, prompt)
├── task (parent=None, is_system=true, prompt)
├── contact (бизнес-тип, prompt)
└── organization (бизнес-тип, prompt)
```

**RelationshipType (PostgreSQL):**
```
RelationshipType (ВСЕ с company_id!)
├── mentions (is_system=true, prompt для AI)
├── linked (is_system=true, БЕЗ prompt - парсер)
├── works_for (кастомный, prompt)
└── manages (кастомный, prompt)
```

### 3. Все с company_id

**НЕТ глобальных типов!**
- При создании компании → копируются системные типы из шаблонов
- Каждая компания может редактировать свои типы
- Полная изоляция данных

### 4. AI с составными промптами

Промпт строится из:
1. `EntityType.prompt` для базового типа (note)
2. `EntityType.prompt` для подтипов (meeting, call)
3. `EntityType.prompt` для бизнес-типов (contact, organization)
4. `RelationshipType.prompt` для связей (works_for, manages)

---

## Архитектура данных

### PostgreSQL + pgvector (Semantic Search)

**Namespace:** `company_id` (без префикса - общая для всех сервисов!)

**Модель:** `CRMEntity` (единая для всех)

**Содержит:**
- Полные metadata для фильтрации
- Embeddings для semantic search
- Все данные сущности (attributes, tags, dates)

**Используется для:**
- Семантический поиск
- Фильтрация по типам/статусам/тегам
- Хранение контента заметок

### PostgreSQL (Relations & Schema)

**Таблицы:**

1. **`entity_types`** - типы сущностей с иерархией
   - `type_id`, `company_id`, `parent_type_id`
   - `prompt` - для AI извлечения
   - Иерархия: note → meeting, call

2. **`relationship_types`** - типы связей
   - `type_id`, `company_id`
   - `prompt` - для AI извлечения
   - `is_directed`, `inverse_type_id`

3. **`relationships`** - граф связей
   - ВСЕ связи между entities
   - `source_entity_id`, `target_entity_id`, `relationship_type`
   - Нет `linked_entity_ids` в vector_documents!

4. **`company_mapping`** - связь company → entity
5. **`access_requests`** - workflow для доступа
6. **`user_profiles`** - профили пользователей

**УДАЛЕНО:**
- `notes` - теперь CRMEntity
- `tasks` - теперь CRMEntity

---

## Сервисы

### EntityService

**Единый сервис для всех типов entities.**

**Функции:**
- CRUD для любого типа (note, task, contact, etc)
- AI анализ текста с составными промптами
- Извлечение entities и relationships
- Каскадное удаление через Saga pattern

**Пример:**
```python
# Создание заметки-встречи
entity = await entity_service.create_entity(
    entity_type="note",
    entity_subtype="meeting",
    name="Встреча с Иваном",
    description="Обсудили проект X",
    note_date=date.today()
)

# AI анализ
result = await entity_service.analyze_text_with_ai(
    AIAnalyzeRequest(
        text="Сегодня встретились с Иваном. Обсудили проект X."
    )
)
```

### AttachmentService

**Универсальный сервис для вложений.**

Работает для ВСЕХ entity типов через RAG Service API.

### CompanyInitService

**Инициализация компании.**

Копирует системные типы из шаблонов с `company_id` новой компании.

---

## Saga Pattern

**Каскадное удаление entity:**

1. Удалить все relationships (PostgreSQL)
2. Удалить все attachments (RAG)
3. Удалить entity (PostgreSQL + pgvector)

При ошибке - откат в обратном порядке.

---

## API Endpoints

**БЕЗ ВЕРСИЙ!** Чистая архитектура.

### Entities

- `POST /entities` - создать entity
- `GET /entities/{entity_id}` - получить entity
- `PUT /entities/{entity_id}` - обновить entity
- `DELETE /entities/{entity_id}` - каскадное удаление
- `GET /entities?entity_type=note&entity_subtype=meeting` - список
- `GET /entities/search?query=...` - семантический поиск
- `POST /entities/analyze` - AI анализ текста

---

## Межсервисное взаимодействие

### С Agents (A2A API)

**Через:** `core.clients.a2a_client.A2AClient`

**Использование:** AI анализ текста

```python
response = await a2a_client.call(
    flow_id="crm_analyzer",
    method="analyze_text",
    params={"text": "...", "prompt": "..."}
)
```

### С RAG (REST API)

**Через:** `core.clients.service_client.ServiceClient`

**Использование:** Управление attachments

```python
response = await service_client.post(
    service="rag",
    path="/rag/api/v1/namespaces/{namespace}/documents",
    files={"file": ...}
)
```

---

## Миграция данных

**НЕТ МИГРАЦИИ!** Система запускается с чистого листа.

Старые данные НЕ переносятся.

---

## Что изменилось

### Удалено

- ❌ `Note`, `Task` модели в PostgreSQL
- ❌ `NoteService`, `TaskService`
- ❌ `AgentsClient` (старый HTTP)
- ❌ `linked_entity_ids` в vector_documents
- ❌ Прямая работа с S3/FileProcessor
- ❌ API v1

### Добавлено

- ✅ Единая модель `CRMEntity`
- ✅ Иерархия `EntityType` с промптами
- ✅ `RelationshipType` с промптами
- ✅ Все типы с `company_id`
- ✅ Saga pattern для каскадного удаления
- ✅ AI с составными промптами
- ✅ A2AClient и ServiceClient из core
- ✅ Универсальный AttachmentService

---

## Разработка

### Запуск

```bash
uv run python -m apps.crm.main
```

### Тесты

```bash
make test-crm
```

---

## Файловая структура

```
apps/crm/
├── models/
│   ├── entity.py          # CRMEntity
│   └── api.py             # API модели
├── db/
│   ├── models.py          # SQLAlchemy (EntityType, RelationshipType, Relationship)
│   └── repositories/
│       ├── entity_repository.py         # PostgreSQL + pgvector
│       ├── entity_type_repository.py    # PostgreSQL
│       ├── relationship_type_repository.py
│       └── relationship_repository.py
├── services/
│   ├── entity_service.py        # Главный сервис
│   ├── attachment_service.py
│   ├── company_init_service.py
│   └── saga.py                  # Saga pattern
├── api/
│   ├── entities.py
│   └── router.py
├── system_templates.py   # Шаблоны системных типов
└── LEGACY_TO_DELETE.md   # Список удаленных файлов
```


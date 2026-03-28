"""
Шаблоны системных типов.

При создании компании эти шаблоны копируются с company_id новой компании.
"""

SYSTEM_ENTITY_TYPE_TEMPLATES = [
    {
        "type_id": "person",
        "parent_type_id": None,
        "name": "Человек",
        "description": "Люди, контакты, персоны",
        "is_system": True,
        "is_event": False,
        "prompt": """
Ищи упоминания людей, персон, контактов.

Ключевые слова:
- Имена людей (Иван, Мария, Петр)
- Должности (менеджер, директор, разработчик)
- Роли (клиент, партнер, коллега)

Извлекай:
- Имя (name)
- Должность (position)
- Email, телефон
- Компания (создавай связь works_at)
        """,
        "icon": "user",
        "color": "#9C27B0",
        "weight_coefficient": 1.0
    },
    {
        "type_id": "organization",
        "parent_type_id": None,
        "name": "Организация",
        "description": "Компании, организации, юр. лица",
        "is_system": True,
        "is_event": False,
        "prompt": """
Ищи упоминания компаний, организаций.

Ключевые слова:
- Названия компаний (Google, Яндекс, ООО)
- Типы (компания, фирма, корпорация)
- Бренды, продукты

Извлекай:
- Название (name)
- Сфера деятельности
- Сайт, контакты
        """,
        "icon": "building-one",
        "color": "#3F51B5",
        "weight_coefficient": 1.0
    },
    {
        "type_id": "note",
        "parent_type_id": None,
        "name": "Заметка",
        "description": "Базовый тип для всех записей",
        "is_system": True,
        "is_event": True,
        "prompt": """
Общий тип для всех записей и заметок.
Ищи любую информацию, которую нужно зафиксировать:
- Встречи, звонки, беседы
- Мысли, идеи, наблюдения
- Резюме, выводы, итоги

Всегда извлекай дату события.
        """,
        "icon": "doc-detail",
        "color": "#607D8B",
        "weight_coefficient": 1.0
    },
    {
        "type_id": "meeting",
        "parent_type_id": "note",
        "name": "Встреча",
        "description": "Встречи, переговоры, совещания",
        "is_system": True,
        "is_event": True,
        "prompt": """
Ищи упоминания встреч, переговоров, совещаний.

Ключевые слова:
- встреча, встретились, провели встречу
- совещание, планерка
- переговоры, обсуждение
- конференция, сессия

Извлекай:
- Участников (создавай связи)
- Дату и время
- Место проведения (офис, онлайн, адрес)
- Обсуждаемые темы
- Договоренности и решения
        """,
        "icon": "chat",
        "color": "#4CAF50",
        "weight_coefficient": 1.2
    },
    {
        "type_id": "call",
        "parent_type_id": "note",
        "name": "Звонок",
        "description": "Телефонные разговоры",
        "is_system": True,
        "is_event": True,
        "prompt": """
Ищи упоминания звонков, телефонных разговоров.

Ключевые слова:
- звонил, позвонил, созвонились
- разговор по телефону
- телефонный разговор
- прозвонил, обзвон

Извлекай:
- Кому звонили (создавай связи)
- Дату и время звонка
- Тему разговора
- Договоренности
- Следующие шаги
        """,
        "icon": "phone",
        "color": "#2196F3",
        "weight_coefficient": 1.0
    },
    {
        "type_id": "task",
        "parent_type_id": None,
        "name": "Задача",
        "description": "Задачи с дедлайнами",
        "is_system": True,
        "is_event": False,
        "prompt": """
Ищи упоминания задач, дел, поручений.

Ключевые слова:
- задача, задание
- поручение, нужно сделать
- дело, to-do
- план, действие

Извлекай:
- Название задачи
- Дедлайн (due_date)
- Исполнителей (assignees)
- Приоритет (low, medium, high, urgent)
- Связанные проекты/сделки
        """,
        "icon": "checklist",
        "color": "#FF9800",
        "weight_coefficient": 1.1
    },
]

SYSTEM_RELATIONSHIP_TYPE_TEMPLATES = [
    {
        "type_id": "mentions",
        "name": "Упоминает",
        "description": "Упоминание entity в тексте (из AI анализа)",
        "is_system": True,
        "is_directed": True,
        "prompt": """
Создавай связь "mentions" когда entity упоминается в тексте,
но НЕ через явную ссылку @entity.

Примеры:
- "Обсудили проект с Иваном" → note mentions contact:Иван
- "Позвонил в Acme Corp" → note mentions organization:Acme
- "Задача по сделке XYZ" → task mentions deal:XYZ

НЕ создавай mentions для явных ссылок через @ (это тип "linked").
        """,
        "icon": "chat",
        "color": "#9E9E9E",
        "weight_default": 0.5
    },
    {
        "type_id": "linked",
        "name": "Явная ссылка",
        "description": "Ссылка через @entity или @link в тексте",
        "is_system": True,
        "is_directed": True,
        "prompt": None,
        "icon": "circular-connection",
        "color": "#2196F3",
        "weight_default": 1.0
    },
]


"""
Шаблоны системных типов.

При создании компании эти шаблоны копируются с company_id новой компании.
"""

SYSTEM_ENTITY_TYPE_TEMPLATES = [
    {
        "type_id": "note",
        "parent_type_id": None,
        "name": "Заметка",
        "description": "Базовый системный тип заметки",
        "is_system": True,
        "is_event": True,
        "prompt": "Извлекай факты, выводы и контекст заметки в структурированный объект note.",
        "icon": "doc-detail",
        "color": "#607D8B",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "summary": {"type": "string", "label": "Краткое содержание"},
            "note_date": {"type": "date", "label": "Дата заметки"},
        },
        "is_context_anchor": False,
    },
    {
        "type_id": "meeting",
        "parent_type_id": "note",
        "name": "Встреча",
        "description": "Запись о встрече с участниками и договоренностями",
        "is_system": True,
        "is_event": True,
        "prompt": "Извлекай участников, обсуждаемые темы, принятые решения и следующие шаги.",
        "icon": "users",
        "color": "#4CAF50",
        "weight_coefficient": 1.2,
        "required_fields": {},
        "optional_fields": {
            "participants": {"type": "string", "label": "Участники"},
            "location": {"type": "string", "label": "Место"},
            "decisions": {"type": "string", "label": "Решения"},
        },
        "is_context_anchor": False,
    },
    {
        "type_id": "call",
        "parent_type_id": "note",
        "name": "Звонок",
        "description": "Запись телефонного разговора",
        "is_system": True,
        "is_event": True,
        "prompt": "Извлекай собеседника, тему разговора и итоги звонка.",
        "icon": "phone",
        "color": "#2196F3",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "contact_name": {"type": "string", "label": "Собеседник"},
            "duration": {"type": "string", "label": "Длительность"},
            "outcome": {"type": "string", "label": "Итог"},
        },
        "is_context_anchor": False,
    },
    {
        "type_id": "task",
        "parent_type_id": None,
        "name": "Задача",
        "description": "Базовый системный тип задачи",
        "is_system": True,
        "is_event": False,
        "prompt": "Извлекай конкретные действия с дедлайном и исполнителями в объект task.",
        "icon": "checklist",
        "color": "#FF9800",
        "weight_coefficient": 1.1,
        "required_fields": {},
        "optional_fields": {
            "title": {"type": "string", "label": "Название задачи"},
            "due_date": {"type": "date", "label": "Срок"},
            "priority": {"type": "enum", "values": ["low", "medium", "high", "urgent"]},
        },
        "is_context_anchor": False,
    },
    {
        "type_id": "contact",
        "parent_type_id": None,
        "name": "Контакт",
        "description": "Человек или контактная запись",
        "is_system": True,
        "is_event": False,
        "prompt": "Извлекай персону, роль и контекст взаимодействия.",
        "icon": "user",
        "color": "#546E7A",
        "weight_coefficient": 1.0,
        "required_fields": {},
        "optional_fields": {
            "display_name": {"type": "string", "label": "Имя"},
            "role": {"type": "string", "label": "Роль"},
        },
        "is_context_anchor": False,
    },
]

COMMON_NAMESPACE_ANCHOR_TYPES = [
    {
        "type_id": "topic",
        "name": "Тема",
        "description": "Направление или поток работы: к какой линии разговора относится заметка (не отдельный человек и не разовое событие).",
        "prompt": "Извлекай название темы, границы и связь с проектом или организацией.",
        "required_fields": {},
        "optional_fields": {
            "title": {"type": "string", "label": "Название темы"},
            "scope": {"type": "string", "label": "Область"},
        },
        "icon": "layers",
        "color": "#3949AB",
        "is_event": False,
        "check_duplicates": False,
        "is_context_anchor": True,
    },
    {
        "type_id": "organization",
        "name": "Организация",
        "description": "Объединяющая сущность: компания, подразделение или юрлицо — контекст заметок об организации.",
        "prompt": "Извлекай организацию, отрасль и роль в контексте.",
        "required_fields": {},
        "optional_fields": {
            "name": {"type": "string", "label": "Название"},
            "industry": {"type": "string", "label": "Отрасль"},
        },
        "icon": "database",
        "color": "#455A64",
        "is_event": False,
        "check_duplicates": True,
        "is_context_anchor": True,
    },
    {
        "type_id": "project",
        "name": "Проект",
        "description": "Инициатива с целями и границами: заметка относится к работе целиком, а не к одному шагу.",
        "prompt": "Извлекай название проекта, статус и ключевые вехи.",
        "required_fields": {},
        "optional_fields": {
            "title": {"type": "string", "label": "Название"},
            "status": {"type": "string", "label": "Статус"},
        },
        "icon": "folder",
        "color": "#5E35B1",
        "is_event": False,
        "check_duplicates": True,
        "is_context_anchor": True,
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
        "weight_default": 0.5,
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
        "weight_default": 1.0,
    },
    {
        "type_id": "related_to",
        "name": "Связан с",
        "description": "Общая ассоциация между сущностями без направления",
        "is_system": True,
        "is_directed": False,
        "prompt": """Создавай связь "related_to" когда две сущности связаны общим контекстом,
но без конкретного направления или иерархии.

Примеры:
- "Проект Alpha связан с инициативой Beta" → project related_to project
- "Клиент интересуется продуктом" → contact related_to deal
- Два контакта упомянуты вместе в одном контексте → contact related_to contact

НЕ используй related_to если есть более точный тип (parent_of, assigned_to, belongs_to).""",
        "icon": "link",
        "color": "#78909C",
        "weight_default": 0.7,
    },
    {
        "type_id": "parent_of",
        "name": "Родитель",
        "description": "Иерархическая связь: родительская сущность",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "child_of",
        "prompt": """Создавай связь "parent_of" когда одна сущность является контейнером или родителем для другой.

Примеры:
- "Проект включает задачу" → project parent_of task
- "Организация имеет отдел" → organization parent_of organization
- "Эпик содержит несколько stories" → task parent_of task

Обратная связь child_of создается автоматически.""",
        "icon": "tree-square-dot",
        "color": "#5C6BC0",
        "weight_default": 1.0,
    },
    {
        "type_id": "child_of",
        "name": "Дочерний",
        "description": "Иерархическая связь: дочерняя сущность",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "parent_of",
        "prompt": None,
        "icon": "tree-square-dot",
        "color": "#5C6BC0",
        "weight_default": 1.0,
    },
    {
        "type_id": "assigned_to",
        "name": "Назначено",
        "description": "Задача или ответственность назначена на сущность",
        "is_system": True,
        "is_directed": True,
        "prompt": """Создавай связь "assigned_to" когда задача или ответственность назначена на человека.

Примеры:
- "Задачу поручили Ивану" → task assigned_to contact:Иван
- "Ответственный за проект — Мария" → project assigned_to contact:Мария
- "Тикет назначен на команду поддержки" → task assigned_to organization""",
        "icon": "user",
        "color": "#26A69A",
        "weight_default": 0.8,
    },
    {
        "type_id": "belongs_to",
        "name": "Принадлежит",
        "description": "Членство или владение: сущность принадлежит другой",
        "is_system": True,
        "is_directed": True,
        "prompt": """Создавай связь "belongs_to" когда контакт работает в организации или сущность принадлежит другой.

Примеры:
- "Иван работает в Acme Corp" → contact:Иван belongs_to organization:Acme
- "Сделка относится к отделу продаж" → deal belongs_to organization
- "Кандидат из компании XYZ" → contact belongs_to organization:XYZ""",
        "icon": "folder",
        "color": "#8D6E63",
        "weight_default": 0.8,
    },
    {
        "type_id": "follows_up",
        "name": "Продолжение",
        "description": "Последовательная цепочка: одна сущность продолжает другую",
        "is_system": True,
        "is_directed": True,
        "prompt": """Создавай связь "follows_up" когда одна встреча, заметка или задача является продолжением предыдущей.

Примеры:
- "Продолжение вчерашнего обсуждения" → note follows_up note
- "Повторная встреча по проекту" → meeting follows_up meeting
- "Задача создана по итогам совещания" → task follows_up note""",
        "icon": "arrow-right",
        "color": "#42A5F5",
        "weight_default": 0.6,
    },
    {
        "type_id": "blocks",
        "name": "Блокирует",
        "description": "Зависимость: сущность блокирует выполнение другой",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "blocked_by",
        "prompt": """Создавай связь "blocks" когда выполнение одной задачи блокирует или зависит от другой.

Примеры:
- "Нельзя начать деплой пока не пройдут тесты" → task:тесты blocks task:деплой
- "Сделка заблокирована юридической проверкой" → task:проверка blocks deal

Обратная связь blocked_by создается автоматически.""",
        "icon": "error",
        "color": "#EF5350",
        "weight_default": 0.9,
    },
    {
        "type_id": "blocked_by",
        "name": "Заблокировано",
        "description": "Обратная зависимость: сущность заблокирована другой",
        "is_system": True,
        "is_directed": True,
        "inverse_type_id": "blocks",
        "prompt": None,
        "icon": "error",
        "color": "#EF5350",
        "weight_default": 0.9,
    },
    {
        "type_id": "duplicates",
        "name": "Дубликат",
        "description": "Маркировка дубликата сущности",
        "is_system": True,
        "is_directed": False,
        "prompt": None,
        "icon": "copy",
        "color": "#BDBDBD",
        "weight_default": 0.3,
    },
    {
        "type_id": "note_voice",
        "name": "Голос заметки",
        "description": "Направленная связь: заметка (источник) — сущность-голос (цель)",
        "is_system": True,
        "is_directed": True,
        "prompt": None,
        "icon": "user",
        "color": "#7CB342",
        "weight_default": 1.0,
    },
    {
        "type_id": "in_context",
        "name": "В контексте",
        "description": "Заметка привязана к объекту контекста: тема, проект, организация или объект работы (сделка, решение), не к заметке и не к отдельному контакту.",
        "is_system": True,
        "is_directed": True,
        "prompt": None,
        "icon": "anchor",
        "color": "#5C6BC0",
        "weight_default": 1.0,
    },
]


NAMESPACE_TEMPLATE_SEEDS = [
    {
        "template_id": "sales",
        "name": "CRM система для продаж",
        "description": "Лиды, контакты, сделки, активность по продажам.",
        "icon": "chart",
        "types": [
            {
                "type_id": "lead",
                "name": "Лид",
                "description": "Объект воронки (возможность): контекст заметок о сделке в целом, не замена контакту.",
                "prompt": "Извлекай потенциальных клиентов и стадию квалификации.",
                "required_fields": {"source": {"type": "string"}, "stage": {"type": "string"}},
                "optional_fields": {"budget": {"type": "number"}},
                "icon": "target-lock",
                "color": "#7E57C2",
                "is_event": False,
                "check_duplicates": True,
                "is_context_anchor": True,
            },
            {
                "type_id": "deal",
                "name": "Сделка",
                "description": "Коммерческая сделка как объект работы: якорь для заметок о переговорах и условиях.",
                "prompt": "Извлекай сумму, стадию и вероятность закрытия сделки.",
                "required_fields": {"amount": {"type": "number"}, "stage": {"type": "string"}},
                "optional_fields": {"close_date": {"type": "date"}},
                "icon": "chart-multifunction",
                "color": "#EF6C00",
                "is_event": False,
                "check_duplicates": True,
                "is_context_anchor": True,
            },
        ]
        + COMMON_NAMESPACE_ANCHOR_TYPES,
    },
    {
        "template_id": "development",
        "name": "Команда разработки",
        "description": "Инциденты, задачи разработки, архитектурные заметки.",
        "icon": "code",
        "types": [
            {
                "type_id": "incident",
                "name": "Инцидент",
                "description": "Сбой или деградация сервиса",
                "prompt": "Извлекай влияние, компонент и приоритет инцидента.",
                "required_fields": {"severity": {"type": "string"}, "service": {"type": "string"}},
                "optional_fields": {"started_at": {"type": "datetime"}},
                "icon": "error",
                "color": "#D32F2F",
                "is_event": True,
                "check_duplicates": True,
                "is_context_anchor": False,
            },
            {
                "type_id": "decision",
                "name": "Архитектурное решение",
                "description": "Зафиксированное решение как контекст для связанных заметок и последствий.",
                "prompt": "Извлекай решение, причины и последствия.",
                "required_fields": {"decision": {"type": "string"}},
                "optional_fields": {"alternatives": {"type": "array"}},
                "icon": "tree-square-dot",
                "color": "#1976D2",
                "is_event": False,
                "check_duplicates": False,
                "is_context_anchor": True,
            },
        ]
        + COMMON_NAMESPACE_ANCHOR_TYPES,
    },
    {
        "template_id": "hr",
        "name": "HR команда",
        "description": "Подбор, интервью, кадровые заметки.",
        "icon": "user",
        "types": [
            {
                "type_id": "candidate",
                "name": "Кандидат",
                "description": "Профиль кандидата",
                "prompt": "Извлекай кандидата, стек и этап найма.",
                "required_fields": {"stage": {"type": "string"}, "position": {"type": "string"}},
                "optional_fields": {"salary_expectation": {"type": "number"}},
                "icon": "user",
                "color": "#8E24AA",
                "is_event": False,
                "check_duplicates": True,
                "is_context_anchor": False,
            },
            {
                "type_id": "interview",
                "name": "Интервью",
                "description": "Запись интервью",
                "prompt": "Извлекай итоги интервью, сильные и слабые стороны.",
                "required_fields": {"result": {"type": "string"}},
                "optional_fields": {"interviewer": {"type": "string"}},
                "icon": "chat",
                "color": "#00897B",
                "is_event": True,
                "check_duplicates": False,
                "is_context_anchor": False,
            },
        ]
        + COMMON_NAMESPACE_ANCHOR_TYPES,
    },
]


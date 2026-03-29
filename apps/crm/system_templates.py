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
        "required_fields": {"summary": {"type": "string", "label": "Краткое содержание"}},
        "optional_fields": {"note_date": {"type": "date", "label": "Дата заметки"}},
    },
    {
        "type_id": "task",
        "parent_type_id": None,
        "name": "Задача (системная)",
        "description": "Базовый системный тип задачи",
        "is_system": True,
        "is_event": False,
        "prompt": "Извлекай конкретные действия с дедлайном и исполнителями в объект task.",
        "icon": "checklist",
        "color": "#FF9800",
        "weight_coefficient": 1.1,
        "required_fields": {"title": {"type": "string", "label": "Название задачи"}},
        "optional_fields": {
            "due_date": {"type": "date", "label": "Срок"},
            "priority": {"type": "enum", "values": ["low", "medium", "high", "urgent"]},
        },
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
                "description": "Потенциальный клиент",
                "prompt": "Извлекай потенциальных клиентов и стадию квалификации.",
                "required_fields": {"source": {"type": "string"}, "stage": {"type": "string"}},
                "optional_fields": {"budget": {"type": "number"}},
                "icon": "target-lock",
                "color": "#7E57C2",
                "is_event": False,
                "check_duplicates": True,
            },
            {
                "type_id": "deal",
                "name": "Сделка",
                "description": "Коммерческая сделка",
                "prompt": "Извлекай сумму, стадию и вероятность закрытия сделки.",
                "required_fields": {"amount": {"type": "number"}, "stage": {"type": "string"}},
                "optional_fields": {"close_date": {"type": "date"}},
                "icon": "chart-multifunction",
                "color": "#EF6C00",
                "is_event": False,
                "check_duplicates": True,
            },
        ],
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
            },
            {
                "type_id": "decision",
                "name": "Архитектурное решение",
                "description": "Принятое техрешение",
                "prompt": "Извлекай решение, причины и последствия.",
                "required_fields": {"decision": {"type": "string"}},
                "optional_fields": {"alternatives": {"type": "array"}},
                "icon": "tree-square-dot",
                "color": "#1976D2",
                "is_event": False,
                "check_duplicates": False,
            },
        ],
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
            },
        ],
    },
]


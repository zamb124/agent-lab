"""
Флоу для юридического агента компании.
Агент специализируется на российском законодательстве.
"""

from app.models import FlowConfig

lawyer_flow = FlowConfig(
    name="Lawyer Flow",
    description="""# Юридический агент

Профессиональный юридический советник, специализирующийся на **российском законодательстве**.

## 🎯 Специализация

- **ГК РФ** — договоры, обязательства, сделки, собственность
- **НК РФ** — налогообложение, вычеты, льготы, декларации  
- **ТК РФ** — трудовые отношения, увольнения, зарплата
- **КоАП РФ** — административные правонарушения, штрафы
- **УК РФ** — уголовная ответственность
- **152-ФЗ** — защита персональных данных
- **14-ФЗ** — закон об ООО

## ⚙️ Установка

### 1. Загрузите документы компании в базу знаний:
- Устав ООО ЭНЖИЛАБС
- Решения учредителей
- Договоры с контрагентами
- Внутренние политики и регламенты
- Трудовые договоры (шаблоны)

### 2. Установите переменные (если нужны кастомные):
- `company_short_name` — краткое наименование (по умолчанию: ООО ЭНЖИЛАБС)
- `company_full_name` — полное наименование
- `ceo_name` — ФИО генерального директора
- `lawyer_bot` — username Telegram бота
- `lawyer_bot_telegram_token` — токен Telegram бота

## 🔧 Возможности

✅ **Консультации по законодательству РФ**
   - Анализ с привязкой к конкретным статьям
   - Ссылки на судебную практику
   - Актуальные разъяснения через поиск в интернете

✅ **Работа с документами**
   - Поиск в базе знаний компании
   - Анализ договоров и соглашений
   - Загрузка новых документов в базу
   - Выявление рисков и рекомендации

✅ **Поиск актуальной информации**
   - Судебная практика ВС РФ и КС РФ
   - Изменения в законодательстве
   - Разъяснения Минфина, ФНС, Роструда

✅ **Структурированные ответы**
   - Правовая позиция
   - Обоснование со статьями законов
   - Конкретные рекомендации
   - Анализ рисков

## 🧠 Модель: Google Gemini 2.5 Pro

Топовая модель с огромным контекстом для глубокого юридического анализа.

## 📚 RAG: База знаний компании

Документы автоматически индексируются и доступны для поиска.""",
    entry_point_agent="app.agents.lawyer.agent.LawyerAgent",
    
    image_path="app/agents/lawyer/LAWYER.png",
    
    platforms={
        "api": {},
        "telegram": {
            "username": "@var:lawyer_bot",
            "token": "@var:lawyer_bot_telegram_token"
        }
    },
    
    variables={
        "company_short_name": "@var:company_short_name",
        "company_full_name": "@var:company_full_name",
        "company_short_name_en": "@var:company_short_name_en",
        "company_full_name_en": "@var:company_full_name_en",
        "ceo_name": "@var:ceo_name",
        "bot_name": "@var:bot_name"
    },

    variables_definitions=[
        {
            "key": "lawyer_bot",
            "description": "Юзернейм Telegram бота для юридического консультанта",
            "default_value": "lawyer_bot",
            "is_secret": False,
            "required": True
        },
        {
            "key": "lawyer_bot_telegram_token",
            "description": "Токен Telegram бота для юридического консультанта",
            "is_secret": True,
            "required": True
        },
        {
            "key": "company_short_name",
            "description": "Краткое наименование компании",
            "default_value": "ООО ЭНЖИЛАБС",
            "is_secret": False,
            "required": False
        },
        {
            "key": "company_full_name",
            "description": "Полное наименование компании",
            "default_value": "Общество с Ограниченной Ответственностью ЭНЖИЛАБС",
            "is_secret": False,
            "required": False
        },
            {
                "key": "ceo_name",
                "description": "ФИО генерального директора",
                "default_value": "Шведов Виктор Викторович",
                "is_secret": False,
                "required": False
            },
            {
                "key": "company_short_name_en",
                "description": "Краткое наименование компании на английском",
                "default_value": "LLC ENZHLABS",
                "is_secret": False,
                "required": False
            },
            {
                "key": "company_full_name_en",
                "description": "Полное наименование компании на английском",
                "default_value": "Limited Liability Company ENZHLABS",
                "is_secret": False,
                "required": False
            },
            {
                "key": "bot_name",
                "description": "Имя бота для отображения",
                "default_value": "Юридический консультант",
                "is_secret": False,
                "required": False
            },
    ],

    enable_reasoning=True,
    
    is_public=True,
)


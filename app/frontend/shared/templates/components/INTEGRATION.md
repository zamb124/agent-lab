# Интеграция: Components + Fields

## Архитектура

```
app/frontend/shared/templates/
├── components/          # Универсальные UI компоненты
│   ├── base/           # Атомарные компоненты (Button, Badge, Icon)
│   ├── layout/         # Layout компоненты (Card, Modal)
│   ├── feedback/       # Обратная связь (Skeleton, Empty State, Alert)
│   └── complex/        # Сложные компоненты (AgentCard, FlowCard)
│
└── fields/             # Автогенерация форм из Pydantic моделей
    ├── base_field.html # Базовый шаблон поля
    ├── str.html        # Текстовое поле
    ├── bool.html       # Checkbox
    ├── enum.html       # Select
    └── ...             # Другие типы полей
```

## Принцип работы

### Fields - Для автоматических форм
Используется когда нужно автоматически сгенерировать форму из Pydantic модели:

```python
# Backend
class AgentConfig(BaseModel):
    name: str = Field(description="Название агента")
    enabled: bool = Field(default=True)
    temperature: float = Field(default=0.7, ge=0, le=2)

# Frontend автоматически генерирует:
# - str.html для name
# - bool.html для enabled  
# - float.html для temperature
```

### Components - Для ручной верстки
Используется когда вручную верстаем интерфейс:

```jinja2
{# Пустое состояние #}
{% include 'components/feedback/empty-state.html' with {
    'icon': 'robot',
    'title': 'Нет агентов',
    'action': {'text': 'Создать', 'variant': 'primary'}
} %}

{# Модалка #}
{% include 'components/layout/modal.html' with {
    'id': 'confirm-delete',
    'title': 'Удалить агента?',
    'actions': [...]
} %}
```

## Интеграция

### Fields используют Components

**До:**
```jinja2
{# fields/str.html #}
<label>{{ title }}</label>
<input type="text" class="form-control" ...>
```

**После:**
```jinja2
{# fields/str.html #}
<label>{{ title }}</label>
{% include 'components/forms/input.html' with {
    'type': 'text',
    'name': field_name,
    'value': value
} %}
```

### Преимущества

1. **DRY** - не дублируем стили и логику
2. **Консистентность** - все input выглядят одинаково
3. **Централизованное обновление** - меняем в одном месте
4. **Переиспользование** - components можно использовать везде

## Примеры использования

### 1. Автоматическая форма (fields/)

```python
# Backend
@router.get("/agent/{agent_id}")
async def get_agent_form(agent_id: str):
    agent = await agent_repo.get(agent_id)
    return render_model_form(agent)  # Автоматически использует fields/
```

### 2. Ручная верстка (components/)

```jinja2
{# templates/custom-page.html #}

{# Скелетон при загрузке #}
<div hx-get="/api/data" hx-trigger="load">
    {% include 'components/feedback/skeleton.html' with {
        'type': 'card',
        'count': 3
    } %}
</div>

{# Пустое состояние #}
{% if not items %}
    {% include 'components/feedback/empty-state.html' with {
        'icon': 'inbox',
        'title': 'Список пуст'
    } %}
{% endif %}

{# Карточки с данными #}
{% for item in items %}
    {% include 'components/layout/card.html' with {
        'title': item.name,
        'content': item.description
    } %}
{% endfor %}
```

## Roadmap

### Phase 1: ✅ Базовые компоненты
- Button, Badge, Icon, Tooltip
- Card, Modal
- Skeleton, Empty State, Loading, Alert

### Phase 2: 🔄 Интеграция с Fields
- Создать components/forms/ для базовых input
- Рефакторить fields/ чтобы использовали components/forms/
- Тестирование

### Phase 3: 📝 Рефакторинг страниц
- Обновить существующие страницы
- Использовать новые компоненты
- Empty states для пустых страниц
- Skeleton loaders для загрузки

## Best Practices

### Когда использовать Fields
- Редактирование моделей (AgentConfig, FlowConfig)
- CRUD операции с автогенерацией
- Inline редактирование в таблицах

### Когда использовать Components
- Лендинги и статические страницы
- Пустые состояния (Empty States)
- Модальные окна
- Кастомные интерфейсы
- Feedback (Loading, Alerts)

### Когда использовать оба
- Форма редактирования (fields/) в модалке (components/layout/modal.html)
- Skeleton loader (components/) пока грузим form (fields/)
- Alert (components/) при ошибке валидации поля (fields/)

## Примеры комбинирования

### Модалка с формой

```jinja2
{% include 'components/layout/modal.html' with {
    'id': 'edit-agent',
    'title': 'Редактировать агента',
    'content': render_fields(agent_config),  {# fields/ #}
    'actions': [
        {'text': 'Сохранить', 'variant': 'primary', 'type': 'submit'},
        {'text': 'Отмена', 'variant': 'secondary'}
    ]
} %}
```

### Страница с состояниями

```jinja2
{# Loading #}
<div id="content" hx-get="/api/agents">
    {% include 'components/feedback/skeleton.html' with {'type': 'card', 'count': 6} %}
</div>

{# Empty #}
{% if not agents %}
    {% include 'components/feedback/empty-state.html' with {...} %}
{% endif %}

{# Data #}
{% for agent in agents %}
    {% include 'components/complex/agent-card.html' with {'agent': agent} %}
{% endfor %}

{# Error #}
{% if error %}
    {% include 'components/feedback/alert.html' with {
        'type': 'danger',
        'title': 'Ошибка',
        'message': error
    } %}
{% endif %}
```

---

## Чеклист миграции

Когда обновляешь существующую страницу:

- [ ] Заменить кастомные кнопки на `components/base/button.html`
- [ ] Добавить Skeleton loader для HTMX загрузки
- [ ] Добавить Empty State если данных может не быть
- [ ] Использовать `components/layout/modal.html` для модалок
- [ ] Заменить кастомные alerts на `components/feedback/alert.html`
- [ ] Проверить адаптивность (mobile)
- [ ] Тестирование


# 🎨 Design System - Agent Lab Components

## Архитектура

### Правильная структура БЕЗ дублирования:

```
app/frontend/shared/templates/
├── components.html          # ← Реэкспортирует все (одна строка импорта!)
│
└── macros/                  # Оригинальные макросы (каждый в своем файле)
    ├── base.html           # button, badge, icon
    ├── feedback.html       # skeleton, empty_state, alert, loading
    ├── data.html           # platform_badge, status_badge, pagination
    ├── layout.html         # card, modal
    ├── forms.html          # input, textarea, select, checkbox
    ├── table.html          # table_container, table_row, table_empty
    └── navigation.html     # tabs, breadcrumbs, dropdown
```

**Принцип:**
- Каждый макрос в ОТДЕЛЬНОМ файле (модульность)
- `components.html` реэкспортирует через `{% from 'macros/...' import ... %}`
- В страницах: `{% import 'components.html' as c %}` - ОДНА строка!

**НЕТ дублирования!** Каждый макрос определен ОДИН раз.

---

## Быстрый старт

```jinja2
{# В начале любого шаблона #}
{% import 'components.html' as c %}

{# Используй все компоненты #}
{{ c.button('Создать', variant='primary', icon='plus') }}
{{ c.empty_state(icon='robot', title='Нет данных') }}
{{ c.skeleton(type='card', count=6) }}
{{ c.platform_badge('telegram') }}
{{ c.status_badge('active') }}
{{ c.pagination(offset, limit, total, '/api/list') }}

{# Call blocks #}
{% call c.card(title='Заголовок') %}
    Контент
{% endcall %}
```

---

## 📦 Все компоненты

### Base (macros/base.html)

**button** - Кнопки с HTMX
```jinja2
{{ c.button('Создать', variant='primary', icon='plus') }}
{{ c.button('Удалить', variant='danger', hx_delete='/api/item/123', hx_confirm='Уверены?') }}
```

**badge** - Бейджи
```jinja2
{{ c.badge('Beta', variant='warning', icon='star') }}
```

**icon** - Иконки
```jinja2
{{ c.icon('robot', size='lg') }}
```

---

### Feedback (macros/feedback.html)

**skeleton** - Skeleton loaders
```jinja2
{{ c.skeleton(type='card', count=6) }}
{{ c.skeleton(type='table', count=10) }}
{{ c.skeleton(type='list', count=5) }}
```

**empty_state** - Пустые состояния
```jinja2
{{ c.empty_state(
    icon='robot',
    title='Нет агентов',
    description='Создайте первого агента',
    button_text='Создать',
    button_onclick='createAgent()'
) }}
```

**alert** - Уведомления
```jinja2
{{ c.alert(type='success', message='Сохранено!') }}
{{ c.alert(type='danger', title='Ошибка', message=error, dismissible=true) }}
```

**loading** - Индикаторы
```jinja2
{{ c.loading() }}
{{ c.loading(text='Сохранение...', size='sm') }}
```

---

### Data (macros/data.html)

**platform_badge** - Бейджи платформ
```jinja2
{{ c.platform_badge('telegram') }}
{{ c.platform_badge('whatsapp') }}
```

**status_badge** - Бейджи статусов
```jinja2
{{ c.status_badge('active') }}
{{ c.status_badge('processing') }}
```

**pagination** - Навигация
```jinja2
{{ c.pagination(offset, limit, total, '/api/list', hx_target='#content') }}
```

**counter_badge** - Счетчики
```jinja2
{{ c.counter_badge(42, variant='primary') }}
```

---

### Layout (macros/layout.html)

**card** - Карточки
```jinja2
{% call c.card(title='Заголовок', icon='robot') %}
    <p>Контент</p>
{% endcall %}
```

**modal** - Модалки
```jinja2
{% call c.modal('my-modal', title='Подтверждение', icon='trash') %}
    <p>Удалить элемент?</p>
    {{ c.button('Да', variant='danger') }}
{% endcall %}
```

---

### Forms (macros/forms.html)

**input** - Текстовые поля
```jinja2
{{ c.input('email', label='Email', type='email', required=true) }}
{{ c.input('name', value=agent.name, hx_put='/api/update', hx_trigger='change delay:500ms') }}
```

**textarea** - Многострочные
```jinja2
{{ c.textarea('description', label='Описание', rows=5) }}
```

**select** - Выпадающие списки
```jinja2
{{ c.select('role', options=['admin', 'user'], label='Роль') }}
```

**checkbox** - Чекбоксы
```jinja2
{{ c.checkbox('enabled', label='Включено', checked=true) }}
```

---

### Table (macros/table.html)

**table_container** - Responsive обёртка
```jinja2
{% call c.table_container(min_width='1000px') %}
    <thead>
        <tr><th>Название</th><th>Статус</th></tr>
    </thead>
    <tbody>
        {% for item in items %}
        <tr>
            <td>{{ item.name }}</td>
            <td>{{ c.status_badge(item.status) }}</td>
        </tr>
        {% endfor %}
    </tbody>
{% endcall %}
```

**table_empty** - Пустая таблица
```jinja2
{{ c.table_empty('Нет данных', colspan=3) }}
```

---

### Navigation (macros/navigation.html)

**tabs** - Вкладки
```jinja2
{{ c.tabs(
    items=[
        {'id': 'all', 'text': 'Все', 'hx_get': '/api/all'},
        {'id': 'active', 'text': 'Активные', 'hx_get': '/api/active'}
    ],
    active='all'
) }}
```

**breadcrumbs** - Хлебные крошки
```jinja2
{{ c.breadcrumbs(
    items=[
        {'text': 'Главная', 'href': '/'},
        {'text': 'Агенты'}
    ]
) }}
```

**dropdown** - Выпадающее меню
```jinja2
{{ c.dropdown(
    button_text='Действия',
    items=[
        {'text': 'Редактировать', 'icon': 'pencil', 'onclick': 'edit()'},
        {'divider': true},
        {'text': 'Удалить', 'icon': 'trash', 'onclick': 'delete()'}
    ]
) }}
```

---

## Типичные паттерны

### Страница со списком
```jinja2
{% import 'components.html' as c %}

<div hx-get="/api/agents" hx-trigger="load">
    {{ c.skeleton(type='card', count=6) }}
</div>

{# В agents_list.html #}
{% import 'components.html' as c %}

{% if agents %}
    <div class="agents-grid">...</div>
{% else %}
    {{ c.empty_state(icon='robot', title='Нет агентов', button_text='Создать') }}
{% endif %}

{% if error %}
    {{ c.alert(type='danger', message=error, dismissible=true) }}
{% endif %}
```

### Таблица с пагинацией
```jinja2
{% import 'components.html' as c %}

{% call c.card(title='Сессии (' + total|string + ')') %}
    {{ c.counter_badge(sessions|length) }}
{% endcall %}

<div class="card-body p-0">
    {% if sessions %}
        {% call c.table_container(min_width='1000px') %}
            <thead>
                <tr>
                    <th>Платформа</th>
                    <th>Статус</th>
                </tr>
            </thead>
            <tbody>
                {% for s in sessions %}
                <tr>
                    <td>{{ c.platform_badge(s.platform) }}</td>
                    <td>{{ c.status_badge(s.status) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        {% endcall %}
        
        <div class="card-footer">
            {{ c.pagination(offset, limit, total, '/api/sessions') }}
        </div>
    {% else %}
        {{ c.empty_state(icon='inbox', title='Нет сессий') }}
    {% endif %}
</div>
```

---

## Добавление нового компонента

1. Создай макрос в нужном файле `macros/*.html`
2. Добавь `{% from 'macros/файл.html' import макрос %}` в `components.html`
3. Обнови `.cursor/rules/frontend.mdc`
4. Используй!

**Пример:**
```jinja2
{# В macros/base.html #}
{% macro tooltip(text, content) %}
<div data-tooltip="{{ text }}">{{ content }}</div>
{% endmacro %}

{# В components.html #}
{% from 'macros/base.html' import tooltip %}

{# Использование #}
{% import 'components.html' as c %}
{{ c.tooltip('Подсказка', 'Наведи на меня') }}
```

---

## Итого

- **7 модульных файлов** в `macros/`
- **1 файл реэкспорта** `components.html`
- **23 компонента** готовы к использованию
- **НЕТ дублирования** - каждый макрос определен один раз
- **Легко расширять** - добавь в `macros/`, реэкспортируй

**Документация компонентов:** См. комментарии в `macros/*.html`

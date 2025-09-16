# Agent Platform Frontend

Современный фронтенд на базе HTMX с темной темой в стиле Langflow. Основан на концепции **Backend-Driven Frontend** где Pydantic модели автоматически генерируют HTML через рекурсивный рендеринг.

## 🏗️ Архитектура

### Backend-Driven Frontend
- **Pydantic модели** автоматически создают HTML шаблоны
- **Рекурсивный рендеринг** - модели рендерят вложенные модели и поля
- **Monkey Patching** - расширяем `BaseModel` и `Field` для фронтенда
- **Динамические шаблоны** - по типу поля (`int.html`, `list_str.html`)

### Принцип рекурсивности

```python
# Модель рендерит себя
flow_model.render(view_mode="table")
  ├── Рендерит каждое поле
  │   ├── str поле → templates/fields/str.html
  │   ├── List[str] поле → templates/fields/list_str.html
  │   └── BaseModel поле → РЕКУРСИВНО вызывает render()
  └── Использует шаблон модели или wrapper
```

## 📁 Структура файлов

```
frontend/
├── README.md                 # Эта документация
├── field_extensions.py       # 🔥 ЯДРО: Monkey patch + рекурсивный рендеринг
├── environment.py            # Настройка Jinja2
├── model_registry.py         # Реестр моделей по storage_prefix
├── wrappers.py              # ModelListWrapper для списков
├── api/
│   ├── models.py            # API для CRUD операций (JSON)
│   └── pages.py             # HTML страницы (auth, dashboard)
├── templates/
│   ├── base.html            # Базовый шаблон
│   ├── auth.html            # Страница авторизации
│   ├── dashboard.html       # Главная страница
│   ├── fields/              # 🎯 Шаблоны полей по типам
│   │   ├── str.html         # string поля
│   │   ├── int.html         # integer поля
│   │   ├── bool.html        # boolean поля
│   │   ├── list_str.html    # List[str] поля
│   │   └── dict_str_any.html # Dict[str, Any] поля
│   ├── wrappers/            # Обертки для разных режимов
│   │   └── table.html       # Строка таблицы
│   └── models/              # Кастомные шаблоны моделей
│       └── ModelListWrapper.html # Таблица со списком
└── static/
    ├── css/                 # 🎨 Модульная система стилей
    │   ├── style.css        # Главный файл (импорты)
    │   ├── variables.css    # CSS переменные (темы)
    │   ├── base.css         # Базовые стили + утилиты
    │   ├── components.css   # Компоненты (кнопки, карточки, таблицы)
    │   ├── layout.css       # Лейаут (сайдбар, хедер, контент)
    │   └── fields.css       # Стили для полей форм
    └── js/
        └── app.js           # 🚀 Главный JS класс
```

## 🔥 Ключевые файлы

### `field_extensions.py` - ЯДРО СИСТЕМЫ
```python
# Monkey patch для BaseModel
def render(self, view_mode="form", **kwargs):
    # Рекурсивно рендерит все поля
    # Определяет шаблон по типу
    # Передает контекст дальше

# Monkey patch для Field  
def render(self, field_name, value, annotation, **kwargs):
    # Динамически находит шаблон по типу
    # list_str.html для List[str]
    # int.html для int
```

### Рекурсивный поток рендеринга
1. **Модель** вызывает `render(view_mode="table")`
2. **Итерируется** по всем полям модели
3. **Каждое поле** рендерится через свой шаблон
4. **Вложенные модели** рекурсивно вызывают `render()`
5. **Результат** собирается в финальный HTML

## 🎨 CSS Архитектура

### Модульная система (по БЭМ принципам)
- `variables.css` - CSS переменные для тем
- `base.css` - Сброс стилей + утилиты
- `components.css` - Переиспользуемые компоненты  
- `layout.css` - Структура страницы
- `fields.css` - Специфичные стили полей

### Темная тема Langflow
```css
:root {
    --bg-primary: #0f0f23;      /* Основной фон */
    --accent-primary: #6366f1;   /* Акцентный цвет */
    --text-primary: #ffffff;     /* Основной текст */
    --radius-lg: 12px;          /* Закругления */
}
```

## 🚀 JavaScript архитектура

### Класс APP (`static/js/app.js`)
```javascript
class APP {
    setupAuth()     // Авторизация + HTMX headers
    setupHTMX()     // Настройки HTMX
    setupUI()       // UI взаимодействия
    toggleTheme()   // Переключение темы
    showNotification() // Система уведомлений
}
```

## 🔄 HTMX Интеграция

### Принципы работы
- **JSON-only** общение через `hx-ext="json-enc"`
- **Минимум JavaScript** - все через HTMX атрибуты
- **Плавные анимации** через CSS transitions
- **Автоматическая авторизация** через headers

### Примеры HTMX
```html
<!-- Загрузка таблицы -->
<a hx-get="/frontend/models/flow?view=table" 
   hx-target="#content">Потоки</a>

<!-- Inline редактирование -->
<input hx-put="/frontend/models/flow/123?view=table"
       hx-ext="json-enc"
       hx-trigger="blur"
       hx-target="closest tr">
```

## 🎯 Динамическое определение шаблонов

### Логика в `get_template_name_from_type()`
```python
List[str] → "list_str"
Dict[str, Any] → "dict_str_any"  
Optional[int] → "int" (Optional игнорируется)
BaseModel → использует wrapper или модель
```

### Поиск шаблонов
1. `templates/fields/{type}.html` - специфичный шаблон
2. `templates/fields/base_field.html` - fallback
3. Для моделей: `templates/models/{ModelName}.html`
4. Для списков: `templates/wrappers/{view_mode}.html`

## 🔧 Режимы отображения (view_mode)

- **`form`** - Форма редактирования
- **`table`** - Строка в таблице (inline edit)
- **`cards`** - Карточки (будущее)

## ⚙️ Конфигурация полей

### Frontend-специфичные атрибуты Field
```python
Field(
    title="Название",
    description="Описание поля", 
    readonly=True,                    # Только чтение
    hidden=True,                      # Скрыто
    groups={'admin': {'required': True}}, # Правила по группам
    placeholder="Введите значение",
    help_text="Подсказка",
    css_class="custom-field",
    widget_attrs={"data-custom": "value"}
)
```

## 🔍 Группы пользователей

### Контекстная фильтрация
```python
# В модели автоматически
user_groups = self._get_current_user_groups()
if not self.is_field_visible_for_group(field_name, user_groups):
    continue  # Скрываем поле
```

## 📋 API Endpoints

### Models API (`/frontend/models/`)
- `GET /{model_type}?view=table` - Список моделей
- `GET /{model_type}/{model_id}` - Конкретная модель  
- `POST /{model_type}` - Создание модели
- `PUT /{model_type}/{model_id}` - Обновление модели
- `DELETE /{model_type}/{model_id}` - Удаление модели

### Pages API (`/frontend/`)
- `GET /` - Главная страница (редирект)
- `GET /auth` - Страница авторизации
- `GET /dashboard` - Панель управления

## 🛠️ Разработка

### Добавление нового типа поля
1. Создать `templates/fields/{type}.html`
2. Добавить CSS в `fields.css` если нужно
3. Тип автоматически определится по аннотации

### Добавление новой модели
1. Добавить `Config.storage_prefix` в модель
2. Зарегистрировать в `ModelRegistry`
3. Опционально создать `templates/models/{ModelName}.html`

### Кастомизация стилей
1. Переменные в `variables.css`
2. Компоненты в `components.css`  
3. Специфичные стили в соответствующие файлы

## 🎨 Дизайн система

### Цвета
- **Primary**: `#6366f1` (индиго)
- **Success**: `#10b981` (зеленый)
- **Danger**: `#ef4444` (красный)
- **Warning**: `#f59e0b` (желтый)

### Закругления
- **SM**: 6px - мелкие элементы
- **MD**: 8px - кнопки, поля
- **LG**: 12px - карточки
- **XL**: 16px - большие элементы

### Тени
- **SM**: Легкая тень для карточек
- **MD**: Средняя тень для hover
- **LG**: Глубокая тень для модалок
- **XL**: Максимальная тень для выпадающих меню

## 🚨 Важные принципы

1. **НЕ хардкодить типы** - все динамически
2. **Рекурсивность везде** - модели рендерят модели
3. **Monkey patch только в field_extensions.py**
4. **CSS переменные** для всех цветов/размеров
5. **Минимум JavaScript** - максимум HTMX
6. **JSON-only** общение с сервером
7. **Группы пользователей** учитывать везде
8. **view_mode** передавать в каждый рендер

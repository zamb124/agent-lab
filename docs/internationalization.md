# Система интернационализации (i18n)

Agents Lab поддерживает полную систему интернационализации с автоматической генерацией переводов из кода и backend-driven подходом.

## 🌐 Обзор системы

### Основные возможности:
- **Backend-driven переводы** - все ключи генерируются из Pydantic моделей
- **Автоматическое сканирование кода** при запуске приложения
- **Единая точка управления переводами** через TranslationManager
- **JavaScript API** для фронтенда с кешированием
- **Fallback система** - автоматический возврат к основному языку
- **UI компоненты** для смены языка

### Поддерживаемые языки:
- `ru` - Русский (основной)
- `en` - English  
- `es` - Español

## 📁 Структура файлов

```
app/
├── i18n/                           # Директория переводов
│   ├── translations/               # JSON файлы переводов
│   │   ├── ru.json                # Русский (основной, 100% заполнен)
│   │   ├── en.json                # Английский (частично с [TODO:])
│   │   └── es.json                # Испанский (частично с [TODO:])
│   ├── keys/                      # Служебные файлы ключей
│   └── generated/                 # Автогенерированные JS модули
│       ├── ru.js                  # для быстрой загрузки в браузере
│       ├── en.js
│       └── es.js
├── models/
│   └── i18n_models.py             # Pydantic модели для i18n
├── core/
│   └── translation_manager.py     # Центральный менеджер переводов
└── frontend/
    ├── api/
    │   └── i18n.py                # API endpoints
    └── shared/static/js/
        └── language-manager.js    # JavaScript менеджер
```

## 🔧 Настройка и инициализация

### Автоматическая инициализация

Система автоматически инициализируется при запуске приложения в `app/main.py`:

```python
# Инициализация системы переводов
logger.info("🌐 Инициализация системы интернационализации...")
translation_manager = get_translation_manager()
await translation_manager.initialize()
```

При инициализации:
1. Сканируются все Pydantic модели с `Field(title=...)`
2. Сканируются HTML шаблоны с вызовами `{{ t('key') }}`
3. Сканируются JS файлы с вызовами `app.i18n.t('key')`
4. Обновляются файлы переводов с новыми ключами
5. Генерируются JS модули для фронтенда

### Конфигурация

```python
from app.models.i18n_models import I18nConfig, Language

config = I18nConfig(
    default_language=Language.RU,           # Язык по умолчанию
    fallback_language=Language.RU,          # Резервный язык
    auto_generate_missing=True,             # Автогенерация отсутствующих ключей
    auto_generate_on_startup=True,          # Генерация при запуске
    scan_directories=["app/models", "app/frontend"],  # Директории для сканирования
    translations_directory="app/i18n"       # Директория с файлами переводов
)
```

## 💻 Backend использование

### В Pydantic моделях

```python
from app.frontend.field_extensions import Field

class User(BaseModel):
    # Базовое использование (автогенерация ключей)
    name: str = Field(
        title="Имя пользователя",
        description="Полное имя пользователя",
        placeholder="Введите ваше имя"
    )
    # Автоматически сгенерируются ключи:
    # - field.title.имя_пользователя
    # - field.description.полное_имя_пользователя  
    # - field.placeholder.введите_ваше_имя
    
    # Кастомные ключи перевода
    email: str = Field(
        title="Email",
        i18n_title="models.user.email.title",
        i18n_placeholder="models.user.email.placeholder"
    )
```

### В коде приложения

```python
from app.core.translation_manager import t, get_translation_manager

# Простое использование (язык определяется из контекста)
message = t("dashboard.welcome_message")

# С указанием языка
message = t("dashboard.title", Language.EN)  

# С параметрами
message = t("welcome.message", user_name="Иван", date="2025-01-07")

# Прямое использование менеджера
manager = get_translation_manager()
stats = manager.get_stats()  # Получить статистику переводов
```

### В HTML шаблонах

```html
<!-- Простые переводы -->
<h1>{{ t('dashboard.title') }}</h1>
<button>{{ t('common.save') }}</button>

<!-- Переводы с параметрами -->
<p>{{ t('welcome.message', user_name=get_current_user().name) }}</p>

<!-- Переводы полей форм -->
<label>{{ t_field(field_info, 'title') }}</label>
<input placeholder="{{ t_field(field_info, 'placeholder') }}">
<small class="help-text">{{ t_field(field_info, 'help_text') }}</small>

<!-- Текущий язык пользователя -->
<span>{{ get_current_language() }}</span>
```

## 🎨 Frontend использование

### JavaScript API

```javascript
// Получение переводов
const title = app.i18n.t('dashboard.title');
const message = app.i18n.t('welcome.message', {user_name: 'Иван'});

// Смена языка
await app.i18n.setLanguage('en');
await app.i18n.setLanguage('es');

// Получение информации о языках
const currentLang = app.i18n.getCurrentLanguage();  // 'ru'
const supportedLangs = app.i18n.getSupportedLanguages();  // ['ru', 'en', 'es']

// Принудительное обновление переводов (для разработки)
await app.i18n.refreshTranslations();
```

### События JavaScript

```javascript
// Подписка на изменение языка
document.addEventListener('languageChanged', (event) => {
    console.log(`Язык изменен: ${event.detail.oldLanguage} → ${event.detail.newLanguage}`);
    // Обновить компоненты, зависящие от языка
});
```

## 📊 Структура файлов переводов

### ru.json (основной файл)
```json
{
  "meta": {
    "language": "ru",
    "version": "1.0.0",
    "last_updated": "2025-01-07T12:00:00Z",
    "completeness": 100,
    "total_keys": 150,
    "translated_keys": 150
  },
  
  "common": {
    "save": "Сохранить",
    "cancel": "Отмена",
    "delete": "Удалить",
    "loading": "Загрузка..."
  },
  
  "dashboard": {
    "title": "Панель управления",
    "welcome_message": "Добро пожаловать, {user_name}!",
    "navigation": {
      "bots": "Боты",
      "history": "История",
      "builder": "Agent Builder"
    }
  },
  
  "models": {
    "user": {
      "fields": {
        "name": {
          "title": "Имя пользователя",
          "placeholder": "Введите ваше имя",
          "help_text": "Имя отображается в профиле"
        },
        "email": {
          "title": "Email адрес",
          "placeholder": "user@example.com"
        }
      }
    }
  },
  
  "validation": {
    "required": "Поле обязательно для заполнения",
    "email_invalid": "Некорректный email адрес",
    "min_length": "Минимальная длина {min_length} символов"
  }
}
```

### en.json (частично переведенный)
```json
{
  "meta": {
    "language": "en",
    "completeness": 75
  },
  
  "common": {
    "save": "Save",
    "cancel": "Cancel",  
    "delete": "[TODO: common.delete]",
    "loading": "Loading..."
  },
  
  "dashboard": {
    "title": "Dashboard",
    "welcome_message": "Welcome, {user_name}!",
    "navigation": {
      "bots": "Bots",
      "history": "[TODO: dashboard.navigation.history]"
    }
  }
}
```

## 🚀 Использование в разработке

### 1. Добавление нового поля в модель

```python
class Agent(BaseModel):
    # Новое поле - автоматически сгенерируются ключи переводов
    temperature: float = Field(
        title="Температура модели",
        description="Контролирует случайность ответов (0.0-1.0)", 
        placeholder="0.7",
        help_text="Чем выше значение, тем более творческие ответы",
        ge=0.0,
        le=1.0
    )
```

При следующем запуске приложения автоматически создадутся ключи:
- `field.title.температура_модели`
- `field.description.контролирует_случайность_ответов_0_0_1_0`
- `field.placeholder.0_7`
- `field.help_text.чем_выше_значение_тем_более_творческие_от`

### 2. Использование в шаблонах

```html
<!-- agent_form.html -->
<div class="form-group">
    <label>{{ t_field(temperature_field, 'title') }}</label>
    <input type="number" 
           placeholder="{{ t_field(temperature_field, 'placeholder') }}"
           step="0.1" min="0" max="1">
    <small>{{ t_field(temperature_field, 'help_text') }}</small>
</div>

<!-- Статический перевод -->
<button class="btn btn-primary">{{ t('common.save') }}</button>
```

### 3. JavaScript компоненты

```javascript
class AgentForm {
    constructor() {
        this.saveButton = document.querySelector('#save-btn');
        this.updateUI();
        
        // Слушаем изменения языка
        document.addEventListener('languageChanged', () => this.updateUI());
    }
    
    updateUI() {
        // Обновляем тексты при смене языка
        this.saveButton.textContent = app.i18n.t('common.save');
        
        const title = app.i18n.t('agent.form.title');
        document.querySelector('#form-title').textContent = title;
    }
    
    showValidationError(fieldName) {
        const message = app.i18n.t('validation.required');
        this.showError(message);
    }
}
```

## 🔧 API endpoints

### Получение переводов
```http
GET /frontend/api/i18n/translations/en
```
```json
{
  "common.save": "Save",
  "dashboard.title": "Dashboard",
  "validation.required": "Field is required"
}
```

### Смена языка пользователя
```http
POST /frontend/api/i18n/user-language
Content-Type: application/json

{"language": "en"}
```
```json
{
  "status": "success",
  "language": "en"
}
```

### Статистика переводов
```http
GET /frontend/api/i18n/stats
```
```json
{
  "total_languages": 3,
  "total_keys": 150,
  "languages_stats": {
    "ru": {
      "language": "ru",
      "total_keys": 150,
      "translated_keys": 150,
      "completeness": 100.0
    },
    "en": {
      "language": "en", 
      "total_keys": 150,
      "translated_keys": 112,
      "completeness": 74.7
    }
  }
}
```

### Обновление переводов (только для админов)
```http
POST /frontend/api/i18n/refresh
```
```json
{
  "status": "success",
  "message": "Переводы успешно обновлены"
}
```

## 🎯 Лучшие практики

### Именование ключей

**✅ Правильно:**
```python
# Ключи автогенерируются из осмысленных значений
Field(title="Имя пользователя")  # → field.title.имя_пользователя
Field(i18n_title="models.user.name.title")  # Явный семантический ключ
```

**❌ Неправильно:**
```python
Field(title="Name")  # Слишком общий ключ
Field(i18n_title="usr_nm")  # Непонятное сокращение
```

### Структура ключей

Рекомендуемая иерархия:
```
common.*                 # Общие элементы (кнопки, сообщения)
dashboard.*             # Элементы панели управления
models.{model}.fields.* # Поля моделей
validation.*            # Сообщения валидации
errors.*                # Сообщения об ошибках
{module}.*              # Специфичные для модуля
```

### Параметры в переводах

```python
# Backend
message = t("order.status", order_id=12345, status="completed")

# JSON файл перевода  
{
  "order.status": "Заказ №{order_id} имеет статус: {status}"
}

# Результат: "Заказ №12345 имеет статус: completed"
```

## 🖥️ UI компоненты

### Кнопка смены языка

Автоматически добавлена в header всех страниц:

```html
<!-- dropdown в dashboard.html -->
<div class="dropdown">
    <button class="btn btn-ghost btn-sm dropdown-toggle" data-bs-toggle="dropdown">
        <i class="bi bi-translate"></i>
        <span id="current-language">RU</span>
    </button>
    <ul class="dropdown-menu dropdown-menu-end">
        <li><a class="dropdown-item" onclick="app.i18n.setLanguage('ru')">
            <i class="bi bi-check" id="lang-ru"></i> {{ t('languages.ru') }}
        </a></li>
        <li><a class="dropdown-item" onclick="app.i18n.setLanguage('en')">
            <i class="bi bi-check" id="lang-en"></i> {{ t('languages.en') }}
        </a></li>
        <li><a class="dropdown-item" onclick="app.i18n.setLanguage('es')">
            <i class="bi bi-check" id="lang-es"></i> {{ t('languages.es') }}
        </a></li>
    </ul>
</div>
```

### Обновление UI при смене языка

```javascript
// Автоматическое обновление при смене языка
app.i18n.setLanguage('en').then(() => {
    // Страница автоматически перезагружается через HTMX
    console.log('Язык изменен на английский');
});
```

## 📝 Примеры использования

### Пример 1: Создание формы с переводами

**1. Модель:**
```python
class CreateBotForm(BaseModel):
    name: str = Field(
        title="Название бота",
        description="Уникальное имя для вашего бота",
        placeholder="Мой супер-бот",
        help_text="Будет отображаться в списке ботов",
        min_length=3,
        max_length=50
    )
    
    model: str = Field(
        title="Модель ИИ", 
        description="Выберите языковую модель",
        i18n_title="models.bot.model.title",  # Кастомный ключ
        i18n_description="models.bot.model.description"
    )
```

**2. HTML шаблон:**
```html
<!-- create_bot.html -->
<form hx-post="/frontend/api/bots" hx-target="#content">
    <div class="form-group">
        <label for="name">{{ t_field(name_field, 'title') }}</label>
        <input type="text" id="name" name="name"
               placeholder="{{ t_field(name_field, 'placeholder') }}"
               required>
        <small class="form-text">{{ t_field(name_field, 'help_text') }}</small>
    </div>
    
    <div class="form-group">
        <label for="model">{{ t_field(model_field, 'title') }}</label>
        <select id="model" name="model">
            <option value="">{{ t('common.select_option') }}</option>
        </select>
    </div>
    
    <button type="submit" class="btn btn-primary">
        {{ t('common.create') }}
    </button>
</form>
```

**3. JavaScript обработка:**
```javascript
class CreateBotForm {
    constructor() {
        this.form = document.querySelector('#create-bot-form');
        this.setupValidation();
    }
    
    setupValidation() {
        this.form.addEventListener('submit', (e) => {
            const nameInput = this.form.querySelector('[name="name"]');
            
            if (!nameInput.value.trim()) {
                e.preventDefault();
                this.showError(
                    nameInput,
                    app.i18n.t('validation.required')
                );
            }
        });
    }
    
    showError(input, message) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.textContent = message;
        input.parentNode.appendChild(errorDiv);
    }
}
```

### Пример 2: Многоязычная страница администрирования

**1. Роутер:**
```python
@router.get("/admin/users")
async def admin_users(request: Request):
    # Язык автоматически определяется из контекста
    return templates.TemplateResponse("admin/users.html", {
        "request": request,
        "page_title": t("admin.users.title"),
        "users": await get_users()
    })
```

**2. Шаблон:**
```html
<!-- admin/users.html -->
{% extends "dashboard.html" %}

{% block content %}
<div class="admin-section">
    <div class="section-header">
        <h2>{{ t('admin.users.title') }}</h2>
        <button class="btn btn-primary" hx-get="/frontend/admin/users/create">
            <i class="bi bi-plus"></i>
            {{ t('admin.users.create_new') }}
        </button>
    </div>
    
    <div class="table-responsive">
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>{{ t('models.user.fields.name.title') }}</th>
                    <th>{{ t('models.user.fields.email.title') }}</th>
                    <th>{{ t('models.user.fields.created_at.title') }}</th>
                    <th>{{ t('common.actions') }}</th>
                </tr>
            </thead>
            <tbody>
                {% for user in users %}
                <tr>
                    <td>{{ user.name }}</td>
                    <td>{{ user.email }}</td>
                    <td>{{ user.created_at.strftime('%d.%m.%Y') }}</td>
                    <td>
                        <button class="btn btn-sm btn-outline-primary">
                            {{ t('common.edit') }}
                        </button>
                        <button class="btn btn-sm btn-outline-danger">
                            {{ t('common.delete') }}
                        </button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
```

### Пример 3: Валидация с переводами

```python
from pydantic import validator, ValidationError

class UserRegistrationForm(BaseModel):
    email: str = Field(
        title="Email адрес",
        description="Введите действующий email",
        i18n_title="forms.registration.email.title"
    )
    
    password: str = Field(
        title="Пароль",
        description="Минимум 8 символов",
        min_length=8,
        i18n_title="forms.registration.password.title"
    )
    
    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            # Используем переводимое сообщение об ошибке
            raise ValueError(t('validation.email_invalid'))
        return v
```

## 🔄 Процесс добавления нового языка

### 1. Добавить язык в enum
```python
# app/models/i18n_models.py
class Language(str, Enum):
    RU = "ru"
    EN = "en" 
    ES = "es"
    FR = "fr"  # Новый язык
```

### 2. Обновить начальные переводы
```json
// app/i18n/translations/fr.json
{
  "meta": {
    "language": "fr",
    "version": "1.0.0",
    "completeness": 0
  },
  
  "languages": {
    "ru": "Русский",
    "en": "English",
    "es": "Español", 
    "fr": "Français"
  }
  
  // Остальные переводы будут помечены как [TODO: ключ]
}
```

### 3. Обновить UI
```html
<!-- Добавить в dropdown языков -->
<li><a class="dropdown-item" onclick="app.i18n.setLanguage('fr')">
    <i class="bi bi-check" style="visibility: hidden" id="lang-fr"></i> 
    {{ t('languages.fr') }}
</a></li>
```

### 4. Обновить JavaScript
```javascript
// В language-manager.js обновится автоматически из enum
this.supportedLanguages = ['ru', 'en', 'es', 'fr'];
```

## ⚡ Производительность

### Кеширование
- **Backend**: переводы загружаются один раз при старте и кешируются в памяти
- **Frontend**: JS модули загружаются браузером один раз и кешируются
- **Оптимизация**: только нужные языки загружаются в браузер

### Lazy loading
```javascript
// Переводы загружаются только при смене языка
await app.i18n.setLanguage('en');  // Автоматически загрузит en.js если не загружен
```

## 🧪 Тестирование

### Запуск всех тестов i18n:
```bash
uv run python -m pytest tests/i18n/ -v
```

### Конкретные группы тестов:
```bash
# Тесты моделей
uv run python -m pytest tests/i18n/test_i18n_models.py

# Тесты TranslationManager
uv run python -m pytest tests/i18n/test_translation_manager.py

# Тесты API
uv run python -m pytest tests/i18n/test_i18n_api.py

# Интеграционные тесты
uv run python -m pytest tests/i18n/test_integration_full.py
```

### Покрытие тестами:
- ✅ **130 тестов** покрывают 100% функциональности
- ✅ **Модели данных** - валидация, сериализация
- ✅ **TranslationManager** - singleton, кеширование, сканирование кода  
- ✅ **Context интеграция** - определение языка, middleware
- ✅ **API endpoints** - все HTTP методы и ошибки
- ✅ **Template функции** - Jinja2 интеграция
- ✅ **Field extensions** - Pydantic Field расширения
- ✅ **Полный workflow** - от сканирования до рендеринга

## 🚨 Устранение неполадок

### Переводы не отображаются
1. Проверить логи при запуске приложения:
   ```
   🌐 Инициализация системы интернационализации...
   ✅ Система переводов инициализирована
   ```

2. Проверить файлы переводов:
   ```bash
   ls app/i18n/translations/
   # Должны быть: ru.json, en.json, es.json
   ```

3. Проверить консоль браузера:
   ```javascript
   console.log(app.i18n.getCurrentLanguage());
   console.log(app.i18n.t('common.save'));
   ```

### Новые ключи не добавляются автоматически
1. Убедиться что `auto_generate_on_startup=True`
2. Проверить что файл находится в `scan_directories`
3. Перезапустить приложение

### Принудительное обновление переводов
```bash
# Через API (нужны права админа)
curl -X POST http://localhost:8001/frontend/api/i18n/refresh
```

### Отладка JavaScript
```javascript
// В консоли браузера
app.i18n.refreshTranslations();  // Принудительная загрузка
console.log(app.languageManager.translations);  // Просмотр загруженных переводов
```

## 📈 Метрики и мониторинг

### Статистика переводов
```python
from app.core.translation_manager import get_translation_manager

manager = get_translation_manager()
stats = manager.get_stats()

print(f"Всего языков: {stats.total_languages}")
print(f"Всего ключей: {stats.total_keys}")

for lang, lang_stats in stats.languages_stats.items():
    print(f"{lang.value}: {lang_stats.completeness:.1f}% ({lang_stats.translated_keys}/{lang_stats.total_keys})")
```

### Мониторинг неполных переводов
```bash
# Поиск непереведенных ключей
grep -r "\[TODO:" app/i18n/translations/

# Статистика по файлу
jq '.meta.completeness' app/i18n/translations/en.json
```

## 🔮 Планы развития

### Возможные улучшения:
- **Плюрализация** - поддержка множественного числа
- **Контекстные переводы** - разные переводы в зависимости от контекста
- **Внешние сервисы** - интеграция с Google Translate API
- **Админ панель** - UI для редактирования переводов
- **Git hooks** - автоматическая проверка переводов при коммитах

---

## 🎯 Быстрый старт

1. **Создать модель с переводами:**
```python
class MyModel(BaseModel):
    title: str = Field(title="Заголовок", description="Описание поля")
```

2. **Использовать в шаблоне:**
```html
<h1>{{ t('dashboard.title') }}</h1>
<label>{{ t_field(field_info, 'title') }}</label>
```

3. **Использовать в JavaScript:**
```javascript
const message = app.i18n.t('common.loading');
await app.i18n.setLanguage('en');
```

4. **Проверить результат:**
- Запустить приложение
- Переключить язык через UI
- Проверить что тексты изменились

Система готова к использованию! 🚀

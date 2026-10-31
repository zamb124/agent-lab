# Core Frontend Library

Общая библиотека UI компонентов для всех сервисов платформы.

## Структура

```
core/frontend/static/
├── assets/               # Статические ресурсы
│   ├── js/              # Lit, marked
│   ├── css/             # tokens.css, reset.css
│   └── icons/           # SVG иконки
├── lib/                 # UI компоненты и утилиты
│   ├── components/      # Platform UI Kit
│   ├── platform-element/# Базовый класс для компонентов
│   ├── events/          # EventBus, фабрики, reducers, effects
│   ├── styles/          # Общие стили
│   └── utils/           # Утилиты
└── pwa/                 # Service Worker, offline, icons
```

## Использование в других сервисах

### 1. Монтирование в FastAPI

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
```

### 2. Стили и бандл в HTML

Зависимости — npm-пакеты, собранные esbuild в `ui-dist/`; import map
не нужен: bare-спецификаторы в бандле отсутствуют, lazy-части —
динамические чанки `chunks/`.

```html
<link rel="stylesheet" href="/static/core/assets/css/tokens.css">
<link rel="stylesheet" href="/static/core/assets/css/reset.css">
<script type="module" src="/<svc>/ui/static/index.js"></script>
```

### 3. Использование компонентов

```javascript
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/glass-card.js';
import '@platform/lib/components/fields/platform-field.js';

// В HTML
<glass-card>
    <h2>Login</h2>
    <platform-field type="email" label="Email"></platform-field>
    <glass-button variant="primary">Submit</glass-button>
</glass-card>
```

Доменное состояние — только через фабрики (`createAsyncOp`, `createResourceCollection`, …) в `apps/<svc>/ui/events/resources/`. Подробности — `frontend.mdc`, `ui_factories.mdc`.

## Доступные компоненты

- `glass-button` — кнопка с вариантами: primary, secondary, danger, ghost
- `glass-card` — карточка с glass эффектом
- `platform-field` — единственный канон полей ввода/отображения

## CSS Variables

Все токены дизайн-системы доступны через CSS Variables:
- `--accent` — основной цвет
- `--glass-solid-medium` — glass фон
- `--text-primary`, `--text-secondary` — цвета текста
- `--space-*` — отступы
- `--radius-*` — радиусы скругления

См. полный список в `assets/css/tokens.css`

# Core Frontend Library

Общая библиотека UI компонентов для всех сервисов платформы.

## Структура

```
core/frontend/static/
├── assets/               # Статические ресурсы
│   ├── js/              # Lit, Zustand, marked
│   ├── css/             # tokens.css, reset.css
│   └── icons/           # SVG иконки
├── lib/                 # UI компоненты и утилиты
│   ├── components/      # Glass UI компоненты
│   ├── platform-element/# Базовый класс для компонентов
│   ├── styles/          # Общие стили
│   └── utils/           # Утилиты
└── services/            # Сервисы (auth, theme, store)
```

## Использование в других сервисах

### 1. Монтирование в FastAPI

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
```

### 2. Import Map в HTML

```html
<script type="importmap">
{
    "imports": {
        "lit": "/static/core/assets/js/lit/lit.min.js",
        "lit/decorators.js": "/static/core/assets/js/lit/decorators.min.js",
        "lit/directives/class-map.js": "/static/core/assets/js/lit/directives/class-map.min.js",
        "lit/directives/guard.js": "/static/core/assets/js/lit/directives/guard.min.js",
        "@platform/lib/": "/static/core/lib/",
        "@platform/services/": "/static/core/services/"
    }
}
</script>

<link rel="stylesheet" href="/static/core/assets/css/tokens.css">
<link rel="stylesheet" href="/static/core/assets/css/reset.css">
```

### 3. Использование компонентов

```javascript
import { GlassButton } from '@platform/lib/components/glass-button.js';
import { GlassCard } from '@platform/lib/components/glass-card.js';
import { GlassInput } from '@platform/lib/components/glass-input.js';

// В HTML
<glass-card>
    <h2>Login</h2>
    <glass-input type="email" placeholder="Email"></glass-input>
    <glass-button variant="primary">Submit</glass-button>
</glass-card>
```

## Доступные компоненты

- `glass-button` - кнопка с вариантами: primary, secondary, danger, ghost
- `glass-card` - карточка с glass эффектом
- `glass-input` - поле ввода

## CSS Variables

Все токены дизайн-системы доступны через CSS Variables:
- `--accent` - основной цвет
- `--glass-solid-medium` - glass фон
- `--text-primary`, `--text-secondary` - цвета текста
- `--space-*` - отступы
- `--radius-*` - радиусы скругления

См. полный список в `assets/css/tokens.css`



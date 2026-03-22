# Современная архитектура Lit компонентов - Руководство

## Обзор

Мы реализовали современную архитектуру для Lit компонентов с полным разделением CSS, HTML и JavaScript, следуя best practices 2025 года.

## Паттерны использования

### 1. Маленькие компоненты (<100 строк CSS)

**Структура файлов:**
```
components/button/
├── index.js     # Класс компонента
└── styles.js    # Стили компонента
```

**Пример: button/styles.js**
```javascript
import { css } from 'lit';

export const buttonStyles = css`
    :host {
        display: inline-block;
    }
    
    button {
        padding: var(--space-2) var(--space-4);
        background: var(--accent);
        color: white;
        border: none;
        border-radius: var(--radius-md);
        cursor: pointer;
    }
`;
```

**Пример: button/index.js**
```javascript
import { html } from 'lit';
import { PlatformElement } from '../../core/platform-element/index.js';
import { buttonStyles } from './styles.js';

export class PlatformButton extends PlatformElement {
    static styles = [
        PlatformElement.styles,  // Базовые + glass стили
        buttonStyles             // Стили компонента
    ];

    render() {
        return html`<button><slot></slot></button>`;
    }
}

customElements.define('platform-button', PlatformButton);
```

### 2. Средние компоненты (100-300 строк)

**Структура файлов:**
```
components/input/platform-input/
├── index.js     # Класс компонента
└── styles.js    # Стили компонента
```

Паттерн такой же, как для маленьких компонентов.

### 3. Большие компоненты (>300 строк)

**Структура файлов:**
```
features/flow-editor/flow-canvas/
├── index.js              # Основной класс
├── templates.js          # HTML шаблоны
├── events.js             # Event handlers
├── drawflow.css          # Чистый CSS для Light DOM
└── drawflow-injector.js  # Инжектор глобальных стилей
```

**Пример: templates.js**
```javascript
import { html } from 'lit';

export function renderCanvas(component) {
    return html`
        <div class="canvas-container">
            ${renderContent(component)}
            ${renderControls(component)}
        </div>
    `;
}

function renderContent(component) {
    return html`<div id="content">...</div>`;
}

function renderControls(component) {
    return html`
        <button @click=${component.handleClick}>
            Click me
        </button>
    `;
}
```

**Пример: events.js**
```javascript
export function setupEvents(component) {
    component._editor.on('change', () => {
        component.emit('changed');
    });
}

export function setupDragDrop(component) {
    const container = component.querySelector('#container');
    container.addEventListener('drop', (e) => {
        // Handle drop
    });
}
```

**Пример: index.js**
```javascript
import { PlatformElement } from '../../../core/platform-element/index.js';
import { renderCanvas } from './templates.js';
import { setupEvents, setupDragDrop } from './events.js';
import { injectStyles } from './injector.js';

export class MyCanvas extends PlatformElement {
    connectedCallback() {
        super.connectedCallback();
        injectStyles();
        setupEvents(this);
        setupDragDrop(this);
    }

    render() {
        return renderCanvas(this);
    }
}
```

## Использование shared стилей

### Glass Morphism

```javascript
import { glassStyles } from '../../../core/shared/glass.styles.js';

static styles = [
    PlatformElement.styles,
    glassStyles,
    myStyles
];

// В HTML используйте классы
html`<div class="glass-medium">Content</div>`
```

### Typography

```javascript
import { typographyStyles } from '../../../core/shared/typography.styles.js';

static styles = [
    PlatformElement.styles,
    typographyStyles
];

// В HTML
html`<span class="text-lg font-semibold">Title</span>`
```

### Animations

```javascript
import { animationStyles } from '../../../core/shared/animations.styles.js';

static styles = [
    PlatformElement.styles,
    animationStyles
];

// В HTML
html`<div class="animate-fade-in">Appears smoothly</div>`
```

## Light DOM для сторонних библиотек

Для интеграции с библиотеками вроде Drawflow, которым нужны глобальные стили:

```javascript
export class MyComponent extends PlatformElement {
    // Используем Light DOM вместо Shadow DOM
    createRenderRoot() {
        return this;
    }

    connectedCallback() {
        super.connectedCallback();
        injectGlobalStyles();  // Инжектим стили в document.head
    }
}
```

## Utilities CSS

Подключите utilities.css в `index.html`:

```html
<link rel="stylesheet" href="/ui/styles/utilities.css">
```

Используйте утилиты в компонентах:

```javascript
html`
    <div class="flex items-center gap-2">
        <span class="text-sm text-secondary">Label</span>
        <button class="cursor-pointer">Click</button>
    </div>
`
```

## Миграция существующих компонентов

### Шаг 1: Создайте структуру папок

```bash
mkdir -p components/my-component
```

### Шаг 2: Вынесите CSS в styles.js

```javascript
// components/my-component/styles.js
import { css } from 'lit';

export const myComponentStyles = css`
    /* Ваши стили здесь */
`;
```

### Шаг 3: Обновите index.js

```javascript
// components/my-component/index.js
import { PlatformElement } from '../../core/platform-element/index.js';
import { myComponentStyles } from './styles.js';

export class MyComponent extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        myComponentStyles
    ];
    
    // Остальной код
}
```

### Шаг 4: Обновите импорт в главном index.js

```javascript
// ui/index.js
await import('./components/my-component/index.js');
```

## Best Practices

1. **Всегда наследуйтесь от PlatformElement** - получите базовые стили и сервисы
2. **Используйте css`` литералы** - они кэшируются Lit автоматически
3. **Выносите большие шаблоны** - если render() >100 строк, создайте templates.js
4. **Группируйте event handlers** - если их >5, создайте events.js
5. **Используйте shared стили** - не дублируйте glass/typography классы
6. **Light DOM только для legacy** - для Drawflow и подобных библиотек
7. **Utilities для простых стилей** - вместо создания CSS классов

## Совместимость

- ✅ Lit 3.x
- ✅ Shadow DOM и Light DOM
- ✅ Constructible Stylesheets
- ✅ Hot Module Replacement (HMR)
- ✅ CSS Custom Properties (CSS Variables)
- ✅ Полная обратная совместимость

## Производительность

- CSS кэшируется Lit один раз на класс
- Shared стили загружаются один раз
- Lazy loading через dynamic imports
- Минимальный bundle size

## Заключение

Эта архитектура обеспечивает:
- 🎯 **Прозрачность** - четкое разделение ответственности
- 📦 **Модульность** - легко переиспользовать компоненты
- 🚀 **Производительность** - оптимальная загрузка
- 🛠️ **Maintainability** - легко поддерживать и расширять
- 👥 **Team-friendly** - несколько разработчиков работают без конфликтов


# I18n Service - Система переводов для Frontend

Легковесная система локализации для Lit компонентов без внешних зависимостей.

## Особенности

- Стартовая локаль без сохранённого выбора: `ru`, если основной язык из `navigator.languages` / `navigator.language` — русский; иначе `en`
- Сохранение выбранного языка в localStorage
- Реактивное обновление компонентов при смене языка
- Поддержка вложенных ключей переводов
- Интерполяция параметров в строках
- Fallback на основной язык

## Быстрый старт

### 1. Импорт

```javascript
import { i18n, useI18n, t } from '@platform/services/i18n/i18n.service.js';
```

После `registerCore` в компонентах доступен **`this.i18n`** (`PlatformElement`); не присваивайте результат `useI18n` в **`this.i18n`** — перезапишете геттер. Вызов **`this.i18n.t(key, params)`** без третьего аргумента использует **дефолтный namespace**: после **`initServices`** **`PlatformApp`** выставляет его через **`i18n.setDefaultNamespace`** по правилу из **`i18n-default-namespace.js`** — сегмент пути **`getBaseUrl()`** без ведущего `/` совпадает с именем JSON (например `/crm` → `crm.json`). Дополнительные бандлы (не основной slug SPA): **`import { I18nNs } from '@platform/services/i18n/i18n.service.js'`** и **`this.i18n.t(key, params, I18nNs.BILLING)`** (также **`I18nNs.LANDING`**, **`I18nNs.PLATFORM`**, **`I18nNs.FRONTEND_PRODUCTS`**) — реестр в **`i18n-default-namespace.js`**.

### 2. Использование в Lit компоненте

#### Вариант A: С хуком `useI18n` (рекомендуется)

```javascript
import { html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { useI18n } from '@platform/services/i18n/i18n.service.js';

export class MyComponent extends PlatformElement {
    constructor() {
        super();
        this.i18n = useI18n(this);
    }

    _switchLanguage() {
        const newLocale = this.i18n.locale() === 'ru' ? 'en' : 'ru';
        this.i18n.setLocale(newLocale);
    }

    render() {
        return html`
            <h1>${this.i18n.t('hero.title')}</h1>
            <p>${this.i18n.t('hero.subtitle', { name: 'World' })}</p>
            <button @click=${this._switchLanguage}>
                ${this.i18n.locale() === 'ru' ? 'EN' : 'RU'}
            </button>
        `;
    }
}
```

#### Вариант B: Прямое использование функции `t()`

```javascript
import { t } from '@platform/services/i18n/i18n.service.js';

// В render методе
render() {
    return html`
        <h1>${t('hero.title')}</h1>
        <p>${t('hero.subtitle')}</p>
    `;
}
```

### 3. Структура ключей переводов

Переводы организованы по namespace (файлам):

```javascript
// Без третьего аргумента — ключ внутри текущего дефолтного namespace (см. PlatformApp / setDefaultNamespace)
t('hero.title')

// Явный другой бандл
t('title', {}, 'common')
```

## API

### `i18n.setLocale(locale: string)`

Переключает язык приложения.

```javascript
await i18n.setLocale('en');
```

### `i18n.getCurrentLocale(): string`

Возвращает текущий язык.

```javascript
const locale = i18n.getCurrentLocale(); // 'ru' | 'en'
```

### `i18n.t(key: string, params?: object, namespace?: string): string`

Получает перевод по ключу. Если **`namespace`** не передан, используется **`i18n.getDefaultNamespace()`** (изначально **`landing`**, приложение может выставить в **`initServices`**).

```javascript
i18n.t('hero.title')

i18n.t('hello', { name: 'John' })

i18n.t('submit', {}, 'common')
```

### `i18n.setDefaultNamespace(namespace: string): void` / `i18n.getDefaultNamespace(): string`

Дефолтный бандл для вызовов **`t`** без третьего аргумента. После **`registerCore`** задаётся из **`PlatformApp.initServices`** по **`i18nDefaultNamespaceForBaseUrl(getBaseUrl())`** ([`i18n-default-namespace.js`](./i18n-default-namespace.js)).

### `i18n.subscribe(callback: Function): Function`

Подписка на изменение языка.

```javascript
const unsubscribe = i18n.subscribe((locale) => {
    console.log('Locale changed to:', locale);
});

// Отписка
unsubscribe();
```

### `i18n.getSupportedLocales(): string[]`

Возвращает список поддерживаемых языков.

```javascript
const locales = i18n.getSupportedLocales(); // ['ru', 'en']
```

### `i18n.getLocaleName(locale: string): string`

Возвращает название языка.

```javascript
i18n.getLocaleName('ru'); // 'Русский'
i18n.getLocaleName('en'); // 'English'
```

## Примеры

### Переключатель языка

```javascript
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { i18n } from '@platform/services/i18n/i18n.service.js';

export class LangSwitcher extends PlatformElement {
    static properties = {
        currentLocale: { type: String }
    };

    constructor() {
        super();
        this.currentLocale = i18n.getCurrentLocale();
    }

    connectedCallback() {
        super.connectedCallback();
        this._unsubscribe = i18n.subscribe((locale) => {
            this.currentLocale = locale;
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._unsubscribe?.();
    }

    async _switchLanguage() {
        const newLocale = this.currentLocale === 'ru' ? 'en' : 'ru';
        await i18n.setLocale(newLocale);
    }

    render() {
        return html`
            <button @click=${this._switchLanguage}>
                ${i18n.getLocaleName(this.currentLocale)}
            </button>
        `;
    }
}

customElements.define('lang-switcher', LangSwitcher);
```

### Компонент с интерполяцией

```javascript
import { useI18n } from '@platform/services/i18n/i18n.service.js';

export class WelcomeMessage extends PlatformElement {
    static properties = {
        userName: { type: String }
    };

    constructor() {
        super();
        this.userName = 'User';
        this.i18n = useI18n(this);
    }

    render() {
        return html`
            <h1>${this.i18n.t('welcome.title', { name: this.userName })}</h1>
        `;
    }
}
```

## Структура файлов переводов

Переводы хранятся в `core/i18n/translations/{locale}/`:

```
translations/
├── ru/
│   ├── landing.json    # Переводы лендинга
│   ├── common.json     # Общие переводы
│   └── ...
└── en/
    ├── landing.json
    ├── common.json
    └── ...
```

### Пример `landing.json`:

```json
{
  "header": {
    "about": "О нас",
    "features": "Возможности",
    "login": "Войти"
  },
  "hero": {
    "title": "Humanitec — ваша команда AI-сотрудников",
    "subtitle": "Доверьте процессы AI-агентам"
  }
}
```

## Backend API

### `GET /api/i18n/{locale}`

Получение всех переводов для указанного языка.

**Request:**
```
GET /api/i18n/ru
```

**Response:**
```json
{
  "landing": {
    "header": {
      "about": "О нас",
      "features": "Возможности"
    }
  },
  "common": {
    "submit": "Отправить",
    "cancel": "Отмена"
  }
}
```

## Best Practices

1. **Используйте `useI18n` хук** - он автоматически обрабатывает подписки и отписки
2. **Группируйте переводы по namespace** - это упрощает поиск и поддержку
3. **Используйте говорящие ключи** - `header.login` лучше чем `h1`
4. **Избегайте хардкода текста** - весь UI текст должен быть переводимым
5. **Проверяйте fallback** - система автоматически вернет ключ, если перевод не найден

## Troubleshooting

### Переводы не загружаются

Проверьте что:
1. Backend сервис запущен
2. Endpoint `/api/i18n/{locale}` доступен
3. Файлы переводов существуют в `core/i18n/translations/`

### Компонент не обновляется при смене языка

Убедитесь что:
1. Используете `useI18n` хук или подписаны через `i18n.subscribe()`
2. Вызываете `this.requestUpdate()` в callback подписки

### Перевод показывает ключ вместо текста

Проверьте:
1. Ключ написан правильно (регистр имеет значение)
2. Перевод существует в файле для текущего языка
3. Namespace указан правильно (по умолчанию 'landing')

## Расширение

### Добавление нового языка

1. Создайте папку в `core/i18n/translations/{locale}/`
2. Добавьте JSON файлы с переводами
3. Добавьте locale в `getSupportedLocales()` и `getLocaleName()`
4. Перезапустите backend

### Добавление нового namespace

1. Создайте файл `{namespace}.json` в `core/i18n/translations/{locale}/`
2. Используйте через `t('key', {}, 'namespace')`


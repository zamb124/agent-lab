---
trigger: model_decision
description: "Core-компоненты типов данных: platform-field, типизированный ввод/отображение атрибутов"
globs:
---
# Data Type Components (`platform-field`)

## Назначение

`<platform-field>` — единственный допустимый способ ввода и отображения типизированных значений атрибутов в UI. Компонент-диспетчер делегирует рендеринг подкомпоненту на основании `type`.

## Расположение

Все файлы в `core/frontend/static/lib/components/fields/`:

| Файл | Описание |
|------|----------|
| `platform-field.js` | Диспетчер: принимает `type`, делегирует подкомпоненту |
| `platform-field-string.js` | Строка (`<input type="text">` / текст) |
| `platform-field-text.js` | Многострочный текст (`<textarea>` / `pre-wrap`) |
| `platform-field-number.js` | Число и целое число (`<input type="number">`) |
| `platform-field-boolean.js` | Булево (`<platform-switch>` / "Да"/"Нет") |
| `platform-field-date.js` | Дата и дата-время (`<platform-date-picker>`) |
| `platform-field-enum.js` | Перечисление (`<select>` / чип) |
| `platform-field-array.js` | Массив (`<tag-input>` / чипы) |
| `platform-field-object.js` | JSON-объект (textarea / pre) |

## API

```html
<platform-field
    .type=${'string'}
    .value=${someValue}
    .config=${{ values: ['a', 'b'] }}
    .label=${'Название поля'}
    .placeholder=${'Подсказка'}
    mode="edit"
    ?disabled=${false}
    @change=${(e) => handleChange(e.detail.value)}
></platform-field>
```

### Свойства

| Свойство | Тип | Описание |
|----------|-----|----------|
| `type` | `string` | Тип данных: `string`, `text`, `number`, `integer`, `boolean`, `date`, `datetime`, `enum`, `array`, `object` |
| `value` | `any` | Типизированное значение |
| `mode` | `string` | `view` (readonly) или `edit` (ввод) |
| `label` | `string` | Подпись поля (опционально) |
| `config` | `object` | Конфигурация по типу. Для `enum`: `{ values: [...] }` |
| `placeholder` | `string` | Placeholder для edit-режима |
| `disabled` | `boolean` | Заблокировано |

### Событие `change`

`detail.value` содержит типизированное значение: `number` для number/integer, `boolean` для boolean, `Array` для array и т.д.

## Импорт

```javascript
import '@platform/lib/components/fields/platform-field.js';
```

Side-effect import: диспетчер автоматически импортирует все подкомпоненты.

## i18n

Ключи в namespace `platform` (`core/i18n/translations/{locale}/platform.json`):

- `platform_field.empty_value` — "Не задано" / "Not set"
- `platform_field.boolean_true` — "Да" / "Yes"
- `platform_field.boolean_false` — "Нет" / "No"
- `platform_field.array_placeholder`
- `platform_field.object_placeholder`

## ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА

### 1. Для атрибутов с известным типом — ТОЛЬКО `platform-field`

Если тип поля известен из схемы (`required_fields` / `optional_fields` типа сущности) — использовать `<platform-field>` с соответствующим `type`. Голый `<input type="text">` для значений с известным типом **запрещён**.

### 2. Для отображения значений атрибутов — ТОЛЬКО `platform-field` в режиме `view`

Запрещено выводить значения атрибутов через `${value}` (строковую интерполяцию). Используй `<platform-field mode="view" .type=${...} .value=${...}>`.

### 3. Добавление нового типа данных

При появлении нового типа:
1. Создать `platform-field-{type}.js` в `core/frontend/static/lib/components/fields/`
2. Зарегистрировать в `FIELD_TYPE_MAP` и `switch` в `platform-field.js`
3. Добавить `type_id` в `SCHEMA_OPTIONS_RESPONSE` в `apps/crm/api/namespaces.py`
4. Добавить проверку в `_check_field_type` в `apps/crm/services/entity_service.py`

### 4. Наследование от `PlatformElement`

Все подкомпоненты наследуют `PlatformElement`, используют `PlatformElement.styles` и shared styles. Стили из `formStyles` — для инпутов, `buttonStyles` — по необходимости.

### 5. Запрещённые практики

- `<input type="text">` для boolean, number, date, enum полей
- `<input type="checkbox">` вместо `<platform-switch>` через `platform-field-boolean`
- Нативный `<input type="date">` / `<input type="datetime-local">` вместо `<platform-date-picker>` через `platform-field-date`
- Самодельные select/dropdown для enum вместо `platform-field-enum`
- Прямой `JSON.stringify(value)` в шаблоне вместо `<platform-field type="object" mode="view">`

## Связанные файлы

- `apps/crm/api/namespaces.py` — `SCHEMA_OPTIONS_RESPONSE` (канонический список типов)
- `apps/crm/services/entity_service.py` — `_check_field_type` (серверная валидация)
- `apps/crm/ui/modals/entity-modal.js` — ввод атрибутов (edit mode)
- `apps/crm/ui/components/entity-card.js` — отображение атрибутов (view mode)

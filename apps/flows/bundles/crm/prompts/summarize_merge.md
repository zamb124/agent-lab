# Daily Summary — слияние промежуточных сводок

Ты объединяешь **несколько** промежуточных сводок за один день в одну итоговую.

Ответ — **только** structured output по схеме API: поля `summary`, `entities`, `key_events`, `statistics`, `highlights`. Без markdown и без текста вне JSON.

## ВХОД

- Дата: {date}
- Namespace: {namespace}
- Промежуточные сводки (JSON массив объектов с полями как у выхода summarize, например summary, entities): {partials_json}

## ЗАДАЧА

Убери дубли, выдели главное за день. Поле `entities` — объединённый список уникальных имён, максимум 8.

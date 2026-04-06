# Daily Summary — чанк заметок

Ты сжимаешь **несколько** кратких карточек заметок за день (уже после AI-анализа) в одну промежуточную сводку.

## ЯЗЫК ОТВЕТА

Код языка интерфейса: `{interface_language_code}`. Все текстовые поля ответа (`summary`, `highlights`, строки в `key_events` и т.д.) — **исключительно на {interface_language_name} языке**. Не смешивай языки.

Ответ — **только** structured output по схеме API: поля `summary`, `entities`, `key_events`, `statistics`, `highlights`. Без markdown и без текста вне JSON.

## ВХОД

- Дата: {date}
- Namespace: {namespace}
- Карточки (JSON массив, поля entity_id, name, entity_subtype, snippet): {notes_json}

## ЗАДАЧА

Сведи только переданные карточки в одну связную сводку. Поле `summary` — **непустая** связная строка на языке интерфейса (несколько предложений). Поле `entities` — ключевые имена из карточек, максимум 8.

---
name: platform-cli
description: Цикл локального агента на CLI platform. Схема агента — bundle в git, платформа исполняет, CLI — единственный API.
---

# platform

Платформа — песочница. `platform` — её CLI, как docker для контейнера. Источник правды схемы — каталог bundle, не редактор.

Имена команд — через дефис: `eval-push`, `files-upload`, `docs-catalogs`, `sessions-inspect`. Пробел между словами argparse не принимает.

## Каталог

```
flow.yaml          # граф: flow_id, name, entry, nodes, edges, branches, variables, resources, triggers
prompts/<id>.md    # node.prompt: "prompts/<id>.md"
code/<id>.py       # node.code: "code/<id>.py" (js/ts/go/cs — по расширению)
schemas/<id>.output.json
evals/suite.yaml   # name, description, tags, rubrics
evals/cases.jsonl  # одна строка — один кейс; name или case_key — стабильный ключ
.platform/lock.json
.platform/schema/
```

`eval-push` читает только `evals/`. Каталог `evaluation/` и вложения рядом с кейсом CLI не видит.

Первая строка `flow.yaml`: `# yaml-language-server: $schema=.platform/schema/flow.schema.json`.
Секреты в bundle не писать. Ссылка — `@var:name`. Значение — `platform vars-set`.

## Как понимать схему

1. `platform schema pull` — JSON Schema с сервера, те же модели, что проверяет API. Без `.platform/schema/flow.schema.json` локальная проверка молчит, серверный `POST /flows/api/v1/flows/validate` всё равно идёт.
2. `platform explain node-types|node <type>|tools|tool <id>|models|resource-types|flow-ui|events` — справочники, прежде чем выдумывать поле.
3. Поле, которого нет в схеме, не добавлять.
4. `validate` красный только когда сервер вернул `valid: false` или локальная схема нашла ошибку. Записи `severity: info` в `errors` при `valid: true` прогон не останавливают.

## Цикл

1. `platform whoami`. Нет пользователя — сначала раздел «Вход».
2. Правишь файлы. Команды bundle принимают `--directory`; корень — каталог с `flow.yaml`.
3. `platform validate --directory <bundle>`.
4. `platform push --directory <bundle>`. Сервер сверяет `base_version` из `.platform/lock.json`. Файла нет — push падает с кодом 2 (`lock has no base_version`): `platform pull` в этот каталог или `push --force-base`. `--force-base` берёт версию, которую CLI только что прочитал, и перезаписывает её. `409 flow_version_conflict` — кто-то сохранил flow: `platform pull`, перенеси правку, push. Push пишет `.platform/lock.json` в `--directory`.
5. `platform run --flow <id> --input "..."`. Файл хода — повтор `--file <path>`: байты уходят `Part.raw`, канал кладёт `FileRef` в `state.files`. `mediaType` CLI берёт из `mimetypes`; неизвестное расширение становится `application/octet-stream`. События — NDJSON в stdout, последняя строка — `summary` (`task_id`, `context_id`, `session_id`, `task_state`, `response`).
6. Код выхода `9` — агент ждёт ввода. Продолжение: `platform run --flow <id> --context <context_id> --input "..."`.
7. `platform sessions-inspect <session_id>` — state, история, трейс. Логи Loki при 503 кладутся в `logs_status` и inspect не падает. `sessions-export` пишет `events.jsonl`, `state.json`, `trace.json`, `logs.jsonl`.
8. Evaluation — раздел ниже. `eval-push` flow не публикует: перед прогоном нужен свой `push`.

Каждый push — новая версия, если содержимое изменилось. Откат: `platform rollback <flow_id> <version>`.

Пустой `branches: {}` исполняется веткой `default`. У `eval-run` и фабрики flow это тот же граф, отдельной ветки в yaml нет.

## Evaluation

1. Кейс, которому нужны файлы, сам их не загружает. `eval-push` копирует JSONL как есть и выбрасывает поля `case_key` и `fixtures`. Текст описания «загрузите и вставьте FileRef» CLI не исполняет.
2. Загрузка: `docs-catalogs` (создание — `docs-catalogs --title <имя>`), затем `files-upload <path> --segment documents --catalog <catalog_id>`. Ответ — `FileRef`. Его объект целиком кладётся в `initial_state.files` в порядке чтения. Поля, которые принимает `ExecutionState.files`: `file_id` или `url`, `original_name`, `content_type`, `file_size`; лишнее поле строгая модель отвергает. `content_type` фильтрует код flow (`image/*`, `application/pdf`, CSV, Excel, Word). `application/octet-stream` эти фильтры не проходит.
3. `evals/suite.yaml` обязателен. Строка кейса несёт `name`, `branch_ids`, `turns` и, когда flow читает `state.files`, `initial_state`. Ход пишет `state.content`; файлы из `initial_state` остаются.
4. `platform eval-push --directory <bundle>`. Повтор с тем же `name` обновляет кейс. В ответе — `suite_id`.
5. `platform eval-run --suite-id <id> --branch default --wait`. CLI не передаёт `max_concurrency`: на сервере это 1, кейсы идут по одному. `--timeout` (общий флаг, по умолчанию 120) — и таймаут HTTP, и срок ожидания `--wait`. Ставь его больше суммы `timeout_seconds` кейсов. Истёкший срок печатает неготовый state и выходит с кодом 0. Продолжение — `eval-report <run_id>`, не второй `eval-run`: у нового прогона другой `idempotency_key`.
6. Прогресс — stderr, строка `eval <event_type> seq=N`, без текста ошибки. Итог `--wait` — JSON прогона. `state: error` — исключение в `case_runs[].error` (`error_case_runs`), checks не считались. `state: failed` — check не прошёл. Оба дают код 10. `canceled` — код 8.

Разбор `error`: `sessions-inspect` сессии кейса. Исключение ноды лежит в истории (`ActivityFailed` / `NodeFailed`). Обрыв `tools.read_file` с 500 — ошибка capability, не провал схемы ответа. Модель и текст провайдера — на span трейса: `platform.llm.provider`, `platform.llm.requested_model`, `platform.error.message`.

`platform logs <session_id>` запрашивает Loki за 7 суток и окно не задаёт. Отказ Loki по длине диапазона — код 7, это не пустая сессия. Тот же отказ inspect прячет в `logs_status`.

## Ошибки

Одна JSON-запись в stderr: `error_code`, `error_detail`, `error_params`, `request_id`, `trace_id`, `http_status`, `retryable`, `hint`. `--json` кладёт успешное тело в stdout одним объектом; прогресс остаётся в stderr. При коде 10 stderr несёт конверт, stdout — тело прогона.

| Код выхода | Смысл |
|---|---|
| 0 | успех, в том числе `--wait`, оборванный по `--timeout` на неготовом state |
| 2 | аргументы или bundle, в том числе нет `evals/suite.yaml` и нет `base_version` в lock |
| 3 | невалидный flow или payload |
| 4 | 401/403 |
| 5 | 404 |
| 6 | конфликт, в том числе base_version |
| 7 | сеть, 502/503/504, отказ Loki |
| 8 | прогон failed/canceled |
| 9 | агент ждёт ввода |
| 10 | evaluation `failed` или `error` |
| 1 | внутреннее |

GET и опросы повторяются. `push` не повторяется. `eval-run` несёт `idempotency_key`. Обрыв SSE не шлёт команду заново: продолжение — `platform wait --flow <id> <task_id>`.

## Данные

- `files-upload <path> --segment documents|rag` — `documents` требует `--catalog`, `rag` требует `--ns`
- `docs-catalogs`, `docs-catalogs --title <имя>`, `docs-add <path> --catalog <id>`, `docs-rag <catalog_id>`
- `rag-ns`, `rag-index <path> --ns <name> --wait`, `rag-search <query> --ns <name>`
- `search <query>`

Пространство Документов — `--namespace` (`X-Platform-Namespace`).

## Вход

`platform login --host <url> --api-key hum_...`

Ключ создаётся в консоли (`POST /frontend/api/api-keys`). `PLATFORM_HOST` и `PLATFORM_API_KEY` главнее файла `~/.config/platform/contexts.toml`. Нет файла и нет этих переменных — любая команда с сетью падает с кодом 2.

Локальный стек: `http://<company_subdomain>.localhost:8002`. Консоль на этом порту проксирует `/flows`, `/documents`, `/rag` и остальные префиксы сервисов. Запрос на порт одного сервиса чужой префикс не обслуживает. Компания ключа и поддомен Host — одна компания. Проверка — `platform whoami`: в теле есть `user` и `company_id`.

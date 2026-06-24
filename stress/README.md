# Stress

Нагрузочный контур проекта. Инструмент: Grafana k6, сценарии лежат по сервисам в
`stress/services`.

## Быстрый запуск

```bash
make stress
```

Если `URL` и `TOKEN` не переданы, runner спросит интерактивно:

```text
Stress URL [http://localhost:8001]:
API token (Enter for no token):
```

Enter на URL означает локальный `http://localhost:8001`.

Локальный smoke:

```bash
make stress PROFILE=smoke URL=http://localhost:8001
```

Production с токеном:

```bash
make stress PROFILE=prod URL=https://humanitec.ru TOKEN=<jwt-or-api-token>
```

Или интерактивно:

```bash
make stress PROFILE=prod RPS=20
```

Результаты пишутся в `stress/results`:

- `report.md` - короткий человекочитаемый отчет;
- `report.html` - HTML версия;
- `summary.json` - полный k6 summary для машинного анализа.

## Профили

- `smoke` - короткая проверка wiring перед реальной нагрузкой.
- `local` - дефолт для локального поиска слабых мест.
- `hard` - агрессивный локальный профиль.
- `prod` - осторожный production-профиль, токен передается через `TOKEN`.

Любой профиль можно переопределить:

```bash
make stress RATE=20 DURATION=3m PRE_ALLOCATED_VUS=80 MAX_VUS=300
```

Удобная форма для RPS:

```bash
make stress RPS=50
make stress 50
make stress-50
make stress-100 DURATION=3m
```

При `RPS=N` runner автоматически поднимает дефолтные VU лимиты до
`PRE_ALLOCATED_VUS=N*2` и `MAX_VUS=N*5`, если они не заданы явно.

Проверить расчёт без запуска:

```bash
make stress 100 DRY_RUN=1
```

## Flows

`stress/services/flows.js` тестирует A2A `message/send` в async-режиме:

1. `message/send` с `metadata.execution_mode=async`.
2. Получение `taskId` без ожидания выполнения flow.
3. Polling результата через A2A `tasks/get`.

Покрыты `example_graph` и `example_react`, разные branches и разные входные данные.
По умолчанию включён `metadata.__mock__` (Mock Control System): каждая llm-нода
получает свою очередь ответов (`nodes.<node_id>`), поэтому runtime стрессуется без
стоимости и нестабильности внешних LLM. Значение mock для любой сущности (tool, node,
flow, llm) — список ответов (FIFO). Для реального LLM профиля:

```bash
make stress STRESS_USE_MOCK=false
```

## Auth локально

Для локальной разработки можно отключить обязательную авторизацию в `conf.local.json`:

```json
"auth": {
  "enabled": false,
  "dev_auto_user_id": "dev-auto-user",
  "dev_auto_company_id": "system",
  "dev_auto_company_name": "System",
  "dev_auto_groups": ["admin", "developers"]
}
```

В `production` этот bypass игнорируется middleware, даже если случайно выставить
`auth.enabled=false`.

## Расширение

Новый сервис добавляется отдельным файлом:

```text
stress/services/<service>.js
```

После этого запуск:

```bash
make stress SERVICE=<service>
```

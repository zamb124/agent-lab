---
title: "Быстрый старт"
description: "Первый запрос к агенту Humanitec через A2A JSON-RPC."
---

<p class="docs-page-kicker">Quickstart</p>
<p class="docs-lead">За несколько минут проверьте Agent Card, отправьте сообщение агенту и перейдите к полной API-документации.</p>

<div class="docs-api-strip">
  <div><span>Base URL</span><code>https://humanitec.ru/flows/a2a/{flow_id}</code></div>
  <div><span>Auth</span><code>Authorization: Bearer {token}</code></div>
  <div><span>Protocol</span><code>JSON-RPC 2.0</code></div>
</div>

## 1. Подготовьте параметры

Для примеров ниже нужны идентификатор flow и токен доступа.

```bash
export HUMANITEC_TOKEN="your_token"
export HUMANITEC_FLOW_ID="my-agent"
export HUMANITEC_BASE_URL="https://humanitec.ru/flows/a2a/${HUMANITEC_FLOW_ID}"
```

!!! tip

    Для серверных интеграций используйте bearer token или API key. Для встроенных виджетов доступен embed session token.

## 2. Получите Agent Card

Agent Card описывает агента, поддерживаемые capabilities и доступные skills.

=== "curl"

    ```bash
    curl -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
      "${HUMANITEC_BASE_URL}"
    ```

=== "HTTP"

    ```http
    GET /flows/a2a/{flow_id} HTTP/1.1
    Host: humanitec.ru
    Authorization: Bearer {token}
    ```

## 3. Отправьте первое сообщение

Все интерактивные вызовы идут через `POST` на URL агента с JSON-RPC телом.

=== "curl"

    ```bash
    curl -X POST "${HUMANITEC_BASE_URL}" \
      -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
      -H "Content-Type: application/json" \
      -d '{
        "jsonrpc": "2.0",
        "id": "1",
        "method": "message/send",
        "params": {
          "message": {
            "role": "user",
            "content": {
              "parts": [
                {"text": "Помоги подготовить краткий статус по проекту"}
              ]
            }
          }
        }
      }'
    ```

=== "JSON-RPC"

    ```json
    {
      "jsonrpc": "2.0",
      "id": "1",
      "method": "message/send",
      "params": {
        "message": {
          "role": "user",
          "content": {
            "parts": [
              { "text": "Помоги подготовить краткий статус по проекту" }
            ]
          }
        }
      }
    }
    ```

## 4. Включите streaming

Для потоковых ответов замените метод на `message/stream`. Ответ приходит через Server-Sent Events.

```bash
curl -N -X POST "${HUMANITEC_BASE_URL}" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "stream-1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "content": {
          "parts": [
            {"text": "Расскажи, какие следующие шаги нужны для запуска агента"}
          ]
        }
      }
    }
  }'
```

## Дальше

<div class="docs-card-grid docs-card-grid-compact">
  <a class="docs-card" href="../api/flows/">
    <span class="docs-card-kicker">API</span>
    <h2>Flows Public API</h2>
    <p>Полная страница A2A методов, skills и задач.</p>
  </a>
  <a class="docs-card" href="../scenarios/">
    <span class="docs-card-kicker">UI</span>
    <h2>Сценарии интерфейса</h2>
    <p>Проверьте, как ключевые пользовательские пути выглядят в продукте.</p>
  </a>
</div>

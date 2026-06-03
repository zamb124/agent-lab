A2A API для Flows - это внешний HTTP-интерфейс, через который ваш backend может запускать опубликованные flows, получать ответы, продолжать диалоги, передавать файлы, подставлять переменные и управлять branches.

Эта страница написана как практическая инструкция для разработчика интеграции. Представьте flow как умного исполнителя: вы отправляете ему сообщение, он создает задачу, выполняет граф и возвращает результат. Если задача долгая, вы можете смотреть ее прогресс потоком или спрашивать статус позже.

## Коротко: что нужно сделать

1. Создайте API token в консоли платформы.
2. Сохраните token на своем backend в secret manager или переменной окружения.
3. Узнайте `flow_id` нужного flow.
4. Получите Agent Card, чтобы увидеть branches, публичные variables и возможности flow.
5. Отправьте JSON-RPC запрос `message/send` или `message/stream` на `/flows/api/v1/{flow_id}`.
6. Для долгих запусков используйте `metadata.execution_mode: "async"` и потом `tasks/get`.

Главный публичный URL:

```text
https://humanitec.ru/flows/api/v1/{flow_id}
```

Локально в dev-окружении обычно используется:

```text
http://lvh.me:8001/flows/api/v1/{flow_id}
```

Для текущего A2A API путь всегда должен начинаться с `/flows/api/v1/`.

## Термины простыми словами

`Flow` - опубликованный сценарий в платформе. Это граф шагов: LLM-ноды, code-ноды, вызовы других flows, обращения к ресурсам и переходы между шагами.

`flow_id` - технический ID flow. Он стоит в URL. Например: `support_agent`.

`Branch` - вариант поведения flow. Например, один flow может иметь branch `default`, branch `sales` и branch `support`. Branch выбирается в запросе через `metadata.branch`.

`branch_id` - технический ID branch. Если вы ничего не передаете, используется `default`.

`Agent Card` - карточка flow. Это JSON с названием, описанием, URL, branches, capabilities и публичными variables. Ее удобно получать перед интеграцией.

`JSON-RPC` - формат запроса, где вы всегда отправляете `method` и `params`. Это похоже на вызов функции по HTTP: "вызови метод `message/send` с такими параметрами".

`Message` - сообщение пользователя для flow. В нем есть `role`, `parts`, `messageId`, а также опциональные `taskId` и `contextId`.

`Task` - один запуск flow. У Task есть `id`, `contextId`, `status`, иногда `artifacts` и `history`.

`taskId` - ID конкретного запуска. Это как номер одной посылки.

`contextId` - ID диалога или цепочки сообщений. Это как номер чата. Если отправлять новые сообщения с тем же `contextId`, flow продолжит тот же диалог.

`Part` - кусок сообщения. Part может быть текстом, файлом или JSON-данными.

## Создание API token в консоли платформы

API token нужен для server-to-server интеграции. Его нельзя класть в браузер, мобильное приложение, публичный репозиторий, HTML-страницу или frontend bundle. Пользователь не должен его видеть.

### 1. Откройте раздел API Keys

Зайдите в консоль платформы под пользователем с ролью owner или admin в компании. В локальном окружении откройте:

```text
http://demo.lvh.me:8002/api-keys
```

В production используйте консоль вашей компании и раздел `API keys`.

![Раздел API Keys в консоли платформы](../../assets/images/a2a-api-token-console.png)

На странице видно список уже созданных ключей. В таблице показывается только prefix ключа, например `hum_abc123...`. Полный secret после создания повторно не показывается.

### 2. Нажмите "Создать ключ"

Нажмите кнопку `+ Создать ключ`. В модальном окне укажите понятное имя. Хорошие имена помогают потом понять, где используется ключ:

- `Production backend - Flows A2A`
- `CRM integration - support_agent`
- `Staging - flow tests`

Выберите scopes:

- `agents:read` - достаточно для чтения Agent Card, запуска flow и получения статуса задач.
- `agents:write` - добавляйте только если вашему backend нужно создавать, обновлять или удалять branches через API.

Не выбирайте лишние scopes "на всякий случай". Если ключ утечет, лишние scopes увеличат ущерб.

![Создание API key для A2A интеграции](../../assets/images/a2a-api-token-create-modal.png)

### 3. Скопируйте secret сразу после создания

После нажатия `Создать` платформа один раз покажет secret вида:

```text
hum_••••••••••••••••••••••••••••••••
```

Скопируйте его сразу и сохраните в надежном месте: secret manager, vault, переменные окружения backend-сервиса или защищенные настройки CI/CD.

![Одноразовый secret API key после создания](../../assets/images/a2a-api-token-created.png)

Важно:

- Secret показывается только один раз.
- Если вы закрыли страницу и не сохранили secret, посмотреть его снова нельзя.
- В такой ситуации отзовите старый ключ и создайте новый.
- Если ключ мог попасть в логи, чат, issue tracker или git, отзовите его и создайте новый.

## Авторизация A2A запросов

Для server-to-server интеграций используйте Bearer token:

```http
Authorization: Bearer hum_your_api_key
Content-Type: application/json
Accept: application/json
```

Пример с переменной окружения:

```bash
export HUMANITEC_TOKEN="hum_your_api_key"
export FLOW_ID="support_agent"
export A2A_URL="https://humanitec.ru/flows/api/v1/${FLOW_ID}"

curl -sS "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Accept: application/json"
```

Не используйте browser cookies (`auth_token`, `session_id`) для backend-интеграций. Cookies нужны для пользователя в консоли, а API token нужен для вашего сервера.

### Где хранить token

Хорошо:

- secret manager облака;
- Kubernetes Secret;
- GitHub Actions / GitLab CI secret variables;
- `.env` только на локальной машине разработчика, если файл не попадает в git.

Плохо:

- прямо в JavaScript frontend;
- в мобильном приложении;
- в публичном репозитории;
- в логах;
- в примерах, которые отправляются клиентам;
- в screenshots без маски.

## Базовые URL и версии

### Agent Card

```http
GET /flows/api/v1/{flow_id}
GET /flows/api/v1/{flow_id}/.well-known/agent-card.json
```

Оба URL возвращают карточку flow. Well-known URL нужен A2A-клиентам, которые автоматически ищут agent card.

### JSON-RPC

```http
POST /flows/api/v1/{flow_id}
```

На этот URL отправляются методы:

- `message/send`
- `message/stream`
- `tasks/get`
- `tasks/cancel`
- `tasks/resubscribe`
- `tasks/pushNotificationConfig/get`
- `tasks/pushNotificationConfig/set`
- `tasks/pushNotificationConfig/delete`
- `tasks/pushNotificationConfig/list`
- `agent/getAuthenticatedExtendedCard`

### REST endpoints для branches

```http
GET    /flows/api/v1/{flow_id}/branches
GET    /flows/api/v1/{flow_id}/branches/{branch_id}
GET    /flows/api/v1/{flow_id}/branches/{branch_id}/tools
GET    /flows/api/v1/{flow_id}/schema
POST   /flows/api/v1/{flow_id}/branches
PUT    /flows/api/v1/{flow_id}/branches/{branch_id}
DELETE /flows/api/v1/{flow_id}/branches/{branch_id}
```

### Версия flow

Если вам нужна конкретная версия flow, передайте `v`:

```http
GET  /flows/api/v1/{flow_id}?v=20260603123000000000
POST /flows/api/v1/{flow_id}?v=20260603123000000000
```

Для JSON-RPC можно также передать версию в `params.metadata.version`:

```json
{
  "jsonrpc": "2.0",
  "id": "run-1",
  "method": "message/send",
  "params": {
    "message": {
      "messageId": "msg-1",
      "role": "user",
      "parts": [{ "kind": "text", "text": "Привет" }]
    },
    "metadata": {
      "version": "20260603123000000000"
    }
  }
}
```

Если версия указана и в query `?v=...`, и в `metadata.version`, приоритет у query.

## JSON-RPC envelope

Каждый JSON-RPC запрос выглядит так:

```json
{
  "jsonrpc": "2.0",
  "id": "request-1",
  "method": "message/send",
  "params": {}
}
```

Поля:

- `jsonrpc` - всегда строка `"2.0"`.
- `id` - строка или число. Сервер вернет это же значение в ответе. Так удобно сопоставлять запрос и ответ.
- `method` - имя метода.
- `params` - объект с параметрами метода. Если параметров нет, передавайте `{}`.

`id` не должен быть `null`, `true`, `false`, массивом или объектом. Используйте строку:

```json
{ "id": "run-2026-06-03-001" }
```

или число:

```json
{ "id": 1 }
```

Успешный ответ:

```json
{
  "jsonrpc": "2.0",
  "id": "request-1",
  "result": {
    "id": "task-123",
    "contextId": "ctx-123",
    "status": { "state": "completed" }
  }
}
```

Ответ с ошибкой:

```json
{
  "jsonrpc": "2.0",
  "id": "request-1",
  "error": {
    "code": -32602,
    "message": "Invalid params: expected object"
  }
}
```

## Message: как правильно отправлять сообщение

Минимальное сообщение:

```json
{
  "messageId": "msg-001",
  "role": "user",
  "parts": [
    {
      "kind": "text",
      "text": "Привет! Помоги оформить заявку."
    }
  ]
}
```

Поля `message`:

- `messageId` - уникальный ID сообщения. Генерируйте новый ID на каждое пользовательское сообщение.
- `role` - обычно `"user"`. Ответы flow приходят с ролью `"agent"`.
- `parts` - массив частей сообщения. Минимум одна часть.
- `contextId` - опционально. Нужен, если вы хотите продолжать тот же диалог.
- `taskId` - опционально. Обычно можно не передавать: сервер сам создаст task id и вернет его.
- `metadata` - техническое поле сообщения A2A. Для настроек запуска в Humanitec используйте `params.metadata`, а не `message.metadata`.

Правильное место для настроек запуска:

```json
{
  "params": {
    "message": {
      "messageId": "msg-001",
      "role": "user",
      "parts": [{ "kind": "text", "text": "Привет" }]
    },
    "metadata": {
      "branch": "default",
      "variables": {
        "customer_id": "cust-123"
      }
    }
  }
}
```

`branch` здесь не является variable. Это отдельная настройка запуска в `params.metadata`.
Runtime variables лежат только внутри `params.metadata.variables`.

Для выбора branch используйте только `params.metadata.branch`.
Для передачи данных в flow используйте только `params.metadata.variables`.
Эти поля не заменяют друг друга.

### taskId и contextId на примере

Представьте, что `contextId` - это тетрадь, а `taskId` - одна задача в этой тетради.

Первое сообщение:

```json
{
  "messageId": "msg-1",
  "role": "user",
  "contextId": "chat-ivan-001",
  "parts": [{ "kind": "text", "text": "Меня зовут Иван" }]
}
```

Второе сообщение в том же диалоге:

```json
{
  "messageId": "msg-2",
  "role": "user",
  "contextId": "chat-ivan-001",
  "parts": [{ "kind": "text", "text": "Как меня зовут?" }]
}
```

Так flow понимает, что это продолжение одного разговора.

Если вы не передадите `contextId`, сервер создаст новый context. Это нормально для одноразовых запросов, но плохо для чата: каждое сообщение будет как новый разговор.

## Первый рабочий запрос

```bash
export HUMANITEC_TOKEN="hum_your_api_key"
export FLOW_ID="support_agent"
export A2A_URL="https://humanitec.ru/flows/api/v1/${FLOW_ID}"

curl -sS -X POST "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "first-run",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "msg-first-run",
        "role": "user",
        "parts": [
          {
            "kind": "text",
            "text": "Привет! Кратко объясни, что умеет этот flow."
          }
        ]
      },
      "metadata": {
        "branch": "default"
      }
    }
  }'
```

Ожидаемый тип ответа:

```json
{
  "jsonrpc": "2.0",
  "id": "first-run",
  "result": {
    "id": "generated-task-id",
    "contextId": "generated-context-id",
    "status": {
      "state": "completed",
      "message": {
        "role": "agent",
        "parts": [
          {
            "kind": "text",
            "text": "..."
          }
        ]
      }
    }
  }
}
```

## Agent Card

Agent Card помогает понять, что опубликовано наружу.

```bash
curl -sS "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Accept: application/json"
```

Пример ответа:

```json
{
  "name": "Support Agent",
  "description": "Помогает клиентам с вопросами поддержки",
  "version": "1.0.0",
  "url": "https://humanitec.ru/flows/api/v1/support_agent",
  "capabilities": {
    "streaming": true,
    "pushNotifications": false,
    "stateTransitionHistory": true
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "branches": [
    {
      "id": "default",
      "name": "Default",
      "description": "Основной сценарий",
      "tags": [],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain"]
    }
  ],
  "variables": {
    "company_name": {
      "title": "Company name",
      "description": "Название компании для ответов",
      "value": "Humanitec"
    }
  }
}
```

Поля:

- `name` и `description` - человекочитаемое название и описание flow.
- `url` - URL для JSON-RPC вызовов.
- `capabilities.streaming` - можно ли использовать `message/stream`.
- `capabilities.pushNotifications` - включены ли push notifications в карточке.
- `capabilities.stateTransitionHistory` - можно ли получать историю переходов статусов.
- `branches` - доступные branches. Их `id` передается в `metadata.branch`.
- `variables` - публичные variables, которые владелец flow разрешил показывать внешнему клиенту.

Agent Card не должна раскрывать secrets. Если переменная не публичная, ее не будет в `variables`.

## Метод message/send

`message/send` отправляет сообщение и возвращает Task.

Есть два режима:

- синхронный режим по умолчанию: сервер ждет завершения flow и возвращает финальный Task;
- async/background режим: сервер быстро возвращает Task со статусом `submitted`, а результат вы забираете через `tasks/get`.

### Синхронный message/send

Используйте для коротких flows, которые обычно отвечают быстро.

```bash
curl -sS -X POST "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "sync-1",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "msg-sync-1",
        "role": "user",
        "contextId": "chat-100",
        "parts": [
          {
            "kind": "text",
            "text": "Составь короткий ответ клиенту о статусе заказа."
          }
        ]
      },
      "metadata": {
        "branch": "default",
        "variables": {
          "order_id": "ORD-100500",
          "tone": "friendly"
        }
      }
    }
  }'
```

Что важно:

- `contextId` можно передавать, если это часть чата.
- `metadata.branch` выбирает branch.
- `metadata.variables` передает значения только для этого запуска или диалога.
- Если flow долгий, синхронный запрос может ждать долго. Для долгих задач лучше async или streaming.

### Async/background message/send

Используйте для долгих flows, где клиенту не нужно держать HTTP-соединение открытым.

```bash
curl -sS -X POST "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "async-1",
    "method": "message/send",
    "params": {
      "message": {
        "messageId": "msg-async-1",
        "role": "user",
        "contextId": "report-chat-77",
        "parts": [
          {
            "kind": "text",
            "text": "Проанализируй приложенный отчет и подготовь выводы."
          }
        ]
      },
      "metadata": {
        "branch": "default",
        "execution_mode": "async"
      }
    }
  }'
```

Ответ будет примерно таким:

```json
{
  "jsonrpc": "2.0",
  "id": "async-1",
  "result": {
    "id": "task-abc",
    "contextId": "report-chat-77",
    "status": {
      "state": "submitted",
      "message": {
        "role": "agent",
        "parts": [{ "kind": "text", "text": "Task submitted" }]
      }
    }
  }
}
```

Дальше опрашивайте `tasks/get` по `id`:

```json
{
  "jsonrpc": "2.0",
  "id": "get-async-1",
  "method": "tasks/get",
  "params": {
    "id": "task-abc",
    "historyLength": 20
  }
}
```

Для `execution_mode` также принимается `"background"`.

### Статусы Task

В `result.status.state` вы можете увидеть:

- `submitted` - задача принята, но еще не начала отдавать результат.
- `working` - задача выполняется.
- `completed` - задача успешно завершилась.
- `input-required` - flow ждет дополнительный ввод пользователя или оператора.
- `failed` - задача завершилась ошибкой.
- `canceled` - задача отменена.
- `rejected` - задача отклонена до выполнения.

Если статус `input-required`, смотрите `status.message`: там обычно есть вопрос или инструкция, что нужно прислать следующим сообщением. Чтобы продолжить тот же диалог, отправьте новое `message/send` или `message/stream` с тем же `contextId`.

## Метод message/stream

`message/stream` запускает flow и возвращает Server-Sent Events (SSE). Это удобно для интерфейса чата, где нужно показывать ответ по мере генерации.

Запрос:

```bash
curl -N -sS -X POST "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "stream-1",
    "method": "message/stream",
    "params": {
      "message": {
        "messageId": "msg-stream-1",
        "role": "user",
        "contextId": "chat-stream-1",
        "parts": [
          {
            "kind": "text",
            "text": "Объясни по шагам, как работает доставка."
          }
        ]
      },
      "metadata": {
        "branch": "default"
      }
    }
  }'
```

Фреймы SSE выглядят так:

```text
data: {"jsonrpc":"2.0","id":"stream-1","result":{"kind":"status-update","status":{"state":"working"}}}

data: {"jsonrpc":"2.0","id":"stream-1","result":{"kind":"artifact-update","artifact":{"parts":[{"kind":"text","text":"Шаг 1..."}]}}}

data: {"jsonrpc":"2.0","id":"stream-1","result":{"kind":"status-update","status":{"state":"completed"},"final":true}}
```

В каждом событии:

- `jsonrpc` и `id` помогают связать событие с вашим запросом.
- `result.kind` показывает тип события.
- `artifact-update` обычно несет кусок результата.
- `status-update` сообщает состояние задачи.
- `message` может нести отдельное сообщение агента.
- `final: true` означает, что поток завершен.

Если в streaming произошла ошибка, она тоже придет как SSE frame:

```text
data: {"jsonrpc":"2.0","id":"stream-1","error":{"code":-32000,"message":"Task failed"}}
```

Минимальный пример чтения SSE в Node.js:

```js
const response = await fetch(process.env.A2A_URL, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${process.env.HUMANITEC_TOKEN}`,
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  },
  body: JSON.stringify({
    jsonrpc: '2.0',
    id: 'stream-node-1',
    method: 'message/stream',
    params: {
      message: {
        messageId: crypto.randomUUID(),
        role: 'user',
        contextId: 'chat-node-1',
        parts: [{ kind: 'text', text: 'Привет!' }],
      },
      metadata: { branch: 'default' },
    },
  }),
});

if (!response.ok) {
  throw new Error(`A2A HTTP error ${response.status}`);
}

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  buffer += decoder.decode(value, { stream: true });
  const frames = buffer.split('\n\n');
  buffer = frames.pop() ?? '';

  for (const frame of frames) {
    const line = frame.split('\n').find((x) => x.startsWith('data: '));
    if (!line) continue;
    const payload = JSON.parse(line.slice(6));
    if (payload.error) throw new Error(payload.error.message);
    console.log(payload.result);
  }
}
```

## Метод tasks/get

`tasks/get` возвращает текущее состояние Task.

Параметры:

- `id` - `taskId` или `contextId`.
- `historyLength` - опционально, сколько последних сообщений истории вернуть.

Пример:

```bash
curl -sS -X POST "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "get-1",
    "method": "tasks/get",
    "params": {
      "id": "task-abc",
      "historyLength": 20
    }
  }'
```

Возможный ответ:

```json
{
  "jsonrpc": "2.0",
  "id": "get-1",
  "result": {
    "id": "task-abc",
    "contextId": "report-chat-77",
    "status": {
      "state": "working",
      "message": {
        "role": "agent",
        "parts": [{ "kind": "text", "text": "" }]
      }
    },
    "history": []
  }
}
```

Если задача не найдена, `result` будет `null`:

```json
{
  "jsonrpc": "2.0",
  "id": "get-1",
  "result": null
}
```

Типичная схема polling:

1. Запустите `message/send` с `metadata.execution_mode: "async"`.
2. Возьмите `result.id`.
3. Раз в 1-3 секунды вызывайте `tasks/get`.
4. Остановите polling, когда `status.state` стал `completed`, `failed`, `canceled`, `rejected` или `input-required`.

Не дергайте `tasks/get` десятки раз в секунду. Это не ускорит flow, но создаст лишнюю нагрузку.

## Метод tasks/cancel

`tasks/cancel` просит отменить выполняющуюся задачу.

Параметры:

- `id` - `taskId` или `contextId`.

Пример:

```bash
curl -sS -X POST "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "cancel-1",
    "method": "tasks/cancel",
    "params": {
      "id": "task-abc"
    }
  }'
```

Успешный ответ:

```json
{
  "jsonrpc": "2.0",
  "id": "cancel-1",
  "result": {
    "id": "task-abc",
    "contextId": "report-chat-77",
    "status": {
      "state": "canceled",
      "message": {
        "role": "agent",
        "parts": [{ "kind": "text", "text": "Task cancelled" }]
      }
    }
  }
}
```

Если задача не найдена:

```json
{
  "jsonrpc": "2.0",
  "id": "cancel-1",
  "error": {
    "code": -32000,
    "message": "Task not found"
  }
}
```

Отмена - не машина времени. Если flow уже успел завершиться, клиент может увидеть финальный статус вместо отмены.

## Метод tasks/resubscribe

`tasks/resubscribe` нужен, если streaming-соединение оборвалось и клиент хочет снова получить состояние задачи.

Параметры:

- `id` - `taskId` или `contextId`.

Пример:

```bash
curl -N -sS -X POST "$A2A_URL" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "resubscribe-1",
    "method": "tasks/resubscribe",
    "params": {
      "id": "task-abc"
    }
  }'
```

Ответ идет как SSE. Если задача найдена, вы получите текущее представление Task в `result`.

## Push notification methods

Push notification methods управляют webhook-конфигурациями для Task:

- `tasks/pushNotificationConfig/set`
- `tasks/pushNotificationConfig/get`
- `tasks/pushNotificationConfig/list`
- `tasks/pushNotificationConfig/delete`

Используйте их только если push notifications включены и согласованы для вашего окружения. Для большинства интеграций проще и надежнее начать с `message/stream` или `tasks/get`.

### tasks/pushNotificationConfig/set

Создает или обновляет webhook config для Task.

```json
{
  "jsonrpc": "2.0",
  "id": "push-set-1",
  "method": "tasks/pushNotificationConfig/set",
  "params": {
    "taskId": "task-abc",
    "pushNotificationConfig": {
      "id": "main-webhook",
      "url": "https://example.com/humanitec/a2a/task-events",
      "token": "optional-shared-secret",
      "authentication": {
        "schemes": ["bearer"],
        "credentials": "optional-credentials"
      }
    }
  }
}
```

Поля:

- `taskId` - ID задачи.
- `pushNotificationConfig.url` - HTTPS endpoint вашего backend.
- `pushNotificationConfig.id` - опциональный ID config. Если у задачи несколько webhooks, задавайте разные ID.
- `pushNotificationConfig.token` - опциональный secret, который ваш backend может использовать для проверки вызова.
- `authentication.schemes` - список схем авторизации, например `["bearer"]`.
- `authentication.credentials` - опциональные credentials для выбранной схемы.

Минимальный вариант:

```json
{
  "taskId": "task-abc",
  "pushNotificationConfig": {
    "id": "main",
    "url": "https://example.com/a2a/task-events"
  }
}
```

### tasks/pushNotificationConfig/get

Возвращает один config.

```json
{
  "jsonrpc": "2.0",
  "id": "push-get-1",
  "method": "tasks/pushNotificationConfig/get",
  "params": {
    "id": "task-abc",
    "pushNotificationConfigId": "main-webhook"
  }
}
```

Если `pushNotificationConfigId` не передать, сервер может вернуть config по умолчанию для задачи.

### tasks/pushNotificationConfig/list

Возвращает все configs задачи.

```json
{
  "jsonrpc": "2.0",
  "id": "push-list-1",
  "method": "tasks/pushNotificationConfig/list",
  "params": {
    "id": "task-abc"
  }
}
```

Ответ:

```json
{
  "jsonrpc": "2.0",
  "id": "push-list-1",
  "result": [
    {
      "taskId": "task-abc",
      "pushNotificationConfig": {
        "id": "main-webhook",
        "url": "https://example.com/humanitec/a2a/task-events"
      }
    }
  ]
}
```

### tasks/pushNotificationConfig/delete

Удаляет config.

```json
{
  "jsonrpc": "2.0",
  "id": "push-delete-1",
  "method": "tasks/pushNotificationConfig/delete",
  "params": {
    "id": "task-abc",
    "pushNotificationConfigId": "main-webhook"
  }
}
```

Успешный ответ:

```json
{
  "jsonrpc": "2.0",
  "id": "push-delete-1",
  "result": null
}
```

## Метод agent/getAuthenticatedExtendedCard

Метод возвращает расширенную Agent Card для аутентифицированного клиента, если такая карточка включена для flow. Если отдельная расширенная карточка не настроена, возвращается обычная Agent Card.

Пример:

```json
{
  "jsonrpc": "2.0",
  "id": "card-extended-1",
  "method": "agent/getAuthenticatedExtendedCard",
  "params": {}
}
```

Используйте этот метод, когда A2A-клиент сначала получил публичную карточку, увидел, что есть authenticated mode, и затем хочет получить данные, доступные только после авторизации.

## Branches

Branch - это вариант flow. Например:

- `default` - основной сценарий;
- `sales` - сценарий для продаж;
- `support` - сценарий поддержки;
- `vip` - сценарий для VIP-клиентов.

Выбор branch при запуске делается через `metadata.branch`:

```json
{
  "metadata": {
    "branch": "support"
  }
}
```

Если `metadata.branch` не передан, используется `default`.

`metadata.branch` применяется при старте нового `contextId`. Если вы продолжаете уже существующий диалог с тем же `contextId`, branch берется из сохраненного состояния этого диалога и не переключается посреди разговора.

### GET /flows/api/v1/{flow_id}/branches

Возвращает список branches.

```bash
curl -sS "$A2A_URL/branches" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Accept: application/json"
```

Ответ:

```json
[
  {
    "id": "default",
    "name": "Default",
    "description": "Основной сценарий",
    "tags": []
  },
  {
    "id": "support",
    "name": "Support",
    "description": "Сценарий поддержки",
    "tags": ["support"]
  }
]
```

### GET /flows/api/v1/{flow_id}/branches/{branch_id}

Возвращает подробное описание branch.

```bash
curl -sS "$A2A_URL/branches/support" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Accept: application/json"
```

Основные поля ответа:

- `id` - branch id.
- `name` - название.
- `description` - описание.
- `tags` - теги.
- `permission` - группы пользователей, которым доступен branch. Пустой список означает доступ для всех пользователей компании, у которых есть доступ к flow.
- `entry` - стартовая нода branch.
- `nodes` - ноды branch.
- `nodes_mode` - как применять `nodes`: `replace` или `merge`.
- `edges` - связи между нодами.
- `edges_mode` - как применять `edges`: `replace` или `merge`.
- `variables` - variables branch.
- `variables_mode` - как применять `variables`: `replace` или `merge`.
- `resources` - ресурсы branch.
- `resources_mode` - как применять `resources`: `replace` или `merge`.
- `speech` - настройки speech-профиля branch, если branch работает с голосом.

Пример фрагмента:

```json
{
  "id": "support",
  "name": "Support",
  "description": "Сценарий поддержки",
  "tags": ["support"],
  "permission": [],
  "entry": "classify",
  "nodes_mode": "replace",
  "edges_mode": "replace",
  "variables_mode": "merge",
  "resources_mode": "merge"
}
```

### GET /flows/api/v1/{flow_id}/branches/{branch_id}/tools

Возвращает инструменты, ноды и переходы, доступные в branch.

```bash
curl -sS "$A2A_URL/branches/support/tools" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Accept: application/json"
```

Ответ может содержать элементы разных типов:

```json
[
  {
    "name": "lookup_order",
    "type": "function",
    "attributes": {
      "description": "Ищет заказ по номеру",
      "source": "reference",
      "parameters_schema": {
        "type": "object",
        "properties": {
          "order_id": { "type": "string" }
        },
        "required": ["order_id"]
      }
    }
  },
  {
    "name": "classify",
    "type": "node",
    "attributes": {
      "description": "ReAct агент",
      "node_type": "llm_node",
      "node_name": "classify"
    }
  },
  {
    "name": "classify -> answer",
    "type": "edge",
    "attributes": {
      "description": "Переход от 'classify' к 'answer'",
      "from_node": "classify",
      "to_node": "answer",
      "condition": null
    }
  }
]
```

Зачем это нужно:

- показать внешнему разработчику, какие function tools может вызвать flow;
- понять структуру branch без открытия редактора;
- проверить, что branch содержит ожидаемые ноды и переходы.

### GET /flows/api/v1/{flow_id}/schema

Возвращает JSON Schema для создания branch.

```bash
curl -sS "$A2A_URL/schema" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Accept: application/json"
```

Используйте schema, если строите UI или валидируете branch payload на своей стороне перед `POST` или `PUT`.

### POST /flows/api/v1/{flow_id}/branches

Создает новый branch. Для этого ключу обычно нужен scope `agents:write`.

Минимальный пример:

```bash
curl -sS -X POST "$A2A_URL/branches" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "branch_id": "support",
    "name": "Support",
    "description": "Сценарий поддержки клиентов",
    "tags": ["support"],
    "permission": [],
    "entry": "answer",
    "nodes": {
      "answer": {
        "type": "llm_node",
        "prompt": "Ответь клиенту кратко и понятно."
      }
    },
    "nodes_mode": "replace",
    "edges": [
      {
        "from_node": "answer",
        "to_node": null
      }
    ],
    "edges_mode": "replace",
    "variables": {
      "tone": {
        "value": "friendly",
        "public": true,
        "title": "Tone",
        "description": "Тон ответа"
      }
    },
    "variables_mode": "merge",
    "resources": {},
    "resources_mode": "merge"
  }'
```

Поля body:

- `branch_id` - обязательный ID нового branch.
- `name` - обязательное название.
- `description` - описание.
- `tags` - массив тегов.
- `permission` - группы доступа. Пустой массив означает "не ограничивать branch отдельными группами".
- `entry` - стартовая нода branch.
- `nodes` - объект нод.
- `nodes_mode` - `replace` заменяет базовые nodes; `merge` добавляет/переопределяет nodes поверх базовых.
- `edges` - массив переходов между нодами.
- `edges_mode` - `replace` или `merge`.
- `variables` - variables branch.
- `variables_mode` - `replace` или `merge`.
- `resources` - ресурсы branch.
- `resources_mode` - `replace` или `merge`.
- `speech` - настройки речи, если branch использует STT/TTS/VAD.

Успешный ответ имеет HTTP status `201`:

```json
{
  "status": "success",
  "message": "Ветка 'support' создана",
  "branch_id": "support"
}
```

Типичные ошибки:

- `400` - body не прошел валидацию или branch после применения невалиден.
- `401` - нет token или token неверный.
- `403` - token есть, но прав недостаточно.
- `404` - flow не найден.
- `409` - branch с таким `branch_id` уже существует.

### PUT /flows/api/v1/{flow_id}/branches/{branch_id}

Полностью заменяет существующий branch. В body нет `branch_id`, потому что он уже в URL.

```bash
curl -sS -X PUT "$A2A_URL/branches/support" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Support v2",
    "description": "Обновленный сценарий поддержки",
    "tags": ["support", "v2"],
    "permission": [],
    "entry": "answer",
    "nodes": {
      "answer": {
        "type": "llm_node",
        "prompt": "Ответь клиенту кратко, спокойно и по делу."
      }
    },
    "nodes_mode": "replace",
    "edges": [
      {
        "from_node": "answer",
        "to_node": null
      }
    ],
    "edges_mode": "replace",
    "variables": {
      "tone": "calm"
    },
    "variables_mode": "merge",
    "resources": {},
    "resources_mode": "merge"
  }'
```

Успешный ответ:

```json
{
  "status": "success",
  "message": "Ветка 'support' обновлена",
  "branch_id": "support"
}
```

Ошибки:

- `400` - invalid body или branch после обновления невалиден.
- `404` - flow или branch не найден.
- `401/403` - проблема с авторизацией или правами.

### DELETE /flows/api/v1/{flow_id}/branches/{branch_id}

Удаляет branch.

```bash
curl -sS -X DELETE "$A2A_URL/branches/support" \
  -H "Authorization: Bearer ${HUMANITEC_TOKEN}" \
  -H "Accept: application/json"
```

Успешный ответ:

```json
{
  "status": "success",
  "message": "Ветка 'support' удалена",
  "branch_id": "support"
}
```

Перед удалением убедитесь, что внешние клиенты не отправляют `metadata.branch: "support"`. Иначе новые запуски начнут получать ошибку branch/permission/validation в зависимости от состояния flow.

## Variables

Variables позволяют передать flow данные без изменения текста пользователя.

Пример:

```json
{
  "metadata": {
    "variables": {
      "customer_name": "Иван",
      "tariff": "pro",
      "order": {
        "id": "ORD-100500",
        "total": 15000,
        "currency": "RUB"
      }
    }
  }
}
```

Где variables используются:

- в prompt'ах flow;
- в input mapping нод;
- в branch configuration;
- в логике code/tools, если flow ожидает эти значения.

### Runtime override

`metadata.variables` переопределяет variables, настроенные в flow или branch, только для конкретного запуска или продолжения диалога.

Если flow имеет переменную:

```json
{
  "company_name": "Default Company"
}
```

а запрос передает:

```json
{
  "metadata": {
    "variables": {
      "company_name": "ACME"
    }
  }
}
```

то в этом запуске flow увидит `ACME`.

### Простые значения и JSON

Можно передавать строки, числа, boolean, массивы и объекты:

```json
{
  "variables": {
    "name": "Анна",
    "age": 17,
    "is_vip": true,
    "tags": ["school", "math"],
    "profile": {
      "city": "Москва",
      "grade": 10
    }
  }
}
```

### Ссылки @var

Если значение верхнего уровня начинается с `@var:`, платформа возьмет значение из сохраненных variables компании:

```json
{
  "metadata": {
    "variables": {
      "crm_token": "@var:crm_token",
      "public_city": "Москва"
    }
  }
}
```

Важно:

- `@var:*` резолвится только на верхнем уровне `metadata.variables`.
- Вложенные `@var:*` внутри объектов не резолвятся автоматически.
- Для secrets лучше использовать сохраненные variables, а не передавать secret прямо в A2A запросе.

Так сработает:

```json
{
  "variables": {
    "api_key": "@var:external_service_api_key"
  }
}
```

Так `@var:*` внутри объекта останется обычной строкой:

```json
{
  "variables": {
    "service": {
      "api_key": "@var:external_service_api_key"
    }
  }
}
```

### Public variables в Agent Card

В Agent Card показываются только variables, которые владелец flow сделал публичными.

Пример:

```json
{
  "variables": {
    "company_name": {
      "title": "Company name",
      "description": "Название компании для ответов",
      "value": "ACME"
    },
    "crm_base_url": {
      "title": "CRM Base URL",
      "type": "reference",
      "key": "crm_base_url"
    }
  }
}
```

Если variable secret или не public, внешняя карточка ее не покажет.

## Files

A2A message может содержать файлы. Файлы передаются как `parts` с `kind: "file"`.

Есть два способа:

- передать bytes в base64;
- передать URI файла.

### Файл bytes/base64

Используйте, когда файл небольшой и ваш backend может безопасно отправить его прямо в JSON.

```json
{
  "kind": "file",
  "file": {
    "name": "invoice.pdf",
    "mimeType": "application/pdf",
    "bytes": "JVBERi0xLjQKJ..."
  }
}
```

Полный пример:

```json
{
  "jsonrpc": "2.0",
  "id": "file-bytes-1",
  "method": "message/send",
  "params": {
    "message": {
      "messageId": "msg-file-1",
      "role": "user",
      "contextId": "file-chat-1",
      "parts": [
        {
          "kind": "text",
          "text": "Проверь счет и скажи сумму к оплате."
        },
        {
          "kind": "file",
          "file": {
            "name": "invoice.pdf",
            "mimeType": "application/pdf",
            "bytes": "JVBERi0xLjQKJ..."
          }
        }
      ]
    },
    "metadata": {
      "branch": "default"
    }
  }
}
```

Требования:

- `file.name` обязателен.
- `file.mimeType` обязателен для корректной передачи файла в flow.
- `file.bytes` должен быть строкой base64.
- Не отправляйте огромные файлы через JSON, если можно использовать ссылку.

### Файл по URI

Используйте, когда файл уже доступен по URL.

```json
{
  "kind": "file",
  "file": {
    "name": "photo.png",
    "mimeType": "image/png",
    "uri": "https://example.com/files/photo.png"
  }
}
```

Полный пример:

```json
{
  "jsonrpc": "2.0",
  "id": "file-uri-1",
  "method": "message/send",
  "params": {
    "message": {
      "messageId": "msg-file-2",
      "role": "user",
      "parts": [
        {
          "kind": "text",
          "text": "Опиши, что на изображении."
        },
        {
          "kind": "file",
          "file": {
            "name": "photo.png",
            "mimeType": "image/png",
            "uri": "https://example.com/files/photo.png"
          }
        }
      ]
    }
  }
}
```

Для URI:

- `file.name` обязателен.
- `file.mimeType` обязателен.
- `file.uri` обязателен.
- URL должен быть доступен тому flow/tool, который будет его использовать.
- Если URI указывает на файл платформы вида `/flows/api/v1/files/download/{file_id}`, файл должен принадлежать той же компании.

### Какие данные о файле получает flow

Flow получает нормализованное описание файла:

```json
{
  "file_id": "file_abc",
  "original_name": "invoice.pdf",
  "url": "/flows/api/v1/files/download/file_abc",
  "content_type": "application/pdf",
  "file_size": 102400
}
```

Поля:

- `file_id` - ID файла в платформе, если файл был сохранен в платформе.
- `original_name` - имя файла от клиента.
- `url` - ссылка на файл.
- `content_type` - MIME type, например `application/pdf`.
- `file_size` - размер файла в bytes, если известен.

Если вы отправляете audio-файл (`audio/*`) как bytes или платформенный файл, flow может получить текстовую расшифровку, если для компании и flow настроен speech-to-text. Если вы отправляете просто внешний URI, убедитесь, что нужный инструмент сам умеет скачать и обработать этот URI.

### Частые ошибки с файлами

- Нет `name` - сервер вернет ошибку валидации файла.
- Нет `mimeType` - flow не сможет надежно понять тип файла.
- `bytes` не base64 - будет ошибка декодирования.
- URI ведет на приватный файл без доступа - flow/tool не сможет его прочитать.
- URI платформенного файла из другой компании - запрос будет отклонен.

## Data parts

Кроме текста и файлов можно передавать структурированные JSON-данные:

```json
{
  "kind": "data",
  "data": {
    "ticket_id": "TCK-100",
    "priority": "high",
    "labels": ["billing", "urgent"]
  }
}
```

Используйте `data`, когда нужно передать объект, а не просить flow извлекать структуру из текста.

Пример:

```json
{
  "messageId": "msg-data-1",
  "role": "user",
  "parts": [
    {
      "kind": "text",
      "text": "Создай ответ по этому тикету."
    },
    {
      "kind": "data",
      "data": {
        "ticket_id": "TCK-100",
        "customer": "Иван",
        "problem": "Не пришел чек"
      }
    }
  ]
}
```

## Embed endpoint для виджетов

Для обычной server-to-server интеграции используйте:

```text
/flows/api/v1/{flow_id}
```

Endpoint embed нужен для браузерных виджетов:

```text
POST /flows/api/v1/embed/{embed_id}
```

Он не принимает обычный company API key напрямую из браузера. Правильная схема такая:

1. Ваш backend хранит `hum_...` API key.
2. Ваш backend вызывает:

```text
POST /frontend/api/embed/configs/{embed_id}/session-token
```

3. Платформа выдает короткоживущий embed-session token.
4. Браузер виджета использует этот короткий token для `/flows/api/v1/embed/{embed_id}`.

Embed-session token обычно ограничен:

- конкретным `embed_id`;
- конкретным `flow_id`;
- конкретным branch;
- разрешенным `Origin`;
- коротким временем жизни;
- набором методов.

Для embed-session token разрешены только:

- `message/send`
- `message/stream`
- `tasks/cancel`

Например, `tasks/get` для embed token не подходит. Для виджетов используйте streaming или логику самого embed runtime.

Никогда не отдавайте company API key `hum_...` в браузер ради embed. В браузер можно отдавать только короткий embed-session token.

## Ошибки

Ошибки бывают двух уровней:

- HTTP status - проблема с самим HTTP-запросом, авторизацией, URL или REST endpoint.
- JSON-RPC error - запрос дошел до A2A handler, но метод или параметры неверные.

### HTTP ошибки

`401 Unauthorized` - token не передан, неверный или истек.

Что проверить:

- есть ли `Authorization: Bearer hum_...`;
- не вставили ли вы пробел/перенос строки в token;
- не отозван ли API key;
- тот ли host и та ли компания.

`403 Forbidden` - token валиден, но доступ запрещен.

Что проверить:

- есть ли права у пользователя, создавшего API key;
- выбран ли правильный branch;
- не ограничен ли branch группами;
- для embed - совпадает ли `Origin`;
- для embed - не отключен ли widget.

`404 Not Found` - flow, branch, embed или URL не найден.

Частые причины:

- используете устаревший URL из старых примеров вместо `/flows/api/v1/{flow_id}`;
- ошиблись в `flow_id`;
- ошиблись в `branch_id`;
- вызываете `GET /branches/{branch_id}` для branch, которого нет;
- вызываете `PUT` вместо `POST` для еще не созданного branch.

`405 Method Not Allowed` - неправильный HTTP method.

Пример: отправили `GET` туда, где нужен `POST`.

`409 Conflict` - конфликт создания.

Пример: `POST /branches` с `branch_id`, который уже существует.

`422 Unprocessable Entity` - REST body не соответствует schema.

Пример: не передали обязательное поле `name` при создании branch.

`500 Internal Server Error` - неожиданная ошибка на стороне платформы или зависимого сервиса. Сохраните `x-request-id` из response headers и передайте его поддержке.

### JSON-RPC коды ошибок

`-32700 Parse error` - body не является валидным JSON.

Пример ошибки:

```json
{
  "jsonrpc": "2.0",
  "id": null,
  "error": {
    "code": -32700,
    "message": "Parse error: ..."
  }
}
```

`-32600 Invalid Request` - JSON-RPC envelope неправильный.

Частые причины:

- нет `method`;
- `id` равен `null`;
- `id` является boolean, массивом или объектом.

`-32601 Method not found` - такого JSON-RPC метода нет.

Проверьте написание:

- правильно: `message/send`;
- неправильно: `messages/send`, `messageSend`, `task/get`.

`-32602 Invalid params` - `params` неправильного типа или поля неверны.

Частые причины:

- `params` не объект;
- `metadata` не объект;
- `metadata.version` не строка;
- `message.parts` пустой или содержит неправильный part;
- `tasks/get` получил `taskId`, а должен получить `id`.

`-32000` - прикладная ошибка выполнения.

Примеры:

- flow не найден;
- task не найден;
- нет доступа к branch;
- embed token не подходит для этого flow;
- embed token не подходит для этого branch;
- Origin не разрешен;
- flow завершился runtime-ошибкой;
- файл не принадлежит компании;
- метод не разрешен для embed-session token.

### Частые исправления запросов

Правильно: URL начинается с `/flows/api/v1/`.

```text
POST /flows/api/v1/support_agent
```

Правильно: `parts` лежит прямо в `message`, а каждый part имеет `kind`.

```json
{
  "message": {
    "messageId": "msg-1",
    "role": "user",
    "parts": [{ "kind": "text", "text": "Привет" }]
  }
}
```

Неправильно: `tasks/get` с `taskId`.

```json
{
  "method": "tasks/get",
  "params": {
    "taskId": "task-abc"
  }
}
```

Правильно:

```json
{
  "method": "tasks/get",
  "params": {
    "id": "task-abc"
  }
}
```

Неправильно: `metadata` строкой.

```json
{
  "metadata": "branch=default"
}
```

Правильно:

```json
{
  "metadata": {
    "branch": "default"
  }
}
```

## Рекомендованный backend wrapper

В реальном проекте лучше не разбрасывать curl/fetch по коду. Сделайте маленький wrapper.

Пример на Node.js:

```js
export async function callFlowA2A({
  flowId,
  method,
  params,
  requestId = crypto.randomUUID(),
}) {
  const url = `https://humanitec.ru/flows/api/v1/${encodeURIComponent(flowId)}`;
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${process.env.HUMANITEC_TOKEN}`,
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    },
    body: JSON.stringify({
      jsonrpc: '2.0',
      id: requestId,
      method,
      params,
    }),
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new Error(`A2A HTTP ${response.status}: ${text}`);
  }

  if (data?.error) {
    const err = new Error(data.error.message);
    err.code = data.error.code;
    throw err;
  }

  return data.result;
}
```

Использование:

```js
const task = await callFlowA2A({
  flowId: 'support_agent',
  method: 'message/send',
  params: {
    message: {
      messageId: crypto.randomUUID(),
      role: 'user',
      contextId: 'chat-123',
      parts: [{ kind: 'text', text: 'Где мой заказ?' }],
    },
    metadata: {
      branch: 'support',
      variables: {
        order_id: 'ORD-100500',
      },
    },
  },
});

console.log(task.status.state);
```

Пример на Python:

```python
import os
import uuid
import httpx


async def call_flow_a2a(flow_id: str, method: str, params: dict) -> dict:
    url = f"https://humanitec.ru/flows/api/v1/{flow_id}"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {os.environ['HUMANITEC_TOKEN']}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": str(uuid.uuid4()),
                "method": method,
                "params": params,
            },
        )

    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(f"A2A error {payload['error']['code']}: {payload['error']['message']}")
    return payload["result"]
```

## Чеклист перед production

- API token создан в консоли платформы.
- Token хранится только на backend.
- У token минимальные scopes.
- В логах token маскируется.
- Используется правильный URL `/flows/api/v1/{flow_id}`.
- `flow_id` и `branch_id` берутся из конфигурации, а не вводятся пользователем без проверки.
- Для чата сохраняется и повторно используется `contextId`.
- Для долгих задач используется `message/stream` или async `message/send` + `tasks/get`.
- Файлы имеют `name` и `mimeType`.
- Для secrets используются `@var:*` или защищенные настройки, а не открытый текст в запросе.
- Ошибки JSON-RPC и HTTP обрабатываются отдельно.
- Для embed не используется company API key в браузере.
- В мониторинге сохраняются `id` JSON-RPC запроса, `task.id`, `contextId` и HTTP `x-request-id`.

## Что смотреть дальше

Ниже на странице находится автоматически сгенерированный справочник endpoints из OpenAPI. Используйте эту инструкцию как "как правильно пользоваться A2A", а справочник ниже - как точный список HTTP routes, параметров и response schemas.

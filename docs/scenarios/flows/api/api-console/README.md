# Flows: API Console и A2A запуск

Полная инструкция по модалке API Console в редакторе Flows: где взять endpoint, как читать A2A JSON-RPC body, как запускать Streaming/Sync/Async и как разбирать реальные ответы API.

## Шаг 1. Открываем API Console из редактора flow

API Console открывается из редактора flow кнопкой `API` в верхней панели. Это не отдельный тестовый
стенд и не пример "примерно как надо": модалка строит endpoint, branch, JSON body, headers и code
samples из текущего `flow_id`, активной ветки и текущих переменных flow.

Кнопки в шапке модалки:

- `Инструкция` открывает эту страницу документации в `/documentation/scenarios/flows/api-console/`.
- `Копировать JSON body` копирует текущий A2A JSON-RPC body для выбранного режима.
- `Fullscreen` разворачивает модалку, когда нужно читать большие JSON/SSE ответы.
- `Close` закрывает модалку и возвращает в редактор.

Левая колонка всегда остается навигацией: карточка endpoint показывает, куда отправлять POST,
какой `branch_id` выбран, какой протокол используется и какой режим активен. Ниже четыре вкладки:
`Старт`, `Примеры`, `Поля A2A`, `Запуск`.

![Открываем API Console из редактора flow](screenshots/001.png)

## Шаг 2. Разбираем вкладку Старт и режимы A2A

Вкладка `Старт` отвечает на вопрос "что мне отправить самым первым запросом".

В верхнем блоке:

- `flow_id` показывает точный ID агента из URL и endpoint.
- `branch_id` показывает ветку выполнения. Для базовой ветки UI показывает `default`.
- `contextId` показывает пример ID диалога. Повторяйте один и тот же `contextId`, чтобы продолжать
  разговор; создавайте новый, чтобы начать чистую сессию.
- счетчик переменных показывает, сколько flow variables есть у текущей ветки.

Переключатель режима меняет весь пример сразу:

- `Streaming` использует `method: "message/stream"` и `Accept: text/event-stream`.
- `Sync` использует `method: "message/send"` и `Accept: application/json`.
- `Async` использует `method: "message/send"` плюс `metadata.execution_mode: "async"`.

Ниже карточки режимов и таблица методов A2A. В обычной интеграции чаще всего нужны
`message/stream`, `message/send` и `tasks/get`; остальные методы нужны для отмены, resubscribe,
Agent Card и push notification config.

![Разбираем вкладку Старт и режимы A2A](screenshots/002.png)

## Шаг 3. Берем готовые curl, Python и JS примеры

Вкладка `Примеры` дает готовые варианты для внешнего клиента.

Что здесь есть:

- языки `curl`, `Python`, `JS`; переключение меняет только код, но не смысл запроса;
- кнопка `Копировать` копирует текущий пример целиком;
- блок `Текущий JSON body` показывает тот же payload, который уйдет в live-run;
- блок `Файлы` показывает A2A `file` part. URI-файл передается с `name` и `mimeType`, а backend
  нормализует его в `state.files`; audio-file дополнительно проходит STT, если voice runtime настроен.

Минимальный JSON-RPC body:

- `jsonrpc: "2.0"` всегда фиксирован.
- `id` нужен клиенту, чтобы сопоставить ответ с запросом.
- `method` зависит от режима.
- `params.message.messageId` уникален для входного сообщения.
- `params.message.role` обычно `user`.
- `params.message.parts` содержит `text`, `file` или `data`.
- `params.message.contextId` связывает сообщения в один диалог.
- `params.metadata.branch` выбирает ветку выполнения.
- `params.metadata.variables` передает runtime variables только для этого запуска.

![Берем готовые curl, Python и JS примеры](screenshots/003.png)

## Шаг 4. Проверяем каждое поле A2A и правила variables

Вкладка `Поля A2A` нужна, когда непонятно, зачем конкретное поле существует.

Главные нюансы:

- `metadata.branch` выбирает ветку графа. Если выбрать base в UI, API получает `default`.
- `metadata.variables` передает данные в запуск flow и не используется для выбора ветки.
- `metadata.version` выбирает версию flow, но query `?v=...` имеет приоритет.
- `metadata.execution_mode` в `message/send` со значением `async` или `background` включает
  асинхронный запуск.
- `metadata.breakpoints` и `metadata.triggers` нужны редактору/debug/trigger runtime; обычному
  публичному клиенту они чаще всего не нужны.

Переменные:

- `metadata.variables` перекрывают flow variables только на время одного запуска.
- Значение может быть примитивом, объектом или массивом.
- Строки с `@var:key` резолвятся через company VariablesService; поддерживается вложенный JSON и
  рекурсивные ссылки вроде `@var:api_endpoint`, если сама переменная содержит `@var:base_url`.
- Если передать объект формата flow variable (`value`, `secret`, `public`, `title`, `description`),
  runtime использует `value`, а остальные поля служат для UI/документации.
- `secret` скрывает значение в UI, но не меняет поведение runtime.
- `public` показывает переменную в Agent Card как параметр, который должен заполнить внешний клиент.

Системные переменные (`user_id`, `company_id`, `active_namespace` и другие) добавляет backend из
авторизованного HTTP-контекста после клиентских variables, поэтому внешний клиент не может подделать
пользователя или компанию через `metadata.variables`.

![Проверяем каждое поле A2A и правила variables](screenshots/004.png)

## Шаг 5. Запускаем Streaming и видим настоящий ответ API

Вкладка `Запуск` — рабочий стол тестирования реального API.

Левая колонка:

- `Режим` выбирает Streaming/Sync/Async и сразу перестраивает method, Accept header и JSON body.
- `contextId` задает диалог. Оставьте его тем же для продолжения, нажмите `Новый contextId` для
  чистой сессии.
- `Сообщение` становится `params.message.parts[0].text`.
- `metadata.variables JSON` попадает в `params.metadata.variables`.
- `Run` отправляет настоящий запрос в текущий `/flows/api/v1/{flow_id}` с текущей browser-сессией.
- `Предпросмотр запроса` показывает HTTP method, Accept, Content-Type, credentials и полный body.

Для Streaming UI отправляет `message/stream`, читает реальные SSE frames и собирает ответ агента из
этих событий. Это режим по умолчанию для чатового UX: пользователь видит ответ по мере генерации,
а разработчик может смотреть каждое событие отдельно.

![Запускаем Streaming и видим настоящий ответ API](screenshots/005.png)

## Шаг 6. Открываем инспектор ответа: JSON, SSE, headers, raw и полный result

Инспектор ответа показывает не только итоговый текст, но весь API-ответ.

Верхняя полоска статуса:

- `HTTP status` и `Content-Type` приходят из реального HTTP response.
- `task_id` создается backend и нужен для `tasks/get`, `tasks/cancel`, `tasks/resubscribe`.
- `context_id` подтверждает, в какой диалог попал запрос.
- `Состояние A2A` показывает `submitted`, `working`, `input-required`, `completed`, `failed` и другие
  состояния task.
- `SSE события` показывает количество stream frames.

Вкладки инспектора:

- `JSON-ответ` — нормализованный JSON body для текущего режима.
- `SSE события` — массив реальных stream events: status updates, artifact updates, final states.
- `Заголовки` — HTTP headers ответа.
- `Raw-ответ` — исходный текст ответа без нормализации.
- `Async опросы` — запросы/ответы `tasks/get`, которые UI делал после async-submit.
- `Полный result` — полный объект, который вернул frontend resource: request envelope, response
  envelope, parsed body, raw text, frames, polls, extracted text и ошибки.

![Открываем инспектор ответа: JSON, SSE, headers, raw и полный result](screenshots/006.png)

## Шаг 7. Проверяем синхронный режим message/send

Sync нужен, когда внешний клиент хочет один HTTP response без чтения SSE.

UI отправляет:

- `method: "message/send"`;
- `Accept: application/json`;
- без `metadata.execution_mode: "async"`.

HTTP-запрос ждет завершения flow и возвращает JSON-RPC response с финальным A2A Task. Этот режим
проще для backend-to-backend интеграций, cron jobs и коротких deterministic flow. Если flow может
работать долго, лучше использовать Streaming или Async, чтобы не держать HTTP request открытым.

![Проверяем синхронный режим message/send](screenshots/007.png)

## Шаг 8. Проверяем async submit и последующие tasks/get опросы

Async нужен для долгих задач и фоновых запусков.

UI отправляет:

- `method: "message/send"`;
- `Accept: application/json`;
- `metadata.execution_mode: "async"`.

Первый ответ должен вернуться быстро со state `submitted` и `task_id`. После этого результат получают
через `tasks/get` по `task_id` или `contextId`. В этой модалке `Async опросы` показывает, какие
`tasks/get` запросы были сделаны и какой финальный Task вернулся.

Типовые сценарии:

- Первый запрос: создайте новый `contextId`, заполните сообщение и нажмите `Run`.
- Продолжение диалога: оставьте прежний `contextId`, отправьте следующее сообщение.
- Ветка: меняйте ветку в редакторе; API использует `metadata.branch`.
- Runtime variables: заполните `metadata.variables JSON`, например `{"customer_name":"Anna"}`.
- Переменные-секреты: передавайте `@var:secret_key`, если значение лежит в VariablesService.
- Ошибка `failed`: смотрите `JSON-ответ`, `Raw-ответ` и `Полный result`.
- Ошибка `input-required`: task ждет пользовательский ввод; отправьте следующее сообщение с тем же
  `contextId`.

![Проверяем async submit и последующие tasks/get опросы](screenshots/008.png)

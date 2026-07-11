"""Короткие тексты подсказок для сценариев API Console (Flows UI E2E)."""

START_DETAILS_RU = (
    "На вкладке «Старт» видно, куда отправлять первый запрос: адрес агента, выбранную "
    "ветку и пример идентификатора диалога. Переключатель режима меняет способ вызова: "
    "потоковый ответ, один синхронный ответ или фоновый запуск с последующей проверкой "
    "статуса."
)

START_DETAILS_EN = (
    "The Start tab shows where to send the first request: agent endpoint, selected branch, "
    "and a sample conversation id. The mode selector changes how the call works: streaming "
    "response, one synchronous response, or a background run with later status checks."
)

SYNC_DETAILS_RU = (
    "Синхронный режим отправляет одно сообщение и ждёт финальный JSON-ответ без чтения "
    "потока событий. Так удобно проверять короткие сценарии и интеграции backend-to-backend."
)

SYNC_DETAILS_EN = (
    "Sync mode sends one message and waits for a final JSON response without reading a "
    "stream of events. This is handy for short scenarios and backend-to-backend integrations."
)

ASYNC_DETAILS_RU = (
    "Асинхронный режим быстро возвращает идентификатор задачи, а результат можно дочитать "
    "отдельными запросами статуса. В модалке видно, какие проверки статуса уже выполнены."
)

ASYNC_DETAILS_EN = (
    "Async mode quickly returns a task id, and you can fetch the result with separate status "
    "requests. The modal shows which status checks were already performed."
)

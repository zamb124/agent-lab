---
trigger: always_on
description: "Правила обработки исключений"
globs:
---
# Правила обработки исключений

Не делай излишние try except блоки - добавляй проверки и бросай исключения с контекстом.

## Логирование исключений

Если лог необходим, используй `exc_info=True`:

<good_example>
try:
    result = await some_operation()
except Exception as e:
    logger.error("Ошибка операции", exc_info=True)
    raise
</good_example>

<bad_example>
logger.error(f"Ошибка получения контактов: {e.response.status_code} - {e.response.text}")
</bad_example>

## Расширение исключений

Расширяй исключение контекстом и прокидывай дальше через `from e`:

<good_example>
try:
    contacts = await amocrm_client.get_contacts(limit=100)
except httpx.HTTPStatusError as e:
    raise httpx.HTTPStatusError(
        f"Не удалось получить контакты из AmoCRM (subdomain={self.subdomain}, limit={limit}): "
        f"{e.response.status_code} - {e.response.text[:200]}",
        request=e.request,
        response=e.response,
    ) from e
</good_example>

## Проверки вместо try-except

Добавляй проверки перед операциями:

<good_example>
if not user_id:
    raise ValueError("user_id не может быть пустым")

if not url.startswith("https://"):
    raise ValueError(f"Небезопасный URL: {url}")
</good_example>
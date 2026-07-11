# tests/ui — E2E UI и документация

Playwright E2E для SPA платформы. Сценарии с `@pytest.mark.scenario` генерируют пользовательские инструкции в `docs/scenarios/`.

## Запуск

```bash
make test-ui          # test-up + pytest tests/ui/e2e
make test-ui-doc      # test-ui + make doc
```

## Новая инструкция

1. Зарегистрируйте **`tag`** в [`docs/scenarios/taxonomy.yaml`](../docs/scenarios/taxonomy.yaml) (если темы ещё нет).
2. Добавьте тест в `tests/ui/e2e/test_<service>_*.py`:

```python
@pytest.mark.scenario(
    service="sync",
    tag="chat",
    doc_slug="send-message-in-channel",
    title="Sync: отправка сообщения в канал",
    title_en="Sync: send a message in a channel",
    description=(
        "**Для чего:** …\n\n"
        "**Какие проблемы решает:** …\n\n"
        "**Результат:** …"
    ),
    description_en="…",
)
async def test_user_sends_message(scenario: ScenarioRecorder, sync_ui: AppUI, page: Page) -> None:
    await scenario.step(
        "Откройте канал",
        page,
        label_en="Open the channel",
        screenshot_name="channel-opened",
        details="Что сделать, зачем это нужно и что должно появиться на экране.",
        details_en="What to do, why it matters, and what should appear on screen.",
    )
    # Ещё 2–5 содержательных шагов.
    await scenario.step(
        "Проверьте отправленное сообщение",
        page,
        label_en="Verify the sent message",
        screenshot_name="message-visible",
        details="**Демонстрация результата.** …\n\n**Итог.** …",
        details_en="**Result demonstration.** …\n\n**Summary.** …",
    )
```

3. Делайте **4–7** пользовательских шагов. У каждого обязательны `page`, `details` и короткий смысловой `screenshot_name`.
4. `make test-ui-doc` — обновить README и статический сайт.

README и его PNG всегда лежат в одном каталоге:

```text
docs/scenarios/sync/chat/send-message-in-channel/
├── README.md
├── README.en.md
├── send-message-in-channel--01-channel-opened.png
└── send-message-in-channel--04-message-visible.png
```

Формат имени задаёт движок: `<doc_slug>--<номер>-<screenshot_name>.png`. Папка `screenshots/` запрещена.

## Office (`/documents`)

- Helpers: [`tests/ui/e2e/office_e2e_helpers.py`](e2e/office_e2e_helpers.py)
- Матрица покрытия: [`tests/ui/e2e/office_e2e_coverage_matrix.md`](e2e/office_e2e_coverage_matrix.md)
- Фикстура: `office_ui` (порт 9008, subdomain `system`)
- API seed: `office_client_http`, `auth_headers_system`; для RAG — `rag_service`, `rag_worker`
- Анонимный preview: `ui_page_anonymous`

## Правила

| Поле | Правило |
|---|---|
| `service` | Ключ из taxonomy: `sync`, `flows`, `platform`, `crm`, `rag`, `frontend`, `office` |
| `tag` | Обязан существовать в `taxonomy.yaml` для этого `service` |
| `doc_slug` | kebab-case, уникален внутри `service` |
| URL в доке | `/documentation/scenarios/{service}/{doc_slug}/` |

Подробнее: [`doc-sources.md`](../doc-sources.md), [`.cursor/rules/testing.mdc`](../.cursor/rules/testing.mdc).

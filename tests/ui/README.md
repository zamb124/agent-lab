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
    description="…",
    description_en="…",
)
async def test_user_sends_message(scenario: ScenarioRecorder, sync_ui: AppUI, page: Page) -> None:
    await scenario.step("Открыт канал", page, label_en="Channel opened")
    await scenario.step("Сообщение отправлено", page, label_en="Message sent")
```

3. Минимум **2** вызова `scenario.step(..., page, label_en=...)` со скриншотами (для Office — целевой формат **4–7** шагов на инструкцию).
4. `make test-ui-doc` — обновить README и статический сайт.

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

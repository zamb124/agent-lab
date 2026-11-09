# tests/ui — E2E UI и документация

Playwright E2E для SPA платформы. Сценарии с `@pytest.mark.scenario` генерируют пользовательские инструкции в `docs/scenarios/`.

## Запуск

```bash
make test-ui          # test-up + pytest tests/ui/e2e -n<ресурсы> --dist=loadfile (+ perf SUMMARY)
make test-ui-doc      # test-ui + make doc
UI_E2E_WORKERS=1 make test-ui   # serial (отладка)
UI_E2E_WORKERS=auto make test-ui  # явно: то же число, что и дефолт
```

`UI_E2E_WORKERS` по умолчанию выводится из ресурсов машины —
`scripts.testing.stack.default_ui_e2e_workers()` = `min(8, cpu//2, ram_gb//3)`,
минимум 2. UI-воркер держит отдельный Chromium (~2-3GB RSS под нагрузкой),
поэтому ram-бюджет жёстче, чем у unit-воркеров (`ram_gb//4` там, браузер
тяжелее). На 8+ воркерах `--dist=loadfile` уже не ускоряет прогон — таймауты
и шум растут быстрее параллелизма.

Бюджет тела теста — **15 с** (`tests/ui/e2e/conftest.py`). Дольше только через `scenario(timeout_seconds=N)`.

### UI perf

На **каждый** прогон `tests/ui/e2e` (включая `make test-ui` / `make test-ui-chat`) collector автоматически пишет подробный отчёт — без флагов и без правок тел тестов.

Собирается:

- HTTP: method, path, status, duration_ms, resource_type, service prefix
- Navigation Timing (DCL / load)
- Long tasks (`PerformanceObserver`)

Артефакты:

```text
artifacts/ui-perf/
├── SUMMARY.md                 # slowest tests, API paths, long tasks, errors
└── gw0/
    └── tests_ui_e2e_....json  # per-test отчёт
```

Метрики относительные (headless + xdist + MockLLM) — для поиска hotspots, не SLA. CI-gate по порогам в v1 нет.

### Параллель и изоляция

- **xdist:** `UI_E2E_WORKERS` — ресурсозависимый дефолт (см. выше), `--dist=loadfile` (файл целиком на одном worker).
- **Company:** `ui_e2e_gw{N}` / subdomain `ui-gw{N}` — не shared `system` roster.
- **MockLLM:** scope `test_e2e_gw{N}`; браузер шлёт `X-Test-Scope` (см. `tests/ui/e2e_worker.py`).
- **Запрещено:** дописывать members в `system` из UI session fixtures; assert'ы на глобальный `system.members`.

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

## Маркетинговые кадры (`tests/ui/shots/`)

Высокоразрешённые (2x) скриншоты продуктов на реальных сидированных демо-данных —
для продуктовых страниц `/products/*` и секции «Возможности платформы» лендинга.

```bash
uv run pytest tests/ui/shots/test_marketing_shots.py -q          # весь suite (32 кадра)
uv run pytest tests/ui/shots/test_marketing_shots.py -k crm -q   # подмножество
```

- **Сиды:** `seed_content.py` — session-фикстура `marketing_seeded`; идемпотентна
  (dedupe по именам/namespace, повторные прогоны не копят дубли). Ошибки сидов
  fail-fast — зелёный тест = сид реально записался.
- **Кадры:** `out/<name>.png` (gitignored). Каждый кадр обязателен к **ручному
  визуальному просмотру** — зелёный тест не означает красивый маркетинговый кадр.
- **Конвейер в лендинг:** `uv run python -m scripts.tools.land_optimize`
  (`sips -Z 2400` → `apps/frontend/ui/assets/images/land/optimized/`), затем
  экспорт URL в `apps/frontend/ui/_helpers/land-product-images.ts`.
- **Особенности:** cookie-баннер снимается до кадра (`dismiss_cookie_banner`);
  geo-кадры ждут реальный рендер карты (source features + `map.loaded()`);
  CRM-граф кадрируется через `_fitNonce`, глубина — `_maxDepth` + `_rebuildGraphByMode()`.

## Office (`/documents`)

- Helpers: [`tests/ui/e2e/office_e2e_helpers.py`](e2e/office_e2e_helpers.py)
- Матрица покрытия: [`tests/ui/e2e/office_e2e_coverage_matrix.md`](e2e/office_e2e_coverage_matrix.md)
- Фикстура: `office_ui` (порт 9008, subdomain worker `ui-gwN`)
- API seed: `office_client_http`, `auth_headers_system` (токен worker-компании); для RAG — `rag_service`, `rag_worker`
- Анонимный preview: `ui_page_anonymous`

## Правила

| Поле | Правило |
|---|---|
| `service` | Ключ из taxonomy: `sync`, `flows`, `platform`, `crm`, `rag`, `frontend`, `office` |
| `tag` | Обязан существовать в `taxonomy.yaml` для этого `service` |
| `doc_slug` | kebab-case, уникален внутри `service` |
| URL в доке | `/documentation/scenarios/{service}/{doc_slug}/` |

Подробнее: [`doc-sources.md`](../doc-sources.md), [`.cursor/rules/testing.mdc`](../.cursor/rules/testing.mdc).

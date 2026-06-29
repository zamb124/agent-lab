---
name: documentator
description: >
  Документатор Humanitec: Playwright tests/ui/e2e, @pytest.mark.scenario,
  docs/scenarios, taxonomy, ScenarioRecorder, make test-ui-doc. Использовать при
  написании E2E-инструкций, scenario README, office/sync/flows/embed сценариев.
---

# Documentator — Humanitec

## База

Полный канон: [`testing.mdc`](../../rules/testing.mdc) § UI E2E, [`tests/ui/README.md`](../../../tests/ui/README.md), [`doc-sources.md`](../../../doc-sources.md). Этот skill — **операционные решения**, которые легко забыть.

**Сюда:** Playwright E2E в `tests/ui/e2e/`, `@pytest.mark.scenario` → `docs/scenarios/` через [`ScenarioRecorder`](../../../tests/ui/scenario_doc.py).

**Не сюда:** unit JS (`tests/frontend_core/`), engine (`tests/ui/engine/`) — только smoke при необходимости.

## Команды

| Команда | Назначение |
|---|---|
| `make test-up` | Postgres / Redis / MinIO — предусловие session HTTP |
| `make test-ui` | Полный прогон; **всегда** `UI_E2E_USE_LVH_ME=1` ([`mk/test.mk`](../../../mk/test.mk)) |
| `make test-ui-doc` | E2E + `check_scenario_docs_quality` + `make doc` |
| `uv run pytest tests/ui/e2e/test_*.py -k ... -v --tb=short` | Точечный прогон |

## Анатомия теста

```python
@pytest.mark.scenario(
    service="sync",           # ключ taxonomy
    tag="chat",               # должен быть в taxonomy.yaml
    doc_slug="send-message",  # kebab-case, уникален в service
    title="Sync: …",
    title_en="Sync: …",       # если есть — label_en у каждого step
    description="…",
)
@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.timeout(120)     # complete guide — до 360
async def test_…(
    scenario: ScenarioRecorder,
    sync_ui: AppUI,
    page: Page,
    unique_id: str,
    auth_token_system: str,
) -> None:
    # 1. API seed (httpx + cookie), не page.evaluate(fetch)
    # 2. await sync_ui.open(page); await sync_ui.expect_shell(page)
    await scenario.step("Краткая подпись шага", page, label_en="Step label")
    await expect(page.locator("sync-app")).to_be_visible()
```

**Фикстуры:** `scenario`, `*_ui` (`flows_ui`, `office_ui`, …), `ui_page_system` / `ui_page_company2` / `ui_page_anonymous`, `auth_token_*`, `unique_id`. Гость: `ui_page_anonymous` без cookie.

**Паттерн:** seed → open shell → действия → `scenario.step(..., page)` на ключевых экранах → `expect`. Эталоны: [`test_sync_complete_guide.py`](../../../tests/ui/e2e/test_sync_complete_guide.py), [`test_flows_editor_scenarios.py`](../../../tests/ui/e2e/test_flows_editor_scenarios.py).

## AppUI, origins, auth

[`AppUI`](../../../tests/ui/harness.py) + реестр [`tests/ui/apps.py`](../../../tests/ui/apps.py): `port`, `spa_path`, `shell_selector`, `subdomain_prefix`.

| Режим | Host | Когда |
|---|---|---|
| `UI_E2E_USE_LVH_ME=1` | `system.lvh.me:900N` | `make test-ui`, subdomain-сервисы |
| default | `system.localhost:900N` / `localhost:900N` | локальный pytest без env |

**Cookies** [`browser_auth.py`](../../../tests/ui/browser_auth.py): `auth_token` на `localhost`, `system.localhost`, `company2.localhost`, **`.lvh.me`** — оба набора, иначе auth ломается при переключении режима.

**Embed / cross-origin:** frontend API и embed script — **`http://localhost:9004`**, не `system.lvh.me` (CORS/cookie). External host page — `localhost`, не `127.0.0.1`.

**Тема:** session init script → light ([`conftest.py`](../../../tests/ui/conftest.py)).

## Инфраструктура фикстур

Порты = [`tests/fixtures/services.py`](../../../tests/fixtures/services.py).

| Сервис | Порт | `*_ui` | Зависимости / нюанс |
|---|---|---|---|
| flows | 9001 | `flows_ui` | `secrets_service` (9022) при `@var:` / external API в flow |
| rag | 9002 | `rag_ui` | subdomain `system` |
| crm | 9003 | `crm_ui` | subdomain `system` |
| frontend | 9004 | `frontend_ui` | settings, agent CTA |
| sync | 9005 | `sync_ui` | `taskiq_worker` для transcribe |
| office | 9008 | `office_ui` | `X-Platform-Namespace`; дерево в sidebar, не отдельная explorer-страница |

Seed: **httpx + auth cookie** или repo helper ([`sync_e2e_helpers.py`](../../../tests/ui/e2e/sync_e2e_helpers.py)). Office API: `office_client_http`; RAG-сценарии — `rag_service`, `rag_worker`.

## Helpers

Один модуль на сервис: `tests/ui/e2e/<service>_e2e_helpers.py` — локаторы, seed, navigation. Префикс: `sync_e2e_*`, `flows_e2e_*`, `office_e2e_*`.

- **Flows API:** edges `from_node`/`to_node`; code node — top-level `code`/`language`, не nested `config` ([`flows_e2e_helpers.py`](../../../tests/ui/e2e/flows_e2e_helpers.py)).
- **Flows UI:** закрыть `flows-floating-panel[show-backdrop]` перед Publish.
- **Office:** 4–7 `scenario.step` на инструкцию; namespace через API + init script/localStorage. Матрица: [`office_e2e_coverage_matrix.md`](../../../tests/ui/e2e/office_e2e_coverage_matrix.md).

## Локаторы и assert

- Ждать **shell** из registry: `flows-app`, `office-app`, `sync-app`, …
- Custom elements: `platform-field`, `platform-button`, `platform-modal-stack`, `platform-bottom-sheet-stack`.
- i18n: regex `(Открыть|Open)`, `(Сохранить|Save)` — не хардкод одного языка.
- Sync: sidebar vs chat header — helpers различают контекст.
- **Запрещено:** ослаблять assert «чтобы прошло»; `networkidle` как единственный sync; моки кроме platform MockLLM; `page.evaluate(fetch)` для setup.

## Scenario → документация

1. `tag` ∈ [`docs/scenarios/taxonomy.yaml`](../../../docs/scenarios/taxonomy.yaml) — иначе CI.
2. `doc_slug` уникален внутри `service`; URL: `/documentation/scenarios/{service}/{doc_slug}/`.
3. Минимум **2 шага + 1 скрин**; **Office — 4–7** шагов.
4. `title_en` в маркере → `label_en` у **каждого** `scenario.step`.
5. README: `## Шаг N.` / `## Step N.`; prose перед скрином — зачем шаг и что на экране.
6. После добавления: `make test-ui-doc`.

## Embed / ESM

- Imports в embed-closure: только **relative** / `lit-shim`; `@platform/...` ловит [`scripts/check_embed_esm_closure.py`](../../../scripts/check_embed_esm_closure.py).
- Fixture `embed_browser_http_stack_ready` зависит от `secrets_service` при flow с переменными.
- Host page и API base — согласованный origin (`localhost:9004`).

## Чеклист перед merge

- [ ] `tag` + `doc_slug` в taxonomy при `@pytest.mark.scenario`
- [ ] helpers вынесены; тест читается как сценарий
- [ ] session fixtures: `secrets_service`, `taskiq_worker`, `rag_worker` — по необходимости
- [ ] `make lint` при правках `tests/ui`
- [ ] целевой pytest или `make test-ui` зелёный
- [ ] scenario — `make test-ui-doc`

## Карта файлов

| Файл | Роль |
|---|---|
| [`tests/ui/conftest.py`](../../../tests/ui/conftest.py) | `page`, `*_ui`, personas, `scenario`, light theme |
| [`tests/ui/harness.py`](../../../tests/ui/harness.py) | `AppUI`, origins, `ui_e2e_use_lvh_me()` |
| [`tests/ui/apps.py`](../../../tests/ui/apps.py) | порты, shell selectors, subdomain |
| [`tests/ui/scenario_doc.py`](../../../tests/ui/scenario_doc.py) | шаги, скрины, README.md/en |
| [`tests/ui/browser_auth.py`](../../../tests/ui/browser_auth.py) | cookie domains |
| [`tests/fixtures/services.py`](../../../tests/fixtures/services.py) | session HTTP servers |

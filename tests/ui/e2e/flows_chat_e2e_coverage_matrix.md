# platform-chat: маршруты и покрытие E2E / browser / unit

Справочник для Playwright E2E (`tests/ui/e2e/test_flows_chat_page.py`, embed autoload) и WTR browser specs (`tests/frontend_core/browser/flows/*chat*`).

## Маршруты flows SPA (`apps/flows/ui/app/flows-app.js`)

| routeKey | path | host |
|----------|------|------|
| `flow_chat` | `/flows/:flowId` | `chat-page` → `<platform-chat display="page" profile="spa">` |
| `flow_chat_branch` | `/flows/:flowId/branch/:branchId` | то же |
| `flow_chat_session` | `/flows/:flowId/session/:sessionId` | restore session |

## Матрица «канон vs тест» (baseline 2026-07-06)

| Область | Unit (Vitest) | WTR browser | pytest backend | pytest UI E2E | Статус |
|---------|---------------|-------------|----------------|---------------|--------|
| Reducer / A2A parse | `chat-state`, `a2a-chat-runtime` | — | `test_embed_stream` | — | OK |
| chat-profile auth | `chat-profile` | stub `chat-profile-stub.js` | `test_chat_profile` | — | OK |
| `flows-chat-message` UI | `flows-chat-markdown-fallback` | 8 tests `flows-chat-message.spec.js` | — | — | OK |
| bubble meta + observability | — | message spec | — | `test_flows_chat_page_observability_*` | OK |
| `flows-chat-input` send/stop/TTS | — | 2 tests | — | — | OK |
| execution-panel host | — | 5 tests | — | — | OK |
| chat-page toolbar + modals | — | 3 tests `chat-page-toolbar.spec.js` | — | header/bubble in chat-page E2E | OK |
| **chat-page SPA send/stream** | — | — | — | `test_flows_chat_page_send_and_stream_reply` | OK |
| cancel / new chat | `chat-state` partial | stop-btn in input spec | cancel in embed_stream | cancel + clear E2E | OK |
| chat-profile на странице | — | stub (no 404) | API matrix | live fetch in E2E | OK |
| policy viewConfig | `chat-profile` | embed override modal | embed API | — | partial |
| observability modals polling | — | `observability-modals-polling.spec.js` | — | tracing/logs E2E | OK |
| handoff/handback cards | `chat-state` | `chat-handoff-card.spec.js` | integration handoff | — | partial |
| embed drawer autoload | `embed-autoload` (10) | embed modals | embed API | `test_embed_autoload_browser` (3) | OK |
| embed code modal | — | 5 tests | production URLs API | — | OK |
| voice in platform-chat | `voice-agent-bridge` | input TTS events | — | `test_voice_chat` (отдельно) | partial |
| landing demo drawer | — | — | `test_public_landing_agents` | `test_landing_demo_drawer_opens_platform_chat` | smoke |
| browser preview / action blocks | — | message spec | — | — | OK |
| files panel + file viewer | — | message + file-viewer | — | — | OK |

## Baseline run (2026-07-06)

| Suite | Команда | Result |
|-------|---------|--------|
| Unit chat | `npx vitest run tests/frontend_core/unit/chat/` | 44 passed |
| WTR chat core | `npm run test:core-browser -- --files '…chat*.spec.js' 'execution-panel-chat-input.spec.js'` | 18+ passed |
| WTR observability + embed | observability-modals, embed-code-modal, embed-chat-override, lara-confirm | 6 passed |
| Backend chat | `pytest tests/flows/e2e/test_embed_stream.py tests/flows/api/test_chat_profile.py tests/frontend/api/test_embed_configs_api.py` | 45 passed |
| Full UI E2E chat | `make test-ui-chat` (flows chat-page + embed autoload + landing drawer) | run in CI / `make test-up` |

## Файлы тестов

| Файл | Сценарии |
|------|----------|
| `test_flows_chat_page.py` | SPA send/stream, observability modals, cancel, new chat |
| `test_embed_autoload_browser.py` | embed autoload mount, toggle, host proxy S2S |
| `test_landing_demo_chat_drawer.py` | landing home demo drawer smoke |
| `flows_e2e_helpers.py` | `flows_api_create_chat_test_flow`, `flows_open_chat_page`, `flows_chat_send_message` |
| `tests/fixtures/flows_chat_e2e.py` | `flows_chat_test_agent`, `flows_chat_slow_agent` |

Browser helpers: `tests/frontend_core/browser/helpers/chat-profile-stub.js`.

Make target: `make test-ui-chat`.

---
name: frontend-engineer
description: Frontend инженер Платформы. ZERO-FALLBACK, ZERO-IMPORT, ZERO-COSTYL, Design Standard. Lit 3 + EventBus + фабрики (createAsyncOp / createResourceCollection / createCursorList / createFacets / createForm / createSlice). Использовать ВСЕГДА при правках в core/frontend/static/lib/**, apps/*/ui/**, добавлении страниц/модалок/компонентов/ресурсов/событий/полей форм/i18n/маршрутов/дизайна/CSS; при упоминании Lit, PlatformElement, PlatformPage, PlatformApp, PlatformModal, PlatformFormModal, useResource, useOp, useForm, useCursorList, useFacets, useSlice, dispatch, EventBus, slice, reducer, modal, bottom sheet, sidebar, breadcrumbs, toast, навигации, темы, locale, фабрик, restMirror, transport='ws', commandType, WS request-reply, factory-registry, glass-modal, platform-modal-stack, platform-field, platform-trace-viewer, platform-log-viewer, platform-user-chip, tokens.css, Figma, Networkle, layout, CSS; перед коммитом любых .js под frontend; при ошибках check_ui_canon / check_ui_factories / check_field_canon / check_i18n / check_i18n_keys / check_core_frontend_canon / check_command_rest_mirror / check_ui_kit_docs; и каждый раз когда задача уровня "изменить UI", "добавить страницу", "новый ресурс", "новая модалка", "новое поле", "i18n", "поменять стейт", "WS-команда", "слать событие", "поменять дизайн".
---

# Frontend Engineer — процедура

Нормы UI — в правилах `frontend.mdc`, `ui_factories.mdc`, `ui_components.mdc`, `ui_fields.mdc`; скил задаёт порядок работы и их не пересказывает. Закон строгости — `main.mdc` § Принципы и § Запреты: костыль хуже явной ошибки, «потом отрефакторим» не бывает, фолбек на пустое значение вместо `throw` — баг.

## 1. Прочитать перед правкой

| Задача | Что открыть |
|---|---|
| любая правка UI | `.cursor/rules/frontend.mdc`, правило домена сервиса (`crm.mdc`, `sync.mdc`, `flows.mdc`, `flow_ui.mdc`, `office.mdc`, `wiki.mdc`, `worktracker.mdc`, `stock.mdc`, `voice.mdc`, `mail.mdc`) |
| состояние, команда, push | `.cursor/rules/ui_factories.mdc`, `.cursor/rules/events.mdc`, `.cursor/rules/architecture.mdc` § REST-зеркало и § WS request-reply |
| модалка, sheet, навигация, крошки, core-компонент | `.cursor/rules/ui_components.mdc` + UIKDS-док компонента `docs/scenarios/platform/ui-kit/<tag>/` |
| поле формы | `.cursor/rules/ui_fields.mdc` |
| визуал, CSS, Figma | [`references/design-standard.md`](.cursor/skills/frontend-engineer/references/design-standard.md) + [`tokens.css`](core/frontend/static/assets/css/tokens.css) |
| AI-провайдеры и модели в UI | `.cursor/rules/ai_models.mdc` § UI |

Код-источник (читать перед нетривиальной правкой): [`platform-element/index.js`](core/frontend/static/lib/platform-element/index.js) — helpers; [`base/PlatformApp.js`](core/frontend/static/lib/base/PlatformApp.js) — статические поля SPA; [`base/use-resource.js`](core/frontend/static/lib/base/use-resource.js) — контроллеры; [`events/factories/`](core/frontend/static/lib/events/factories/) — JSDoc-контракт опций каждой фабрики; [`events/contract.js`](core/frontend/static/lib/events/contract.js) — `CoreEvents`.

## 2. Выбрать инструмент

1. Доменные данные — всегда фабрика; поле компонента под данные домена не заводим.
2. Какая фабрика:
   - список сущностей с CRUD → `createResourceCollection`;
   - лента больше одной страницы, курсор, фильтры → `createCursorList`;
   - одиночная команда, загрузка одного объекта, действие → `createAsyncOp`;
   - typeahead по фасетам → `createFacets`;
   - форма с валидацией → `createForm` с `submitEvent` на операцию или коллекцию;
   - состояние без сети (overlay, presence, push-only) → `createSlice`.
3. Кейс не ложится — комбинация фабрик; седьмую фабрику и локальный store не пишем, пробел канона закрываем правкой правила.
4. Транспорт: сервис из `COMMAND_WS_SERVICES` (`scripts/check_command_rest_mirror.py`) → `transport: 'ws'` + `wsTimeoutMs` + `restMirror`; имя фабрики ≠ backend-команде → `commandType`. HTTP — только если фабрика в `COMMAND_WS_HTTP_ALLOWLIST` или сервис вне `COMMAND_WS_SERVICES`.
5. UI-примитив — сначала core UI Kit (`ui_components.mdc` § Один компонент на задачу, [`core/frontend/static/lib/components/`](core/frontend/static/lib/components/)); не хватает возможности — расширяем core-компонент, а не пишем свой в сервисе.
6. Поле — `<platform-field>`; сырой тег — только по whitelist `ui_fields.mdc`.

## 3. Порядок реализации

1. Backend-контракт: команда `<svc>/<entity>/<verb>_requested` в `<SVC>_OPERATIONS` и REST-зеркало, push — `register_platform_event` (скил `backend-engineer`, `architecture.mdc` § Новая команда).
2. Фабрика в `apps/<svc>/ui/events/resources/<entity>.resource.js` (кросс-сервисная — `core/frontend/static/lib/events/resources/`) → [`recipes.md`](.cursor/skills/frontend-engineer/recipes.md) § 1–6.
3. Ключи i18n парой `ru`/`en`: toast, подписи, `routes.<key>`, `bottom_nav.<key>` → recipes § 12.
4. Регистрация фабрики в `static factories` `<svc>-app.js`, маршрут с `titleKey`.
5. Страница, модалка, компонент: база, `use*` по имени, helpers, `<platform-field>`, `<platform-breadcrumbs>` → recipes § 7–10.
6. Push и исходы мутаций — мерж в `extraReducer`/`extraEffect` фабрики, без reload в странице → recipes § 11.
7. Тесты: reducer — unit, контроллер — WTR; новый `platform-*` — UIKDS-карточка → recipes § 15.
8. Новый паттерн, компонент или конвенция — правка правила-владельца в том же изменении (`main.mdc` § Принципы, п.9).

## 4. Канон мешает

- Правило не даёт решить задачу честно — формулируем конфликт и правим правило в том же изменении, потом код. Обход в коде «пока» запрещён.
- Костыль прошёл CI — сначала детектор в `scripts/check_ui_canon.sh`, `scripts/check_ui_factories.py` или `scripts/check_core_frontend_canon.py` (скил `refactor-engineer`, режим `gate`), потом код, потом правило.
- Каталог типовых костылей и замен — [`anti-patterns.md`](.cursor/skills/frontend-engineer/anti-patterns.md).

## 5. Гейты перед «готово»

Порядок — от быстрых к медленным; любой красный — возврат к канону, не обход.

```bash
make check-ui-canon              # scripts/check_ui_canon.sh + check_flow_ui_hard_cut.py
make check-ui-factories          # name, baseUrl, toast-ключи ru+en, static factories
make check-command-rest-mirror   # restMirror ↔ FastAPI route, transport 'ws'
make check-core-frontend-canon   # зоны core/frontend/static/lib/**, embed ESM closure
make check-field-canon           # сырые input/textarea/select
make check-i18n                  # JSON бандлов, пары файлов ru/en
make check-i18n-keys             # каждый t('key') резолвится
uv run python scripts/report_ui_i18n_gaps.py --app <svc>   # отчёт: цель — 0 кириллицы в литералах
make check-events-canon          # сборная: все canon-гейты UI и событий
make lint-ts                     # check-events-canon + check_ui_kit_docs + field + logging
make ui                          # lint-ts + test-frontend-core (canon, Vitest, WTR incl. UI Kit L1)
```

- Правка core UI Kit или модалки — ещё `make test-ui-components`; UIKDS-сценарии и доки — `make ui-doc` (нужен `make test-up`).
- Изменение затрагивает Python — `make lint` целиком (`main.mdc` § Lint gate).

## 6. Визуальная проверка

1. Поднять стек: `make app` (mprocs, granian `--reload`; занятые порты — `make app APP_KILL=1`).
2. Открыть сервис: frontend `http://localhost:8002/`, flows `:8001/flows`, CRM `:8003/crm`, RAG `:8004/rag`, Sync `:8005/sync`, Documents `:8008/documents`, worktracker `:8021/worktracker`, wiki `:8023/wiki`, stock `:8026/stock`.
3. Desktop `1440x1024`; shell, страница или модалка — ещё mobile `390x844` или `430x932`. Нет overlap, горизонтального скролла, обрезанного текста; ритм — по [`references/design-standard.md`](.cursor/skills/frontend-engineer/references/design-standard.md).
4. Скриншоты до и после — в отчёте задачи.

## 7. Чек-лист «готово»

- [ ] Все команды § 5 зелёные.
- [ ] Каждый новый `t('key')` есть в `core/i18n/translations/ru/<ns>.json` и `en/<ns>.json`; динамических ключей нет.
- [ ] Каждая новая команда `_requested` имеет REST-зеркало; push не совпадает с командой по имени.
- [ ] Новая фабрика — уникальное `<svc>/<entity>`, в `static factories`; компонент берёт её по имени.
- [ ] Новая модалка или sheet — `modalKind`/`bottomSheetKind` + регистрация, открытие только helper-ом.
- [ ] Нет `||`/`??`-фолбеков, ручных `_busy`, `await this.dispatch`, reload по push в странице.
- [ ] Поля — `<platform-field>`; локальных `.form-*`/`.field-pill*` CSS нет.
- [ ] Утилиты — из `core/frontend/static/lib/utils/`; upload — `platform/file_create`; ключи localStorage — `platformStorageKey`.
- [ ] Визуал — токены и core-компоненты, без локальных hex/rgba; responsive sanity пройден.
- [ ] Новый `platform-*` имеет UIKDS-карточку в `tests/ui/design-system/components/<tag>/`.
- [ ] Новый паттерн отражён в правиле-владельце.

## 8. Отладка

- `?platform_devtools=1` в URL — лог каждого события в console и `window.__platformDevtools__ = { trail(), state(), dispatch(), clear() }` ([`events/devtools.js`](core/frontend/static/lib/events/devtools.js)); флаг runtime, в код и ссылки не попадает.
- `getFactory: factory "…" not registered` — фабрика не в `static factories` приложения, где её берёт `use*` (в тесте — не зарегистрирована после `clearFactoryRegistry()`); `has kind "…", expected "…"` — не тот helper (`useOp` на коллекцию).
- `i18n key required (format "namespace:key")` — toast-ключ без namespace (`requireI18nKey`).
- `restMirror is required when transport='ws'` — у WS-фабрики нет `restMirror`.
- `commandType … must end with "_requested"` — неверный тип WS-кадра.
- Шторм HTTP/WS после рендера — `run()` в `updated()`/`render()` без проверки `busy`/`error`/`lastResult`.
- Кнопка «создать» заблокирована при загрузке списка — дизейбл от `loading` вместо `createInFlight`.
- Пустое место вместо иконки — имя без ассета; прогнать `tests/frontend_core/unit/utils/ui-icon-assets.spec.js`.

## Файлы скила

- [`anti-patterns.md`](.cursor/skills/frontend-engineer/anti-patterns.md) — плохо → хорошо → детектор.
- [`recipes.md`](.cursor/skills/frontend-engineer/recipes.md) — пошаговые рецепты.
- [`references/design-standard.md`](.cursor/skills/frontend-engineer/references/design-standard.md) — Figma → tokens.css.

# Frontend Anti-Patterns — плохо → хорошо → детектор

Каждая запись — типовой костыль, единственная замена и детектор. «п.N» — пункт `scripts/check_ui_canon.sh`. Детектора нет — сначала добавь его (скил `refactor-engineer`, режим `gate`), потом правь код. Нормы — в `.cursor/rules/frontend.mdc`, `ui_factories.mdc`, `ui_components.mdc`, `ui_fields.mdc`.

## 0. Машинные сигнатуры (миграционный режим)

Детекторы миграции — правила `scripts/ui_canon_rules.py` (`rule_id`); гейт —
`check_ui_kit_canon.py` (hard-счётчики в `ui_canon_baseline.json`), очередь —
`report_ui_kostyli.py`. Карта `rule_id` → раздел этого файла:

| rule_id | severity | раздел/замена |
|---|---|---|
| `ui_js_files` | hard | миграция .js → .ts (recipes §16) |
| `fetch_outside_events` | hard | § 2 HTTP мимо фабрики |
| `window_dialogs` | hard | § 3 → `platformConfirm` |
| `createelement_modal` | hard | § 3 → `this.openModal` |
| `localstorage_raw` | hard | § 1 → `platformStorageKey` |
| `vendored_lit_path` | hard | § 1 → `from 'lit'` |
| `vendored_dep_path` | hard | § 1 → `from 'marked'/'centrifuge'` |
| `extends_native` | hard | § 1 → `PlatformElement`/`PlatformPage`/`PlatformModal` |
| `custom_primitive` | hard | kit-примитив или kit-gap (§ цикл migration-loop) |
| `raw_controls` | hard | `<platform-field>` (`ui_fields.mdc`) |
| `manual_pill` | hard | `<platform-field-shell>` / `<platform-field>` |
| `raw_dispatch_events` | hard | § 3 → helpers базы |
| `window_custom_event` | hard | EventBus/фабрики |
| `hex_colors` | soft | tokens.css |
| `innerhtml_raw` | soft | html``/unsafeHTML с явной причиной |
| `setinterval_poll` | soft | push/фабрика |
| `window_listeners` | soft | helpers/EventBus |
| `manual_busy_state` | soft | useOp/createForm |

## 1. Базы, импорты, геттеры

| Плохо | Хорошо | Детектор |
|---|---|---|
| `class MyPage extends LitElement` / `extends HTMLElement` | `extends PlatformPage` (`PlatformElement`, `PlatformModal`) | п.1, `scripts/check_core_frontend_canon.py` |
| `import … from '/static/core/lib/…'` | `import … from '@platform/lib/…'` | п.2 |
| `import { syncX } from '../../../sync/ui/components/…'` в flows | общий модуль в `core/frontend/static/lib/` | нет |
| `this.services.api.get(…)`, `this.notify.toast(…)`, `this.team` | фабрика + `this.toast(…)`; команда — `use*` | п.6 (apps), п.11 (core) |
| `ServiceRegistry`, `BaseStore`, `AppEvents`, Zustand | фабрика + helper базы | п.3, п.4 |
| `this.bus.getState().frontendApiKeys.items` | `this.useResource('frontend/api_keys').items` или `this.select(…)` | п.14 |
| `this.i18n.t(…)`, `this.i18n.getCurrentLocale()` | `this.t(…)`, `this.select((s) => s.i18n.locale)` | п.14 |
| `import { I18nNs } …; static i18nNamespace = I18nNs.FRONTEND` | `static i18nNamespace = 'frontend'` или `defaultI18nNamespace` приложения | п.13 |

## 2. HTTP и состояние мимо фабрики

```js
// плохо: состояние в полях страницы, fetch в компоненте
async firstUpdated() { this._items = await (await fetch('/frontend/api/api-keys')).json(); this.requestUpdate(); }
// хорошо
constructor() { super(); this._keys = this.useResource('frontend/api_keys', { autoload: true }); }
```
Детектор: п.7 (`fetch`); поле-состояние — нет.

```js
// плохо: псевдо-slice на push
this.useEvent(CRM_NOTE_CREATED, (e) => { this._notes.push(e.payload.note); this.requestUpdate(); });
// хорошо: extraReducer фабрики crm/notes
extraReducer: (state, event) => event.type === CRM_NOTE_CREATED ? upsertItem(state, event.payload.note, 'entity_id') : state,
```
Детектор: нет (reload ловит `_check_push_reload`, локальный массив — нет).

| Плохо | Хорошо | Детектор |
|---|---|---|
| `getServiceSlices() { return { mySlice: { reducer, initial } }; }` | фабрика в `static factories` | нет |
| `apps/<svc>/ui/services/`, `store/`, `stores/` | фабрики в `events/resources/` | п.8 |
| `apps/<svc>/ui/events/effects/`, `events/reducers/`, `events/selectors.js` | логика в фабрике; связка с core — bridge-effect `events/<svc>-*.effect.js` | п.13 (`events/effects`), остальное — нет |
| `new WebSocket(…)` + `ws.send({ type: '…_requested' })` для команды | фабрика `transport: 'ws'` + `commandType` | `scripts/check_core_frontend_canon.py` (core), apps — нет |
| `apps/<svc>/ui/components/*-trace-tree.js`, свой span waterfall | `<platform-trace-viewer>` ([`platform-trace-viewer.js`](core/frontend/static/lib/components/platform-trace-viewer.js)) | нет |
| своя `.log-entry` таблица | `<platform-log-viewer>` ([`platform-log-viewer.js`](core/frontend/static/lib/components/platform-log-viewer.js)) | нет |

## 3. Прямой dispatch и модалки

| Плохо | Хорошо | Детектор |
|---|---|---|
| `this.dispatch(CoreEvents.UI_TOAST_SHOW, { type, i18n_key })` | `this.toast('foo.bar', { type: 'error' })` | п.13 (pages/modals) |
| `this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey, params, search })` | `this.navigate('channel', { channelId }, { search: '?focus=…' })` | п.13 |
| `this.dispatch(CoreEvents.UI_CLIPBOARD_COPY_REQUESTED, …)` | `this.copyToClipboard(text, { success_i18n_key, error_i18n_key })` | п.13 |
| `this.dispatch(CoreEvents.THEME_SET_REQUESTED, …)`, `AUTH_COMPANY_SWITCH_REQUESTED` | `this.setTheme('dark')`, `this.switchCompany(company_id)` | нет |
| `document.createElement('x-modal'); document.body.appendChild(m); m.open = true` | `this.openModal(XModal, props)` | п.9 |
| `this.open = false` в модалке формы | `this.closeAfterSave()`; снаружи — `this.closeModal('<scope>.<entity>')` | п.9 |
| `super.showModal()` | модалку открывает стек: `this.openModal(kind)` снаружи | п.14 |
| `window.confirm('Удалить?')` | `await platformConfirm(this.t('foo.confirm_delete'), { variant: 'danger', … })` | нет |
| `window.dispatchEvent(new CustomEvent('open-modal', …))` | `this.openModal(…)` | п.5 (apps) |

## 4. Фолбеки

```js
// плохо
const items = (this._keys && this._keys.items) || [];
extraReducer: (state, event) => ({ ...state, last: event.payload || {} }),
// хорошо: initialSlice гарантирует массив, невалидный push отбрасывается явно
const items = this._keys.items;
extraReducer: (state, event, events) => {
    if (event.type !== events.CREATED) return state;
    const item = event.payload.item;
    if (!item || typeof item.key_id !== 'string') return state;
    return { ...state, last: item };
},
```
Детектор: п.15 (`*.resource.js`), `scripts/check_core_frontend_canon.py` (core reducers и factories); pages, modals, components — нет.

```js
// плохо: тихий catch
request: async () => { try { return await httpRequest({ url, method: 'GET' }); } catch { return []; } },
// хорошо: HttpError уходит в *_failed фабрики, прочая ошибка всплывает
request: async () => httpRequest({ url, method: 'GET' }),
```
Детектор: нет.

| Плохо | Хорошо | Детектор |
|---|---|---|
| `search(facet, q) { const query = q \|\| ''; }` в контроллере | `if (typeof q !== 'string') throw new Error('search: q required')` | нет |
| `space.space_id \|\| space.id` в странице | helper `apps/<svc>/ui/_helpers/<svc>-id-resolvers.js` | нет |
| `created_at: raw.created_at \|\| new Date().toISOString()` в `mapItem` | обязательное поле отсутствует — `throw` | нет |
| «временно вернём пустой список» / `// TODO` | `throw new Error('not implemented: …')`, причина чинится | нет |

## 5. Команды, ожидание, гонки

```js
// плохо: ручной busy
async _onCreate() { if (this._busy) return; this._busy = true; try { await this._op.run(p); } finally { this._busy = false; } }
// хорошо
render() { return html`<platform-button ?disabled=${this._op.busy} @click=${() => this._op.run(p)}>…</platform-button>`; }
```
Детектор: нет.

```js
// плохо: fake await и цепочка без id
await this.dispatch('crm/notes/create_requested', { text });
this._entities.create(task); this._relationships.create({ to_entity_id: '???' });
// хорошо
const result = await this._createNote.run({ text });
if (this._createNote.error) return;
const created = await this._createEntity(task);   // recipes.md § 3
await this._createRelationship({ from_entity_id: noteId, to_entity_id: created.entity_id, relationship_type: 'has_task' });
```
Детектор: п.14 ловит только `await (this.dispatch(...))`; цепочка — нет.

```js
// плохо: чужой ответ перезаписывает свежий результат
this.useEvent('crm/note_search/succeeded', (e) => { this._results = e.payload.result.items; });
// хорошо
this.useEvent(this._search.op.events.SUCCEEDED, (e) => {
    if (e.meta.causation_id !== this._search.lastRequestId) return;
    this._results = e.payload.result.items;
});
```
Детектор: нет.

| Плохо | Хорошо | Детектор |
|---|---|---|
| `?disabled=${this._items.loading}` у кнопки «создать» | `?disabled=${this._items.createInFlight}` | нет |
| `this._entities.create(p).id` без проверки | `requested` — `undefined` при `createInFlight`: проверить `typeof requested.id === 'string'` | нет |
| `bus.subscribeType(CREATED, …)` без снятия подписки | снять обе подписки при первом совпадении `causation_id` (recipes.md § 3) | нет |
| `updated() { this._load.run(); }` | старт в `connectedCallback` или по действию; в `updated()` — только по смене свойства и с проверкой `busy`/`lastResult` | нет |
| `try { await runViaWs(p) } catch { await runViaHttp(p) }` | один транспорт фабрики; обрыв — `GET /realtime/api/v1/events/{event_id}/terminal` | нет |
| WS-фабрика без `restMirror` | `restMirror: { method, path }` на FastAPI route | runtime `throw`, `scripts/check_command_rest_mirror.py` |
| `commandType: 'sync/calls/invite'` | `commandType: 'sync/calls/invite_requested'` | runtime `throw` |
| push `sync/messages/send` при команде `sync/messages/send_requested` | другое entity: `sync/message/created` | нет |

## 6. Push и перезагрузка

```js
// плохо: страница перезагружает коллекцию на push
this.useEvent(CRM_NOTE_UPDATED, () => this._notes.load());
// хорошо: фабрика мержит; страница реагирует только UI
extraReducer: (state, event) => event.type === CRM_NOTE_UPDATED ? upsertItem(state, event.payload.note, 'entity_id') : state,
```
Детектор: `scripts/check_platform_events_canon.py` (`_check_push_reload`).

| Плохо | Хорошо | Детектор |
|---|---|---|
| `useEvent(WS_CONNECTED, () => this._tasks.load())` в странице | `extraEffect` фабрики на `CoreEvents.WS_CONNECTED` → `reloadLastList(ctx, resource)` | `_check_push_reload` |
| `useEvent(NS_UPDATE_SUCCEEDED, () => this._graph.run(q))` | `onSuccess: (ctx) => rerunLastRequest(ctx, graphOp, { when })` | `_check_push_reload` |
| литерал `'crm/task/updated'` в странице | константа `CRM_TASK_UPDATED` из `../events/types.js` | `scripts/check_platform_events_canon.py` |

## 7. Имена, i18n, toast

| Плохо | Хорошо | Детектор |
|---|---|---|
| `this.dispatch('foo/bar', …)`, `'Foo/Bar/Baz'`, `'foo-bar/baz/qux'` | `'crm/note/created'` — ≥3 сегмента snake_case | п.12, `assertEventType` |
| `name: 'crm.notes.create'`, `'notes/create'` | `name: 'crm/note_create'` | `scripts/check_ui_factories.py`, `assertResourceName` |
| `successToastKey: 'foo.bar'` | `'frontend:foo.bar'` | `scripts/check_ui_factories.py`, `requireI18nKey` |
| `this.t('foo.' + status)` | `status === 'forbidden' ? this.t('foo.forbidden') : …` + `throw` на неизвестном | нет (`check_i18n_keys.py` пропускает динамику) |
| `html\`<button>Сохранить</button>\`` | `this.t('action_save', null, 'common')` + ключи ru/en | `scripts/report_ui_i18n_gaps.py` (отчёт) |
| ключ только в `ru/<ns>.json` | тот же ключ в `en/<ns>.json` | toast — `check_ui_factories.py`, прочие — нет |

## 8. Поля форм

| Плохо | Хорошо | Детектор |
|---|---|---|
| `<input type="text" class="form-input">` | `<platform-field type="string" input-type="email">` | `scripts/check_field_canon.sh` |
| `<textarea>` без `data-canon` | `<platform-field type="text">` или `<platform-markdown-editor>` | `scripts/check_field_canon.sh` |
| `<select>` для enum | `<platform-field type="enum" .config=${{ values }}>` | `scripts/check_field_canon.sh` |
| `import '@platform/lib/components/glass-input.js'` | `<platform-field>` | п.18 |
| `css\`.form-input { … } .field-pill { … }\`` в `apps/**` | токены `--field-pill-*` в `tokens.css` | п.17 |
| `.config=${{ values: ['flow_a', 'flow_b'] }}` для id | `values: [{ value: 'flow_a', label: 'Продажи' }]` | нет |
| `<div class="hint">${this.t('…')}</div>` под полем | `.hint=${this.t('…')}` у `<platform-field>` | нет |
| `<tag-input flat>` | pill-режим без атрибута | нет |
| `type="checkbox"` во flows UI | `platform-field type="boolean"` или `platform-segmented-control` | п.32 |

## 9. Утилиты и файлы

| Плохо | Хорошо | Детектор |
|---|---|---|
| `function escapeHtml(s) { … }` | `escapeHtml` из `@platform/lib/utils/escape-html.js` | п.19c |
| `const EMAIL_RE = /^[^\s@]+@…/`, `_digitsOnly(v)` | `isValidEmail`, `digitsOnly` из `@platform/lib/utils/validators.js` | п.19b |
| `h = (h * 31 + s.charCodeAt(i))` | `hashString31`, `hueFromString` из `@platform/lib/utils/hash-string.js` | п.19d |
| `new Intl.NumberFormat('ru-RU')`, `toLocaleDateString('ru-RU')` | `formatPlatformNumber(v, locale)`, `formatPlatformDate(v, locale)` с `state.i18n.locale` | п.19a |
| `globalThis.marked`, `<script src="…/marked.js">` | `markdownToHtml` из `@platform/lib/utils/markdown.js` | п.19c-2 |
| `localStorage.setItem('sync.chat.draft', …)` | `platformStorageKey('sync', 'chat_draft')` | нет |
| свой `createAsyncOp` с `FormData` для файла, `name: 'sync/file_upload'` | `useOp('platform/file_create')` → chunked `uploadPlatformFile` (`createPlatformFileCreateOp`) | `scripts/check_files_canon.py`, `scripts/check_files_ui_canon.sh` |

## 10. Визуал, shell, core-компоненты

```css
/* плохо: копия Figma CSS-export */
.daily-summary { background: rgba(153, 166, 249, 0.2); border-radius: 16px; padding: 20px; }
.tag-orange { background: #FF885C; }
/* хорошо: semantic tokens */
.daily-summary { background: var(--crm-summary-bg); border: 1px solid var(--crm-summary-stroke); border-radius: var(--radius-lg); padding: var(--space-5); }
.tag-orange { background: var(--crm-note-related-orange-bg); }
```
Детектор: п.23 (только flows UI); остальное — нет. Карта Figma → токены — `references/design-standard.md`.

| Плохо | Хорошо | Детектор |
|---|---|---|
| `transition: all 0.2s` | `transition: var(--motion-transition-interactive)` | п.0 |
| `@keyframes spin` в сервисе | `<platform-spinner>` | п.34 |
| `position: fixed` + свой расчёт координат, `z-index: 9999` у dropdown | `<platform-popover>` / `<platform-menu>` | нет |
| `customElements.define('crm-mobile-app-header', …)`, гамбургер | `static bottomNavItems` + `<platform-top-bar>` | п.20 (header), гамбургер — нет |
| `<platform-bottom-nav>` в разметке сервиса | статические поля `PlatformApp`, рендер — `PlatformApp.render()` | п.20 |
| `<sync-user-row>`, `<crm-user-avatar>`, `${user_id}` в таблице | `<platform-user-chip user-id=${id}>` | нет |
| своя модалка профиля | `this.openModal('platform.user_info', { userId })` | нет |
| `user.companies[0].roles.includes('admin')` | `state.auth.user.canAdmin` из `GET /auth/me` | нет |
| hero-секция на рабочей странице | workspace: `<page-header>`, фильтры, список, панель действий | нет |
| `<svg>` inline в странице | `<platform-icon name="…">`; бренд — `colored` | `tests/frontend_core/unit/utils/ui-icon-assets.spec.js` |
| локальный provider allowlist, `fallback_models` как `string[]` | typed catalog backend, `LLMCallConfig[]` в том же редакторе → `ai_models.mdc` § UI | нет |

## 11. Тесты

| Плохо | Хорошо | Детектор |
|---|---|---|
| второй тест падает `registerFactory: … already registered` | `beforeEach`: `clearFactoryRegistry()`, `_resetResourceRegistryForTests()`, `resetPlatformBusForTests()` | нет |
| `vi.spyOn(factory, 'reducer')` | reducer — чистая `(state, event) => state`; effect — фейковый `ctx` | нет |
| `document.body.appendChild(el)` без очистки | `fixture` Web Test Runner | нет |

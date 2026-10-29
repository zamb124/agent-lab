# Frontend Anti-Patterns — плохо → хорошо → детектор

Каждая запись — класс нарушения, единственная замена и детектор. «п.N» — пункт `scripts/gates/frontend/ui_canon.sh`; `rule_id` — правило `scripts/gates/frontend/ui_canon_rules.py`; «проба» — секция `.cursor/skills/frontend-engineer/scripts/ui_audit.py`. «Нет» — детектора нет: первым шагом среза он добавляется (`references/loop.md` § Детектор). Детектор, который проба «Слепота» отмечает слепым, не защищает: сначала `references/playbooks.md` § Слепой гейт → зрячий. Нормы — `frontend.mdc`, `ui_factories.mdc`, `ui_components.mdc`, `ui_fields.mdc`; эталон — `references/target-architecture.md`.

## 0. Машинные сигнатуры

| rule_id или проба | severity | Раздел |
|---|---|---|
| `ts_controller_cast` | hard | § 1 |
| `ts_explicit_any`, `ts_type_assertion`, `ts_double_cast`, `ts_non_null_assertion` | soft | § 1 |
| `ts_silent_catch`, `ts_console`, проба «Скрытое» | soft, — | § 2 |
| проба «Конвейер», «Слепота» | — | § 3 |
| `vendored_lit_path`, `vendored_dep_path`, проба «Мосты» | hard, — | § 4 |
| `ui_js_files` | hard | § 5 |
| `extends_native` | hard | § 6 |
| `fetch_outside_events` | hard | § 7 |
| `window_dialogs`, `createelement_modal`, `raw_dispatch_events`, `window_custom_event` | hard | § 8 |
| `ts_literal_fallback` | soft | § 9 |
| `manual_busy_state` | soft | § 10 |
| `setinterval_poll`, `window_listeners` | soft | § 11 |
| `raw_controls`, `manual_pill` | hard | § 13 |
| `localstorage_raw` | hard | § 14 |
| `custom_primitive`, `hex_colors`, `innerhtml_raw` | hard, soft, soft | § 15 |

## 1. Типы

| Плохо | Хорошо | Детектор |
|---|---|---|
| `(flow: any)`, `Record<string, any>`, `any[]` | тип элемента или результата фабрики; `unknown` сужается только на границе | `ts_explicit_any` |
| `this.useSlice('crm/daily_notes_ui') as CrmDailyNotesUiController` | тип контроллера выводится из имени: `use*` по `PlatformFactoryRegistry` | `ts_controller_cast` |
| `interface XController extends SliceController { value: XSlice \| undefined; doX: (p?: unknown) => void }` | `ControllerFor<'<svc>/<entity>'>`; `S` — аннотация `state` в `extraReducer` | `tsc` (`value` без `undefined`, payload действия обязателен) |
| `(this._x.doX as (...args: any[]) => any)()` | `this._x.doX(null)` — действие типизировано по `actions` фабрики | `ts_explicit_any` |
| фабрика объявлена без блока `declare module '@platform/lib/events/factory-registry.js'` | запись `'<svc>/<entity>': typeof <factory>` в `PlatformFactoryRegistry` | `tsc` |
| `(event.payload as Record<string, any>).item` | payload из карты событий по литералу типа | `ts_type_assertion` |
| `value as unknown as Foo` | тип чинится в источнике потери (фабрика, контроллер, транспорт) | `ts_double_cast` |
| `this._authSel.value!`, `doc.file_id!`, `queue.shift()!` | тип без `null` в контракте или явный `throw` на отсутствии | `ts_non_null_assertion` |
| `interface TemplateRow { … }` в странице при той же форме у backend | `import type { … } from '../events/wire.gen.js'` (`references/playbooks.md` § Wire-типы из Pydantic) | нет |
| `interface ResourceItem { [key: string]: unknown }` как тип элемента | generic `TItem` | нет |
| `(event.target as HTMLInputElement).value` | `if (!(event.target instanceof HTMLInputElement)) throw new Error('…')`; событие kit — `CustomEvent<{ value: T }>` из `HTMLElementEventMap` | `ts_type_assertion` |
| `(this.constructor as PlatformAppCtor).factories` | типизированное статическое поле базы и `static override` наследника | `ts_type_assertion` |
| `// @ts-ignore`, `// @ts-expect-error`, `// @ts-nocheck`, `// eslint-disable` | честный тип; не типизируется — корень в kit | нет |

## 2. Замалчивание

```ts
// плохо: ошибка исчезает, работа продолжается в другом режиме
try { stream = await getUserMedia(constraints); } catch { stream = await getUserMedia({ audio: true }); }
try { this._ws.close(); } catch { /* noop */ }

// хорошо: конкретный класс → проброс с причиной; teardown по состоянию
try {
    stream = await navigator.mediaDevices.getUserMedia(constraints);
} catch (err) {
    if (err instanceof DOMException) throw new Error(`microphone unavailable: ${err.name}`, { cause: err });
    throw err;
}
if (this._wsState === 'open') this._ws.close(1000, 'client_close');
```
Детектор: `ts_silent_catch`.

| Плохо | Хорошо | Детектор |
|---|---|---|
| `try { new URL(raw) } catch { return null }` | `URL.canParse(raw)` и явная ветка; невалидный конфиг — `new URL` без `try` | `ts_silent_catch` |
| `try { node.disconnect() } catch { /* noop */ }` при teardown, `try { ctx.close() } catch {}` | вызов без `try` (идемпотентные DOM/Web Audio вызовы не бросают); асинхронный `close()`/`resume()` — `.catch` с событием `error` и guard по `state` | `ts_silent_catch` |
| `try { stop() } catch {}` перед следующим шагом завершения | `try { … } finally { следующий шаг }`: все шаги выполняются, первая ошибка не теряется | `ts_silent_catch` |
| `try { storage.getItem } catch { return null }` | `catch (err)` только `DOMException` `SecurityError`, остальное `throw err` | `ts_silent_catch` |
| `try { return await response.json() } catch { return null }` для тела отказа | чтение `text()`; JSON — по первому символу `{`/`[` и `JSON.parse` без `try` (как у успешного ответа) | `ts_silent_catch` |
| `catch {` вокруг `JSON.parse` пользовательского текста | `catch (err)`: `SyntaxError` — ошибка поля, остальное `throw err` | `ts_silent_catch` |
| `catch {` вокруг `OpController.run()` | `run()` не reject'ит: `error !== null` → `throw`; пустой ответ не подменяет результат. `failureStatus === 404` страница показывает как «не найдено» | `ts_silent_catch` |
| `console.warn('… failed', err)` и продолжение | `throw` или `*_FAILED` фабрики; диагностика — `?platform_devtools=1` | `ts_console` |
| effect бросил → событие без потребителя, операция `busy` навсегда | `*_FAILED` операции по `causation_id` + видимая ошибка (`references/playbooks.md` § Ошибка эффекта) | нет |
| сервис отдаёт `ui/`, когда нет `ui-dist` | старт падает с подсказкой `make ui-build` | проба «Конвейер» |
| `function stringOr(value: unknown, fallback: string)` | контракт значения в источнике; отсутствие — `throw` | нет |
| `s.calendar \|\| {}`, `select.value \|\| initialSlice` | `PlatformBusState`: core-слайс есть всегда; `value` до подключения бросает | `ts_literal_fallback` |
| `(event.payload \|\| {})` | `payloadFields`: `null` — событие без полей; не-объект — `throw` | `ts_literal_fallback` |
| `// ui-canon: allow <rule>`, `exempt_in_embed_closure` | исправить код или сигнатуру детектора; принципиальное — `Исключение:` в правиле-владельце | проба «Скрытое» |
| находка не попала в отчёт как «мелочь» | раздел отчёта «Найдено и не исправлено» | — |

## 3. Слепой контроль

| Плохо | Хорошо | Детектор |
|---|---|---|
| гейт ищет маску `*.<kind>.js`, на диске `*.<kind>.ts` | маска на `.ts` + падение при пустом наборе | проба «Слепота» |
| `if path.suffix not in {".py", ".js", ".md"}` | набор с `.ts` | проба «Слепота» |
| `FILES = ("<entity>.resource.js", …)` → пустой `glob` → `continue` | фактические имена; пустой набор — падение | проба «Слепота» |
| гейт требует `apps/<svc>/ui/pages/<page>.js`, файл — `.ts` | путь `.ts` | проба «Слепота» |
| `js_or_ts(path)`: «есть `.js` — он, иначе `.ts`» | путь как есть | проба «Мосты» |
| метрика долга только в отчёте | hard-правило + baseline (`references/playbooks.md` § Метрика → ratchet) | — |
| `tsc` только в `make ui` | `tsc` в `make lint-ts` и в Docker `ui-builder` | проба «Конвейер» |
| правило или скил ссылается на `….js`, которого нет | путь as-is | проба «Слепота», `rules_drift.py` |

## 4. Мосты и дубли источников

| Плохо | Хорошо | Детектор |
|---|---|---|
| `import { LitElement } from '../../assets/js/lit/lit.min.js'`, реэкспорт через `lit-shim.ts` | `import { LitElement } from 'lit'` | `vendored_lit_path`, проба «Мосты» |
| плагин сборки переписывает vendored-пути на npm | импорт npm напрямую, плагин удалён | проба «Мосты» |
| `<script type="importmap">` в `index.html` при бандле | удалён | проба «Мосты» |
| WTR грузит vendored `lit.min.js`, прод — npm `lit` | один npm `lit` | лог WTR `Multiple versions of Lit loaded` |
| `tsSiblingMiddleware`, `plugin.resolveImport = undefined`, `jsToTsSibling` | тесты на `.ts`, штатный резолв раннера | проба «Мосты» |
| фолбек точки входа `index.ts \| index.js` | одна точка входа `index.ts` | проба «Мосты» |
| codemod миграции остался в `scripts/` после миграции | удалён | нет |

## 5. TS и Lit

| Плохо | Хорошо | Детектор |
|---|---|---|
| UI-файл `.js` | `.ts` (`recipes.md` § 16) | `ui_js_files` |
| `static override properties = { count: { type: Number } }; count = 0;` | `declare count: number;` + присваивание в `constructor()`: инициализатор при `useDefineForClassFields` глушит accessor Lit | нет |
| декоратор `@property()` | `static override properties` + `declare` | нет |
| `import { Foo } from` для типа | `import type { Foo }` | `tsc` (`verbatimModuleSyntax`) |
| `import './x.ts'`, импорт без расширения | `import './x.js'` для файла `x.ts` | нет |

## 6. Базы, импорты, геттеры

| Плохо | Хорошо | Детектор |
|---|---|---|
| `class MyPage extends LitElement` / `extends HTMLElement` | `extends PlatformPage` (`PlatformElement`, `PlatformModal`) | `extends_native`, п.1, `scripts/gates/frontend/core_frontend_canon.py` |
| `import … from '/static/core/lib/…'` | `import … from '@platform/lib/…'` | п.2 |
| `import { syncX } from '../../../sync/ui/components/…'` во flows | общий модуль в `core/frontend/static/lib/` | `scripts/gates/backend/cross_service_imports.py` (Python), UI — нет |
| `this.services.api.get(…)`, `this.notify.toast(…)`, `this.team` | фабрика + `this.toast(…)`; команда — `use*` | п.6, п.11 |
| `ServiceRegistry`, `BaseStore`, `AppEvents`, Zustand | фабрика + helper базы | п.3, п.4 |
| `this.bus.getState().frontendApiKeys.items` | `this.useResource('frontend/api_keys').items` или `this.select(…)` | п.14 |
| `this.i18n.t(…)`, `this.i18n.getCurrentLocale()` | `this.t(…)`, `this.select((s) => s.i18n.locale)` | п.14 |
| `import { I18nNs } …; static i18nNamespace = I18nNs.FRONTEND` | `static i18nNamespace = 'frontend'` или `defaultI18nNamespace` приложения | п.13 |
| `import { widgetsResource } from '../events/resources/widgets.resource.js'` в странице или sheet | фабрика по имени `this.useResource('<svc>/widgets')`; тип — `import type` | п.13 (pages, modals), `components/**` — нет |

## 7. HTTP и состояние мимо фабрики

```ts
// плохо: состояние в полях страницы, fetch в компоненте
override async firstUpdated(): Promise<void> {
    this._items = await (await fetch('/frontend/api/api-keys')).json();
}
// хорошо
private readonly _keys = this.useResource('frontend/api_keys', { autoload: true });
```
Детектор: `fetch_outside_events`, п.7; поле-состояние — нет.

```ts
// плохо: псевдо-slice на push
this.useEvent(CRM_NOTE_CREATED, (event) => { this._notes.push(event.payload.note); this.requestUpdate(); });
// хорошо: extraReducer фабрики crm/notes
extraReducer: (state, event) => (event.type === CRM_NOTE_CREATED ? upsertItem(state, event.payload.note, 'entity_id') : state),
```
Детектор: нет (reload ловит `_check_push_reload`, локальный массив — нет).

| Плохо | Хорошо | Детектор |
|---|---|---|
| `getServiceSlices() { return { mySlice: { reducer, initial } }; }` | фабрика в `static factories` | нет |
| `apps/<svc>/ui/services/`, `store/`, `stores/` | фабрики в `events/resources/` | п.8 |
| `apps/<svc>/ui/events/effects/`, `events/reducers/`, `events/selectors.ts` | логика в фабрике; связка с core — bridge-effect `events/<svc>-*.effect.ts` | п.13 (`events/effects`), остальное — нет |
| `new WebSocket(…)` + `ws.send({ type: '…_requested' })` для команды | фабрика `transport: 'ws'` + `commandType` | `scripts/gates/frontend/core_frontend_canon.py` (core), apps — нет |
| свой span waterfall, `*-trace-tree.ts` | `<platform-trace-viewer>` | нет |
| своя `.log-entry` таблица | `<platform-log-viewer>` | нет |

## 8. Прямой dispatch и модалки

| Плохо | Хорошо | Детектор |
|---|---|---|
| `this.dispatch(CoreEvents.UI_TOAST_SHOW, { type, i18n_key })` | `this.toast('foo.bar', { type: 'error' })` | `raw_dispatch_events`, п.13 |
| `this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, { routeKey, params, search })` | `this.navigate('channel', { channelId }, { search: '?focus=…' })` | `raw_dispatch_events`, п.13 |
| `this.dispatch(CoreEvents.UI_CLIPBOARD_COPY_REQUESTED, …)` | `this.copyToClipboard(text, { success_i18n_key, error_i18n_key })` | `raw_dispatch_events`, п.13 |
| `this.dispatch(CoreEvents.THEME_SET_REQUESTED, …)`, `AUTH_COMPANY_SWITCH_REQUESTED` | `this.setTheme('dark')`, `this.switchCompany(companyId)` | `raw_dispatch_events` |
| `document.createElement('x-modal'); document.body.appendChild(modal); modal.open = true` | `this.openModal(XModal, props)` | `createelement_modal`, п.9 |
| `this.open = false` в модалке формы | `this.closeAfterSave()`; снаружи — `this.closeModal('<scope>.<entity>')` | п.9 |
| `super.showModal()` | модалку открывает стек: `this.openModal(kind)` | п.14 |
| `window.confirm('Удалить?')` | `await platformConfirm(this.t('foo.confirm_delete'), { variant: 'danger', … })` | `window_dialogs` |
| `window.dispatchEvent(new CustomEvent('open-modal', …))` | `this.openModal(…)` | `window_custom_event`, п.5 |

## 9. Фолбеки

```ts
// плохо
const items = (this._keys && this._keys.items) || [];
extraReducer: (state, event) => ({ ...state, last: event.payload || {} }),
created_at: typeof raw.created_at === 'string' ? raw.created_at : new Date().toISOString(),

// хорошо: initialSlice гарантирует массив; невалидный push отбрасывается явно; обязательное поле — throw
const items = this._keys.items;
extraReducer: (state, event, events) => {
    if (event.type !== events.CREATED) return state;
    const item = event.payload.item;
    if (typeof item.key_id !== 'string') return state;
    return { ...state, last: item };
},
mapItem: (raw) => {
    if (typeof raw.created_at !== 'string') throw new Error('<svc>/widgets.mapItem: created_at required');
    // …
},
```
Детектор: `ts_literal_fallback`, п.15 (`*.resource.*`), `scripts/gates/frontend/core_frontend_canon.py` (core reducers и factories).

```ts
// плохо: тихий catch
request: async () => { try { return await httpRequest({ url, method: 'GET' }); } catch { return []; } },
// хорошо: HttpError уходит в *_failed фабрики, прочая ошибка всплывает
request: async () => httpRequest({ url, method: 'GET' }),
```
Детектор: `ts_silent_catch`.

| Плохо | Хорошо | Детектор |
|---|---|---|
| `search(facet, q) { const query = typeof q === 'string' ? q : ''; }` | `if (typeof q !== 'string') throw new Error('search: q required')` | `ts_literal_fallback` (частично) |
| `space.space_id \|\| space.id` в странице | helper `apps/<svc>/ui/_helpers/<svc>-id-resolvers.ts` | `ts_literal_fallback` (частично) |
| `${m.email \|\| ''}` в шаблоне | тип значения без `null` или явная ветка шаблона | `ts_literal_fallback` |
| «вернём пустой список», `// TODO` | `throw new Error('not implemented: …')` и причина чинится | нет |

## 10. Команды, ожидание, гонки

```ts
// плохо: ручной busy
private async _onCreate(): Promise<void> {
    if (this._busy) return;
    this._busy = true;
    try { await this._op.run(payload); } finally { this._busy = false; }
}
// хорошо
override render(): TemplateResult {
    return html`<platform-button ?disabled=${this._op.busy} @click=${() => this._op.run(payload)}>…</platform-button>`;
}
```
Детектор: `manual_busy_state`.

```ts
// плохо: fake await и цепочка без id
await this.dispatch('crm/notes/create_requested', { text });
this._entities.create(task); this._relationships.create({ to_entity_id: '???' });
// хорошо
const note = await this._createNote.run({ text });
if (note === null) return;
const created = await this._createEntity(task);          // recipes.md § 3
await this._createRelationship.run({ from_entity_id: note.entity_id, to_entity_id: created.entity_id, relationship_type: 'has_task' });
```
Детектор: п.14 ловит только `await (this.dispatch(...))`; цепочка — нет.

```ts
// плохо: чужой ответ перезаписывает свежий результат
this.useEvent('crm/note_search/succeeded', (event) => { this._results = event.payload.result.items; });
// хорошо
this.useEvent(this._search.op.events.SUCCEEDED, (event) => {
    if (event.meta.causation_id !== this._search.lastRequestId) return;
    this._results = event.payload.result.items;
});
```
Детектор: нет.

| Плохо | Хорошо | Детектор |
|---|---|---|
| `?disabled=${this._items.loading}` у кнопки «создать» | `?disabled=${this._items.createInFlight}` | нет |
| `this._entities.create(p).id` без проверки | `create()` возвращает `undefined` при `createInFlight`: проверить `typeof requested.id === 'string'` | нет |
| `bus.subscribeType(CREATED, …)` без снятия | снять обе подписки при первом совпадении `causation_id` (`recipes.md` § 3) | нет |
| `override updated(): void { this._load.run(); }` | старт в `connectedCallback` или по действию; в `updated()` — по смене свойства с проверкой `busy`/`lastResult` | нет |
| `try { await runViaWs(p) } catch { await runViaHttp(p) }` | один транспорт фабрики; обрыв — `GET /realtime/api/v1/events/{event_id}/terminal` | `ts_silent_catch` (частично) |
| WS-фабрика без `restMirror` | `restMirror: { method, path }` на FastAPI route | runtime `throw`, `scripts/gates/backend/command_rest_mirror.py` |
| `commandType: 'sync/calls/invite'` | `commandType: 'sync/calls/invite_requested'` | runtime `throw` |
| push `sync/messages/send` при команде `sync/messages/send_requested` | другое entity: `sync/message/created` | нет |

## 11. Push, перезагрузка, глобальные слушатели

```ts
// плохо: страница перезагружает коллекцию на push
this.useEvent(CRM_NOTE_UPDATED, () => this._notes.load());
// хорошо: фабрика мержит; страница реагирует только UI
extraReducer: (state, event) => (event.type === CRM_NOTE_UPDATED ? upsertItem(state, event.payload.note, 'entity_id') : state),
```
Детектор: `scripts/gates/backend/platform_events.py` (`_check_push_reload`).

| Плохо | Хорошо | Детектор |
|---|---|---|
| `useEvent(WS_CONNECTED, () => this._tasks.load())` в странице | `extraEffect` фабрики на `CoreEvents.WS_CONNECTED` → `reloadLastList(ctx, resource)` | `_check_push_reload` |
| `useEvent(NS_UPDATE_SUCCEEDED, () => this._graph.run(q))` | `onSuccess: (ctx) => rerunLastRequest(ctx, graphOp, { when })` | `_check_push_reload` |
| литерал `'crm/task/updated'` в странице | константа `CRM_TASK_UPDATED` из `../events/types.js` | `scripts/gates/backend/platform_events.py` |
| `setInterval(() => this._load.run(), 5000)` | push через фабрику; поллинг — только внешний источник без push, с причиной в коде | `setinterval_poll` |
| `window.addEventListener('keydown', …)` в компоненте сервиса | helper базы или core-компонент (`<platform-command-palette>`, `<platform-popover>`) | `window_listeners` |

## 12. Имена, i18n, toast

| Плохо | Хорошо | Детектор |
|---|---|---|
| `this.dispatch('foo/bar', …)`, `'Foo/Bar/Baz'`, `'foo-bar/baz/qux'` | `'crm/note/created'` — не меньше трёх сегментов snake_case | п.12, `assertEventType` |
| `name: 'crm.notes.create'`, `'notes/create'` | `name: 'crm/note_create'` | `scripts/gates/frontend/ui_factories.py`, `assertResourceName` |
| `successToastKey: 'foo.bar'` | `'frontend:foo.bar'` | `scripts/gates/frontend/ui_factories.py`, `requireI18nKey` |
| `this.t('foo.' + status)` | `status === 'forbidden' ? this.t('foo.forbidden') : …` + `throw` на неизвестном | нет (`check_i18n_keys.py` пропускает динамику) |
| `` html`<button>Сохранить</button>` `` | `this.t('action_save', null, 'common')` + ключи ru/en | `scripts/tools/report_ui_i18n_gaps.py` (отчёт) |
| ключ только в `ru/<ns>.json` | тот же ключ в `en/<ns>.json` | toast — `scripts/gates/frontend/ui_factories.py`, прочие — нет |

## 13. Поля форм

| Плохо | Хорошо | Детектор |
|---|---|---|
| `<input type="text" class="form-input">` | `<platform-field type="string" input-type="email">` | `raw_controls`, `scripts/gates/frontend/field_canon.sh` |
| `<textarea>` без `data-canon` | `<platform-field type="text">` или `<platform-markdown-editor>` | `raw_controls`, `scripts/gates/frontend/field_canon.sh` |
| `<select>` для enum | `<platform-field type="enum" .config=${{ values }}>` | `raw_controls`, `scripts/gates/frontend/field_canon.sh` |
| ручная `.field-pill`-разметка | `<platform-field-shell>` или `<platform-field>` | `manual_pill` |
| `import '@platform/lib/components/glass-input.js'` | `<platform-field>` | п.18 |
| `` css`.form-input { … } .field-pill { … }` `` в `apps/**` | токены `--field-pill-*` в `tokens.css` | п.17 |
| `.config=${{ values: ['flow_a', 'flow_b'] }}` для id | `values: [{ value: 'flow_a', label: this.t('…') }]` | нет |
| `<div class="hint">${this.t('…')}</div>` под полем | `.hint=${this.t('…')}` у `<platform-field>` | нет |
| `<tag-input flat>` | pill-режим без атрибута | нет |
| `type="checkbox"` во flows UI | `<platform-field type="boolean">` или `<platform-segmented-control>` | п.32 |

## 14. Утилиты и файлы

| Плохо | Хорошо | Детектор |
|---|---|---|
| `function escapeHtml(s: string) { … }` | `escapeHtml` из `@platform/lib/utils/escape-html.js` | п.19c |
| `const EMAIL_RE = /^[^\s@]+@…/`, `_digitsOnly(v)` | `isValidEmail`, `digitsOnly` из `@platform/lib/utils/validators.js` | п.19b |
| `h = (h * 31 + s.charCodeAt(i))` | `hashString31`, `hueFromString` из `@platform/lib/utils/hash-string.js` | п.19d |
| `new Intl.NumberFormat('ru-RU')`, `toLocaleDateString('ru-RU')` | `formatPlatformNumber(v, locale)`, `formatPlatformDate(v, locale)` с `state.i18n.locale` | п.19a |
| `globalThis.marked`, `<script src="…/marked.js">` | `markdownToHtml` из `@platform/lib/utils/markdown.js` | п.19c-2 |
| `localStorage.setItem('sync.chat.draft', …)` | `platformStorageKey('sync', 'chat_draft')` | `localstorage_raw` |
| свой `createAsyncOp` с `FormData`, `name: 'sync/file_upload'` | `useOp('platform/file_create')` → chunked `uploadPlatformFile` | `scripts/gates/files/files_canon.py`, `scripts/gates/files/files_ui_canon.sh` |

## 15. Визуал, shell, core-компоненты

```css
/* плохо: копия Figma CSS-export */
.daily-summary { background: rgba(153, 166, 249, 0.2); border-radius: 16px; padding: 20px; }
.tag-orange { background: #FF885C; }
/* хорошо: semantic tokens */
.daily-summary { background: var(--crm-summary-bg); border: 1px solid var(--crm-summary-stroke); border-radius: var(--radius-lg); padding: var(--space-5); }
.tag-orange { background: var(--crm-note-related-orange-bg); }
```
Детектор: `hex_colors`; п.23 — только flows UI. Карта Figma → токены — `references/design-standard.md`.

| Плохо | Хорошо | Детектор |
|---|---|---|
| `transition: all 0.2s` | `transition: var(--motion-transition-interactive)` | п.0 |
| `@keyframes spin` в сервисе | `<platform-spinner>` | п.34 |
| локальный `.btn { color: white; … }` в странице | `<platform-button>` или классы `buttonStyles` из `PlatformElement.styles` | нет |
| `customElements.define('<svc>-dropdown', …)` | kit-примитив; нет в kit — срез kit | `custom_primitive` |
| `position: fixed` + свой расчёт координат, `z-index: 9999` у dropdown | `<platform-popover>` / `<platform-menu>` | нет |
| `customElements.define('crm-mobile-app-header', …)`, гамбургер | `static bottomNavItems` + `<platform-top-bar>` | п.20 (header), гамбургер — нет |
| `<platform-bottom-nav>` в разметке сервиса | статические поля `PlatformApp`, рендер — `PlatformApp.render()` | п.20 |
| `<sync-user-row>`, `<crm-user-avatar>`, `${user_id}` в таблице | `<platform-user-chip user-id=${id}>` | нет |
| своя модалка профиля | `this.openModal('platform.user_info', { userId })` | нет |
| `user.companies[0].roles.includes('admin')` | `state.auth.user.canAdmin` из `GET /auth/me` | нет |
| hero-секция на рабочей странице | workspace: `<page-header>`, фильтры, список, панель действий | нет |
| `<svg>` inline в странице | `<platform-icon name="…">`; бренд — `colored` | `tests/frontend_core/unit/utils/ui-icon-assets.spec.js` |
| `element.innerHTML = html` | `html```, `unsafeHTML` после DOMPurify с причиной в коде | `innerhtml_raw` |
| локальный provider allowlist, `fallback_models: string[]` | typed catalog backend, `LLMCallConfig[]` в том же редакторе (`ai_models.mdc` § UI) | нет |

## 16. Тесты

| Плохо | Хорошо | Детектор |
|---|---|---|
| `*.spec.js` | `*.spec.ts` (`references/playbooks.md` § Тесты на TS) | `ui_js_files` |
| второй тест падает `registerFactory: … already registered` | `beforeEach`: `clearFactoryRegistry()`, `_resetResourceRegistryForTests()`, `resetPlatformBusForTests()` | нет |
| `vi.spyOn(factory, 'reducer')` | reducer — чистая `(state, event) => state`; effect — фейковый `ctx` | нет |
| `document.body.appendChild(el)` без очистки | `fixture` из `@open-wc/testing` | нет |
| тест на vendored Lit, прод на npm `lit` | один npm `lit` (`references/playbooks.md` § Один Lit) | лог WTR |

# Frontend Recipes — типовые сценарии end-to-end

Каждый рецепт = весь путь от файла фабрики до использования в компоненте + i18n + чек-лист. Цитирует каноничные примеры в репозитории.

См. также: [`SKILL.md`](.cursor/skills/frontend-engineer/SKILL.md), [`anti-patterns.md`](.cursor/skills/frontend-engineer/anti-patterns.md), правила в `.cursor/rules/`.

---

## 1. Новый CRUD-ресурс (createResourceCollection)

Каноничный пример: [`apps/frontend/ui/events/resources/api-keys.resource.js`](apps/frontend/ui/events/resources/api-keys.resource.js) + [`apps/frontend/ui/pages/api-keys/api-keys-page.js`](apps/frontend/ui/pages/api-keys/api-keys-page.js).

### Шаги

1. Создать `apps/<svc>/ui/events/resources/<entity>.resource.js`:

```js
import { createResourceCollection } from '@platform/lib/events/index.js';

export const myEntitiesResource = createResourceCollection({
    name: '<svc>/<entity>',                              // ровно 2 сегмента, lowercase snake_case
    baseUrl: '/<svc>/api/<entities>',                    // FastAPI route в apps/<svc>/api/**
    idField: 'entity_id',                                // имя поля id в модели
    operations: ['list', 'create', 'update', 'remove'],  // get опционально
    toastKeys: {
        create:        '<svc>:<entity>_modal.toast_created',
        create_error:  '<svc>:<entity>_modal.err_create_failed',
        update:        '<svc>:<entity>_page.toast_updated',
        remove:        '<svc>:<entity>_page.toast_removed',
    },
    mapItem: (raw) => {
        if (typeof raw.entity_id !== 'string') {
            throw new Error('<svc>/<entity>.mapItem: entity_id required');
        }
        return {
            entity_id: raw.entity_id,
            name: typeof raw.name === 'string' ? raw.name : '',
            tags: Array.isArray(raw.tags) ? raw.tags : [],
            created_at: typeof raw.created_at === 'string' ? raw.created_at : new Date().toISOString(),
        };
    },
});
```

2. Зарегистрировать в `apps/<svc>/ui/app/<svc>-app.js`:

```js
import { myEntitiesResource } from '../events/resources/<entity>.resource.js';

export class MyApp extends PlatformApp {
    static defaultI18nNamespace = '<svc>';
    static factories = [
        myEntitiesResource,
        /* ... */
    ];
}
```

3. Использовать на странице (`apps/<svc>/ui/pages/<entity>-page.js`):

```js
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';

export class MyEntitiesPage extends PlatformPage {
    constructor() {
        super();
        this._entities = this.useResource('<svc>/<entity>', { autoload: true });
    }

    _create(payload) {
        this._entities.create(payload);   // toast 'create' покажется автоматически по toastKeys.create
    }

    render() {
        if (this._entities.loading && this._entities.items.length === 0) {
            return html`<glass-spinner></glass-spinner>`;
        }
        return html`
            <button ?disabled=${this._entities.createInFlight} @click=${() => this.openModal(MyEntityCreateModal)}>
                ${this.t('<entity>_page.create')}
            </button>
            ${this._entities.items.map((it) => html`
                <my-entity-row .item=${it}
                               ?busy=${this._entities.isBusy(it.entity_id)}
                               @remove=${() => this._entities.remove(it.entity_id)}>
                </my-entity-row>
            `)}
        `;
    }
}
```

4. i18n — пара ключей в `core/i18n/translations/{ru,en}/<svc>.json`:

```json
{
  "<entity>_page": {
    "create": "Создать",
    "toast_renamed": "Переименовано",
    "toast_revoked": "Удалено"
  },
  "<entity>_modal": {
    "toast_created": "Создано",
    "err_create_failed": "Не удалось создать"
  }
}
```

5. Backend — FastAPI route в `apps/<svc>/api/<entities>.py` под `GET/POST /<entities>`, `GET/PATCH/DELETE /<entities>/{entity_id}`. CI [`scripts/check_command_rest_mirror.py`](scripts/check_command_rest_mirror.py) сверит наличие.

### Свойства `ResourceController` (источник правды — [`use-resource.js`](core/frontend/static/lib/base/use-resource.js))

| Свойство / метод | Назначение |
|---|---|
| `ctl.items` | Текущий список (`Array`, гарантирован фабрикой). |
| `ctl.byId` | Словарь по id. |
| `ctl.loading` | Только для `list`. Для дизейбла кнопки create — НЕ использовать. |
| `ctl.createInFlight` | Lock на `create` (см. ui_factories.mdc, секция «Сериализованный create»). |
| `ctl.error` / `ctl.lastError` | Текущая ошибка (`null` если нет). |
| `ctl.busyIds` / `ctl.isBusy(id)` | Item-level busy для update/remove. |
| `ctl.load(query?)` | Re-fetch list. |
| `ctl.get(id)` | Загрузить один item. |
| `ctl.create(payload)` | Послать `_requested`. Идемпотентен на повторный клик. |
| `ctl.update(id, payload)` | Обновить. |
| `ctl.remove(id)` | Удалить. |
| `ctl.<actionMethod>(payload)` | Из `actions: { methodName: 'verb' }` фабрики. |

### Чек-лист

- [ ] `name` — `<svc>/<entity>`, lowercase, snake_case, ровно 2 сегмента.
- [ ] `baseUrl` — реальный FastAPI route в `apps/<svc>/api/**`.
- [ ] Все mutating операции имеют `toastKeys.<op>` в `<ns>:` формате.
- [ ] Каждый toast-ключ парно есть в `core/i18n/translations/{ru,en}/<ns>.json`.
- [ ] Фабрика добавлена в `static factories = [...]` в `<svc>-app.js`.
- [ ] В page — `this.useResource('<svc>/<entity>', { autoload: true })`, **не** `import` фабрики.
- [ ] Кнопка create дизейблится через `this._entities.createInFlight`.
- [ ] `make check-ui-canon` + `make check-ui-factories` + `make check-i18n-keys` зелёные.

---

## 2. Новая команда (createAsyncOp): HTTP и WS

Каноничный пример HTTP: [`apps/frontend/ui/events/resources/tracing.resource.js`](apps/frontend/ui/events/resources/tracing.resource.js) (`tracingTraceLoadOp`).
Каноничный пример WS: [`apps/sync/ui/events/resources/calls.resource.js`](apps/sync/ui/events/resources/calls.resource.js) (`callInviteOp`).

### Вариант A — HTTP

```js
import { createAsyncOp } from '@platform/lib/events/index.js';
import { httpRequest } from '@platform/lib/events/http.js';

export const inviteAcceptOp = createAsyncOp({
    name: 'frontend/invite_accept',
    silent: true,            // ИЛИ successToastKey + errorToastKey
    restMirror: { method: 'POST', path: '/frontend/api/invites/:token/accept' },
    request: async ({ payload }) => {
        if (!payload || typeof payload.token !== 'string') {
            throw new Error('invite_accept: token required');
        }
        return await httpRequest({
            method: 'POST',
            url: `/frontend/api/invites/${encodeURIComponent(payload.token)}/accept`,
            body: payload.body || null,
        });
    },
});
```

В компоненте:

```js
this._accept = this.useOp('frontend/invite_accept');

async _onAccept(token) {
    const result = await this._accept.run({ token });
    if (this._accept.error) {
        this.toast('common:error_generic', { type: 'error' });
        return;
    }
    this.navigate('dashboard', {}, { replace: true });
}
```

### Вариант B — WS (request-reply)

```js
export const callInviteOp = createAsyncOp({
    name: 'sync/calls_invite',                                                  // имя фабрики
    transport: 'ws',
    wsTimeoutMs: 8_000,
    silent: true,
    commandType: 'sync/calls/invite_requested',                                 // тип WS-фрейма (если != events.REQUESTED)
    restMirror: { method: 'POST', path: '/sync/api/v1/calls/:call_id/invite' }, // обязательно для transport: 'ws'
});
```

`request` указывать не обязательно — фабрика сама шлёт `wsRequest({ type: commandType, payload, ... })` и ждёт `*_succeeded` / `*_failed`.

### Свойства `OpController`

| Свойство / метод | Назначение |
|---|---|
| `ctl.busy` | true пока `_requested` ещё не получил succeeded/failed. |
| `ctl.error` | Последняя ошибка. |
| `ctl.lastResult` | Результат последнего successful запуска. |
| `await ctl.run(payload)` | Возвращает Promise: SUCCEEDED → `result`, FAILED → `null` (ошибка в `ctl.error`). |

`ctl.run` НЕ бросает на FAILED — это явный контракт fire-and-forget. Если важно различить — проверить `ctl.error` после `await`.

### Чек-лист

- [ ] `name` уникальный в репо (можно отличаться от `commandType`).
- [ ] `restMirror` указывает на реальный FastAPI route.
- [ ] Для `transport: 'ws'`: задан `wsTimeoutMs` (>0), `commandType` заканчивается на `_requested`, есть backend-handler в `apps/<svc>/realtime/command_router.py`.
- [ ] Если `silent: false` — обе пары `successToastKey` + `errorToastKey` заданы и парны в i18n.
- [ ] `make check-command-rest-mirror` зелёный.

---

## 2bis. Идемпотентные команды и ожидание ответа от бэка

Любая mutating-команда — это `_requested` → серверное `_succeeded` / `_failed`. Между нажатием и ответом проходит время. **Запрещено** позволять второй `_requested` от одного действия пользователя — это плодит дубликаты. **Запрещено** держать `this._busy` руками.

Платформа даёт три каноничных механизма, и других не нужно. Подробное правило — раздел «Идемпотентные команды» в [`SKILL.md`](.cursor/skills/frontend-engineer/SKILL.md).

### Паттерн A — встроенный `createInFlight` для `createResourceCollection.create`

Это **базовый** паттерн. Reducer + effect + controller сами защищают от двойного клика и параллельных effect-запусков (см. [`core/frontend/static/lib/events/factories/resource-collection.js`](core/frontend/static/lib/events/factories/resource-collection.js), поля `createInFlight` / `createLockEventId`).

Каноничное применение: [`apps/crm/ui/modals/namespace-modal.js`](apps/crm/ui/modals/namespace-modal.js).

```js
// 1. В компоненте — controller через helper:
constructor() {
    super();
    this._namespaces = this.useResource('crm/namespaces');
    this._createForm = this.useForm('crm/namespace_create_form');
}

// 2. Кнопка дизейблится от createInFlight (НЕ loading — loading относится только к list):
_isCreateOperationBusy() {
    if (!this._isCreate()) return false;
    return this._createForm.submitting || this._namespaces.createInFlight;
}

render() {
    return html`
        <button ?disabled=${this._isCreateOperationBusy()}
                @click=${() => this._namespaces.create({ name: this._draft })}>
            ${this.t('namespace_modal.action_create')}
        </button>
    `;
}
```

`this._namespaces.create({ name })`:

- Первый вызов: диспатчит `crm/namespaces/create_requested`, reducer ставит `createInFlight: true`, effect делает HTTP/WS.
- Повторный вызов **до** ответа: `ResourceController.create()` видит `createInFlight === true` и возвращает `undefined` без диспатча.
- Любой повторный `dispatch('crm/namespaces/create_requested', ...)` (например из теста или devtools): reducer не меняет lock, effect видит `event.id !== createLockEventId` и пропускает HTTP.

Аналогично для команды редактирования — кнопка «Сохранить» использует `this._updateOp.busy`:

```js
const busy = isCreate ? this._entities.createInFlight : this._updateOp.busy;
```

Каноничный пример: [`apps/crm/ui/components/note-card-view.js`](apps/crm/ui/components/note-card-view.js) (строка `~3544`).

### Паттерн B — `OpController.run()` с матчингом по `causation_id`

Реализация: [`OpController`](core/frontend/static/lib/base/use-resource.js) — `run(payload)` диспатчит `events.REQUESTED`, подписывается на `events.SUCCEEDED`/`FAILED`, фильтрует по `event.meta.causation_id === requested.id` и резолвит Promise.

Контракт:

- SUCCEEDED → `resolve(result)` (`event.payload.result`).
- FAILED → `resolve(null)` (НЕ reject — это специальный контракт, чтобы fire-and-forget вызовы не падали в unhandled rejection). Ошибка читается из `ctl.error`.

В компоненте:

```js
this._invite = this.useOp('frontend/invite_accept');

async _onAccept(token) {
    const result = await this._invite.run({ token });
    if (this._invite.error) {
        this.toast('common:error_generic', { type: 'error' });
        return;
    }
    this.navigate('dashboard', {}, { replace: true });
}

render() {
    return html`<button ?disabled=${this._invite.busy} @click=${this._onAccept}>${this.t('action.accept')}</button>`;
}
```

Если одна op'а используется для **разных целей** — фильтруй по `causation_id` от своего dispatch. Пример из CRM: одна op `crm/entity_search` обслуживает три use-case (mention popup, voice search, context search), у каждого свой `requestId`:

```js
// apps/crm/ui/components/note-card-view.js (~1557)
this.useEvent(this._entitySearch.op.events.SUCCEEDED, (event) => {
    const cid = event.meta && typeof event.meta.causation_id === 'string' ? event.meta.causation_id : null;
    const purpose = this._entitySearchPurpose;

    if (purpose === 'mention') {
        if (this._mentionRequestId === null || cid !== this._mentionRequestId) return;
        this._mentionResults = result.items;
        this._mentionLoading = false;
        return;
    }
    if (purpose === 'voice') {
        if (this._voiceSearchRequestId === null || cid !== this._voiceSearchRequestId) return;
        // ...
    }
});
```

`this._mentionRequestId` ставится в момент диспатча: `const requested = this._entitySearch.run(payload); this._mentionRequestId = requested.id;`. Это делает компонент устойчивым к гонкам — поздний ответ от устаревшего поиска не перезапишет результат свежего.

Каноничный пример: [`apps/crm/ui/pages/daily-notes-page.js`](apps/crm/ui/pages/daily-notes-page.js) (`useEvent('crm/note_search/succeeded', ...)` фильтрует `event.meta.causation_id !== this._lastSearchRequestId`).

### Паттерн C — `_waitForResourceResult` / `_awaitOp` для зависимой цепочки

Когда нужен **`item`/`result` сразу после команды** для следующего шага (классика: создать сущность → получить `entity_id` → создать relationship), а готового `run()` нет (например для `ResourceController.create`) — пишется helper, который ждёт SUCCEEDED по `causation_id`.

Каноничный пример: [`apps/crm/ui/pages/note-page.js`](apps/crm/ui/pages/note-page.js) (метод `_waitForResourceResult`).

```js
_waitForResourceResult(controller, requestedId) {
    const bus = controller.bus;
    const successType = controller.resource.events.CREATED;
    const failedType = controller.resource.events.CREATE_FAILED;
    return new Promise((resolve, reject) => {
        let offSuccess = null;
        let offFailed = null;
        const cleanup = () => {
            if (typeof offSuccess === 'function') offSuccess();
            if (typeof offFailed === 'function') offFailed();
        };
        offSuccess = bus.subscribeType(successType, (event) => {
            if (!event.meta || event.meta.causation_id !== requestedId) return;
            cleanup();
            const item = event.payload && typeof event.payload.item === 'object' ? event.payload.item : null;
            resolve(item);
        });
        offFailed = bus.subscribeType(failedType, (event) => {
            if (!event.meta || event.meta.causation_id !== requestedId) return;
            cleanup();
            const message = event.payload && typeof event.payload.message === 'string'
                ? event.payload.message
                : 'resource create failed';
            reject(new Error(message));
        });
    });
}

async _createEntity(payload) {
    const requested = this._entities.create(payload);
    if (!requested || typeof requested.id !== 'string') {
        throw new Error('CRMNotePage._createEntity: create dispatch returned no id');
    }
    return await this._waitForResourceResult(this._entities, requested.id);
}

async _createRelationship(payload) {
    const requested = this._relationships.create(payload);
    if (!requested || typeof requested.id !== 'string') {
        throw new Error('CRMNotePage._createRelationship: create dispatch returned no id');
    }
    return await this._waitForResourceResult(this._relationships, requested.id);
}

async _onTaskAdd(text) {
    const note = this._resolveNote();
    if (!note) return;
    const task = await this._createEntity({ entity_type: 'task', name: text, namespace: note.namespace });
    if (!task) return;
    await this._createRelationship({
        from_entity_id: note.entity_id,
        to_entity_id: task.entity_id,
        relationship_type: 'has_task',
    });
}
```

Важные детали:

1. `this._entities.create(payload)` возвращает `undefined`, если уже есть in-flight create (см. паттерн A). Поэтому проверяй `requested && typeof requested.id === 'string'` перед `_waitForResourceResult` — `undefined` означает «дубликат проигнорирован», ждать нечего.
2. `cleanup()` снимает обе подписки **немедленно** при первом подходящем событии, иначе утечка слушателей.
3. Если нужен `result` от `createAsyncOp` — используй [`OpController.run()`](core/frontend/static/lib/base/use-resource.js); `_awaitOp` нужен только когда `run()` не подходит (например для нескольких параллельных запусков с зависимыми результатами).

Аналогичный helper для async-op с reject вместо resolve(null) — [`apps/crm/ui/modals/knowledge-import-modal.js`](apps/crm/ui/modals/knowledge-import-modal.js):

```js
_awaitOp(controller, payload) {
    return new Promise((resolve, reject) => {
        const op = controller.op;
        const requested = controller.run(payload);
        if (!requested || typeof requested.id !== 'string') {
            throw new Error('_awaitOp: REQUESTED event missing id');
        }
        const requestedId = requested.id;
        let unsubOk = null;
        let unsubFail = null;
        unsubOk = this.bus.subscribeType(op.events.SUCCEEDED, (event) => {
            if (event.meta.causation_id !== requestedId) return;
            unsubOk();
            unsubFail();
            resolve(event.payload.result);
        });
        unsubFail = this.bus.subscribeType(op.events.FAILED, (event) => {
            if (event.meta.causation_id !== requestedId) return;
            unsubOk();
            unsubFail();
            reject(new Error(event.payload.message));
        });
    });
}
```

Применяется когда нужно последовательно импортировать N файлов с обработкой ошибок отдельно по каждому.

### Сводная таблица «когда что брать»

| Задача | Решение |
|---|---|
| Кнопка «Создать» в форме / модалке. | `?disabled=${this._res.createInFlight}` (Паттерн A). |
| Кнопка «Сохранить» в режиме редактирования через async-op. | `?disabled=${this._updateOp.busy}` (Паттерн B). |
| Кнопка действия (типа «Отправить инвайт»). | `?disabled=${this._inviteOp.busy}` + `await this._inviteOp.run(payload)` (Паттерн B). |
| Создать сущность и сразу её ID использовать в следующей команде. | `_waitForResourceResult` (Паттерн C) или `OpController.run()` + чтение `lastResult`. |
| Поиск с дебаунсом (одна op, много запусков). | Хранить `_lastSearchRequestId`, фильтровать `useEvent` по `causation_id` (Паттерн B, без `await ctl.run()`). |
| Push-уведомления, не команды. | `useEvent('<svc>/<entity>/<verb>', handler)` + `extraReducer` фабрики (см. рецепт 9). |

### Чек-лист

- [ ] Кнопки команд дизейблятся **только** через `createInFlight` / `OpController.busy` / `FormController.submitting`. Никаких `this._busy = true / false`.
- [ ] Подписки на `op.events.SUCCEEDED` / `FAILED` фильтруются по `event.meta.causation_id === requested.id`.
- [ ] При `ResourceController.create` для последующего `await result` — проверка `requested && typeof requested.id === 'string'` (иначе это дубликат, событие не придёт).
- [ ] Нет `await this.dispatch(...)` — `dispatch` fire-and-forget (см. [`anti-patterns.md`](.cursor/skills/frontend-engineer/anti-patterns.md) пункт 3.4).
- [ ] Помощник `_waitForResourceResult` / `_awaitOp` снимает обе подписки в `cleanup()` при первом матче.
- [ ] При гонке (несколько одинаковых команд из одного компонента) — каждая хранит свой `requestId` (как `_mentionRequestId` / `_voiceSearchRequestId` в `note-card-view.js`).

---

## 3. Cursor-paginated лента (createCursorList)

Каноничный пример: [`apps/frontend/ui/events/resources/tracing.resource.js`](apps/frontend/ui/events/resources/tracing.resource.js) (`tracingSpansList`).

### Шаги

```js
import { createCursorList } from '@platform/lib/events/index.js';

function _buildSpansQuery(filters) {
    const q = {};
    if (filters.company_id)    q.company_id_query = filters.company_id;
    if (filters.user_id)       q.user_id_query = filters.user_id;
    if (filters.from_time)     q.from_time = filters.from_time;
    if (filters.to_time)       q.to_time = filters.to_time;
    return q;
}

export const tracingSpansList = createCursorList({
    name: 'frontend/tracing_spans',
    baseUrl: '/frontend/api/platform-tracing/spans',
    pageSize: 50,
    buildQuery: _buildSpansQuery,
    statusMap: { 403: 'forbidden', 503: 'unavailable' },   // терминальные события из HTTP-кодов
    errorToastKey: 'frontend:tracing_page.load_error',
});
```

В компоненте:

```js
this._spans = this.useCursorList('frontend/tracing_spans', { autoload: true });

render() {
    if (this._spans.terminal === 'forbidden') {
        return html`<empty-state .label=${this.t('tracing_page.forbidden')}></empty-state>`;
    }
    return html`
        ${this._spans.items.map((s) => html`<span-row .item=${s}></span-row>`)}
        ${this._spans.hasMore
            ? html`<button ?disabled=${this._spans.loadingMore} @click=${() => this._spans.loadMore()}>
                ${this.t('common:action_load_more')}
            </button>`
            : ''}
    `;
}

_onFiltersChange(patch) {
    this._spans.changeFilters(patch);
}
```

### Свойства `CursorListController`

| Свойство / метод | Назначение |
|---|---|
| `ctl.items` | Накопленный список. |
| `ctl.hasMore` | Есть ли следующая страница. |
| `ctl.loading` | Первый запрос (или после `load(filters)`). |
| `ctl.loadingMore` | `loadMore()` в процессе. |
| `ctl.terminal` | Из `statusMap` — например `'forbidden'`/`'unavailable'`. |
| `ctl.filters` | Текущие фильтры. |
| `ctl.load(filters?)` | Сброс + запрос. |
| `ctl.loadMore()` | Подгрузить следующую страницу. |
| `ctl.changeFilters(patch)` | Merge новых фильтров и перезапросить. |
| `ctl.resetFilters()` | Вернуть `initialFilters`. |

---

## 4. Typeahead / facets (createFacets)

Каноничный пример: [`apps/frontend/ui/events/resources/tracing.resource.js`](apps/frontend/ui/events/resources/tracing.resource.js) (`tracingFacets`).

```js
import { createFacets } from '@platform/lib/events/index.js';

export const tracingFacets = createFacets({
    name: 'frontend/tracing_facets',
    baseUrl: '/frontend/api/platform-tracing/facets',
    facets: {
        companies:   'companies',
        users:       'users',
        services:    'services',
        namespaces:  'namespaces',
        operations:  'operations',
        event_types: 'event-types',
    },
    debounceMs: 200,
    minQueryLength: 2,
    pageSize: 20,
});
```

Использование:

```js
this._facets = this.useFacets('frontend/tracing_facets');

_onCompanyTyped(query) {
    this._facets.search('companies', query);
}

render() {
    return html`
        <input @input=${(e) => this._onCompanyTyped(e.target.value)} />
        ${this._facets.loading('companies')
            ? html`<glass-spinner></glass-spinner>`
            : html`<ul>${this._facets.items('companies').map((it) => html`<li>${it.label}</li>`)}</ul>`}
    `;
}
```

---

## 5. Форма с валидацией (createForm)

```js
import { createForm } from '@platform/lib/events/index.js';
import { myEntityCreateOp } from './<entity>.resource.js';

export const myEntityForm = createForm({
    name: '<svc>/<entity>_create_form',
    schema: {
        name: { required: true, minLength: 1, maxLength: 64, errorKey: '<svc>:<entity>_modal.err_name' },
        tags: { required: false },
    },
    initial: { name: '', tags: [] },
    submitEvent: myEntityCreateOp.events.REQUESTED,         // когда form.submit() пройдёт валидацию — диспатчит этот тип
    buildPayload: (draft) => ({ name: draft.name.trim(), tags: draft.tags }),
});
```

В модалке (наследник `PlatformFormModal`):

```js
constructor() {
    super();
    this._form = this.useForm('<svc>/<entity>_create_form');
}

connectedCallback() {
    super.connectedCallback();
    this._form.openForm({ name: this.props && this.props.preset_name ? this.props.preset_name : '' });
}

async handleSubmit() {
    this._form.submit();   // если валидно — диспатчит submitEvent
    if (this._form.isValid) this.closeAfterSave();
}
```

---

## 6. UI-only slice (createSlice) — push-only / overlay

Каноничный пример: `createSlice('sync/call_ui')` в [`apps/sync/ui/events/resources/calls.resource.js`](apps/sync/ui/events/resources/calls.resource.js) и `createSlice('sync/presence')` в [`apps/sync/ui/events/resources/presence.resource.js`](apps/sync/ui/events/resources/presence.resource.js).

```js
import { createSlice } from '@platform/lib/events/index.js';

export const callUiSlice = createSlice({
    name: 'sync/call_ui',
    extraInitial: {
        activeCall: null,
        incomingCall: null,
        overlayMinimized: false,
        recordingStatus: 'idle',
    },
    extraEvents: {
        OVERLAY_MINIMIZED: 'overlay_minimized',
        OVERLAY_EXPANDED: 'overlay_expanded',
        OVERLAY_CLOSED: 'overlay_closed',
        RECORDING_STATUS_SET: 'recording_status_set',
    },
    actions: {
        minimizeOverlay: 'overlay_minimized',
        expandOverlay: 'overlay_expanded',
        closeOverlay: 'overlay_closed',
        setRecordingStatus: 'recording_status_set',
    },
    extraReducer: (state, event, events) => {
        if (event.type === 'sync/call/incoming') {
            const p = event.payload;
            if (!p || typeof p.call_id !== 'string') return state;
            return { ...state, incomingCall: p };
        }
        if (event.type === 'sync/call/ended') {
            return { ...state, activeCall: null, overlayMinimized: false, recordingStatus: 'idle' };
        }
        if (event.type === events.OVERLAY_MINIMIZED) {
            return { ...state, overlayMinimized: true };
        }
        /* ... */
        return state;
    },
});
```

Использование:

```js
this._callUi = this.useSlice('sync/call_ui');

render() {
    const { activeCall, overlayMinimized } = this._callUi.value;
    if (!activeCall) return '';
    if (overlayMinimized) {
        return html`<minimized-call-banner @click=${() => this._callUi.expandOverlay(null)}></minimized-call-banner>`;
    }
    return html`<sync-call-overlay-modal .callId=${activeCall.call_id}></sync-call-overlay-modal>`;
}
```

### Запреты в createSlice

- `transport`, `request`, `restMirror`, `wsTimeoutMs` — не поддерживаются (slice без транспорта). [`scripts/check_ui_factories.py`](scripts/check_ui_factories.py) бросает.
- `extraInitial` обязан содержать минимум один ключ.
- `extraReducer` обязателен и должен быть pure.

---

## 7. Новая страница

Каноничный пример: [`apps/frontend/ui/pages/api-keys/api-keys-page.js`](apps/frontend/ui/pages/api-keys/api-keys-page.js).

### Шаги

1. Создать `apps/<svc>/ui/pages/<page>.js`:

```js
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-breadcrumbs.js';

export class MyEntityPage extends PlatformPage {
    static i18nNamespace = '<svc>';   // ИЛИ опираться на defaultI18nNamespace в <svc>-app.js

    static styles = [
        PlatformPage.styles,
        css`:host { display: block; padding: var(--space-4); }`,
    ];

    constructor() {
        super();
        this._entities = this.useResource('<svc>/<entity>', { autoload: true });
    }

    render() {
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header
                title=${this.t('<entity>_page.title')}
                subtitle=${this.t('<entity>_page.subtitle')}
            >
                <button slot="actions" class="btn" @click=${() => this.openModal(MyEntityCreateModal)}>
                    ${this.t('<entity>_page.create')}
                </button>
            </page-header>
            <div class="page-body">
                ${this._entities.loading && this._entities.items.length === 0
                    ? html`<glass-spinner></glass-spinner>`
                    : this._entities.items.map((it) => html`...`)}
            </div>
        `;
    }
}
customElements.define('<svc>-<entity>-page', MyEntityPage);
```

2. Зарегистрировать маршрут в `apps/<svc>/ui/app/<svc>-app.js`:

```js
const ROUTES = [
    /* ... */
    { key: '<entity>', path: '<entities>' },                   // путь относительно baseUrl сервиса
    { key: '<entity>-detail', path: '<entities>/:id', parent: '<entity>' },
];
```

3. Импортировать в `<svc>-app.js`:

```js
import '../pages/<page>.js';
```

4. Добавить в `renderRoute(routeKey, params)`:

```js
renderRoute(routeKey, params) {
    if (routeKey === '<entity>')        return html`<<svc>-<entity>-page></<svc>-<entity>-page>`;
    if (routeKey === '<entity>-detail') return html`<<svc>-<entity>-detail-page .entityId=${params.id}></<svc>-<entity>-detail-page>`;
    /* ... */
}
```

5. Заголовок маршрута для breadcrumbs — секция `routes` в `core/i18n/translations/{ru,en}/<svc>.json`:

```json
{
  "routes": {
    "<entity>": "Сущности",
    "<entity>-detail": "Детали"
  }
}
```

### Чек-лист

- [ ] Класс наследует `PlatformPage`, не `LitElement`.
- [ ] Файл импортирует **только** lit + base + core UI Kit + локальные стили/модалки/компоненты сервиса (zero-import canon).
- [ ] Нет `dispatch(CoreEvents.UI_*|ROUTER_*|AUTH_*|...)` напрямую — только helpers.
- [ ] Все строки — через `this.t(...)`; парные ключи в `ru/en` бандлах.
- [ ] Маршрут зарегистрирован в `getRoutes()`; `renderRoute(routeKey, params)` обновлён.
- [ ] `routes.<routeKey>` есть в обоих i18n-бандлах.

---

## 8. Новая модалка

Каноничный пример: [`apps/frontend/ui/modals/create-api-key-modal.js`](apps/frontend/ui/modals/create-api-key-modal.js).

### Шаги

```js
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

export class MyEntityCreateModal extends PlatformFormModal {
    static modalKind = '<scope>.<entity>_create';   // ^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$
    static i18nNamespace = '<svc>';

    static styles = [...PlatformFormModal.styles, css`/* ... */`];

    static properties = {
        ...PlatformFormModal.properties,
        _name: { state: true },
    };

    constructor() {
        super();
        this._name = '';
        this.size = 'md';
        this._entities = this.useResource('<svc>/<entity>');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('<entity>_modal.header_create');
    }

    validateForm() {
        const errors = {};
        if (!this._name.trim()) errors.name = this.t('<entity>_modal.err_name');
        return errors;
    }

    async handleSubmit() {
        this._entities.create({ name: this._name.trim() });
        this.closeAfterSave();
    }

    renderFormBody() {
        return html`
            <glass-input
                label=${this.t('<entity>_modal.field_name')}
                .value=${this._name}
                @input=${(e) => { this._name = e.detail.value; }}
            ></glass-input>
        `;
    }
}
customElements.define('<svc>-<entity>-create-modal', MyEntityCreateModal);
registerModalKind(MyEntityCreateModal.modalKind, '<svc>-<entity>-create-modal');
```

В странице:

```js
this.openModal(MyEntityCreateModal);
// ИЛИ по строке:
this.openModal('<scope>.<entity>_create', { /* props */ });
```

### Чек-лист

- [ ] Класс наследует `PlatformModal` или `PlatformFormModal` (overlay-баннеры — `PlatformElement`, см. `sync.call_incoming`).
- [ ] `static modalKind = '<scope>.<entity>'` — точка как разделитель, snake_case.
- [ ] `customElements.define(...)` + `registerModalKind(kind, tagName)` рядом.
- [ ] Импорт модалки в `<svc>-app.js` (или там, где она открывается) — иначе `getModalTag` бросит.
- [ ] Открытие — через `this.openModal(...)`, **не** `document.createElement`.
- [ ] Закрытие из формы — `this.closeAfterSave()`; снаружи — `this.closeModal('<scope>.<entity>')`.

---

## 9. WS push-подписка (backend → UI)

Каноничные примеры:

- Backend: [`core/ui_events/dispatcher.py::publish_ui_event_to_user`](core/ui_events/dispatcher.py).
- Frontend: `useEvent('sync/call/incoming', ...)` в `sync-app.js`; `extraReducer` push-событий в [`apps/sync/ui/events/resources/messages.resource.js`](apps/sync/ui/events/resources/messages.resource.js).

### Backend

```python
from core.ui_events import publish_ui_event_to_user

await publish_ui_event_to_user(
    user_id=note.author_user_id,
    type="crm/note/updated",
    payload={"note_id": note.id, "text": note.text},
    correlation_id=trace_id,
)
```

Имя события **не** должно совпадать с командой. Например:
- команда: `crm/notes/update_requested` → reply `crm/notes/update_succeeded`
- push: `crm/note/updated` (другое entity: `note` vs `notes`).

### Frontend — два варианта

A. Реактивно через `extraReducer` фабрики (рекомендуется):

```js
export const notesResource = createResourceCollection({
    name: 'crm/notes',
    baseUrl: '/crm/api/v1/notes',
    idField: 'note_id',
    operations: ['list', 'get', 'create', 'update', 'remove'],
    toastKeys: { /* ... */ },
    extraReducer: (state, event) => {
        if (event.type === 'crm/note/updated') {
            const p = event.payload;
            if (!p || typeof p.note_id !== 'string') return state;
            const items = state.items.map((it) => it.note_id === p.note_id ? { ...it, text: p.text } : it);
            return { ...state, items };
        }
        return state;
    },
});
```

B. Точечно в компоненте (для UI-action — например подсветка):

```js
constructor() {
    super();
    this._notes = this.useResource('crm/notes', { autoload: true });
}

connectedCallback() {
    super.connectedCallback();
    this.useEvent('crm/note/updated', ({ payload }) => {
        if (!payload || typeof payload.note_id !== 'string') return;
        this._highlightedNoteId = payload.note_id;
        setTimeout(() => { this._highlightedNoteId = null; this.requestUpdate(); }, 1500);
        this.requestUpdate();
    });
}
```

### Чек-лист

- [ ] Имя push-события `<scope>/<entity>/<verb>`, ≥3 сегмента, snake_case.
- [ ] Имя НЕ совпадает с командой (без `_requested`/`_succeeded`/`_failed`).
- [ ] REST-зеркала у push-события **нет** (запрет в [`scripts/check_command_rest_mirror.py`](scripts/check_command_rest_mirror.py)).
- [ ] Reducer / handler нормализует payload, игнорирует невалидное (`return state` без бросания).

---

## 10. Toast / clipboard / navigate / locale / theme / company

Все через helpers базы — никакого `dispatch(CoreEvents.*)`.

### Toast

```js
this.toast('foo.bar');                              // namespace из static i18nNamespace
this.toast('frontend:foo.bar');                     // явный
this.toast('foo.error', { type: 'error' });
this.toast('foo.template', { vars: { name: x } });
this.toast('foo.persist', { duration: 10_000 });
```

### Clipboard (через core effect, обработка ошибок)

```js
this.copyToClipboard(secret, {
    success_i18n_key: 'api_key_modal.toast_key_copied',
    error_i18n_key: 'api_key_modal.err_copy_failed',
});
```

Оба ключа обязательны — иначе `throw`. Это zero-fallback canon.

### Navigate

```js
this.navigate('channel', { channelId });
this.navigate('channel', { channelId }, { search: '?focus=msg_42' });
this.navigate('login', {}, { replace: true });
```

`navigationOptions.search` обязан быть строкой (с/без ведущего `?`); `replace` — boolean.

### Locale

```js
this.setLocale('en');
```

### Theme

```js
this.setTheme('dark');     // 'dark' | 'light'
```

### Company

```js
this.switchCompany(company_id);
```

### OAuth

```js
this.startOAuth('yandex', { returnPath: '/dashboard' });
this.startOAuth('google', { plan: 'pro' });
```

---

## 11. Новый i18n-ключ

### Шаги

1. Добавить ключ в обе локали:

`core/i18n/translations/ru/<ns>.json`:
```json
{
  "<section>": {
    "<key>": "Текст на русском {{name}}"
  }
}
```

`core/i18n/translations/en/<ns>.json`:
```json
{
  "<section>": {
    "<key>": "English text {{name}}"
  }
}
```

2. Использовать в коде:

```js
this.t('<section>.<key>', { name: 'Foo' });
this.t('<section>.<key>', { name: 'Foo' }, '<ns>');   // явный namespace
```

3. Прогнать проверки:

```bash
make check-i18n             # парность ru/en, структура
make check-i18n-keys        # код использует ключ + ключ есть в JSON
uv run python scripts/report_ui_i18n_gaps.py --app <svc>   # 0 кириллицы вне i18n
```

### Запреты

- Динамический ключ `t('<section>.' + status)` — нельзя.
- Toast-ключ без namespace (`successToastKey: 'foo.bar'`) — нельзя, только `<ns>:<dotted.key>`.
- Литерал кириллицы вместо `t(...)` — нельзя.
- Импорт `I18nNs.X` в pages/modals — нельзя, пиши `static i18nNamespace = 'frontend'` строкой.

---

## 12. Bridge-effect (доменное → core STORAGE_*/AUTH_*)

Допустимо **только** как тонкая связка. Каноничный пример: [`apps/sync/ui/events/sync-persist.effect.js`](apps/sync/ui/events/sync-persist.effect.js).

```js
// apps/<svc>/ui/events/<svc>-persist.effect.js
import { CoreEvents } from '@platform/lib/events/contract.js';

export function create<Svc>PersistEffect() {
    return (event, ctx) => {
        if (event.type === '<svc>/spaces/space_selected') {
            ctx.dispatch(CoreEvents.STORAGE_PERSIST_REQUESTED, {
                key: '<svc>:selectedSpaceId',
                value: event.payload && event.payload.space_id ? event.payload.space_id : null,
            }, { source: 'local' });
            return;
        }
        if (event.type === CoreEvents.AUTH_USER_LOADED) {
            ctx.dispatch(CoreEvents.STORAGE_LOAD_REQUESTED, { key: '<svc>:selectedSpaceId' }, { source: 'local' });
            return;
        }
    };
}
```

Подключение в `<svc>-app.js`:

```js
import { create<Svc>PersistEffect } from '../events/<svc>-persist.effect.js';

export class <Svc>App extends PlatformApp {
    /* ... */
    getServiceEffects() {
        return [createRouterEffect(<SVC>_ROUTES), create<Svc>PersistEffect()];
    }
}
```

### Что bridge-effect НЕ должен делать

- `httpRequest` / `fetch` — это контракт `createAsyncOp`/`createResourceCollection`.
- Мутировать доменный slice — это контракт reducer'а фабрики.
- Содержать бизнес-логику — это backend.

---

## 13. Использование core UI Kit (обязательное)

| Задача | Решение | Запрет |
|---|---|---|
| Trace tree / waterfall spans | `<platform-trace-viewer .roots=${...}>` + `'trace-span-select'` event | Свой `*-trace-tree`, `*-span-list` |
| Список логов Loki | `<platform-log-viewer .entries=${...}>` + `'copy-request'` event | Своя `.log-entry` таблица |
| Чужой пользователь по `user_id` | `<platform-user-chip user-id="user_..." size="sm\|md" ?interactive>` | Сырой `${user_id}`, `*-user-row`, `*-user-avatar` |
| Профиль / редактирование пользователя | `this.openModal('platform.user_info', { userId })` | Своя «модалка профиля» |
| Хлебные крошки | `<platform-breadcrumbs></platform-breadcrumbs>` или `<platform-breadcrumbs current-label=${dynamic}>` | Свой breadcrumb-компонент |
| Confirm dialog | `await platformConfirm(message, { title, variant: 'danger', confirmText, cancelText })` | `window.confirm()`, ручная модалка |
| Иконка | `<platform-icon name="..."></platform-icon>` | `<svg>` inline в pages/modals |
| Загрузка | `<glass-spinner></glass-spinner>` | Свой spinner |
| Поле ввода | `<glass-input>`, `<glass-textarea>`, `<glass-button>` | Сырой `<input>` без стилей токенов |
| Заголовок страницы | `<page-header title="..." subtitle="...">` + slot `actions` | Свой header |
| Sidebar | `<platform-service-sidebar>` + опционально `<platform-sidebar-nav-tree storage-scope="<svc>">` | Своя оболочка sidebar |
| Picker IANA таймзоны | `<platform-timezone-picker>` | Свой dropdown |
| Cron поле | `<platform-cron-field>` | Свой parser cron |
| Color picker палитры | `<platform-palette-color-picker>` | Свой color input |
| Date / calendar | `<platform-date-picker>` / `<platform-calendar-modal>` | Свой календарь |

---

## 14. Запуск платформы локально

```bash
make app                      # uv run python scripts/run.py all (uvicorn --reload + TaskIQ workers + scheduler)
make app APP_KILL=1           # сначала убить процессы на портах HTTP
```

Frontend сервиса виден на:
- `http://localhost:8002/` — frontend (landing + console)
- `http://localhost:8003/crm` — CRM
- `http://localhost:8004/rag` — RAG
- `http://localhost:8005/sync` — Sync
- `http://localhost:8001/flows` — Flows
- `http://localhost:8008/documents` — Office
- `http://localhost:8015/voice` — Voice gateway

DevTools: добавить `?platform_devtools=1` в URL — лог событий в console + `window.__platformDevtools__`.

---

## 15. Полный чек-лист «фича готова»

```bash
# Канон
make check-ui-canon
make check-ui-factories
make check-command-rest-mirror
make check-core-frontend-canon

# i18n
make check-i18n
make check-i18n-keys
uv run python scripts/report_ui_i18n_gaps.py --app <svc>   # = 0 совпадений

# Объединённая цель — обязательна перед коммитом
make check-events-canon

# Тесты ядра
make test-frontend-core-canon
make test-frontend-core-unit

# Lit-компоненты (если правил core UI Kit или модалки)
make test-ui-components

# Browser layer (если правил event-flow / SelectController / use*-helpers)
make test-frontend-core-browser
```

Все зелёные → готово. Хоть один красный → возвращаемся к канону, чиним причину, не «обходим». Костыли запрещены.

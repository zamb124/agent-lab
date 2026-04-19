/**
 * createSlice — фабрика slice-only сущностей (UI-only state без HTTP/WS).
 *
 * Назначение: завести именованный slice + reducer + actions без транспорта.
 * Для случаев, когда домен — чисто клиентский (звонок UI: `activeCall`,
 * `incomingCall`, `recordingStatus`; presence push-only) или slice
 * накапливается через push-события из bus и не требует request-reply.
 *
 * Контракт обязательных полей (отсутствие любого — `throw` на старте):
 *   - name: 'scope/entity' (lowercase, snake_case, ровно 2 сегмента)
 *   - extraInitial: { ... } — каноничная форма slice (массивы [], словари {},
 *     строки '', числа 0). Минимум один ключ.
 *   - extraReducer(state, event, events) — pure (state, event) => state.
 *
 * Опциональные:
 *   - sliceKey: переопределение sliceKey (default — derived из name).
 *   - extraEvents: { KEY: 'verb' } — дополнительные события scope namespace.
 *   - actions: { methodName: 'verb' } — методы контроллера, диспатчат
 *     '<name>/<verb>' с любым payload.
 *
 * Чего у slice-фабрики НЕТ:
 *   - request / transport / restMirror / wsTimeoutMs — slice не ходит в сеть.
 *   - effect — нет автоматического побочного действия (только pure reducer).
 *
 * См. ui_factories.mdc — раздел про createSlice.
 */

import {
    assertResourceName,
    deriveSliceKey,
    buildEventType,
    registerResourceName,
    freeze,
    requireField,
    requireFunction,
} from './_internal.js';

export function createSlice(options) {
    if (!options || typeof options !== 'object') {
        throw new Error('createSlice: options object required');
    }
    const name = requireField(options, 'name', 'createSlice');
    assertResourceName(name);

    if (options.transport !== undefined) {
        throw new Error(`createSlice(${name}): transport is forbidden (slice-only factory has no network).`);
    }
    if (options.request !== undefined) {
        throw new Error(`createSlice(${name}): request is forbidden (slice-only factory has no network).`);
    }
    if (options.restMirror !== undefined) {
        throw new Error(`createSlice(${name}): restMirror is forbidden (slice-only factory has no network).`);
    }
    if (options.wsTimeoutMs !== undefined) {
        throw new Error(`createSlice(${name}): wsTimeoutMs is forbidden (slice-only factory has no transport).`);
    }
    if (options.effect !== undefined) {
        throw new Error(`createSlice(${name}): effect is forbidden (slice-only factory has only reducer).`);
    }

    const extraInitial = requireField(options, 'extraInitial', 'createSlice');
    if (typeof extraInitial !== 'object' || Array.isArray(extraInitial)) {
        throw new Error(`createSlice(${name}): extraInitial must be plain object.`);
    }
    if (Object.keys(extraInitial).length === 0) {
        throw new Error(`createSlice(${name}): extraInitial must have at least one key.`);
    }
    const extraReducer = requireFunction(
        requireField(options, 'extraReducer', 'createSlice'),
        `createSlice(${name}).extraReducer`,
    );

    const sliceKey = options.sliceKey || deriveSliceKey(name);
    const extraEventsConfig = options.extraEvents && typeof options.extraEvents === 'object'
        ? options.extraEvents
        : null;
    const actionsConfig = options.actions && typeof options.actions === 'object'
        ? options.actions
        : null;

    registerResourceName(name, 'slice');

    const eventsMap = {};
    if (extraEventsConfig) {
        for (const [key, verb] of Object.entries(extraEventsConfig)) {
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createSlice(${name}): extraEvents.${key} must be non-empty verb`);
            }
            eventsMap[key] = buildEventType(name, verb);
        }
    }
    const actionsMap = {};
    if (actionsConfig) {
        for (const [methodName, verb] of Object.entries(actionsConfig)) {
            if (typeof methodName !== 'string' || methodName.length === 0) {
                throw new Error(`createSlice(${name}): actions key must be non-empty method name`);
            }
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createSlice(${name}): actions.${methodName} must be non-empty verb`);
            }
            const eventType = buildEventType(name, verb);
            eventsMap[verb.toUpperCase()] = eventType;
            actionsMap[methodName] = eventType;
        }
    }
    const events = freeze(eventsMap);
    const actions = freeze(actionsMap);
    const initialSlice = freeze({ ...extraInitial });

    function reducer(state = initialSlice, event) {
        const next = extraReducer(state, event, events);
        if (next && next !== state) {
            return freeze(next);
        }
        return state;
    }

    function _readSlice(state) {
        const slice = state[sliceKey];
        if (slice === undefined) {
            throw new Error(`createSlice(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice: (state) => _readSlice(state),
    });

    return freeze({
        kind: 'slice',
        name,
        sliceKey,
        events,
        actions,
        reducer,
        slice: freeze({ reducer, initial: initialSlice }),
        selectors,
        // Нет effect: фабрика не подписывается на bus.
    });
}

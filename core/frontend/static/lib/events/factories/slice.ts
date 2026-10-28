/**
 * createSlice — фабрика только slice сущностей (состояние только для UI без HTTP/WS).
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
 *   - extraReducer(state, event, events) — чистая функция (state, event) => state.
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
import type { PlatformEvent } from '../contract.js';
import { isPlainRecord } from '../payload.js';
import type { ActionMap, PlatformFactory } from '../factory-registry.js';
import type { SliceDef } from '../reducers/index.js';

export interface SliceFactoryOptions<S extends object = Record<string, unknown>, A extends ActionMap = ActionMap> {
    name: string;
    extraInitial: NoInfer<S>;
    extraReducer: (state: S, event: PlatformEvent, events: Readonly<Record<string, string>>) => NoInfer<S> | null | undefined;
    sliceKey?: string;
    extraEvents?: Record<string, string>;
    actions?: A;
    transport?: never;
    request?: never;
    restMirror?: never;
    wsTimeoutMs?: never;
    effect?: never;
}

export interface SliceFactory<S extends object = Record<string, unknown>, A extends ActionMap = ActionMap> extends PlatformFactory {
    kind: 'slice';
    name: string;
    sliceKey: string;
    events: Readonly<Record<string, string>>;
    actions: Readonly<A>;
    reducer(state: S | undefined, event: PlatformEvent): S;
    slice: SliceDef<S>;
    selectors: { slice: (state: Record<string, unknown>) => S };
}

export function createSlice<S extends object = Record<string, unknown>, A extends ActionMap = Record<never, string>>(
    options: SliceFactoryOptions<S, A>,
): SliceFactory<S, A> {
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
    const extraReducer = requireFunction<SliceFactoryOptions<S, A>['extraReducer']>(
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

    const eventsMap: Record<string, string> = {};
    if (extraEventsConfig) {
        for (const [key, verb] of Object.entries(extraEventsConfig)) {
            if (typeof verb !== 'string' || verb.length === 0) {
                throw new Error(`createSlice(${name}): extraEvents.${key} must be non-empty verb`);
            }
            eventsMap[key] = buildEventType(name, verb);
        }
    }
    const actionsMap: Record<string, string> = {};
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
    // Ключи actionsMap — ключи options.actions (A); значения — полные типы событий.
    function isBuiltActionMap(value: Record<string, string>): value is A {
        if (actionsConfig === null) {
            return Object.keys(value).length === 0;
        }
        return Object.keys(actionsConfig).every((key) => {
            const eventType = value[key];
            return typeof eventType === 'string' && eventType.length > 0;
        });
    }
    if (!isBuiltActionMap(actionsMap)) {
        throw new Error(`createSlice(${name}): actions map does not match options.actions`);
    }
    const actions = freeze(actionsMap);

    function isSliceState(value: unknown): value is S {
        if (!isPlainRecord(value)) return false;
        return Object.keys(extraInitial).every((key) => Object.prototype.hasOwnProperty.call(value, key));
    }

    const seededSlice = { ...extraInitial };
    if (!isSliceState(seededSlice)) {
        throw new Error(`createSlice(${name}): extraInitial is not a slice object`);
    }
    const initialSlice = freeze(seededSlice);

    function reducer(state: S = initialSlice, event: PlatformEvent): S {
        const next = extraReducer(state, event, events);
        if (next && next !== state) {
            return freeze(next);
        }
        return state;
    }

    function _readSlice(state: Record<string, unknown>): S {
        // Корневое состояние шины хранит slices разных фабрик; slice этой фабрики кладёт её reducer.
        const slice = state[sliceKey];
        if (!isSliceState(slice)) {
            throw new Error(`createSlice(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice: (state: Record<string, unknown>) => _readSlice(state),
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

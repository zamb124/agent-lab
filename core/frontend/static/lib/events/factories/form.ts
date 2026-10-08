/**
 * createForm — фабрика state-машины формы для модалок и страниц.
 *
 * Назначение: управлять draft-state, валидацией и сабмитом без ручных
 * `setState` и `_performSave` в компоненте. Сам сабмит — это дispatch события
 * целевой фабрики (createAsyncOp.events.REQUESTED или
 * createResourceCollection.events.CREATE_REQUESTED/UPDATE_REQUESTED). createForm
 * НЕ делает HTTP сам — он только готовит payload и передаёт его в op.
 *
 * Контракт:
 *   - name: 'scope/form_name'
 *   - schema: { [field]: { обязательный?: bool, minLength?, maxLength?, pattern?,
 *       validate?: (value, draft) => string|null, errorKey?: i18n }, ... }
 *   - initial: { [field]: value } — обязательно (zero-guess)
 *   - submitEvent: string — тип события, в которое передаём draft (или payload
 *     из buildPayload)
 *   - submittingClearOnEventTypes?: string[] — после SUBMIT_REQUESTED сбрасывать
 *     submitting при любом из этих типов событий (например CREATED / CREATE_FAILED
 *     у createResourceCollection), иначе submitting остаётся true до OPENED.
 *   - buildPayload?: (draft) => any — опционально; по умолчанию {...draft}
 *
 * Возвращает:
 *   { name, sliceKey, events: { OPENED, CLOSED, FIELD_CHANGED, RESET,
 *       SUBMIT_REQUESTED, SUBMIT_INVALID }, reducer, slice, selectors, effect,
 *     submitEvent }
 *
 * Жизненный цикл:
 *   1. dispatch OPENED { initial? } — сбрасывает draft и errors
 *   2. dispatch FIELD_CHANGED { field, value } — обновляет draft и
 *      пересчитывает ошибку конкретного поля
 *   3. dispatch SUBMIT_REQUESTED — фабрика валидирует draft; если ок →
 *      диспатчит submitEvent с payload, иначе → SUBMIT_INVALID { errors }
 *   3b. при указанных submittingClearOnEventTypes — приём CREATED/CREATE_FAILED
 *      (и др.) сбрасывает submitting
 *   4. dispatch CLOSED — обнуляет slice
 */

import {
    assertResourceName,
    deriveSliceKey,
    buildEventType,
    registerResourceName,
    freeze,
    requireField,
} from './_internal.js';
import type { EffectCtx, PlatformEvent } from '../contract.js';
import type { PlatformFactory } from '../factory-registry.js';
import type { SliceDef } from '../reducers/index.js';

export interface FormFieldRule {
    required?: boolean;
    minLength?: number;
    maxLength?: number;
    pattern?: RegExp;
    validate?: (value: unknown, draft: Record<string, unknown>) => string | null;
    errorKey?: string;
}

export interface FormSlice {
    open: boolean;
    draft: Readonly<Record<string, unknown>>;
    errors: Readonly<Record<string, string>>;
    submitting: boolean;
    [key: string]: unknown;
}

export interface FormOptions {
    name: string;
    schema: Record<string, FormFieldRule>;
    initial: Record<string, unknown>;
    submitEvent: string;
    submittingClearOnEventTypes?: string[];
    buildPayload?: (draft: Record<string, unknown>) => unknown;
    sliceKey?: string;
}

export interface FormFactory extends PlatformFactory {
    kind: 'form';
    name: string;
    sliceKey: string;
    events: Readonly<{ OPENED: string; CLOSED: string; FIELD_CHANGED: string; RESET: string; SUBMIT_REQUESTED: string; SUBMIT_INVALID: string }>;
    submitEvent: string;
    reducer: (state: FormSlice | undefined, event: PlatformEvent) => FormSlice;
    slice: SliceDef<FormSlice>;
    selectors: {
        slice: (state: Record<string, unknown>) => FormSlice;
        open: (state: Record<string, unknown>) => boolean;
        draft: (state: Record<string, unknown>) => Readonly<Record<string, unknown>>;
        errors: (state: Record<string, unknown>) => Readonly<Record<string, string>>;
        submitting: (state: Record<string, unknown>) => boolean;
        isValid: (state: Record<string, unknown>) => boolean;
    };
    effect: (event: PlatformEvent, ctx: EffectCtx) => void;
}

export function createForm(options: FormOptions): FormFactory {
    if (!options || typeof options !== 'object') {
        throw new Error('createForm: options object required');
    }
    const name = requireField(options, 'name', 'createForm');
    assertResourceName(name);
    const schema = requireField(options, 'schema', `createForm(${name})`);
    if (typeof schema !== 'object' || Object.keys(schema).length === 0) {
        throw new Error(`createForm(${name}): schema must be non-empty object`);
    }
    const initial = requireField(options, 'initial', `createForm(${name})`);
    if (typeof initial !== 'object') {
        throw new Error(`createForm(${name}): initial must be object`);
    }
    for (const field of Object.keys(schema)) {
        if (!(field in initial)) {
            throw new Error(`createForm(${name}): initial.${field} is required`);
        }
    }
    const submitEvent = requireField(options, 'submitEvent', `createForm(${name})`);
    if (typeof submitEvent !== 'string' || submitEvent.length === 0) {
        throw new Error(`createForm(${name}): submitEvent must be non-empty event type`);
    }
    const buildPayload = typeof options.buildPayload === 'function'
        ? options.buildPayload
        : (draft: Record<string, unknown>) => ({ ...draft });

    const submittingClearOnEventTypes = Array.isArray(options.submittingClearOnEventTypes)
        ? options.submittingClearOnEventTypes
        : [];
    for (const t of submittingClearOnEventTypes) {
        if (typeof t !== 'string' || t.length === 0) {
            throw new Error(`createForm(${name}): submittingClearOnEventTypes must be non-empty strings`);
        }
    }
    const _submittingClearSet = new Set(submittingClearOnEventTypes);

    const sliceKey = options.sliceKey || deriveSliceKey(name);
    registerResourceName(name, 'form');

    const events = freeze({
        OPENED:           buildEventType(name, 'opened'),
        CLOSED:           buildEventType(name, 'closed'),
        FIELD_CHANGED:    buildEventType(name, 'field_changed'),
        RESET:            buildEventType(name, 'reset'),
        SUBMIT_REQUESTED: buildEventType(name, 'submit_requested'),
        SUBMIT_INVALID:   buildEventType(name, 'submit_invalid'),
    });

    const initialSlice: FormSlice = freeze({
        open: false,
        draft: freeze({ ...initial }),
        errors: freeze({}),
        submitting: false,
    });

    function reducer(state: FormSlice = initialSlice, event: PlatformEvent): FormSlice {
        switch (event.type) {
            case events.OPENED: {
                const p = event.payload as { initial?: unknown } | null;
                const seed = p && p.initial && typeof p.initial === 'object'
                    ? p.initial as Record<string, unknown>
                    : {};
                return freeze({
                    open: true,
                    draft: freeze({ ...initial, ...seed }),
                    errors: freeze({}),
                    submitting: false,
                });
            }
            case events.CLOSED:
                return initialSlice;
            case events.FIELD_CHANGED: {
                const p = event.payload as { field?: unknown; value?: unknown } | null;
                if (!p || typeof p.field !== 'string') {
                    throw new Error(`createForm(${name}): FIELD_CHANGED payload.field required (string)`);
                }
                const field = p.field;
                if (!(field in schema)) {
                    throw new Error(`createForm(${name}): FIELD_CHANGED unknown field "${field}"`);
                }
                if (!('value' in p)) {
                    throw new Error(`createForm(${name}): FIELD_CHANGED payload.value required`);
                }
                const value = p.value;
                const draft = freeze({ ...state.draft, [field]: value });
                const fieldError = _validateField(field, value, draft, schema);
                const errors: Record<string, string> = { ...state.errors };
                if (fieldError) errors[field] = fieldError;
                else delete errors[field];
                return freeze({ ...state, draft, errors: freeze(errors) });
            }
            case events.RESET:
                return freeze({ ...state, draft: freeze({ ...initial }), errors: freeze({}) });
            case events.SUBMIT_REQUESTED:
                return freeze({ ...state, submitting: true });
            case events.SUBMIT_INVALID: {
                const p = event.payload as { errors?: unknown } | null;
                if (!p || !p.errors || typeof p.errors !== 'object') {
                    throw new Error(`createForm(${name}): SUBMIT_INVALID payload.errors required (object)`);
                }
                return freeze({
                    ...state,
                    submitting: false,
                    errors: freeze(p.errors as Record<string, string>) as Readonly<Record<string, string>>,
                });
            }
            default: {
                if (state.submitting && _submittingClearSet.has(event.type)) {
                    return freeze({ ...state, submitting: false });
                }
                return state;
            }
        }
    }

    function _readSlice(state: Record<string, unknown>): FormSlice {
        const slice = state[sliceKey] as FormSlice | undefined;
        if (slice === undefined) {
            throw new Error(`createForm(${name}): slice "${sliceKey}" not registered in bus`);
        }
        return slice;
    }

    const selectors = freeze({
        slice:      (state: Record<string, unknown>) => _readSlice(state),
        open:       (state: Record<string, unknown>) => Boolean(_readSlice(state).open),
        draft:      (state: Record<string, unknown>) => _readSlice(state).draft,
        errors:     (state: Record<string, unknown>) => _readSlice(state).errors,
        submitting: (state: Record<string, unknown>) => Boolean(_readSlice(state).submitting),
        isValid:    (state: Record<string, unknown>) => Object.keys(_readSlice(state).errors).length === 0,
    });

    function effect(event: PlatformEvent, ctx: EffectCtx): void {
        if (event.type !== events.SUBMIT_REQUESTED) return;
        const slice = _readSlice(ctx.getState() as Record<string, unknown>);
        const errors = _validateAll(slice.draft, schema);
        if (Object.keys(errors).length > 0) {
            ctx.dispatch(events.SUBMIT_INVALID, { errors }, { causation_id: event.id });
            return;
        }
        const payload = buildPayload(slice.draft);
        ctx.dispatch(submitEvent, payload, { causation_id: event.id });
    }

    return freeze({
        kind: 'form',
        name,
        sliceKey,
        events,
        submitEvent,
        reducer,
        slice: freeze({ reducer, initial: initialSlice }),
        selectors,
        effect,
    });
}

function _validateField(field: string, value: unknown, draft: Record<string, unknown>, schema: Record<string, FormFieldRule>): string | null {
    const rule = schema[field];
    if (!rule) return null;
    if (rule.required) {
        if (value === undefined || value === null) return rule.errorKey || 'required';
        if (typeof value === 'string' && value.trim().length === 0) return rule.errorKey || 'required';
        if (Array.isArray(value) && value.length === 0) return rule.errorKey || 'required';
    }
    if (typeof value === 'string') {
        if (typeof rule.minLength === 'number' && value.length < rule.minLength) {
            return rule.errorKey || 'too_short';
        }
        if (typeof rule.maxLength === 'number' && value.length > rule.maxLength) {
            return rule.errorKey || 'too_long';
        }
        if (rule.pattern instanceof RegExp && value.length > 0 && !rule.pattern.test(value)) {
            return rule.errorKey || 'pattern_mismatch';
        }
    }
    if (typeof rule.validate === 'function') {
        const custom = rule.validate(value, draft);
        if (custom) return custom;
    }
    return null;
}

function _validateAll(draft: Record<string, unknown>, schema: Record<string, FormFieldRule>): Record<string, string> {
    const errors: Record<string, string> = {};
    for (const field of Object.keys(schema)) {
        const err = _validateField(field, draft[field], draft, schema);
        if (err) errors[field] = err;
    }
    return errors;
}

/**
 * createForm: schema/initial/submitEvent — обязательны.
 * Reducer обрабатывает OPENED/CLOSED/FIELD_CHANGED/RESET/SUBMIT_*; effect валидирует
 * draft и либо диспатчит submitEvent, либо SUBMIT_INVALID.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createForm } from '@platform/lib/events/factories/form.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';

beforeEach(() => resetFactories());
afterEach(() => resetFactories());

const opts = (overrides = {}) => ({
    name: 'svc/api_key_form',
    schema: {
        name: { required: true, minLength: 3, maxLength: 64, errorKey: 'svc:form.name_required' },
        scopes: { required: true },
    },
    initial: { name: '', scopes: [] },
    submitEvent: 'svc/api_keys/create_requested',
    ...overrides,
});

describe('createForm: contract', () => {
    it('обязательные поля', () => {
        expect(() => Reflect.apply(createForm, null, [{}])).toThrow(/name/);
        expect(() => Reflect.apply(createForm, null, [{ name: 'svc/x' }])).toThrow(/schema/);
        expect(() => Reflect.apply(createForm, null, [{ name: 'svc/x', schema: { a: {} } }])).toThrow(/initial/);
        expect(() => Reflect.apply(createForm, null, [{ name: 'svc/x', schema: { a: {} }, initial: {} }])).toThrow(/initial.a/);
        expect(() => Reflect.apply(createForm, null, [{ name: 'svc/x', schema: { a: {} }, initial: { a: '' } }])).toThrow(/submitEvent/);
    });

    it('schema — непустой объект', () => {
        expect(() => Reflect.apply(createForm, null, [opts({ schema: {} })])).toThrow(/schema/);
    });

    it('каждое поле schema должно быть в initial', () => {
        const o = opts();
        Reflect.deleteProperty(o.initial, 'scopes');
        expect(() => Reflect.apply(createForm, null, [o])).toThrow(/initial.scopes/);
    });

    it('генерирует все 6 событий формы', () => {
        const f = createForm(opts());
        for (const k of ['OPENED', 'CLOSED', 'FIELD_CHANGED', 'RESET', 'SUBMIT_REQUESTED', 'SUBMIT_INVALID']) {
            expect(Reflect.get(f.events, k)).toMatch(/^svc\/api_key_form\//);
        }
    });
});

describe('createForm: reducer', () => {
    it('OPENED заполняет draft из initial + seed', () => {
        const f = createForm(opts());
        const next = f.reducer(f.slice.initial, { type: f.events.OPENED, payload: { initial: { name: 'preset' } }, id: 'o1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next.open).toBe(true);
        expect(next.draft).toEqual({ name: 'preset', scopes: [] });
    });

    it('CLOSED → initialSlice', () => {
        const f = createForm(opts());
        const seeded = f.reducer(f.slice.initial, { type: f.events.OPENED, payload: { initial: { name: 'x' } }, id: 'o1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        const next = f.reducer(seeded, { type: f.events.CLOSED, payload: null, id: 'c1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next).toBe(f.slice.initial);
    });

    it('FIELD_CHANGED обновляет draft + ставит ошибку при minLength', () => {
        const f = createForm(opts());
        const opened = f.reducer(f.slice.initial, { type: f.events.OPENED, payload: { initial: null }, id: 'o1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        const next = f.reducer(opened, { type: f.events.FIELD_CHANGED, payload: { field: 'name', value: 'ab' }, id: 'fc1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next.draft.name).toBe('ab');
        expect(next.errors.name).toBe('svc:form.name_required');
        const next2 = f.reducer(next, { type: f.events.FIELD_CHANGED, payload: { field: 'name', value: 'abcd' }, id: 'fc2', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next2.errors.name).toBeUndefined();
    });

    it('FIELD_CHANGED unknown field — throw', () => {
        const f = createForm(opts());
        expect(() => f.reducer(f.slice.initial, { type: f.events.FIELD_CHANGED, payload: { field: 'mystery', value: 1 }, id: 'fc1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } })).toThrow(/unknown field/);
    });

    it('FIELD_CHANGED без field — throw', () => {
        const f = createForm(opts());
        expect(() => f.reducer(f.slice.initial, { type: f.events.FIELD_CHANGED, payload: { value: 1 }, id: 'fc1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } })).toThrow(/field/);
    });

    it('FIELD_CHANGED без value — throw', () => {
        const f = createForm(opts());
        expect(() => f.reducer(f.slice.initial, { type: f.events.FIELD_CHANGED, payload: { field: 'name' }, id: 'fc1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } })).toThrow(/value/);
    });

    it('SUBMIT_REQUESTED ставит submitting=true', () => {
        const f = createForm(opts());
        const opened = f.reducer(f.slice.initial, { type: f.events.OPENED, payload: null, id: 'o1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        const next = f.reducer(opened, { type: f.events.SUBMIT_REQUESTED, payload: null, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next.submitting).toBe(true);
    });

    it('SUBMIT_INVALID кладёт errors и снимает submitting', () => {
        const f = createForm(opts());
        const next = f.reducer(f.slice.initial, { type: f.events.SUBMIT_INVALID, payload: { errors: { name: 'svc:form.name_required' } }, id: 'si1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next.submitting).toBe(false);
        expect(next.errors).toEqual({ name: 'svc:form.name_required' });
    });

    it('submittingClearOnEventTypes снимает submitting после внешнего события', () => {
        const extOk = 'svc/widgets/created';
        const f = createForm(opts({ submittingClearOnEventTypes: [extOk] }));
        const opened = f.reducer(f.slice.initial, { type: f.events.OPENED, payload: null, id: 'o1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        const submitting = f.reducer(opened, { type: f.events.SUBMIT_REQUESTED, payload: null, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(submitting.submitting).toBe(true);
        const cleared = f.reducer(submitting, { type: extOk, payload: { item: { id: '1' } }, id: 'c1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(cleared.submitting).toBe(false);
    });

    it('submittingClearOnEventTypes — пустая строка в массиве — throw', () => {
        expect(() => Reflect.apply(createForm, null, [opts({ submittingClearOnEventTypes: [''] })])).toThrow(/submittingClearOnEventTypes/);
    });

    it('RESET возвращает draft = initial', () => {
        const f = createForm(opts());
        const opened = f.reducer(f.slice.initial, { type: f.events.OPENED, payload: { initial: { name: 'x' } }, id: 'o1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        const next = f.reducer(opened, { type: f.events.RESET, payload: null, id: 'r1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } });
        expect(next.draft).toEqual({ name: '', scopes: [] });
    });
});

describe('createForm: effect', () => {
    it('валидный draft → диспатчит submitEvent с buildPayload', () => {
        const f = createForm(opts());
        const state = { [f.sliceKey]: { ...f.slice.initial, draft: { name: 'valid', scopes: ['read'] } } };
        const dispatched: DispatchedRecord[] = [];
        f.effect({ type: f.events.SUBMIT_REQUESTED, payload: null, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, buildCtx(() => state, dispatched));
        const submit = dispatched.find((d) => d.type === 'svc/api_keys/create_requested');
        expect(submit).toBeTruthy();
        expect(submit?.payload).toEqual({ name: 'valid', scopes: ['read'] });
    });

    it('невалидный draft → SUBMIT_INVALID без submitEvent', () => {
        const f = createForm(opts());
        const state = { [f.sliceKey]: { ...f.slice.initial, draft: { name: 'ab', scopes: [] } } };
        const dispatched: DispatchedRecord[] = [];
        f.effect({ type: f.events.SUBMIT_REQUESTED, payload: null, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, buildCtx(() => state, dispatched));
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(f.events.SUBMIT_INVALID);
        expect(types).not.toContain('svc/api_keys/create_requested');
        const invalid = dispatched.find((d) => d.type === f.events.SUBMIT_INVALID);
        expect(prop(prop(invalid?.payload, 'errors'), 'name')).toBe('svc:form.name_required');
        expect(prop(prop(invalid?.payload, 'errors'), 'scopes')).toBeDefined();
    });

    it('buildPayload(draft) применяется', () => {
        const f = createForm({
            ...opts(),
            buildPayload: (draft: Record<string, unknown>) => ({ payload: String(prop(draft, 'name')).toUpperCase() }),
        });
        const state = { [f.sliceKey]: { ...f.slice.initial, draft: { name: 'valid', scopes: ['x'] } } };
        const dispatched: DispatchedRecord[] = [];
        f.effect({ type: f.events.SUBMIT_REQUESTED, payload: null, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, buildCtx(() => state, dispatched));
        const submit = dispatched.find((d) => d.type === 'svc/api_keys/create_requested');
        expect(submit?.payload).toEqual({ payload: 'VALID' });
    });

    it('schema.validate(value, draft) — кастомная функция', () => {
        const f = createForm({
            name: 'svc/login',
            schema: {
                email: { required: true },
                password: { required: true, validate: (v, draft) => (v === draft.email ? 'svc:login.same_as_email' : null) },
            },
            initial: { email: '', password: '' },
            submitEvent: 'svc/auth/login_requested',
        });
        const state = { [f.sliceKey]: { ...f.slice.initial, draft: { email: 'a@b', password: 'a@b' } } };
        const dispatched: DispatchedRecord[] = [];
        f.effect({ type: f.events.SUBMIT_REQUESTED, payload: null, id: 's1', meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } }, buildCtx(() => state, dispatched));
        const invalid = dispatched.find((d) => d.type === f.events.SUBMIT_INVALID);
        expect(prop(prop(invalid?.payload, 'errors'), 'password')).toBe('svc:login.same_as_email');
    });
});

describe('createForm: selectors', () => {
    it('isValid истинно при пустых errors', () => {
        const f = createForm(opts());
        const state = { [f.sliceKey]: { ...f.slice.initial, errors: {} } };
        expect(f.selectors.isValid(state)).toBe(true);
        const state2 = { [f.sliceKey]: { ...f.slice.initial, errors: { name: 'x' } } };
        expect(f.selectors.isValid(state2)).toBe(false);
    });
});

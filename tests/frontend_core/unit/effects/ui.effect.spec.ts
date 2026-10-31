import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { createUiEffect } from '@platform/lib/events/effects/ui.effect.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { installFakeStorage } from '../../helpers/fake-storage.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildCtx } from '../../helpers/bus-fixtures.js';
import { prop } from '../../helpers/prop.js';
import type { DispatchedRecord } from '../../helpers/bus-fixtures.js';
import type { PlatformEvent } from '../../../../core/frontend/static/lib/events/contract.js';

let dom: ReturnType<typeof installDomShim>;
let storage: ReturnType<typeof installFakeStorage>;

beforeEach(() => {
    dom = installDomShim();
    storage = installFakeStorage();
    // ui.effect использует window.localStorage — синхронизируем
    if (!dom) throw new Error('dom required');

    dom.window.localStorage = storage.localStorage;
});
afterEach(() => {
    storage.uninstall();
    dom.uninstall();
});

const ev = (type: string | undefined, payload: unknown): PlatformEvent => {
    if (type === undefined) throw new Error('event type required');
    return { id: `id_${type}`, type, payload, meta: { ts: 0, source: 'local', causation_id: null, correlation_id: null, trace_id: null } };
};

describe('uiEffect: NAMESPACE_SELECT_REQUESTED', () => {
    it('требует company_id', async () => {
        await expect(createUiEffect()(ev(CoreEvents.UI_NAMESPACE_SELECT_REQUESTED, { selection: 'public' }), buildCtx(() => ({}), []))).rejects.toThrow(/company_id/);
    });

    it('persist в localStorage и эмитит CHANGED + RELOAD_REQUESTED', async () => {
        const dispatched: DispatchedRecord[] = [];
        await createUiEffect()(ev(CoreEvents.UI_NAMESPACE_SELECT_REQUESTED, { company_id: 'c1', selection: 'public' }), buildCtx(() => ({}), dispatched));
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(CoreEvents.UI_NAMESPACE_CHANGED);
        expect(types).toContain(CoreEvents.UI_DOCUMENTS_RELOAD_REQUESTED);
        const map = JSON.parse(storage.localStorage.getItem('platform:crm:last_namespace_by_company') ?? '{}');
        expect(map.c1).toBe('public');
    });

    it('selection=null или "all" → __ALL__ в storage, "all" в payload CHANGED', async () => {
        const dispatched: DispatchedRecord[] = [];
        await createUiEffect()(ev(CoreEvents.UI_NAMESPACE_SELECT_REQUESTED, { company_id: 'c1', selection: null }), buildCtx(() => ({}), dispatched));
        const map = JSON.parse(storage.localStorage.getItem('platform:crm:last_namespace_by_company') ?? '{}');
        expect(map.c1).toBe('__ALL__');
        const changed = dispatched.find((d) => d.type === CoreEvents.UI_NAMESPACE_CHANGED);
        expect(prop(changed?.payload, 'selection')).toBe('all');
    });
});

describe('uiEffect: CLIPBOARD_COPY_REQUESTED', () => {
    beforeEach(() => {
        Object.defineProperty(globalThis.navigator, 'clipboard', {
            value: { writeText: vi.fn(async () => undefined) },
            configurable: true,
        });
    });

    it('требует text', async () => {
        await expect(createUiEffect()(ev(CoreEvents.UI_CLIPBOARD_COPY_REQUESTED, {}), buildCtx(() => ({}), []))).rejects.toThrow(/text/);
    });

    it('успех → CLIPBOARD_COPIED + toast (если success_i18n_key)', async () => {
        const dispatched: DispatchedRecord[] = [];
        await createUiEffect()(
            ev(CoreEvents.UI_CLIPBOARD_COPY_REQUESTED, { text: 'hello', success_i18n_key: 'ok' }),
            buildCtx(() => ({}), dispatched),
        );
        const types = dispatched.map((d) => d.type);
        expect(types).toContain(CoreEvents.UI_CLIPBOARD_COPIED);
        expect(types).toContain(CoreEvents.UI_TOAST_SHOW);
    });

    it('ошибка → CLIPBOARD_COPY_FAILED + error toast', async () => {
        Object.defineProperty(globalThis.navigator, 'clipboard', {
            value: { writeText: vi.fn(async () => { throw new Error('denied'); }) },
            configurable: true,
        });
        const dispatched: DispatchedRecord[] = [];
        await createUiEffect()(
            ev(CoreEvents.UI_CLIPBOARD_COPY_REQUESTED, { text: 'hi', error_i18n_key: 'err' }),
            buildCtx(() => ({}), dispatched),
        );
        const failed = dispatched.find((d) => d.type === CoreEvents.UI_CLIPBOARD_COPY_FAILED);
        expect(failed).toBeTruthy();
    });
});

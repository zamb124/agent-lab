/**
 * Contract: assertEventType, createEvent, CoreEvents.
 *
 * Все имена событий обязаны проходить EVENT_TYPE_PATTERN
 * (`<scope>/<entity>/<verb>` lowercase snake_case, >= 3 сегмента).
 * Источник `meta.source` — закрытое множество.
 */

import { describe, it, expect } from 'vitest';
import {
    assertEventType,
    createEvent,
    CoreEvents,
    CORE_SCOPES,
} from '@platform/lib/events/contract.js';

describe('assertEventType', () => {
    it('пропускает валидные имена', () => {
        for (const t of [
            'ui/toast/show',
            'auth/session/login_requested',
            'crm/note/created',
            'sync/messages/send_requested',
            'frontend/api_keys/list_loaded',
        ]) {
            expect(assertEventType(t)).toBe(t);
        }
    });

    it('бросает на невалидных именах', () => {
        for (const bad of [
            '',
            'foo',
            'foo/bar',
            'Foo/bar/baz',
            'foo/Bar/baz',
            'foo/bar/baz-qux',
            'foo//baz',
            123,
            null,
            undefined,
        ]) {
            expect(() => assertEventType(bad)).toThrow();
        }
    });
});

describe('createEvent', () => {
    it('заполняет id, ts, source, type, payload', () => {
        const before = Date.now();
        const ev = createEvent('ui/toast/show', { type: 'info' });
        const after = Date.now();
        expect(ev.type).toBe('ui/toast/show');
        expect(ev.payload).toEqual({ type: 'info' });
        expect(ev.id).toMatch(/^e_[a-z0-9]+_[a-z0-9]+_[a-z0-9]+$/);
        expect(ev.meta.source).toBe('local');
        expect(ev.meta.ts).toBeGreaterThanOrEqual(before);
        expect(ev.meta.ts).toBeLessThanOrEqual(after);
        expect(ev.meta.causation_id).toBeNull();
        expect(ev.meta.correlation_id).toBeNull();
        expect(ev.meta.trace_id).toBeNull();
    });

    it('payload undefined → null (zero-guess)', () => {
        const ev = createEvent('ui/toast/show');
        expect(ev.payload).toBeNull();
    });

    it('бросает на неизвестном source', () => {
        expect(() => createEvent('ui/toast/show', null, { source: 'cosmic' })).toThrow(/source/);
    });

    it('пропускает все валидные source', () => {
        for (const s of ['local', 'ws', 'http', 'router', 'storage', 'timer', 'system']) {
            const ev = createEvent('ui/toast/show', null, { source: s });
            expect(ev.meta.source).toBe(s);
        }
    });

    it('id монотонный (хотя бы _seq инкрементируется)', () => {
        const a = createEvent('ui/toast/show');
        const b = createEvent('ui/toast/show');
        expect(a.id).not.toBe(b.id);
    });
});

describe('CoreEvents', () => {
    it('каждое значение проходит assertEventType', () => {
        for (const [key, value] of Object.entries(CoreEvents)) {
            expect(() => assertEventType(value), `CoreEvents.${key} = ${value}`).not.toThrow();
        }
    });

    it('заморожен (Object.freeze)', () => {
        expect(Object.isFrozen(CoreEvents)).toBe(true);
    });
});

describe('CORE_SCOPES', () => {
    it('заморожен и содержит ожидаемые scope', () => {
        expect(Object.isFrozen(CORE_SCOPES)).toBe(true);
        for (const expected of ['UI', 'AUTH', 'THEME', 'I18N', 'ROUTER', 'NETWORK']) {
            expect(CORE_SCOPES).toHaveProperty(expected);
        }
    });
});

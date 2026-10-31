/**
 * Канон-тест имён событий: каждый exported реестр core-событий обязан проходить
 * assertEventType. Это страховка против опечаток (дефис вместо подчёркивания,
 * заглавные буквы, пропуск сегмента).
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { CoreEvents, assertEventType } from '@platform/lib/events/contract.js';
import { CoreAuthEvents } from '@platform/lib/events/effects/auth.effect.js';
import { ICON_EVENTS } from '@platform/lib/events/reducers/icon.js';
import { FILES_EVENTS } from '@platform/lib/events/reducers/files.js';
import { FILE_TYPES_EVENTS } from '@platform/lib/events/reducers/file-types.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import { TEAM_EVENTS } from '@platform/lib/events/reducers/team.js';
import { CALENDAR_EVENTS } from '@platform/lib/events/reducers/calendar.js';
import { NOTIFICATIONS_EVENTS } from '@platform/lib/events/reducers/notifications.js';
import { I18N_NAMESPACE_SET_REQUESTED } from '@platform/lib/events/reducers/i18n.js';
import { PWA_EVENTS } from '@platform/lib/events/effects/pwa.effect.js';
import { createAsyncOp } from '@platform/lib/events/factories/async-op.js';
import { createResourceCollection } from '@platform/lib/events/factories/resource-collection.js';
import { createForm } from '@platform/lib/events/factories/form.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

const REGISTRIES = [
    ['CoreEvents', CoreEvents],
    ['CoreAuthEvents', CoreAuthEvents],
    ['ICON_EVENTS', ICON_EVENTS],
    ['FILES_EVENTS', FILES_EVENTS],
    ['FILE_TYPES_EVENTS', FILE_TYPES_EVENTS],
    ['COMPANIES_EVENTS', COMPANIES_EVENTS],
    ['TEAM_EVENTS', TEAM_EVENTS],
    ['CALENDAR_EVENTS', CALENDAR_EVENTS],
    ['NOTIFICATIONS_EVENTS', NOTIFICATIONS_EVENTS],
    ['PWA_EVENTS', PWA_EVENTS],
];

describe('canon: every core event registry passes assertEventType', () => {
    for (const [label, registry] of REGISTRIES) {
        it(`${label} — все значения валидны`, () => {
            expect(typeof registry).toBe('object');
            const entries = Object.entries(registry);
            expect(entries.length).toBeGreaterThan(0);
            for (const [k, v] of entries) {
                expect(() => assertEventType(v), `${label}.${k} = ${v}`).not.toThrow();
            }
        });
    }

    it('I18N_NAMESPACE_SET_REQUESTED одиночный экспорт', () => {
        expect(() => assertEventType(I18N_NAMESPACE_SET_REQUESTED)).not.toThrow();
    });
});

describe('canon: factory-generated events also pass assertEventType', () => {
    beforeEach(() => resetFactories());
    afterEach(() => resetFactories());

    it('createAsyncOp генерирует валидные имена', () => {
        const op = createAsyncOp({
            name: 'svc/some_op', silent: true, request: async () => ({}),
            extraEvents: { CANCELLED: 'cancelled' },
            actions: { retry: 'retry_requested' },
        });
        for (const v of Object.values(op.events)) {
            expect(() => assertEventType(v)).not.toThrow();
        }
        for (const v of Object.values(op.actions)) {
            expect(() => assertEventType(v)).not.toThrow();
        }
    });

    it('createResourceCollection генерирует валидные имена', () => {
        const r = createResourceCollection({
            name: 'svc/items', baseUrl: '/api/items', idField: 'id',
            operations: ['list', 'create'],
            toastKeys: { create: 'svc:items.created' },
        });
        for (const v of Object.values(r.events)) {
            expect(() => assertEventType(v)).not.toThrow();
        }
    });

    it('createForm генерирует валидные имена', () => {
        const f = createForm({
            name: 'svc/login_form',
            schema: { email: {}, password: {} },
            initial: { email: '', password: '' },
            submitEvent: 'svc/auth/login_requested',
        });
        for (const v of Object.values(f.events)) {
            expect(() => assertEventType(v)).not.toThrow();
        }
    });
});

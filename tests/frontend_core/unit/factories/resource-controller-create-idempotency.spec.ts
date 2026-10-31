/**
 * Сериализованный create: ResourceController + slice createResourceCollection.
 * Инварианты: второй `create()` не уходит в bus; источник правды — reducer после
 * первого `dispatch` (тот же тик, до async effect). Соответствует слоям
 * ui_events: dispatch → reducer → state → controller.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createResourceCollection } from '@platform/lib/events/factories/resource-collection.js';
import type { ResourceCollectionOptions } from '@platform/lib/events/factories/resource-collection.js';
import { ResourceController } from '@platform/lib/base/use-resource.js';
import type { ControllerHost } from '@platform/lib/base/use-resource.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { resetPlatformBusForTests, setPlatformBus } from '@platform/lib/events/bus-singleton.js';
import type { PlatformBusLike } from '@platform/lib/events/bus-singleton.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { EventBus } from '@platform/lib/events/bus.js';
import { EventLog } from '@platform/lib/events/log.js';
import { buildPlatformReducer } from '@platform/lib/events/reducers/index.js';
import type { SliceDef } from '@platform/lib/events/reducers/index.js';

interface TestController {
    hostConnected?(): void;
}

interface TestHost extends ControllerHost {
    controllers: TestController[];
}

let dom: ReturnType<typeof installDomShim>;

const baseResOpts = (): ResourceCollectionOptions => ({
    name: 'svc/res_items',
    baseUrl: '/api/res_items',
    idField: 'id',
    operations: ['list', 'create', 'update', 'remove', 'get'],
    toastKeys: {
        create: 'svc:res_items.created',
        update: 'svc:res_items.updated',
        remove: 'svc:res_items.removed',
    },
});

function _buildPlatformBus(slices: Record<string, SliceDef>) {
    const { reducer, initialState } = buildPlatformReducer(slices);
    const log = new EventLog({ devMode: true });
    const bus = new EventBus({ reducer, initialState, log });
    return { bus, events: () => log.snapshot() };
}

function _makeHost(bus: PlatformBusLike): TestHost {
    const host: TestHost = {
        bus,
        controllers: [],
        addController(ctl: TestController) {
            host.controllers.push(ctl);
        },
        requestUpdate() {},
    };
    return host;
}

function _connectAll(host: TestHost): void {
    for (const c of host.controllers) {
        c.hostConnected?.();
    }
}

beforeEach(() => {
    dom = installDomShim();
    resetFactories();
    resetPlatformBusForTests();
});

afterEach(() => {
    resetPlatformBusForTests();
    resetFactories();
    dom.uninstall();
});

describe('ResourceController.create: идемпотентность до async effect', () => {
    it('второй create() возвращает undefined и не добавляет событие CREATE_REQUESTED', () => {
        const r = createResourceCollection(baseResOpts());
        const { bus, events } = _buildPlatformBus({ [r.sliceKey]: r.slice });
        setPlatformBus(bus);
        const host = _makeHost(bus);
        const ctl = new ResourceController(host, r, { autoload: false });
        _connectAll(host);

        const first = ctl.create({ name: 'a' });
        expect(typeof first).toBe('object');
        expect(first).not.toBeNull();
        expect(ctl.createInFlight).toBe(true);

        const second = ctl.create({ name: 'b' });
        expect(second).toBeUndefined();

        const createRequested = events().filter((e) => e.type === r.events.CREATE_REQUESTED);
        expect(createRequested).toHaveLength(1);
    });

    it('после CREATED в reducer (симуляция) второй create() снова диспатчит', () => {
        const r = createResourceCollection(baseResOpts());
        const { bus, events } = _buildPlatformBus({ [r.sliceKey]: r.slice });
        setPlatformBus(bus);
        const host = _makeHost(bus);
        const ctl = new ResourceController(host, r, { autoload: false });
        _connectAll(host);

        ctl.create({ name: 'first' });
        bus.dispatch(
            r.events.CREATED,
            { item: { id: 'i1', name: 'first' } },
            { source: 'http' },
        );
        expect(ctl.createInFlight).toBe(false);

        ctl.create({ name: 'second' });
        const n = events().filter((e) => e.type === r.events.CREATE_REQUESTED).length;
        expect(n).toBe(2);
    });
});

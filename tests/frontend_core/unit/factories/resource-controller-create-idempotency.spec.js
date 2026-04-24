/**
 * Сериализованный create: ResourceController + slice createResourceCollection.
 * Инварианты: второй `create()` не уходит в bus; источник правды — reducer после
 * первого `dispatch` (тот же тик, до async effect). Соответствует слоям
 * ui_events: dispatch → reducer → state → controller.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createResourceCollection } from '@platform/lib/events/factories/resource-collection.js';
import { ResourceController } from '@platform/lib/base/use-resource.js';
import { buildBus } from '../../helpers/bus-fixtures.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { resetPlatformBusForTests, setPlatformBus } from '@platform/lib/events/bus-singleton.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';

let dom;

const baseResOpts = () => ({
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

function _makeHost(bus) {
    return {
        bus,
        controllers: [],
        addController(ctl) {
            this.controllers.push(ctl);
        },
        requestUpdate() {},
    };
}

function _connectAll(host) {
    for (const c of host.controllers) {
        if (typeof c.hostConnected === 'function') {
            c.hostConnected();
        }
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
        const { bus, events } = buildBus({ slices: { [r.sliceKey]: r.slice } });
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
        const { bus, events } = buildBus({ slices: { [r.sliceKey]: r.slice } });
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

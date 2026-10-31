/**
 * SelectController — Lit Reactive Controller над платформенным bus.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { SelectController } from '@platform/lib/events/select-controller.js';
import { setPlatformBus, resetPlatformBusForTests } from '@platform/lib/events/bus-singleton.js';
import { installDomShim } from '../helpers/dom-shim.js';
import { buildEchoSlice } from '../helpers/bus-fixtures.js';
import { prop } from '../helpers/prop.js';
import { EventBus } from '@platform/lib/events/bus.js';
import { EventLog } from '@platform/lib/events/log.js';
import { buildPlatformReducer } from '@platform/lib/events/reducers/index.js';
import type { SliceDef } from '@platform/lib/events/reducers/index.js';
import type { PlatformBusState } from '@platform/lib/events/bus-state.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';

interface TestController {
    hostConnected(): void;
    hostDisconnected(): void;
}

interface BoxState {
    items: unknown;
    at: number;
}

let dom: ReturnType<typeof installDomShim>;

function _buildHost() {
    const host = {
        controllers: [] as TestController[],
        updates: 0,
        addController(ctl: TestController) { host.controllers.push(ctl); },
        requestUpdate() { host.updates += 1; },
    };
    return host;
}

function _buildPlatformBus(slices: Record<string, SliceDef>) {
    const { reducer, initialState } = buildPlatformReducer(slices);
    const log = new EventLog({ devMode: true });
    const bus = new EventBus({ reducer, initialState, log });
    return { bus };
}

beforeEach(() => {
    dom = installDomShim();
    resetPlatformBusForTests();
});

afterEach(() => {
    resetPlatformBusForTests();
    dom.uninstall();
});

describe('SelectController: contract', () => {
    it('требует selector-функцию', () => {
        const host = _buildHost();
        expect(() => Reflect.construct(SelectController, [host, null])).toThrow(/selector function required/);
        expect(() => Reflect.construct(SelectController, [host, 'not a function'])).toThrow();
    });

    it('добавляет себя в host.addController', () => {
        const host = _buildHost();
        const ctl = new SelectController(host, (s: Readonly<PlatformBusState>) => s);
        expect(host.controllers).toContain(ctl);
    });

    it('value до hostConnected — ошибка', () => {
        const host = _buildHost();
        const ctl = new SelectController(host, (s: Readonly<PlatformBusState>) => s);
        expect(() => ctl.value).toThrow(/before hostConnected/);
    });
});

describe('SelectController: lifecycle', () => {
    it('hostConnected читает value из bus.getState()', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = _buildPlatformBus(slice);
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s: Readonly<PlatformBusState>) => s['echo']);
        ctl.hostConnected();
        expect(ctl.value).toEqual({ lastType: null, lastPayload: null });
    });

    it('подписка на bus.subscribeSelector обновляет value и вызывает requestUpdate', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = _buildPlatformBus(slice);
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s: Readonly<PlatformBusState>) => s['echo']);
        ctl.hostConnected();
        const updatesBefore = host.updates;
        bus.dispatch('test/sample/changed', { x: 42 }, { source: 'local' });
        expect(ctl.value).toEqual({ lastType: 'test/sample/changed', lastPayload: { x: 42 } });
        expect(host.updates).toBe(updatesBefore + 1);
    });

    it('hostDisconnected отписывает от bus', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = _buildPlatformBus(slice);
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s: Readonly<PlatformBusState>) => s['echo']);
        ctl.hostConnected();
        ctl.hostDisconnected();
        const updatesBefore = host.updates;
        bus.dispatch('test/sample/again', { y: 1 }, { source: 'local' });
        expect(host.updates).toBe(updatesBefore);
    });
});

describe('SelectController: shallow equality', () => {
    it('не вызывает requestUpdate если новое value shallow-равно старому', () => {
        const slice: Record<string, SliceDef<BoxState>> = {
            box: {
                initial: { items: [], at: 0 },
                reducer(state: BoxState = { items: [], at: 0 }, event: PlatformEvent): BoxState {
                    if (event.type === 'box/touch/done') {
                        // тот же items-массив (по ссылке), только at меняется
                        return { ...state, at: state.at + 1 };
                    }
                    if (event.type === 'box/items/set') {
                        return { ...state, items: prop(event.payload, 'items') };
                    }
                    return state;
                },
            },
        };
        const { bus } = _buildPlatformBus(slice);
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s: Readonly<PlatformBusState>) => prop(s['box'], 'items'));
        ctl.hostConnected();
        const initialUpdates = host.updates;
        bus.dispatch('box/touch/done', null, { source: 'local' });
        // items по ссылке не изменился — равенство срабатывает
        expect(host.updates).toBe(initialUpdates);

        bus.dispatch('box/items/set', { items: ['a'] }, { source: 'local' });
        expect(host.updates).toBeGreaterThan(initialUpdates);
        expect(ctl.value).toEqual(['a']);
    });

    it('кастомный equality', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = _buildPlatformBus(slice);
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(
            host,
            (s: Readonly<PlatformBusState>) => s['echo'],
            { equality: () => true }, // никогда не triggers update
        );
        ctl.hostConnected();
        const updatesBefore = host.updates;
        bus.dispatch('test/x/y', { v: 1 }, { source: 'local' });
        expect(host.updates).toBe(updatesBefore);
    });
});

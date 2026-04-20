/**
 * SelectController — Lit Reactive Controller над платформенным bus.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { SelectController } from '@platform/lib/events/select-controller.js';
import { setPlatformBus, resetPlatformBusForTests } from '@platform/lib/events/bus-singleton.js';
import { installDomShim } from '../helpers/dom-shim.js';
import { buildBus, buildEchoSlice } from '../helpers/bus-fixtures.js';

let dom;

function _buildHost() {
    return {
        controllers: [],
        updates: 0,
        addController(ctl) { this.controllers.push(ctl); },
        requestUpdate() { this.updates += 1; },
    };
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
        expect(() => new SelectController(host, null)).toThrow(/selector function required/);
        expect(() => new SelectController(host, 'not a function')).toThrow();
    });

    it('добавляет себя в host.addController', () => {
        const host = _buildHost();
        const ctl = new SelectController(host, (s) => s);
        expect(host.controllers).toContain(ctl);
    });

    it('value = undefined до hostConnected', () => {
        const host = _buildHost();
        const ctl = new SelectController(host, (s) => s);
        expect(ctl.value).toBeUndefined();
    });
});

describe('SelectController: lifecycle', () => {
    it('hostConnected читает value из bus.getState()', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = buildBus({ slices: slice });
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s) => s.echo);
        ctl.hostConnected();
        expect(ctl.value).toEqual({ lastType: null, lastPayload: null });
    });

    it('подписка на bus.subscribeSelector обновляет value и вызывает requestUpdate', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = buildBus({ slices: slice });
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s) => s.echo);
        ctl.hostConnected();
        const updatesBefore = host.updates;
        bus.dispatch('test/sample/changed', { x: 42 }, { source: 'local' });
        expect(ctl.value).toEqual({ lastType: 'test/sample/changed', lastPayload: { x: 42 } });
        expect(host.updates).toBe(updatesBefore + 1);
    });

    it('hostDisconnected отписывает от bus', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = buildBus({ slices: slice });
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s) => s.echo);
        ctl.hostConnected();
        ctl.hostDisconnected();
        const updatesBefore = host.updates;
        bus.dispatch('test/sample/again', { y: 1 }, { source: 'local' });
        expect(host.updates).toBe(updatesBefore);
    });
});

describe('SelectController: shallow equality', () => {
    it('не вызывает requestUpdate если новое value shallow-равно старому', () => {
        const slice = {
            box: {
                initial: { items: [], at: 0 },
                reducer(state = { items: [], at: 0 }, event) {
                    if (event.type === 'box/touch/done') {
                        // тот же items-массив (по ссылке), только at меняется
                        return { ...state, at: state.at + 1 };
                    }
                    if (event.type === 'box/items/set') {
                        return { ...state, items: event.payload };
                    }
                    return state;
                },
            },
        };
        const { bus } = buildBus({ slices: slice });
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(host, (s) => s.box.items);
        ctl.hostConnected();
        const initialUpdates = host.updates;
        bus.dispatch('box/touch/done', null, { source: 'local' });
        // items по ссылке не изменился — равенство срабатывает
        expect(host.updates).toBe(initialUpdates);

        bus.dispatch('box/items/set', ['a'], { source: 'local' });
        expect(host.updates).toBeGreaterThan(initialUpdates);
        expect(ctl.value).toEqual(['a']);
    });

    it('кастомный equality', () => {
        const slice = buildEchoSlice('echo');
        const { bus } = buildBus({ slices: slice });
        setPlatformBus(bus);
        const host = _buildHost();
        const ctl = new SelectController(
            host,
            (s) => s.echo,
            { equality: () => true }, // никогда не triggers update
        );
        ctl.hostConnected();
        const updatesBefore = host.updates;
        bus.dispatch('test/x/y', { v: 1 }, { source: 'local' });
        expect(host.updates).toBe(updatesBefore);
    });
});

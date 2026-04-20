/**
 * OpController.run() контракт:
 *   - SUCCEEDED → resolve(result) (значение из event.payload.result).
 *   - FAILED    → resolve(null), ошибка кладётся в state.error slice.
 *
 * Никакого reject — fire-and-forget вызовы (`this._typing.run(...)`
 * без await/catch) не должны порождать unhandled promise rejection.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { createAsyncOp } from '@platform/lib/events/factories/async-op.js';
import { OpController } from '@platform/lib/base/use-resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { resetPlatformBusForTests, setPlatformBus } from '@platform/lib/events/bus-singleton.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { buildBus } from '../../helpers/bus-fixtures.js';

let dom;
let busHandle;

function _buildOp() {
    return createAsyncOp({
        name: 'svc/op_test',
        silent: true,
        request: async () => ({ ok: true }),
    });
}

function _buildHost(bus) {
    return {
        bus,
        addController: () => {},
        requestUpdate: () => {},
    };
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

describe('OpController.run: zero unhandled rejection contract', () => {
    it('resolve с result при SUCCEEDED', async () => {
        const op = _buildOp();
        busHandle = buildBus({ slices: { [op.sliceKey]: { initial: op.slice.initial, reducer: op.slice.reducer } } });
        setPlatformBus(busHandle.bus);
        const host = _buildHost(busHandle.bus);
        const ctl = new OpController(host, op);

        const promise = ctl.run({ x: 1 });
        // Эмулируем serverside SUCCEEDED reply от effect'а: dispatch event с result в payload
        // и meta.causation_id = id REQUESTED-события.
        const requestedEvents = busHandle.events().filter((e) => e.type === op.events.REQUESTED);
        expect(requestedEvents).toHaveLength(1);
        const requestedId = requestedEvents[0].id;
        busHandle.bus.dispatch(
            op.events.SUCCEEDED,
            { result: { ok: true, n: 42 } },
            { causation_id: requestedId, source: 'system' },
        );
        await expect(promise).resolves.toEqual({ ok: true, n: 42 });
    });

    it('resolve с null при FAILED — без reject', async () => {
        const op = _buildOp();
        busHandle = buildBus({ slices: { [op.sliceKey]: { initial: op.slice.initial, reducer: op.slice.reducer } } });
        setPlatformBus(busHandle.bus);
        const host = _buildHost(busHandle.bus);
        const ctl = new OpController(host, op);

        const promise = ctl.run({ x: 1 });
        const requestedEvents = busHandle.events().filter((e) => e.type === op.events.REQUESTED);
        const requestedId = requestedEvents[0].id;
        busHandle.bus.dispatch(
            op.events.FAILED,
            { message: 'Boom', code: 'forbidden' },
            { causation_id: requestedId, source: 'system' },
        );
        await expect(promise).resolves.toBeNull();
    });

    it('fire-and-forget run() не throws unhandled rejection при FAILED', async () => {
        const op = _buildOp();
        busHandle = buildBus({ slices: { [op.sliceKey]: { initial: op.slice.initial, reducer: op.slice.reducer } } });
        setPlatformBus(busHandle.bus);
        const host = _buildHost(busHandle.bus);
        const ctl = new OpController(host, op);

        // Caller НЕ делает await и НЕ навешивает .catch — это типичный fire-and-forget
        // (например, this._typing.run({...}) на каждом keystroke).
        const unhandledHandler = (event) => {
            throw new Error(`unhandled rejection leaked: ${event.reason}`);
        };
        if (typeof process !== 'undefined' && typeof process.on === 'function') {
            process.on('unhandledRejection', unhandledHandler);
        }
        try {
            ctl.run({ x: 1 });
            const requestedEvents = busHandle.events().filter((e) => e.type === op.events.REQUESTED);
            const requestedId = requestedEvents[0].id;
            busHandle.bus.dispatch(
                op.events.FAILED,
                { message: 'Boom', code: 'forbidden' },
                { causation_id: requestedId, source: 'system' },
            );
            // Ждём microtask: если бы был reject — handler сработал бы.
            await new Promise((r) => setTimeout(r, 0));
        } finally {
            if (typeof process !== 'undefined' && typeof process.off === 'function') {
                process.off('unhandledRejection', unhandledHandler);
            }
        }
    });

    it('игнорирует FAILED с другим causation_id', async () => {
        const op = _buildOp();
        busHandle = buildBus({ slices: { [op.sliceKey]: { initial: op.slice.initial, reducer: op.slice.reducer } } });
        setPlatformBus(busHandle.bus);
        const host = _buildHost(busHandle.bus);
        const ctl = new OpController(host, op);

        const promise = ctl.run({ x: 1 });
        // FAILED от чужого запроса — не должен резолвить наш promise.
        busHandle.bus.dispatch(
            op.events.FAILED,
            { message: 'other request', code: 'unrelated' },
            { causation_id: 'other_id', source: 'system' },
        );

        // Наш SUCCEEDED дойдёт корректно.
        const requestedEvents = busHandle.events().filter((e) => e.type === op.events.REQUESTED);
        const requestedId = requestedEvents[0].id;
        busHandle.bus.dispatch(
            op.events.SUCCEEDED,
            { result: { v: 'ok' } },
            { causation_id: requestedId, source: 'system' },
        );
        await expect(promise).resolves.toEqual({ v: 'ok' });
    });
});

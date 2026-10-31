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
import type { AsyncOpFactory } from '@platform/lib/events/factories/async-op.js';
import { OpController } from '@platform/lib/base/use-resource.js';
import type { ControllerHost } from '@platform/lib/base/use-resource.js';
import { resetFactories } from '../../helpers/factory-fixtures.js';
import { resetPlatformBusForTests, setPlatformBus } from '@platform/lib/events/bus-singleton.js';
import type { PlatformBusLike } from '@platform/lib/events/bus-singleton.js';
import { installDomShim } from '../../helpers/dom-shim.js';
import { EventBus } from '@platform/lib/events/bus.js';
import { EventLog } from '@platform/lib/events/log.js';
import { buildPlatformReducer } from '@platform/lib/events/reducers/index.js';
import type { SliceDef } from '@platform/lib/events/reducers/index.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';

interface NodeLikeProcess {
    on?(event: string, handler: (reason: unknown) => void): void;
    off?(event: string, handler: (reason: unknown) => void): void;
}

let dom: ReturnType<typeof installDomShim>;
let busHandle: ReturnType<typeof _buildPlatformBus>;

function _buildPlatformBus(slices: Record<string, SliceDef>) {
    const { reducer, initialState } = buildPlatformReducer(slices);
    const log = new EventLog({ devMode: true });
    const bus = new EventBus({ reducer, initialState, log });
    return { bus, log, events: () => log.snapshot() };
}

function _buildOp() {
    return createAsyncOp({
        name: 'svc/op_test',
        silent: true,
        request: async () => ({ ok: true }),
    });
}

function _buildHost(bus: PlatformBusLike): ControllerHost {
    return {
        bus,
        addController: () => {},
        requestUpdate: () => {},
    };
}

function _evType(op: AsyncOpFactory, key: string): string {
    const t = op.events[key];
    if (typeof t !== 'string') throw new Error(`op.events.${key} missing`);
    return t;
}

function _requestedId(op: AsyncOpFactory): string {
    const ev = busHandle.events().find((e: PlatformEvent) => e.type === op.events.REQUESTED);
    if (!ev) throw new Error('REQUESTED event was not dispatched');
    return ev.id;
}

function _setup() {
    const op = _buildOp();
    busHandle = _buildPlatformBus({ [op.sliceKey]: op.slice });
    setPlatformBus(busHandle.bus);
    const host = _buildHost(busHandle.bus);
    const ctl = new OpController(host, op);
    return { op, ctl };
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
        const { op, ctl } = _setup();

        const promise = ctl.run({ x: 1 });
        // Эмулируем serverside SUCCEEDED reply от effect'а: dispatch event с result в payload
        // и meta.causation_id = id REQUESTED-события.
        const requestedId = _requestedId(op);
        busHandle.bus.dispatch(
            _evType(op, 'SUCCEEDED'),
            { result: { ok: true, n: 42 } },
            { causation_id: requestedId, source: 'system' },
        );
        await expect(promise).resolves.toEqual({ ok: true, n: 42 });
    });

    it('resolve с null при FAILED — без reject', async () => {
        const { op, ctl } = _setup();

        const promise = ctl.run({ x: 1 });
        const requestedId = _requestedId(op);
        busHandle.bus.dispatch(
            _evType(op, 'FAILED'),
            { message: 'Boom', code: 'forbidden' },
            { causation_id: requestedId, source: 'system' },
        );
        await expect(promise).resolves.toBeNull();
        expect(ctl.failureStatus).toBeNull();
    });

    it('FAILED с HTTP status запоминает failureStatus', async () => {
        const { op, ctl } = _setup();

        const promise = ctl.run({ x: 1 });
        const requestedId = _requestedId(op);
        busHandle.bus.dispatch(
            _evType(op, 'FAILED'),
            { message: 'missing', status: 404 },
            { causation_id: requestedId, source: 'http' },
        );
        await expect(promise).resolves.toBeNull();
        expect(ctl.error).toBe('missing');
        expect(ctl.failureStatus).toBe(404);
    });

    it('fire-and-forget run() не throws unhandled rejection при FAILED', async () => {
        const { op, ctl } = _setup();

        // Caller НЕ делает await и НЕ навешивает .catch — это типичный fire-and-forget
        // (например, this._typing.run({...}) на каждом keystroke).
        const unhandledHandler = (reason: unknown) => {
            throw new Error(`unhandled rejection leaked: ${String(reason)}`);
        };
        const proc: NodeLikeProcess | undefined = Reflect.get(globalThis, 'process');
        if (proc && typeof proc.on === 'function') {
            proc.on('unhandledRejection', unhandledHandler);
        }
        try {
            ctl.run({ x: 1 });
            const requestedId = _requestedId(op);
            busHandle.bus.dispatch(
                _evType(op, 'FAILED'),
                { message: 'Boom', code: 'forbidden' },
                { causation_id: requestedId, source: 'system' },
            );
            // Ждём microtask: если бы был reject — handler сработал бы.
            await new Promise((r) => setTimeout(r, 0));
        } finally {
            if (proc && typeof proc.off === 'function') {
                proc.off('unhandledRejection', unhandledHandler);
            }
        }
    });

    it('игнорирует FAILED с другим causation_id', async () => {
        const { op, ctl } = _setup();

        const promise = ctl.run({ x: 1 });
        // FAILED от чужого запроса — не должен резолвить наш promise.
        busHandle.bus.dispatch(
            _evType(op, 'FAILED'),
            { message: 'other request', code: 'unrelated' },
            { causation_id: 'other_id', source: 'system' },
        );

        // Наш SUCCEEDED дойдёт корректно.
        const requestedId = _requestedId(op);
        busHandle.bus.dispatch(
            _evType(op, 'SUCCEEDED'),
            { result: { v: 'ok' } },
            { causation_id: requestedId, source: 'system' },
        );
        await expect(promise).resolves.toEqual({ v: 'ok' });
    });
});

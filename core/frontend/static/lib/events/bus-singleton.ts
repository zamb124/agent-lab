/**
 * Глобальный singleton EventBus — единственная точка доступа из компонентов.
 *
 * EventBus создаётся в PlatformApp.bootstrap (см. base/PlatformApp.js). До этого
 * вызовы getPlatformBus() бросают исключение — это инвариант: ни один компонент
 * не может работать вне приложения.
 */

import type { PlatformEvent, EventMetaInput } from './contract.js';
import type { PlatformBusState } from './bus-state.js';

export interface PlatformBusLike {
    dispatch: (event: PlatformEvent | string, payload?: unknown, meta?: EventMetaInput) => PlatformEvent | null;
    getState: () => Readonly<PlatformBusState>;
    subscribeType: (type: string, callback: (event: PlatformEvent) => void) => () => void;
    subscribeSelector: <V>(
        selector: (state: Readonly<PlatformBusState>) => V,
        callback: (value: V, prevValue: V | undefined) => void,
        opts?: { equality?: (a: V, b: V) => boolean },
    ) => () => void;
    subscribeAny: (callback: (event: PlatformEvent) => void) => () => void;
}

const KEY = '__PLATFORM_BUS__' as const;

declare global {
    interface Window {
        __PLATFORM_BUS__?: PlatformBusLike;
    }
}

/**
 * Потребитель bus, подключившийся до того, как PlatformApp его поднял.
 *
 * DSD-гидратация апгрейдит элементы при customElements.define — порядок задаёт
 * разметка снапшота, а не граф модулей, поэтому hostConnected контроллера может
 * прийти раньше setPlatformBus. Контроллер ждёт в очереди и получает
 * bindPlatformBus синхронно в момент установки bus — до того, как Lit выполнит
 * первый render на микротасках.
 */
export interface PlatformBusConsumer {
    bindPlatformBus(bus: PlatformBusLike): void;
}

const _pendingConsumers = new Set<PlatformBusConsumer>();

export function awaitPlatformBus(consumer: PlatformBusConsumer): void {
    _pendingConsumers.add(consumer);
}

export function cancelPlatformBusWait(consumer: PlatformBusConsumer): void {
    _pendingConsumers.delete(consumer);
}

export function setPlatformBus(bus: PlatformBusLike): void {
    if (typeof window === 'undefined') {
        throw new Error('setPlatformBus: window unavailable');
    }
    if (!bus || typeof bus.dispatch !== 'function') {
        throw new Error('setPlatformBus: invalid bus');
    }
    if (window[KEY] && window[KEY] !== bus) {
        throw new Error('setPlatformBus: bus already initialized');
    }
    window[KEY] = bus;
    const pending = [..._pendingConsumers];
    _pendingConsumers.clear();
    for (const consumer of pending) {
        consumer.bindPlatformBus(bus);
    }
}

export function getPlatformBus(): PlatformBusLike {
    if (typeof window === 'undefined') {
        throw new Error('getPlatformBus: window unavailable');
    }
    const bus = window[KEY];
    if (!bus) {
        throw new Error('getPlatformBus: bus not initialized; PlatformApp must bootstrap first');
    }
    return bus;
}

export function hasPlatformBus(): boolean {
    return typeof window !== 'undefined' && Boolean(window[KEY]);
}

/** Только для тестов: сброс. */
export function resetPlatformBusForTests(): void {
    _pendingConsumers.clear();
    if (typeof window !== 'undefined') {
        delete window[KEY];
    }
}

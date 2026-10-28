/**
 * Минимальный devtools-оверлей для EventBus.
 *
 * Включается через ?platform_devtools=1 или window.__PLATFORM_DEVTOOLS__ = true
 * до создания bus. Пишет последние события в консоль и кладёт api на window:
 *   window.__platformDevtools__ = { trail(), state(), replay(), clear() }
 *
 * Полноценный UI-оверлей — отдельная задача; здесь — только API.
 */

import type { EventBus } from './bus.js';
import type { PlatformBusState } from './bus-state.js';
import type { EventLog } from './log.js';
import type { PlatformEvent, EventMetaInput } from './contract.js';

declare global {
    interface Window {
        __PLATFORM_DEVTOOLS__?: boolean;
        __platformDevtools__?: {
            trail: (limit?: number) => PlatformEvent[];
            state: () => unknown;
            dispatch: (type: string, payload?: unknown, meta?: EventMetaInput) => PlatformEvent | null;
            clear: () => void;
        };
    }
}

/** Единственный флаг диагностики: `?platform_devtools=1` или `window.__PLATFORM_DEVTOOLS__ = true`. */
export function isPlatformDevtoolsEnabled(): boolean {
    return typeof window !== 'undefined'
        && (window.__PLATFORM_DEVTOOLS__ === true || /[?&]platform_devtools=1\b/.test(location.search));
}

/** Диагностическая запись подсистемы; без флага devtools ничего не пишет. */
export function devtoolsLog(scope: string, message: string, payload?: unknown): void {
    if (!isPlatformDevtoolsEnabled()) return;
    // eslint-disable-next-line no-console
    console.debug(`[${scope}]`, message, payload);
}

export function maybeAttachDevtools(bus: EventBus<PlatformBusState>, log: EventLog): void {
    if (!isPlatformDevtoolsEnabled()) return;

    bus.subscribeAny((event: PlatformEvent) => {
        // eslint-disable-next-line no-console
        console.debug('[bus]', event.type, event.payload, event.meta);
    });

    window.__platformDevtools__ = {
        trail: (limit?: number) => log.snapshot(limit),
        state: () => bus.getState(),
        dispatch: (type: string, payload?: unknown, meta?: EventMetaInput) => bus.dispatch(type, payload, meta),
        clear: () => log.reset(),
    };
}

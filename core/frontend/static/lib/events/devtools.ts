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

export function maybeAttachDevtools(bus: EventBus, log: EventLog): void {
    if (typeof window === 'undefined') return;
    const enabled = window.__PLATFORM_DEVTOOLS__ === true
        || /[?&]platform_devtools=1\b/.test(location.search);
    if (!enabled) return;

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

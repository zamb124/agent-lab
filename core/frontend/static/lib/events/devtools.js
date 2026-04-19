/**
 * Минимальный devtools-оверлей для EventBus.
 *
 * Включается через ?platform_devtools=1 или window.__PLATFORM_DEVTOOLS__ = true
 * до создания bus. Пишет последние события в консоль и кладёт api на window:
 *   window.__platformDevtools__ = { trail(), state(), replay(), clear() }
 *
 * Полноценный UI-оверлей — отдельная задача; здесь — только API.
 */

export function maybeAttachDevtools(bus, log) {
    if (typeof window === 'undefined') return;
    const enabled = window.__PLATFORM_DEVTOOLS__ === true
        || /[?&]platform_devtools=1\b/.test(location.search);
    if (!enabled) return;

    bus.subscribeAny((event) => {
        // eslint-disable-next-line no-console
        console.debug('[bus]', event.type, event.payload, event.meta);
    });

    window.__platformDevtools__ = {
        trail: (limit) => log.snapshot(limit),
        state: () => bus.getState(),
        dispatch: (type, payload, meta) => bus.dispatch(type, payload, meta),
        clear: () => log.reset(),
    };
}

/**
 * Глобальный singleton EventBus — единственная точка доступа из компонентов.
 *
 * EventBus создаётся в PlatformApp.bootstrap (см. base/PlatformApp.js). До этого
 * вызовы getPlatformBus() бросают исключение — это инвариант: ни один компонент
 * не может работать вне приложения.
 */

const KEY = '__PLATFORM_BUS__';

export function setPlatformBus(bus) {
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
}

export function getPlatformBus() {
    if (typeof window === 'undefined') {
        throw new Error('getPlatformBus: window unavailable');
    }
    const bus = window[KEY];
    if (!bus) {
        throw new Error('getPlatformBus: bus not initialized; PlatformApp must bootstrap first');
    }
    return bus;
}

export function hasPlatformBus() {
    return typeof window !== 'undefined' && Boolean(window[KEY]);
}

/** Только для тестов: сброс. */
export function resetPlatformBusForTests() {
    if (typeof window !== 'undefined') {
        delete window[KEY];
    }
}

/**
 * Реестр фабрик — singleton lookup фабрики по имени.
 *
 * Назначение: страница/модалка достаёт фабрику (resource-collection / async-op /
 * form / cursor-list / facets / slice) по строковому имени без явного импорта
 * объекта. Регистрация происходит один раз при boot'е PlatformApp через
 * `static factories`.
 *
 * Контракт:
 *   - Имя фабрики уникально в рамках процесса. Повторная регистрация под
 *     тем же именем — `throw` (zero-guess).
 *   - Запрос несуществующей фабрики или фабрики не того kind — `throw`.
 *   - Никаких неявных дефолтов. Если что-то не так, падаем сразу.
 */

const KNOWN_KINDS = new Set([
    'async-op',
    'resource-collection',
    'cursor-list',
    'facets',
    'form',
    'slice',
]);

const _registry = new Map();

export function registerFactory(factory) {
    if (!factory || typeof factory !== 'object') {
        throw new Error('registerFactory: factory object required');
    }
    if (typeof factory.name !== 'string' || factory.name.length === 0) {
        throw new Error('registerFactory: factory.name required');
    }
    if (!KNOWN_KINDS.has(factory.kind)) {
        throw new Error(`registerFactory: unknown factory.kind "${factory.kind}" (factory: ${factory.name})`);
    }
    if (_registry.has(factory.name)) {
        const existing = _registry.get(factory.name);
        if (existing === factory) return factory;
        throw new Error(`registerFactory: factory "${factory.name}" already registered with a different instance`);
    }
    _registry.set(factory.name, factory);
    return factory;
}

export function getFactory(name, expectedKind) {
    if (typeof name !== 'string' || name.length === 0) {
        throw new Error('getFactory: name required');
    }
    const factory = _registry.get(name);
    if (!factory) {
        throw new Error(`getFactory: factory "${name}" not registered. Did you add it to static factories of your PlatformApp?`);
    }
    if (expectedKind && factory.kind !== expectedKind) {
        throw new Error(`getFactory: factory "${name}" has kind "${factory.kind}", expected "${expectedKind}"`);
    }
    return factory;
}

export function hasFactory(name) {
    return _registry.has(name);
}

export function clearFactoryRegistry() {
    _registry.clear();
}

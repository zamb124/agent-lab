/**
 * Реестр фабрик — singleton lookup фабрики по имени.
 *
 * Назначение: страница/модалка достаёт фабрику (resource-collection / async-op /
 * form / cursor-list / facets / slice) по строковому имени без явного импорта
 * объекта. Регистрация происходит внутри `create*`-хелперов при eval'е модуля
 * фабрики — до апгрейда custom elements при DSD-гидратации снапшота.
 * `static factories` в PlatformApp нужен только для сборки slices/effects в bus.
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

export type FactoryKind = 'async-op' | 'resource-collection' | 'cursor-list' | 'facets' | 'form' | 'slice';

export interface PlatformFactory {
    name: string;
    kind: FactoryKind;
    [key: string]: unknown;
}

/** `actions` фабрики: имя метода контроллера → полный тип события. */
export type ActionMap = Readonly<Record<string, string>>;

/**
 * Типовой реестр имён: каждый модуль фабрик расширяет его module augmentation
 * `declare module '@platform/lib/events/factory-registry.js' { interface PlatformFactoryRegistry { '<svc>/<entity>': typeof factory } }`.
 * Helpers `use*` принимают только зарегистрированное имя своего вида и выводят из него тип контроллера;
 * повтор имени с другим типом фабрики — ошибка компиляции.
 */
export interface PlatformFactoryRegistry {}

export type PlatformFactoryName = keyof PlatformFactoryRegistry & string;

export type FactoryNameOfKind<K extends FactoryKind> = {
    [N in PlatformFactoryName]: PlatformFactoryRegistry[N] extends { kind: K } ? N : never;
}[PlatformFactoryName];

const _registry = new Map<string, PlatformFactory>();

export function registerFactory<T extends PlatformFactory>(factory: T): T {
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
        const existing: unknown = _registry.get(factory.name);
        if (existing === factory) return factory;
        throw new Error(`registerFactory: factory "${factory.name}" already registered with a different instance`);
    }
    _registry.set(factory.name, factory);
    return factory;
}

function isRegistryFactory<N extends PlatformFactoryName>(
    factory: unknown,
    name: N,
    expectedKind: PlatformFactoryRegistry[N]['kind'],
): factory is PlatformFactoryRegistry[N] {
    if (!factory || typeof factory !== 'object') return false;
    if (!('name' in factory) || !('kind' in factory)) return false;
    return factory.name === name && factory.kind === expectedKind;
}

export function getFactory<N extends PlatformFactoryName>(name: N, expectedKind: PlatformFactoryRegistry[N]['kind']): PlatformFactoryRegistry[N] {
    if (typeof name !== 'string' || name.length === 0) {
        throw new Error('getFactory: name required');
    }
    const factory = _registry.get(name);
    if (!factory) {
        throw new Error(`getFactory: factory "${name}" not registered. Did you add it to static factories of your PlatformApp?`);
    }
    if (factory.kind !== expectedKind) {
        throw new Error(`getFactory: factory "${name}" has kind "${factory.kind}", expected "${expectedKind}"`);
    }
    if (!isRegistryFactory(factory, name, expectedKind)) {
        throw new Error(`getFactory: factory "${name}" is not the registered instance`);
    }
    return factory;
}

export function hasFactory(name: string): boolean {
    return _registry.has(name);
}

export function clearFactoryRegistry(): void {
    _registry.clear();
}

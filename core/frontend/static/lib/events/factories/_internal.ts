/**
 * Внутренние утилиты фабрик. Не экспортируются наружу пакета.
 */

import { assertEventType } from '../contract.js';

const NAME_PATTERN = /^[a-z][a-z0-9_]*\/[a-z][a-z0-9_]*$/;

/**
 * Проверить имя ресурса/операции (`scope/entity`). Бросает на нарушении.
 */
export function assertResourceName(name: unknown): asserts name is string {
    if (typeof name !== 'string' || !NAME_PATTERN.test(name)) {
        throw new Error(
            `Resource name "${name}" violates contract. Expected scope/entity (lowercase, snake_case, exactly 2 segments).`,
        );
    }
}

/**
 * Из `<scope>/<entity>` собрать `scopeEntity` (lowerCamelCase, segmenty по `_`).
 */
export function deriveSliceKey(name: string): string {
    assertResourceName(name);
    const [scope, entity] = name.split('/') as [string, string];
    return _toCamel(scope) + _capitalize(_toCamel(entity));
}

function _toCamel(s: string): string {
    return s.split('_').map((part, idx) => (idx === 0 ? part : _capitalize(part))).join('');
}

function _capitalize(s: string): string {
    if (s.length === 0) return s;
    return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Сформировать имя события `${name}/${verb}` и провалидировать.
 */
export function buildEventType(name: string, verb: string): string {
    if (typeof verb !== 'string' || verb.length === 0) {
        throw new Error('buildEventType: verb required');
    }
    const t = `${name}/${verb}`;
    return assertEventType(t);
}

/**
 * Реестр зарегистрированных имён ресурсов. Защита от дубликатов.
 */
const _registry = new Map<string, unknown>();

export function registerResourceName(name: string, owner?: unknown): void {
    if (_registry.has(name)) {
        throw new Error(`Resource name "${name}" is already registered by another factory.`);
    }
    _registry.set(name, owner || true);
}

export function _resetResourceRegistryForTests(): void {
    _registry.clear();
}

/**
 * Заморозить структуру глубоко (одного уровня хватает: state выстраиваем сами).
 */
export function freeze<T>(value: T): T {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
        return Object.freeze(value);
    }
    return value;
}

/**
 * Безопасный assert: бросает с понятным контекстом.
 */
export function requireField<T, K extends keyof T>(obj: T | null | undefined, field: K, context: string): NonNullable<T[K]> {
    if (obj === null || obj === undefined || obj[field] === undefined || obj[field] === null) {
        throw new Error(`${context}: option "${String(field)}" is required`);
    }
    return obj[field] as NonNullable<T[K]>;
}

export function requireFunction<T extends (...args: never[]) => unknown>(value: unknown, context: string): T {
    if (typeof value !== 'function') {
        throw new Error(`${context}: must be a function`);
    }
    return value as T;
}

export function requireI18nKey(value: unknown, context: string): string {
    if (typeof value !== 'string' || value.length === 0 || !value.includes(':')) {
        throw new Error(`${context}: i18n key required (format "namespace:key")`);
    }
    return value;
}

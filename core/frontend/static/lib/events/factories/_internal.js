/**
 * Внутренние утилиты фабрик. Не экспортируются наружу пакета.
 */

import { assertEventType } from '../contract.js';

const NAME_PATTERN = /^[a-z][a-z0-9_]*\/[a-z][a-z0-9_]*$/;

/**
 * Проверить имя ресурса/операции (`scope/entity`). Бросает на нарушении.
 */
export function assertResourceName(name) {
    if (typeof name !== 'string' || !NAME_PATTERN.test(name)) {
        throw new Error(
            `Resource name "${name}" violates contract. Expected scope/entity (lowercase, snake_case, exactly 2 segments).`,
        );
    }
}

/**
 * Из `<scope>/<entity>` собрать `scopeEntity` (lowerCamelCase, segmenty по `_`).
 */
export function deriveSliceKey(name) {
    assertResourceName(name);
    const [scope, entity] = name.split('/');
    return _toCamel(scope) + _capitalize(_toCamel(entity));
}

function _toCamel(s) {
    return s.split('_').map((part, idx) => (idx === 0 ? part : _capitalize(part))).join('');
}

function _capitalize(s) {
    if (s.length === 0) return s;
    return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Сформировать имя события `${name}/${verb}` и провалидировать.
 */
export function buildEventType(name, verb) {
    if (typeof verb !== 'string' || verb.length === 0) {
        throw new Error('buildEventType: verb required');
    }
    const t = `${name}/${verb}`;
    return assertEventType(t);
}

/**
 * Реестр зарегистрированных имён ресурсов. Защита от дубликатов.
 */
const _registry = new Map();

export function registerResourceName(name, owner) {
    if (_registry.has(name)) {
        throw new Error(`Resource name "${name}" is already registered by another factory.`);
    }
    _registry.set(name, owner || true);
}

export function _resetResourceRegistryForTests() {
    _registry.clear();
}

/**
 * Заморозить структуру глубоко (одного уровня хватает: state выстраиваем сами).
 */
export function freeze(value) {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
        return Object.freeze(value);
    }
    return value;
}

/**
 * Безопасный assert: бросает с понятным контекстом.
 */
export function requireField(obj, field, context) {
    if (obj === null || obj === undefined || obj[field] === undefined || obj[field] === null) {
        throw new Error(`${context}: option "${field}" is required`);
    }
    return obj[field];
}

export function requireFunction(value, context) {
    if (typeof value !== 'function') {
        throw new Error(`${context}: must be a function`);
    }
    return value;
}

export function requireI18nKey(value, context) {
    if (typeof value !== 'string' || value.length === 0 || !value.includes(':')) {
        throw new Error(`${context}: i18n key required (format "namespace:key")`);
    }
    return value;
}

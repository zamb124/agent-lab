/**
 * Тело события. `null` — команда без полей. Не-объект, кроме `null`, — ошибка контракта.
 */

import type { PlatformEvent } from './contract.js';

export function isPlainRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/**
 * Поля payload. `null` и `undefined` — пустое событие (команда без полей).
 * Массив, строка и число — сломанный контракт.
 */
export function payloadFields(event: PlatformEvent): Record<string, unknown> {
    if (event.payload === null || event.payload === undefined) {
        return {};
    }
    if (!isPlainRecord(event.payload)) {
        throw new Error(`${event.type}: object payload required`);
    }
    return event.payload;
}

/** Нет поля или null — пустой объект. Иной тип — ошибка контракта. */
export function recordField(value: unknown, label: string): Record<string, unknown> {
    if (value === undefined || value === null) {
        return {};
    }
    if (!isPlainRecord(value)) {
        throw new Error(`${label} must be an object`);
    }
    return value;
}

export function stringField(value: unknown): string | null {
    return typeof value === 'string' && value.length > 0 ? value : null;
}

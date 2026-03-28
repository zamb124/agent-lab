/**
 * Нейтральные утилиты нормализации ссылок на сущности/пространства.
 */

export function resolveObjectName(value, emptyValue = null) {
    if (value == null) {
        return emptyValue;
    }
    if (typeof value === 'string') {
        const normalized = value.trim();
        return normalized.length > 0 ? normalized : emptyValue;
    }
    if (typeof value === 'object' && typeof value.name === 'string') {
        const normalized = value.name.trim();
        return normalized.length > 0 ? normalized : emptyValue;
    }
    throw new Error('Invalid object name value');
}

/**
 * Утилиты валидации
 */

export function isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
}

export function isValidUrl(url) {
    try {
        new URL(url);
        return true;
    } catch (e) {
        return false;
    }
}

export function isValidVariableName(name) {
    return /^[a-z_][a-z0-9_]*$/.test(name);
}

export function validateRequired(value, fieldName) {
    if (!value || (typeof value === 'string' && !value.trim())) {
        throw new Error(`${fieldName} обязательно для заполнения`);
    }
    return true;
}

export function validateMinMax(value, min, max, fieldName) {
    if (value < min || value > max) {
        throw new Error(`${fieldName} должно быть между ${min} и ${max}`);
    }
    return true;
}


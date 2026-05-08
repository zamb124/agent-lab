/**
 * Канонические regex-валидаторы для frontend.
 * Один источник правды; локальные `EMAIL_RE` в apps запрещены.
 */

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Минимум 10 цифр (российский телефон с любым форматом ввода). */
export const PHONE_DIGITS_MIN = 10;

const _DIGIT_RE = /\D+/g;

/**
 * @param {unknown} value
 * @returns {boolean}
 */
export function isValidEmail(value) {
    return typeof value === 'string' && EMAIL_RE.test(value.trim());
}

/**
 * Извлекает только цифры из строки.
 * @param {unknown} value
 * @returns {string}
 */
export function digitsOnly(value) {
    return typeof value === 'string' ? value.replace(_DIGIT_RE, '') : '';
}

/**
 * Базовая проверка телефона: не <PHONE_DIGITS_MIN цифр.
 * @param {unknown} value
 * @returns {boolean}
 */
export function isValidPhone(value) {
    return digitsOnly(value).length >= PHONE_DIGITS_MIN;
}

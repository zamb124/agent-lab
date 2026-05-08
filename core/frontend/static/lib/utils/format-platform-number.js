/**
 * Форматирование чисел и валюты с учётом активной локали.
 *
 * Локаль передаётся аргументом (компонент берёт её через
 * `this.select((s) => s.i18n.locale).value`); жёсткий хардкод `'ru-RU'` запрещён.
 */

const _SUPPORTED_LOCALES = Object.freeze(new Set(['ru', 'en']));

function _resolveLocale(locale) {
    if (typeof locale !== 'string' || locale.length === 0) {
        throw new Error('format-platform-number: locale must be non-empty string');
    }
    const lc = locale.toLowerCase();
    if (!_SUPPORTED_LOCALES.has(lc)) {
        throw new Error(`format-platform-number: locale "${locale}" not supported (expected ru|en)`);
    }
    return lc === 'ru' ? 'ru-RU' : 'en-US';
}

/**
 * @param {number} value
 * @param {string} locale  'ru' | 'en' (active state.i18n.locale)
 * @param {Intl.NumberFormatOptions} [options]
 * @returns {string}
 */
export function formatPlatformNumber(value, locale, options = {}) {
    if (typeof value !== 'number' || !Number.isFinite(value)) {
        return '—';
    }
    return new Intl.NumberFormat(_resolveLocale(locale), options).format(value);
}

/**
 * Деньги в рублях (валюта `RUB` фиксирована — это платформенная валюта биллинга).
 *
 * @param {number} amount
 * @param {string} locale  'ru' | 'en'
 * @param {{ minimumFractionDigits?: number, maximumFractionDigits?: number }} [options]
 * @returns {string}
 */
export function formatPlatformCurrencyRub(amount, locale, options = {}) {
    if (typeof amount !== 'number' || !Number.isFinite(amount)) {
        return '—';
    }
    return new Intl.NumberFormat(_resolveLocale(locale), {
        style: 'currency',
        currency: 'RUB',
        minimumFractionDigits: typeof options.minimumFractionDigits === 'number' ? options.minimumFractionDigits : 2,
        maximumFractionDigits: typeof options.maximumFractionDigits === 'number' ? options.maximumFractionDigits : 2,
    }).format(amount);
}

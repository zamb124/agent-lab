/**
 * Форматирование дат и времени с учётом активной локали.
 *
 * Локаль передаётся аргументом (компонент берёт её через
 * `this.select((s) => s.i18n.locale).value`); жёсткий хардкод `'ru-RU'` запрещён.
 */

const _SUPPORTED_LOCALES = Object.freeze(new Set(['ru', 'en']));
const _CANONICAL_ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const _CANONICAL_ISO_DATETIME = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;

function _pad2(value) {
    return String(value).padStart(2, '0');
}

function _resolveLocale(locale) {
    if (typeof locale !== 'string' || locale.length === 0) {
        throw new Error('format-platform-date: locale must be non-empty string');
    }
    const lc = locale.toLowerCase();
    if (!_SUPPORTED_LOCALES.has(lc)) {
        throw new Error(`format-platform-date: locale "${locale}" not supported (expected ru|en)`);
    }
    return lc === 'ru' ? 'ru-RU' : 'en-US';
}

function _toDate(input) {
    if (input instanceof Date) {
        return Number.isNaN(input.getTime()) ? null : input;
    }
    if (typeof input === 'string' && input.length > 0) {
        const d = new Date(input);
        return Number.isNaN(d.getTime()) ? null : d;
    }
    if (typeof input === 'number' && Number.isFinite(input)) {
        const d = new Date(input);
        return Number.isNaN(d.getTime()) ? null : d;
    }
    return null;
}

/**
 * @param {Date|string|number} input
 * @param {string} locale  'ru' | 'en'
 * @param {Intl.DateTimeFormatOptions} [options]  по умолчанию — короткая дата
 * @returns {string}
 */
export function formatPlatformDate(input, locale, options = { day: '2-digit', month: '2-digit', year: 'numeric' }) {
    const d = _toDate(input);
    if (d === null) {
        return '—';
    }
    return new Intl.DateTimeFormat(_resolveLocale(locale), options).format(d);
}

/**
 * @param {Date|string|number} input
 * @param {string} locale  'ru' | 'en'
 * @returns {string}  "DD.MM.YYYY HH:MM" или "MM/DD/YYYY, HH:MM" в зависимости от локали
 */
export function formatPlatformDateTime(input, locale) {
    return formatPlatformDate(input, locale, {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
    });
}

/**
 * @param {Date|string|number} input
 * @param {string} locale
 * @returns {string}  "HH:MM"
 */
export function formatPlatformTime(input, locale) {
    return formatPlatformDate(input, locale, { hour: '2-digit', minute: '2-digit' });
}

/**
 * @param {string|null|undefined} value
 * @returns {string}
 */
export function normalizeIsoDateTimeForField(value) {
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value !== 'string') {
        throw new Error('normalizeIsoDateTimeForField: value must be string');
    }
    if (value.length === 0) {
        return '';
    }
    if (_CANONICAL_ISO_DATETIME.test(value)) {
        return value;
    }
    const parsed = _toDate(value);
    if (parsed === null) {
        throw new Error(`normalizeIsoDateTimeForField: invalid datetime: ${value}`);
    }
    return `${parsed.getFullYear()}-${_pad2(parsed.getMonth() + 1)}-${_pad2(parsed.getDate())}T${_pad2(parsed.getHours())}:${_pad2(parsed.getMinutes())}`;
}

/**
 * @param {string|null|undefined} value
 * @returns {string}
 */
export function normalizeIsoDateForField(value) {
    if (value === null || value === undefined) {
        return '';
    }
    if (typeof value !== 'string') {
        throw new Error('normalizeIsoDateForField: value must be string');
    }
    if (value.length === 0) {
        return '';
    }
    if (_CANONICAL_ISO_DATE.test(value)) {
        return value;
    }
    const parsed = _toDate(value);
    if (parsed === null) {
        throw new Error(`normalizeIsoDateForField: invalid date: ${value}`);
    }
    return `${parsed.getFullYear()}-${_pad2(parsed.getMonth() + 1)}-${_pad2(parsed.getDate())}`;
}

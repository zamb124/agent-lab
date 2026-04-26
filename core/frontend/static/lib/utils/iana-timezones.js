/**
 * Стабильный IANA-список, если Intl.supportedValuesOf('timeZone') недоступен.
 */
const FALLBACK_IANA_TIME_ZONES = [
    'UTC',
    'Europe/Moscow',
    'Europe/London',
    'Europe/Berlin',
    'Europe/Paris',
    'Europe/Istanbul',
    'America/New_York',
    'America/Chicago',
    'America/Denver',
    'America/Los_Angeles',
    'America/Sao_Paulo',
    'America/Toronto',
    'America/Vancouver',
    'Asia/Dubai',
    'Asia/Almaty',
    'Asia/Kolkata',
    'Asia/Bangkok',
    'Asia/Singapore',
    'Asia/Shanghai',
    'Asia/Tokyo',
    'Asia/Seoul',
    'Australia/Sydney',
    'Pacific/Auckland',
];

/**
 * Все известные IANA time zones, отсортированные (Unicode order).
 * Предпочтительно из Intl.supportedValuesOf (современные браузеры); иначе жёсткий fallback.
 */
export function getSortedIanaTimeZones() {
    let list;
    if (typeof Intl !== 'undefined' && typeof Intl.supportedValuesOf === 'function') {
        try {
            list = Intl.supportedValuesOf('timeZone');
        } catch {
            list = null;
        }
    }
    if (!Array.isArray(list) || list.length === 0) {
        list = [...FALLBACK_IANA_TIME_ZONES];
    }
    const unique = [...new Set(list)];
    unique.sort((a, b) => a.localeCompare(b, 'en'));
    if (!unique.includes('UTC')) {
        unique.push('UTC');
        unique.sort((a, b) => a.localeCompare(b, 'en'));
    }
    return unique;
}

let _cacheAll;
export function getCachedSortedIanaTimeZones() {
    if (!_cacheAll) {
        _cacheAll = getSortedIanaTimeZones();
    }
    return _cacheAll;
}

export { FALLBACK_IANA_TIME_ZONES };

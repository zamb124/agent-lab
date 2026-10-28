/**
 * Все известные IANA time zones, отсортированные (Unicode order).
 * Источник — Intl.supportedValuesOf('timeZone'); без него браузер не поддерживается.
 */
export function getSortedIanaTimeZones(): string[] {
    const unique = [...new Set(Intl.supportedValuesOf('timeZone'))];
    unique.sort((a, b) => a.localeCompare(b, 'en'));
    if (!unique.includes('UTC')) {
        unique.push('UTC');
        unique.sort((a, b) => a.localeCompare(b, 'en'));
    }
    return unique;
}

let _cacheAll: string[] | null = null;
export function getCachedSortedIanaTimeZones(): string[] {
    if (!_cacheAll) {
        _cacheAll = getSortedIanaTimeZones();
    }
    return _cacheAll;
}


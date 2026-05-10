/**
 * Если вся строка — один ограждающий GFM-блок (язык markdown/md или без метки),
 * возвращает содержимое внутри. Иначе — исходную строку без изменений.
 */
export function stripOuterMarkdownCodeFence(raw) {
    if (typeof raw !== 'string') {
        return '';
    }
    const trimmed = raw.trim();
    if (trimmed.length === 0) {
        return '';
    }
    const openMatch = trimmed.match(/^```(?:markdown|md)?\s*\r?\n/i);
    if (!openMatch) {
        return trimmed;
    }
    const afterOpen = trimmed.slice(openMatch[0].length);
    const closeIdx = afterOpen.lastIndexOf('```');
    if (closeIdx < 0) {
        return trimmed;
    }
    const inner = afterOpen.slice(0, closeIdx).trim();
    return inner.length === 0 ? trimmed : inner;
}

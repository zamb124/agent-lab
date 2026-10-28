/**
 * JSON-массив непустых строк для argv / egress_hosts.
 * Неполный ввод `[` не ошибка: platform-field string шлёт change на каждый input.
 */

/**
 * @typedef {{ status: 'empty' } | { status: 'incomplete' } | { status: 'invalid' } | { status: 'ok', items: string[] }} JsonStringListParse
 */

/**
 * @param {string} text
 * @returns {JsonStringListParse}
 */
export function parseJsonStringList(text: any) {
    if (typeof text !== 'string') {
        throw new Error('parseJsonStringList: text string required');
    }
    const trimmed = text.trim();
    if (trimmed.length === 0) {
        return { status: 'empty' };
    }
    if (!trimmed.startsWith('[') || !trimmed.endsWith(']')) {
        return { status: 'incomplete' };
    }
    let parsed;
    try {
        parsed = JSON.parse(trimmed);
    } catch (exc) {
        if (!(exc instanceof SyntaxError)) {
            throw exc;
        }
        return { status: 'invalid' };
    }
    if (!Array.isArray(parsed) || parsed.some((item) => typeof item !== 'string' || item.length === 0)) {
        return { status: 'invalid' };
    }
    return { status: 'ok', items: parsed };
}

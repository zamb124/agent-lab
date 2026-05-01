/**
 * Имя иконки platform-icon для визуализации tool call по полю `name` (эвристика).
 *
 * @param {string} name
 * @returns {string}
 */
export function toolCallIconName(name) {
    if (typeof name !== 'string') {
        throw new Error('toolCallIconName: string required');
    }
    const lower = name.toLowerCase();
    if (lower.length === 0) {
        return 'zap';
    }
    if (lower.includes('search') || lower.includes('rag') || lower.includes('retriev')) {
        return 'search';
    }
    if (lower.includes('file') || lower.includes('read') || lower.includes('upload') || lower.includes('download')) {
        return 'file';
    }
    if (lower.includes('contract') || lower.includes('draft') || lower.includes('write') || lower.includes('edit')) {
        return 'edit';
    }
    if (lower.includes('http') || lower.includes('fetch') || lower.includes('web') || lower.includes('request')) {
        return 'search';
    }
    if (lower.includes('code') || lower.includes('run') || lower.includes('exec') || lower.includes('shell')) {
        return 'terminal';
    }
    if (lower.includes('mail') || lower.includes('message') || lower.includes('chat')) {
        return 'message-circle';
    }
    if (lower.includes('calendar') || lower.includes('schedule') || lower.includes('time')) {
        return 'calendar';
    }
    if (lower.includes('image') || lower.includes('photo') || lower.includes('vision')) {
        return 'image';
    }
    return 'zap';
}

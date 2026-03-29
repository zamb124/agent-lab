/** Превью для строки списка каналов по payload сообщения (как на сервере). */
const PREVIEW_MAX = 120;

/**
 * @param {object} p — payload message.created / MessageRead.
 * @returns {string|null}
 */
export function lanePreviewFromMessagePayload(p) {
    if (!p || typeof p !== 'object') {
        throw new Error('payload сообщения обязателен.');
    }
    const contents = p.contents;
    if (!Array.isArray(contents) || contents.length === 0) {
        return null;
    }
    const sorted = [...contents].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    const block = sorted[0];
    const t = block.type;
    const d = block.data;
    if (t === 'text/plain') {
        if (typeof d?.body !== 'string') {
            throw new Error('text/plain: ожидается data.body строка.');
        }
        const raw = d.body.trim();
        if (raw === '') {
            return '';
        }
        if (raw.length <= PREVIEW_MAX) {
            return raw;
        }
        return `${raw.slice(0, PREVIEW_MAX - 1)}…`;
    }
    if (t === 'code/block') {
        return '[Код]';
    }
    if (t === 'mock/image') {
        return '[Изображение]';
    }
    if (t === 'file/image') {
        return '[Фото]';
    }
    if (t === 'file/document') {
        return '[Файл]';
    }
    if (t === 'file/audio') {
        return '[Аудио]';
    }
    if (t === 'git/reference') {
        return '[Git]';
    }
    if (t === 'custom_tool_response') {
        return '[Инструмент]';
    }
    throw new Error(`Неизвестный тип контента для превью: ${t}`);
}

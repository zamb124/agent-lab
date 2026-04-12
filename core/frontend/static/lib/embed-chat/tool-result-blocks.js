/**
 * Извлекает UI blocks из результата tool (content строка или объект).
 *
 * Контракт доставки блоков в embed-чат (приоритет — JSON в tool_result):
 * - Парсится `toolResult.content` | `output` | `text` (строка JSON или объект).
 * - Если значение — массив объектов с полем `type`, он трактуется как список блоков.
 * - Если объект с полем `blocks` (массив) — используется `blocks`.
 * - Если объект с полем `files` (массив) — каждый элемент мапится в блок `file_card`
 *   (`file_id`, `name`, `mime_type`, `url`, `preview_url`).
 * Типы `card` / `table` / `actions` / `text`: см. `embed-builtin-blocks.js` и `embed-block-renderer.js`
 * (у `table` поле JSON `title` → свойство `caption` у Lit-компонента).
 * Невалидный JSON не даёт блоков; рендерер показывает fallback для неизвестного `type`.
 */

function tryParseJson(text) {
    if (text == null || typeof text !== 'string') {
        return null;
    }
    const t = text.trim();
    if (!t.startsWith('{') && !t.startsWith('[')) {
        return null;
    }
    try {
        return JSON.parse(t);
    } catch {
        return null;
    }
}

/**
 * @param {object} toolResult - как в metadata.tool_result от A2A
 * @returns {object[]|null}
 */
export function blocksFromToolResult(toolResult) {
    if (!toolResult || typeof toolResult !== 'object') {
        return null;
    }
    const raw = toolResult.content ?? toolResult.output ?? toolResult.text;
    if (raw == null) {
        return null;
    }
    let data = raw;
    if (typeof raw === 'string') {
        data = tryParseJson(raw);
        if (data == null) {
            return null;
        }
    }
    if (Array.isArray(data)) {
        return data;
    }
    if (data.blocks && Array.isArray(data.blocks)) {
        return data.blocks;
    }
    if (data.files && Array.isArray(data.files)) {
        return data.files.map((f) => ({
            type: 'file_card',
            file_id: f.file_id,
            name: f.name || f.original_name,
            mime_type: f.mime_type || f.content_type,
            url: f.url,
            preview_url: f.preview_url,
        }));
    }
    return null;
}

/**
 * @param {object[]} existing
 * @param {object|null} toolResult
 * @returns {object[]}
 */
export function mergeBlocksFromToolResult(existing, toolResult) {
    const incoming = blocksFromToolResult(toolResult);
    if (!incoming || incoming.length === 0) {
        return existing || [];
    }
    const base = Array.isArray(existing) ? [...existing] : [];
    return base.concat(incoming);
}

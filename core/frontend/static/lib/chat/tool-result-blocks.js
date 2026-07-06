/**
 * Извлекает UI blocks из результата tool (content строка или объект).
 *
 * Контракт доставки блоков в flows-chat (приоритет — JSON в tool_result):
 * - Парсится `toolResult.content` | `output` | `text` (строка JSON или объект).
 * - Если значение — массив объектов с полем `type`, он трактуется как список блоков.
 * - Если объект с полем `blocks` (массив) — используется `blocks`.
 * - Если объект с полем `files` (массив) — каждый элемент мапится в блок `file_card`
 *   (`file_id`, `name`, `mime_type`, `url`, `preview_url`).
 * Типы `card` / `table` / `actions` / `text`: см. `flows-chat-builtin-blocks.js`
 * и `flows-chat-block-renderer.js`
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

function fileCardFromToolFile(file, document = null) {
    if (!file || typeof file !== 'object') {
        return null;
    }
    const doc =
        document && typeof document === 'object' && !Array.isArray(document)
            ? document
            : file.document && typeof file.document === 'object' && !Array.isArray(file.document)
              ? file.document
              : null;
    const capabilities =
        file.capabilities && typeof file.capabilities === 'object' && !Array.isArray(file.capabilities)
            ? { ...file.capabilities }
            : {};
    if (doc) {
        capabilities.document = doc;
    }
    const editorUrl =
        typeof file.editor_url === 'string' && file.editor_url.length > 0
            ? file.editor_url
            : typeof doc?.editor_url === 'string'
              ? doc.editor_url
              : '';
    return {
        type: 'file_card',
        file_id: file.file_id,
        name: file.name || file.original_name || doc?.title,
        mime_type: file.mime_type || file.content_type,
        file_size: file.file_size || file.size,
        url: file.url,
        preview_url: file.preview_url,
        editor_url: editorUrl,
        binding_id: file.binding_id || doc?.binding_id,
        catalog_id: file.catalog_id || doc?.catalog_id,
        document_type: file.document_type || doc?.document_type,
        namespace: file.namespace || doc?.namespace,
        document: doc,
        capabilities,
    };
}

/**
 * @param {object} toolResult - как в metadata.tool_result от A2A
 * @returns {object[]|null}
 */
export function blocksFromToolResult(toolResult) {
    if (!toolResult || typeof toolResult !== 'object') {
        return null;
    }
    const raw = toolResult.content ?? toolResult.output ?? toolResult.text ?? toolResult.result;
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
        return data.files
            .map((f) => fileCardFromToolFile(f))
            .filter((block) => block !== null);
    }
    if (data.file && typeof data.file === 'object') {
        const block = fileCardFromToolFile(data.file, data.document);
        return block ? [block] : null;
    }
    if (data.document && typeof data.document === 'object') {
        const block = fileCardFromToolFile(data.document, data.document);
        return block ? [block] : null;
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
    const displayOnly = incoming.filter(
        (block) => block && typeof block === 'object' && block.type !== 'actions',
    );
    if (displayOnly.length === 0) {
        return existing || [];
    }
    const base = Array.isArray(existing) ? [...existing] : [];
    return base.concat(displayOnly);
}

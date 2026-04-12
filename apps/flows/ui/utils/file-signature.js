/**
 * Сигнатура вложения для текста промпта / сообщения (как FileProcessor.format_file_message).
 * Drag payload для переноса из чипа ноды: кастомный тип + text/plain (промпт).
 */

/** @type {string} */
export const FLOWS_NODE_FILE_MIME = 'application/x-humanitec-flows-node-file+json';

/**
 * @param {DataTransfer} dataTransfer
 * @param {object} fileEntry
 */
export function setFlowsNodeFileDragData(dataTransfer, fileEntry) {
    const payload = JSON.stringify({
        name: fileEntry.name || '',
        path: fileEntry.path || '',
        file_id: fileEntry.file_id != null && fileEntry.file_id !== '' ? String(fileEntry.file_id) : null,
    });
    dataTransfer.setData(FLOWS_NODE_FILE_MIME, payload);
    dataTransfer.setData('text/plain', formatFileSignatureForPrompt(fileEntry));
    dataTransfer.effectAllowed = 'copy';
}

/**
 * Python inline code: чтение вложения по имени (тот же смысл, что tool read_file).
 * @param {object} fileEntry
 * @returns {string}
 */
export function buildPythonReadFileSnippet(fileEntry) {
    const nameLit = JSON.stringify(fileEntry.name || '');
    return (
        `# read_file: вложение по имени (как tool read_file)\n` +
        `_f = next((x for x in get_files(state) if x.get("name") == ${nameLit}), None)\n` +
        `if _f is None:\n` +
        `    raise ValueError("file not in state.files: " + ${nameLit})\n` +
        `read_file_result = await reader.read(_f)\n`
    );
}

/**
 * Добавляет одинаковый префикс к каждой непустой строке (отступ контейнера вокруг сниппета).
 * @param {string} text
 * @param {string} linePrefix — пробелы/табы как в начале строки редактора
 * @returns {string}
 */
export function prefixCodeLines(text, linePrefix) {
    if (!linePrefix) {
        return text;
    }
    return text
        .split('\n')
        .map((line) => (line.length === 0 ? '' : linePrefix + line))
        .join('\n');
}

/**
 * @param {object} fileEntry — запись как в state.files: name, path, mime_type?, size?, file_id?
 * @returns {string}
 */
export function formatFileSignatureForPrompt(fileEntry) {
    const name = (fileEntry && fileEntry.name) || 'file';
    const fileId = (fileEntry && fileEntry.file_id) || '';
    const url = (fileEntry && fileEntry.path) || '';
    const contentType = (fileEntry && fileEntry.mime_type) || 'unknown';
    const sizeBytes =
        typeof (fileEntry && fileEntry.size) === 'number'
            ? fileEntry.size
            : parseInt(String((fileEntry && fileEntry.size) || '0'), 10) || 0;
    const sizeStr =
        sizeBytes >= 1024 * 1024
            ? `${(sizeBytes / (1024 * 1024)).toFixed(2)} MB`
            : `${sizeBytes} байт`;
    return `[FILE] Файл: ${name} (ID: ${fileId}, URL: ${url}, тип: ${contentType}, размер: ${sizeStr}) [/FILE]`;
}

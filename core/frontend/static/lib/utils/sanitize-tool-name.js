/**
 * Имя tool в схеме function-calling (OpenAI-совместимо), как `sanitize_tool_name`
 * в backend `apps/flows/src/tools/base.py`.
 */

import { md5HexUtf8 } from './md5-hex.js';

/**
 * @param {string} name
 * @returns {string}
 */
export function sanitizeToolName(name) {
    if (typeof name !== 'string') {
        throw new Error('sanitizeToolName: name must be string');
    }
    let sanitized = name.replace(/[^a-zA-Z0-9_-]/g, '_');
    sanitized = sanitized.replace(/_+/g, '_');
    sanitized = sanitized.replace(/^[_-]+|[_-]+$/g, '');
    if (sanitized.length === 0) {
        sanitized = `tool_${md5HexUtf8(name).slice(0, 8)}`;
    }
    return sanitized;
}

/**
 * Форматирование результатов выполнения нод для pill на канве и инспектора.
 */

import { formatJsonPretty } from '@platform/lib/utils/json-format.js';

export const CANVAS_RUN_RESULT_GAP = 8;
export const CANVAS_RUN_RESULT_PILL_COLLAPSED_H = 44;
export const CANVAS_RUN_RESULT_PILL_PAD_V = 12;
export const CANVAS_RUN_RESULT_HEADLINE_LINE_H = 15;
export const CANVAS_RUN_RESULT_HEADLINE_MAX_LINES = 2;
export const CANVAS_RUN_RESULT_META_H = 14;
export const CANVAS_RUN_RESULT_META_MARGIN = 2;
export const CANVAS_RUN_RESULT_CHANGE_ROW_LABEL_LINE_H = 14;
export const CANVAS_RUN_RESULT_CHANGE_ROW_DETAIL_LINE_H = 14;
export const CANVAS_RUN_RESULT_CHANGE_ROW_DETAIL_MARGIN = 1;
export const CANVAS_RUN_RESULT_CHANGE_ROW_BADGE_H = 16;
export const CANVAS_RUN_RESULT_CHANGE_ROW_GAP = 4;
export const CANVAS_RUN_RESULT_CHANGE_ROW_CHARS_PER_LINE = 22;
export const CANVAS_RUN_RESULT_CHANGE_LIST_GAP = 6;
export const CANVAS_RUN_RESULT_MORE_ROW_H = 18;
export const CANVAS_RUN_RESULT_BOTTOM_PAD = 4;
export const CANVAS_RUN_RESULT_PRIMARY_MAX = 80;
export const CANVAS_RUN_RESULT_VALUE_MAX = 48;
export const CANVAS_RUN_RESULT_DIFF_PREVIEW_MAX = 48;
export const CANVAS_RUN_RESULT_EXPANDED_DIFF_LINES = 8;

/**
 * @typedef {(key: string, params?: Record<string, string>) => string} CanvasRunResultTranslate
 */

/**
 * @typedef {'null' | 'empty' | 'boolean' | 'number' | 'string' | 'markdown' | 'json_string' | 'status_map' | 'array' | 'object'} NodeRunValueKind
 */

/**
 * @typedef {{
 *   kind: NodeRunValueKind,
 *   preview: string,
 *   parsed: unknown,
 * }} NodeRunValueClassification
 */

/**
 * @typedef {{
 *   path: string,
 *   changeType: 'added' | 'changed' | 'removed',
 *   badge: string,
 *   badgeLabel: string,
 *   label: string,
 *   detail: string,
 *   valueKind: NodeRunValueKind,
 *   typeLabel: string,
 * }} NodeRunChangeRow
 */

/**
 * @typedef {{
 *   headline: string,
 *   changeRows: NodeRunChangeRow[],
 *   omittedCount: number,
 *   hasMeta: boolean,
 * }} NodeRunViewModel
 */

const DEFAULT_I18N = Object.freeze({
    'canvas_run_result.change_added': 'Added',
    'canvas_run_result.change_changed': 'Changed',
    'canvas_run_result.change_removed': 'Removed',
    'canvas_run_result.value_array_items_one': '{{count}} item',
    'canvas_run_result.value_array_items_other': '{{count}} items',
    'canvas_run_result.value_object_fields_one': '{{count}} field',
    'canvas_run_result.value_object_fields_other': '{{count}} fields',
    'canvas_run_result.value_null': 'null',
    'canvas_run_result.value_empty': 'empty',
    'canvas_run_result.value_true': 'true',
    'canvas_run_result.value_false': 'false',
    'canvas_run_result.headline_external_api': 'HTTP {{status}}',
    'canvas_run_result.headline_channel_ok': 'Message sent',
    'canvas_run_result.headline_hitl': 'Handoff to operator',
    'canvas_run_result.type_null': 'null',
    'canvas_run_result.type_empty': 'empty',
    'canvas_run_result.type_boolean': 'boolean',
    'canvas_run_result.type_number': 'number',
    'canvas_run_result.type_string': 'string',
    'canvas_run_result.type_markdown': 'markdown',
    'canvas_run_result.type_json': 'json',
    'canvas_run_result.type_status': 'status',
    'canvas_run_result.type_array': 'array ({{count}})',
    'canvas_run_result.type_object': 'object ({{count}})',
    'canvas_run_result.more_changes': '+{{count}} more',
});

/**
 * @param {CanvasRunResultTranslate | undefined} t
 * @returns {CanvasRunResultTranslate}
 */
function _resolveTranslate(t) {
    if (typeof t === 'function') {
        return t;
    }
    return (key, params) => {
        let text = DEFAULT_I18N[key];
        if (typeof text !== 'string') {
            throw new Error(`flows-node-run-result: missing default i18n key ${key}`);
        }
        if (params) {
            for (const [paramKey, paramValue] of Object.entries(params)) {
                text = text.replace(`{{${paramKey}}}`, paramValue);
            }
        }
        return text;
    };
}

/**
 * @param {unknown} value
 */
function _isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @param {unknown} value
 */
function _isStatusEntry(value) {
    if (!_isPlainObject(value)) {
        return false;
    }
    return 'ok' in value;
}

/**
 * @param {unknown} value
 */
function _isStatusMap(value) {
    if (!_isPlainObject(value)) {
        return false;
    }
    const entries = Object.entries(value);
    if (entries.length === 0) {
        return false;
    }
    for (let i = 0; i < entries.length; i += 1) {
        if (!_isStatusEntry(entries[i][1])) {
            return false;
        }
    }
    return true;
}

/**
 * @param {Record<string, unknown>} value
 */
function _formatStatusMap(value) {
    const parts = [];
    const entries = Object.entries(value);
    for (let i = 0; i < entries.length; i += 1) {
        const key = entries[i][0];
        const entry = entries[i][1];
        if (!_isStatusEntry(entry)) {
            continue;
        }
        const statusEntry = /** @type {Record<string, unknown>} */ (entry);
        const okValue = statusEntry.ok;
        const statusText = okValue === true ? 'ok' : 'fail';
        let part = `${key}: ${statusText}`;
        const latencyMs = statusEntry.latency_ms;
        if (typeof latencyMs === 'number' && Number.isFinite(latencyMs)) {
            part += ` · ${String(Math.round(latencyMs))} ms`;
        }
        parts.push(part);
    }
    return parts.join(', ');
}

/**
 * @param {string} text
 * @returns {{ ok: true, value: object } | { ok: false }}
 */
function _parseJsonContainer(text) {
    const trimmed = text.trim();
    if (trimmed.length === 0) {
        return { ok: false };
    }
    const first = trimmed[0];
    if (first !== '{' && first !== '[') {
        return { ok: false };
    }
    try {
        const parsed = JSON.parse(trimmed);
        if (parsed !== null && typeof parsed === 'object') {
            return { ok: true, value: parsed };
        }
        return { ok: false };
    } catch (err) {
        if (err instanceof SyntaxError) {
            return { ok: false };
        }
        throw err;
    }
}

/**
 * @param {string} text
 */
function _looksLikeMarkdown(text) {
    if (/^#{1,6}\s+\S/m.test(text)) {
        return true;
    }
    if (/^\d+\.\s+\[[^\]]+\]\(/m.test(text)) {
        return true;
    }
    if (/\[[^\]]+\]\([^)]+\)/.test(text)) {
        return true;
    }
    return false;
}

/**
 * @param {unknown} value
 * @returns {NodeRunValueClassification}
 */
export function classifyNodeRunValue(value) {
    if (value === undefined) {
        throw new Error('classifyNodeRunValue: value is undefined');
    }
    if (value === null) {
        return { kind: 'null', preview: '', parsed: null };
    }
    if (typeof value === 'boolean') {
        return { kind: 'boolean', preview: '', parsed: value };
    }
    if (typeof value === 'number' || typeof value === 'bigint') {
        return { kind: 'number', preview: String(value), parsed: value };
    }
    if (typeof value === 'string') {
        if (value.length === 0) {
            return { kind: 'empty', preview: '', parsed: value };
        }
        const json = _parseJsonContainer(value);
        if (json.ok) {
            return { kind: 'json_string', preview: '', parsed: json.value };
        }
        if (_looksLikeMarkdown(value)) {
            return { kind: 'markdown', preview: value, parsed: value };
        }
        return { kind: 'string', preview: value, parsed: value };
    }
    if (Array.isArray(value)) {
        return { kind: 'array', preview: '', parsed: value };
    }
    if (_isStatusMap(value)) {
        return { kind: 'status_map', preview: '', parsed: value };
    }
    if (_isPlainObject(value)) {
        return { kind: 'object', preview: '', parsed: value };
    }
    throw new Error(`classifyNodeRunValue: unsupported type ${typeof value}`);
}

/**
 * @param {NodeRunValueClassification} classified
 * @param {CanvasRunResultTranslate | undefined} t
 */
export function nodeRunValueKindLabel(classified, t) {
    if (classified === null || typeof classified !== 'object') {
        throw new Error('nodeRunValueKindLabel: classified is required');
    }
    t = _resolveTranslate(t);
    const kind = classified.kind;
    if (kind === 'null') {
        return t('canvas_run_result.type_null');
    }
    if (kind === 'empty') {
        return t('canvas_run_result.type_empty');
    }
    if (kind === 'boolean') {
        return t('canvas_run_result.type_boolean');
    }
    if (kind === 'number') {
        return t('canvas_run_result.type_number');
    }
    if (kind === 'string') {
        return t('canvas_run_result.type_string');
    }
    if (kind === 'markdown') {
        return t('canvas_run_result.type_markdown');
    }
    if (kind === 'json_string') {
        return t('canvas_run_result.type_json');
    }
    if (kind === 'status_map') {
        return t('canvas_run_result.type_status');
    }
    if (kind === 'array') {
        if (!Array.isArray(classified.parsed)) {
            throw new Error('nodeRunValueKindLabel: array classification requires array parsed');
        }
        return t('canvas_run_result.type_array', { count: String(classified.parsed.length) });
    }
    if (kind === 'object') {
        if (!_isPlainObject(classified.parsed)) {
            throw new Error('nodeRunValueKindLabel: object classification requires object parsed');
        }
        const count = Object.keys(/** @type {Record<string, unknown>} */ (classified.parsed)).length;
        return t('canvas_run_result.type_object', { count: String(count) });
    }
    throw new Error(`nodeRunValueKindLabel: unknown kind ${kind}`);
}

/**
 * @param {NodeRunValueClassification} classified
 * @param {CanvasRunResultTranslate} t
 * @param {number} maxLen
 */
function _formatClassifiedCanvasValue(classified, t, maxLen) {
    if (classified.kind === 'null') {
        return t('canvas_run_result.value_null');
    }
    if (classified.kind === 'empty') {
        return t('canvas_run_result.value_empty');
    }
    if (classified.kind === 'json_string' || classified.kind === 'array' || classified.kind === 'object' || classified.kind === 'status_map') {
        return formatCanvasValue(classified.parsed, t, maxLen);
    }
    if (classified.kind === 'boolean') {
        return formatCanvasValue(classified.parsed, t, maxLen);
    }
    if (classified.kind === 'number') {
        return truncateForCanvas(classified.preview, maxLen);
    }
    if (classified.kind === 'markdown' || classified.kind === 'string') {
        return truncateForCanvas(classified.preview, maxLen);
    }
    throw new Error(`_formatClassifiedCanvasValue: unknown kind ${classified.kind}`);
}

/**
 * @param {unknown} value
 * @param {CanvasRunResultTranslate} t
 * @param {number} maxLen
 */
export function formatCanvasValue(value, t, maxLen = CANVAS_RUN_RESULT_VALUE_MAX) {
    t = _resolveTranslate(t);
    if (value === undefined) {
        throw new Error('formatCanvasValue: value is undefined');
    }
    if (value === null) {
        return t('canvas_run_result.value_null');
    }
    if (typeof value === 'string') {
        if (value.length === 0) {
            return t('canvas_run_result.value_empty');
        }
        return truncateForCanvas(value, maxLen);
    }
    if (typeof value === 'number' || typeof value === 'bigint') {
        return truncateForCanvas(String(value), maxLen);
    }
    if (typeof value === 'boolean') {
        return value
            ? t('canvas_run_result.value_true')
            : t('canvas_run_result.value_false');
    }
    if (Array.isArray(value)) {
        const count = String(value.length);
        const key = value.length === 1
            ? 'canvas_run_result.value_array_items_one'
            : 'canvas_run_result.value_array_items_other';
        return t(key, { count });
    }
    if (_isStatusMap(value)) {
        return truncateForCanvas(_formatStatusMap(/** @type {Record<string, unknown>} */ (value)), maxLen);
    }
    if (_isPlainObject(value)) {
        const entries = Object.entries(/** @type {Record<string, unknown>} */ (value));
        const count = String(entries.length);
        const fieldsKey = entries.length === 1
            ? 'canvas_run_result.value_object_fields_one'
            : 'canvas_run_result.value_object_fields_other';
        const previews = [];
        for (let i = 0; i < entries.length && previews.length < 2; i += 1) {
            const entryValue = entries[i][1];
            if (typeof entryValue === 'string' || typeof entryValue === 'number' || typeof entryValue === 'boolean') {
                previews.push(`${entries[i][0]}: ${String(entryValue)}`);
            }
        }
        const base = t(fieldsKey, { count });
        if (previews.length === 0) {
            return truncateForCanvas(base, maxLen);
        }
        return truncateForCanvas(`${base} (${previews.join(', ')})`, maxLen);
    }
    return truncateForCanvas(String(value), maxLen);
}

/**
 * @param {unknown} value
 */
export function serializeNodeRunValue(value) {
    const classified = classifyNodeRunValue(value);
    if (classified.kind === 'null') {
        return 'null';
    }
    if (classified.kind === 'empty') {
        return '';
    }
    if (classified.kind === 'boolean') {
        return classified.parsed === true ? 'true' : 'false';
    }
    if (classified.kind === 'number') {
        return String(classified.parsed);
    }
    if (classified.kind === 'string' || classified.kind === 'markdown') {
        if (typeof classified.parsed !== 'string') {
            throw new Error('serializeNodeRunValue: string classification requires string parsed');
        }
        return classified.parsed;
    }
    if (
        classified.kind === 'json_string'
        || classified.kind === 'array'
        || classified.kind === 'object'
        || classified.kind === 'status_map'
    ) {
        return formatJsonPretty(classified.parsed);
    }
    throw new Error(`serializeNodeRunValue: unknown kind ${classified.kind}`);
}

/**
 * @param {string} parentPath
 * @param {string | number} key
 * @param {boolean} isIndex
 */
export function jsonTreeChildPath(parentPath, key, isIndex) {
    if (typeof parentPath !== 'string') {
        throw new Error('jsonTreeChildPath: parentPath must be a string');
    }
    if (typeof isIndex !== 'boolean') {
        throw new Error('jsonTreeChildPath: isIndex must be a boolean');
    }
    if (isIndex) {
        if (typeof key !== 'number' || !Number.isFinite(key) || key < 0) {
            throw new Error('jsonTreeChildPath: array index must be a non-negative number');
        }
        return `${parentPath}[${String(Math.floor(key))}]`;
    }
    if (typeof key !== 'string' || key.length === 0) {
        throw new Error('jsonTreeChildPath: object key must be a non-empty string');
    }
    if (parentPath.length === 0) {
        return key;
    }
    return `${parentPath}.${key}`;
}

/**
 * @param {string} path
 */
export function formatDiffPathLabel(path) {
    if (typeof path !== 'string') {
        throw new Error('formatDiffPathLabel: path must be a string');
    }
    if (path.startsWith('variables.')) {
        return path.slice('variables.'.length);
    }
    return path;
}

/**
 * @param {string} path
 * @param {string} primaryField
 */
function _diffPathScore(path, primaryField) {
    if (primaryField.length > 0) {
        if (path === primaryField || path.startsWith(`${primaryField}.`)) {
            return 0;
        }
    }
    if (path.startsWith('variables.')) {
        return 1;
    }
    return 2;
}

/**
 * @param {unknown[]} diff
 * @param {string} primaryField
 */
function _sortDiffForDisplay(diff, primaryField) {
    return [...diff].sort((left, right) => {
        const leftPath = /** @type {{ path: string }} */ (left).path;
        const rightPath = /** @type {{ path: string }} */ (right).path;
        const leftScore = _diffPathScore(leftPath, primaryField);
        const rightScore = _diffPathScore(rightPath, primaryField);
        if (leftScore !== rightScore) {
            return leftScore - rightScore;
        }
        return leftPath.localeCompare(rightPath);
    });
}

/**
 * @param {unknown} diffEntry
 * @param {'new' | 'old'} side
 */
export function resolveInspectValue(diffEntry, side) {
    if (diffEntry === null || typeof diffEntry !== 'object' || Array.isArray(diffEntry)) {
        throw new Error('resolveInspectValue: diff entry must be an object');
    }
    if (side !== 'new' && side !== 'old') {
        throw new Error('resolveInspectValue: side must be new or old');
    }
    const entry = /** @type {Record<string, unknown>} */ (diffEntry);
    if (side === 'new') {
        if (!('new_value' in entry)) {
            throw new Error('resolveInspectValue: new_value is required');
        }
        return entry.new_value;
    }
    if (!('old_value' in entry)) {
        throw new Error('resolveInspectValue: old_value is required');
    }
    return entry.old_value;
}

/**
 * @param {unknown} diffEntry
 * @param {CanvasRunResultTranslate} t
 * @returns {NodeRunChangeRow}
 */
function _buildChangeRow(diffEntry, t) {
    if (diffEntry === null || typeof diffEntry !== 'object' || Array.isArray(diffEntry)) {
        throw new Error('buildNodeRunChangeRows: diff entry must be an object');
    }
    const entry = /** @type {Record<string, unknown>} */ (diffEntry);
    const path = entry.path;
    const changeType = entry.change_type;
    if (typeof path !== 'string') {
        throw new Error('buildNodeRunChangeRows: diff entry.path must be a string');
    }
    if (changeType !== 'added' && changeType !== 'changed' && changeType !== 'removed') {
        throw new Error('buildNodeRunChangeRows: diff entry.change_type must be added, changed, or removed');
    }
    if (!('old_value' in entry)) {
        throw new Error('buildNodeRunChangeRows: diff entry.old_value is required');
    }
    if (!('new_value' in entry)) {
        throw new Error('buildNodeRunChangeRows: diff entry.new_value is required');
    }
    t = _resolveTranslate(t);
    let badge = '~';
    let badgeLabel = t('canvas_run_result.change_changed');
    if (changeType === 'added') {
        badge = '+';
        badgeLabel = t('canvas_run_result.change_added');
    } else if (changeType === 'removed') {
        badge = '-';
        badgeLabel = t('canvas_run_result.change_removed');
    }
    const inspectValue = changeType === 'removed' ? entry.old_value : entry.new_value;
    const classified = classifyNodeRunValue(inspectValue);
    const typeLabel = nodeRunValueKindLabel(classified, t);
    let detail = '';
    if (changeType === 'changed') {
        const oldClassified = classifyNodeRunValue(entry.old_value);
        const newClassified = classifyNodeRunValue(entry.new_value);
        const oldText = _formatClassifiedCanvasValue(oldClassified, t, 24);
        const newText = _formatClassifiedCanvasValue(newClassified, t, 24);
        detail = `${oldText} → ${newText}`;
    } else {
        detail = _formatClassifiedCanvasValue(classified, t, CANVAS_RUN_RESULT_VALUE_MAX);
    }
    return {
        path,
        changeType,
        badge,
        badgeLabel,
        label: formatDiffPathLabel(path),
        detail,
        valueKind: classified.kind,
        typeLabel,
    };
}

/**
 * @param {Record<string, unknown>} result
 * @param {CanvasRunResultTranslate | undefined} t
 * @param {{ limit?: number }} [options]
 * @returns {NodeRunChangeRow[]}
 */
export function buildNodeRunChangeRows(result, t, options) {
    if (result === null || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('buildNodeRunChangeRows: result must be an object');
    }
    const diff = result.diff;
    if (!Array.isArray(diff)) {
        throw new Error('buildNodeRunChangeRows: result.diff must be an array');
    }
    const primaryField = typeof result.primary_field === 'string' ? result.primary_field : '';
    const sorted = _sortDiffForDisplay(diff, primaryField);
    let limit = sorted.length;
    if (options !== undefined) {
        if (options === null || typeof options !== 'object' || Array.isArray(options)) {
            throw new Error('buildNodeRunChangeRows: options must be an object');
        }
        if ('limit' in options) {
            const rawLimit = options.limit;
            if (typeof rawLimit !== 'number' || !Number.isFinite(rawLimit) || rawLimit <= 0) {
                throw new Error('buildNodeRunChangeRows: options.limit must be a positive number');
            }
            limit = Math.floor(rawLimit);
        }
    }
    const rows = [];
    for (let i = 0; i < sorted.length && i < limit; i += 1) {
        rows.push(_buildChangeRow(sorted[i], t));
    }
    return rows;
}

/**
 * @param {Record<string, unknown>} result
 * @param {CanvasRunResultTranslate} t
 */
function _findDiffValue(result, pathPrefix) {
    const diff = result.diff;
    if (!Array.isArray(diff)) {
        return null;
    }
    for (let i = 0; i < diff.length; i += 1) {
        const entry = diff[i];
        if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
            continue;
        }
        const path = /** @type {{ path?: unknown }} */ (entry).path;
        if (typeof path !== 'string') {
            continue;
        }
        if (path === pathPrefix || path.startsWith(`${pathPrefix}.`)) {
            if ('new_value' in entry) {
                return /** @type {{ new_value: unknown }} */ (entry).new_value;
            }
        }
    }
    return null;
}

/**
 * @param {string} preview
 */
function _looksLikeRawJson(preview) {
    const trimmed = preview.trim();
    return trimmed.startsWith('{') || trimmed.startsWith('[');
}

/**
 * @param {Record<string, unknown>} result
 * @param {CanvasRunResultTranslate | undefined} t
 */
export function buildNodeRunHeadline(result, t) {
    if (result === null || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('buildNodeRunHeadline: result must be an object');
    }
    t = _resolveTranslate(t);
    const kind = result.kind;
    if (kind === 'error') {
        const errorText = result.error;
        if (typeof errorText !== 'string') {
            throw new Error('buildNodeRunHeadline: error result.error must be a string');
        }
        return truncateForCanvas(errorText, CANVAS_RUN_RESULT_PRIMARY_MAX);
    }
    if (kind !== 'ok') {
        throw new Error('buildNodeRunHeadline: result.kind must be ok or error');
    }
    const nodeType = typeof result.node_type === 'string' ? result.node_type : '';
    const preview = typeof result.result_preview === 'string' ? result.result_preview : '';
    const primaryField = typeof result.primary_field === 'string' ? result.primary_field : '';

    if (nodeType === 'llm_node') {
        if (preview.length > 0 && !_looksLikeRawJson(preview)) {
            return truncateForCanvas(preview, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
        const responseValue = _findDiffValue(result, 'response');
        if (responseValue !== null) {
            return formatCanvasValue(responseValue, t, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
    }

    if (nodeType === 'mcp') {
        const nestedStatus = _findDiffValue(result, 'variables.search_providers_status');
        let statusValue = nestedStatus;
        if (statusValue === null) {
            statusValue = _findDiffValue(result, 'search_providers_status');
        }
        if (statusValue !== null && _isStatusMap(statusValue)) {
            return formatCanvasValue(statusValue, t, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
        const mcpValue = _findDiffValue(result, 'mcp_result');
        if (mcpValue !== null) {
            return formatCanvasValue(mcpValue, t, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
    }

    if (nodeType === 'code') {
        if (preview.length > 0 && !_looksLikeRawJson(preview)) {
            return truncateForCanvas(preview, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
        const resultValue = _findDiffValue(result, 'result');
        if (resultValue !== null) {
            return formatCanvasValue(resultValue, t, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
    }

    if (nodeType === 'external_api') {
        const apiStatus = _findDiffValue(result, 'api_status');
        if (typeof apiStatus === 'number' || typeof apiStatus === 'string') {
            const statusText = t('canvas_run_result.headline_external_api', {
                status: String(apiStatus),
            });
            const apiResponse = _findDiffValue(result, 'api_response');
            if (apiResponse !== null) {
                const body = formatCanvasValue(apiResponse, t, 40);
                return truncateForCanvas(`${statusText} · ${body}`, CANVAS_RUN_RESULT_PRIMARY_MAX);
            }
            return truncateForCanvas(statusText, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
    }

    if (nodeType === 'flow' || nodeType === 'remote_flow') {
        if (preview.length > 0) {
            return truncateForCanvas(preview, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
        const resultValue = _findDiffValue(result, 'result');
        if (resultValue !== null) {
            return formatCanvasValue(resultValue, t, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
    }

    if (nodeType === 'hitl_node') {
        return truncateForCanvas(
            t('canvas_run_result.headline_hitl'),
            CANVAS_RUN_RESULT_PRIMARY_MAX,
        );
    }

    if (nodeType === 'channel') {
        return truncateForCanvas(
            t('canvas_run_result.headline_channel_ok'),
            CANVAS_RUN_RESULT_PRIMARY_MAX,
        );
    }

    if (preview.length > 0 && !_looksLikeRawJson(preview)) {
        return truncateForCanvas(preview, CANVAS_RUN_RESULT_PRIMARY_MAX);
    }

    if (primaryField.length > 0) {
        const primaryValue = _findDiffValue(result, primaryField);
        if (primaryValue !== null) {
            return formatCanvasValue(primaryValue, t, CANVAS_RUN_RESULT_PRIMARY_MAX);
        }
    }

    const changeRows = buildNodeRunChangeRows(result, t, { limit: 1 });
    if (changeRows.length > 0) {
        const first = changeRows[0];
        return truncateForCanvas(`${first.label}: ${first.detail}`, CANVAS_RUN_RESULT_PRIMARY_MAX);
    }

    return '';
}

/**
 * @param {Record<string, unknown>} result
 * @param {CanvasRunResultTranslate | undefined} t
 * @returns {NodeRunViewModel}
 */
export function buildNodeRunViewModel(result, t) {
    t = _resolveTranslate(t);
    const headline = buildNodeRunHeadline(result, t);
    const allRows = result.kind === 'ok' ? buildNodeRunChangeRows(result, t) : [];
    const limit = CANVAS_RUN_RESULT_EXPANDED_DIFF_LINES;
    const changeRows = allRows.length > limit ? allRows.slice(0, limit) : allRows;
    const omittedCount = allRows.length > limit ? allRows.length - limit : 0;
    let hasMeta = false;
    const durationMs = result.duration_ms;
    if (typeof durationMs === 'number' && Number.isFinite(durationMs)) {
        hasMeta = true;
    }
    if (result.kind === 'ok' && allRows.length > 0) {
        hasMeta = true;
    }
    return {
        headline,
        changeRows,
        omittedCount,
        hasMeta,
    };
}

/**
 * @param {string} text
 * @param {number} maxLen
 */
export function truncateForCanvas(text, maxLen) {
    if (typeof text !== 'string') {
        throw new Error('truncateForCanvas: text must be a string');
    }
    if (!Number.isFinite(maxLen) || maxLen <= 0) {
        throw new Error('truncateForCanvas: maxLen must be a positive number');
    }
    if (text.length <= maxLen) {
        return text;
    }
    if (maxLen === 1) {
        return '…';
    }
    return `${text.slice(0, maxLen - 1)}…`;
}

/**
 * @param {unknown[]} results
 */
export function pickLatestNodeRunResult(results) {
    if (!Array.isArray(results)) {
        throw new Error('pickLatestNodeRunResult: results must be an array');
    }
    if (results.length === 0) {
        return null;
    }
    const last = results[results.length - 1];
    if (last === null || typeof last !== 'object' || Array.isArray(last)) {
        throw new Error('pickLatestNodeRunResult: last result must be an object');
    }
    return last;
}

/**
 * @param {unknown[]} results
 * @param {number} runIndex
 */
export function findNodeRunResult(results, runIndex) {
    if (!Array.isArray(results) || results.length === 0) {
        throw new Error('findNodeRunResult: results must be a non-empty array');
    }
    if (typeof runIndex !== 'number' || !Number.isFinite(runIndex)) {
        throw new Error('findNodeRunResult: runIndex must be a number');
    }
    const index = Math.floor(runIndex);
    for (let i = 0; i < results.length; i += 1) {
        const item = results[i];
        if (item === null || typeof item !== 'object' || Array.isArray(item)) {
            throw new Error('findNodeRunResult: result must be an object');
        }
        const itemIndex = /** @type {{ run_index?: unknown }} */ (item).run_index;
        if (typeof itemIndex === 'number' && Number.isFinite(itemIndex) && Math.floor(itemIndex) === index) {
            return item;
        }
    }
    throw new Error(`findNodeRunResult: no result for run_index ${String(index)}`);
}

/**
 * @param {unknown[]} results
 * @param {number} runIndex
 */
export function isLatestNodeRun(results, runIndex) {
    const latest = pickLatestNodeRunResult(results);
    if (latest === null) {
        throw new Error('isLatestNodeRun: results must be non-empty');
    }
    const latestIndex = typeof latest.run_index === 'number' && Number.isFinite(latest.run_index)
        ? Math.floor(latest.run_index)
        : results.length - 1;
    if (typeof runIndex !== 'number' || !Number.isFinite(runIndex)) {
        throw new Error('isLatestNodeRun: runIndex must be a number');
    }
    return latestIndex === Math.floor(runIndex);
}

/**
 * @param {Record<string, unknown>} result
 * @param {CanvasRunResultTranslate | undefined} t
 */
export function buildNodeRunPrimaryLine(result, t) {
    return buildNodeRunHeadline(result, t);
}

/**
 * @param {Record<string, unknown>} result
 */
export function countNodeRunDiffChanges(result) {
    if (result === null || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('countNodeRunDiffChanges: result must be an object');
    }
    const diff = result.diff;
    if (!Array.isArray(diff)) {
        throw new Error('countNodeRunDiffChanges: result.diff must be an array');
    }
    return diff.length;
}

/**
 * @param {Record<string, unknown>} result
 * @param {string} path
 */
export function findDiffEntryByPath(result, path) {
    if (result === null || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('findDiffEntryByPath: result must be an object');
    }
    if (typeof path !== 'string' || path.length === 0) {
        throw new Error('findDiffEntryByPath: path must be a non-empty string');
    }
    const diff = result.diff;
    if (!Array.isArray(diff)) {
        throw new Error('findDiffEntryByPath: result.diff must be an array');
    }
    for (let i = 0; i < diff.length; i += 1) {
        const entry = diff[i];
        if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
            throw new Error('findDiffEntryByPath: diff entry must be an object');
        }
        if (entry.path === path) {
            return entry;
        }
    }
    throw new Error(`findDiffEntryByPath: no diff entry for path ${path}`);
}

/**
 * @param {Record<string, unknown>} result
 * @param {string} path
 */
export function nodeRunDiffHasPath(result, path) {
    if (result === null || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('nodeRunDiffHasPath: result must be an object');
    }
    if (typeof path !== 'string' || path.length === 0) {
        throw new Error('nodeRunDiffHasPath: path must be a non-empty string');
    }
    const diff = result.diff;
    if (!Array.isArray(diff)) {
        throw new Error('nodeRunDiffHasPath: result.diff must be an array');
    }
    for (let i = 0; i < diff.length; i += 1) {
        const entry = diff[i];
        if (entry === null || typeof entry !== 'object' || Array.isArray(entry)) {
            throw new Error('nodeRunDiffHasPath: diff entry must be an object');
        }
        if (entry.path === path) {
            return true;
        }
    }
    return false;
}

/**
 * @param {Record<string, unknown>} result
 * @param {CanvasRunResultTranslate | undefined} t
 * @returns {string[]}
 */
export function buildNodeRunDiffPreviewLines(result, t) {
    const rows = buildNodeRunChangeRows(result, t, { limit: CANVAS_RUN_RESULT_EXPANDED_DIFF_LINES });
    return rows.map((row) => truncateForCanvas(
        `${row.badge} ${row.label}  ${row.detail}`,
        CANVAS_RUN_RESULT_DIFF_PREVIEW_MAX,
    ));
}

/**
 * @param {string} text
 * @param {number} charsPerLine
 */
function _estimateTextLineCount(text, charsPerLine) {
    if (text.length === 0) {
        return 0;
    }
    if (!Number.isFinite(charsPerLine) || charsPerLine <= 0) {
        throw new Error('_estimateTextLineCount: charsPerLine must be a positive number');
    }
    return Math.ceil(text.length / charsPerLine);
}

/**
 * @param {NodeRunChangeRow} row
 */
function _estimateChangeRowHeight(row) {
    const labelLines = _estimateTextLineCount(row.label, CANVAS_RUN_RESULT_CHANGE_ROW_CHARS_PER_LINE);
    let bodyHeight = labelLines * CANVAS_RUN_RESULT_CHANGE_ROW_LABEL_LINE_H;
    const detailLines = _estimateTextLineCount(row.detail, CANVAS_RUN_RESULT_CHANGE_ROW_CHARS_PER_LINE);
    if (detailLines > 0) {
        bodyHeight += CANVAS_RUN_RESULT_CHANGE_ROW_DETAIL_MARGIN
            + detailLines * CANVAS_RUN_RESULT_CHANGE_ROW_DETAIL_LINE_H;
    }
    return Math.max(CANVAS_RUN_RESULT_CHANGE_ROW_BADGE_H, bodyHeight);
}

/**
 * @param {NodeRunChangeRow[]} rows
 */
function _estimateChangeListHeight(rows) {
    if (rows.length === 0) {
        return 0;
    }
    let height = CANVAS_RUN_RESULT_CHANGE_LIST_GAP;
    for (let i = 0; i < rows.length; i += 1) {
        height += _estimateChangeRowHeight(rows[i]);
    }
    height += (rows.length - 1) * CANVAS_RUN_RESULT_CHANGE_ROW_GAP;
    return height;
}

/**
 * @param {Record<string, unknown>} result
 * @param {boolean} expanded
 * @param {CanvasRunResultTranslate | undefined} t
 */
export function getNodeRunResultPillHeight(result, expanded, t) {
    if (result === null || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('getNodeRunResultPillHeight: result must be an object');
    }
    if (typeof expanded !== 'boolean') {
        throw new Error('getNodeRunResultPillHeight: expanded must be a boolean');
    }
    const viewModel = buildNodeRunViewModel(result, t);
    let height = CANVAS_RUN_RESULT_PILL_PAD_V + CANVAS_RUN_RESULT_BOTTOM_PAD;
    height += CANVAS_RUN_RESULT_HEADLINE_LINE_H * CANVAS_RUN_RESULT_HEADLINE_MAX_LINES;
    if (viewModel.hasMeta) {
        height += CANVAS_RUN_RESULT_META_MARGIN + CANVAS_RUN_RESULT_META_H;
    }
    if (expanded && viewModel.changeRows.length > 0) {
        height += _estimateChangeListHeight(viewModel.changeRows);
        if (viewModel.omittedCount > 0) {
            height += CANVAS_RUN_RESULT_CHANGE_ROW_GAP + CANVAS_RUN_RESULT_MORE_ROW_H;
        }
    }
    return Math.max(CANVAS_RUN_RESULT_PILL_COLLAPSED_H, height);
}

/**
 * @param {string} nodeId
 * @param {number} runIndex
 */
export function nodeRunResultExpandKey(nodeId, runIndex) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('nodeRunResultExpandKey: nodeId must be a non-empty string');
    }
    if (!Number.isFinite(runIndex)) {
        throw new Error('nodeRunResultExpandKey: runIndex must be a number');
    }
    return `${nodeId}:${String(Math.floor(runIndex))}`;
}

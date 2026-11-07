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

type CanvasRunResultTranslate = (key: string, params?: Record<string, string>) => string;

type NodeRunValueKind = 'null' | 'empty' | 'boolean' | 'number' | 'string' | 'markdown' | 'json_string' | 'status_map' | 'array' | 'object';

interface NodeRunValueClassification {
    kind: NodeRunValueKind;
    preview: string;
    parsed: unknown;
}

interface NodeRunChangeRow {
    path: string;
    changeType: 'added' | 'changed' | 'removed';
    badge: string;
    badgeLabel: string;
    label: string;
    detail: string;
    valueKind: NodeRunValueKind;
    typeLabel: string;
}

interface NodeRunViewModel {
    headline: string;
    changeRows: NodeRunChangeRow[];
    omittedCount: number;
    hasMeta: boolean;
}

const DEFAULT_I18N: Record<string, string> = Object.freeze({
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

function isCanvasRunResultTranslate(value: unknown): value is CanvasRunResultTranslate {
    return typeof value === 'function';
}

function _resolveTranslate(translate: unknown): CanvasRunResultTranslate {
    if (isCanvasRunResultTranslate(translate)) {
        return translate;
    }
    return (key, params) => {
        let text = DEFAULT_I18N[key];
        if (typeof text !== 'string') {
            throw new Error(`flows-node-run-result: missing default i18n key ${key}`);
        }
        if (params !== undefined) {
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
function _isPlainObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * @param {unknown} value
 */
function _isStatusEntry(value: unknown): value is Record<string, unknown> {
    if (!_isPlainObject(value)) {
        return false;
    }
    return 'ok' in value;
}

/**
 * @param {unknown} value
 */
function _isStatusMap(value: unknown): value is Record<string, unknown> {
    if (!_isPlainObject(value)) {
        return false;
    }
    const entries = Object.entries(value);
    if (entries.length === 0) {
        return false;
    }
    for (let i = 0; i < entries.length; i += 1) {
        const pair = entries[i];
        if (pair === undefined) {
            throw new Error('node run result: status entry missing');
        }
        if (!_isStatusEntry(pair[1])) {
            return false;
        }
    }
    return true;
}

/**
 * @param {Record<string, unknown>} value
 */
function _formatStatusMap(value: Record<string, unknown>) {
    const parts: string[] = [];
    const entries = Object.entries(value);
    for (let i = 0; i < entries.length; i += 1) {
        const pair = entries[i];
        if (pair === undefined) {
            throw new Error('node run result: status entry missing');
        }
        const key = pair[0];
        const entry = pair[1];
        if (!_isStatusEntry(entry)) {
            continue;
        }
        const okValue = entry.ok;
        const statusText = okValue === true ? 'ok' : 'fail';
        let part = `${key}: ${statusText}`;
        const latencyMs = entry.latency_ms;
        if (typeof latencyMs === 'number' && Number.isFinite(latencyMs)) {
            part += ` · ${String(Math.round(latencyMs))} ms`;
        }
        parts.push(part);
    }
    return parts.join(', ');
}

function _parseJsonContainer(text: string): { ok: true; value: unknown } | { ok: false } {
    const trimmed = text.trim();
    if (trimmed.length === 0) {
        return { ok: false };
    }
    const first = trimmed[0];
    if (first !== '{' && first !== '[') {
        return { ok: false };
    }
    try {
        const parsed: unknown = JSON.parse(trimmed);
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

function _looksLikeMarkdown(text: string) {
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

export function classifyNodeRunValue(value: unknown): NodeRunValueClassification {
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

export function nodeRunValueKindLabel(classified: NodeRunValueClassification, translate: unknown) {
    const t = _resolveTranslate(translate);
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
        const count = Object.keys(classified.parsed).length;
        return t('canvas_run_result.type_object', { count: String(count) });
    }
    throw new Error(`nodeRunValueKindLabel: unknown kind ${kind}`);
}

function _formatClassifiedCanvasValue(classified: NodeRunValueClassification, translate: unknown, maxLen: number) {
    const t = _resolveTranslate(translate);
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

export function formatCanvasValue(value: unknown, translate: unknown, maxLen = CANVAS_RUN_RESULT_VALUE_MAX) {
    const t = _resolveTranslate(translate);
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
        return truncateForCanvas(_formatStatusMap(value), maxLen);
    }
    if (_isPlainObject(value)) {
        const entries = Object.entries(value);
        const count = String(entries.length);
        const fieldsKey = entries.length === 1
            ? 'canvas_run_result.value_object_fields_one'
            : 'canvas_run_result.value_object_fields_other';
        const previews: string[] = [];
        for (let i = 0; i < entries.length && previews.length < 2; i += 1) {
            const pair = entries[i];
            if (pair === undefined) {
                throw new Error('node run result: field entry missing');
            }
            const entryValue = pair[1];
            if (typeof entryValue === 'string' || typeof entryValue === 'number' || typeof entryValue === 'boolean') {
                previews.push(`${pair[0]}: ${String(entryValue)}`);
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
export function serializeNodeRunValue(value: unknown) {
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
 * @param {string} path
 */
export function formatDiffPathLabel(path: string) {
    if (typeof path !== 'string') {
        throw new Error('formatDiffPathLabel: path must be a string');
    }
    if (path.startsWith('variables.')) {
        return path.slice('variables.'.length);
    }
    return path;
}

function _diffPathScore(path: string, primaryField: string) {
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

function _diffEntryPath(entry: unknown): string {
    if (!_isPlainObject(entry) || typeof entry.path !== 'string') {
        throw new Error('node run result: diff entry path must be a string');
    }
    return entry.path;
}

function _sortDiffForDisplay(diff: unknown[], primaryField: string) {
    return [...diff].sort((left, right) => {
        const leftPath = _diffEntryPath(left);
        const rightPath = _diffEntryPath(right);
        const leftScore = _diffPathScore(leftPath, primaryField);
        const rightScore = _diffPathScore(rightPath, primaryField);
        if (leftScore !== rightScore) {
            return leftScore - rightScore;
        }
        return leftPath.localeCompare(rightPath);
    });
}

export function resolveInspectValue(diffEntry: unknown, side: unknown) {
    if (!_isPlainObject(diffEntry)) {
        throw new Error('resolveInspectValue: diff entry must be an object');
    }
    if (side !== 'new' && side !== 'old') {
        throw new Error('resolveInspectValue: side must be new or old');
    }
    const entry = diffEntry;
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

function _buildChangeRow(diffEntry: unknown, translate: unknown): NodeRunChangeRow {
    if (!_isPlainObject(diffEntry)) {
        throw new Error('buildNodeRunChangeRows: diff entry must be an object');
    }
    const entry = diffEntry;
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
    const t = _resolveTranslate(translate);
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

export function buildNodeRunChangeRows(result: unknown, translate: unknown, options?: unknown): NodeRunChangeRow[] {
    if (!_isPlainObject(result)) {
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
        if (!_isPlainObject(options)) {
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
    const rows: NodeRunChangeRow[] = [];
    for (let i = 0; i < sorted.length && i < limit; i += 1) {
        const entry = sorted[i];
        if (entry === undefined) {
            throw new Error('node run result: diff entry missing');
        }
        rows.push(_buildChangeRow(entry, translate));
    }
    return rows;
}

function _findDiffValue(result: Record<string, unknown>, pathPrefix: string): unknown {
    const diff = result.diff;
    if (!Array.isArray(diff)) {
        return null;
    }
    for (const entry of diff) {
        if (!_isPlainObject(entry) || typeof entry.path !== 'string') {
            continue;
        }
        if (entry.path === pathPrefix || entry.path.startsWith(`${pathPrefix}.`)) {
            if ('new_value' in entry) {
                return entry.new_value;
            }
        }
    }
    return null;
}

function _looksLikeRawJson(preview: string) {
    const trimmed = preview.trim();
    return trimmed.startsWith('{') || trimmed.startsWith('[');
}

export function buildNodeRunHeadline(result: unknown, translate: unknown) {
    if (!_isPlainObject(result)) {
        throw new Error('buildNodeRunHeadline: result must be an object');
    }
    const t = _resolveTranslate(translate);
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
        if (first === undefined) {
            throw new Error('node run result: change row missing');
        }
        return truncateForCanvas(`${first.label}: ${first.detail}`, CANVAS_RUN_RESULT_PRIMARY_MAX);
    }

    return '';
}

export function buildNodeRunViewModel(result: unknown, translate: unknown): NodeRunViewModel {
    if (!_isPlainObject(result)) {
        throw new Error('buildNodeRunViewModel: result must be an object');
    }
    const t = _resolveTranslate(translate);
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

export function truncateForCanvas(text: unknown, maxLen: unknown) {
    if (typeof text !== 'string') {
        throw new Error('truncateForCanvas: text must be a string');
    }
    if (typeof maxLen !== 'number' || !Number.isFinite(maxLen) || maxLen <= 0) {
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

export function pickLatestNodeRunResult(results: unknown): Record<string, unknown> | null {
    if (!Array.isArray(results)) {
        throw new Error('pickLatestNodeRunResult: results must be an array');
    }
    if (results.length === 0) {
        return null;
    }
    const last = results[results.length - 1];
    if (!_isPlainObject(last)) {
        throw new Error('pickLatestNodeRunResult: last result must be an object');
    }
    return last;
}

export function findNodeRunResult(results: unknown, runIndex: unknown): Record<string, unknown> {
    if (!Array.isArray(results) || results.length === 0) {
        throw new Error('findNodeRunResult: results must be a non-empty array');
    }
    if (typeof runIndex !== 'number' || !Number.isFinite(runIndex)) {
        throw new Error('findNodeRunResult: runIndex must be a number');
    }
    const index = Math.floor(runIndex);
    for (let i = 0; i < results.length; i += 1) {
        const item = results[i];
        if (!_isPlainObject(item)) {
            throw new Error('findNodeRunResult: result must be an object');
        }
        const itemIndex = item.run_index;
        if (typeof itemIndex === 'number' && Number.isFinite(itemIndex) && Math.floor(itemIndex) === index) {
            return item;
        }
    }
    throw new Error(`findNodeRunResult: no result for run_index ${String(index)}`);
}

export function isLatestNodeRun(results: unknown, runIndex: unknown) {
    if (!Array.isArray(results)) {
        throw new Error('isLatestNodeRun: results must be an array');
    }
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

export function buildNodeRunPrimaryLine(result: unknown, translate: unknown) {
    return buildNodeRunHeadline(result, translate);
}

export function countNodeRunDiffChanges(result: unknown) {
    if (!_isPlainObject(result)) {
        throw new Error('countNodeRunDiffChanges: result must be an object');
    }
    const diff = result.diff;
    if (!Array.isArray(diff)) {
        throw new Error('countNodeRunDiffChanges: result.diff must be an array');
    }
    return diff.length;
}

export function findDiffEntryByPath(result: unknown, path: string): Record<string, unknown> {
    if (!_isPlainObject(result)) {
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
        if (!_isPlainObject(entry)) {
            throw new Error('findDiffEntryByPath: diff entry must be an object');
        }
        if (entry.path === path) {
            return entry;
        }
    }
    throw new Error(`findDiffEntryByPath: no diff entry for path ${path}`);
}

export function nodeRunDiffHasPath(result: unknown, path: string) {
    if (!_isPlainObject(result)) {
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
        if (!_isPlainObject(entry)) {
            throw new Error('nodeRunDiffHasPath: diff entry must be an object');
        }
        if (entry.path === path) {
            return true;
        }
    }
    return false;
}

export function buildNodeRunDiffPreviewLines(result: unknown, translate: unknown) {
    const rows = buildNodeRunChangeRows(result, translate, { limit: CANVAS_RUN_RESULT_EXPANDED_DIFF_LINES });
    return rows.map((row) => truncateForCanvas(
        `${row.badge} ${row.label}  ${row.detail}`,
        CANVAS_RUN_RESULT_DIFF_PREVIEW_MAX,
    ));
}

function _estimateTextLineCount(text: string, charsPerLine: number) {
    if (text.length === 0) {
        return 0;
    }
    if (!Number.isFinite(charsPerLine) || charsPerLine <= 0) {
        throw new Error('_estimateTextLineCount: charsPerLine must be a positive number');
    }
    return Math.ceil(text.length / charsPerLine);
}

function _estimateChangeRowHeight(row: NodeRunChangeRow) {
    const labelLines = _estimateTextLineCount(row.label, CANVAS_RUN_RESULT_CHANGE_ROW_CHARS_PER_LINE);
    let bodyHeight = labelLines * CANVAS_RUN_RESULT_CHANGE_ROW_LABEL_LINE_H;
    const detailLines = _estimateTextLineCount(row.detail, CANVAS_RUN_RESULT_CHANGE_ROW_CHARS_PER_LINE);
    if (detailLines > 0) {
        bodyHeight += CANVAS_RUN_RESULT_CHANGE_ROW_DETAIL_MARGIN
            + detailLines * CANVAS_RUN_RESULT_CHANGE_ROW_DETAIL_LINE_H;
    }
    return Math.max(CANVAS_RUN_RESULT_CHANGE_ROW_BADGE_H, bodyHeight);
}

function _estimateChangeListHeight(rows: NodeRunChangeRow[]) {
    if (rows.length === 0) {
        return 0;
    }
    let height = CANVAS_RUN_RESULT_CHANGE_LIST_GAP;
    for (const row of rows) {
        height += _estimateChangeRowHeight(row);
    }
    height += (rows.length - 1) * CANVAS_RUN_RESULT_CHANGE_ROW_GAP;
    return height;
}

export function getNodeRunResultPillHeight(result: unknown, expanded: unknown, translate: unknown) {
    if (result === null || typeof result !== 'object' || Array.isArray(result)) {
        throw new Error('getNodeRunResultPillHeight: result must be an object');
    }
    if (typeof expanded !== 'boolean') {
        throw new Error('getNodeRunResultPillHeight: expanded must be a boolean');
    }
    const viewModel = buildNodeRunViewModel(result, translate);
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

export function nodeRunResultExpandKey(nodeId: string, runIndex: unknown) {
    if (typeof nodeId !== 'string' || nodeId.length === 0) {
        throw new Error('nodeRunResultExpandKey: nodeId must be a non-empty string');
    }
    if (typeof runIndex !== 'number' || !Number.isFinite(runIndex)) {
        throw new Error('nodeRunResultExpandKey: runIndex must be a number');
    }
    return `${nodeId}:${String(Math.floor(runIndex))}`;
}

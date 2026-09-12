/**
 * Декодер A2A Parts по ``mediaType`` и применение RFC 6902 к проекции state.
 *
 * ``text`` → текст; ``url`` → файл; ``data`` без mediaType → произвольный JSON
 * платформенного артефакта (tool_call, node_start, operator_files, …);
 * ``application/json`` → snapshot state; ``application/json-patch+json`` → патч;
 * ``application/vnd.platform.ui+json`` → событие интерфейса. Любой другой
 * mediaType у ``data`` Part — ошибка протокола.
 */

import {
    FLOW_UI_ACTION_MEDIA_TYPE,
    FLOW_UI_MEDIA_TYPE,
    JSON_MEDIA_TYPE,
    JSON_PATCH_MEDIA_TYPE,
} from './constants.js';

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function decodePart(part) {
    if (!isObject(part)) throw new Error('flow-ui: Part must be an object');
    if (typeof part.text === 'string') return { kind: 'text', text: part.text };
    if (typeof part.url === 'string') {
        return {
            kind: 'file',
            file: {
                url: part.url,
                mediaType: typeof part.mediaType === 'string' ? part.mediaType : '',
                filename: typeof part.filename === 'string' ? part.filename : '',
            },
        };
    }
    if (part.raw !== undefined) {
        return {
            kind: 'raw',
            raw: part.raw,
            mediaType: typeof part.mediaType === 'string' ? part.mediaType : '',
        };
    }
    if (!('data' in part)) throw new Error('flow-ui: Part has neither text, url, raw nor data');
    const mediaType = typeof part.mediaType === 'string' ? part.mediaType : '';
    if (mediaType === '') return { kind: 'data', value: part.data };
    if (mediaType === JSON_MEDIA_TYPE) {
        if (!isObject(part.data)) throw new Error('flow-ui: state snapshot must be an object');
        return { kind: 'json', value: part.data };
    }
    if (mediaType === JSON_PATCH_MEDIA_TYPE) {
        if (!Array.isArray(part.data)) throw new Error('flow-ui: json patch must be an array');
        return { kind: 'json_patch', operations: part.data };
    }
    if (mediaType === FLOW_UI_MEDIA_TYPE) {
        if (!isObject(part.data) || (part.data.kind !== 'render' && part.data.kind !== 'navigate')) {
            throw new Error('flow-ui: ui event must be render or navigate');
        }
        return { kind: 'ui', event: part.data };
    }
    if (mediaType === FLOW_UI_ACTION_MEDIA_TYPE) {
        if (!isObject(part.data) || typeof part.data.action !== 'string') {
            throw new Error('flow-ui: ui action part requires action');
        }
        return { kind: 'ui_action', action: part.data };
    }
    throw new Error(`flow-ui: unsupported Part mediaType ${JSON.stringify(mediaType)}`);
}

export function decodeParts(parts) {
    return (Array.isArray(parts) ? parts : []).map(decodePart);
}

export function textFromParts(parts) {
    let text = '';
    for (const part of Array.isArray(parts) ? parts : []) {
        if (isObject(part) && typeof part.text === 'string') text += part.text;
    }
    return text;
}

export function filesFromParts(parts) {
    return decodeParts(parts).filter((decoded) => decoded.kind === 'file').map((decoded) => decoded.file);
}

export function firstDataFromParts(parts) {
    for (const part of Array.isArray(parts) ? parts : []) {
        if (isObject(part) && 'data' in part) return part.data;
    }
    return null;
}

function pointerSegments(pointer) {
    if (pointer === '') return [];
    if (!pointer.startsWith('/')) throw new Error(`flow-ui: invalid JSON pointer ${JSON.stringify(pointer)}`);
    return pointer.slice(1).split('/').map((segment) => segment.replace(/~1/g, '/').replace(/~0/g, '~'));
}

function cloneJson(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
}

/** Применяет add/replace/remove к копии ``target``; чужой путь при remove — ошибка (как в Python). */
export function applyJsonPatch(target, operations) {
    if (!isObject(target)) throw new Error('flow-ui: json patch target must be an object');
    if (!Array.isArray(operations)) throw new Error('flow-ui: json patch operations must be an array');
    let result = cloneJson(target);
    for (const operation of operations) {
        if (!isObject(operation) || typeof operation.path !== 'string') {
            throw new Error('flow-ui: json patch operation requires path');
        }
        if (operation.op !== 'add' && operation.op !== 'replace' && operation.op !== 'remove') {
            throw new Error(`flow-ui: unsupported json patch op ${JSON.stringify(operation.op)}`);
        }
        const segments = pointerSegments(operation.path);
        if (segments.length === 0) {
            if (operation.op === 'remove') throw new Error('flow-ui: json patch cannot remove document root');
            if (!isObject(operation.value)) throw new Error('flow-ui: json patch root value must be an object');
            result = cloneJson(operation.value);
            continue;
        }
        let parent = result;
        for (const segment of segments.slice(0, -1)) {
            if (!isObject(parent[segment])) {
                if (operation.op === 'remove') {
                    throw new Error(`flow-ui: json patch path ${operation.path} does not exist`);
                }
                parent[segment] = {};
            }
            parent = parent[segment];
        }
        const key = segments[segments.length - 1];
        if (operation.op === 'remove') {
            if (!Object.prototype.hasOwnProperty.call(parent, key)) {
                throw new Error(`flow-ui: json patch path ${operation.path} does not exist`);
            }
            delete parent[key];
        } else {
            parent[key] = cloneJson(operation.value);
        }
    }
    return result;
}

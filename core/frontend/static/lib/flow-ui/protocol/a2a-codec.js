/**
 * JSON-RPC тела и URL A2A 1.0 для Flow UI.
 *
 * Upstream-сообщение пользователя — обычное A2A ``Message``: ``text`` Part плюс
 * файловые Parts ``{url, mediaType, filename}``, либо ровно один ``data`` Part
 * ``application/vnd.platform.ui-action+json`` для действия блока интерфейса.
 */

import { A2A_PROTOCOL_VERSION, FLOW_UI_ACTION_MEDIA_TYPE } from './constants.js';

/**
 * UUID v4 через getRandomValues: ``crypto.randomUUID`` есть только в secure context,
 * а локальный стенд и E2E ходят по HTTP company-host.
 */
export function randomUuid() {
    if (!globalThis.crypto || typeof globalThis.crypto.getRandomValues !== 'function') {
        throw new Error('flow-ui: crypto.getRandomValues is required');
    }
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function createProtocolId(prefix = 'flow-ui') {
    return `${prefix}:${randomUuid()}`;
}

function rpc(method, params) {
    return { jsonrpc: '2.0', id: createProtocolId('rpc'), method, params };
}

export function a2aEndpointUrl({ baseUrl = '', flowId = '', embedId = '' }) {
    const root = String(baseUrl).trim().replace(/\/$/, '');
    if (!root) throw new Error('flow-ui: baseUrl is required');
    const embed = String(embedId || '').trim();
    const flow = String(flowId || '').trim();
    if (embed) return `${root}/api/v1/embed/${encodeURIComponent(embed)}`;
    if (!flow) throw new Error('flow-ui: flowId or embedId is required');
    return `${root}/api/v1/${encodeURIComponent(flow)}`;
}

/** Ветка графа ``base`` в A2A и control plane называется ``default``. */
export function normalizeFlowUIBranchId(branchId) {
    const raw = typeof branchId === 'string' && branchId.trim() !== '' ? branchId.trim() : 'default';
    return raw === 'base' ? 'default' : raw;
}

/** ``GET .../interface`` — design-time документ, права, look и capabilities. */
export function interfaceUrl(target) {
    const branch = normalizeFlowUIBranchId(target?.branchId);
    const query = branch === 'default' ? '' : `?branch_id=${encodeURIComponent(branch)}`;
    return `${a2aEndpointUrl(target)}/interface${query}`;
}

export function flowUIShareCollectionUrl({ baseUrl = '' } = {}) {
    const root = String(baseUrl).trim().replace(/\/$/, '');
    if (!root) throw new Error('flow-ui: baseUrl is required for share collection');
    return `${root}/api/v1/flow-ui/shares`;
}

export function buildA2aFileParts(files) {
    const list = Array.isArray(files) ? files : [];
    return list.map((file) => {
        if (!file || typeof file !== 'object') {
            throw new Error('flow-ui: file part source must be an object');
        }
        if (typeof file.url !== 'string' || file.url.trim() === '') {
            throw new Error('flow-ui: file part requires url');
        }
        if (typeof file.content_type !== 'string' || file.content_type.trim() === '') {
            throw new Error('flow-ui: file part requires content_type');
        }
        if (typeof file.original_name !== 'string' || file.original_name.trim() === '') {
            throw new Error('flow-ui: file part requires original_name');
        }
        return { url: file.url, mediaType: file.content_type, filename: file.original_name };
    });
}

/**
 * @param {{
 *   contextId?: string | null,
 *   taskId?: string | null,
 *   text?: string,
 *   files?: object[],
 *   action?: { action: string, source: string, fields: object, payload: object } | null,
 * }} input
 */
export function buildUserMessage({ contextId = null, taskId = null, text = '', files = [], action = null }) {
    const message = { messageId: createProtocolId('message'), role: 'ROLE_USER', parts: [] };
    if (action !== null) {
        if (typeof text === 'string' && text.trim() !== '') {
            throw new Error('flow-ui: ui action cannot be combined with message text');
        }
        if (typeof action.action !== 'string' || action.action.trim() === '') {
            throw new Error('flow-ui: ui action requires action name');
        }
        if (typeof action.source !== 'string' || action.source.trim() === '') {
            throw new Error('flow-ui: ui action requires source block_id');
        }
        message.parts.push({
            data: {
                action: action.action,
                source: action.source,
                fields: action.fields && typeof action.fields === 'object' ? action.fields : {},
                payload: action.payload && typeof action.payload === 'object' ? action.payload : {},
            },
            mediaType: FLOW_UI_ACTION_MEDIA_TYPE,
        });
    } else {
        message.parts.push({ text: typeof text === 'string' ? text : '' });
    }
    message.parts.push(...buildA2aFileParts(files));
    if (typeof contextId === 'string' && contextId !== '') message.contextId = contextId;
    if (typeof taskId === 'string' && taskId !== '') message.taskId = taskId;
    return message;
}

export function buildSendMessageBody(message, { streaming = true, branchId = 'default', variables = null } = {}) {
    const params = { message };
    const metadata = {};
    const branch = normalizeFlowUIBranchId(branchId);
    if (branch !== 'default') metadata.branch = branch;
    if (variables !== null && variables !== undefined) {
        if (typeof variables !== 'object' || Array.isArray(variables)) {
            throw new Error('flow-ui: metadata.variables must be a plain object');
        }
        if (Object.keys(variables).length > 0) metadata.variables = variables;
    }
    if (Object.keys(metadata).length > 0) params.metadata = metadata;
    return rpc(streaming ? 'SendStreamingMessage' : 'SendMessage', params);
}

export function buildListTasksBody({ contextId, pageSize = 50, pageToken = '', includeArtifacts = true } = {}) {
    if (typeof contextId !== 'string' || contextId.trim() === '') {
        throw new Error('flow-ui: ListTasks contextId is required');
    }
    if (!Number.isInteger(pageSize) || pageSize < 1) {
        throw new Error('flow-ui: ListTasks pageSize must be a positive int');
    }
    if (typeof pageToken !== 'string') {
        throw new Error('flow-ui: ListTasks pageToken must be a string');
    }
    return rpc('ListTasks', { contextId, pageSize, pageToken, includeArtifacts: Boolean(includeArtifacts) });
}

export function buildSubscribeTaskBody(taskId) {
    if (typeof taskId !== 'string' || !taskId.trim()) {
        throw new Error('flow-ui: SubscribeToTask taskId is required');
    }
    return rpc('SubscribeToTask', { id: taskId });
}

export function buildCancelTaskBody(taskId) {
    if (typeof taskId !== 'string' || !taskId.trim()) {
        throw new Error('flow-ui: CancelTask taskId is required');
    }
    return rpc('CancelTask', { id: taskId });
}

export function a2aRequestHeaders(headers = {}, { stream = false } = {}) {
    return {
        'Content-Type': 'application/json',
        Accept: stream ? 'text/event-stream' : 'application/json',
        'A2A-Version': A2A_PROTOCOL_VERSION,
        ...headers,
    };
}

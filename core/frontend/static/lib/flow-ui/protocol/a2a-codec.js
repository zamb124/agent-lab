import {
    A2A_PROTOCOL_VERSION,
    A2UI_EXTENSION_URI,
    A2UI_MEDIA_TYPE,
    A2UI_VERSION,
    FLOW_UI_ACTIONS,
    LINNEX_CATALOG_ID,
} from './constants.js';
import { cloneSerializable } from '../utils/clone.js';

let fallbackId = 0;

export function createProtocolId(prefix = 'flow-ui') {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === 'function') {
        return `${prefix}:${globalThis.crypto.randomUUID()}`;
    }
    fallbackId += 1;
    return `${prefix}:${Date.now()}:${fallbackId}`;
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

/** Graph branch `base` is A2A/control-plane `default`. */
export function normalizeFlowUIBranchId(branchId) {
    const raw = typeof branchId === 'string' && branchId.trim() !== '' ? branchId.trim() : 'default';
    return raw === 'base' ? 'default' : raw;
}

export function interfaceProfileUrl(target) {
    const branch = normalizeFlowUIBranchId(target?.branchId);
    const query = branch === 'default' ? '' : `?branch_id=${encodeURIComponent(branch)}`;
    return `${a2aEndpointUrl(target)}/interface-profile${query}`;
}

export function flowUIShareCollectionUrl({ baseUrl = '' } = {}) {
    const root = String(baseUrl).trim().replace(/\/$/, '');
    if (!root) throw new Error('flow-ui: baseUrl is required for share collection');
    return `${root}/api/v1/flow-ui/shares`;
}

export function a2uiCapabilities() {
    return {
        [A2UI_VERSION]: {
            supportedCatalogIds: [LINNEX_CATALOG_ID],
            inlineCatalogs: [],
        },
    };
}

function cleanObject(value) {
    return Object.fromEntries(Object.entries(value).filter(([, item]) => item !== undefined));
}

export function buildFlowUIMessage({
    kind,
    contextId = null,
    document = null,
    surfaceId = 'main',
    sourceComponentId = 'root',
    actionContext = {},
    clientMutationId = createProtocolId('mutation'),
    actionId = createProtocolId('action'),
    branchId = 'default',
    metadata = {},
}) {
    const actionName = FLOW_UI_ACTIONS[kind];
    if (!actionName) throw new Error(`flow-ui: unsupported command ${JSON.stringify(kind)}`);
    if (kind !== 'bootstrap' && (!document || typeof document !== 'object')) {
        throw new Error(`flow-ui: ${kind} requires an authoritative document`);
    }

    const message = {
        messageId: createProtocolId('message'),
        role: 'ROLE_USER',
        extensions: [A2UI_EXTENSION_URI],
        parts: [{
            data: [{
                version: A2UI_VERSION,
                action: {
                    name: actionName,
                    surfaceId,
                    sourceComponentId,
                    timestamp: new Date().toISOString(),
                    context: actionContext && typeof actionContext === 'object' ? actionContext : {},
                },
            }],
            mediaType: A2UI_MEDIA_TYPE,
            metadata: { mimeType: A2UI_MEDIA_TYPE },
        }],
    };
    if (typeof contextId === 'string' && contextId) message.contextId = contextId;

    const platformUi = cleanObject({
        documentId: document?.document_id,
        revision: document?.revision,
        actionId,
        clientMutationId,
        activePageId: document?.active_page_id,
        sessionViewState: document?.session_view_state ?? {},
    });
    const messageMetadata = {
        ...metadata,
        branch: branchId || 'default',
        platformUi,
        a2uiClientCapabilities: a2uiCapabilities(),
    };
    if (kind !== 'bootstrap') {
        if (!document.surfaces || typeof document.surfaces !== 'object') {
            throw new Error(`flow-ui: ${kind} document.surfaces is required`);
        }
        messageMetadata.a2uiClientDataModel = {
            version: A2UI_VERSION,
            surfaces: Object.fromEntries(
                Object.entries(document.surfaces).map(([id, surface]) => [
                    id,
                    { values: cloneSerializable(surface?.data_model?.values ?? {}) },
                ]),
            ),
        };
    }
    message.metadata = messageMetadata;
    return Object.freeze({ message, actionId, clientMutationId });
}

export function buildSendMessageBody(command, { streaming = false } = {}) {
    const body = {
        jsonrpc: '2.0',
        id: createProtocolId('rpc'),
        method: streaming ? 'SendStreamingMessage' : 'SendMessage',
        params: { message: command.message },
    };
    /** @type {Record<string, unknown>} */
    const paramsMetadata = {};
    const branch = command.message?.metadata?.branch;
    if (typeof branch === 'string' && branch) {
        paramsMetadata.branch = branch;
    }
    const variables = command.message?.metadata?.variables;
    if (variables != null) {
        if (typeof variables !== 'object' || Array.isArray(variables)) {
            throw new Error('flow-ui: message.metadata.variables must be a plain object');
        }
        paramsMetadata.variables = variables;
    }
    if (Object.keys(paramsMetadata).length > 0) {
        body.params.metadata = paramsMetadata;
    }
    return body;
}

export function buildGetTaskBody(taskId, historyLength = 100) {
    return {
        jsonrpc: '2.0',
        id: createProtocolId('rpc'),
        method: 'GetTask',
        params: { id: taskId, historyLength },
    };
}

export function buildListTasksBody({
    contextId,
    pageSize = 50,
    pageToken = '',
    includeArtifacts = true,
    historyLength = 0,
} = {}) {
    if (typeof contextId !== 'string' || contextId.trim() === '') {
        throw new Error('flow-ui: ListTasks contextId is required');
    }
    if (!Number.isInteger(pageSize) || pageSize < 1) {
        throw new Error('flow-ui: ListTasks pageSize must be a positive int');
    }
    if (typeof pageToken !== 'string') {
        throw new Error('flow-ui: ListTasks pageToken must be a string');
    }
    const params = {
        contextId,
        pageSize,
        pageToken,
        includeArtifacts: Boolean(includeArtifacts),
    };
    if (Number.isInteger(historyLength) && historyLength > 0) {
        params.historyLength = historyLength;
    }
    return {
        jsonrpc: '2.0',
        id: createProtocolId('rpc'),
        method: 'ListTasks',
        params,
    };
}

export function buildSubscribeTaskBody(taskId, { afterSequence = 0 } = {}) {
    if (typeof taskId !== 'string' || !taskId.trim()) {
        throw new Error('flow-ui: SubscribeToTask taskId is required');
    }
    if (!Number.isInteger(afterSequence) || afterSequence < 0) {
        throw new Error('flow-ui: SubscribeToTask afterSequence must be a non-negative int');
    }
    const params = { id: taskId };
    if (afterSequence > 0) {
        params.metadata = {
            platformUi: {
                afterSequence,
            },
        };
    }
    return {
        jsonrpc: '2.0',
        id: createProtocolId('rpc'),
        method: 'SubscribeToTask',
        params,
    };
}

export function buildCancelTaskBody(taskId) {
    return {
        jsonrpc: '2.0',
        id: createProtocolId('rpc'),
        method: 'CancelTask',
        params: { id: taskId },
    };
}

export function a2aRequestHeaders(headers = {}, { stream = false } = {}) {
    return {
        'Content-Type': 'application/json',
        Accept: stream ? 'text/event-stream' : 'application/json',
        'A2A-Version': A2A_PROTOCOL_VERSION,
        'A2A-Extensions': A2UI_EXTENSION_URI,
        ...headers,
    };
}

export function buildA2aFileParts(files) {
    const list = Array.isArray(files) ? files : [];
    return list.map((file) => {
        if (!file || typeof file !== 'object') {
            throw new Error('flow-ui: buildA2aFileParts entry must be an object');
        }
        if (typeof file.file_id === 'string' && file.file_id.trim() !== '') {
            return {
                file: {
                    name: file.original_name || file.filename || file.file_id,
                    mimeType: file.content_type || 'application/octet-stream',
                    uri: file.url || undefined,
                },
                metadata: { file_id: file.file_id },
            };
        }
        if (typeof file.url === 'string' && file.url.trim() !== '') {
            return {
                file: {
                    name: file.original_name || file.filename || 'file',
                    mimeType: file.content_type || 'application/octet-stream',
                    uri: file.url,
                },
            };
        }
        throw new Error('flow-ui: buildA2aFileParts requires file_id or url');
    });
}

/**
 * Plain-text SendStreamingMessage body for hosts that are not Flow UI submit.
 */
export function buildA2aSendStreamingMessageBody(input) {
    if (!input || typeof input !== 'object') {
        throw new Error('flow-ui: buildA2aSendStreamingMessageBody input required');
    }
    const a2aMessage = {
        messageId: createProtocolId('message'),
        role: 'ROLE_USER',
        parts: [
            { text: typeof input.message === 'string' ? input.message : '' },
            ...buildA2aFileParts(input.files),
        ],
    };
    if (typeof input.contextId === 'string' && input.contextId.length > 0) {
        a2aMessage.contextId = input.contextId;
    }
    const body = {
        jsonrpc: '2.0',
        id: createProtocolId('rpc'),
        method: 'SendStreamingMessage',
        params: { message: a2aMessage },
    };
    const metadata =
        input.metadata && typeof input.metadata === 'object' ? { ...input.metadata } : {};
    const branchId =
        input.branchId != null && String(input.branchId).trim() !== ''
            ? normalizeFlowUIBranchId(input.branchId)
            : null;
    if (branchId && branchId !== 'default') {
        metadata.branch = branchId;
    }
    if (Object.keys(metadata).length > 0) {
        body.params.metadata = metadata;
    }
    return body;
}

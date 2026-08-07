import { A2UI_EXTENSION_URI, A2UI_MEDIA_TYPE } from './constants.js';
import { cloneSerializable } from '../utils/clone.js';

const RESERVED = new Set([
    'id', 'component', 'children', 'child', 'kind', 'layout', 'placement',
    'action', 'actionSlot', 'actions', 'visibility', 'checks', 'provenance',
]);

function clone(value) {
    return cloneSerializable(value);
}

function snake(value) {
    if (Array.isArray(value)) return value.map(snake);
    if (!value || typeof value !== 'object') return value;
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [
        key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
        snake(item),
    ]));
}

function decodeAction(payload) {
    if (payload?.event) return { kind: 'event', name: payload.event.name, context: clone(payload.event.context || {}) };
    if (payload?.functionCall) {
        return { kind: 'local', name: payload.functionCall.call, context: clone(payload.functionCall.args || {}) };
    }
    return null;
}

export function decodeA2UIComponent(input) {
    if (!input || typeof input !== 'object' || typeof input.id !== 'string') {
        throw new Error('flow-ui: invalid A2UI component');
    }
    const properties = {};
    const bindings = {};
    for (const [key, value] of Object.entries(input)) {
        if (RESERVED.has(key)) continue;
        if (value && typeof value === 'object' && Object.keys(value).length === 1 && typeof value.path === 'string') {
            bindings[key] = value.path;
        } else properties[key] = clone(value);
    }
    const actions = {};
    if (input.action) {
        const action = decodeAction(input.action);
        if (action) actions[input.actionSlot || 'press'] = action;
    }
    for (const [slot, payload] of Object.entries(input.actions || {})) {
        const action = decodeAction(payload);
        if (action) actions[slot] = action;
    }
    return {
        component_id: input.id,
        type: input.component,
        kind: input.kind || ((input.children || input.child) ? 'container' : 'leaf'),
        properties,
        children: clone(input.children || (input.child ? [input.child] : [])),
        container_layout: input.layout ? snake(input.layout) : null,
        placement: input.placement ? snake(input.placement) : { base: {}, overrides: {} },
        bindings,
        actions,
        visibility: clone(input.visibility || null),
        checks: clone(input.checks || []),
        provenance: input.provenance ? snake(input.provenance) : null,
    };
}

function pointerParts(path) {
    if (path === '/' || path === '') return [];
    if (!path.startsWith('/')) throw new Error(`flow-ui: invalid JSON pointer ${path}`);
    return path.slice(1).split('/').map((segment) => segment.replace(/~1/g, '/').replace(/~0/g, '~'));
}

function setPointer(root, path, value, remove = false) {
    const parts = pointerParts(path);
    if (parts.length === 0) return remove ? {} : clone(value);
    const result = clone(root || {});
    let target = result;
    for (let index = 0; index < parts.length - 1; index += 1) {
        const key = parts[index];
        if (!target[key] || typeof target[key] !== 'object') target[key] = {};
        target = target[key];
    }
    const leaf = parts[parts.length - 1];
    if (remove) delete target[leaf];
    else target[leaf] = clone(value);
    return result;
}

export function isA2UIArtifact(artifact) {
    if (!artifact || typeof artifact !== 'object') return false;
    if (Array.isArray(artifact.extensions) && artifact.extensions.includes(A2UI_EXTENSION_URI)) return true;
    return (artifact.parts || []).some((part) => (
        String(part?.mediaType || part?.metadata?.mimeType || '').toLowerCase() === A2UI_MEDIA_TYPE
    ));
}

export function flowUIDocumentFromGenericArtifact(artifact) {
    for (const part of artifact?.parts || []) {
        const document = part?.data?.flowUi;
        if (document && typeof document === 'object') return clone(document);
    }
    return null;
}

function documentMetadata(artifact) {
    const meta = artifact?.metadata?.platformUi;
    if (!meta || typeof meta !== 'object') throw new Error('flow-ui: A2UI artifact metadata is missing');
    return meta;
}

export function applyA2UIArtifact(current, artifact) {
    const generic = flowUIDocumentFromGenericArtifact(artifact);
    if (generic) return generic;
    if (!isA2UIArtifact(artifact)) return current;
    const metadata = documentMetadata(artifact);
    if (typeof metadata.documentId !== 'string' || !metadata.documentId) {
        throw new Error('flow-ui: A2UI artifact metadata.documentId is required');
    }
    if (!Number.isFinite(Number(metadata.revision)) || Number(metadata.revision) < 1) {
        throw new Error('flow-ui: A2UI artifact metadata.revision must be >= 1');
    }
    if (typeof metadata.templateVersion !== 'string' || !metadata.templateVersion) {
        throw new Error('flow-ui: A2UI artifact metadata.templateVersion is required');
    }
    if (typeof metadata.catalogId !== 'string' || !metadata.catalogId) {
        throw new Error('flow-ui: A2UI artifact metadata.catalogId is required');
    }
    if (typeof metadata.activePageId !== 'string' || !metadata.activePageId) {
        throw new Error('flow-ui: A2UI artifact metadata.activePageId is required');
    }
    let document = current && current.document_id === metadata.documentId
        ? clone(current)
        : {
            schema_version: Number(metadata.schemaVersion ?? 1),
            document_id: metadata.documentId,
            revision: Number(metadata.revision),
            template_version: metadata.templateVersion,
            catalog_id: metadata.catalogId,
            active_page_id: metadata.activePageId,
            session_view_state: clone(metadata.sessionViewState ?? {}),
            pages: clone(metadata.pages ?? {}),
            surfaces: {},
            global_data_model: { content: {}, values: {}, system: {} },
            policy: clone(metadata.policy ?? {}),
        };
    for (const part of artifact.parts || []) {
        if (!Array.isArray(part?.data)) continue;
        for (const message of part.data) {
            if (!message || typeof message !== 'object') continue;
            if (message.createSurface) {
                const payload = message.createSurface;
                document.surfaces[payload.surfaceId] = {
                    surface_id: payload.surfaceId,
                    catalog_id: payload.catalogId,
                    root_component_id: 'root',
                    components: {},
                    data_model: { content: {}, values: {}, system: {} },
                    owner: 'platform',
                    send_data_model: payload.sendDataModel !== false,
                };
            } else if (message.updateComponents) {
                const payload = message.updateComponents;
                const surface = document.surfaces[payload.surfaceId];
                if (!surface) throw new Error(`flow-ui: unknown surface ${payload.surfaceId}`);
                for (const component of payload.components || []) {
                    const decoded = decodeA2UIComponent(component);
                    surface.components[decoded.component_id] = decoded;
                }
            } else if (message.updateDataModel) {
                const payload = message.updateDataModel;
                const surface = document.surfaces[payload.surfaceId];
                if (!surface) throw new Error(`flow-ui: unknown surface ${payload.surfaceId}`);
                surface.data_model = setPointer(
                    surface.data_model,
                    payload.path,
                    payload.value,
                    !Object.prototype.hasOwnProperty.call(payload, 'value'),
                );
            } else if (message.deleteSurface) {
                delete document.surfaces[message.deleteSurface.surfaceId];
            }
        }
    }
    document.revision = Number(metadata.revision);
    document.active_page_id = metadata.activePageId;
    if (metadata.pages && typeof metadata.pages === 'object') {
        document.pages = clone(metadata.pages);
    }
    if (metadata.sessionViewState && typeof metadata.sessionViewState === 'object') {
        document.session_view_state = clone(metadata.sessionViewState);
    }
    if (metadata.policy && typeof metadata.policy === 'object') {
        document.policy = clone(metadata.policy);
    }
    return document;
}

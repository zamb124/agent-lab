/**
 * HITL operator_handoff transport for platform-flow-ui.
 * History: REST snapshot. Live: A2A SubscribeToTask. Send: HITL ask or worktracker complete.
 */

import { buildWorkItemFileCreateSpecJson } from '../../utils/file-create-spec.js';
import { runA2aTaskLiveTail } from './a2a-task-live-tail.js';
import {
    isPlatformFileRef,
    uploadPlatformFile,
} from '../../utils/platform-file-upload.js';

function flowsRoot(baseUrl) {
    if (typeof baseUrl !== 'string' || baseUrl.trim() === '') {
        throw new Error('FlowUIHitlTransport: baseUrl is required');
    }
    return baseUrl.trim().replace(/\/$/, '');
}

function randomIdempotencyKey() {
    // crypto.randomUUID есть только в secure context (HTTPS / localhost).
    // Локальный стенд и E2E ходят по HTTP company-host — UUID собираем из getRandomValues.
    if (!globalThis.crypto || typeof globalThis.crypto.getRandomValues !== 'function') {
        throw new Error('hitl-transport: crypto.getRandomValues is required');
    }
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function isBrowserFile(file) {
    return typeof File !== 'undefined' && file instanceof File;
}

export class FlowUIHitlTransport {
    /**
     * @param {{
     *   workItemId: string,
     *   conversation: {
     *     session_id: string,
     *     context_id: string,
     *     flow_id: string,
     *     branch_id?: string,
     *     a2a_task_id: string,
     *   },
     *   mode?: 'takeover'|'single_reply',
     *   baseUrl?: string,
     *   credentials?: RequestCredentials,
     *   getHeaders?: () => Promise<Record<string, string>>|Record<string, string>,
     *   fetchImpl?: typeof fetch,
     * }} options
     */
    constructor(options) {
        if (!options || typeof options !== 'object') {
            throw new Error('FlowUIHitlTransport: options required');
        }
        if (typeof options.workItemId !== 'string' || options.workItemId.trim() === '') {
            throw new Error('FlowUIHitlTransport: workItemId required');
        }
        const conv = options.conversation;
        if (!conv || typeof conv !== 'object') {
            throw new Error('FlowUIHitlTransport: conversation required');
        }
        for (const key of ['session_id', 'context_id', 'flow_id', 'a2a_task_id']) {
            if (typeof conv[key] !== 'string' || conv[key].trim() === '') {
                throw new Error(`FlowUIHitlTransport: conversation.${key} required`);
            }
        }
        const mode = typeof options.mode === 'string' && options.mode.length > 0
            ? options.mode
            : 'takeover';
        if (mode !== 'takeover' && mode !== 'single_reply') {
            throw new Error(`FlowUIHitlTransport: unsupported mode ${JSON.stringify(mode)}`);
        }
        this._workItemId = options.workItemId.trim();
        this._conversation = conv;
        this._mode = mode;
        this._a2aTaskId = conv.a2a_task_id.trim();
        this._root = flowsRoot(options.baseUrl);
        this._credentials = options.credentials || 'include';
        this._getHeaders = typeof options.getHeaders === 'function'
            ? options.getHeaders
            : async () => ({});
        this._fetch = typeof options.fetchImpl === 'function'
            ? options.fetchImpl
            : globalThis.fetch.bind(globalThis);
        /** @type {import('./flow-ui-controller.js').FlowUIController|null} */
        this._controller = null;
        /** @type {AbortController|null} */
        this._liveAbort = null;
        this._seenMessageIds = new Set();
    }

    attach(controller) {
        if (!controller || typeof controller.applyA2AFrame !== 'function') {
            throw new Error('FlowUIHitlTransport.attach: FlowUIController required');
        }
        this._controller = controller;
        controller.hitlTransport = this;
        if (this._conversation.context_id) {
            controller.contextId = this._conversation.context_id;
        }
    }

    async loadHistory() {
        if (this._controller === null) {
            throw new Error('FlowUIHitlTransport.loadHistory: not attached');
        }
        const headers = await this._getHeaders();
        const url = `${this._root}/api/v1/hitl/${encodeURIComponent(this._workItemId)}/conversation`;
        const response = await this._fetch(url, {
            method: 'GET',
            headers: { Accept: 'application/json', ...headers },
            credentials: this._credentials,
        });
        if (!response.ok) {
            throw new Error(`hitl-transport: snapshot HTTP ${response.status}`);
        }
        const snapshot = await response.json();
        const turns = Array.isArray(snapshot.turns) ? snapshot.turns : [];
        for (const turn of turns) {
            if (turn && typeof turn === 'object' && typeof turn.message_id === 'string') {
                this._seenMessageIds.add(turn.message_id);
            }
        }
        this._startLiveTail();
        return snapshot;
    }

    _startLiveTail() {
        this._stopLiveTail();
        this._liveAbort = new AbortController();
        void this._runLiveTail(this._liveAbort);
    }

    _stopLiveTail() {
        if (this._liveAbort !== null) {
            this._liveAbort.abort();
            this._liveAbort = null;
        }
    }

    /**
     * @param {AbortController} abort
     */
    async _runLiveTail(abort) {
        await runA2aTaskLiveTail({
            target: {
                baseUrl: this._root,
                flowId: this._conversation.flow_id,
            },
            taskId: this._a2aTaskId,
            headersFn: () => this._getHeaders(),
            credentials: this._credentials,
            signal: abort.signal,
            onFrame: (frame) => {
                if (abort.signal.aborted || this._controller === null) return;
                this._controller.applyA2AFrame(frame);
            },
        });
        if (this._liveAbort === abort) this._liveAbort = null;
    }

    /**
     * @param {unknown[]} files
     */
    async _resolveFileRefs(files) {
        const list = Array.isArray(files) ? files : [];
        const refs = [];
        for (const file of list) {
            if (isPlatformFileRef(file)) {
                refs.push({
                    file_id: file.file_id,
                    original_name: file.original_name,
                    content_type: file.content_type,
                    file_size: file.file_size,
                    url: typeof file.url === 'string' ? file.url : null,
                });
                continue;
            }
            if (!isBrowserFile(file)) {
                throw new Error('hitl-transport: files must be File or FileRef');
            }
            refs.push(await this._uploadBrowserFile(file));
        }
        return refs;
    }

    async _uploadBrowserFile(file) {
        const headers = await this._getHeaders();
        const result = await uploadPlatformFile({
            file,
            spec: buildWorkItemFileCreateSpecJson({ workItemId: this._workItemId }),
            credentials: this._credentials,
            headers,
            fetchImpl: this._fetch,
        });
        if (!result || typeof result !== 'object' || typeof result.file_id !== 'string') {
            throw new Error('hitl-transport: file upload result.file_id required');
        }
        return {
            file_id: result.file_id,
            original_name: typeof result.original_name === 'string' ? result.original_name : file.name,
            content_type: typeof result.content_type === 'string'
                ? result.content_type
                : (file.type || 'application/octet-stream'),
            file_size: typeof result.file_size === 'number' ? result.file_size : file.size,
            url: typeof result.url === 'string' ? result.url : null,
        };
    }

    /**
     * @param {{ message?: string, files?: unknown[] }} input
     */
    async send(input) {
        const message = input && typeof input.message === 'string' ? input.message.trim() : '';
        const fileRefs = await this._resolveFileRefs(
            input && Array.isArray(input.files) ? input.files : [],
        );
        if (message === '' && fileRefs.length === 0) {
            throw new Error('hitl-transport: send requires text or files');
        }
        if (this._mode === 'single_reply') {
            await this._completeWithReply(message, fileRefs);
            return;
        }
        await this._sendAsk(message, fileRefs);
    }

    async _sendAsk(text, fileRefs) {
        const headers = await this._getHeaders();
        const url = `${this._root}/api/v1/hitl/${encodeURIComponent(this._workItemId)}/conversation/messages`;
        const response = await this._fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...headers },
            credentials: this._credentials,
            body: JSON.stringify({
                text,
                idempotency_key: randomIdempotencyKey(),
                file_ids: fileRefs.map((ref) => ref.file_id),
            }),
        });
        if (!response.ok) {
            throw new Error(`hitl-transport: send HTTP ${response.status}`);
        }
        const turn = await response.json();
        if (turn && typeof turn === 'object' && typeof turn.message_id === 'string') {
            this._seenMessageIds.add(turn.message_id);
        }
        return turn;
    }

    async _completeWithReply(text, fileRefs) {
        const headers = await this._getHeaders();
        const url = `/worktracker/api/v1/work-items/${encodeURIComponent(this._workItemId)}/complete`;
        const response = await this._fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...headers },
            credentials: this._credentials,
            body: JSON.stringify({
                resolution_text: text,
                resolution_files: fileRefs,
            }),
        });
        if (!response.ok) {
            throw new Error(`hitl-transport: complete HTTP ${response.status}`);
        }
        return response.json();
    }

    async cancel() {
        /* Live tail only; send cancellation is separate CancelTask on the controller. */
    }

    dispose() {
        this._stopLiveTail();
        if (this._controller && this._controller.hitlTransport === this) {
            this._controller.hitlTransport = null;
        }
        this._controller = null;
    }
}

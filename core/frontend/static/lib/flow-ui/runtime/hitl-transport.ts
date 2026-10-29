/**
 * Транспорт оператора (profile ``operator_handoff``): история и live-кадры — A2A Task
 * пользователя через ``FlowUIClient`` (ListTasks + SubscribeToTask), отправка — HITL REST
 * (``takeover``) либо завершение WorkItem ответом (``single_reply``).
 */

import { buildWorkItemFileCreateSpecJson } from '../../utils/file-create-spec.js';
import { isPlatformFileRef, uploadPlatformFile } from '../../utils/platform-file-upload.js';
import { randomUuid } from '../../a2a/a2a-codec.js';
import { flowUIText } from '../utils/text.js';
import type { FlowUiBlock, FlowUiRecord } from './flow-ui-store.js';
import { templatePaths } from './templating.js';
import type { FlowUIClient } from './flow-ui-client.js';

type FlowUiLocale = 'ru' | 'en';

export interface HitlConversation {
    session_id: string;
    context_id: string;
    flow_id: string;
    branch_id?: string;
    a2a_task_id: string;
}

export interface FlowUIHitlTransportOptions {
    workItemId: string;
    conversation: HitlConversation;
    mode?: string;
    baseUrl: string;
    credentials?: RequestCredentials;
    getHeaders?: () => Promise<Record<string, string>> | Record<string, string>;
    fetchImpl?: typeof fetch;
}

function isBrowserFile(file: unknown): file is File {
    return typeof File !== 'undefined' && file instanceof File;
}

function fieldValueText(value: unknown, locale: FlowUiLocale): string {
    if (Array.isArray(value)) return value.map((item) => fieldValueText(item, locale)).join(', ');
    if (typeof value === 'boolean') return flowUIText(locale, value ? 'value_yes' : 'value_no');
    if (isPlatformFileRef(value)) return value.original_name;
    if (value === null || value === undefined) return '';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
}

/**
 * Ход оператора из ui-action. HITL REST принимает только текст и файлы, поэтому значения
 * полей идут строками «подпись: значение» в порядке страницы, файлы ``file_upload`` —
 * вложениями, а действие без полей уходит своим именем.
 *
 * @param {{ name: string }} action
 * @param {Record<string, unknown>} fields
 * @param {object[]} inputBlocks блоки активной страницы, пишущие поле state
 * @param {'ru' | 'en'} locale
 * @returns {{ text: string, files: object[] }}
 */
export function operatorTurnFromAction(
    action: { name?: unknown } | null | undefined,
    fields: FlowUiRecord,
    inputBlocks: FlowUiBlock[],
    locale: FlowUiLocale,
): { text: string; files: unknown[] } {
    if (!action || typeof action.name !== 'string' || action.name === '') {
        throw new Error('hitl-transport: operator action requires name');
    }
    const lines: string[] = [];
    const files: unknown[] = [];
    for (const block of inputBlocks) {
        const field = block.field as string;
        if (!Object.prototype.hasOwnProperty.call(fields, field)) continue;
        const value = fields[field];
        if (block.type === 'file_upload') {
            if (Array.isArray(value)) files.push(...value);
            continue;
        }
        const label = typeof block.label === 'string' && block.label !== '' && templatePaths(block.label).length === 0
            ? block.label
            : field;
        lines.push(`${label}: ${fieldValueText(value, locale)}`);
    }
    return { text: lines.length > 0 ? lines.join('\n') : action.name, files };
}

export class FlowUIHitlTransport {
    /**
     * @param {{
     *   workItemId: string,
     *   conversation: { session_id: string, context_id: string, flow_id: string, branch_id?: string, a2a_task_id: string },
     *   mode?: 'takeover' | 'single_reply',
     *   baseUrl: string,
     *   credentials?: RequestCredentials,
     *   getHeaders?: () => Promise<Record<string, string>> | Record<string, string>,
     *   fetchImpl?: typeof fetch,
     * }} options
     */
    workItemId: string;
    conversation: HitlConversation;
    mode: 'takeover' | 'single_reply';
    taskId: string;
    private _root: string;
    private _credentials: RequestCredentials;
    private _getHeaders: () => Promise<Record<string, string>> | Record<string, string>;
    private _fetch: typeof fetch;
    private _client: FlowUIClient | null;

    constructor(options: FlowUIHitlTransportOptions) {
        if (!options || typeof options !== 'object') throw new Error('FlowUIHitlTransport: options required');
        if (typeof options.workItemId !== 'string' || options.workItemId.trim() === '') {
            throw new Error('FlowUIHitlTransport: workItemId required');
        }
        const conversation = options.conversation;
        if (!conversation || typeof conversation !== 'object') {
            throw new Error('FlowUIHitlTransport: conversation required');
        }
        for (const key of ['session_id', 'context_id', 'flow_id', 'a2a_task_id'] as const) {
            if (typeof conversation[key] !== 'string' || conversation[key].trim() === '') {
                throw new Error(`FlowUIHitlTransport: conversation.${key} required`);
            }
        }
        const mode: string = typeof options.mode === 'string' && options.mode !== '' ? options.mode : 'takeover';
        if (mode !== 'takeover' && mode !== 'single_reply') {
            throw new Error(`FlowUIHitlTransport: unsupported mode ${JSON.stringify(mode)}`);
        }
        if (typeof options.baseUrl !== 'string' || options.baseUrl.trim() === '') {
            throw new Error('FlowUIHitlTransport: baseUrl is required');
        }
        this.workItemId = options.workItemId.trim();
        this.conversation = conversation;
        this.mode = mode;
        this.taskId = conversation.a2a_task_id.trim();
        this._root = options.baseUrl.trim().replace(/\/$/, '');
        this._credentials = options.credentials === 'omit' ? 'omit' : 'include';
        this._getHeaders = typeof options.getHeaders === 'function' ? options.getHeaders : async () => ({});
        this._fetch = typeof options.fetchImpl === 'function' ? options.fetchImpl : globalThis.fetch.bind(globalThis);
        this._client = null;
    }

    /** Открывает контекст пользователя в клиенте и держит live tail задачи оператора. */
    async attach(client: FlowUIClient) {
        if (!client || typeof client.open !== 'function') throw new Error('FlowUIHitlTransport.attach: client required');
        this._client = client;
        await client.open({ contextId: this.conversation.context_id });
        client.tail(this.taskId, { untilTerminal: true });
    }

    private async _resolveFileRefs(files: unknown): Promise<FlowUiRecord[]> {
        const refs: FlowUiRecord[] = [];
        for (const file of Array.isArray(files) ? files : []) {
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
            if (!isBrowserFile(file)) throw new Error('hitl-transport: files must be File or FileRef');
            const headers = await this._getHeaders();
            const uploaded = await uploadPlatformFile({
                file,
                spec: buildWorkItemFileCreateSpecJson({ workItemId: this.workItemId }),
                credentials: this._credentials,
                headers,
                fetchImpl: this._fetch,
            });
            if (!uploaded || typeof uploaded.file_id !== 'string') {
                throw new Error('hitl-transport: file upload result.file_id required');
            }
            refs.push({
                file_id: uploaded.file_id,
                original_name: uploaded.original_name,
                content_type: uploaded.content_type,
                file_size: uploaded.file_size,
                url: typeof uploaded.url === 'string' ? uploaded.url : null,
            });
        }
        return refs;
    }

    /** @param {{ text?: string, files?: unknown[] }} input */
    async send(input: { text?: unknown; files?: unknown[] } | null | undefined) {
        const text = input && typeof input.text === 'string' ? input.text.trim() : '';
        const fileRefs = await this._resolveFileRefs(input && Array.isArray(input.files) ? input.files : []);
        if (text === '' && fileRefs.length === 0) throw new Error('hitl-transport: send requires text or files');
        const headers = await this._getHeaders();
        const common = { 'Content-Type': 'application/json', Accept: 'application/json', ...headers };
        if (this.mode === 'single_reply') {
            const response = await this._fetch(
                `/worktracker/api/v1/work-items/${encodeURIComponent(this.workItemId)}/complete`,
                {
                    method: 'POST',
                    headers: common,
                    credentials: this._credentials,
                    body: JSON.stringify({ resolution_text: text, resolution_files: fileRefs }),
                },
            );
            if (!response.ok) throw new Error(`hitl-transport: complete HTTP ${response.status}`);
            return response.json();
        }
        const response = await this._fetch(
            `${this._root}/api/v1/hitl/${encodeURIComponent(this.workItemId)}/conversation/messages`,
            {
                method: 'POST',
                headers: common,
                credentials: this._credentials,
                body: JSON.stringify({
                    text,
                    idempotency_key: randomUuid(),
                    file_ids: fileRefs.map((ref) => ref.file_id),
                }),
            },
        );
        if (!response.ok) throw new Error(`hitl-transport: send HTTP ${response.status}`);
        return response.json();
    }

    dispose() {
        if (this._client !== null) this._client.stopTail();
        this._client = null;
    }
}

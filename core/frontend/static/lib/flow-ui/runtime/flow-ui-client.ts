/**
 * Клиент Flow UI поверх A2A 1.0: interface REST + SendStreamingMessage / ListTasks /
 * SubscribeToTask / CancelTask. Все кадры складываются в ``FlowUIStore``.
 *
 * Подписки: ``on('frame' | 'task' | 'ui' | 'state' | 'error', handler)`` → unsubscribe.
 */

import { isPlainRecord } from '../../events/payload.js';
import {
    a2aEndpointUrl,
    buildCancelTaskBody,
    buildListTasksBody,
    buildSendMessageBody,
    buildSubscribeTaskBody,
    buildUserMessage,
    createProtocolId,
    flowUIShareCollectionUrl,
    interfaceUrl,
    normalizeFlowUIBranchId,
} from '../../a2a/a2a-codec.js';
import {
    consumeA2AStream,
    flowUIIsAbortError,
    isSettledTaskState,
    isTerminalTaskState,
    sendA2ARequest,
    type A2aError,
} from '../../a2a/a2a-stream.js';
import { STATE_ARTIFACT_ID } from '../../a2a/constants.js';
import type { A2aFileSource, A2aUiActionInput } from '../../a2a/a2a-codec.js';
import type { A2aAccumulatedTask } from '../../a2a/a2a-task-accumulator.js';
import type { ApplyFrameResult, FlowUiDocument, FlowUiRecord } from './flow-ui-store.js';
import { FlowUIStore } from './flow-ui-store.js';
import { taskInterrupt } from './operator-handoff-from-task.js';

const EVENT_TYPES = new Set(['frame', 'task', 'ui', 'state', 'error']);

export interface FlowUIClientOptions {
    baseUrl: string;
    flowId?: string;
    embedId?: string;
    branchId?: string | null;
    credentials?: RequestCredentials;
    getHeaders?: () => Promise<Record<string, string>> | Record<string, string>;
    getVariables?: () => Record<string, unknown> | null;
    store?: FlowUIStore;
}

export type FlowUiClientEventType = 'frame' | 'task' | 'ui' | 'state' | 'error';
type FlowUiClientHandler = (detail: unknown) => void;

export interface FlowUiSendInput {
    text?: string;
    files?: A2aFileSource[];
    action?: A2aUiActionInput | null;
    taskId?: string | null;
}

function frameRecord(value: unknown, label: string): FlowUiRecord | undefined {
    if (value === undefined || value === null) return undefined;
    if (!isPlainRecord(value)) {
        throw new Error(`flow-ui: ${label} must be an object`);
    }
    return value;
}

function requireFrame(frame: unknown): FlowUiRecord {
    if (!isPlainRecord(frame)) {
        throw new Error('flow-ui: A2A frame must be an object');
    }
    return frame;
}

function statusState(status: unknown): unknown {
    if (status === undefined || status === null) return undefined;
    if (!isPlainRecord(status)) {
        throw new Error('flow-ui: task status must be an object');
    }
    return status.state;
}

/** ``artifact.artifactId`` кадра artifactUpdate для сравнения со STATE_ARTIFACT_ID. */
function frameArtifactId(frame: FlowUiRecord): unknown {
    const result = frameRecord(frame.result, 'frame.result');
    const update = result === undefined ? undefined : frameRecord(result.artifactUpdate, 'artifactUpdate');
    const artifact = update === undefined ? undefined : frameRecord(update.artifact, 'artifact');
    return artifact === undefined ? undefined : artifact.artifactId;
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
    return new Promise((resolve, reject) => {
        if (signal.aborted) {
            reject(new DOMException('Aborted', 'AbortError'));
            return;
        }
        const timer = setTimeout(resolve, ms);
        signal.addEventListener('abort', () => {
            clearTimeout(timer);
            reject(new DOMException('Aborted', 'AbortError'));
        }, { once: true });
    });
}

export class FlowUIClient {
    /**
     * @param {{
     *   baseUrl: string,
     *   flowId?: string,
     *   embedId?: string,
     *   branchId?: string,
     *   credentials?: RequestCredentials,
     *   getHeaders?: () => Promise<Record<string, string>> | Record<string, string>,
     *   getVariables?: () => Record<string, unknown> | null,
     *   store?: FlowUIStore,
     * }} options
     */
    target: { baseUrl: string; flowId: string; embedId: string; branchId: string };
    endpoint: string;
    credentials: RequestCredentials;
    private _getHeaders: () => Promise<Record<string, string>> | Record<string, string>;
    private _getVariables: () => Record<string, unknown> | null;
    store: FlowUIStore;
    private _listeners: Map<string, Set<FlowUiClientHandler>>;
    private _streamAbort: AbortController | null;
    private _tailAbort: AbortController | null;
    private _tailTaskId: string;
    disposed: boolean;

    constructor(options: FlowUIClientOptions) {
        if (!options || typeof options !== 'object') throw new Error('flow-ui: client options required');
        this.target = {
            baseUrl: options.baseUrl,
            flowId: typeof options.flowId === 'string' ? options.flowId : '',
            embedId: typeof options.embedId === 'string' ? options.embedId : '',
            branchId: normalizeFlowUIBranchId(options.branchId),
        };
        this.endpoint = a2aEndpointUrl(this.target);
        this.credentials = options.credentials === 'omit' ? 'omit' : 'include';
        this._getHeaders = typeof options.getHeaders === 'function' ? options.getHeaders : () => ({});
        this._getVariables = typeof options.getVariables === 'function' ? options.getVariables : () => null;
        this.store = options.store instanceof FlowUIStore ? options.store : new FlowUIStore();
        this._listeners = new Map();
        this._streamAbort = null;
        this._tailAbort = null;
        this._tailTaskId = '';
        this.disposed = false;
    }

    get contextId() {
        return this.store.contextId;
    }

    get streaming() {
        return this._streamAbort !== null;
    }

    on(type: string, handler: FlowUiClientHandler): () => void {
        if (!EVENT_TYPES.has(type)) throw new Error(`flow-ui: unknown client event ${JSON.stringify(type)}`);
        if (typeof handler !== 'function') throw new Error('flow-ui: client handler must be a function');
        if (!this._listeners.has(type)) this._listeners.set(type, new Set());
        this._listeners.get(type)?.add(handler);
        return () => {
            this._listeners.get(type)?.delete(handler);
        };
    }

    private _emit(type: string, detail: unknown) {
        const handlers = this._listeners.get(type);
        if (handlers === undefined) return;
        for (const handler of [...handlers]) handler(detail);
    }

    private async _headers(): Promise<Record<string, string>> {
        const headers = await this._getHeaders();
        if (headers === null || typeof headers !== 'object' || Array.isArray(headers)) {
            throw new Error('flow-ui: getHeaders must resolve to a headers object');
        }
        return headers;
    }

    /**
     * Interface с сервера (viewer, capabilities, look, документ); ``document`` — локальный
     * документ редактора поверх серверного. Существующий ``contextId`` — replay Tasks;
     * без него клиент создаёт новый: A2A принимает contextId от клиента.
     * @param {{ contextId?: string | null, document?: object | null }} [options]
     */
    async open({ contextId = null, document = null }: { contextId?: string | null; document?: FlowUiDocument | null } = {}): Promise<FlowUIStore> {
        const hydrateExisting = typeof contextId === 'string' && contextId !== '';
        this.store.resetContext(hydrateExisting ? contextId : createProtocolId('context'));
        const response = await fetch(interfaceUrl(this.target), {
            method: 'GET',
            headers: { Accept: 'application/json', ...(await this._headers()) },
            credentials: this.credentials,
        });
        if (!response.ok) {
            const error: A2aError = new Error(`flow-ui: interface HTTP ${response.status}`);
            error.status = response.status;
            throw error;
        }
        this.store.setInterface(await response.json());
        if (document !== null) this.store.setDocument(document);
        if (hydrateExisting) await this.hydrate();
        return this.store;
    }

    /** ListTasks по контексту; незавершённый последний Task продолжает стримить через SubscribeToTask. */
    async hydrate() {
        const contextId = this.store.contextId;
        if (contextId === null) throw new Error('flow-ui: hydrate requires contextId');
        let pageToken = '';
        do {
            const frame = await sendA2ARequest({
                url: this.endpoint,
                body: buildListTasksBody({ contextId, pageToken }),
                headers: await this._headers(),
                credentials: this.credentials,
            });
            const result = frameRecord(frame.result, 'ListTasks result');
            if (result === undefined || !Array.isArray(result.tasks)) {
                throw new Error('flow-ui: ListTasks result.tasks must be an array');
            }
            for (const task of result.tasks) {
                if (!isPlainRecord(task)) {
                    throw new Error('flow-ui: ListTasks task must be an object');
                }
                this.applyFrame({ result: { task } });
            }
            const nextPageToken = result.nextPageToken;
            if (nextPageToken === undefined || nextPageToken === null || nextPageToken === '') {
                pageToken = '';
            } else if (typeof nextPageToken !== 'string') {
                throw new Error('flow-ui: ListTasks nextPageToken must be a string');
            } else {
                pageToken = nextPageToken;
            }
        } while (pageToken !== '');
        const last = this.store.orderedTasks().at(-1);
        if (last) {
            this.store.activeTaskId = last.id;
            this._tailIfOpen(last);
        }
        this.store.emitChange();
    }

    /** Незавершённый Task или Task, ждущий оператора/OAuth/handoff, дочитывается после закрытия стрима. */
    private _tailIfOpen(task: A2aAccumulatedTask) {
        const state = statusState(task.status);
        const interrupt = taskInterrupt(task);
        if (interrupt !== null && interrupt.continues) {
            if (!isTerminalTaskState(state)) this.tail(task.id, { untilTerminal: true });
            return;
        }
        if (!isSettledTaskState(state)) this.tail(task.id);
    }

    /** Кадр A2A из любого источника (stream, tail, voice bridge). */
    applyFrame(frame: FlowUiRecord): ApplyFrameResult | null {
        if (this.disposed) return null;
        const applied = this.store.applyFrame(frame);
        this._emit('frame', frame);
        if (applied.frameKind === 'artifactUpdate' && frameArtifactId(frame) === STATE_ARTIFACT_ID) {
            this._emit('state', this.store.state);
        }
        for (const event of applied.uiEvents) this._emit('ui', event);
        if (applied.changedTaskId) {
            this.store.activeTaskId = applied.changedTaskId;
            this._emit('task', this.store.task(applied.changedTaskId));
        }
        return applied;
    }

    /**
     * Ход пользователя: текст с файлами либо действие блока.
     * @param {{ text?: string, files?: object[], action?: object | null, taskId?: string | null }} input
     */
    async send({ text = '', files = [], action = null, taskId = null }: FlowUiSendInput = {}): Promise<A2aAccumulatedTask | null> {
        if (this._streamAbort !== null) throw new Error('flow-ui: a turn is already streaming');
        const message = buildUserMessage({ contextId: this.store.contextId, taskId, text, files, action });
        const body = buildSendMessageBody(message, {
            streaming: true,
            branchId: this.target.branchId,
            variables: this._getVariables(),
        });
        const abort = new AbortController();
        this._streamAbort = abort;
        this.store.setStreaming(true);
        this.stopTail();
        this.store.setPending({ text, files, action, messageId: message.messageId });
        const fields = action && isPlainRecord(action.fields) ? Object.keys(action.fields) : [];
        let editsCleared = fields.length === 0;
        try {
            await consumeA2AStream(
                { url: this.endpoint, body, headers: await this._headers(), credentials: this.credentials, signal: abort.signal },
                (frame: unknown) => {
                    if (abort.signal.aborted) return;
                    const record = requireFrame(frame);
                    const applied = this.applyFrame(record);
                    if (!editsCleared && applied?.frameKind === 'artifactUpdate'
                        && frameArtifactId(record) === STATE_ARTIFACT_ID) {
                        editsCleared = true;
                        this.store.clearEdits(fields);
                    }
                },
            );
        } catch (error) {
            if (!flowUIIsAbortError(error)) {
                this.store.setPending(null);
                this.store.setError(error);
                this._emit('error', error);
                throw error;
            }
        } finally {
            if (this._streamAbort === abort) {
                this._streamAbort = null;
                this.store.setStreaming(false);
            }
            if (this.store.pending !== null) this.store.setPending(null);
        }
        const task = this.store.task(this.store.activeTaskId);
        if (task) this._tailIfOpen(task);
        return task;
    }

    /**
     * SubscribeToTask с переподключением. По умолчанию — до settled-состояния Task;
     * ``untilTerminal`` — пока Task ждёт оператора (INPUT_REQUIRED), кадры продолжают идти.
     */
    tail(taskId: string, { untilTerminal = false }: { untilTerminal?: boolean } = {}) {
        if (this._tailTaskId === taskId && this._tailAbort !== null) return;
        this.stopTail();
        const abort = new AbortController();
        this._tailAbort = abort;
        this._tailTaskId = taskId;
        void this._runTail(taskId, abort, untilTerminal);
    }

    private async _runTail(taskId: string, abort: AbortController, untilTerminal: boolean) {
        const settled = (): boolean => {
            const status = this.store.task(taskId)?.status;
            const state = statusState(status);
            return untilTerminal ? isTerminalTaskState(state) : isSettledTaskState(state);
        };
        while (!abort.signal.aborted && !settled()) {
            try {
                await consumeA2AStream(
                    {
                        url: this.endpoint,
                        body: buildSubscribeTaskBody(taskId),
                        headers: await this._headers(),
                        credentials: this.credentials,
                        signal: abort.signal,
                    },
                    (frame: unknown) => {
                        if (!abort.signal.aborted) this.applyFrame(requireFrame(frame));
                    },
                );
            } catch (error) {
                if (flowUIIsAbortError(error)) break;
                this._emit('error', error);
            }
            // Пауза нужна только перед переподключением: сервер закрыл стрим, а Task ещё открыт
            if (abort.signal.aborted || settled()) break;
            try {
                await sleep(800, abort.signal);
            } catch (error) {
                if (flowUIIsAbortError(error)) break;
                throw error;
            }
        }
        if (this._tailAbort === abort) {
            this._tailAbort = null;
            this._tailTaskId = '';
        }
    }

    stopTail() {
        if (this._tailAbort !== null) this._tailAbort.abort();
        this._tailAbort = null;
        this._tailTaskId = '';
    }

    async cancel() {
        if (!this.store.taskRunning) throw new Error('flow-ui: no running task to cancel');
        const taskId = this.store.activeTaskId;
        if (taskId === null || taskId.length === 0) {
            throw new Error('flow-ui: running task has no id');
        }
        const frame = await sendA2ARequest({
            url: this.endpoint,
            body: buildCancelTaskBody(taskId),
            headers: await this._headers(),
            credentials: this.credentials,
        });
        this.applyFrame(frame);
    }

    /** Новый contextId для того же интерфейса; все Tasks и локальные правки сбрасываются. */
    newContext() {
        this.abortStream();
        this.stopTail();
        this.store.resetContext(createProtocolId('context'));
        return this.store.contextId;
    }

    abortStream() {
        if (this._streamAbort === null) return;
        this._streamAbort.abort();
        this._streamAbort = null;
        this.store.setStreaming(false);
    }

    async createShare({ permission = 'viewer', redactedPaths = [], expiresInSeconds = 86_400 }: {
        permission?: string;
        redactedPaths?: string[];
        expiresInSeconds?: number;
    } = {}) {
        if (this.store.contextId === null) throw new Error('flow-ui: share requires an open context');
        if (this.target.flowId === '') throw new Error('flow-ui: share requires flowId');
        const response = await fetch(flowUIShareCollectionUrl(this.target), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(await this._headers()) },
            credentials: this.credentials,
            body: JSON.stringify({
                flow_id: this.target.flowId,
                context_id: this.store.contextId,
                permission,
                redacted_paths: redactedPaths,
                expires_in_seconds: expiresInSeconds,
            }),
        });
        if (!response.ok) throw new Error(`flow-ui: share create HTTP ${response.status}`);
        return response.json();
    }

    async revokeShare(grantId: unknown) {
        if (typeof grantId !== 'string' || grantId === '') throw new Error('flow-ui: grant_id is required');
        const response = await fetch(`${flowUIShareCollectionUrl(this.target)}/${encodeURIComponent(grantId)}`, {
            method: 'DELETE',
            headers: { ...(await this._headers()) },
            credentials: this.credentials,
        });
        if (!response.ok && response.status !== 404) throw new Error(`flow-ui: share revoke HTTP ${response.status}`);
    }

    dispose() {
        this.disposed = true;
        this.abortStream();
        this.stopTail();
        this._listeners.clear();
    }
}

/**
 * Единое состояние клиента Flow UI.
 *
 * - ``interface`` — ответ ``GET .../interface`` (document, viewer, look, capabilities, flow_identity);
 * - ``state`` — проекция ExecutionState: свёртка артефактов ``state`` всех Tasks контекста
 *   (snapshot ``application/json`` + патчи RFC 6902) в порядке их появления;
 * - ``edits`` — локальные значения полей ввода до отправки действия;
 * - ``slots`` — последний рендер агента в именованные ``slot``-блоки (артефакт ``ui``);
 * - ``tasks`` — аккумулятор A2A Tasks (история диалога, статусы, артефакты);
 * - ``pageId`` — активная страница документа.
 */

import { recordField } from '../../events/payload.js';
import { isSettledTaskState } from '../protocol/a2a-stream.js';
import { applyA2AFrame, createA2ATaskAccumulator } from '../protocol/a2a-task-accumulator.js';
import { CONVERSATION_SLOT_ID, INPUT_BLOCK_TYPES, STATE_ARTIFACT_ID, UI_ARTIFACT_ID } from '../protocol/constants.js';
import { applyJsonPatch, decodePart } from '../protocol/parts.js';
import { valueAtPath } from './templating.js';

export type FlowUiRecord = Record<string, unknown>;

export interface FlowUiBlock extends FlowUiRecord {
    type: string;
    field?: unknown;
    required?: boolean;
    blocks?: unknown;
    columns?: unknown;
    tabs?: unknown;
    settings?: unknown;
}

export interface FlowUiPage extends FlowUiRecord {
    page_id: string;
    blocks: FlowUiBlock[];
}

export interface FlowUiDocument extends FlowUiRecord {
    pages: FlowUiPage[];
    start_page_id: string;
}

export interface FlowUiInterfaceResponse extends FlowUiRecord {
    document: FlowUiDocument;
}

export interface FlowUiUiEvent extends FlowUiRecord {
    kind: string;
    slot_id?: unknown;
    page_id?: unknown;
    blocks?: unknown;
}

export interface CollectFieldsResult {
    fields: Record<string, unknown>;
    missing: Set<string>;
}

/** Хост ``<platform-flow-ui>``, видимый рендерерам блоков через ``ctx.host``. */
export interface FlowUiHostLike {
    voiceSessionActive: boolean;
    voiceSessionReady(): boolean;
    toggleVoiceSession(): void;
    openBrowserPreview(options: Record<string, unknown>): void;
}

/** Контекст рендера блоков (см. ``blocks/registry.js``); расширяет ``TemplateContext``. */
export interface FlowUiRenderContext {
    editing: boolean;
    state: FlowUiRecord;
    locale: string;
    readonly: boolean;
    pending: boolean;
    platformUiOrigin: string;
    theme?: unknown;
    selectedBlockId?: string | null;
    flowIdentity?: FlowUiRecord | null;
    slots: Record<string, unknown>;
    fieldErrors: Set<string>;
    uploading: Set<string>;
    store: FlowUIStore;
    host: FlowUiHostLike;
    fieldValue(field: unknown): unknown;
    onFieldChange(field: unknown, value: unknown): void;
    onAction(block: FlowUiBlock, action: unknown): void;
    onNavigate(pageId: unknown): void;
    onOpenUrl(url: string): void;
    onPrompt(prompt: string): void;
    onFilesSelected(block: FlowUiBlock, files: unknown): void;
    onHtmlBridgeEvent?: unknown;
    renderBlocks?(blocks: unknown): unknown;
    requestUpdate(): void;
}

export type FlowUiBlockRenderer = (block: FlowUiBlock, ctx: FlowUiRenderContext) => unknown;

export interface ApplyFrameResult {
    accumulator: ReturnType<typeof createA2ATaskAccumulator>;
    changedTaskId: string | null;
    frameKind: string | null;
    message?: FlowUiRecord;
    uiEvents: FlowUiUiEvent[];
}

function isObject(value: unknown): value is FlowUiRecord {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function isBlock(value: unknown): value is FlowUiBlock {
    return isObject(value) && typeof value.type === 'string';
}

function isUiEvent(value: Record<string, unknown>): value is FlowUiUiEvent {
    return typeof value.kind === 'string';
}

/** ``html`` с ``field`` пишет поле через ``flowUi.setValue`` наравне с блоками ввода. */
function writesField(block: FlowUiBlock): boolean {
    return INPUT_BLOCK_TYPES.has(block.type) || (block.type === 'html' && block.field !== null && block.field !== undefined);
}

function isEmptyFieldValue(value: unknown): boolean {
    return value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0);
}

export class FlowUIStore {
    interface: FlowUiInterfaceResponse | null;
    document: FlowUiDocument | null;
    pageId: string | null;
    state: FlowUiRecord;
    edits: Record<string, unknown>;
    fieldErrors: Set<string>;
    uploading: Set<string>;
    blockLocal: Map<string, FlowUiRecord>;
    slots: Record<string, unknown>;
    tasks: ReturnType<typeof createA2ATaskAccumulator>;
    contextId: string | null;
    activeTaskId: string | null;
    pending: FlowUiRecord | null;
    streaming: boolean;
    error: unknown;
    private _listeners: Set<(store: FlowUIStore) => void>;

    constructor() {
        this.interface = null;
        this.document = null;
        this.pageId = null;
        this.state = {};
        this.edits = {};
        this.fieldErrors = new Set();
        this.uploading = new Set();
        this.blockLocal = new Map();
        this.slots = {};
        this.tasks = createA2ATaskAccumulator();
        this.contextId = null;
        this.activeTaskId = null;
        this.pending = null;
        this.streaming = false;
        this.error = null;
        this._listeners = new Set();
    }

    subscribe(listener: (store: FlowUIStore) => void): () => boolean {
        if (typeof listener !== 'function') throw new Error('flow-ui: store listener must be a function');
        this._listeners.add(listener);
        return () => this._listeners.delete(listener);
    }

    emitChange(): void {
        for (const listener of [...this._listeners]) listener(this);
    }

    setInterface(interfaceResponse: FlowUiInterfaceResponse): void {
        if (!isObject(interfaceResponse) || !isObject(interfaceResponse.document)) {
            throw new Error('flow-ui: interface response requires document');
        }
        this.interface = interfaceResponse;
        this.setDocument(interfaceResponse.document);
    }

    /** Локальный документ (редактор/предпросмотр) поверх серверного ответа. */
    setDocument(document: FlowUiDocument): void {
        if (!isObject(document) || !Array.isArray(document.pages) || document.pages.length === 0) {
            throw new Error('flow-ui: document requires pages');
        }
        this.document = document;
        if (this.pageId === null || !this.page(this.pageId)) {
            if (!this.page(document.start_page_id)) {
                throw new Error(`flow-ui: document start_page_id ${JSON.stringify(document.start_page_id)} is not a page`);
            }
            this.pageId = document.start_page_id;
        }
        this.emitChange();
    }

    page(pageId: string | null): FlowUiPage | null {
        if (!this.document) return null;
        const page = this.document.pages.find((item) => item.page_id === pageId);
        return page === undefined ? null : page;
    }

    navigate(pageId: string): void {
        if (!this.page(pageId)) throw new Error(`flow-ui: unknown page_id ${JSON.stringify(pageId)}`);
        this.pageId = pageId;
        this.emitChange();
    }

    conversationSettings(): FlowUiRecord {
        const settings: FlowUiRecord = {};
        if (!this.document) return settings;
        for (const page of this.document.pages) {
            for (const block of iterBlocks(page.blocks)) {
                if (block.type === 'conversation') return isObject(block.settings) ? block.settings : settings;
            }
        }
        return settings;
    }

    /** Значение поля ввода: локальная правка приоритетнее проекции state. */
    fieldValue(field: string): unknown {
        if (Object.prototype.hasOwnProperty.call(this.edits, field)) return this.edits[field];
        return valueAtPath(this.state, field);
    }

    setEdit(field: string, value: unknown): void {
        if (typeof field !== 'string' || field === '') throw new Error('flow-ui: field is required');
        this.edits = { ...this.edits, [field]: value };
        if (this.fieldErrors.has(field)) {
            const remaining = new Set(this.fieldErrors);
            remaining.delete(field);
            this.fieldErrors = remaining;
        }
        this.emitChange();
    }

    /** Обязательные поля без значения после попытки отправить действие. */
    setFieldErrors(fields: Iterable<string>): void {
        this.fieldErrors = new Set(fields);
        this.emitChange();
    }

    setUploading(field: string, active: boolean): void {
        const uploading = new Set(this.uploading);
        if (active) uploading.add(field);
        else uploading.delete(field);
        this.uploading = uploading;
        this.emitChange();
    }

    /** Эфемерное состояние блока (активная вкладка), не входящее в state и ui-action. */
    localState(blockId: string): FlowUiRecord {
        const existing = this.blockLocal.get(blockId);
        if (existing !== undefined) return existing;
        const created: FlowUiRecord = {};
        this.blockLocal.set(blockId, created);
        return created;
    }

    /** Блоки активной страницы, пишущие поле state. */
    inputBlocks(): FlowUiBlock[] {
        const page = this.page(this.pageId);
        return [...iterBlocks(page ? page.blocks : [])].filter(writesField);
    }

    /**
     * Значения полей активной страницы для ui-action: непустые значения и явные локальные правки;
     * ``missing`` — обязательные поля без значения.
     */
    collectFields(): CollectFieldsResult {
        const fields: Record<string, unknown> = {};
        const missing = new Set<string>();
        for (const block of this.inputBlocks()) {
            const field = block.field === undefined || block.field === null ? '' : String(block.field);
            const value = this.fieldValue(field);
            const empty = isEmptyFieldValue(value);
            if (block.required === true && empty) missing.add(field);
            if (!empty || Object.prototype.hasOwnProperty.call(this.edits, field)) fields[field] = value === undefined ? null : value;
        }
        return { fields, missing };
    }

    clearEdits(fields: Iterable<string>): void {
        const next = { ...this.edits };
        for (const field of fields) delete next[field];
        this.edits = next;
        this.emitChange();
    }

    /** Локальный ход пользователя до первого кадра Task. */
    setPending(pending: FlowUiRecord | null): void {
        this.pending = pending;
        this.emitChange();
    }

    /** HTTP-стрим хода открыт: новый ход нельзя начать, пока клиент не закрыл предыдущий. */
    setStreaming(streaming: boolean): void {
        if (this.streaming === streaming) return;
        this.streaming = streaming;
        this.emitChange();
    }

    setError(error: unknown): void {
        this.error = error;
        this.emitChange();
    }

    /** Тестовый state редактора: подстановка шаблонов и условий без Tasks. */
    setState(state: FlowUiRecord): void {
        if (!isObject(state)) throw new Error('flow-ui: state must be an object');
        this.state = state;
        this.emitChange();
    }

    resetContext(contextId: string | null): void {
        this.contextId = contextId;
        this.activeTaskId = null;
        this.pending = null;
        this.state = {};
        this.edits = {};
        this.fieldErrors = new Set();
        this.uploading = new Set();
        this.blockLocal = new Map();
        this.slots = {};
        this.error = null;
        this.tasks = createA2ATaskAccumulator();
        if (this.document) this.pageId = null;
        if (this.document) this.setDocument(this.document);
        else this.emitChange();
    }

    task(taskId: string | null): import('../protocol/a2a-task-accumulator.js').A2aAccumulatedTask | null {
        if (taskId === null || taskId.length === 0) return null;
        const task = this.tasks.tasksById[taskId];
        return task === undefined ? null : task;
    }

    /**
     * Активный Task выполняется: известен, не завершён и не ждёт ввода. Только такой Task
     * можно отменить. Источник — состояние Task, а не открытость HTTP-стрима: после отмены
     * или перезагрузки стрима может не быть, а Task всё ещё выполняется, и наоборот.
     */
    get taskRunning(): boolean {
        const task = this.task(this.activeTaskId);
        const status = task?.status;
        return task !== null && !isSettledTaskState(
            isObject(status) ? status.state : undefined,
        );
    }

    /** Ход ещё идёт: локальный ход до первого кадра Task или выполняющийся Task. */
    get turnActive(): boolean {
        return this.pending !== null || this.taskRunning;
    }

    orderedTasks(): import('../protocol/a2a-task-accumulator.js').A2aAccumulatedTask[] {
        return this.tasks.taskOrder
            .map((taskId) => this.tasks.tasksById[taskId])
            .filter((task): task is import('../protocol/a2a-task-accumulator.js').A2aAccumulatedTask => task !== undefined);
    }

    /**
     * Кадр A2A (stream / ListTasks snapshot). Возвращает результат аккумулятора и
     * список декодированных ui-событий кадра, чтобы клиент оповестил подписчиков.
     */
    applyFrame(frame: FlowUiRecord): ApplyFrameResult {
        const applied = applyA2AFrame(this.tasks, frame);
        const uiEvents: FlowUiUiEvent[] = [];
        if (applied.frameKind === 'artifactUpdate') {
            const result = isObject(frame.result) ? frame.result : undefined;
            const artifactUpdate = result !== undefined && isObject(result.artifactUpdate) ? result.artifactUpdate : undefined;
            const artifact = recordField(artifactUpdate === undefined ? undefined : artifactUpdate.artifact, 'flow-ui artifact');
            const artifactId = artifact.artifactId;
            if (artifactId === STATE_ARTIFACT_ID) this._foldState();
            if (artifactId === UI_ARTIFACT_ID) {
                const parts = Array.isArray(artifact.parts) ? artifact.parts : [];
                for (const part of parts) {
                    const decoded = decodePart(part);
                    if (decoded.kind !== 'ui') throw new Error('flow-ui: ui artifact part must be a ui event');
                    if (!isUiEvent(decoded.event)) throw new Error('flow-ui: ui event kind required');
                    this._applyUiEvent(decoded.event);
                    uiEvents.push(decoded.event);
                }
            }
        } else if (applied.frameKind === 'task') {
            this._foldState();
            this._foldSlots();
        }
        if (applied.changedTaskId) {
            const task = this.tasks.tasksById[applied.changedTaskId];
            if (task && this.contextId === null) this.contextId = task.contextId;
            // Локальный ход живёт, пока сервер не отдал Task-снимок с history: status/artifact
            // кадры не несут сообщение пользователя, и лента потеряла бы его до конца стрима.
            if (this.pending !== null && applied.frameKind === 'task') this.pending = null;
        }
        this.emitChange();
        return { ...applied, uiEvents };
    }

    private _stateParts(): unknown[] {
        const parts: unknown[] = [];
        for (const task of this.orderedTasks()) {
            const artifact = task.artifactsById[STATE_ARTIFACT_ID];
            if (artifact && Array.isArray(artifact.parts)) parts.push(...artifact.parts);
        }
        return parts;
    }

    private _foldState(): void {
        let state: FlowUiRecord = {};
        for (const part of this._stateParts()) {
            const decoded = decodePart(part);
            if (decoded.kind === 'json') state = decoded.value;
            else if (decoded.kind === 'json_patch') state = applyJsonPatch(state, decoded.operations);
            else throw new Error('flow-ui: state artifact accepts only json snapshot or json patch');
        }
        this.state = state;
    }

    private _foldSlots(): void {
        this.slots = {};
        for (const task of this.orderedTasks()) {
            const artifact = task.artifactsById[UI_ARTIFACT_ID];
            if (!artifact || !Array.isArray(artifact.parts)) continue;
            for (const part of artifact.parts) {
                const decoded = decodePart(part);
                if (decoded.kind !== 'ui') throw new Error('flow-ui: ui artifact part must be a ui event');
                if (!isUiEvent(decoded.event)) throw new Error('flow-ui: ui event kind required');
                this._applyUiEvent(decoded.event);
            }
        }
    }

    private _applyUiEvent(event: FlowUiUiEvent): void {
        if (event.kind === 'render') {
            if (event.slot_id === CONVERSATION_SLOT_ID) return;
            const slotId = typeof event.slot_id === 'string' ? event.slot_id : '';
            this.slots = { ...this.slots, [slotId]: event.blocks };
            return;
        }
        // История диалога живёт дольше документа: страница из старого ``ui_navigate`` могла быть
        // удалена в редакторе, тогда переход не выполняется и активная страница не меняется.
        const pageId = typeof event.page_id === 'string' ? event.page_id : null;
        if (pageId !== null && this.page(pageId)) this.pageId = pageId;
    }
}

/** Обход блоков в глубину: section/columns/tabs содержат вложенные списки. */
export function* iterBlocks(blocks: unknown): Generator<FlowUiBlock, void, void> {
    for (const raw of Array.isArray(blocks) ? blocks : []) {
        if (!isBlock(raw)) continue;
        const block = raw;
        yield block;
        if (block.type === 'section') yield* iterBlocks(block.blocks);
        if (block.type === 'columns') {
            for (const column of Array.isArray(block.columns) ? block.columns : []) {
                yield* iterBlocks(isObject(column) ? column.blocks : []);
            }
        }
        if (block.type === 'tabs') {
            for (const tab of Array.isArray(block.tabs) ? block.tabs : []) {
                yield* iterBlocks(isObject(tab) ? tab.blocks : []);
            }
        }
    }
}

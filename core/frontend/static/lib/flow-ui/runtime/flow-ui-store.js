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

import { isSettledTaskState } from '../protocol/a2a-stream.js';
import { applyA2AFrame, createA2ATaskAccumulator } from '../protocol/a2a-task-accumulator.js';
import { CONVERSATION_SLOT_ID, INPUT_BLOCK_TYPES, STATE_ARTIFACT_ID, UI_ARTIFACT_ID } from '../protocol/constants.js';
import { applyJsonPatch, decodePart } from '../protocol/parts.js';
import { valueAtPath } from './templating.js';

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/** ``html`` с ``field`` пишет поле через ``flowUi.setValue`` наравне с блоками ввода. */
function writesField(block) {
    return INPUT_BLOCK_TYPES.has(block.type) || (block.type === 'html' && block.field !== null);
}

function isEmptyFieldValue(value) {
    return value === undefined || value === null || value === '' || (Array.isArray(value) && value.length === 0);
}

export class FlowUIStore {
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

    subscribe(listener) {
        if (typeof listener !== 'function') throw new Error('flow-ui: store listener must be a function');
        this._listeners.add(listener);
        return () => this._listeners.delete(listener);
    }

    emitChange() {
        for (const listener of [...this._listeners]) listener(this);
    }

    setInterface(interfaceResponse) {
        if (!isObject(interfaceResponse) || !isObject(interfaceResponse.document)) {
            throw new Error('flow-ui: interface response requires document');
        }
        this.interface = interfaceResponse;
        this.setDocument(interfaceResponse.document);
    }

    /** Локальный документ (редактор/предпросмотр) поверх серверного ответа. */
    setDocument(document) {
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

    page(pageId) {
        if (!this.document) return null;
        return this.document.pages.find((page) => page.page_id === pageId) || null;
    }

    navigate(pageId) {
        if (!this.page(pageId)) throw new Error(`flow-ui: unknown page_id ${JSON.stringify(pageId)}`);
        this.pageId = pageId;
        this.emitChange();
    }

    conversationSettings() {
        const settings = {};
        if (!this.document) return settings;
        for (const page of this.document.pages) {
            for (const block of iterBlocks(page.blocks)) {
                if (block.type === 'conversation') return isObject(block.settings) ? block.settings : settings;
            }
        }
        return settings;
    }

    /** Значение поля ввода: локальная правка приоритетнее проекции state. */
    fieldValue(field) {
        if (Object.prototype.hasOwnProperty.call(this.edits, field)) return this.edits[field];
        return valueAtPath(this.state, field);
    }

    setEdit(field, value) {
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
    setFieldErrors(fields) {
        this.fieldErrors = new Set(fields);
        this.emitChange();
    }

    setUploading(field, active) {
        const uploading = new Set(this.uploading);
        if (active) uploading.add(field);
        else uploading.delete(field);
        this.uploading = uploading;
        this.emitChange();
    }

    /** Эфемерное состояние блока (активная вкладка), не входящее в state и ui-action. */
    localState(blockId) {
        if (!this.blockLocal.has(blockId)) this.blockLocal.set(blockId, {});
        return this.blockLocal.get(blockId);
    }

    /** Блоки активной страницы, пишущие поле state. */
    inputBlocks() {
        const page = this.page(this.pageId);
        return [...iterBlocks(page ? page.blocks : [])].filter(writesField);
    }

    /**
     * Значения полей активной страницы для ui-action: непустые значения и явные локальные правки;
     * ``missing`` — обязательные поля без значения.
     */
    collectFields() {
        const fields = {};
        const missing = new Set();
        for (const block of this.inputBlocks()) {
            const value = this.fieldValue(block.field);
            const empty = isEmptyFieldValue(value);
            if (block.required === true && empty) missing.add(block.field);
            if (!empty || Object.prototype.hasOwnProperty.call(this.edits, block.field)) fields[block.field] = value === undefined ? null : value;
        }
        return { fields, missing };
    }

    clearEdits(fields) {
        const next = { ...this.edits };
        for (const field of fields) delete next[field];
        this.edits = next;
        this.emitChange();
    }

    /** Локальный ход пользователя до первого кадра Task. */
    setPending(pending) {
        this.pending = pending;
        this.emitChange();
    }

    /** HTTP-стрим хода открыт: новый ход нельзя начать, пока клиент не закрыл предыдущий. */
    setStreaming(streaming) {
        if (this.streaming === streaming) return;
        this.streaming = streaming;
        this.emitChange();
    }

    setError(error) {
        this.error = error;
        this.emitChange();
    }

    /** Тестовый state редактора: подстановка шаблонов и условий без Tasks. */
    setState(state) {
        if (!isObject(state)) throw new Error('flow-ui: state must be an object');
        this.state = state;
        this.emitChange();
    }

    resetContext(contextId) {
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

    task(taskId) {
        return taskId ? this.tasks.tasksById[taskId] || null : null;
    }

    /**
     * Активный Task выполняется: известен, не завершён и не ждёт ввода. Только такой Task
     * можно отменить. Источник — состояние Task, а не открытость HTTP-стрима: после отмены
     * или перезагрузки стрима может не быть, а Task всё ещё выполняется, и наоборот.
     */
    get taskRunning() {
        const task = this.task(this.activeTaskId);
        return task !== null && !isSettledTaskState(task.status?.state);
    }

    /** Ход ещё идёт: локальный ход до первого кадра Task или выполняющийся Task. */
    get turnActive() {
        return this.pending !== null || this.taskRunning;
    }

    orderedTasks() {
        return this.tasks.taskOrder.map((taskId) => this.tasks.tasksById[taskId]);
    }

    /**
     * Кадр A2A (stream / ListTasks snapshot). Возвращает результат аккумулятора и
     * список декодированных ui-событий кадра, чтобы клиент оповестил подписчиков.
     */
    applyFrame(frame) {
        const applied = applyA2AFrame(this.tasks, frame);
        const uiEvents = [];
        if (applied.frameKind === 'artifactUpdate') {
            const artifact = frame.result.artifactUpdate.artifact;
            const artifactId = artifact.artifactId;
            if (artifactId === STATE_ARTIFACT_ID) this._foldState();
            if (artifactId === UI_ARTIFACT_ID) {
                for (const part of artifact.parts) {
                    const decoded = decodePart(part);
                    if (decoded.kind !== 'ui') throw new Error('flow-ui: ui artifact part must be a ui event');
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

    _stateParts() {
        const parts = [];
        for (const task of this.orderedTasks()) {
            const artifact = task.artifactsById[STATE_ARTIFACT_ID];
            if (artifact) parts.push(...artifact.parts);
        }
        return parts;
    }

    _foldState() {
        let state = {};
        for (const part of this._stateParts()) {
            const decoded = decodePart(part);
            if (decoded.kind === 'json') state = decoded.value;
            else if (decoded.kind === 'json_patch') state = applyJsonPatch(state, decoded.operations);
            else throw new Error('flow-ui: state artifact accepts only json snapshot or json patch');
        }
        this.state = state;
    }

    _foldSlots() {
        this.slots = {};
        for (const task of this.orderedTasks()) {
            const artifact = task.artifactsById[UI_ARTIFACT_ID];
            if (!artifact) continue;
            for (const part of artifact.parts) {
                const decoded = decodePart(part);
                if (decoded.kind !== 'ui') throw new Error('flow-ui: ui artifact part must be a ui event');
                this._applyUiEvent(decoded.event);
            }
        }
    }

    _applyUiEvent(event) {
        if (event.kind === 'render') {
            if (event.slot_id === CONVERSATION_SLOT_ID) return;
            this.slots = { ...this.slots, [event.slot_id]: event.blocks };
            return;
        }
        // История диалога живёт дольше документа: страница из старого ``ui_navigate`` могла быть
        // удалена в редакторе, тогда переход не выполняется и активная страница не меняется.
        if (this.page(event.page_id)) this.pageId = event.page_id;
    }
}

/** Обход блоков в глубину: section/columns/tabs содержат вложенные списки. */
export function* iterBlocks(blocks) {
    for (const block of Array.isArray(blocks) ? blocks : []) {
        yield block;
        if (block.type === 'section') yield* iterBlocks(block.blocks);
        if (block.type === 'columns') for (const column of block.columns) yield* iterBlocks(column.blocks);
        if (block.type === 'tabs') for (const tab of block.tabs) yield* iterBlocks(tab.blocks);
    }
}

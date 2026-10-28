/**
 * Проекция A2A Tasks в ленту диалога. Один Task — один ход: сообщение пользователя
 * (ROLE_USER из history), активность инструментов, карточки агента (артефакт ``ui`` →
 * slot ``conversation``), reasoning, текст ``response``, реплики HITL
 * (``user_message`` / ``operator_reply`` в порядке артефактов), статус Task.
 */

import { isPlainRecord } from '../../events/payload.js';
import { isSettledTaskState } from '../protocol/a2a-stream.js';
import {
    CONVERSATION_SLOT_ID,
    OPERATOR_REPLY_ARTIFACT_NAME,
    REASONING_ARTIFACT_NAME,
    RESPONSE_ARTIFACT_NAME,
    UI_ARTIFACT_ID,
    USER_MESSAGE_ARTIFACT_NAME,
} from '../protocol/constants.js';
import { decodePart, filesFromParts, firstDataFromParts, textFromParts } from '../protocol/parts.js';
import { flowUIText } from '../utils/text.js';
import { taskInterrupt, type FlowUiTaskInterrupt } from './operator-handoff-from-task.js';

export interface FlowUiTask extends Record<string, unknown> {
    id?: unknown;
    status?: unknown;
    history?: unknown;
    artifacts?: unknown;
    artifactsById?: unknown;
    metadata?: unknown;
}

export interface FlowUiSettings extends Record<string, unknown> {
    show_activity?: boolean;
    tool_calls?: string;
    errors?: string;
    show_skill_loads?: boolean;
    show_reasoning?: boolean;
}

export interface FlowUiStoreLike {
    orderedTasks(): FlowUiTask[];
    state: { files?: unknown };
    task(id: string | null): FlowUiTask | null | undefined;
    activeTaskId: string | null;
}

export interface FlowUiActivityItem {
    id: unknown;
    kind: string;
    status: string;
    label: string;
    detail: string;
}

export interface ConversationTurnUser {
    text: string;
    files: Record<string, unknown>[];
    action: Record<string, unknown> | null;
}

export interface ConversationTurnDialogueItem {
    id: unknown;
    role: 'user' | 'operator';
    text: string;
    author: Record<string, unknown> | null;
}

export interface ConversationTurn {
    taskId: string;
    state: string;
    settled: boolean;
    user: ConversationTurnUser | null;
    activity: FlowUiActivityItem[];
    cards: Record<string, unknown>[];
    reasoning: string;
    text: string;
    author: Record<string, unknown> | null;
    dialogue: ConversationTurnDialogueItem[];
    interrupt: FlowUiTaskInterrupt | null;
    error: string;
}

type AnyRecord = Record<string, unknown>;

function artifactsOf(task: FlowUiTask): AnyRecord[] {
    return Array.isArray(task.artifacts) ? task.artifacts.filter(isPlainRecord) : [];
}

function authorOf(artifact: AnyRecord): AnyRecord | null {
    const metadata = artifact.metadata;
    if (!isPlainRecord(metadata) || !isPlainRecord(metadata.author)) {
        return null;
    }
    return metadata.author;
}

function taskStatus(task: FlowUiTask): AnyRecord | undefined {
    return isPlainRecord(task.status) ? task.status : undefined;
}

function statusMessage(status: AnyRecord | undefined): AnyRecord | undefined {
    if (status === undefined || !isPlainRecord(status.message)) {
        return undefined;
    }
    return status.message;
}

/** FileRef из A2A file Part (клиентское вложение пользователя). */
function fileRefFromPart(file: { url: string; filename: string; mediaType: string }): AnyRecord {
    return {
        file_id: null,
        url: file.url,
        original_name: file.filename !== '' ? file.filename : file.url.split('/').pop(),
        content_type: file.mediaType !== '' ? file.mediaType : 'application/octet-stream',
        file_size: null,
    };
}

export function userMessageOfTask(task: FlowUiTask): ConversationTurnUser | null {
    const history = Array.isArray(task.history) ? task.history : [];
    for (const raw of history) {
        if (!isPlainRecord(raw)) continue;
        const message = raw;
        if (message.role !== 'ROLE_USER') continue;
        if (typeof message.taskId === 'string' && message.taskId !== '' && message.taskId !== task.id) continue;
        const decoded = (Array.isArray(message.parts) ? message.parts : []).map(decodePart);
        const action = decoded.find((part) => part.kind === 'ui_action');
        return {
            text: textFromParts(message.parts),
            files: filesFromParts(message.parts).map(fileRefFromPart),
            action: action && action.kind === 'ui_action' ? action.action : null,
        };
    }
    return null;
}

/** Чипы инструментов и ошибок нод из платформенных data-артефактов задачи. */
export function taskActivity(task: FlowUiTask, settings: FlowUiSettings, locale: string): FlowUiActivityItem[] {
    const showTools = settings.show_activity !== false && settings.tool_calls !== 'hidden';
    const detailed = settings.tool_calls === 'detailed';
    const byId = new Map<string, FlowUiActivityItem>();
    const errors: FlowUiActivityItem[] = [];
    for (const artifact of artifactsOf(task)) {
        const name = typeof artifact.name === 'string' ? artifact.name : '';
        const payload = firstDataFromParts(artifact.parts);
        if (!isPlainRecord(payload)) continue;
        if (name.startsWith('node_error_')) {
            const detail = typeof payload.error === 'string' ? payload.error : '';
            errors.push({
                id: artifact.artifactId,
                kind: 'error',
                status: 'error',
                label: settings.errors === 'detailed' && detail !== '' ? detail : flowUIText(locale, 'turn_toast_error_generic'),
                detail: settings.errors === 'detailed' ? detail : '',
            });
            continue;
        }
        if (typeof payload.tool !== 'string' || typeof payload.tool_call_id !== 'string') continue;
        const isSkill = payload.tool === 'load_agent_skill';
        if (isSkill ? settings.show_skill_loads === false : !showTools) continue;
        const previous = byId.get(payload.tool_call_id);
        const isResult = Object.prototype.hasOwnProperty.call(payload, 'result');
        let detail = previous ? previous.detail : '';
        if (detailed && !isResult && payload.args && typeof payload.args === 'object') detail = JSON.stringify(payload.args);
        if (detailed && isResult && typeof payload.result === 'string') detail = payload.result.slice(0, 160);
        const args = payload.args;
        const skillId = isPlainRecord(args) && typeof args.agent_skill_id === 'string'
            ? args.agent_skill_id
            : '';
        byId.set(payload.tool_call_id, {
            id: payload.tool_call_id,
            kind: isSkill ? 'skill' : 'tool',
            label: isSkill && skillId !== '' ? skillId : (previous ? previous.label : payload.tool),
            detail,
            status: isResult || (previous && previous.status === 'done') ? 'done' : 'running',
        });
    }
    if (isSettledTaskState(taskStatus(task)?.state)) {
        for (const item of byId.values()) if (item.status === 'running') item.status = 'done';
    }
    return [...byId.values(), ...errors];
}

/** Карточки агента в ленте: рендеры одного ``block_id`` заменяют друг друга на месте первого. */
export function taskCards(task: FlowUiTask): AnyRecord[] {
    const byId = isPlainRecord(task.artifactsById) ? task.artifactsById : null;
    const artifact = byId ? byId[UI_ARTIFACT_ID] : null;
    if (!isPlainRecord(artifact)) return [];
    const parts = artifact.parts;
    const cards = new Map<unknown, AnyRecord>();
    for (const part of Array.isArray(parts) ? parts : []) {
        const decoded = decodePart(part);
        if (decoded.kind !== 'ui') continue;
        const event = decoded.event;
        if (event.kind !== 'render' || event.slot_id !== CONVERSATION_SLOT_ID) continue;
        const blocks = Array.isArray(event.blocks) ? event.blocks : [];
        for (const block of blocks) {
            if (!isPlainRecord(block)) continue;
            cards.set(block.block_id, block);
        }
    }
    return [...cards.values()];
}

export function taskText(task: FlowUiTask, artifactName: string): string {
    return artifactsOf(task)
        .filter((artifact) => artifact.name === artifactName)
        .map((artifact) => textFromParts(artifact.parts))
        .join('');
}

/** Реплики HITL в порядке артефактов: пользователь ↔ оператор во время takeover. */
export function taskDialogue(task: FlowUiTask): ConversationTurnDialogueItem[] {
    const items: ConversationTurnDialogueItem[] = [];
    for (const artifact of artifactsOf(task)) {
        if (artifact.name === USER_MESSAGE_ARTIFACT_NAME) {
            items.push({ id: artifact.artifactId, role: 'user', text: textFromParts(artifact.parts), author: null });
        } else if (artifact.name === OPERATOR_REPLY_ARTIFACT_NAME) {
            items.push({ id: artifact.artifactId, role: 'operator', text: textFromParts(artifact.parts), author: authorOf(artifact) });
        }
    }
    return items;
}

export function taskErrorText(task: FlowUiTask, settings: FlowUiSettings, locale: string): string {
    const status = taskStatus(task);
    if (status?.state !== 'TASK_STATE_FAILED') return '';
    if (settings.errors === 'detailed') {
        const message = statusMessage(status);
        const detail = textFromParts(message?.parts);
        if (detail !== '') return detail;
    }
    return flowUIText(locale, 'turn_toast_error_generic');
}

/**
 * Вопрос interrupt, дословно повторяющий текст ответа (LLM уже озвучил его в ``response``),
 * не показывается вторым пузырём: остаются только kind и действия (OAuth, ожидание оператора).
 */
function interruptWithoutEcho(interrupt: FlowUiTaskInterrupt | null, text: string): FlowUiTaskInterrupt | null {
    if (interrupt === null || interrupt.kind === 'user_message' || interrupt.question === '') return interrupt;
    if (interrupt.question.trim() !== text.trim()) return interrupt;
    return { ...interrupt, question: '' };
}

/**
 * @returns {{
 *   taskId: string, state: string, settled: boolean,
 *   user: { text: string, files: object[], action: object | null } | null,
 *   activity: object[], cards: object[], reasoning: string, text: string,
 *   author: object | null, dialogue: object[], interrupt: object | null,
 *   error: string, files: object[],
 * }}
 */
export function conversationTurn(task: FlowUiTask, settings: FlowUiSettings, locale: string): ConversationTurn {
    const status = taskStatus(task);
    const state = typeof status?.state === 'string' ? status.state : 'TASK_STATE_SUBMITTED';
    const settled = isSettledTaskState(state);
    const responseArtifact = artifactsOf(task).find((artifact) => artifact.name === RESPONSE_ARTIFACT_NAME);
    const interrupt = taskInterrupt(task);
    let text = taskText(task, RESPONSE_ARTIFACT_NAME);
    if (text === '' && interrupt !== null && interrupt.kind === 'user_message') text = interrupt.question;
    if (text === '' && state === 'TASK_STATE_COMPLETED') {
        const message = statusMessage(status);
        text = textFromParts(message?.parts);
    }
    return {
        taskId: typeof task.id === 'string' ? task.id : '',
        state,
        settled,
        user: userMessageOfTask(task),
        activity: taskActivity(task, settings, locale),
        cards: taskCards(task),
        reasoning: settings.show_reasoning === true ? taskText(task, REASONING_ARTIFACT_NAME) : '',
        text,
        author: responseArtifact ? authorOf(responseArtifact) : null,
        dialogue: taskDialogue(task),
        interrupt: interruptWithoutEcho(interrupt, text),
        error: taskErrorText(task, settings, locale),
    };
}

export function conversationTurns(store: FlowUiStoreLike, settings: FlowUiSettings, locale: string): ConversationTurn[] {
    return store.orderedTasks().map((task) => conversationTurn(task, settings, locale));
}

/** Уникальные FileRef сессии: вложения пользователя и файлы из проекции ``state.files``. */
export function sessionFiles(store: FlowUiStoreLike): AnyRecord[] {
    const byKey = new Map<string, AnyRecord>();
    const put = (ref: unknown) => {
        if (!isPlainRecord(ref)) return;
        const record = ref;
        const key = typeof record.file_id === 'string' && record.file_id !== '' ? record.file_id : record.url;
        if (typeof key !== 'string' || key === '') return;
        const previous = byKey.get(key);
        byKey.set(key, { ...(previous === undefined ? {} : previous), ...record });
    };
    for (const task of store.orderedTasks()) {
        const user = userMessageOfTask(task);
        if (user) user.files.forEach(put);
    }
    if (Array.isArray(store.state.files)) store.state.files.forEach(put);
    return [...byKey.values()];
}

/**
 * Interrupt Task из ``status.message.metadata.platform_interrupt`` (A2A INPUT_REQUIRED).
 * ``operator_task``, ``oauth_required`` и ``handoff`` продолжаются без хода пользователя —
 * такие Tasks клиент дочитывает через SubscribeToTask до terminal-состояния.
 */

import { isPlainRecord } from '../../events/payload.js';
import { isInterruptedTaskState } from '../protocol/a2a-stream.js';
import { textFromParts } from '../protocol/parts.js';

const CONTINUING_KINDS: ReadonlySet<string> = new Set(['operator_task', 'oauth_required', 'handoff']);

type FlowUiRecord = Record<string, unknown>;

function objectOrEmpty(value: unknown): FlowUiRecord {
    if (isPlainRecord(value)) return value;
    return {};
}

/**
 * @returns {{
 *   kind: string,
 *   question: string,
 *   continues: boolean,
 *   handoffMode: string,
 *   workItemId: string | null,
 *   taskTitle: string,
 *   authUrl: string,
 *   provider: string,
 *   service: string,
 * } | null}
 */
export interface FlowUiTaskInterrupt {
    kind: string;
    question: string;
    continues: boolean;
    handoffMode: string;
    workItemId: string | null;
    taskTitle: string;
    authUrl: string;
    provider: string;
    service: string;
}

export function taskInterrupt(task: FlowUiRecord | null | undefined): FlowUiTaskInterrupt | null {
    if (!task || typeof task !== 'object') return null;
    const status = objectOrEmpty(task.status);
    if (!isInterruptedTaskState(status.state)) return null;
    const message = objectOrEmpty(status.message);
    const packed = objectOrEmpty(message.metadata).platform_interrupt
        ?? objectOrEmpty(task?.metadata).platform_interrupt;
    const interrupt = objectOrEmpty(packed);
    const body = objectOrEmpty(interrupt.body);
    const kind = typeof body.kind === 'string' && body.kind !== '' ? body.kind : 'user_message';
    const question = typeof interrupt.question === 'string' && interrupt.question !== ''
        ? interrupt.question
        : textFromParts(message.parts);
    return {
        kind,
        question,
        continues: CONTINUING_KINDS.has(kind),
        handoffMode: typeof body.handoff_mode === 'string' && body.handoff_mode !== '' ? body.handoff_mode : 'single_reply',
        workItemId: typeof body.work_item_id === 'string' && body.work_item_id !== '' ? body.work_item_id : null,
        taskTitle: typeof body.task_title === 'string' ? body.task_title : '',
        authUrl: typeof body.auth_url === 'string' ? body.auth_url : '',
        provider: typeof body.provider === 'string' ? body.provider : '',
        service: typeof body.service === 'string' ? body.service : '',
    };
}

/**
 * @returns {{ mode: 'single_reply' | 'takeover', workItemId: string | null, taskId: string } | null}
 */
export interface OperatorHandoff {
    mode: 'single_reply' | 'takeover';
    workItemId: string | null;
    taskId: string;
}

export function operatorHandoffFromTask(task: FlowUiRecord | null | undefined): OperatorHandoff | null {
    const interrupt = taskInterrupt(task);
    if (interrupt === null || interrupt.kind !== 'operator_task') return null;
    if (interrupt.handoffMode !== 'takeover' && interrupt.handoffMode !== 'single_reply') {
        throw new Error(`operatorHandoffFromTask: unsupported handoff_mode ${JSON.stringify(interrupt.handoffMode)}`);
    }
    if (task === undefined || task === null) {
        throw new Error('operatorHandoffFromTask: task required');
    }
    const rawId = task.id;
    const taskId = rawId === undefined || rawId === null || rawId === '' || rawId === false || rawId === 0
        ? ''
        : String(rawId);
    return { mode: interrupt.handoffMode, workItemId: interrupt.workItemId, taskId };
}

export function operatorHandoffFromTasks(tasksById: unknown, taskOrder: unknown): OperatorHandoff | null {
    const order: unknown[] = Array.isArray(taskOrder) ? taskOrder : [];
    const byId = objectOrEmpty(tasksById);
    for (let index = order.length - 1; index >= 0; index -= 1) {
        const raw = byId[String(order[index])];
        if (raw !== undefined && raw !== null && !isPlainRecord(raw)) {
            throw new Error('operatorHandoffFromTasks: task must be an object');
        }
        const handoff = operatorHandoffFromTask(raw);
        if (handoff) return handoff;
    }
    return null;
}

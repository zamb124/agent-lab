/**
 * Interrupt Task из ``status.message.metadata.platform_interrupt`` (A2A INPUT_REQUIRED).
 * ``operator_task``, ``oauth_required`` и ``handoff`` продолжаются без хода пользователя —
 * такие Tasks клиент дочитывает через SubscribeToTask до terminal-состояния.
 */

import { isInterruptedTaskState } from '../protocol/a2a-stream.js';
import { textFromParts } from '../protocol/parts.js';

const CONTINUING_KINDS = new Set(['operator_task', 'oauth_required', 'handoff']);

function objectOrEmpty(value) {
    return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
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
export function taskInterrupt(task) {
    if (!task || typeof task !== 'object') return null;
    const status = objectOrEmpty(task.status);
    if (!isInterruptedTaskState(status.state)) return null;
    const message = objectOrEmpty(status.message);
    const packed = objectOrEmpty(message.metadata).platform_interrupt
        ?? objectOrEmpty(task.metadata).platform_interrupt;
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
export function operatorHandoffFromTask(task) {
    const interrupt = taskInterrupt(task);
    if (interrupt === null || interrupt.kind !== 'operator_task') return null;
    if (interrupt.handoffMode !== 'takeover' && interrupt.handoffMode !== 'single_reply') {
        throw new Error(`operatorHandoffFromTask: unsupported handoff_mode ${JSON.stringify(interrupt.handoffMode)}`);
    }
    return { mode: interrupt.handoffMode, workItemId: interrupt.workItemId, taskId: task.id };
}

export function operatorHandoffFromTasks(tasksById, taskOrder) {
    const order = Array.isArray(taskOrder) ? taskOrder : [];
    for (let index = order.length - 1; index >= 0; index -= 1) {
        const handoff = operatorHandoffFromTask(objectOrEmpty(tasksById)[order[index]]);
        if (handoff) return handoff;
    }
    return null;
}

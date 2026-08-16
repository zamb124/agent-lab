import { inputRequiredFieldsFromA2a, isA2aInterruptedState } from '../protocol/a2a-result-helpers.js';

function taskMetadata(task) {
    const fromTask = task.metadata && typeof task.metadata === 'object' ? task.metadata : {};
    const status = task.status && typeof task.status === 'object' ? task.status : {};
    const fromStatus = status.metadata && typeof status.metadata === 'object' ? status.metadata : {};
    const message = status.message && typeof status.message === 'object' ? status.message : {};
    const fromMessage = message.metadata && typeof message.metadata === 'object' ? message.metadata : {};
    return { ...fromTask, ...fromStatus, ...fromMessage };
}

/**
 * @param {unknown} task
 * @returns {{ mode: 'single_reply'|'takeover', workItemId: string|null, taskId: string }|null}
 */
export function operatorHandoffFromTask(task) {
    if (!task || typeof task !== 'object') return null;
    const taskId = typeof task.id === 'string' ? task.id.trim() : '';
    if (taskId === '') return null;
    const state = task.status && typeof task.status === 'object' ? task.status.state : null;
    if (!isA2aInterruptedState(state)) return null;
    const message = task.status && typeof task.status === 'object' ? task.status.message : null;
    const fields = inputRequiredFieldsFromA2a(message, taskMetadata(task));
    if (fields.interruptKind !== 'operator_task') return null;
    if (fields.handoffMode !== 'takeover' && fields.handoffMode !== 'single_reply') {
        throw new Error(
            `operatorHandoffFromTask: unsupported handoffMode ${JSON.stringify(fields.handoffMode)}`,
        );
    }
    const mode = fields.handoffMode;
    const workItemId = typeof fields.workItemId === 'string' && fields.workItemId.trim() !== ''
        ? fields.workItemId
        : null;
    return { mode, workItemId, taskId };
}

/**
 * @param {Record<string, unknown>} tasksById
 * @param {string[]} taskOrder
 */
export function operatorHandoffFromTasks(tasksById, taskOrder) {
    if (!tasksById || typeof tasksById !== 'object') return null;
    const order = Array.isArray(taskOrder) ? taskOrder : [];
    for (let index = order.length - 1; index >= 0; index -= 1) {
        const taskId = order[index];
        const handoff = operatorHandoffFromTask(tasksById[taskId]);
        if (handoff) return handoff;
    }
    return null;
}

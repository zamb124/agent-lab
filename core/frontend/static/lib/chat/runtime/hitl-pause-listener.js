/**
 * Активная HITL-пауза в chat runtime state (operator_task + workItemId).
 *
 * Live-доставка реплик — `ChatController.syncHitlLiveTail` → A2A
 * `SubscribeToTask` на `stream:{a2a_task_id}`, не company WS.
 */

/**
 * @param {object} state chat runtime state
 * @returns {{
 *   workItemId: string,
 *   taskId: string,
 *   contextId: string,
 *   flowId: string,
 *   sessionId: string|null,
 * } | null}
 */
export function findActiveHitlPause(state) {
    if (!state || typeof state !== 'object') {
        return null;
    }
    const contextId = typeof state.currentContextId === 'string' ? state.currentContextId : '';
    if (contextId === '') {
        return null;
    }
    const bucket = state.messagesByContextId && state.messagesByContextId[contextId];
    const messages = bucket && Array.isArray(bucket.messages) ? bucket.messages : [];
    for (let i = messages.length - 1; i >= 0; i -= 1) {
        const message = messages[i];
        if (!message || typeof message !== 'object') {
            continue;
        }
        const inputRequired = message.inputRequired;
        if (!inputRequired || typeof inputRequired !== 'object') {
            continue;
        }
        if (inputRequired.interruptKind !== 'operator_task') {
            continue;
        }
        const workItemId = typeof inputRequired.workItemId === 'string' ? inputRequired.workItemId.trim() : '';
        if (workItemId === '') {
            continue;
        }
        const taskId = typeof message.taskId === 'string' && message.taskId.length > 0
            ? message.taskId
            : (typeof state.currentTaskId === 'string' ? state.currentTaskId : '');
        if (taskId === '') {
            continue;
        }
        const flowId = typeof state.currentFlowId === 'string' ? state.currentFlowId : '';
        const sessionId = typeof state.sessionId === 'string' && state.sessionId.length > 0
            ? state.sessionId
            : (flowId !== '' ? `${flowId}:${contextId}` : null);
        return {
            workItemId,
            taskId,
            contextId,
            flowId,
            sessionId,
        };
    }
    return null;
}

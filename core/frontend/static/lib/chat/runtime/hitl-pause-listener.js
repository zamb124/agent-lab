/**
 * Активные паузы chat runtime для live `SubscribeToTask`.
 *
 * - HITL `operator_task` + workItemId
 * - OAuth `oauth_required` + authUrl (backend держит SSE через platform_oauth_continue)
 *
 * Live-доставка — `ChatController.syncHitlLiveTail` → A2A `SubscribeToTask`
 * на `stream:{a2a_task_id}`, не company WS.
 */

/**
 * @param {object} state chat runtime state
 * @param {string} contextId
 * @returns {object[]}
 */
function _messagesForContext(state, contextId) {
    const bucket = state.messagesByContextId && state.messagesByContextId[contextId];
    return bucket && Array.isArray(bucket.messages) ? bucket.messages : [];
}

/**
 * @param {object} state
 * @param {string} contextId
 * @param {object} message
 * @returns {{ taskId: string, contextId: string, flowId: string, sessionId: string|null }}
 */
function _pauseIds(state, contextId, message) {
    const taskId = typeof message.taskId === 'string' && message.taskId.length > 0
        ? message.taskId
        : (typeof state.currentTaskId === 'string' ? state.currentTaskId : '');
    const flowId = typeof state.currentFlowId === 'string' ? state.currentFlowId : '';
    const sessionId = typeof state.sessionId === 'string' && state.sessionId.length > 0
        ? state.sessionId
        : (flowId !== '' ? `${flowId}:${contextId}` : null);
    return { taskId, contextId, flowId, sessionId };
}

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
    const messages = _messagesForContext(state, contextId);
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
        const ids = _pauseIds(state, contextId, message);
        if (ids.taskId === '') {
            continue;
        }
        return {
            workItemId,
            taskId: ids.taskId,
            contextId: ids.contextId,
            flowId: ids.flowId,
            sessionId: ids.sessionId,
        };
    }
    return null;
}

/**
 * OAuth pause: Authorize в новой вкладке → backend resume → SubscribeToTask подхватывает stream.
 *
 * @param {object} state chat runtime state
 * @returns {{
 *   taskId: string,
 *   contextId: string,
 *   flowId: string,
 *   sessionId: string|null,
 *   authUrl: string,
 * } | null}
 */
export function findActiveOauthPause(state) {
    if (!state || typeof state !== 'object') {
        return null;
    }
    const contextId = typeof state.currentContextId === 'string' ? state.currentContextId : '';
    if (contextId === '') {
        return null;
    }
    const messages = _messagesForContext(state, contextId);
    for (let i = messages.length - 1; i >= 0; i -= 1) {
        const message = messages[i];
        if (!message || typeof message !== 'object') {
            continue;
        }
        const inputRequired = message.inputRequired;
        if (!inputRequired || typeof inputRequired !== 'object') {
            continue;
        }
        if (inputRequired.interruptKind !== 'oauth_required') {
            continue;
        }
        const authUrl = typeof inputRequired.authUrl === 'string' ? inputRequired.authUrl.trim() : '';
        if (authUrl === '') {
            continue;
        }
        const ids = _pauseIds(state, contextId, message);
        if (ids.taskId === '') {
            continue;
        }
        return {
            taskId: ids.taskId,
            contextId: ids.contextId,
            flowId: ids.flowId,
            sessionId: ids.sessionId,
            authUrl,
        };
    }
    return null;
}

/**
 * HITL или OAuth — любой live-tail pause для SubscribeToTask.
 *
 * @param {object} state
 * @returns {{
 *   taskId: string,
 *   contextId: string,
 *   flowId: string,
 *   sessionId: string|null,
 *   kind: 'operator_task'|'oauth_required',
 *   workItemId?: string,
 *   authUrl?: string,
 * } | null}
 */
export function findActiveLiveTailPause(state) {
    const hitl = findActiveHitlPause(state);
    if (hitl !== null) {
        return {
            ...hitl,
            kind: 'operator_task',
        };
    }
    const oauth = findActiveOauthPause(state);
    if (oauth !== null) {
        return {
            ...oauth,
            kind: 'oauth_required',
        };
    }
    return null;
}

import { consumedPendingTurnIds } from '../catalog/platform/conversation-turn.js';

function emptyContext(contextId) {
    return {
        contextId,
        document: null,
        hydration: 'idle',
        serverRevision: null,
        pendingMutations: [],
        pendingTurns: [],
        submitting: false,
        saveStatus: 'saved',
        taskOrder: [],
        tasksById: {},
        activeTaskId: null,
        operatorHandoff: null,
        connection: 'offline',
        conflict: null,
        error: null,
    };
}

export function createFlowUIRuntimeState() {
    return {
        contextsById: {},
        activeContextId: null,
        profile: null,
        look: null,
    };
}

function contextFor(state, contextId) {
    return state.contextsById[contextId] || emptyContext(contextId);
}

function withContext(state, contextId, update) {
    const current = contextFor(state, contextId);
    return {
        ...state,
        activeContextId: contextId,
        contextsById: { ...state.contextsById, [contextId]: { ...current, ...update } },
    };
}

export function reduceFlowUIState(state, event) {
    switch (event.type) {
        case 'profile.loaded':
            return { ...state, profile: event.profile, look: event.profile.look || null };
        case 'context.loading':
            return withContext(state, event.contextId, { hydration: 'loading', connection: 'connecting', error: null });
        case 'context.hydrated':
            return withContext(state, event.contextId, {
                hydration: 'ready', connection: 'online', document: event.document,
                serverRevision: event.document.revision, conflict: null, error: null,
            });
        case 'context.failed':
            return withContext(state, event.contextId, { hydration: 'error', connection: 'offline', error: event.error });
        case 'context.activate':
            return { ...state, activeContextId: event.contextId };
        case 'document.local': {
            const context = contextFor(state, event.contextId);
            return withContext(state, event.contextId, {
                document: event.document,
                pendingMutations: [...context.pendingMutations, event.mutation],
                saveStatus: 'pending',
            });
        }
        case 'document.preview':
            return withContext(state, event.contextId, {
                document: event.document,
                saveStatus: 'saved',
                conflict: null,
            });
        case 'document.ack': {
            const context = contextFor(state, event.contextId);
            const acknowledged = new Set(event.mutationIds || [event.mutationId]);
            return withContext(state, event.contextId, {
                document: event.document,
                serverRevision: event.document.revision,
                pendingMutations: context.pendingMutations.filter((item) => !acknowledged.has(item.id)),
                saveStatus: context.pendingMutations.every((item) => acknowledged.has(item.id)) ? 'saved' : 'pending',
                conflict: null,
            });
        }
        case 'document.conflict':
            return withContext(state, event.contextId, { conflict: event.conflict, saveStatus: 'conflict' });
        case 'tasks.changed': {
            const context = contextFor(state, event.contextId);
            const pendingTurns = Array.isArray(context.pendingTurns) ? context.pendingTurns : [];
            const tasks = (event.taskOrder || [])
                .map((taskId) => event.tasksById?.[taskId])
                .filter((task) => task && typeof task === 'object');
            const consumed = consumedPendingTurnIds(tasks, pendingTurns);
            return withContext(state, event.contextId, {
                tasksById: event.tasksById,
                taskOrder: event.taskOrder,
                activeTaskId: event.activeTaskId,
                pendingTurns: pendingTurns.filter((item) => !consumed.has(item.id)),
                operatorHandoff: Object.prototype.hasOwnProperty.call(event, 'operatorHandoff')
                    ? event.operatorHandoff
                    : context.operatorHandoff,
            });
        }
        case 'turn.optimistic': {
            if (typeof event.turn?.id !== 'string' || event.turn.id.trim() === '') {
                throw new Error('flow-ui: turn.optimistic requires turn.id');
            }
            if (typeof event.turn?.text !== 'string') {
                throw new Error('flow-ui: turn.optimistic requires turn.text');
            }
            if (event.turn.files != null && !Array.isArray(event.turn.files)) {
                throw new Error('flow-ui: turn.optimistic files must be an array');
            }
            // A new submit replaces any orphan pending turn that never received
            // mutation_id — otherwise a stale optimistic user attaches to the next task.
            return withContext(state, event.contextId, {
                pendingTurns: [{
                    id: event.turn.id,
                    text: event.turn.text,
                    files: Array.isArray(event.turn.files) ? event.turn.files : [],
                }],
            });
        }
        case 'submit.started':
            return withContext(state, event.contextId, { submitting: true });
        case 'submit.finished':
            return withContext(state, event.contextId, { submitting: false });
        default:
            return state;
    }
}

export function activeFlowUIContext(state) {
    return state.activeContextId ? state.contextsById[state.activeContextId] || null : null;
}

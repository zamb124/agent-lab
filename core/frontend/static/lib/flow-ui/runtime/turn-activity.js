/**
 * Pure turn-activity derivation for Flow UI chrome toasts and conversation chips.
 * Toasts: used when the active page has no conversation feed — form/dashboard pages
 * still need working / response / (gated) reasoning feedback.
 * Conversation: `projectConversationActivity` feeds inline chips inside ArtifactFeed.
 */
import {
    conversationTurnText,
    isSettledTaskState,
} from '../catalog/platform/conversation-turn.js';
import { adaptCurrentArtifact } from '../protocol/current-artifact-adapters.js';
import { flowUIText } from '../utils/text.js';

/** Mirrors FlowInterfacePolicySnapshot defaults (core/state/flow_ui.py). */
export const FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS = Object.freeze({
    show_reasoning: false,
    tool_calls_display: 'compact',
    show_activity: true,
    show_skill_loads: true,
    errors_display: 'generic',
    allow_cancel: true,
});

/**
 * @param {unknown} document
 * @returns {typeof FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS}
 */
export function resolveTurnActivityPolicy(document) {
    const policy = document && typeof document === 'object' && document.policy
        && typeof document.policy === 'object'
        ? document.policy
        : {};
    return Object.freeze({
        show_reasoning: typeof policy.show_reasoning === 'boolean'
            ? policy.show_reasoning
            : FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS.show_reasoning,
        tool_calls_display: policy.tool_calls_display === 'hidden'
            || policy.tool_calls_display === 'compact'
            || policy.tool_calls_display === 'detailed'
            ? policy.tool_calls_display
            : FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS.tool_calls_display,
        show_activity: typeof policy.show_activity === 'boolean'
            ? policy.show_activity
            : FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS.show_activity,
        show_skill_loads: typeof policy.show_skill_loads === 'boolean'
            ? policy.show_skill_loads
            : FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS.show_skill_loads,
        errors_display: policy.errors_display === 'detailed' || policy.errors_display === 'generic'
            ? policy.errors_display
            : FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS.errors_display,
        allow_cancel: typeof policy.allow_cancel === 'boolean'
            ? policy.allow_cancel
            : FLOW_UI_TURN_ACTIVITY_POLICY_DEFAULTS.allow_cancel,
    });
}

/**
 * True when the active surface already hosts conversation transcript UI.
 * @param {unknown} document
 */
export function hasConversationFeed(document) {
    if (!document || typeof document !== 'object') return false;
    const pages = document.pages;
    const surfaces = document.surfaces;
    if (!pages || typeof pages !== 'object' || !surfaces || typeof surfaces !== 'object') {
        return false;
    }
    const pageId = document.active_page_id;
    if (typeof pageId !== 'string' || pageId === '') return false;
    const page = pages[pageId];
    if (!page || typeof page !== 'object') return false;
    const surfaceId = page.root_surface_id;
    if (typeof surfaceId !== 'string' || surfaceId === '') return false;
    const surface = surfaces[surfaceId];
    const components = surface && typeof surface === 'object' ? surface.components : null;
    if (!components || typeof components !== 'object') return false;
    for (const component of Object.values(components)) {
        if (!component || typeof component !== 'object') continue;
        if (component.type === 'ConversationFeed') return true;
        if (component.type === 'ArtifactFeed'
            && component.properties
            && typeof component.properties === 'object'
            && component.properties.presentation === 'conversation') {
            return true;
        }
    }
    return false;
}

function textFromParts(parts) {
    if (!Array.isArray(parts)) return '';
    return parts
        .map((part) => (part && typeof part.text === 'string' ? part.text : ''))
        .join('');
}

function firstDataPayload(artifact) {
    const parts = Array.isArray(artifact?.parts) ? artifact.parts : [];
    for (const part of parts) {
        if (part && typeof part === 'object' && Object.prototype.hasOwnProperty.call(part, 'data')) {
            return part.data;
        }
    }
    return null;
}

/**
 * @param {unknown} payload
 * @param {string} adaptedName
 * @param {string} kind
 * @returns {string}
 */
function toolNameFromPayload(payload, adaptedName, kind) {
    if (payload && typeof payload === 'object') {
        if (typeof payload.tool === 'string' && payload.tool.trim() !== '') {
            return payload.tool.trim();
        }
        if (typeof payload.name === 'string' && payload.name.trim() !== '') {
            return payload.name.trim();
        }
    }
    const stripped = typeof adaptedName === 'string'
        ? adaptedName.replace(/^tool_(call|result):/, '')
        : '';
    if (stripped !== '') return stripped;
    return kind;
}

/**
 * @param {unknown} payload
 * @returns {string}
 */
function skillLabelFromPayload(payload) {
    if (!payload || typeof payload !== 'object') return 'skill';
    if (typeof payload.agent_skill_id === 'string' && payload.agent_skill_id.trim() !== '') {
        return payload.agent_skill_id.trim();
    }
    if (typeof payload.name === 'string' && payload.name.trim() !== '') {
        return payload.name.trim();
    }
    return 'skill';
}

/**
 * @param {object} task
 */
export function taskReasoningText(task) {
    if (!task || typeof task !== 'object') {
        throw new Error('flow-ui: taskReasoningText requires task object');
    }
    return (Array.isArray(task.artifacts) ? task.artifacts : [])
        .filter((artifact) => artifact && typeof artifact === 'object' && artifact.name === 'reasoning')
        .map((artifact) => textFromParts(artifact.parts))
        .join('');
}

/**
 * @param {object} task
 * @param {{ show_activity: boolean, tool_calls_display: string, show_skill_loads: boolean }} policy
 */
export function taskActivitySummary(task, policy) {
    if (!task || typeof task !== 'object') {
        throw new Error('flow-ui: taskActivitySummary requires task object');
    }
    const items = projectConversationActivity(task, policy)
        .filter((item) => item.kind === 'tool' || item.kind === 'skill');
    if (items.length === 0) return '';
    const labels = items.map((item) => item.label);
    if (policy.tool_calls_display === 'detailed' || policy.show_skill_loads === true) {
        return labels.slice(0, 4).join(' · ');
    }
    return labels[labels.length - 1];
}

/**
 * Policy-gated activity chips for conversation ArtifactFeed.
 * Observability artifacts stay out of turn text / EmptyState; they render here.
 *
 * @param {object} task
 * @param {{
 *   show_activity: boolean,
 *   tool_calls_display: string,
 *   show_skill_loads: boolean,
 *   errors_display: string,
 * }} policy
 * @param {'ru' | 'en'} [locale]
 * @returns {readonly {
 *   id: string,
 *   kind: 'tool' | 'skill' | 'error',
 *   label: string,
 *   detail: string,
 *   status: 'running' | 'done' | 'error',
 * }[]}
 */
export function projectConversationActivity(task, policy, locale = 'ru') {
    if (!task || typeof task !== 'object') {
        throw new Error('flow-ui: projectConversationActivity requires task object');
    }
    const showTools = policy.show_activity === true && policy.tool_calls_display !== 'hidden';
    const showSkills = policy.show_skill_loads === true;
    const detailed = policy.tool_calls_display === 'detailed';

    /** @type {Map<string, { id: string, kind: 'tool' | 'skill', label: string, detail: string, status: 'running' | 'done' | 'error' }>} */
    const byKey = new Map();
    /** @type {{ id: string, kind: 'tool' | 'skill' | 'error', label: string, detail: string, status: 'running' | 'done' | 'error' }[]} */
    const errors = [];

    for (const artifact of Array.isArray(task.artifacts) ? task.artifacts : []) {
        if (!artifact || typeof artifact !== 'object') continue;
        const artifactName = typeof artifact.name === 'string' ? artifact.name : '';

        if (artifactName.startsWith('node_error')) {
            const payload = firstDataPayload(artifact);
            const detail = payload && typeof payload === 'object' && typeof payload.error === 'string'
                ? payload.error
                : '';
            const label = policy.errors_display === 'detailed' && detail !== ''
                ? detail
                : flowUIText(locale, 'turn_toast_error_generic');
            errors.push({
                id: typeof artifact.artifactId === 'string' && artifact.artifactId !== ''
                    ? artifact.artifactId
                    : `error:${artifactName}`,
                kind: 'error',
                label,
                detail: policy.errors_display === 'detailed' ? detail : '',
                status: 'error',
            });
            continue;
        }

        let adapted;
        try {
            adapted = adaptCurrentArtifact(artifact);
        } catch {
            continue;
        }
        if (!adapted) continue;

        if (adapted.kind === 'tool_call' || adapted.kind === 'tool_result') {
            const payload = adapted.payload && typeof adapted.payload === 'object'
                ? adapted.payload
                : null;
            const toolName = toolNameFromPayload(payload, adapted.name, adapted.kind);
            const isSkillTool = toolName === 'load_agent_skill';
            if (isSkillTool) {
                if (!showSkills) continue;
            } else if (!showTools) {
                continue;
            }
            const callId = payload && typeof payload.tool_call_id === 'string' && payload.tool_call_id !== ''
                ? payload.tool_call_id
                : adapted.artifact_id;
            const kind = isSkillTool ? 'skill' : 'tool';
            const skillArg = payload?.args && typeof payload.args === 'object'
                ? payload.args.agent_skill_id
                : null;
            const labelFromArgs = kind === 'skill' && typeof skillArg === 'string' && skillArg.trim() !== ''
                ? skillArg.trim()
                : '';
            let detail = '';
            if (detailed && payload?.args && typeof payload.args === 'object') {
                detail = JSON.stringify(payload.args);
            } else if (adapted.kind === 'tool_result' && detailed && typeof payload?.result === 'string') {
                detail = payload.result.slice(0, 160);
            }
            const prev = byKey.get(callId);
            const status = adapted.kind === 'tool_result' ? 'done' : (prev?.status === 'done' ? 'done' : 'running');
            const label = labelFromArgs
                || (prev && typeof prev.label === 'string' && prev.label !== '' && prev.label !== toolName
                    ? prev.label
                    : toolName);
            byKey.set(callId, {
                id: callId,
                kind,
                label,
                detail: detail || prev?.detail || '',
                status,
            });
            continue;
        }

        if (adapted.kind === 'skill_activity') {
            if (!showSkills) continue;
            const payload = adapted.payload && typeof adapted.payload === 'object'
                ? adapted.payload
                : null;
            const label = skillLabelFromPayload(payload);
            byKey.set(adapted.artifact_id, {
                id: adapted.artifact_id,
                kind: 'skill',
                label,
                detail: '',
                status: 'done',
            });
        }
    }

    if (task.status?.state === 'TASK_STATE_FAILED') {
        const failedDetail = taskErrorText(task, policy, locale);
        if (!errors.some((item) => item.kind === 'error')) {
            errors.push({
                id: `task-error:${typeof task.id === 'string' ? task.id : 'unknown'}`,
                kind: 'error',
                label: failedDetail,
                detail: policy.errors_display === 'detailed' ? failedDetail : '',
                status: 'error',
            });
        }
    }

    // ask_user / auth interrupt: tool_call without tool_result is no longer in-flight.
    if (isSettledTaskState(task.status?.state)) {
        for (const item of byKey.values()) {
            if (item.status === 'running') {
                item.status = 'done';
            }
        }
    }

    return Object.freeze([
        ...Array.from(byKey.values()).map((item) => Object.freeze(item)),
        ...errors.map((item) => Object.freeze(item)),
    ]);
}

export function taskErrorText(task, policy, locale) {
    if (task.status?.state !== 'TASK_STATE_FAILED') {
        const nodeErrors = (Array.isArray(task.artifacts) ? task.artifacts : [])
            .filter((artifact) => artifact && typeof artifact === 'object'
                && typeof artifact.name === 'string'
                && artifact.name.startsWith('node_error'));
        if (nodeErrors.length > 0 && policy.errors_display === 'detailed') {
            const payload = firstDataPayload(nodeErrors[nodeErrors.length - 1]);
            if (payload && typeof payload === 'object' && typeof payload.error === 'string') {
                return payload.error;
            }
        }
        if (nodeErrors.length > 0) {
            return flowUIText(locale, 'turn_toast_error_generic');
        }
        return '';
    }
    if (policy.errors_display === 'detailed') {
        const message = task.status?.message;
        const detail = message && typeof message === 'object' ? textFromParts(message.parts) : '';
        if (detail !== '') return detail;
        const terminalError = typeof task.terminal_task_error === 'string' ? task.terminal_task_error : '';
        if (terminalError !== '') return terminalError;
        for (const artifact of Array.isArray(task.artifacts) ? task.artifacts : []) {
            if (!artifact || typeof artifact !== 'object') continue;
            if (typeof artifact.name !== 'string' || !artifact.name.startsWith('node_error')) continue;
            const payload = firstDataPayload(artifact);
            if (payload && typeof payload === 'object' && typeof payload.error === 'string') {
                return payload.error;
            }
        }
    }
    return flowUIText(locale, 'turn_toast_error_generic');
}

function resolveActiveTask(context) {
    if (!context || typeof context !== 'object') return null;
    const activeTaskId = typeof context.activeTaskId === 'string' ? context.activeTaskId : '';
    const tasksById = context.tasksById && typeof context.tasksById === 'object' ? context.tasksById : {};
    if (activeTaskId !== '' && tasksById[activeTaskId]) {
        return tasksById[activeTaskId];
    }
    const order = Array.isArray(context.taskOrder) ? context.taskOrder : [];
    for (let index = order.length - 1; index >= 0; index -= 1) {
        const task = tasksById[order[index]];
        if (task && typeof task === 'object') return task;
    }
    return null;
}

/**
 * @param {{
 *   document: object | null | undefined,
 *   context: object | null | undefined,
 *   locale: 'ru' | 'en',
 *   capabilities?: { cancel?: boolean } | null,
 * }} args
 * @returns {readonly {
 *   id: string,
 *   kind: 'working' | 'reasoning' | 'activity' | 'response' | 'error',
 *   title: string,
 *   body: string,
 *   streaming: boolean,
 *   dismissible: boolean,
 *   canCancel: boolean,
 * }[]}
 */
export function deriveTurnActivityToasts({ document, context, locale, capabilities = null }) {
    if (!document || typeof document !== 'object') return Object.freeze([]);
    if (hasConversationFeed(document)) return Object.freeze([]);

    const policy = resolveTurnActivityPolicy(document);
    const submitting = context?.submitting === true;
    const task = resolveActiveTask(context);
    if (!submitting && !task) return Object.freeze([]);

    const taskId = typeof task?.id === 'string' && task.id !== '' ? task.id : 'pending';
    const state = typeof task?.status?.state === 'string' ? task.status.state : '';
    const settled = state !== '' && isSettledTaskState(state);
    const failed = state === 'TASK_STATE_FAILED';
    const working = submitting || (task != null && !settled);
    const canCancel = policy.allow_cancel === true
        && capabilities?.cancel !== false
        && working
        && !failed;

    /** @type {{ id: string, kind: string, title: string, body: string, streaming: boolean, dismissible: boolean, canCancel: boolean }[]} */
    const toasts = [];

    if (failed) {
        toasts.push({
            id: `error:${taskId}`,
            kind: 'error',
            title: flowUIText(locale, 'turn_toast_error'),
            body: taskErrorText(task, policy, locale),
            streaming: false,
            dismissible: true,
            canCancel: false,
        });
    } else if (working) {
        toasts.push({
            id: `working:${taskId}`,
            kind: 'working',
            title: flowUIText(locale, 'turn_toast_working'),
            body: '',
            streaming: true,
            dismissible: false,
            canCancel,
        });
    }

    if (task && policy.show_reasoning === true) {
        const reasoning = taskReasoningText(task);
        if (reasoning !== '') {
            toasts.push({
                id: `reasoning:${taskId}`,
                kind: 'reasoning',
                title: flowUIText(locale, 'turn_toast_reasoning'),
                body: reasoning,
                streaming: !settled,
                dismissible: settled,
                canCancel: false,
            });
        }
    }

    if (task) {
        const activity = taskActivitySummary(task, policy);
        if (activity !== '') {
            toasts.push({
                id: `activity:${taskId}`,
                kind: 'activity',
                title: flowUIText(locale, 'turn_toast_activity'),
                body: activity,
                streaming: !settled,
                dismissible: settled,
                canCancel: false,
            });
        }
    }

    if (task) {
        const response = conversationTurnText(task);
        if (response !== '') {
            toasts.push({
                id: `response:${taskId}`,
                kind: 'response',
                title: flowUIText(locale, 'turn_toast_response'),
                body: response,
                streaming: !settled,
                dismissible: true,
                canCancel: false,
            });
        }
    }

    // Cap at 3: prefer error/response/working over reasoning/activity.
    const priority = { error: 0, response: 1, working: 2, reasoning: 3, activity: 4 };
    toasts.sort((left, right) => priority[left.kind] - priority[right.kind]);
    return Object.freeze(toasts.slice(0, 3).map((toast) => Object.freeze(toast)));
}

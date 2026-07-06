/**
 * Профиль поверхности чата и итоговый viewConfig.
 *
 * Профиль (`spa | editor_test | embed_public | embed_preview`) описывает
 * возможности точки монтирования; policy (`FlowConfig.chat`, приходит из
 * chat-profile endpoint) — что владелец flow разрешил показывать пользователю.
 * `resolveChatViewConfig(profile, chatPolicy)` = policy ∩ capabilities;
 * `editor_test` игнорирует policy и показывает всё. Невалидный вход — throw.
 */

export const CHAT_PROFILE_KINDS = Object.freeze(['spa', 'editor_test', 'embed_public', 'embed_preview']);

const TOOL_CALLS_DISPLAY_VALUES = Object.freeze(['hidden', 'compact', 'detailed']);
const ERRORS_DISPLAY_VALUES = Object.freeze(['generic', 'detailed']);

/**
 * Возможности точки монтирования по kind. Возможность = «умеет ли эта
 * поверхность физически показать элемент», policy решает «разрешено ли».
 */
const PROFILE_CAPABILITIES = Object.freeze({
    spa: Object.freeze({
        runTrace: true,
        traceActions: true,
        browserPreviews: true,
        filesPanel: true,
        cancel: true,
    }),
    editor_test: Object.freeze({
        runTrace: true,
        traceActions: true,
        browserPreviews: true,
        filesPanel: true,
        cancel: true,
    }),
    embed_public: Object.freeze({
        runTrace: false,
        traceActions: false,
        browserPreviews: true,
        filesPanel: true,
        cancel: true,
    }),
    embed_preview: Object.freeze({
        runTrace: false,
        traceActions: false,
        browserPreviews: true,
        filesPanel: true,
        cancel: true,
    }),
});

/**
 * @param {{ kind: string, capabilities?: object }} input
 * @returns {{ kind: string, capabilities: object }}
 */
export function createChatProfile(input) {
    if (!input || typeof input !== 'object') {
        throw new Error('chat-profile: input object required');
    }
    const kind = input.kind;
    if (!CHAT_PROFILE_KINDS.includes(kind)) {
        throw new Error(`chat-profile: unknown profile kind ${JSON.stringify(kind)}`);
    }
    const base = PROFILE_CAPABILITIES[kind];
    const overrides = input.capabilities && typeof input.capabilities === 'object' ? input.capabilities : {};
    for (const key of Object.keys(overrides)) {
        if (!(key in base)) {
            throw new Error(`chat-profile: unknown capability ${JSON.stringify(key)}`);
        }
        if (typeof overrides[key] !== 'boolean') {
            throw new Error(`chat-profile: capability ${key} must be boolean`);
        }
    }
    return Object.freeze({
        kind,
        capabilities: Object.freeze({ ...base, ...overrides }),
    });
}

function _boolPolicy(chatPolicy, field, defaultValue) {
    const value = chatPolicy[field];
    if (value === undefined || value === null) {
        return defaultValue;
    }
    if (typeof value !== 'boolean') {
        throw new Error(`chat-profile: policy field ${field} must be boolean`);
    }
    return value;
}

function _enumPolicy(chatPolicy, field, allowed, defaultValue) {
    const value = chatPolicy[field];
    if (value === undefined || value === null) {
        return defaultValue;
    }
    if (!allowed.includes(value)) {
        throw new Error(`chat-profile: policy field ${field} has invalid value ${JSON.stringify(value)}`);
    }
    return value;
}

function _greetingPolicy(chatPolicy) {
    const value = chatPolicy.greeting_message;
    if (value === undefined || value === null) {
        return null;
    }
    if (typeof value !== 'string') {
        throw new Error('chat-profile: policy field greeting_message must be string or null');
    }
    return value.trim() === '' ? null : value;
}

function _suggestedPromptsPolicy(chatPolicy) {
    const value = chatPolicy.suggested_prompts;
    if (value === undefined || value === null) {
        return Object.freeze([]);
    }
    if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) {
        throw new Error('chat-profile: policy field suggested_prompts must be string[]');
    }
    return Object.freeze(value.filter((item) => item.trim() !== ''));
}

/**
 * Итоговая конфигурация рендера чат-поверхности.
 *
 * @param {{ kind: string, capabilities: object }} profile — из createChatProfile
 * @param {object|null|undefined} chatPolicy — `FlowConfig.chat` (snake_case, из chat-profile endpoint);
 *   null/undefined — дефолтная policy (Pydantic defaults).
 */
export function resolveChatViewConfig(profile, chatPolicy) {
    if (!profile || typeof profile !== 'object' || !CHAT_PROFILE_KINDS.includes(profile.kind)) {
        throw new Error('chat-profile: profile from createChatProfile required');
    }
    if (chatPolicy !== undefined && chatPolicy !== null && typeof chatPolicy !== 'object') {
        throw new Error('chat-profile: chatPolicy must be object or null');
    }
    const policy = chatPolicy && typeof chatPolicy === 'object' ? chatPolicy : {};
    const caps = profile.capabilities;

    if (profile.kind === 'editor_test') {
        return Object.freeze({
            profileKind: profile.kind,
            showReasoning: true,
            toolCallsDisplay: 'detailed',
            showActivity: true,
            errorsDisplay: 'detailed',
            showRunTrace: true,
            showTraceActions: true,
            showBrowserPreviews: true,
            showFilesPanel: true,
            allowCancel: true,
            greetingMessage: _greetingPolicy(policy),
            suggestedPrompts: _suggestedPromptsPolicy(policy),
        });
    }

    const traceActionsPolicyDefault = profile.kind === 'spa';
    const showTraceActions = profile.kind === 'spa'
        ? caps.traceActions
        : caps.traceActions && _boolPolicy(policy, 'show_trace_actions', traceActionsPolicyDefault);
    return Object.freeze({
        profileKind: profile.kind,
        showReasoning: _boolPolicy(policy, 'show_reasoning', false),
        toolCallsDisplay: _enumPolicy(policy, 'tool_calls_display', TOOL_CALLS_DISPLAY_VALUES, 'compact'),
        showActivity: _boolPolicy(policy, 'show_activity', true),
        errorsDisplay: _enumPolicy(policy, 'errors_display', ERRORS_DISPLAY_VALUES, 'generic'),
        showRunTrace: caps.runTrace && _boolPolicy(policy, 'show_run_trace', false),
        showTraceActions,
        showBrowserPreviews: caps.browserPreviews && _boolPolicy(policy, 'show_browser_previews', true),
        showFilesPanel: caps.filesPanel && _boolPolicy(policy, 'show_files_panel', true),
        allowCancel: caps.cancel && _boolPolicy(policy, 'allow_cancel', true),
        greetingMessage: _greetingPolicy(policy),
        suggestedPrompts: _suggestedPromptsPolicy(policy),
    });
}

/**
 * Загрузка chat-profile с backend.
 *
 * @param {{
 *   baseUrl?: string,
 *   flowId?: string,
 *   embedId?: string,
 *   headers?: Record<string, string>,
 *   credentials?: RequestCredentials,
 *   signal?: AbortSignal,
 * }} options — flowId → GET /flows/api/v1/{flow_id}/chat-profile (session/API key);
 *   embedId → GET /flows/api/v1/embed/{embed_id}/chat-profile (embed session).
 * @returns {Promise<{ flow_id: string, branch_id: string, chat: object,
 *   viewer: { can_edit_flow: boolean }, look: object|null }>}
 */
export async function fetchChatProfile(options) {
    const baseUrl = typeof options.baseUrl === 'string' ? options.baseUrl.trim().replace(/\/$/, '') : '';
    const root = baseUrl !== '' ? baseUrl : '/flows';
    const embedId = typeof options.embedId === 'string' ? options.embedId.trim() : '';
    const flowId = typeof options.flowId === 'string' ? options.flowId.trim() : '';
    let url;
    if (embedId !== '') {
        url = `${root}/api/v1/embed/${encodeURIComponent(embedId)}/chat-profile`;
    } else if (flowId !== '') {
        url = `${root}/api/v1/${encodeURIComponent(flowId)}/chat-profile`;
    } else {
        throw new Error('chat-profile: flowId or embedId required');
    }
    const response = await fetch(url, {
        method: 'GET',
        headers: { Accept: 'application/json', ...(options.headers || {}) },
        credentials: options.credentials || 'include',
        signal: options.signal,
    });
    if (!response.ok) {
        throw new Error(`chat-profile: HTTP ${response.status} for ${url}`);
    }
    const profile = await response.json();
    if (!profile || typeof profile !== 'object' || !profile.chat || typeof profile.chat !== 'object') {
        throw new Error('chat-profile: response must contain chat policy object');
    }
    if (!profile.viewer || typeof profile.viewer !== 'object') {
        throw new Error('chat-profile: response must contain viewer object');
    }
    return profile;
}

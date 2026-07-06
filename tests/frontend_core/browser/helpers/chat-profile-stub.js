/**
 * Перехват GET …/chat-profile для изолированных browser-тестов platform-chat / chat-page.
 */

class MockResponse {
    constructor({ status = 200, headers = {}, body = null } = {}) {
        this.ok = status >= 200 && status < 300;
        this.status = status;
        this.headers = {
            get(name) {
                return headers[name.toLowerCase()] ?? null;
            },
        };
        this._body = body;
    }

    async text() {
        return typeof this._body === 'string' ? this._body : JSON.stringify(this._body || '');
    }

    async json() {
        return typeof this._body === 'string' ? JSON.parse(this._body) : this._body;
    }
}

const DEFAULT_CHAT_POLICY = Object.freeze({
    show_reasoning: false,
    tool_calls_display: 'compact',
    show_activity: true,
    errors_display: 'generic',
    show_run_trace: false,
    show_trace_actions: true,
    show_browser_previews: true,
    show_files_panel: true,
    allow_cancel: true,
    greeting_message: null,
    suggested_prompts: [],
});

/**
 * @param {{
 *   flowId?: string,
 *   embedId?: string,
 *   chatPolicy?: object|null,
 *   branchId?: string,
 *   look?: object|null,
 *   canEditFlow?: boolean,
 * }} options
 * @returns {() => void}
 */
export function installChatProfileFetchStub(options = {}) {
    const flowId = typeof options.flowId === 'string' ? options.flowId.trim() : 'demo_flow';
    const embedId = typeof options.embedId === 'string' ? options.embedId.trim() : '';
    const branchId = typeof options.branchId === 'string' ? options.branchId.trim() : 'default';
    const chatPolicy = options.chatPolicy === undefined ? DEFAULT_CHAT_POLICY : options.chatPolicy;
    const look = options.look === undefined ? null : options.look;
    const canEditFlow = options.canEditFlow !== false;
    const prevFetch = window.fetch;

    window.fetch = async (rawUrl, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const url = new URL(String(rawUrl), window.location.href);
        const isChatProfile = method === 'GET' && /\/chat-profile$/.test(url.pathname);
        if (!isChatProfile) {
            return prevFetch(rawUrl, init);
        }

        if (embedId !== '' && url.pathname.endsWith(`/embed/${encodeURIComponent(embedId)}/chat-profile`)) {
            return new MockResponse({
                status: 200,
                headers: { 'content-type': 'application/json' },
                body: {
                    flow_id: flowId,
                    branch_id: branchId,
                    chat: chatPolicy,
                    viewer: { can_edit_flow: canEditFlow },
                    look,
                },
            });
        }

        if (flowId !== '' && url.pathname.endsWith(`/${encodeURIComponent(flowId)}/chat-profile`)) {
            return new MockResponse({
                status: 200,
                headers: { 'content-type': 'application/json' },
                body: {
                    flow_id: flowId,
                    branch_id: branchId,
                    chat: chatPolicy,
                    viewer: { can_edit_flow: canEditFlow },
                    look,
                },
            });
        }

        return prevFetch(rawUrl, init);
    };

    return () => {
        window.fetch = prevFetch;
    };
}

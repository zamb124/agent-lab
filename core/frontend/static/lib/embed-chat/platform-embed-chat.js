import { LitElement, html, css, nothing } from 'lit';
import { streamEmbedA2A } from './embed-a2a-stream.js';
import {
    crmA2aInterfaceLanguageVariables,
    embedChatLabelsForLang,
} from './embed-chat-default-labels.js';
import { reduceEmbedStreamEvent } from './embed-stream-handler.js';
import { registerBuiltinEmbedBlocks } from './embed-builtin-blocks.js';
import './embed-block-renderer.js';
import './embed-chat-input.js';

let mid = 0;

/**
 * Автономный чат: A2A stream + блоки. Без apps/crm, apps/flows.
 *
 * Свойства:
 * - flowsBaseUrl, flowId, skillId
 * - title
 * - labels: { send, placeholder, newChat, greeting, ... }
 * - useCredentials: boolean (fetch credentials: include — cookie при том же site / см. хост)
 * - getAuthToken: async () => ({ Authorization?: 'Bearer ...' })
 * - actionHandlers: Record<string, (detail: object) => void>
 * - enableVoice: boolean
 * - embedTheme: 'light' | 'dark' (атрибут embed-theme)
 * - interfaceLocale: ru | en | auto — metadata.variables для A2A (язык ответа Lara/CRM)
 * - showLocaleControl: переключатель ru/en/auto в композере
 * - hideHeader: скрыть внутренний header (например когда заголовок и действия в drawer)
 */
export class PlatformEmbedChat extends LitElement {
    static properties = {
        flowsBaseUrl: { type: String, attribute: 'flows-base-url' },
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
        title: { type: String },
        labels: { type: Object },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        embedTheme: { type: String, attribute: 'embed-theme' },
        interfaceLocale: { type: String, attribute: 'interface-locale' },
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        hideHeader: { type: Boolean, attribute: 'hide-header' },
        greetingSent: { type: Boolean, state: true },
    };

    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            height: 100%;
            min-height: 200px;
            font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
            --embed-radius: 25px;
            --embed-chat-text: rgba(255, 255, 255, 0.92);
            --embed-chat-muted: rgba(255, 255, 255, 0.52);
            --embed-chat-border: rgba(255, 255, 255, 0.11);
            --embed-chat-surface: rgba(255, 255, 255, 0.07);
            --embed-chat-accent: #99a6f9;
            --embed-chat-on-accent: #0f0f12;
            --embed-chat-accent-muted: rgba(153, 166, 249, 0.28);
            --embed-chat-input-bg: rgba(0, 0, 0, 0.22);
            --embed-chat-composer-bg: rgba(255, 255, 255, 0.06);
            --embed-chat-panel-bg: transparent;
            --embed-chat-interrupt-bg: rgba(153, 166, 249, 0.1);
            color: var(--embed-chat-text);
            background: var(--embed-chat-panel-bg);
            border-radius: 0;
            border: none;
            overflow: hidden;
        }
        :host([embed-theme='light']) {
            --embed-chat-text: #1c1f2e;
            --embed-chat-muted: rgba(28, 31, 46, 0.52);
            --embed-chat-border: rgba(28, 31, 46, 0.1);
            --embed-chat-surface: rgba(28, 31, 46, 0.05);
            --embed-chat-accent: #6d62e8;
            --embed-chat-on-accent: #ffffff;
            --embed-chat-accent-muted: rgba(109, 98, 232, 0.2);
            --embed-chat-input-bg: rgba(255, 255, 255, 0.92);
            --embed-chat-composer-bg: #f2f3f8;
            --embed-chat-interrupt-bg: rgba(109, 98, 232, 0.1);
        }
        header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 4px 4px 12px 8px;
            border-bottom: 1px solid var(--embed-chat-border);
            font-weight: 600;
            font-size: 15px;
            border-radius: 0;
        }
        .scroll {
            flex: 1;
            min-height: 0;
            overflow-y: auto;
            padding: 12px 4px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }
        .msg {
            max-width: 92%;
            padding: 12px 14px;
            border-radius: var(--embed-radius);
            font-size: 14px;
            line-height: 1.45;
        }
        .msg.user {
            align-self: flex-end;
            background: var(--embed-chat-accent-muted);
        }
        .msg.assistant {
            align-self: flex-start;
            background: var(--embed-chat-surface);
            border: 1px solid var(--embed-chat-border);
        }
        .meta {
            font-size: 11px;
            color: var(--embed-chat-muted);
            margin-bottom: 4px;
        }
        .tools {
            font-size: 11px;
            color: var(--embed-chat-muted);
            margin-top: 8px;
        }
        .interrupt {
            margin-top: 10px;
            padding: 12px 14px;
            border-radius: var(--embed-radius);
            border: 1px solid var(--embed-chat-accent);
            background: var(--embed-chat-interrupt-bg);
        }
        button.link {
            background: transparent;
            border: none;
            color: var(--embed-chat-accent);
            cursor: pointer;
            font-size: 13px;
            padding: 0;
            border-radius: var(--embed-radius);
        }
    `;

    constructor() {
        super();
        this.flowsBaseUrl = '';
        this.flowId = '';
        this.skillId = '';
        this.title = 'Assistant';
        this.labels = {};
        this.useCredentials = false;
        this.enableVoice = true;
        this.embedTheme = 'dark';
        this.interfaceLocale = 'auto';
        this.showLocaleControl = false;
        this.hideHeader = false;
        this.getAuthToken = undefined;
        this.actionHandlers = {};
        /** @type {Array<object>} */
        this._messages = [];
        this._loading = false;
        this._contextId = `${Date.now()}`;
        this._currentTaskId = null;
        this.greetingSent = false;
        registerBuiltinEmbedBlocks();
    }

    _langForUiLabels() {
        const il = String(this.interfaceLocale || '').trim().toLowerCase();
        const primary = il.split(/[-_]/)[0];
        if (primary === 'en') {
            return 'en';
        }
        if (primary === 'ru') {
            return 'ru';
        }
        const doc = String(document.documentElement.lang || '').trim().toLowerCase();
        return doc.startsWith('en') ? 'en' : 'ru';
    }

    _mergedLabels() {
        const base = embedChatLabelsForLang(this._langForUiLabels());
        const extra = this.labels && typeof this.labels === 'object' ? this.labels : {};
        return { ...base, ...extra };
    }

    _lb(key, fb) {
        const L = this._mergedLabels();
        return L[key] != null && L[key] !== '' ? L[key] : fb;
    }

    _onEmbedLocaleChange(e) {
        const loc = e.detail?.locale;
        if (loc !== 'auto' && loc !== 'ru' && loc !== 'en') {
            return;
        }
        this.interfaceLocale = loc;
        this.requestUpdate();
    }

    connectedCallback() {
        super.connectedCallback();
        this.addEventListener('embed-block-action', this._onBlockAction);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('embed-block-action', this._onBlockAction);
    }

    _onBlockAction = (e) => {
        const { action_id: actionId, payload } = e.detail || {};
        if (!actionId || typeof actionId !== 'string') {
            return;
        }
        const fn = this.actionHandlers[actionId];
        if (typeof fn === 'function') {
            fn(payload || {});
        }
    };

    async firstUpdated() {
        if (this.greetingSent) {
            return;
        }
        const g = this._lb('greeting', '');
        if (g) {
            this._messages = [
                {
                    id: `sys_${++mid}`,
                    role: 'assistant',
                    content: g,
                    blocks: [],
                    toolCalls: [],
                    toolResults: [],
                },
            ];
            this.greetingSent = true;
            this.requestUpdate();
        }
    }

    _fileToBase64Part(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const base64 = reader.result.split(',')[1];
                resolve({
                    kind: 'file',
                    name: file.name,
                    mimeType: file.type,
                    data: base64,
                });
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    async _onSend(e) {
        const { message, files = [] } = e.detail;
        if ((!message && files.length === 0) || this._loading) {
            return;
        }
        if (!this.flowsBaseUrl || !this.flowId) {
            throw new Error('flowsBaseUrl and flowId are required');
        }

        const fileParts = await Promise.all(files.map((f) => this._fileToBase64Part(f)));

        this._messages = [
            ...this._messages,
            {
                id: `u_${++mid}`,
                role: 'user',
                content: message,
                filesMeta: files.map((f) => ({ name: f.name, size: f.size })),
            },
        ];

        const assistantMsg = {
            id: `a_${++mid}`,
            role: 'assistant',
            content: '',
            streaming: true,
            reasoning: '',
            toolCalls: [],
            toolResults: [],
            blocks: [],
            inputRequired: null,
            breakpoint: null,
        };
        this._messages = [...this._messages, assistantMsg];
        this._loading = true;
        this.requestUpdate();

        const getHeaders = async () => {
            if (typeof this.getAuthToken !== 'function') {
                return {};
            }
            const h = await this.getAuthToken();
            return h && typeof h === 'object' ? h : {};
        };

        const langVars = crmA2aInterfaceLanguageVariables(this.interfaceLocale);

        try {
            await streamEmbedA2A(
                {
                    baseUrl: this.flowsBaseUrl,
                    flowId: this.flowId,
                    message,
                    contextId: this._contextId,
                    skillId: this.skillId || null,
                    files: fileParts,
                    metadata: { variables: { ...langVars } },
                    getHeaders,
                    credentials: this.useCredentials ? 'include' : 'omit',
                },
                (event) => this._handleEvent(event, assistantMsg.id),
            );
        } catch (err) {
            const m = err instanceof Error ? err.message : String(err);
            this._patchMessage(assistantMsg.id, { content: m, streaming: false });
        }

        this._loading = false;
        this.requestUpdate();
    }

    _findMessage(id) {
        return this._messages.find((m) => m.id === id);
    }

    _patchMessage(id, patch) {
        this._messages = this._messages.map((m) => (m.id === id ? { ...m, ...patch } : m));
        this.requestUpdate();
    }

    _handleEvent(event, messageId) {
        const msg = this._findMessage(messageId);
        if (!msg) {
            return;
        }
        const reduced = reduceEmbedStreamEvent(msg, event);
        if (reduced.currentTaskId) {
            this._currentTaskId = reduced.currentTaskId;
        }
        if (reduced.contextId) {
            this._contextId = reduced.contextId;
        }
        if (reduced.taskId) {
            this._currentTaskId = reduced.taskId;
        }
        const patch = reduced.patch;
        if (patch && Object.keys(patch).length > 0) {
            const merged = { ...msg, ...patch };
            this._messages = this._messages.map((m) => (m.id === messageId ? merged : m));
        }
        this.requestUpdate();
    }

    _newChat() {
        this._contextId = `${Date.now()}`;
        const g = this._lb('greeting', '');
        this._messages = g
            ? [
                  {
                      id: `sys_${++mid}`,
                      role: 'assistant',
                      content: g,
                      blocks: [],
                      toolCalls: [],
                      toolResults: [],
                  },
              ]
            : [];
        this.greetingSent = Boolean(g);
        this.requestUpdate();
    }

    /** Сброс диалога; вызывается с хоста (drawer) при скрытом внутреннем header. */
    startNewChat() {
        this._newChat();
    }

    render() {
        const head = this.hideHeader
            ? nothing
            : html`
                  <header>
                      <span>${this.title}</span>
                      <button type="button" class="link" @click=${this._newChat}>
                          ${this._lb('new_chat', 'New chat')}
                      </button>
                  </header>
              `;
        return html`
            ${head}
            <div class="scroll">
                ${this._messages.map((m) => this._renderMessage(m))}
            </div>
            <embed-chat-input
                ?loading=${this._loading}
                placeholder=${this._lb('placeholder', 'Message...')}
                .labels=${this._mergedLabels()}
                ?enable-voice=${this.enableVoice}
                ?show-locale-control=${this.showLocaleControl}
                interface-locale=${this.interfaceLocale || 'auto'}
                @embed-locale-change=${this._onEmbedLocaleChange}
                @embed-send=${this._onSend}
            ></embed-chat-input>
        `;
    }

    _renderMessage(m) {
        if (m.role === 'user') {
            const files =
                m.filesMeta && m.filesMeta.length
                    ? html`<div class="meta">${m.filesMeta.map((f) => f.name).join(', ')}</div>`
                    : nothing;
            return html`
                <div class="msg user">
                    ${files}
                    ${m.content || ''}
                </div>
            `;
        }
        const tools =
            m.toolCalls && m.toolCalls.length
                ? html`<div class="tools">${m.toolCalls.map((t) => t.name || t.function?.name || 'tool').join(', ')}</div>`
                : nothing;
        const blocks = (m.blocks || []).map(
            (b) => html`<embed-block-renderer .block=${b}></embed-block-renderer>`,
        );
        const interrupt = m.inputRequired
            ? html`
                  <div class="interrupt">
                      <div>${m.inputRequired.question || ''}</div>
                  </div>
              `
            : nothing;
        return html`
            <div class="msg assistant">
                <div style="white-space: pre-wrap;">${m.content || ''}${m.streaming ? ' ...' : ''}</div>
                ${interrupt}
                ${blocks}
                ${tools}
            </div>
        `;
    }
}

customElements.define('platform-embed-chat', PlatformEmbedChat);

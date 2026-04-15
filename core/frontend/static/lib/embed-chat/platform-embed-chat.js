import { LitElement, html, css, nothing } from './lit-shim.js';
import { unsafeHTML } from './unsafe-html-shim.js';
import { streamEmbedA2A } from './embed-a2a-stream.js';
import { embedAssistantMarkdownToHtml } from './embed-chat-markdown.js';
import {
    normalizeEmbedBlockForFlowsUrls,
    rewriteFlowsFileUrlsInHtml,
} from './embed-flows-url-rewrite.js';
import {
    crmA2aInterfaceLanguageVariables,
    embedChatLabelsForLang,
} from './embed-chat-default-labels.js';
import { reduceEmbedStreamEvent } from './embed-stream-handler.js';
import { registerBuiltinEmbedBlocks } from './embed-builtin-blocks.js';
import './embed-block-renderer.js';
import './embed-chat-input.js';

let mid = 0;
const ASSISTANT_EVENT_SCHEMA_VERSION = '1.0.0';

/**
 * Автономный чат: A2A stream + блоки. Без apps/crm, apps/flows.
 *
 * Свойства:
 * - flowsBaseUrl, flowId, embedId, skillId (embedId приоритетен для внешнего embed-route)
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
 * - getExtraMetadataVariables: async () => Record<string, unknown> — доп. ключи в metadata.variables (мёрж после языка)
 * - getContextVariables: async () => Record<string, unknown> — контекст экрана/сущности для ассистента (мёрж после getExtraMetadataVariables)
 * - eventNamespace: префикс событий для внешнего хоста (по умолчанию assistant)
 * - assistantTitle (assistant-title): имя в шапке; иначе title; иначе labels.title из локали (?embed_assistant_name= на странице — см. drawer)
 *
 * Событие (после завершения стрима ответа на отправку пользователя): **`humanitec-embed-chat-assistant-reply-completed`**, bubbles + composed — для счётчика на FAB drawer.
 */
export class PlatformEmbedChat extends LitElement {
    static properties = {
        flowsBaseUrl: { type: String, attribute: 'flows-base-url' },
        flowId: { type: String, attribute: 'flow-id' },
        embedId: { type: String, attribute: 'embed-id' },
        skillId: { type: String, attribute: 'skill-id' },
        title: { type: String },
        assistantTitle: { type: String, attribute: 'assistant-title' },
        labels: { type: Object },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        embedTheme: { type: String, attribute: 'embed-theme' },
        interfaceLocale: { type: String, attribute: 'interface-locale' },
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        hideHeader: { type: Boolean, attribute: 'hide-header' },
        visible: { type: Boolean, reflect: true },
        eventNamespace: { type: String, attribute: 'event-namespace' },
        eventAckRetries: { type: Number, attribute: 'event-ack-retries' },
        eventAckTimeoutMs: { type: Number, attribute: 'event-ack-timeout-ms' },
        getExtraMetadataVariables: { type: Object },
        getContextVariables: { type: Object },
        greetingSent: { type: Boolean, state: true },
        _credentials: { state: true },
        _credPopover: { state: true },
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
        .interrupt-banner {
            font-size: 12px;
            color: var(--embed-chat-muted);
            margin-bottom: 8px;
        }
        .embed-oauth-link {
            display: inline-block;
            margin-top: 8px;
            padding: 6px 16px;
            background: var(--embed-chat-accent, #4285f4);
            color: #fff;
            border-radius: 6px;
            text-decoration: none;
            font-size: 13px;
            font-weight: 500;
            transition: opacity 0.15s;
        }
        .embed-oauth-link:hover {
            opacity: 0.85;
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
        .embed-msg-md {
            color: inherit;
            overflow-wrap: anywhere;
            word-break: break-word;
            max-width: 100%;
        }
        .embed-msg-md > :first-child {
            margin-top: 0;
        }
        .embed-msg-md > :last-child {
            margin-bottom: 0;
        }
        .embed-msg-md p,
        .embed-msg-md ul,
        .embed-msg-md ol,
        .embed-msg-md blockquote,
        .embed-msg-md pre,
        .embed-msg-md h1,
        .embed-msg-md h2,
        .embed-msg-md h3,
        .embed-msg-md h4 {
            margin: 0 0 10px 0;
        }
        .embed-msg-md ul,
        .embed-msg-md ol {
            padding-left: 1.25rem;
        }
        .embed-msg-md a {
            color: var(--embed-chat-accent);
        }
        .embed-msg-md code {
            background: var(--embed-chat-composer-bg);
            border-radius: 6px;
            padding: 1px 5px;
            font-size: 0.92em;
        }
        .embed-msg-md pre {
            background: var(--embed-chat-input-bg);
            border: 1px solid var(--embed-chat-border);
            border-radius: 10px;
            padding: 10px;
            overflow: auto;
        }
        .embed-msg-md pre code {
            background: transparent;
            border: 0;
            padding: 0;
        }
        .embed-msg-md table {
            border-collapse: collapse;
            width: 100%;
            margin: 0 0 10px 0;
            font-size: 13px;
        }
        .embed-msg-md th,
        .embed-msg-md td {
            border: 1px solid var(--embed-chat-border);
            padding: 6px 8px;
        }
        .embed-stream-dots {
            color: var(--embed-chat-muted);
        }
        .embed-stream-caret {
            display: inline-block;
            margin-left: 2px;
            color: var(--embed-chat-muted);
            animation: embed-caret-blink 1s steps(1, end) infinite;
        }
        @keyframes embed-caret-blink {
            0%,
            49% {
                opacity: 1;
            }
            50%,
            100% {
                opacity: 0;
            }
        }
        .embed-operator-reply {
            margin-top: 12px;
            padding: 10px 12px;
            border-radius: 12px;
            border: 1px solid var(--embed-chat-border);
            background: var(--embed-chat-interrupt-bg);
        }
        .embed-operator-reply-label {
            font-size: 12px;
            font-weight: 600;
            color: var(--embed-chat-muted);
            margin-bottom: 6px;
        }
        .embed-file-card {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            margin-top: 6px;
            padding: 2px 0;
            font-size: 12px;
            color: var(--embed-chat-accent, #3b82f6);
            text-decoration: none;
            cursor: pointer;
        }
        .embed-file-card:hover {
            text-decoration: underline;
        }
        .embed-cred-badges {
            position: absolute;
            top: 8px;
            right: 8px;
            z-index: 5;
            display: flex;
            gap: 4px;
            pointer-events: all;
        }
        .embed-cred-anchor {
            position: relative;
        }
        .embed-cred-badge {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 600;
            color: #fff;
            cursor: pointer;
            border: none;
            padding: 0;
            transition: transform 0.15s ease, box-shadow 0.15s ease;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
        }
        .embed-cred-badge:hover {
            transform: scale(1.15);
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
        }
        .embed-cred-popover {
            position: absolute;
            top: calc(100% + 6px);
            right: 0;
            min-width: 160px;
            background: var(--embed-chat-surface, rgba(30, 30, 40, 0.95));
            border: 1px solid var(--embed-chat-border);
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            z-index: 100;
        }
        .embed-cred-popover-title {
            font-size: 13px;
            font-weight: 500;
            color: var(--embed-chat-text);
        }
        .embed-cred-disconnect {
            background: none;
            border: 1px solid #e53935;
            color: #e53935;
            border-radius: 4px;
            padding: 4px 12px;
            font-size: 12px;
            cursor: pointer;
            transition: background 0.15s ease, color 0.15s ease;
        }
        .embed-cred-disconnect:hover {
            background: #e53935;
            color: #fff;
        }
        .embed-chat-content {
            position: relative;
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
        }
    `;

    constructor() {
        super();
        this.flowsBaseUrl = '';
        this.flowId = '';
        this.embedId = '';
        this.skillId = '';
        this.title = '';
        this.assistantTitle = '';
        this.labels = {};
        this.useCredentials = false;
        this.enableVoice = true;
        this.embedTheme = 'dark';
        this.interfaceLocale = 'auto';
        this.showLocaleControl = false;
        this.hideHeader = false;
        this.visible = true;
        this.eventNamespace = 'assistant';
        this.eventAckRetries = 0;
        this.eventAckTimeoutMs = 2500;
        this.getContextVariables = undefined;
        this.getAuthToken = undefined;
        this.actionHandlers = {};
        /** @type {Array<object>} */
        this._messages = [];
        this._loading = false;
        this._sseOpen = false;
        this._contextId = `${Date.now()}`;
        this._currentTaskId = null;
        this.greetingSent = false;
        /** Пользователь у низа — продолжаем автопрокрутку при новых кусках ответа */
        this._stickToBottom = true;
        /** После отправки пользователя ждём завершения стрима — для счётчика на FAB drawer. */
        this._pendingAssistantReplyNotify = false;
        /** @type {Array<{provider:string, service:string}>} */
        this._credentials = [];
        this._credPopover = null;
        this._uiEventDispatchKeys = new Set();
        this._greetingTypingRunId = 0;
        this._pendingEventAcks = new Map();
        this._boundAckListener = (event) => this._handleHostEventAck(event, true);
        this._boundNackListener = (event) => this._handleHostEventAck(event, false);
        this._ackEventName = null;
        this._nackEventName = null;
        this._onCredClickOutside = this._onCredClickOutside.bind(this);
        registerBuiltinEmbedBlocks();
    }

    static _SCROLL_STICK_PX = 56;

    _onScrollAreaScroll = (e) => {
        const el = e.currentTarget;
        if (!(el instanceof HTMLElement)) {
            return;
        }
        const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
        this._stickToBottom = gap <= PlatformEmbedChat._SCROLL_STICK_PX;
    };

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

    _headDisplayTitle() {
        const a = this.assistantTitle != null ? String(this.assistantTitle).trim() : '';
        if (a) {
            return a;
        }
        const t = this.title != null ? String(this.title).trim() : '';
        if (t) {
            return t;
        }
        return this._lb('title', 'Assistant');
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
        document.addEventListener('click', this._onCredClickOutside);
        this._bindAckListeners();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('embed-block-action', this._onBlockAction);
        document.removeEventListener('click', this._onCredClickOutside);
        this._unbindAckListeners();
        this._pendingEventAcks.forEach((pending) => {
            if (pending.timer) {
                clearTimeout(pending.timer);
            }
        });
        this._pendingEventAcks.clear();
    }

    _bindAckListeners() {
        this._unbindAckListeners();
        const ns = this._normalizedEventNamespace();
        this._ackEventName = `${ns}:ack`;
        this._nackEventName = `${ns}:nack`;
        window.addEventListener(this._ackEventName, this._boundAckListener);
        window.addEventListener(this._nackEventName, this._boundNackListener);
    }

    _unbindAckListeners() {
        if (this._ackEventName) {
            window.removeEventListener(this._ackEventName, this._boundAckListener);
        }
        if (this._nackEventName) {
            window.removeEventListener(this._nackEventName, this._boundNackListener);
        }
        this._ackEventName = null;
        this._nackEventName = null;
    }

    _handleHostEventAck(event, accepted) {
        const detail = event?.detail && typeof event.detail === 'object' ? event.detail : {};
        const eventId = typeof detail.id === 'string' ? detail.id.trim() : '';
        if (!eventId) {
            return;
        }
        const pending = this._pendingEventAcks.get(eventId);
        if (!pending) {
            return;
        }
        if (pending.timer) {
            clearTimeout(pending.timer);
        }
        this._pendingEventAcks.delete(eventId);
        if (!accepted && pending.retriesLeft > 0) {
            this._dispatchAssistantEnvelope(pending.envelope, pending.retriesLeft - 1);
        }
    }

    _onBlockAction = (e) => {
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        const actionId = typeof detail.action_id === 'string' ? detail.action_id.trim() : '';
        const actionKind = typeof detail.action_kind === 'string' ? detail.action_kind.trim() : '';
        if (!actionId || !actionKind) {
            return;
        }
        const payload = {
            action_id: actionId,
            action_kind: actionKind,
            pending_action_id:
                typeof detail.pending_action_id === 'string' && detail.pending_action_id.trim()
                    ? detail.pending_action_id.trim()
                    : null,
            arguments:
                detail.arguments && typeof detail.arguments === 'object' && !Array.isArray(detail.arguments)
                    ? detail.arguments
                    : {},
            context:
                detail.context && typeof detail.context === 'object' && !Array.isArray(detail.context)
                    ? detail.context
                    : {},
        };
        this._emitAssistantEvent('action_invoked', payload);
        const fn = this.actionHandlers['assistant:action_invoked'];
        if (typeof fn === 'function') {
            fn(payload);
        }
    };

    _normalizedEventNamespace() {
        const raw = typeof this.eventNamespace === 'string' ? this.eventNamespace.trim() : '';
        return raw || 'assistant';
    }

    _newEventId() {
        return `${Date.now()}-${Math.random().toString(16).slice(2)}-${mid++}`;
    }

    _buildAssistantEnvelope(type, payload = {}, overrides = {}) {
        const eventNamespace = this._normalizedEventNamespace();
        const envelope = {
            version: ASSISTANT_EVENT_SCHEMA_VERSION,
            id: typeof overrides.id === 'string' && overrides.id.trim() ? overrides.id.trim() : this._newEventId(),
            type,
            source:
                typeof overrides.source === 'string' && overrides.source.trim()
                    ? overrides.source.trim()
                    : eventNamespace,
            correlation_id:
                typeof overrides.correlation_id === 'string' && overrides.correlation_id.trim()
                    ? overrides.correlation_id.trim()
                    : null,
            timestamp: new Date().toISOString(),
            payload,
        };
        return envelope;
    }

    _dispatchAssistantEnvelope(detail, retriesLeft = null) {
        const eventNamespace = this._normalizedEventNamespace();
        this.dispatchEvent(
            new CustomEvent(`${eventNamespace}:event`, {
                bubbles: true,
                composed: true,
                detail,
            }),
        );
        this.dispatchEvent(
            new CustomEvent(`${eventNamespace}:${detail.type}`, {
                bubbles: true,
                composed: true,
                detail,
            }),
        );
        const totalRetries = Number.isInteger(this.eventAckRetries) ? this.eventAckRetries : 0;
        const timeoutMs = Number.isInteger(this.eventAckTimeoutMs) ? this.eventAckTimeoutMs : 2500;
        const nextRetries = retriesLeft == null ? totalRetries : retriesLeft;
        if (nextRetries <= 0) {
            return;
        }
        const timer = setTimeout(() => {
            const pending = this._pendingEventAcks.get(detail.id);
            if (!pending) {
                return;
            }
            this._pendingEventAcks.delete(detail.id);
            this._dispatchAssistantEnvelope(detail, pending.retriesLeft - 1);
        }, timeoutMs);
        this._pendingEventAcks.set(detail.id, { envelope: detail, retriesLeft: nextRetries, timer });
    }

    _emitAssistantEvent(type, payload = {}) {
        const detail = this._buildAssistantEnvelope(type, payload);
        this._dispatchAssistantEnvelope(detail);
    }

    _uiEventDispatchKey(uiEvent, index, messageId) {
        const eventId =
            uiEvent.id != null && String(uiEvent.id).trim() ? String(uiEvent.id).trim() : `idx:${index}`;
        const eventType = String(uiEvent.type || '').trim();
        const payload = uiEvent.payload && typeof uiEvent.payload === 'object' ? uiEvent.payload : {};
        return `${messageId || 'no-message'}|${eventType}|${eventId}|${JSON.stringify(payload)}`;
    }

    _emitUiEvents(uiEvents, messageId) {
        if (!Array.isArray(uiEvents) || uiEvents.length === 0) {
            return;
        }
        this._mergeBlocksFromUiEvents(uiEvents, messageId);
        uiEvents.forEach((uiEvent, index) => {
            if (!uiEvent || typeof uiEvent !== 'object') {
                return;
            }
            const type = typeof uiEvent.type === 'string' ? uiEvent.type.trim() : '';
            if (!type) {
                return;
            }
            const dedupeKey = this._uiEventDispatchKey(uiEvent, index, messageId);
            if (this._uiEventDispatchKeys.has(dedupeKey)) {
                return;
            }
            this._uiEventDispatchKeys.add(dedupeKey);
            const payload = uiEvent.payload && typeof uiEvent.payload === 'object' ? uiEvent.payload : {};
            const detail = this._buildAssistantEnvelope(type, payload, {
                id: uiEvent.id || null,
                source: uiEvent.source || null,
                correlation_id: uiEvent.correlation_id || null,
            });
            this._dispatchAssistantEnvelope(detail);
        });
    }

    _mergeBlocksFromUiEvents(uiEvents, messageId) {
        const msg = this._findMessage(messageId);
        if (!msg) {
            return;
        }
        const currentBlocks = Array.isArray(msg.blocks) ? msg.blocks : [];
        let nextBlocks = currentBlocks;
        let changed = false;
        for (const uiEvent of uiEvents) {
            if (!uiEvent || typeof uiEvent !== 'object') {
                continue;
            }
            const payload = uiEvent.payload && typeof uiEvent.payload === 'object' ? uiEvent.payload : {};
            const payloadBlocks = Array.isArray(payload.blocks) ? payload.blocks : [];
            if (payloadBlocks.length === 0) {
                continue;
            }
            const validBlocks = payloadBlocks.filter(
                (b) => b && typeof b === 'object' && typeof b.type === 'string' && b.type.trim(),
            );
            if (validBlocks.length === 0) {
                continue;
            }
            nextBlocks = nextBlocks.concat(validBlocks);
            changed = true;
        }
        if (changed) {
            this._patchMessage(messageId, { blocks: nextBlocks });
        }
    }

    async _getEmbedAuthHeaders() {
        if (typeof this.getAuthToken !== 'function') {
            return {};
        }
        const h = await this.getAuthToken();
        return h && typeof h === 'object' ? h : {};
    }

    async _loadEmbedCredentials() {
        if (!this.flowsBaseUrl || !this.useCredentials) {
            return;
        }
        if (typeof this.getAuthToken === 'function') {
            return;
        }
        const headers = await this._getEmbedAuthHeaders();
        const resp = await fetch(`${this.flowsBaseUrl}/api/v1/integrations/credentials`, {
            headers,
            credentials: this.useCredentials ? 'include' : 'omit',
        });
        if (!resp.ok) {
            return;
        }
        this._credentials = await resp.json();
    }

    async _deleteEmbedCredential(provider, service) {
        if (!this.flowsBaseUrl || !this.useCredentials) {
            return;
        }
        if (typeof this.getAuthToken === 'function') {
            return;
        }
        const headers = await this._getEmbedAuthHeaders();
        await fetch(
            `${this.flowsBaseUrl}/api/v1/integrations/credentials/${encodeURIComponent(provider)}/${encodeURIComponent(service)}`,
            {
                method: 'DELETE',
                headers,
                credentials: this.useCredentials ? 'include' : 'omit',
            },
        );
        this._credentials = this._credentials.filter(
            (c) => !(c.provider === provider && c.service === service),
        );
        this._credPopover = null;
    }

    _onCredClickOutside(e) {
        if (this._credPopover !== null && !e.composedPath().includes(this)) {
            this._credPopover = null;
        }
    }

    _toggleCredPopover(key, e) {
        e.stopPropagation();
        this._credPopover = this._credPopover === key ? null : key;
    }

    async firstUpdated() {
        this._loadEmbedCredentials();
        this._startGreetingTypingIfNeeded();
    }

    _startGreetingTypingIfNeeded() {
        if (this.greetingSent || !this.visible) {
            return;
        }
        const greetingText = this._lb('greeting', '');
        if (!greetingText) {
            return;
        }
        this.greetingSent = true;
        this._stickToBottom = true;
        void this._animateGreetingTyping(greetingText);
    }

    async _animateGreetingTyping(text) {
        const greetingText = typeof text === 'string' ? text : '';
        if (!greetingText) {
            return;
        }
        const runId = ++this._greetingTypingRunId;
        const messageId = `sys_${++mid}`;
        this._messages = [
            {
                id: messageId,
                role: 'assistant',
                content: '',
                blocks: [],
                toolCalls: [],
                toolResults: [],
                streaming: true,
            },
        ];
        this.requestUpdate();

        const chunkSize = 3;
        const delayMs = 14;
        for (let cursor = 0; cursor < greetingText.length; cursor += chunkSize) {
            if (runId !== this._greetingTypingRunId) {
                return;
            }
            const content = greetingText.slice(0, cursor + chunkSize);
            this._patchMessage(messageId, { content, streaming: true });
            await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
        if (runId !== this._greetingTypingRunId) {
            return;
        }
        this._patchMessage(messageId, { content: greetingText, streaming: false });
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('visible')) {
            this._startGreetingTypingIfNeeded();
        }
        if (changed.has('eventNamespace')) {
            this._bindAckListeners();
        }
        if (!this._stickToBottom) {
            return;
        }
        const run = () => {
            const el = this.renderRoot?.querySelector('.scroll');
            if (el instanceof HTMLElement) {
                el.scrollTop = el.scrollHeight;
            }
        };
        requestAnimationFrame(() => {
            requestAnimationFrame(run);
        });
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
        if (this._sseOpen) {
            return;
        }
        if (!this.flowsBaseUrl || (!this.flowId && !this.embedId)) {
            throw new Error('flowsBaseUrl and (flowId or embedId) are required');
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
            operatorReply: '',
            toolCalls: [],
            toolResults: [],
            blocks: [],
            inputRequired: null,
            breakpoint: null,
        };
        this._messages = [...this._messages, assistantMsg];
        this._activeStreamMessageId = assistantMsg.id;
        this._loading = true;
        this._sseOpen = true;
        this._pendingAssistantReplyNotify = true;
        this._stickToBottom = true;
        this.requestUpdate();

        const getHeaders = async () => {
            if (typeof this.getAuthToken !== 'function') {
                return {};
            }
            const h = await this.getAuthToken();
            return h && typeof h === 'object' ? h : {};
        };

        const langVars = crmA2aInterfaceLanguageVariables(this.interfaceLocale);
        let extraVars = {};
        if (typeof this.getExtraMetadataVariables === 'function') {
            const raw = await this.getExtraMetadataVariables();
            if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
                extraVars = raw;
            }
        }
        let contextVars = {};
        if (typeof this.getContextVariables === 'function') {
            const raw = await this.getContextVariables();
            if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
                contextVars = raw;
            }
        }
        const variables = { ...langVars, ...extraVars, ...contextVars };
        this._emitAssistantEvent('context_requested', {
            flow_id: this.flowId || null,
            skill_id: this.skillId || null,
            embed_id: this.embedId || null,
            variables,
        });

        try {
            await streamEmbedA2A(
                {
                    baseUrl: this.flowsBaseUrl,
                    flowId: this.flowId,
                    embedId: this.embedId || null,
                    message,
                    contextId: this._contextId,
                    skillId: this.skillId || null,
                    files: fileParts,
                    metadata: { variables },
                    getHeaders,
                    credentials: this.useCredentials ? 'include' : 'omit',
                },
                (event) => this._handleEvent(event, this._activeStreamMessageId),
            );
        } catch (err) {
            const m = err instanceof Error ? err.message : String(err);
            this._patchMessage(assistantMsg.id, { content: m, streaming: false });
            this._emitAssistantEvent('error', {
                message: m,
                flow_id: this.flowId || null,
                skill_id: this.skillId || null,
                embed_id: this.embedId || null,
            });
        } finally {
            this._loading = false;
            this._sseOpen = false;
            if (this._pendingAssistantReplyNotify) {
                this._pendingAssistantReplyNotify = false;
                this.dispatchEvent(
                    new CustomEvent('humanitec-embed-chat-assistant-reply-completed', {
                        bubbles: true,
                        composed: true,
                    }),
                );
            }
            this.requestUpdate();
        }
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
        const r = event?.result;
        const md = r?.metadata || {};
        const st = r?.status?.state;
        const stStr = typeof st === 'string' ? st : st?.value;
        if (
            (md.platform_handoff_continue === true || md.platform_oauth_continue === true) &&
            (stStr === 'input-required' || stStr === 'input_required') &&
            !r?.final
        ) {
            this._loading = false;
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
        if (reduced.operatorMessage) {
            const opMsg = {
                id: `op_${++mid}`,
                role: 'operator',
                content: reduced.operatorMessage,
                operatorReply: '',
                blocks: [],
                toolCalls: [],
                toolResults: [],
            };
            this._messages = [...this._messages, opMsg];
            this.requestUpdate();
            return;
        }
        if (reduced.operatorFiles) {
            const lastOp = [...this._messages].reverse().find((m) => m.role === 'operator');
            if (lastOp) {
                this._patchMessage(lastOp.id, {
                    fileIds: [...(lastOp.fileIds || []), ...reduced.operatorFiles],
                });
            } else {
                const opMsg = {
                    id: `op_${++mid}`,
                    role: 'operator',
                    content: '',
                    fileIds: reduced.operatorFiles,
                    operatorReply: '',
                    blocks: [],
                    toolCalls: [],
                    toolResults: [],
                };
                this._messages = [...this._messages, opMsg];
            }
            this.requestUpdate();
            return;
        }
        if (reduced.splitMessage) {
            this._patchMessage(messageId, { inputRequired: null, streaming: false });
            const resumeMsg = {
                id: `a_${++mid}`,
                role: 'assistant',
                content: reduced.patch.content || '',
                streaming: true,
                reasoning: '',
                operatorReply: '',
                toolCalls: [],
                toolResults: [],
                blocks: [],
                inputRequired: null,
                breakpoint: null,
            };
            this._messages = [...this._messages, resumeMsg];
            this._activeStreamMessageId = resumeMsg.id;
            this.requestUpdate();
            return;
        }
        if (reduced.uiEvent && typeof reduced.uiEvent === 'object') {
            this._emitUiEvents([reduced.uiEvent], messageId);
        }
        const patch = reduced.patch;
        if (patch && Object.keys(patch).length > 0) {
            const merged = { ...msg, ...patch };
            this._messages = this._messages.map((m) => (m.id === messageId ? merged : m));
            if (Array.isArray(patch.uiEvents) && patch.uiEvents.length > 0) {
                this._emitUiEvents(patch.uiEvents, messageId);
            }
        }
        this.requestUpdate();
    }

    _newChat() {
        this._pendingAssistantReplyNotify = false;
        this._greetingTypingRunId += 1;
        this._contextId = `${Date.now()}`;
        this._uiEventDispatchKeys.clear();
        this._messages = [];
        this.greetingSent = false;
        this._stickToBottom = true;
        this.requestUpdate();
        this._startGreetingTypingIfNeeded();
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
                      <span>${this._headDisplayTitle()}</span>
                      <button type="button" class="link" @click=${this._newChat}>
                          ${this._lb('new_chat', 'New chat')}
                      </button>
                  </header>
              `;
        const credBadges =
            this._credentials.length > 0
                ? html`
                      <div class="embed-cred-badges">
                          ${this._credentials.map((c) => {
                              const key = `${c.provider}:${c.service}`;
                              const letter = (c.service || '?')[0].toUpperCase();
                              const colors = { google: '#4285F4', yandex: '#FC3F1D' };
                              const bg = colors[c.provider] || '#666';
                              const title = this._lb('integration_badge_title', 'Connected')
                                  .replace('{provider}', c.provider)
                                  .replace('{service}', c.service);
                              return html`
                                  <div class="embed-cred-anchor">
                                      <button
                                          class="embed-cred-badge"
                                          style="background:${bg}"
                                          title="${title}"
                                          @click=${(e) => this._toggleCredPopover(key, e)}
                                      >
                                          ${letter}
                                      </button>
                                      ${this._credPopover === key
                                          ? html`
                                                <div class="embed-cred-popover" @click=${(e) => e.stopPropagation()}>
                                                    <div class="embed-cred-popover-title">
                                                        ${c.provider} / ${c.service}
                                                    </div>
                                                    <button
                                                        class="embed-cred-disconnect"
                                                        @click=${() => this._deleteEmbedCredential(c.provider, c.service)}
                                                    >
                                                        ${this._lb('integration_disconnect', 'Disconnect')}
                                                    </button>
                                                </div>
                                            `
                                          : nothing}
                                  </div>
                              `;
                          })}
                      </div>
                  `
                : nothing;

        return html`
            ${head}
            <div class="embed-chat-content">
                ${credBadges}
                <div class="scroll" @scroll=${this._onScrollAreaScroll}>
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
            </div>
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
        if (m.role === 'operator') {
            const flowsRootOp = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim()) || '';
            const fileCards = (m.fileIds || []).map(
                (fid) => html`
                    <a
                        href="${flowsRootOp}/api/v1/files/download/${fid}"
                        target="_blank"
                        rel="noopener"
                        class="embed-file-card"
                    >
                        ${this._lb('download_file', 'Download')}
                    </a>
                `,
            );
            return html`
                <div class="msg assistant embed-operator-msg">
                    <div class="embed-operator-reply-label">${this._lb('operator_reply_heading', 'Operator')}</div>
                    <div class="embed-msg-md">${unsafeHTML(embedAssistantMarkdownToHtml(m.content || ''))}</div>
                    ${fileCards}
                </div>
            `;
        }
        const tools =
            m.toolCalls && m.toolCalls.length
                ? html`<div class="tools">${m.toolCalls.map((t) => t.name || t.function?.name || 'tool').join(', ')}</div>`
                : nothing;
        const flowsRoot = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim()) || '';
        const blocks = (m.blocks || []).map((b) => {
            const nb = normalizeEmbedBlockForFlowsUrls(b, flowsRoot);
            return html`<embed-block-renderer .block=${nb}></embed-block-renderer>`;
        });
        const bodyHtml = rewriteFlowsFileUrlsInHtml(
            embedAssistantMarkdownToHtml(m.content || ''),
            flowsRoot,
        );
        const interrupt = m.inputRequired
            ? html`
                  <div class="interrupt">
                      ${m.inputRequired.interruptKind === 'operator_task'
                          ? html`<div class="interrupt-banner">${this._lb('interrupt_operator_banner', '')}</div>`
                          : nothing}
                      ${m.inputRequired.interruptKind === 'oauth_required'
                          ? html`<div class="interrupt-banner">${this._lb('interrupt_oauth_banner', 'Authorization required')}</div>`
                          : nothing}
                      <div class="embed-msg-md">
                          ${unsafeHTML(
                              rewriteFlowsFileUrlsInHtml(
                                  embedAssistantMarkdownToHtml(m.inputRequired.question || ''),
                                  flowsRoot,
                              ),
                          )}
                      </div>
                      ${m.inputRequired.interruptKind === 'oauth_required' && m.inputRequired.authUrl
                          ? html`<a class="embed-oauth-link" href="${m.inputRequired.authUrl}" target="_blank" rel="noopener noreferrer">${this._lb('interrupt_oauth_button', 'Authorize')}</a>`
                          : nothing}
                  </div>
              `
            : nothing;
        const operatorReplyHtml =
            m.operatorReply && String(m.operatorReply).trim()
                ? html`
                      <div class="embed-operator-reply">
                          <div class="embed-operator-reply-label">${this._lb('operator_reply_heading', 'Operator')}</div>
                          <div class="embed-msg-md">
                              ${unsafeHTML(
                                  rewriteFlowsFileUrlsInHtml(
                                      embedAssistantMarkdownToHtml(String(m.operatorReply)),
                                      flowsRoot,
                                  ),
                              )}
                          </div>
                      </div>
                  `
                : nothing;
        return html`
            <div class="msg assistant">
                <div class="embed-msg-md">${unsafeHTML(bodyHtml)}</div>
                ${m.streaming ? html`<span class="embed-stream-caret" aria-hidden="true">|</span>` : nothing}
                ${interrupt}
                ${operatorReplyHtml}
                ${blocks}
                ${tools}
            </div>
        `;
    }
}

customElements.define('platform-embed-chat', PlatformEmbedChat);

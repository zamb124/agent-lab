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
import {
    pairEmbedToolCallsAndResults,
    embedToolRowDisplayName,
    formatEmbedToolPairHintText,
} from './embed-tool-helpers.js';
import { toolCallIconName } from '../utils/tool-call-icon.js';
import '../components/platform-icon.js';
import '../components/platform-help-hint.js';
import '../components/platform-assistant-message-actions.js';
import {
    readTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '../voice/tts-output-pref.js';
import {
    resolveVoiceHttpOrigin,
    resolveVoiceHttpOriginFromFlowsBaseUrl,
} from '../voice/voice-http-origin.js';
import { VoiceMediaSession } from '../voice/voice-media-session.js';
import { normalizeVoiceLocaleForWs } from '../voice/normalize-voice-locale.js';
import { fetchFlowVoiceSessionQueryDict } from '../voice/fetch-flow-voice-session-query.js';
import {
    feedStreamTtsFromA2aResult,
    primeStreamTtsPlaybackFromUserGesture,
    stopStreamTtsPlayback,
    setStreamTtsTarget,
    clearStreamTtsTarget,
} from '../voice/stream-tts-registry.js';
import './embed-block-renderer.js';
import './embed-chat-input.js';
import { hasPlatformBus } from '../events/bus-singleton.js';
import { bootstrapPlatformBus, completeBootstrap } from '../events/bootstrap.js';

let mid = 0;

/** Путь вида `/flows` для baseUrl платформы; пустая строка — как у shell без сервисного префикса. */
function _serviceBasePathFromFlowsBaseUrl(flowsBaseUrl) {
    if (typeof flowsBaseUrl !== 'string') {
        return '';
    }
    const t = flowsBaseUrl.trim();
    if (t === '') return '';
    try {
        const baseHref = typeof globalThis.location !== 'undefined' && globalThis.location.href
            ? globalThis.location.href
            : 'https://localhost/';
        const href = /^https?:\/\//i.test(t) ? t : new URL(t, baseHref).href;
        const pathname = new URL(href).pathname.replace(/\/+$/, '');
        return pathname;
    } catch {
        return '';
    }
}

function _platformApexOriginFromFlowsBaseUrl(flowsBaseUrl) {
    if (typeof flowsBaseUrl !== 'string') {
        return '';
    }
    const t = flowsBaseUrl.trim();
    if (t === '') {
        return '';
    }
    try {
        const baseHref =
            typeof globalThis.location !== 'undefined' && globalThis.location.href
                ? globalThis.location.href
                : 'https://localhost/';
        const href = /^https?:\/\//i.test(t) ? t : new URL(t, baseHref).href;
        const u = new URL(href);
        return `${u.protocol}//${u.host}`;
    } catch {
        return '';
    }
}

/** @param {unknown} raw */
function _normalizedPlatformUiOrigin(raw) {
    if (typeof raw !== 'string') {
        return '';
    }
    const t = raw.trim();
    if (t === '') {
        return '';
    }
    try {
        const baseHref =
            typeof globalThis.location !== 'undefined' && globalThis.location.href
                ? globalThis.location.href
                : 'https://localhost/';
        const href = /^https?:\/\//i.test(t) ? t : new URL(t, baseHref).href;
        const u = new URL(href);
        return `${u.protocol}//${u.host}`;
    } catch {
        return '';
    }
}

/**
 * Core-компоненты (platform-assistant-message-actions и др.) расширяют PlatformElement,
 * который в connectedCallback требует getPlatformBus. Полноценного PlatformApp в embed нет —
 * поднимаем один EventBus синхронно до super.connectedCallback.
 */
function ensurePlatformBusForEmbedChat(flowsBaseUrl, platformUiOrigin) {
    if (typeof window === 'undefined' || hasPlatformBus()) return;
    const devMode =
        typeof location !== 'undefined' && /[?&]platform_devtools=1\b/.test(location.search);
    const apex =
        _normalizedPlatformUiOrigin(platformUiOrigin) ||
        _platformApexOriginFromFlowsBaseUrl(flowsBaseUrl);
    const baseUrl = _serviceBasePathFromFlowsBaseUrl(flowsBaseUrl);
    bootstrapPlatformBus({
        baseUrl,
        platformApexOrigin: apex || undefined,
        routes: [],
        slices: {},
        effects: [],
        devMode,
    });
    completeBootstrap();
}

const ASSISTANT_EVENT_SCHEMA_VERSION = '1.0.0';

/**
 * Автономный чат: A2A stream + блоки. Без apps/crm, apps/flows.
 *
 * Свойства:
 * - flowsBaseUrl, platformUiOrigin (platform-ui-origin): origin UI-платформы для bus (i18n, иконки, file-types);
 *   если пусто — берётся origin из flowsBaseUrl
 * - flowId, embedId, branchId или skillId (легаси атрибут skill-id; embedId приоритетен для внешнего embed-route)
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
 * - companyId (company-id), voiceBaseUrl (voice-base-url): для потоковой озвучки A2A без drawer; voiceBaseUrl опционально — из flowsBaseUrl
 *
 * Событие (после завершения стрима ответа на отправку пользователя): **`humanitec-embed-chat-assistant-reply-completed`**, bubbles + composed — для счётчика на FAB drawer.
 */
export class PlatformEmbedChat extends LitElement {
    static properties = {
        flowsBaseUrl: { type: String, attribute: 'flows-base-url' },
        platformUiOrigin: { type: String, attribute: 'platform-ui-origin' },
        flowId: { type: String, attribute: 'flow-id' },
        embedId: { type: String, attribute: 'embed-id' },
        branchId: { type: String, attribute: 'branch-id' },
        skillId: { type: String, attribute: 'skill-id' },
        title: { type: String },
        assistantTitle: { type: String, attribute: 'assistant-title' },
        labels: { type: Object },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        voiceDuplex: { type: Boolean, attribute: 'voice-duplex' },
        voiceComposerActive: { type: Boolean, attribute: 'voice-composer-active' },
        voiceComposerStatus: { type: String, attribute: 'voice-composer-status' },
        embedTheme: { type: String, attribute: 'embed-theme' },
        interfaceLocale: { type: String, attribute: 'interface-locale' },
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        hideHeader: { type: Boolean, attribute: 'hide-header' },
        companyId: { type: String, attribute: 'company-id' },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        visible: { type: Boolean, reflect: true },
        eventNamespace: { type: String, attribute: 'event-namespace' },
        eventAckRetries: { type: Number, attribute: 'event-ack-retries' },
        eventAckTimeoutMs: { type: Number, attribute: 'event-ack-timeout-ms' },
        getExtraMetadataVariables: { type: Object },
        getContextVariables: { type: Object },
        greetingSent: { type: Boolean, state: true },
        _credentials: { state: true },
        _credPopover: { state: true },
        _embedTtsOnlyMedia: { state: true },
        _embedTtsOnlyStreamStarting: { state: true },
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
        .scroll > .msg {
            align-self: flex-start;
            max-width: 92%;
        }
        .embed-msg-group {
            display: flex;
            flex-direction: column;
            max-width: 92%;
            min-width: 0;
            align-items: stretch;
        }
        .embed-msg-group.user {
            align-self: flex-end;
            align-items: flex-end;
        }
        .embed-msg-group.assistant {
            align-self: flex-start;
        }
        .msg {
            max-width: 100%;
            min-width: 0;
            width: fit-content;
            padding: 12px 14px;
            border-radius: var(--embed-radius);
            font-size: 14px;
            line-height: 1.45;
            box-sizing: border-box;
        }
        .embed-msg-group.user .msg {
            width: auto;
        }
        .embed-msg-group.assistant .msg {
            width: 100%;
        }
        .msg.user {
            background: var(--embed-chat-accent-muted);
        }
        .msg.assistant {
            background: var(--embed-chat-surface);
            border: 1px solid var(--embed-chat-border);
        }
        .embed-assistant-actions,
        .embed-user-actions {
            margin-top: 6px;
            padding: 0 2px;
        }
        .embed-msg-group.user .embed-user-actions {
            display: flex;
            justify-content: flex-end;
            width: 100%;
            box-sizing: border-box;
        }
        .meta {
            font-size: 11px;
            color: var(--embed-chat-muted);
            margin-bottom: 4px;
        }
        .embed-tool-stack {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            margin-top: 10px;
        }
        .embed-tool-orb {
            position: relative;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 30px;
            height: 30px;
            margin-left: -10px;
            border-radius: 50%;
            background: var(--embed-chat-composer-bg);
            border: 1px solid var(--embed-chat-border);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
        }
        :host([embed-theme='light']) .embed-tool-orb {
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
        }
        .embed-tool-orb:first-child {
            margin-left: 0;
        }
        .embed-tool-orb-inner {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
        }
        .embed-tool-orb platform-help-hint {
            display: inline-flex;
            align-items: center;
            justify-content: center;
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
        this.platformUiOrigin = '';
        this.flowId = '';
        this.embedId = '';
        this.branchId = '';
        this.skillId = '';
        this.title = '';
        this.assistantTitle = '';
        this.labels = {};
        this.useCredentials = false;
        this.enableVoice = true;
        this.voiceDuplex = false;
        this.voiceComposerActive = false;
        this.voiceComposerStatus = 'idle';
        this.embedTheme = 'dark';
        this.interfaceLocale = 'auto';
        this.showLocaleControl = false;
        this.hideHeader = false;
        this.companyId = '';
        this.voiceBaseUrl = '';
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
        this._cancelBusy = false;
        /** @type {AbortController|null} */
        this._streamAbort = null;
        this._contextId = `${Date.now()}`;
        this._currentTaskId = null;
        this.greetingSent = false;
        /** Пользователь у низа — продолжаем автопрокрутку при новых кусках ответа */
        this._stickToBottom = true;
        /** После отправки пользователя ждём завершения стрима — для счётчика на FAB drawer. */
        this._pendingAssistantReplyNotify = false;
        /** @type {string|null} */
        this._voiceStreamAssistantId = null;
        /** @type {Record<string, unknown>|null} */
        this._voicePendingStreamMetadata = null;
        /** @type {Array<{provider:string, service:string}>} */
        this._credentials = [];
        this._credPopover = null;
        /** @type {InstanceType<typeof VoiceMediaSession> | null} */
        this._embedTtsOnlyMedia = null;
        this._embedTtsOnlyStreamStarting = false;
        this._uiEventDispatchKeys = new Set();
        this._greetingTypingRunId = 0;
        this._pendingEventAcks = new Map();
        this._boundAckListener = (event) => this._handleHostEventAck(event, true);
        this._boundNackListener = (event) => this._handleHostEventAck(event, false);
        this._ackEventName = null;
        this._nackEventName = null;
        this._onCredClickOutside = this._onCredClickOutside.bind(this);
        this._onTtsPrefForEmbed = () => {
            this.requestUpdate();
            this._syncEmbedStreamTtsAfterPrefChange();
        };
        this._onTtsStorageForEmbed = (e) => {
            if (
                e.storageArea === window.localStorage
                && e.key === TTS_OUTPUT_STORAGE_KEY
            ) {
                this.requestUpdate();
                this._syncEmbedStreamTtsAfterPrefChange();
            }
        };
        registerBuiltinEmbedBlocks();
    }

    _embedBranchId() {
        const a = this.branchId != null ? String(this.branchId).trim() : '';
        const b = this.skillId != null ? String(this.skillId).trim() : '';
        return a || b;
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

    /**
     * Origin голосового шлюза для POST /api/v1/synthesize (кнопка озвучки).
     * На странице embed хост документа часто не совпадает с хостом flows — URL из flowsBaseUrl.
     * @returns {string}
     */
    _embedAssistantTtsVoiceBaseUrl() {
        if (!readTtsOutputEnabled()) {
            return '';
        }
        const flows = this.flowsBaseUrl != null ? String(this.flowsBaseUrl).trim() : '';
        if (flows !== '') {
            return resolveVoiceHttpOriginFromFlowsBaseUrl(flows);
        }
        return resolveVoiceHttpOrigin();
    }

    /**
     * HTTP-база voice для WS TTS-only (без проверки pref озвучки).
     * @returns {string}
     */
    _resolvedVoiceHttpBaseForStream() {
        const explicit = String(this.voiceBaseUrl || '').trim().replace(/\/$/, '');
        if (explicit !== '') {
            return explicit;
        }
        const flows = this.flowsBaseUrl != null ? String(this.flowsBaseUrl).trim() : '';
        if (flows !== '') {
            return resolveVoiceHttpOriginFromFlowsBaseUrl(flows);
        }
        return resolveVoiceHttpOrigin();
    }

    /**
     * @returns {boolean}
     */
    _voiceEmbedTtsContextReady() {
        const voiceBase = this._resolvedVoiceHttpBaseForStream();
        if (voiceBase === '') {
            return false;
        }
        if (!this.embedId && !this.flowId) {
            return false;
        }
        if (String(this.companyId || '').trim() === '') {
            return false;
        }
        if (String(this.flowsBaseUrl || '').trim() === '') {
            return false;
        }
        return true;
    }

    /**
     * @returns {Record<string, string>}
     */
    _wsLanguageQueryForVoiceSession() {
        const il = String(this.interfaceLocale || '').trim();
        if (il === '' || il.toLowerCase() === 'auto') {
            return {};
        }
        try {
            return { language: normalizeVoiceLocaleForWs(il) };
        } catch {
            return {};
        }
    }

    /**
     * @returns {Promise<Record<string, string>>}
     */
    async _mergeEmbedTtsOnlyWsQuery() {
        let serverQuery = {};
        const fid = String(this.flowId || '').trim();
        const root = String(this.flowsBaseUrl || '').replace(/\/$/, '');
        if (fid !== '' && root !== '') {
            serverQuery = await fetchFlowVoiceSessionQueryDict({
                flowsApiRoot: root,
                flowId: fid,
                branchId: this.branchId,
                skillIdLegacy: this.skillId,
                credentials: this.useCredentials === true ? 'include' : 'omit',
                getHeaders:
                    typeof this.getAuthToken === 'function' ? () => this.getAuthToken() : async () => ({}),
            });
        }
        const wsQuery = { ...serverQuery };
        Object.assign(wsQuery, this._wsLanguageQueryForVoiceSession());
        return wsQuery;
    }

    _disposeEmbedTtsOnlyStream() {
        const m = this._embedTtsOnlyMedia;
        this._embedTtsOnlyMedia = null;
        this._embedTtsOnlyStreamStarting = false;
        clearStreamTtsTarget();
        if (m) {
            try {
                m.close();
            } catch {
                /* noop */
            }
        }
    }

    /**
     * @param {Record<string, string>} wsQuery
     * @returns {VoiceMediaSession}
     */
    _createEmbedTtsOnlyVoiceMediaSession(wsQuery) {
        const voiceBaseUrl = this._resolvedVoiceHttpBaseForStream().replace(/\/$/, '');
        const companyId = String(this.companyId || '').trim();
        const sessionId = `tts_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
        const wsBase = voiceBaseUrl.replace(/^http/, 'ws');
        const opts = {
            baseUrl: wsBase,
            sessionId,
            companyId,
            autoRecord: false,
        };
        if (Object.keys(wsQuery).length > 0) {
            Object.assign(opts, { query: wsQuery });
        }
        const media = new VoiceMediaSession(opts);
        media.addEventListener('error', (e) => {
            this.dispatchEvent(
                new CustomEvent('humanitec-embed-voice-error', {
                    bubbles: true,
                    composed: true,
                    detail: e.detail,
                }),
            );
        });
        media.addEventListener('closed', () => {
            if (this._embedTtsOnlyMedia === media) {
                this._embedTtsOnlyMedia = null;
                clearStreamTtsTarget();
            }
        });
        return media;
    }

    /**
     * @param {VoiceMediaSession} media
     * @returns {Promise<void>}
     */
    async _finalizeEmbedTtsOnlyStreamAfterConnect(media) {
        await media.connect();
        if (this._embedTtsOnlyMedia !== media) {
            try {
                media.close();
            } catch {
                /* noop */
            }
            return;
        }
        if (this.voiceComposerActive || !readTtsOutputEnabled() || !this.visible) {
            this._embedTtsOnlyMedia = null;
            clearStreamTtsTarget();
            try {
                media.close();
            } catch {
                /* noop */
            }
            return;
        }
        setStreamTtsTarget(media, readTtsOutputEnabled);
    }

    /**
     * Жест отправки: WS только для TTS (`speak`). Публичный API для drawer.
     */
    primeStreamTtsFromUserGesture() {
        if (!readTtsOutputEnabled()) {
            return;
        }
        if (this.voiceComposerActive) {
            return;
        }
        if (!this._voiceEmbedTtsContextReady()) {
            return;
        }
        if (this._embedTtsOnlyMedia !== null && this._embedTtsOnlyMedia.isConnected) {
            this._embedTtsOnlyMedia.primePlaybackFromUserGesture();
            setStreamTtsTarget(this._embedTtsOnlyMedia, readTtsOutputEnabled);
            return;
        }
        if (this._embedTtsOnlyStreamStarting) {
            const m = this._embedTtsOnlyMedia;
            if (m && typeof m.primePlaybackFromUserGesture === 'function') {
                m.primePlaybackFromUserGesture();
            }
            if (m) {
                setStreamTtsTarget(m, readTtsOutputEnabled);
            }
            return;
        }
        this._disposeEmbedTtsOnlyStream();
        this._embedTtsOnlyStreamStarting = true;
        void (async () => {
            /** @type {InstanceType<typeof VoiceMediaSession>|null} */
            let media = null;
            try {
                const wsQuery = await this._mergeEmbedTtsOnlyWsQuery();
                media = this._createEmbedTtsOnlyVoiceMediaSession(wsQuery);
                this._embedTtsOnlyMedia = media;
                media.primePlaybackFromUserGesture();
                setStreamTtsTarget(media, readTtsOutputEnabled);
                await this._finalizeEmbedTtsOnlyStreamAfterConnect(media);
            } catch (err) {
                if (this._embedTtsOnlyMedia === media) {
                    this._embedTtsOnlyMedia = null;
                }
                clearStreamTtsTarget();
                if (media !== null) {
                    try {
                        media.close();
                    } catch {
                        /* noop */
                    }
                }
                this.dispatchEvent(
                    new CustomEvent('humanitec-embed-voice-error', {
                        bubbles: true,
                        composed: true,
                        detail: {
                            code: 'voice/tts_stream_connect_failed',
                            detail: err instanceof Error ? err.message : String(err),
                        },
                    }),
                );
            } finally {
                this._embedTtsOnlyStreamStarting = false;
            }
        })();
    }

    async ensureTtsOnlyStream() {
        if (!readTtsOutputEnabled()) {
            this._disposeEmbedTtsOnlyStream();
            return;
        }
        if (!this.visible || this.voiceComposerActive) {
            return;
        }
        if (!this._voiceEmbedTtsContextReady()) {
            return;
        }
        if (this._embedTtsOnlyMedia !== null && this._embedTtsOnlyMedia.isConnected) {
            setStreamTtsTarget(this._embedTtsOnlyMedia, readTtsOutputEnabled);
            return;
        }
        if (this._embedTtsOnlyStreamStarting) {
            return;
        }
        this._disposeEmbedTtsOnlyStream();
        this._embedTtsOnlyStreamStarting = true;
        /** @type {InstanceType<typeof VoiceMediaSession>|null} */
        let media = null;
        try {
            const wsQuery = await this._mergeEmbedTtsOnlyWsQuery();
            media = this._createEmbedTtsOnlyVoiceMediaSession(wsQuery);
            this._embedTtsOnlyMedia = media;
            await this._finalizeEmbedTtsOnlyStreamAfterConnect(media);
        } catch (err) {
            if (this._embedTtsOnlyMedia === media) {
                this._embedTtsOnlyMedia = null;
            }
            clearStreamTtsTarget();
            if (media !== null) {
                try {
                    media.close();
                } catch {
                    /* noop */
                }
            }
            this.dispatchEvent(
                new CustomEvent('humanitec-embed-voice-error', {
                    bubbles: true,
                    composed: true,
                    detail: {
                        code: 'voice/tts_stream_connect_failed',
                        detail: err instanceof Error ? err.message : String(err),
                    },
                }),
            );
        } finally {
            this._embedTtsOnlyStreamStarting = false;
        }
    }

    disposeTtsOnlyStream() {
        this._disposeEmbedTtsOnlyStream();
    }

    _syncEmbedStreamTtsAfterPrefChange() {
        if (!readTtsOutputEnabled()) {
            this._disposeEmbedTtsOnlyStream();
            return;
        }
        if (this.visible && !this.voiceComposerActive) {
            void this.ensureTtsOnlyStream();
        }
    }

    /**
     * Пока tts-only WS коннектится, `feedStreamTtsFromA2aResult` без цели; ждём перед SSE.
     * @returns {Promise<void>}
     */
    async _awaitEmbedTtsOnlyReady() {
        if (!this._voiceEmbedTtsContextReady()) {
            return;
        }
        const t0 = Date.now();
        const maxMs = 2500;
        while (Date.now() - t0 < maxMs) {
            if (this.voiceComposerActive || !readTtsOutputEnabled()) {
                return;
            }
            if (
                !this._embedTtsOnlyStreamStarting
                && this._embedTtsOnlyMedia !== null
                && this._embedTtsOnlyMedia.isConnected
            ) {
                return;
            }
            await new Promise((r) => setTimeout(r, 40));
        }
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
        ensurePlatformBusForEmbedChat(this.flowsBaseUrl, this.platformUiOrigin);
        super.connectedCallback();
        this.addEventListener('embed-block-action', this._onBlockAction);
        document.addEventListener('click', this._onCredClickOutside);
        this._bindAckListeners();
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefForEmbed);
            window.addEventListener('storage', this._onTtsStorageForEmbed);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('embed-block-action', this._onBlockAction);
        document.removeEventListener('click', this._onCredClickOutside);
        if (typeof window !== 'undefined') {
            window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefForEmbed);
            window.removeEventListener('storage', this._onTtsStorageForEmbed);
        }
        this._unbindAckListeners();
        this._pendingEventAcks.forEach((pending) => {
            if (pending.timer) {
                clearTimeout(pending.timer);
            }
        });
        this._pendingEventAcks.clear();
        this._disposeEmbedTtsOnlyStream();
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
        if (changed.has('visible') && !this.visible) {
            this._disposeEmbedTtsOnlyStream();
        }
        if (changed.has('flowId') || changed.has('branchId') || changed.has('skillId')) {
            this._disposeEmbedTtsOnlyStream();
        }
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

    async _mergeSendMetadataVariables() {
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
        return { ...langVars, ...extraVars, ...contextVars };
    }

    /**
     * Текущий A2A contextId (синхронизация с VoiceAgentBridge).
     * @returns {string}
     */
    getA2aContextId() {
        return this._contextId;
    }

    /**
     * Metadata для очередного voice message/stream (после prepareVoiceUserTurn).
     * @returns {Record<string, unknown>|null}
     */
    consumeVoiceStreamMetadata() {
        const m = this._voicePendingStreamMetadata;
        this._voicePendingStreamMetadata = null;
        return m;
    }

    /**
     * Подготовка UI и metadata перед голосовым A2A-стримом.
     * @param {string} userText
     */
    async prepareVoiceUserTurn(userText) {
        const message = typeof userText === 'string' ? userText.trim() : '';
        if (message === '') {
            throw new Error('platform-embed-chat: empty voice text');
        }
        if (this._voiceStreamAssistantId != null) {
            this.finalizeVoiceA2aStream();
        }
        if (this._sseOpen || this._loading) {
            throw new Error('platform-embed-chat: stream active');
        }
        if (!this.flowsBaseUrl || (!this.flowId && !this.embedId)) {
            throw new Error('platform-embed-chat: missing flows config');
        }

        this._messages = [
            ...this._messages,
            {
                id: `u_${++mid}`,
                role: 'user',
                content: message,
                filesMeta: [],
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
        this._voiceStreamAssistantId = assistantMsg.id;
        this._activeStreamMessageId = assistantMsg.id;
        this._loading = true;
        this._sseOpen = true;
        this._pendingAssistantReplyNotify = true;
        this._stickToBottom = true;
        this.requestUpdate();

        const variables = await this._mergeSendMetadataVariables();
        this._voicePendingStreamMetadata = { variables };
        this._emitAssistantEvent('context_requested', {
            flow_id: this.flowId || null,
            branch_id: this._embedBranchId() || null,
            embed_id: this.embedId || null,
            variables,
        });
    }

    /**
     * Проброс SSE события A2A в тот же рендер, что и текстовая отправка.
     * @param {object} event
     */
    applyVoiceA2aStreamEvent(event) {
        const id = this._voiceStreamAssistantId;
        if (!id) {
            return;
        }
        this._handleEvent(event, id);
    }

    /**
     * Завершение голосового A2A (успех, abort или после ошибки с патчем).
     */
    finalizeVoiceA2aStream() {
        const id = this._voiceStreamAssistantId;
        if (id) {
            const msg = this._findMessage(id);
            if (msg && msg.streaming) {
                this._patchMessage(id, { streaming: false });
            }
        }
        this._voiceStreamAssistantId = null;
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

    /**
     * Ошибка голосового стрима: текст ошибки в пузырь ассистента.
     * @param {string} detail
     */
    failVoiceA2aStream(detail) {
        const id = this._voiceStreamAssistantId;
        if (id) {
            const m = typeof detail === 'string' ? detail : String(detail || 'Error');
            this._patchMessage(id, { content: m, streaming: false });
        }
        this.finalizeVoiceA2aStream();
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

    _onEmbedComposeEdit(e) {
        const detail = e.detail;
        const text = detail && typeof detail.text === 'string' ? detail.text : '';
        if (text === '') {
            return;
        }
        const input = this.renderRoot?.querySelector('embed-chat-input');
        if (!input || typeof input.setDraft !== 'function') {
            throw new Error('platform-embed-chat: embed-chat-input.setDraft unavailable');
        }
        input.setDraft(text);
    }

    _onEmbedStop() {
        if (this._cancelBusy) {
            return;
        }
        if (!this._loading) {
            return;
        }
        stopStreamTtsPlayback();
        if (this._voiceStreamAssistantId != null) {
            this.dispatchEvent(
                new CustomEvent('humanitec-embed-voice-bridge-user-stop', {
                    bubbles: true,
                    composed: true,
                }),
            );
            return;
        }
        const ac = this._streamAbort;
        if (ac !== null) {
            try {
                ac.abort();
            } catch {
                /* noop */
            }
        }
        const tid = this._currentTaskId;
        if (typeof tid === 'string' && tid !== '') {
            this._cancelBusy = true;
            this.requestUpdate();
            void this._postEmbedTasksCancel(tid).finally(() => {
                this._cancelBusy = false;
                this.requestUpdate();
            });
        }
    }

    /**
     * @param {string} taskId
     * @returns {Promise<void>}
     */
    _postEmbedTasksCancel(taskId) {
        const root = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim().replace(/\/$/, '')) || '';
        if (root === '') {
            return Promise.resolve();
        }
        const url = this.embedId
            ? `${root}/api/v1/embed/${encodeURIComponent(this.embedId)}`
            : `${root}/api/v1/${encodeURIComponent(this.flowId)}`;
        const run = async () => {
            const getHeaders = async () => {
                if (typeof this.getAuthToken !== 'function') {
                    return {};
                }
                const h = await this.getAuthToken();
                return h && typeof h === 'object' ? h : {};
            };
            const extra = await getHeaders();
            await fetch(url, {
                method: 'POST',
                credentials: this.useCredentials ? 'include' : 'omit',
                headers: {
                    'Content-Type': 'application/json',
                    ...extra,
                },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    id: String(Date.now()),
                    method: 'tasks/cancel',
                    params: { id: taskId },
                }),
            });
        };
        return run().catch(() => {
            /* стрим уже оборван на клиенте */
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

        stopStreamTtsPlayback();

        if (readTtsOutputEnabled()) {
            primeStreamTtsPlaybackFromUserGesture();
            this.primeStreamTtsFromUserGesture();
            await this._awaitEmbedTtsOnlyReady();
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
        this._streamAbort = new AbortController();
        this.requestUpdate();

        const getHeaders = async () => {
            if (typeof this.getAuthToken !== 'function') {
                return {};
            }
            const h = await this.getAuthToken();
            return h && typeof h === 'object' ? h : {};
        };

        const variables = await this._mergeSendMetadataVariables();
        this._emitAssistantEvent('context_requested', {
            flow_id: this.flowId || null,
            branch_id: this._embedBranchId() || null,
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
                    branchId: this._embedBranchId() || null,
                    files: fileParts,
                    metadata: { variables },
                    getHeaders,
                    credentials: this.useCredentials ? 'include' : 'omit',
                    signal: this._streamAbort.signal,
                },
                (event) => this._handleEvent(event, this._activeStreamMessageId),
            );
        } catch (err) {
            const aborted = err instanceof Error && err.name === 'AbortError';
            if (aborted) {
                this._patchMessage(assistantMsg.id, { streaming: false });
            } else {
                const m = err instanceof Error ? err.message : String(err);
                const isGuestLimit =
                    typeof m === 'string' &&
                    (m.includes('Достигнут лимит сообщений для этого виджета') ||
                        m.includes('Guest message limit reached for this widget'));
                if (isGuestLimit) {
                    this._patchMessage(assistantMsg.id, {
                        content: '',
                        streaming: false,
                        inputRequired: {
                            interruptKind: 'oauth_required',
                            question: m,
                            authUrl: '/login',
                        },
                    });
                } else {
                    this._patchMessage(assistantMsg.id, { content: m, streaming: false });
                }
                this._emitAssistantEvent('error', {
                    message: m,
                    flow_id: this.flowId || null,
                    branch_id: this._embedBranchId() || null,
                    embed_id: this.embedId || null,
                });
            }
        } finally {
            this._streamAbort = null;
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
        const streamResult = event && typeof event === 'object' ? event.result : null;
        if (streamResult !== null && typeof streamResult === 'object') {
            feedStreamTtsFromA2aResult(streamResult);
        }
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
                    ?cancel-busy=${this._cancelBusy}
                    placeholder=${this._lb('placeholder', 'Message...')}
                    .labels=${this._mergedLabels()}
                    ?enable-voice=${this.enableVoice}
                    ?voice-duplex=${this.voiceDuplex}
                    ?voice-active=${this.voiceComposerActive}
                    voice-composer-status=${this.voiceComposerStatus || 'idle'}
                    ?show-locale-control=${this.showLocaleControl}
                    interface-locale=${this.interfaceLocale || 'auto'}
                    @embed-locale-change=${this._onEmbedLocaleChange}
                    @embed-send=${this._onSend}
                    @embed-stop=${this._onEmbedStop}
                ></embed-chat-input>
            </div>
        `;
    }

    _renderEmbedToolStack(m) {
        const rows = pairEmbedToolCallsAndResults(m.toolCalls, m.toolResults);
        if (rows.length === 0) {
            return nothing;
        }
        const defaultName = this._lb('tool_default_name', 'tool');
        const hintStrings = {
            tool_hint_tool_name: this._lb('tool_hint_tool_name', 'Tool: {name}'),
            tool_hint_args_label: this._lb('tool_hint_args_label', 'Arguments:'),
            tool_hint_result_label: this._lb('tool_hint_result_label', 'Result:'),
        };
        const nameList = rows.map((row) => embedToolRowDisplayName(row.call, row.result, defaultName)).join(', ');
        const aria = this._lb('tool_stack_aria', 'Tool calls: {names}').replace(/\{names\}/g, nameList);
        return html`
            <div class="embed-tool-stack" role="group" aria-label=${aria}>
                ${rows.map(
                    (row, index) => {
                        const name = embedToolRowDisplayName(row.call, row.result, defaultName);
                        const icon = toolCallIconName(name);
                        const hint = formatEmbedToolPairHintText(row.call, row.result, hintStrings, defaultName);
                        const z = index + 1;
                        return html`
                            <span class="embed-tool-orb" style="z-index: ${z}">
                                <platform-help-hint .text=${hint} .label=${name} ?wide=${true}>
                                    <span class="embed-tool-orb-inner" tabindex="0" role="img" aria-label=${name}>
                                        <platform-icon name=${icon} size="16"></platform-icon>
                                    </span>
                                </platform-help-hint>
                            </span>
                        `;
                    },
                )}
            </div>
        `;
    }

    _renderMessage(m) {
        if (m.role === 'user') {
            const files =
                m.filesMeta && m.filesMeta.length
                    ? html`<div class="meta">${m.filesMeta.map((f) => f.name).join(', ')}</div>`
                    : nothing;
            const body = typeof m.content === 'string' ? m.content.trim() : '';
            const userActions =
                body !== ''
                    ? html`
                          <div class="embed-user-actions">
                              <platform-assistant-message-actions
                                  .text=${body}
                                  voice-base-url=""
                                  credentials=${this.useCredentials ? 'include' : 'omit'}
                                  show-edit
                                  @compose-edit=${this._onEmbedComposeEdit}
                              ></platform-assistant-message-actions>
                          </div>
                      `
                    : nothing;
            return html`
                <div class="embed-msg-group user">
                    <div class="msg user">
                        ${files}
                        ${m.content || ''}
                    </div>
                    ${userActions}
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
        const toolStack = this._renderEmbedToolStack(m);
        const flowsRoot = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim()) || '';
        const blocks = (m.blocks || []).map((b) => {
            const nb = normalizeEmbedBlockForFlowsUrls(b, flowsRoot);
            return html`<embed-block-renderer .block=${nb}></embed-block-renderer>`;
        });
        const bodyHtml = rewriteFlowsFileUrlsInHtml(
            embedAssistantMarkdownToHtml(m.content || '', { streaming: Boolean(m.streaming) }),
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
        const assistantActions =
            !m.streaming && typeof m.content === 'string' && m.content.trim() !== ''
                ? html`
                      <div class="embed-assistant-actions">
                          <platform-assistant-message-actions
                              .text=${String(m.content).trim()}
                              voice-base-url=${this._embedAssistantTtsVoiceBaseUrl()}
                              credentials=${this.useCredentials ? 'include' : 'omit'}
                              .getHeaders=${typeof this.getAuthToken === 'function' ? this.getAuthToken : null}
                          ></platform-assistant-message-actions>
                      </div>
                  `
                : nothing;
        return html`
            <div class="embed-msg-group assistant">
                <div class="msg assistant">
                    <div class="embed-msg-md">${unsafeHTML(bodyHtml)}</div>
                    ${m.streaming ? html`<span class="embed-stream-caret" aria-hidden="true">|</span>` : nothing}
                    ${interrupt}
                    ${operatorReplyHtml}
                    ${blocks}
                    ${toolStack}
                </div>
                ${assistantActions}
            </div>
        `;
    }
}

customElements.define('platform-embed-chat', PlatformEmbedChat);

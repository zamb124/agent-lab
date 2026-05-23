import { LitElement, html, css, nothing } from '../lit-shim.js';
import { streamEmbedA2A } from './embed-a2a-stream.js';
import {
    crmA2aInterfaceLanguageVariables,
    embedChatLabelsForLang,
} from './embed-chat-default-labels.js';
import { mergeBlocksFromToolResult } from '../flows-chat/tool-result-blocks.js';
import { normalizeFlowChatBlockForFlowsUrls } from '../flows-chat/flows-url-rewrite.js';
import {
    inputRequiredFieldsFromA2a,
    mapA2aResultToChatRuntimeEvents,
    resolveA2aContextId,
} from '../flows-chat/a2a-chat-runtime.js';
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
import '../flows-chat/flows-chat-message.js';
import '../flows-chat/flows-chat-files-panel.js';
import './embed-chat-input.js';
import { getActivePlatformNamespaceName } from '../utils/platform-namespace.js';
import { getPlatformBus, hasPlatformBus } from '../events/bus-singleton.js';
import { bootstrapPlatformBus, completeBootstrap } from '../events/bootstrap.js';
import { CoreEvents } from '../events/contract.js';

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

/** @param {unknown} payload */
function _normalizePendingActionIdFromPayload(payload) {
    const o =
        payload && typeof payload === 'object' && !Array.isArray(payload)
            ? /** @type {Record<string, unknown>} */ (payload)
            : {};
    const top = o.pending_action_id;
    if (typeof top === 'string' && top.trim()) {
        return top.trim();
    }
    const argsRaw = o.arguments;
    const args =
        argsRaw && typeof argsRaw === 'object' && !Array.isArray(argsRaw)
            ? /** @type {Record<string, unknown>} */ (argsRaw)
            : {};
    const fromArgs = args.pending_action_id;
    if (typeof fromArgs === 'string' && fromArgs.trim()) {
        return fromArgs.trim();
    }
    const ctxRaw = o.context;
    const ctx =
        ctxRaw && typeof ctxRaw === 'object' && !Array.isArray(ctxRaw)
            ? /** @type {Record<string, unknown>} */ (ctxRaw)
            : {};
    const fromCtx = ctx.pending_action_id;
    if (typeof fromCtx === 'string' && fromCtx.trim()) {
        return fromCtx.trim();
    }
    return '';
}

/** @param {unknown} raw */
function _embedRouteKeyForOpenEntityContext(raw) {
    const t = typeof raw === 'string' ? raw.trim().toLowerCase() : '';
    if (t === 'note' || t === 'meeting' || t === 'call') {
        return 'note';
    }
    return 'entity';
}

/**
 * CRM (и другой SPA с теми же ключами роутера): переход по `entity_id` из кнопки блока actions.
 *
 * @param {Record<string, unknown>} args
 * @param {Record<string, unknown>} ctx
 * @returns {boolean}
 */
function _tryDispatchEmbeddedRouterOpenEntity(args, ctx) {
    const rid =
        typeof args.entity_id === 'string' && args.entity_id.trim()
            ? args.entity_id.trim()
            : '';
    if (!rid || !hasPlatformBus()) {
        return false;
    }
    /** @type {{ getState?: () => unknown; dispatch?: (...args: unknown[]) => void }} */
    let bus;
    try {
        bus = getPlatformBus();
    } catch {
        return false;
    }
    if (!bus || typeof bus.getState !== 'function' || typeof bus.dispatch !== 'function') {
        return false;
    }
    const st = bus.getState();
    if (!st || typeof st !== 'object') {
        return false;
    }
    const routerRaw = /** @type {Record<string, unknown>} */ (st).router;
    if (!routerRaw || typeof routerRaw !== 'object') {
        return false;
    }
    const routesRaw = routerRaw.routes;
    if (!Array.isArray(routesRaw) || routesRaw.length === 0) {
        return false;
    }
    const c = ctx && typeof ctx === 'object' && !Array.isArray(ctx) ? ctx : {};
    const etCand = /** @type {Record<string, unknown>} */ (c).entity_type ?? /** @type {Record<string, unknown>} */ (c).entityType;
    const etStr = typeof etCand === 'string' ? etCand : '';
    const routeKey = _embedRouteKeyForOpenEntityContext(etStr);
    if (
        !routesRaw.some((r) => r && typeof r === 'object' && /** @type {{ key?: string }} */ (r).key === routeKey)
    ) {
        return false;
    }
    bus.dispatch(
        CoreEvents.ROUTER_NAVIGATE_REQUESTED,
        { routeKey, params: { itemId: rid } },
        { source: 'platform_embed_chat_open_entity' },
    );
    return true;
}

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

function _isEmbedGuestLimitMessage(text) {
    const raw = typeof text === 'string' ? text.trim() : '';
    if (raw.length === 0) {
        return false;
    }
    return (
        raw.includes('Достигнут лимит сообщений для этого виджета') ||
        raw.includes('Guest message limit reached for this widget')
    );
}

function _embedString(value) {
    return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function _embedFileKey(file) {
    if (!file || typeof file !== 'object') {
        return '';
    }
    return (
        _embedString(file.file_id)
        || _embedString(file.url)
        || _embedString(file.preview_url)
        || _embedString(file.original_name)
        || _embedString(file.name)
    );
}

function _upsertEmbedFiles(existing, incoming) {
    const out = Array.isArray(existing) ? [...existing] : [];
    const index = new Map();
    out.forEach((file, i) => {
        const key = _embedFileKey(file);
        if (key) {
            index.set(key, i);
        }
    });
    for (const file of Array.isArray(incoming) ? incoming : []) {
        if (!file || typeof file !== 'object') {
            continue;
        }
        const key = _embedFileKey(file);
        if (!key) {
            out.push(file);
            continue;
        }
        const existingIndex = index.get(key);
        if (typeof existingIndex === 'number') {
            out[existingIndex] = { ...out[existingIndex], ...file };
        } else {
            index.set(key, out.length);
            out.push(file);
        }
    }
    return out;
}

/**
 * Автономный чат: A2A stream + блоки. Без apps/crm, apps/flows.
 *
 * Свойства:
 * - flowsBaseUrl, platformUiOrigin (platform-ui-origin): origin UI-платформы для bus (i18n, иконки, file-types);
 *   если пусто — берётся origin из flowsBaseUrl
 * - flowId, embedId, branchId (embedId приоритетен для внешнего embed-route)
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
        flows-chat-message {
            max-width: 92%;
            min-width: 0;
            align-self: flex-start;
            --flows-chat-radius: var(--embed-radius);
            --flows-chat-text: var(--embed-chat-text);
            --flows-chat-muted: var(--embed-chat-muted);
            --flows-chat-secondary: var(--embed-chat-muted);
            --flows-chat-border: var(--embed-chat-border);
            --flows-chat-surface: var(--embed-chat-surface);
            --flows-chat-surface-subtle: var(--embed-chat-composer-bg);
            --flows-chat-accent: var(--embed-chat-accent);
            --flows-chat-accent-muted: var(--embed-chat-accent-muted);
            --flows-chat-info-bg: var(--embed-chat-interrupt-bg);
            --flows-chat-info-border: var(--embed-chat-accent);
        }
        flows-chat-message[data-role='user'] {
            align-self: flex-end;
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
        this._streamTaskPrimed = false;
        this.greetingSent = false;
        /** Пользователь у низа — продолжаем автопрокрутку при новых кусках ответа */
        this._stickToBottom = true;
        /** После отправки пользователя ждём завершения стрима — для счётчика на FAB drawer. */
        this._pendingAssistantReplyNotify = false;
        /** @type {boolean} */
        this._embeddedLaraApplyInFlight = false;
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
    }

    _embedBranchId() {
        return this.branchId != null ? String(this.branchId).trim() : '';
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
        if (!this._streamTtsAllowed()) {
            return '';
        }
        const flows = this.flowsBaseUrl != null ? String(this.flowsBaseUrl).trim() : '';
        if (flows !== '') {
            return resolveVoiceHttpOriginFromFlowsBaseUrl(flows);
        }
        return resolveVoiceHttpOrigin();
    }

    _streamTtsAllowed() {
        return (this.enableVoice === true || this.voiceDuplex === true) && readTtsOutputEnabled();
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
                credentials: this.useCredentials === true ? 'include' : 'omit',
                getHeaders: () => this._outboundFlowsRequestHeaders(),
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
        if (this.voiceComposerActive || !this._streamTtsAllowed() || !this.visible) {
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
        if (!this._streamTtsAllowed()) {
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
        if (!this._streamTtsAllowed()) {
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
        if (!this._streamTtsAllowed()) {
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
            if (this.voiceComposerActive || !this._streamTtsAllowed()) {
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
        this.addEventListener('flows-chat-block-action', this._onBlockAction);
        this.addEventListener('flows-chat-action-config-error', this._onEmbedActionConfigError);
        document.addEventListener('click', this._onCredClickOutside);
        this._bindAckListeners();
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPrefForEmbed);
            window.addEventListener('storage', this._onTtsStorageForEmbed);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('flows-chat-block-action', this._onBlockAction);
        this.removeEventListener('flows-chat-action-config-error', this._onEmbedActionConfigError);
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

    _onEmbedActionConfigError = (e) => {
        if (typeof e.stopPropagation === 'function') {
            e.stopPropagation();
        }
        const d = e?.detail && typeof e.detail === 'object' ? e.detail : {};
        const m =
            typeof d.message === 'string' && d.message.trim()
                ? d.message.trim()
                : 'Действие не настроено. Повторите запрос.';
        this._appendLocalAssistantEcho(m);
    };

    _onBlockAction = (e) => {
        if (typeof e.stopPropagation === 'function') {
            e.stopPropagation();
        }
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        const actionId = typeof detail.action_id === 'string' ? detail.action_id.trim() : '';
        const actionKind = typeof detail.action_kind === 'string' ? detail.action_kind.trim() : '';
        if (!actionId || !actionKind) {
            this._appendLocalAssistantEcho(
                'Не удалось обработать кнопку: нет идентификатора действия. Отправьте сообщение заново или обновите чат.',
            );
            return;
        }
        const args =
            detail.arguments && typeof detail.arguments === 'object' && !Array.isArray(detail.arguments)
                ? detail.arguments
                : {};
        const ctx =
            detail.context && typeof detail.context === 'object' && !Array.isArray(detail.context)
                ? detail.context
                : {};
        const pendingResolved =
            _normalizePendingActionIdFromPayload({
                pending_action_id: detail.pending_action_id,
                arguments: args,
                context: ctx,
            }) || null;
        const payload = {
            action_id: actionId,
            action_kind: actionKind,
            pending_action_id: pendingResolved,
            arguments: args,
            context: ctx,
        };
        const fn = this.actionHandlers['assistant:action_invoked'];
        if (typeof fn === 'function') {
            this._emitAssistantEvent('action_invoked', payload);
            fn(payload);
            return;
        }
        if (payload.action_kind === 'open_entity') {
            const ok = _tryDispatchEmbeddedRouterOpenEntity(args, ctx);
            queueMicrotask(() => {
                try {
                    this._emitAssistantEvent('action_invoked', payload);
                } catch (err) {
                    const m = err instanceof Error ? err.message : String(err);
                    console.warn('platform-embed-chat: action_invoked emit failed', err);
                    this._appendLocalAssistantEcho(
                        `Не удалось уведомить хост о действии: ${m}`,
                    );
                }
            });
            if (!ok) {
                this._appendLocalAssistantEcho(
                    'Не удалось открыть сущность: нет маршрута в приложении, неверный entity_id или чат без полноценного router.',
                );
            }
            return;
        }
        void this._tryDefaultEmbeddedLaraApply(payload).catch((err) => {
            const m = err instanceof Error ? err.message : String(err);
            console.warn('platform-embed-chat: Lara default apply rejected', err);
            this._appendLocalAssistantEcho(`Ошибка применения действия: ${m}`);
        });
        queueMicrotask(() => {
            try {
                this._emitAssistantEvent('action_invoked', payload);
            } catch (err) {
                const m = err instanceof Error ? err.message : String(err);
                console.warn('platform-embed-chat: action_invoked emit failed', err);
                this._appendLocalAssistantEcho(
                    `Не удалось уведомить хост о действии: ${m}`,
                );
            }
        });
    };

    /** @param {string} raw */
    _appendLocalAssistantEcho(raw) {
        const text = typeof raw === 'string' ? raw.trim() : '';
        if (!text) {
            return;
        }
        const msg = {
            id: `a_${++mid}`,
            role: 'assistant',
            content: text,
            streaming: false,
            reasoning: '',
            operatorReply: '',
            toolCalls: [],
            toolResults: [],
            blocks: [],
            inputRequired: null,
            breakpoint: null,
        };
        this._messages = [...this._messages, msg];
        this._stickToBottom = true;
        this.requestUpdate();
    }

    /** @param {unknown} body */
    _summarizeEmbeddedLaraApply(body) {
        if (!body || typeof body !== 'object') {
            return 'Готово.';
        }
        const o = /** @type {Record<string, unknown>} */ (body);
        const res = o.result;
        const resDict = res && typeof res === 'object' && !Array.isArray(res) ? /** @type {Record<string, unknown>} */ (res) : null;
        if (resDict) {
            const m = resDict.message;
            if (typeof m === 'string' && m.trim()) {
                return m.trim();
            }
            const ent = resDict.entity;
            const entDict = ent && typeof ent === 'object' && !Array.isArray(ent)
                ? /** @type {Record<string, unknown>} */ (ent)
                : null;
            if (entDict) {
                const nm = entDict.name;
                if (typeof nm === 'string' && nm.trim()) {
                    return nm.trim();
                }
            }
        }
        const st = o.status;
        if (st === 'applied') {
            return 'Действие применено.';
        }
        return 'Готово.';
    }

    /** @param {Response} resp @param {unknown} body */
    _embeddedLaraApplyHttpErrorText(resp, body) {
        const fb = `${resp.status} ${resp.statusText || ''}`.trim();
        if (!body || typeof body !== 'object') {
            return fb;
        }
        const detail = /** @type {Record<string, unknown>} */ (body).detail;
        if (typeof detail === 'string' && detail.trim()) {
            return detail.trim();
        }
        if (Array.isArray(detail)) {
            const parts = detail
                .map((item) => {
                    if (!item || typeof item !== 'object') {
                        return '';
                    }
                    const loc = Array.isArray(item.loc) ? item.loc.join('.') : '';
                    const msg = typeof item.msg === 'string' ? item.msg.trim() : '';
                    if (loc && msg) {
                        return `${loc}: ${msg}`;
                    }
                    return msg;
                })
                .filter((x) => x);
            if (parts.length > 0) {
                return parts.join('; ');
            }
        }
        return fb;
    }

    /** @param {Record<string, unknown>} payload */
    async _tryDefaultEmbeddedLaraApply(payload) {
        if (payload.action_kind !== 'apply') {
            return;
        }
        const pid = _normalizePendingActionIdFromPayload(payload);
        if (!pid) {
            this._appendLocalAssistantEcho(
                'Не удалось подтвердить действие: нет pending_action_id. Повторите шаг создания черновика в чате.',
            );
            return;
        }
        const root = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim().replace(/\/$/, '')) || '';
        if (!root) {
            this._appendLocalAssistantEcho(
                'Не задан flowsBaseUrl: нельзя применить действие Lara. Обратитесь к администратору.',
            );
            return;
        }
        const contextIdRaw = typeof this.getA2aContextId === 'function' ? this.getA2aContextId() : '';
        const contextId = typeof contextIdRaw === 'string' ? contextIdRaw.trim() : '';
        if (!contextId) {
            this._appendLocalAssistantEcho(
                'Нет идентификатора сессии чата — отправьте сообщение заново и снова нажмите «Создать заметку».',
            );
            return;
        }
        if (this._embeddedLaraApplyInFlight) {
            return;
        }

        this._embeddedLaraApplyInFlight = true;
        const url = `${root}/api/v1/lara/pending-actions/apply`;
        try {
            const heads = await this._outboundFlowsRequestHeaders();
            const resp = await fetch(url, {
                method: 'POST',
                credentials: this.useCredentials ? 'include' : 'omit',
                headers: {
                    'Content-Type': 'application/json',
                    Accept: 'application/json',
                    ...heads,
                },
                body: JSON.stringify({
                    pending_action_id: pid,
                    context_id: contextId,
                }),
            });
            /** @type {unknown} */
            let parsed = null;
            try {
                const rawText = await resp.text();
                if (rawText) {
                    parsed = JSON.parse(rawText);
                }
            } catch {
                parsed = null;
            }
            if (!resp.ok) {
                const errLine = `Не удалось применить действие (${this._embeddedLaraApplyHttpErrorText(resp, parsed)})`;
                this._appendLocalAssistantEcho(errLine);
                return;
            }
            this._appendLocalAssistantEcho(this._summarizeEmbeddedLaraApply(parsed));
        } catch (e) {
            const m = e instanceof Error ? e.message : String(e);
            this._appendLocalAssistantEcho(`Ошибка сети при применении: ${m}`);
        } finally {
            this._embeddedLaraApplyInFlight = false;
        }
    }

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

    /**
     * Исходящие заголовки к flows API (A2A, Lara apply, credentials): Authorization из getAuthToken
     * и X-Platform-Namespace из выбора CRM для company-id (localStorage/UI), см. core/clients/service_client.py.
     * @returns {Promise<Record<string, string>>}
     */
    async _outboundFlowsRequestHeaders() {
        const out = /** @type {Record<string, string>} */ ({});
        if (typeof this.getAuthToken === 'function') {
            const h = await this.getAuthToken();
            if (h && typeof h === 'object') {
                Object.assign(out, h);
            }
        }
        const cid = typeof this.companyId === 'string' ? this.companyId.trim() : '';
        if (cid !== '') {
            const ns = getActivePlatformNamespaceName(cid);
            if (typeof ns === 'string' && ns.trim() !== '') {
                out['X-Platform-Namespace'] = ns.trim();
            }
        }
        return out;
    }

    async _getEmbedAuthHeaders() {
        return this._outboundFlowsRequestHeaders();
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
        if (changed.has('flowId') || changed.has('branchId')) {
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
        if (e && typeof e.stopPropagation === 'function') {
            e.stopPropagation();
        }
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
            const extra = await this._outboundFlowsRequestHeaders();
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

        if (this._streamTtsAllowed()) {
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
        this._streamTaskPrimed = false;
        this._loading = true;
        this._sseOpen = true;
        this._pendingAssistantReplyNotify = true;
        this._stickToBottom = true;
        this._streamAbort = new AbortController();
        this.requestUpdate();

        const getHeaders = () => this._outboundFlowsRequestHeaders();

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
                if (_isEmbedGuestLimitMessage(m)) {
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

    _appendOperatorMessage(text) {
        const opMsg = {
            id: `op_${++mid}`,
            role: 'operator',
            content: text,
            operatorReply: '',
            blocks: [],
            toolCalls: [],
            toolResults: [],
        };
        this._messages = [...this._messages, opMsg];
    }

    _appendOperatorFiles(fileIds) {
        const lastOp = [...this._messages].reverse().find((m) => m.role === 'operator');
        if (lastOp) {
            const current = Array.isArray(lastOp.fileIds) ? lastOp.fileIds : [];
            this._messages = this._messages.map((m) => (
                m.id === lastOp.id ? { ...m, fileIds: [...current, ...fileIds] } : m
            ));
            return;
        }
        this._messages = [
            ...this._messages,
            {
                id: `op_${++mid}`,
                role: 'operator',
                content: '',
                fileIds,
                operatorReply: '',
                blocks: [],
                toolCalls: [],
                toolResults: [],
            },
        ];
    }

    _startResumeAssistantMessage(messageId, taskId, content) {
        this._patchMessage(messageId, { inputRequired: null, streaming: false });
        const resumeMsg = {
            id: `a_${++mid}`,
            role: 'assistant',
            content,
            streaming: true,
            reasoning: '',
            operatorReply: '',
            toolCalls: [],
            toolResults: [],
            blocks: [],
            inputRequired: null,
            breakpoint: null,
            taskId,
        };
        this._messages = [...this._messages, resumeMsg];
        this._activeStreamMessageId = resumeMsg.id;
    }

    _patchActiveAssistantFromRuntime(messageId, runtimeEvent) {
        const msg = this._findMessage(messageId);
        if (!msg) {
            return;
        }
        const payload = runtimeEvent.payload && typeof runtimeEvent.payload === 'object' ? runtimeEvent.payload : {};
        const taskId = typeof payload.task_id === 'string' ? payload.task_id : this._currentTaskId;
        if (runtimeEvent.type === 'task_started') {
            this._patchMessage(messageId, { taskId, streaming: true });
            return;
        }
        if (runtimeEvent.type === 'content_chunk') {
            const text = typeof payload.text === 'string' ? payload.text : '';
            if (msg.inputRequired) {
                this._startResumeAssistantMessage(messageId, taskId, text);
                return;
            }
            this._patchMessage(messageId, { content: `${typeof msg.content === 'string' ? msg.content : ''}${text}` });
            return;
        }
        if (runtimeEvent.type === 'reasoning_chunk') {
            const text = typeof payload.text === 'string' ? payload.text : '';
            this._patchMessage(messageId, { reasoning: `${typeof msg.reasoning === 'string' ? msg.reasoning : ''}${text}` });
            return;
        }
        if (runtimeEvent.type === 'activity') {
            this._patchMessage(messageId, { activity: typeof payload.text === 'string' ? payload.text : '' });
            return;
        }
        if (runtimeEvent.type === 'tool_calls') {
            const existing = Array.isArray(msg.toolCalls) ? msg.toolCalls : [];
            const incoming = Array.isArray(payload.tool_calls) ? payload.tool_calls : [];
            const add = incoming.filter((tc) => !existing.some((item) => item && item.id === tc.id));
            if (add.length > 0) {
                this._patchMessage(messageId, { toolCalls: [...existing, ...add] });
            }
            return;
        }
        if (runtimeEvent.type === 'tool_result') {
            const existing = Array.isArray(msg.toolResults) ? msg.toolResults : [];
            const tr = payload.tool_result && typeof payload.tool_result === 'object' ? payload.tool_result : null;
            if (tr && !existing.some((item) => item && item.id === tr.id)) {
                this._patchMessage(messageId, {
                    toolResults: [...existing, tr],
                    blocks: mergeBlocksFromToolResult(Array.isArray(msg.blocks) ? msg.blocks : [], tr),
                });
            }
            return;
        }
        if (runtimeEvent.type === 'completed') {
            const content = typeof payload.content === 'string' ? payload.content : '';
            const current = typeof msg.content === 'string' ? msg.content.trim() : '';
            this._patchMessage(messageId, {
                content: content.length > 0 && current.length === 0 ? content : msg.content,
                streaming: false,
                inputRequired: null,
            });
            return;
        }
        if (runtimeEvent.type === 'failed') {
            const error = typeof payload.error === 'string' && payload.error.length > 0 ? payload.error : 'Request failed';
            if (_isEmbedGuestLimitMessage(error)) {
                this._patchMessage(messageId, {
                    content: '',
                    streaming: false,
                    inputRequired: {
                        interruptKind: 'oauth_required',
                        question: error,
                        authUrl: '/login',
                    },
                });
            } else {
                this._patchMessage(messageId, { content: error, streaming: false, inputRequired: null });
            }
            return;
        }
        if (runtimeEvent.type === 'breakpoint') {
            this._patchMessage(messageId, {
                streaming: false,
                breakpoint: payload.breakpoint,
                inputRequired: null,
            });
            return;
        }
        if (runtimeEvent.type === 'input_required') {
            this._loading = false;
            this._patchMessage(messageId, {
                streaming: false,
                inputRequired: inputRequiredFieldsFromA2a(payload.message, payload.result_metadata),
            });
        }
    }

    _applyRuntimeEvent(runtimeEvent, messageId) {
        if (runtimeEvent.type === 'operator_reply') {
            const text = typeof runtimeEvent.payload?.text === 'string' ? runtimeEvent.payload.text : '';
            this._appendOperatorMessage(text);
            return;
        }
        if (runtimeEvent.type === 'operator_files') {
            const fileIds = Array.isArray(runtimeEvent.payload?.file_ids) ? runtimeEvent.payload.file_ids : [];
            this._appendOperatorFiles(fileIds);
            return;
        }
        if (runtimeEvent.type === 'files_event') {
            const eventPayload = runtimeEvent.payload?.event?.payload;
            const files = eventPayload && typeof eventPayload === 'object' && Array.isArray(eventPayload.files)
                ? eventPayload.files
                : [];
            if (files.length > 0) {
                const msg = Array.isArray(this._messages)
                    ? this._messages.find((item) => item && item.id === messageId)
                    : null;
                this._patchMessage(messageId, {
                    files: _upsertEmbedFiles(Array.isArray(msg?.files) ? msg.files : [], files),
                });
            }
            return;
        }
        if (runtimeEvent.type === 'ui_event') {
            const uiEvent = runtimeEvent.payload?.event;
            if (uiEvent && typeof uiEvent === 'object') {
                this._emitUiEvents([uiEvent], messageId);
            }
            return;
        }
        this._patchActiveAssistantFromRuntime(messageId, runtimeEvent);
    }

    _handleEvent(event, messageId) {
        const result = event && typeof event === 'object' ? event.result : null;
        if (!result || typeof result !== 'object') {
            return;
        }
        feedStreamTtsFromA2aResult(result);
        const mapped = mapA2aResultToChatRuntimeEvents(result, {
            contextId: this._contextId,
            currentTaskId: this._currentTaskId,
            taskPrimed: this._streamTaskPrimed,
        });
        this._streamTaskPrimed = mapped.taskPrimed;
        if (mapped.nextTaskId) {
            this._currentTaskId = mapped.nextTaskId;
        }
        const resolvedContextId = resolveA2aContextId(result, this._contextId);
        if (resolvedContextId) {
            this._contextId = resolvedContextId;
        }
        const targetMessageId = this._activeStreamMessageId ? this._activeStreamMessageId : messageId;
        for (const runtimeEvent of mapped.events) {
            this._applyRuntimeEvent(runtimeEvent, targetMessageId);
        }
        this.requestUpdate();
    }

    _newChat() {
        this._pendingAssistantReplyNotify = false;
        this._greetingTypingRunId += 1;
        this._contextId = `${Date.now()}`;
        this._currentTaskId = null;
        this._streamTaskPrimed = false;
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

        const files = this._sessionFilesForSharedPanel();

        return html`
            ${head}
            <div class="embed-chat-content">
                ${credBadges}
                ${files.length > 0
                    ? html`
                          <flows-chat-files-panel
                              .files=${files}
                              active-company-id=${this.companyId || ''}
                              document-base-url=${this._embedDocumentBaseUrl()}
                          ></flows-chat-files-panel>
                      `
                    : nothing}
                <div class="scroll" @scroll=${this._onScrollAreaScroll}>
                    ${this._messages.map((m) => this._renderChatSurfaceMessage(m))}
                </div>
                <embed-chat-input
                    .loading=${this._loading}
                    .cancelBusy=${this._cancelBusy}
                    placeholder=${this._lb('placeholder', 'Message...')}
                    .labels=${this._mergedLabels()}
                    .enableVoice=${this.enableVoice}
                    .voiceDuplex=${this.voiceDuplex}
                    .voiceActive=${this.voiceComposerActive}
                    voice-status=${this.voiceComposerStatus || 'idle'}
                    .showLocaleControl=${this.showLocaleControl}
                    interface-locale=${this.interfaceLocale || 'auto'}
                    @embed-locale-change=${this._onEmbedLocaleChange}
                    @embed-send=${this._onSend}
                    @embed-stop=${this._onEmbedStop}
                ></embed-chat-input>
            </div>
        `;
    }

    _embedDocumentBaseUrl() {
        return (
            _normalizedPlatformUiOrigin(this.platformUiOrigin)
            || _platformApexOriginFromFlowsBaseUrl(this.flowsBaseUrl)
        );
    }

    _fileFromPanelBlock(block) {
        if (!block || typeof block !== 'object' || block.type !== 'file_card') {
            return null;
        }
        const root = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim()) || '';
        const normalized = normalizeFlowChatBlockForFlowsUrls(block, root);
        const document =
            normalized.document && typeof normalized.document === 'object' && !Array.isArray(normalized.document)
                ? normalized.document
                : null;
        const capabilities =
            normalized.capabilities && typeof normalized.capabilities === 'object' && !Array.isArray(normalized.capabilities)
                ? { ...normalized.capabilities }
                : {};
        const editorUrl = _embedString(normalized.editor_url);
        if (document) {
            capabilities.document = document;
        } else if (editorUrl.length > 0) {
            capabilities.document = {
                binding_id: _embedString(normalized.binding_id),
                file_id: _embedString(normalized.file_id),
                catalog_id: _embedString(normalized.catalog_id),
                document_type: _embedString(normalized.document_type),
                title: _embedString(normalized.name || normalized.original_name),
                namespace: _embedString(normalized.namespace),
                editor_url: editorUrl,
                editable: true,
            };
        }
        return {
            file_id: _embedString(normalized.file_id),
            original_name: _embedString(normalized.original_name || normalized.name),
            content_type: _embedString(normalized.content_type || normalized.mime_type),
            file_size: Number(normalized.file_size || normalized.size) || 0,
            url: _embedString(normalized.url || normalized.preview_url),
            capabilities,
            document: capabilities.document || null,
        };
    }

    _sessionFilesForSharedPanel() {
        let files = [];
        const root = String(this.flowsBaseUrl || '').replace(/\/$/, '');
        for (const message of Array.isArray(this._messages) ? this._messages : []) {
            files = _upsertEmbedFiles(files, Array.isArray(message.files) ? message.files : []);
            for (const fid of Array.isArray(message.fileIds) ? message.fileIds : []) {
                const id = _embedString(fid);
                if (id.length === 0) {
                    continue;
                }
                files = _upsertEmbedFiles(files, [{
                    file_id: id,
                    original_name: this._lb('operator_files', 'Attached files'),
                    url: root ? `${root}/api/v1/files/download/${encodeURIComponent(id)}` : '',
                }]);
            }
            for (const block of Array.isArray(message.blocks) ? message.blocks : []) {
                const file = this._fileFromPanelBlock(block);
                if (file) {
                    files = _upsertEmbedFiles(files, [file]);
                }
            }
        }
        return files.filter((file) => _embedFileKey(file).length > 0);
    }

    _renderChatSurfaceMessage(m) {
        const labels = this._mergedLabels();
        const flowsRoot = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim()) || '';
        return html`
            <flows-chat-message
                variant="embed"
                data-role=${m.role || 'assistant'}
                .role=${m.role || 'assistant'}
                .content=${m.content || ''}
                ?streaming=${Boolean(m.streaming)}
                .reasoning=${m.reasoning || ''}
                .activity=${m.activity || ''}
                .toolCalls=${Array.isArray(m.toolCalls) ? m.toolCalls : []}
                .toolResults=${Array.isArray(m.toolResults) ? m.toolResults : []}
                .browserPreviews=${Array.isArray(m.browserPreviews) ? m.browserPreviews : []}
                .inputRequired=${m.inputRequired || null}
                .operatorReply=${m.operatorReply || ''}
                .breakpoint=${m.breakpoint || null}
                .files=${Array.isArray(m.files) ? m.files : []}
                .filesMeta=${Array.isArray(m.filesMeta) ? m.filesMeta : []}
                .fileIds=${Array.isArray(m.fileIds) ? m.fileIds : []}
                .blocks=${Array.isArray(m.blocks) ? m.blocks : []}
                .taskId=${m.taskId || ''}
                .labels=${labels}
                .flowRoot=${flowsRoot}
                .useCredentials=${this.useCredentials}
                .voiceBaseUrl=${this._embedAssistantTtsVoiceBaseUrl()}
                .getHeaders=${typeof this.getAuthToken === 'function' ? this.getAuthToken : null}
                .showAvatar=${false}
                .showHeader=${false}
                .showTraceControls=${false}
                @compose-edit=${this._onEmbedComposeEdit}
            ></flows-chat-message>
        `;
    }
}

customElements.define('platform-embed-chat', PlatformEmbedChat);

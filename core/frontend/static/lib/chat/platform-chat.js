import { LitElement, html, css, nothing } from '../lit-shim.js';
import { ChatController, TtsOnlyStreamLifecycle } from './runtime/chat-controller.js';
import { createChatProfile, resolveChatViewConfig, fetchChatProfile } from './runtime/chat-profile.js';
import { OperatorConversationTransport } from './runtime/operator-conversation-transport.js';
import { crmA2aInterfaceLanguageVariables, embedChatLabelsForLang } from './chat-default-labels.js';
import { readEmbedChatUrlParams, applyEmbedChatDrawerSizeVars } from './chat-url-params.js';
import { resolveEmbedChatTheme } from './chat-theme.js';
import { mergeBlocksFromToolResult } from './tool-result-blocks.js';
import { normalizeChatAuthor } from './chat-author.js';
import { normalizeFlowChatBlockForPlatformUrls, CANONICAL_FILES_DOWNLOAD_PREFIX } from './flows-url-rewrite.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import {
    readTtsOutputEnabled,
    toggleTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '../voice/tts-output-pref.js';
import {
    resolveVoiceHttpOrigin,
    resolveVoiceHttpOriginFromFlowsBaseUrl,
} from '../voice/voice-http-origin.js';
import { VoiceMediaSession } from '../voice/voice-media-session.js';
import { VoiceAgentBridge } from '../voice/voice-agent-bridge.js';
import { disposeVoiceMediaThenBridge } from '../voice/dispose-voice-session.js';
import { normalizeVoiceLocaleForWs } from '../voice/normalize-voice-locale.js';
import { fetchFlowVoiceSessionQueryDict } from '../voice/fetch-flow-voice-session-query.js';
import {
    primeStreamTtsPlaybackFromUserGesture,
    stopStreamTtsPlayback,
    setStreamTtsTarget,
} from '../voice/stream-tts-registry.js';
import './chat-message.js';
import './chat-files-panel.js';
import './chat-input.js';
import { getActivePlatformNamespaceName } from '../utils/platform-namespace.js';
import { getPlatformBus, hasPlatformBus } from '../events/bus-singleton.js';
import { bootstrapPlatformBus, completeBootstrap } from '../events/bootstrap.js';
import { CoreEvents } from '../events/contract.js';
import {
    readLaraLauncherPosition,
    writeLaraLauncherPosition,
} from './launcher-position-preference.js';

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
function _routeKeyForOpenEntityContext(raw) {
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
    const routeKey = _routeKeyForOpenEntityContext(etStr);
    if (
        !routesRaw.some((r) => r && typeof r === 'object' && /** @type {{ key?: string }} */ (r).key === routeKey)
    ) {
        return false;
    }
    bus.dispatch(
        CoreEvents.ROUTER_NAVIGATE_REQUESTED,
        { routeKey, params: { itemId: rid } },
        { source: 'platform_chat_open_entity' },
    );
    return true;
}

/**
 * Core-компоненты (platform-assistant-message-actions и др.) расширяют PlatformElement,
 * который в connectedCallback требует getPlatformBus. Полноценного PlatformApp на внешнем
 * сайте нет — поднимаем один EventBus синхронно до super.connectedCallback.
 */
function ensurePlatformBusForStandaloneChat(flowsBaseUrl, platformUiOrigin) {
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

function _chatString(value) {
    return typeof value === 'string' ? value : value == null ? '' : String(value);
}

function _panelFileKey(file) {
    if (!file || typeof file !== 'object') {
        return '';
    }
    return (
        _chatString(file.file_id)
        || _chatString(file.url)
        || _chatString(file.preview_url)
        || _chatString(file.original_name)
    );
}

function _upsertPanelFiles(existing, incoming) {
    const out = Array.isArray(existing) ? [...existing] : [];
    const index = new Map();
    out.forEach((file, i) => {
        const key = _panelFileKey(file);
        if (key) {
            index.set(key, i);
        }
    });
    for (const file of Array.isArray(incoming) ? incoming : []) {
        if (!file || typeof file !== 'object') {
            continue;
        }
        const key = _panelFileKey(file);
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
 * Единый чат-компонент платформы (Chat Surface 2.0).
 *
 * Один `<platform-chat>` обслуживает все поверхности: SPA-страницу чата, панель
 * редактора/хелперов и drawer-виджет на внешнем сайте. Режим задаётся ТОЛЬКО
 * параметрами — отдельных «embed»/«lara» компонентов не существует.
 *
 * Параметры:
 * - profile: `spa | editor_test | embed_public | embed_preview` — возможности точки
 *   монтирования (см. chat/runtime/chat-profile.js). `editor_test` показывает всё.
 * - display: `page | panel | drawer`. `drawer` включает FAB, slide-панель, drag,
 *   maximize/fullscreen и unread-бейдж (бывший platform-embed-chat-drawer).
 * - Идентификаторы: flow-id/branch-id ИЛИ embed-id; flows-base-url, platform-ui-origin.
 * - Auth: use-credentials (cookie) или .getAuthToken → async () => ({ Authorization }).
 * - Policy: `.chatPolicy` (FlowConfig.chat, snake_case) — если хост уже знает её;
 *   иначе компонент сам грузит GET …/chat-profile (flow или embed auth-путь) и
 *   берёт оттуда policy + look (theme/assistant_title/placeholder/voice.*).
 * - Voice: enable-voice + voice-enabled (duplex WS), voice-default-on, voice-base-url, company-id.
 * - Внешний контракт: event-namespace envelope `assistant:event` + acks,
 *   actionHandlers, conversation-key, getExtraMetadataVariables/getContextVariables,
 *   toggle-event-name (drawer), `humanitec-embed-*` события — без изменений
 *   (external-embed-event-contract-v1).
 *
 * Состояние — только через ChatController (chat/runtime): pure reducer chat-state.js
 * + один SSE-клиент a2a-stream.js. Видимость элементов — только через viewConfig
 * (resolveChatViewConfig(profile, policy)), не через отдельные boolean-props.
 */
export class PlatformChat extends LitElement {
    static properties = {
        profile: { type: String },
        display: { type: String },
        flowsBaseUrl: { type: String, attribute: 'flows-base-url' },
        platformUiOrigin: { type: String, attribute: 'platform-ui-origin' },
        flowId: { type: String, attribute: 'flow-id' },
        embedId: { type: String, attribute: 'embed-id' },
        workItemId: { type: String, attribute: 'work-item-id' },
        interactionPolicy: { type: Object, attribute: 'interaction-policy' },
        branchId: { type: String, attribute: 'branch-id' },
        assistantTitle: { type: String, attribute: 'assistant-title' },
        labels: { type: Object },
        chatPolicy: { type: Object },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        voiceEnabled: { type: Boolean, attribute: 'voice-enabled' },
        voiceDefaultOn: { type: Boolean, attribute: 'voice-default-on' },
        voiceBaseUrl: { type: String, attribute: 'voice-base-url' },
        companyId: { type: String, attribute: 'company-id' },
        theme: { type: String },
        interfaceLocale: { type: String, attribute: 'interface-locale' },
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        hideHeader: { type: Boolean, attribute: 'hide-header' },
        eventNamespace: { type: String, attribute: 'event-namespace' },
        conversationKey: { type: String, attribute: 'conversation-key' },
        eventAckRetries: { type: Number, attribute: 'event-ack-retries' },
        eventAckTimeoutMs: { type: Number, attribute: 'event-ack-timeout-ms' },
        getExtraMetadataVariables: { type: Object },
        getContextVariables: { type: Object },
        getSendMetadata: { type: Object },
        freshContextPerTurn: { type: Boolean, attribute: 'fresh-context-per-turn' },
        actionHandlers: { type: Object },
        getAuthToken: { type: Object },
        open: { type: Boolean, reflect: true },
        showLauncher: { type: Boolean, attribute: 'show-launcher' },
        launcherStorageScope: { type: String, attribute: 'launcher-storage-scope' },
        initialOpen: { type: Boolean, attribute: 'initial-open' },
        toggleEventName: { type: String, attribute: 'toggle-event-name' },
        panelMaximized: { type: Boolean, state: true },
        fabUnreadCount: { type: Number, state: true },
        _voiceOn: { state: true },
        _voiceStatus: { state: true },
        _credentials: { state: true },
        _credPopover: { state: true },
        _greeting: { state: true },
        _viewConfig: { state: true },
    };

    static styles = css`
        :host {
            display: flex;
            flex-direction: column;
            height: 100%;
            min-height: 200px;
            font-family: var(--font-sans);
            color: var(--platform-chat-text);
            background: var(--platform-chat-page-bg);
            border-radius: 0;
            border: none;
            overflow: hidden;
        }
        :host([display='drawer']) {
            display: contents;
        }
        header.surface-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 4px 4px 12px 8px;
            border-bottom: 1px solid var(--platform-chat-border);
            font-weight: 600;
            font-size: 15px;
            border-radius: 0;
        }
        .surface {
            position: relative;
            display: flex;
            flex-direction: column;
            flex: 1;
            min-height: 0;
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
            --flows-chat-radius: var(--platform-chat-radius);
            --flows-chat-text: var(--platform-chat-text);
            --flows-chat-muted: var(--platform-chat-muted);
            --flows-chat-secondary: var(--platform-chat-muted);
            --flows-chat-border: var(--platform-chat-border);
            --flows-chat-surface: var(--platform-chat-surface);
            --flows-chat-surface-subtle: var(--platform-chat-surface-subtle);
            --flows-chat-accent: var(--platform-chat-accent);
            --flows-chat-accent-muted: var(--platform-chat-accent-muted);
            --flows-chat-on-accent: var(--platform-chat-on-accent);
            --flows-chat-info-bg: var(--platform-chat-interrupt-bg);
            --flows-chat-info-border: var(--platform-chat-accent);
        }
        flows-chat-message[data-role='user'] {
            align-self: flex-end;
        }
        button.link {
            background: transparent;
            border: none;
            color: var(--platform-chat-accent);
            cursor: pointer;
            font-size: 13px;
            padding: 0;
            border-radius: var(--platform-chat-radius);
        }
        .suggested-prompts {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            padding: 0 4px 10px;
        }
        .suggested-prompt {
            border: 1px solid var(--platform-chat-border);
            background: var(--platform-chat-surface);
            color: var(--platform-chat-text);
            border-radius: 999px;
            padding: 7px 14px;
            font-size: 13px;
            cursor: pointer;
            transition: background 0.15s ease;
        }
        .suggested-prompt:hover {
            background: var(--platform-chat-accent-muted);
        }
        .chat-composer {
            border-top: 1px solid var(--platform-chat-border);
            padding: 12px 0 0;
            background: transparent;
        }
        .chat-composer flows-chat-input {
            --flows-chat-input-max-width: none;
            --flows-chat-input-margin: 0;
            --flows-chat-input-min-height: 52px;
            --flows-chat-input-padding: 0;
            --flows-chat-input-body-padding: 10px 12px 2px;
            --flows-chat-input-toolbar-padding: 2px 6px 6px;
            --flows-chat-input-toolbar-gap: 6px;
            --flows-chat-input-gap: 6px;
            --flows-chat-input-radius: var(--radius-2xl, 24px);
            --flows-chat-input-bg: var(--platform-chat-composer-bg);
            --flows-chat-input-border: var(--platform-chat-border);
            --flows-chat-input-text: var(--platform-chat-text);
            --flows-chat-input-muted: var(--platform-chat-muted);
            --flows-chat-input-accent: var(--platform-chat-accent);
            --flows-chat-input-button-size: 36px;
            --flows-chat-input-button-radius: 50%;
            --flows-chat-input-button-bg: var(--platform-chat-surface);
            --flows-chat-input-button-hover-bg: var(--platform-chat-surface-hover);
            --flows-chat-input-button-color: var(--platform-chat-text);
            --flows-chat-input-button-hover-color: var(--platform-chat-text);
            --flows-chat-input-active-bg: var(--platform-chat-accent-muted);
            --flows-chat-input-active-color: var(--platform-chat-text);
            --flows-chat-input-send-size: 36px;
            --flows-chat-input-send-radius: 50%;
            --flows-chat-input-send-bg: var(--platform-chat-accent);
            --flows-chat-input-send-color: var(--platform-chat-on-accent);
            --flows-chat-input-send-shadow: none;
            --flows-chat-input-send-hover-shadow: none;
            --flows-chat-input-chip-bg: var(--platform-chat-surface);
            --flows-chat-input-file-radius: 999px;
            --flows-chat-input-file-padding: 4px 8px;
            --flows-chat-input-danger: rgba(229, 57, 53, 0.9);
            --flows-chat-input-danger-bg: var(--platform-chat-input-bg);
            --flows-chat-input-textarea-max-height: 140px;
            --flows-chat-input-textarea-font-size: 15px;
            --flows-chat-input-textarea-padding: 0;
            --flows-chat-input-locale-max-width: 120px;
        }
        .cred-badges {
            position: absolute;
            top: 8px;
            right: 8px;
            z-index: 5;
            display: flex;
            gap: 4px;
            pointer-events: all;
        }
        .cred-anchor {
            position: relative;
        }
        .cred-badge {
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
        .cred-badge:hover {
            transform: scale(1.15);
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35);
        }
        .cred-popover {
            position: absolute;
            top: calc(100% + 6px);
            right: 0;
            min-width: 160px;
            background: var(--platform-chat-surface);
            border: 1px solid var(--platform-chat-border);
            border-radius: 8px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
            padding: 10px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            z-index: 100;
        }
        .cred-popover-title {
            font-size: 13px;
            font-weight: 500;
            color: var(--platform-chat-text);
        }
        .cred-disconnect {
            background: none;
            border: 1px solid #e53935;
            color: #e53935;
            border-radius: 4px;
            padding: 4px 12px;
            font-size: 12px;
            cursor: pointer;
            transition: background 0.15s ease, color 0.15s ease;
        }
        .cred-disconnect:hover {
            background: #e53935;
            color: #fff;
        }

        /* ---------- display="drawer": FAB + slide-панель ---------- */
        .fab {
            position: fixed;
            z-index: 25000;
            right: max(16px, env(safe-area-inset-right, 0px));
            bottom: max(16px, env(safe-area-inset-bottom, 0px));
            width: 56px;
            height: 56px;
            border-radius: 50%;
            border: 1px solid var(--platform-chat-drawer-fab-border);
            background: var(--platform-chat-drawer-fab-bg);
            color: var(--platform-chat-drawer-fab-fg);
            box-shadow: var(--platform-chat-drawer-fab-shadow);
            cursor: pointer;
            touch-action: none;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            box-sizing: border-box;
            transition:
                transform 0.18s ease,
                background 0.18s ease,
                border-color 0.18s ease,
                box-shadow 0.18s ease;
        }
        :host([data-embed-position='bottom-left']) .fab {
            right: auto;
            left: max(16px, env(safe-area-inset-left, 0px));
        }
        .fab-badge {
            position: absolute;
            top: 2px;
            right: 2px;
            min-width: 18px;
            height: 18px;
            padding: 0 5px;
            box-sizing: border-box;
            border-radius: 9px;
            background: #e53935;
            color: #fff;
            font-size: 11px;
            font-weight: 700;
            line-height: 18px;
            text-align: center;
            pointer-events: none;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.28);
        }
        .fab:hover {
            background: var(--platform-chat-drawer-fab-bg-hover);
            border-color: rgba(255, 255, 255, 0.22);
            transform: translateY(-1px) scale(1.03);
        }
        .fab:active {
            transform: scale(0.98);
        }
        .fab-logo {
            width: 42px;
            height: 42px;
            display: block;
            object-fit: contain;
            pointer-events: none;
            filter: drop-shadow(0 0 10px rgba(255, 180, 220, 0.22));
        }
        @media (max-width: 767px) {
            .fab {
                width: 52px;
                height: 52px;
                right: max(12px, env(safe-area-inset-right, 0px));
                bottom: max(12px, env(safe-area-inset-bottom, 0px));
            }
        }
        .panel {
            position: fixed;
            z-index: 24995;
            top: max(12px, env(safe-area-inset-top, 0px));
            right: max(12px, env(safe-area-inset-right, 0px));
            bottom: max(12px, env(safe-area-inset-bottom, 0px));
            left: auto;
            height: auto;
            width: var(
                --embed-panel-width,
                min(calc(100vw - 24px), max(320px, min(52vw, 440px)))
            );
            max-height: var(--embed-panel-max-height, calc(100dvh - 24px));
            box-sizing: border-box;
            padding: 14px 14px 16px;
            display: flex;
            flex-direction: column;
            gap: 10px;
            border-radius: var(--platform-chat-drawer-radius);
            background: var(--platform-chat-panel-bg);
            border: 1px solid var(--platform-chat-panel-border);
            box-shadow: var(--platform-chat-panel-shadow);
            backdrop-filter: blur(var(--glass-blur-strong, 60px));
            -webkit-backdrop-filter: blur(var(--glass-blur-strong, 60px));
            opacity: 1;
            transform: translate3d(0, 0, 0);
            transition:
                opacity 0.32s cubic-bezier(0.22, 1, 0.36, 1),
                transform 0.38s cubic-bezier(0.22, 1, 0.36, 1),
                top 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                right 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                bottom 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                left 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                width 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                max-height 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                border-radius 0.38s cubic-bezier(0.22, 1, 0.36, 1),
                box-shadow 0.38s ease,
                visibility 0s linear 0s;
        }
        :host([data-embed-position='bottom-left']) .panel {
            right: auto;
            left: max(12px, env(safe-area-inset-left, 0px));
        }
        .panel.panel--collapsed {
            opacity: 0;
            transform: translate3d(calc(100% + 28px), 0, 0);
            pointer-events: none;
            visibility: hidden;
            transition:
                opacity 0.28s cubic-bezier(0.22, 1, 0.36, 1),
                transform 0.36s cubic-bezier(0.22, 1, 0.36, 1),
                top 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                right 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                bottom 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                left 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                width 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                max-height 0.42s cubic-bezier(0.22, 1, 0.36, 1),
                border-radius 0.38s cubic-bezier(0.22, 1, 0.36, 1),
                box-shadow 0.38s ease,
                visibility 0s linear 0.36s;
        }
        :host([data-embed-position='bottom-left']) .panel.panel--collapsed {
            transform: translate3d(calc(-100% - 28px), 0, 0);
        }
        @media (prefers-reduced-motion: reduce) {
            .panel,
            .panel.panel--collapsed,
            .panel:fullscreen {
                transition-duration: 0.01ms !important;
                transition-delay: 0s !important;
            }
        }
        .panel-head {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
            padding: 4px 4px 12px 8px;
            border-bottom: 1px solid var(--platform-chat-panel-border);
        }
        .panel-head.panel-head--draggable {
            cursor: grab;
            user-select: none;
        }
        .panel-head.panel-head--dragging {
            cursor: grabbing;
        }
        .panel-head-title {
            flex: 1;
            min-width: 0;
            font-weight: 600;
            font-size: 15px;
            color: var(--platform-chat-text);
        }
        .panel-head-actions {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
        }
        .close-btn {
            width: 44px;
            height: 44px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: var(--platform-chat-drawer-radius);
            border: 1px solid var(--platform-chat-panel-border);
            background: var(--platform-chat-drawer-close-bg);
            color: var(--platform-chat-drawer-close-fg);
            cursor: pointer;
            padding: 0;
        }
        .close-btn:hover {
            background: var(--platform-chat-drawer-close-hover);
        }
        .close-btn svg {
            width: 18px;
            height: 18px;
            display: block;
        }
        .panel .drawer-chat {
            flex: 1;
            min-height: 0;
            display: flex;
            flex-direction: column;
            color: var(--platform-chat-text);
        }
        @media (min-width: 768px) {
            .panel.panel--maximized {
                top: max(24px, env(safe-area-inset-top, 0px));
                right: max(24px, env(safe-area-inset-right, 0px));
                bottom: max(24px, env(safe-area-inset-bottom, 0px));
                left: max(24px, env(safe-area-inset-left, 0px));
                width: auto;
                height: auto;
                max-height: none;
                border-radius: min(var(--platform-chat-drawer-radius), 20px);
            }
        }
        @media (max-width: 767px) {
            .panel.panel--maximized {
                top: max(0px, env(safe-area-inset-top, 0px));
                right: max(0px, env(safe-area-inset-right, 0px));
                bottom: max(0px, env(safe-area-inset-bottom, 0px));
                left: max(0px, env(safe-area-inset-left, 0px));
                width: auto;
                height: auto;
                max-height: none;
                border-radius: min(var(--platform-chat-drawer-radius), 20px);
            }
        }
        .panel:fullscreen {
            top: 0;
            right: 0;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 100%;
            max-height: none;
            border-radius: 0;
            padding: max(14px, env(safe-area-inset-top, 0px)) max(14px, env(safe-area-inset-right, 0px))
                max(16px, env(safe-area-inset-bottom, 0px)) max(14px, env(safe-area-inset-left, 0px));
            transition:
                opacity 0.32s cubic-bezier(0.22, 1, 0.36, 1),
                transform 0.38s cubic-bezier(0.22, 1, 0.36, 1),
                top 0.45s cubic-bezier(0.22, 1, 0.36, 1),
                right 0.45s cubic-bezier(0.22, 1, 0.36, 1),
                bottom 0.45s cubic-bezier(0.22, 1, 0.36, 1),
                left 0.45s cubic-bezier(0.22, 1, 0.36, 1),
                width 0.45s cubic-bezier(0.22, 1, 0.36, 1),
                height 0.45s cubic-bezier(0.22, 1, 0.36, 1),
                max-height 0.45s cubic-bezier(0.22, 1, 0.36, 1),
                border-radius 0.4s cubic-bezier(0.22, 1, 0.36, 1),
                padding 0.4s cubic-bezier(0.22, 1, 0.36, 1),
                box-shadow 0.38s ease,
                visibility 0s linear 0s;
        }
    `;

    constructor() {
        super();
        this.profile = 'embed_public';
        this.display = 'page';
        this.flowsBaseUrl = '';
        this.platformUiOrigin = '';
        this.flowId = '';
        this.embedId = '';
        /** WorkItem(operator_handoff) id — идентификатор поверхности профиля operator_handoff. */
        this.workItemId = '';
        /** @type {object|null} interaction_policy задачи (mode/can_send/can_complete/conversation). */
        this.interactionPolicy = null;
        this.branchId = '';
        this.assistantTitle = '';
        this.labels = {};
        /** @type {object|null} FlowConfig.chat (snake_case); null — грузится из chat-profile */
        this.chatPolicy = null;
        this.useCredentials = false;
        this.enableVoice = true;
        this.voiceEnabled = false;
        this.voiceDefaultOn = false;
        this.voiceBaseUrl = '';
        this.companyId = '';
        this.theme = 'auto';
        this.interfaceLocale = 'auto';
        this.showLocaleControl = false;
        this.hideHeader = false;
        this.eventNamespace = 'assistant';
        this.conversationKey = '';
        this.eventAckRetries = 0;
        this.eventAckTimeoutMs = 2500;
        this.getExtraMetadataVariables = undefined;
        this.getContextVariables = undefined;
        /** Хост-metadata верхнего уровня A2A message/stream (например breakpoints редактора). */
        this.getSendMetadata = undefined;
        /** Каждый ход — новая сессия (editor test run без persist context). */
        this.freshContextPerTurn = false;
        this.getAuthToken = undefined;
        this.actionHandlers = {};
        this.open = false;
        this.showLauncher = false;
        this.launcherStorageScope = 'core';
        this.initialOpen = false;
        this.toggleEventName = 'humanitec-embed-chat-toggle';
        this.panelMaximized = false;
        this.fabUnreadCount = 0;

        /** @type {InstanceType<typeof OperatorConversationTransport>|null} operator_handoff транспорт. */
        this._operatorTransport = null;
        this._operatorHistoryLoaded = false;

        /** @type {InstanceType<typeof ChatController>} */
        this._controller = new ChatController({
            target: this._controllerTarget(),
            getHeaders: () => this._outboundFlowsRequestHeaders(),
            credentials: 'omit',
            onChange: () => {
                this._syncHitlLiveTail();
                this.requestUpdate();
                this.dispatchEvent(new CustomEvent('chat-state-changed', { bubbles: true, composed: true }));
            },
            onUiEvent: (uiEvent, meta) => this._onControllerUiEvent(uiEvent, meta),
            onRunEvent: (type, payload) => this._emitChatRunEvent(type, payload),
        });
        this._controller.initSession({});

        /** look из chat-profile (embed): theme, assistant_title, placeholder, voice_*, position */
        this._look = null;
        /** @type {object|null} */
        this._fetchedPolicy = null;
        this._chatProfileRequested = false;
        this._viewConfig = this._resolveViewConfig();

        /** Блоки из ui_event по taskId (мерж в активное сообщение при рендере). */
        this._uiBlocksByTaskId = {};

        /** Greeting-пузырь: локальная презентация, не часть runtime state. */
        this._greeting = null;
        this._greetingTypingRunId = 0;
        this._greetingStarted = false;

        this._stickToBottom = true;
        this._pendingAssistantReplyNotify = false;
        this._laraApplyInFlight = false;

        /** @type {Array<{provider:string, service:string, created_at?:string}>} */
        this._credentials = [];
        this._credPopover = null;
        this._uiEventDispatchKeys = new Set();
        this._pendingEventAcks = new Map();
        this._boundAckListener = (event) => this._handleHostEventAck(event, true);
        this._boundNackListener = (event) => this._handleHostEventAck(event, false);
        this._ackEventName = null;
        this._nackEventName = null;
        this._onCredClickOutside = this._onCredClickOutside.bind(this);

        /** Voice duplex (микрофон, WS-эфир) — бывшая оркестрация drawer. */
        this._voiceOn = false;
        this._voiceStatus = 'idle';
        /** @type {InstanceType<typeof VoiceMediaSession>|null} */
        this._voiceMedia = null;
        /** @type {InstanceType<typeof VoiceAgentBridge>|null} */
        this._voiceBridge = null;
        this._voiceDisconnectExpected = false;
        /** @type {ReturnType<typeof setTimeout>|null} */
        this._voiceReconnectAfterCloseTimer = null;
        /** @type {{ contextId: string|null, taskId: string|null, taskPrimed: boolean }|null} */
        this._voiceStreamState = null;
        /** @type {Record<string, unknown>|null} */
        this._voicePendingStreamMetadata = null;

        this._ttsOnly = new TtsOnlyStreamLifecycle({
            isAllowed: () => this._ttsOnlyAllowed(),
            getWsBase: () => this._resolvedVoiceHttpBaseForStream(),
            getCompanyId: () => String(this.companyId || '').trim(),
            getWsQuery: () => this._mergeTtsOnlyWsQuery(),
            readTtsEnabled: readTtsOutputEnabled,
            onError: (err) => this._emitVoiceError('voice/tts_stream_connect_failed', err),
        });

        this._onTtsPref = () => {
            this.requestUpdate();
            this._syncStreamTtsAfterPrefChange();
        };
        this._onTtsStorage = (e) => {
            if (e.storageArea === window.localStorage && e.key === TTS_OUTPUT_STORAGE_KEY) {
                this.requestUpdate();
                this._syncStreamTtsAfterPrefChange();
            }
        };

        /* drawer chrome */
        /** @type {(() => void) | null} */
        this._boundToggle = null;
        /** @type {string | null} */
        this._toggleListenerEventName = null;
        /** @type {(() => void) | null} */
        this._onPlatformThemeChange = null;
        /** @type {(() => void) | null} */
        this._onPopStateEmbedParams = null;
        /** @type {(() => void) | null} */
        this._onFullscreenChange = null;
        this._panelNativeFullscreen = false;
        this._drawerOwnsNativeFullscreen = false;
        this._layerBaseZIndex = nextModalLayerZIndex();
        this._panelDragActive = false;
        this._panelDragPosition = null;
        this._panelDragContext = null;
        this._fabDragPosition = null;
        this._fabDragContext = null;
        this._fabDragActive = false;
        this._suppressFabClick = false;
        this._initialOpenConsumed = false;
        this._onPanelDragPointerMove = this._onPanelDragPointerMove.bind(this);
        this._onPanelDragPointerUp = this._onPanelDragPointerUp.bind(this);
        this._onFabDragPointerMove = this._onFabDragPointerMove.bind(this);
        this._onFabDragPointerUp = this._onFabDragPointerUp.bind(this);
        this._onViewportResize = this._onViewportResize.bind(this);
    }

    /* ------------------------------------------------------------------ */
    /* Target / auth                                                       */
    /* ------------------------------------------------------------------ */

    _controllerTarget() {
        return {
            baseUrl: String(this.flowsBaseUrl || '').trim().replace(/\/$/, ''),
            flowId: String(this.flowId || '').trim(),
            embedId: String(this.embedId || '').trim(),
            branchId: this._branchId() || null,
        };
    }

    _branchId() {
        return this.branchId != null ? String(this.branchId).trim() : '';
    }

    _isOperatorProfile() {
        return this.profile === 'operator_handoff';
    }

    /** conversation-ref из interaction_policy задачи. */
    _operatorConversationRef() {
        const policy = this.interactionPolicy;
        if (!policy || typeof policy !== 'object') {
            return null;
        }
        const conv = policy.conversation;
        if (!conv || typeof conv !== 'object' || typeof conv.context_id !== 'string' || conv.context_id === '') {
            return null;
        }
        return conv;
    }

    /**
     * Смонтировать operator-транспорт: REST snapshot + live tasks/resubscribe.
     * Ждёт work-item-id + interaction_policy.conversation с a2a_task_id.
     */
    _ensureOperatorTransport() {
        if (!this._isOperatorProfile() || this._operatorHistoryLoaded) {
            return;
        }
        const workItemId = String(this.workItemId || '').trim();
        const conversation = this._operatorConversationRef();
        if (workItemId === '' || conversation === null) {
            return;
        }
        const a2aTaskId = typeof conversation.a2a_task_id === 'string'
            ? conversation.a2a_task_id.trim()
            : '';
        if (a2aTaskId === '') {
            return;
        }
        if (this._operatorTransport !== null) {
            return;
        }
        this._operatorTransport = new OperatorConversationTransport({
            workItemId,
            conversation,
            mode: typeof this.interactionPolicy.mode === 'string'
                ? this.interactionPolicy.mode
                : 'takeover',
            baseUrl: String(this.flowsBaseUrl || '').trim().replace(/\/$/, ''),
            credentials: this._requestCredentials(),
            getHeaders: () => this._outboundFlowsRequestHeaders(),
        });
        this._controller.setTransport(this._operatorTransport);
        void this._controller.loadHistory().then(() => {
            this._operatorHistoryLoaded = true;
        }).catch(() => {
            if (this._operatorTransport !== null) {
                this._operatorTransport.dispose();
                this._operatorTransport = null;
            }
            this._operatorHistoryLoaded = false;
        });
    }

    /** Виден ли композер: takeover (can_send) или single_reply (can_complete → Send=complete). */
    _composerVisible() {
        if (!this._isOperatorProfile()) {
            return true;
        }
        const policy = this.interactionPolicy;
        if (!policy || typeof policy !== 'object') {
            return false;
        }
        if (policy.can_send === true) {
            return true;
        }
        return policy.mode === 'single_reply' && policy.can_complete === true;
    }

    /**
     * User-chat: на operator_task — live A2A tasks/resubscribe (тот же stream, что у operator).
     * Для operator_handoff не нужен — там OperatorConversationTransport со своим resubscribe.
     */
    _syncHitlLiveTail() {
        if (this._isOperatorProfile()) {
            this._controller.stopHitlLiveTail();
            return;
        }
        this._controller.syncHitlLiveTail();
    }

    _requestCredentials() {
        return this.useCredentials === true ? 'include' : 'omit';
    }

    /**
     * Исходящие заголовки к flows API (A2A, chat-profile, Lara apply, credentials):
     * Authorization из getAuthToken и X-Platform-Namespace из выбора CRM для company-id.
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

    /* ------------------------------------------------------------------ */
    /* Profile / viewConfig                                                */
    /* ------------------------------------------------------------------ */

    _resolveViewConfig() {
        const profile = createChatProfile({ kind: this.profile });
        const policy = this.chatPolicy && typeof this.chatPolicy === 'object'
            ? this.chatPolicy
            : this._fetchedPolicy;
        return resolveChatViewConfig(profile, policy);
    }

    _refreshViewConfig() {
        this._viewConfig = this._resolveViewConfig();
        this._startGreetingTypingIfNeeded();
    }

    async _loadChatProfileIfNeeded() {
        if (this._chatProfileRequested) {
            return;
        }
        if (this.chatPolicy && typeof this.chatPolicy === 'object') {
            return;
        }
        const target = this._controllerTarget();
        if (target.flowId === '' && target.embedId === '') {
            return;
        }
        this._chatProfileRequested = true;
        try {
            const headers = await this._outboundFlowsRequestHeaders();
            const profile = await fetchChatProfile({
                baseUrl: target.baseUrl,
                flowId: target.embedId === '' ? target.flowId : '',
                embedId: target.embedId,
                headers,
                credentials: this._requestCredentials(),
            });
            this._fetchedPolicy = profile.chat;
            if (profile.look && typeof profile.look === 'object') {
                this._applyLook(profile.look);
            }
            this._refreshViewConfig();
        } catch (err) {
            // Policy — рендер-конфигурация: без профиля работаем на Pydantic-дефолтах.
            console.warn('platform-chat: chat-profile load failed', err);
        }
    }

    /** look из EmbedConfig (chat-profile embed): применяется только там, где хост не задал своё. */
    _applyLook(look) {
        this._look = look;
        if (!this.hasAttribute('theme') && typeof look.theme === 'string' && look.theme.trim() !== '') {
            this.theme = look.theme.trim();
        }
        if (
            !this.hasAttribute('assistant-title')
            && typeof look.assistant_title === 'string'
            && look.assistant_title.trim() !== ''
        ) {
            this.assistantTitle = look.assistant_title.trim();
        }
        if (
            !this.hasAttribute('interface-locale')
            && typeof look.interface_locale === 'string'
            && look.interface_locale.trim() !== ''
        ) {
            this.interfaceLocale = look.interface_locale.trim();
        }
        if (!this.hasAttribute('voice-enabled') && typeof look.voice_enabled === 'boolean') {
            this.voiceEnabled = look.voice_enabled;
        }
        if (!this.hasAttribute('voice-default-on') && typeof look.voice_default_on === 'boolean') {
            this.voiceDefaultOn = look.voice_default_on;
        }
        if (typeof look.primary_color === 'string' && look.primary_color.trim() !== '') {
            this.style.setProperty('--platform-chat-accent', look.primary_color.trim());
        }
        if (typeof look.position === 'string' && look.position.trim() === 'bottom-left') {
            this.setAttribute('data-embed-position', 'bottom-left');
        }
        this.requestUpdate();
    }

    /* ------------------------------------------------------------------ */
    /* Labels / i18n                                                       */
    /* ------------------------------------------------------------------ */

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

    /* ------------------------------------------------------------------ */
    /* Runtime state helpers                                               */
    /* ------------------------------------------------------------------ */

    get _runtimeState() {
        return this._controller.state;
    }

    /** Read-only chat runtime state для хоста (header actions, статус, run trace). */
    get runtimeState() {
        return this._controller.state;
    }

    /** Проброс run-события flow/node хосту (редактор диспатчит его в bus как flows/run/*). */
    _emitChatRunEvent(type, payload) {
        this.dispatchEvent(
            new CustomEvent('chat-run-event', {
                bubbles: true,
                composed: true,
                detail: { type, payload },
            }),
        );
    }

    /** Восстановление сессии из ExecutionState (SPA host: URL ?session=). */
    loadSession(payload) {
        if (!payload || typeof payload !== 'object') {
            throw new Error('platform-chat: loadSession payload required');
        }
        this._controller.applyRuntimeVerb('session_loaded', payload);
    }

    /** Отмена активной задачи (abort SSE + tasks/cancel); публичный API хоста. */
    async cancelActiveTask() {
        await this._controller.cancel();
    }

    _currentMessages() {
        const state = this._runtimeState;
        const ctx = state.currentContextId;
        if (typeof ctx !== 'string' || ctx.length === 0) {
            return [];
        }
        const bucket = state.messagesByContextId[ctx];
        return bucket && Array.isArray(bucket.messages) ? bucket.messages : [];
    }

    _isLoading() {
        return this._runtimeState.streaming || this._controller.sending || this._voiceStreamState !== null;
    }

    /**
     * Текущий A2A contextId (синхронизация с VoiceAgentBridge, Lara apply).
     * @returns {string}
     */
    getA2aContextId() {
        const ctx = this._runtimeState.currentContextId;
        return typeof ctx === 'string' ? ctx : '';
    }

    _visible() {
        return this.display !== 'drawer' || this.open === true;
    }

    /* ------------------------------------------------------------------ */
    /* Lifecycle                                                           */
    /* ------------------------------------------------------------------ */

    connectedCallback() {
        ensurePlatformBusForStandaloneChat(this.flowsBaseUrl, this.platformUiOrigin);
        super.connectedCallback();
        this.addEventListener('flows-chat-block-action', this._onBlockAction);
        this.addEventListener('flows-chat-action-config-error', this._onActionConfigError);
        document.addEventListener('click', this._onCredClickOutside);
        this._bindAckListeners();
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPref);
            window.addEventListener('storage', this._onTtsStorage);
        }
        if (this.display === 'drawer') {
            this._applyEmbedUrlParams();
            this._onPopStateEmbedParams = () => this._applyEmbedUrlParams();
            window.addEventListener('popstate', this._onPopStateEmbedParams);
            window.addEventListener('resize', this._onViewportResize);
            this._onPlatformThemeChange = () => {
                if ((this.theme || 'auto').toLowerCase() === 'auto') {
                    this.requestUpdate();
                }
            };
            window.addEventListener('theme-change', this._onPlatformThemeChange);
            this._onFullscreenChange = () => {
                const panel = this.renderRoot?.querySelector('.panel');
                if (!panel) {
                    return;
                }
                if (document.fullscreenElement === panel) {
                    this._stopPanelDrag();
                    this._panelNativeFullscreen = true;
                    return;
                }
                if (this._panelNativeFullscreen || this._drawerOwnsNativeFullscreen) {
                    this._stopPanelDrag();
                    this._panelNativeFullscreen = false;
                    this._drawerOwnsNativeFullscreen = false;
                    if (this.panelMaximized) {
                        this.panelMaximized = false;
                        this.requestUpdate();
                    }
                }
            };
            document.addEventListener('fullscreenchange', this._onFullscreenChange);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('flows-chat-block-action', this._onBlockAction);
        this.removeEventListener('flows-chat-action-config-error', this._onActionConfigError);
        document.removeEventListener('click', this._onCredClickOutside);
        if (typeof window !== 'undefined') {
            window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsPref);
            window.removeEventListener('storage', this._onTtsStorage);
        }
        this._unbindAckListeners();
        this._pendingEventAcks.forEach((pending) => {
            if (pending.timer) {
                clearTimeout(pending.timer);
            }
        });
        this._pendingEventAcks.clear();
        this._ttsOnly.dispose();
        this._clearVoiceReconnectTimer();
        if (this._voiceOn) {
            this._voiceDisconnectExpected = true;
            const m = this._voiceMedia;
            const b = this._voiceBridge;
            this._voiceMedia = null;
            this._voiceBridge = null;
            this._voiceOn = false;
            this._voiceStatus = 'idle';
            void disposeVoiceMediaThenBridge(m, b).finally(() => {
                this._voiceDisconnectExpected = false;
            });
        }
        this._stopPanelDrag();
        this._stopFabDrag();
        if (this._onPopStateEmbedParams) {
            window.removeEventListener('popstate', this._onPopStateEmbedParams);
            this._onPopStateEmbedParams = null;
        }
        window.removeEventListener('resize', this._onViewportResize);
        if (this._onPlatformThemeChange) {
            window.removeEventListener('theme-change', this._onPlatformThemeChange);
            this._onPlatformThemeChange = null;
        }
        if (this._onFullscreenChange) {
            document.removeEventListener('fullscreenchange', this._onFullscreenChange);
            this._onFullscreenChange = null;
        }
        this._unbindToggleListener();
        if (this._operatorTransport !== null) {
            this._operatorTransport.dispose();
            this._operatorTransport = null;
        }
        this._controller.dispose();
    }

    firstUpdated() {
        this._ensureOperatorTransport();
        this._loadEmbedCredentials();
        void this._loadChatProfileIfNeeded();
        this._startGreetingTypingIfNeeded();
        if (this.display === 'drawer') {
            this._bindToggleListener();
            this._restoreFabDragPosition();
        }
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (this.display === 'drawer' && !this._initialOpenConsumed && this.initialOpen) {
            this._initialOpenConsumed = true;
            this.open = true;
        }
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('flowId') || changed.has('embedId') || changed.has('branchId') || changed.has('flowsBaseUrl')) {
            this._controller.setTarget(this._controllerTarget());
            this._ttsOnly.dispose();
        }
        if (changed.has('useCredentials')) {
            this._controller.setCredentials(this._requestCredentials());
        }
        if (changed.has('profile') || changed.has('chatPolicy')) {
            this._refreshViewConfig();
        }
        if (changed.has('profile') || changed.has('workItemId') || changed.has('interactionPolicy')) {
            this._ensureOperatorTransport();
        }
        if (changed.has('conversationKey') && changed.get('conversationKey') !== undefined) {
            this._newChat();
        }
        if (changed.has('toggleEventName') && this.display === 'drawer') {
            this._bindToggleListener();
        }
        if (changed.has('eventNamespace')) {
            this._bindAckListeners();
        }
        if (changed.has('voiceEnabled') && this.voiceEnabled !== true && this._voiceOn) {
            void this._stopVoice();
        }
        if (changed.has('open')) {
            this._onOpenChanged();
        }
        const resolved = resolveEmbedChatTheme(this.theme);
        if (this.getAttribute('data-embed-theme') !== resolved) {
            this.setAttribute('data-embed-theme', resolved);
        }
        if ((changed.has('open') && !this.open) || (changed.has('panelMaximized') && this.panelMaximized)) {
            this._stopPanelDrag();
        }
        if (changed.has('open') && this.open) {
            this.updateComplete.then(() => this._syncPanelToViewport());
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

    _onOpenChanged() {
        if (this.display !== 'drawer') {
            return;
        }
        this.dispatchEvent(
            new CustomEvent('humanitec-embed-drawer-open-changed', {
                bubbles: true,
                composed: true,
                detail: { open: this.open },
            }),
        );
        if (!this.open) {
            this._ttsOnly.dispose();
            if (this._voiceOn) {
                void this._stopVoice();
            }
            return;
        }
        this._startGreetingTypingIfNeeded();
        if (this.voiceEnabled && readTtsOutputEnabled() && !this._voiceOn) {
            void this._ttsOnly.ensure();
        }
        if (this.voiceEnabled && this.voiceDefaultOn && !this._voiceOn) {
            this._startVoice().catch(() => { /* ошибки идут через humanitec-embed-voice-error */ });
        }
    }

    /* ------------------------------------------------------------------ */
    /* Drawer: URL params, toggle, drag, fullscreen                        */
    /* ------------------------------------------------------------------ */

    _applyEmbedUrlParams() {
        const p = readEmbedChatUrlParams();
        if (p.theme) {
            this.theme = p.theme;
        }
        if (p.locale) {
            this.interfaceLocale = p.locale;
        }
        if (p.showLocaleControl !== undefined) {
            this.showLocaleControl = p.showLocaleControl;
        }
        if (p.assistantTitle) {
            this.assistantTitle = p.assistantTitle;
        }
        if (p.branchId) {
            this.branchId = p.branchId;
        }
        applyEmbedChatDrawerSizeVars(this, p);
    }

    _unbindToggleListener() {
        if (this._boundToggle && this._toggleListenerEventName) {
            window.removeEventListener(this._toggleListenerEventName, this._boundToggle);
        }
        this._boundToggle = null;
        this._toggleListenerEventName = null;
    }

    _bindToggleListener() {
        this._unbindToggleListener();
        const name = (this.toggleEventName && String(this.toggleEventName).trim()) || 'humanitec-embed-chat-toggle';
        this._boundToggle = (event) => {
            const requestedOpen = event?.detail?.open;
            const next = typeof requestedOpen === 'boolean' ? requestedOpen : !this.open;
            if (next) {
                this._layerBaseZIndex = nextModalLayerZIndex();
                this.fabUnreadCount = 0;
            }
            this.open = next;
        };
        this._toggleListenerEventName = name;
        window.addEventListener(name, this._boundToggle);
    }

    _toggle() {
        const next = !this.open;
        if (next) {
            this._layerBaseZIndex = nextModalLayerZIndex();
            this.fabUnreadCount = 0;
        } else {
            this._stopPanelDrag();
        }
        this.open = next;
    }

    _fabPreferenceBranchId() {
        const branchId = String(this.branchId).trim();
        if (/^[a-z][a-z0-9_]*$/.test(branchId)) {
            return branchId;
        }
        const embedId = typeof this.embedId === 'string' ? this.embedId.trim() : '';
        const flowId = typeof this.flowId === 'string' ? this.flowId.trim() : '';
        const surfaceId = embedId !== '' ? embedId : flowId;
        const normalized = surfaceId.toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
        if (!/^[a-z][a-z0-9_]*$/.test(normalized)) {
            throw new Error('PlatformChat launcher persistence requires branch-id, embed-id, or flow-id');
        }
        return normalized;
    }

    _restoreFabDragPosition() {
        if (!this.showLauncher) {
            return;
        }
        const position = readLaraLauncherPosition(
            this.launcherStorageScope,
            this._fabPreferenceBranchId(),
        );
        if (position === null) {
            return;
        }
        this._fabDragPosition = position;
        this.requestUpdate();
        void this.updateComplete.then(() => this._syncFabToViewport());
    }

    _fabInlineStyle() {
        let style = `z-index:${this._layerZIndex(3)}`;
        if (this._fabDragPosition !== null) {
            style += `;left:${this._fabDragPosition.left}px;top:${this._fabDragPosition.top}px;right:auto;bottom:auto`;
        }
        return style;
    }

    _bindFabDragListeners() {
        window.addEventListener('pointermove', this._onFabDragPointerMove);
        window.addEventListener('pointerup', this._onFabDragPointerUp);
        window.addEventListener('pointercancel', this._onFabDragPointerUp);
    }

    _unbindFabDragListeners() {
        window.removeEventListener('pointermove', this._onFabDragPointerMove);
        window.removeEventListener('pointerup', this._onFabDragPointerUp);
        window.removeEventListener('pointercancel', this._onFabDragPointerUp);
    }

    _stopFabDrag() {
        this._fabDragContext = null;
        this._fabDragActive = false;
        this._unbindFabDragListeners();
    }

    _clampFabDragPosition(top, left, width, height) {
        const margin = 8;
        const maxLeft = Math.max(margin, window.innerWidth - width - margin);
        const maxTop = Math.max(margin, window.innerHeight - height - margin);
        return {
            left: Math.min(Math.max(left, margin), maxLeft),
            top: Math.min(Math.max(top, margin), maxTop),
        };
    }

    _applyFabDragPosition(fab) {
        if (!(fab instanceof HTMLElement) || this._fabDragPosition === null) {
            return;
        }
        fab.style.left = `${this._fabDragPosition.left}px`;
        fab.style.top = `${this._fabDragPosition.top}px`;
        fab.style.right = 'auto';
        fab.style.bottom = 'auto';
    }

    _syncFabToViewport() {
        if (this._fabDragPosition === null) {
            return;
        }
        const fab = this.renderRoot?.querySelector('.fab');
        if (!(fab instanceof HTMLElement)) {
            return;
        }
        const rect = fab.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) {
            return;
        }
        const clamped = this._clampFabDragPosition(
            this._fabDragPosition.top,
            this._fabDragPosition.left,
            rect.width,
            rect.height,
        );
        if (
            clamped.left === this._fabDragPosition.left
            && clamped.top === this._fabDragPosition.top
        ) {
            return;
        }
        this._fabDragPosition = clamped;
        this._applyFabDragPosition(fab);
        writeLaraLauncherPosition(
            this.launcherStorageScope,
            this._fabPreferenceBranchId(),
            clamped,
        );
        this.requestUpdate();
    }

    _onFabPointerDown(event) {
        if (event.button !== 0) {
            return;
        }
        const fab = this.renderRoot?.querySelector('.fab');
        if (!(fab instanceof HTMLElement)) {
            return;
        }
        const rect = fab.getBoundingClientRect();
        this._fabDragContext = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            offsetX: event.clientX - rect.left,
            offsetY: event.clientY - rect.top,
            width: rect.width,
            height: rect.height,
        };
        this._fabDragActive = false;
        this._bindFabDragListeners();
    }

    _onFabDragPointerMove(event) {
        const context = this._fabDragContext;
        if (context === null || event.pointerId !== context.pointerId) {
            return;
        }
        if (!this._fabDragActive) {
            const distance = Math.hypot(
                event.clientX - context.startX,
                event.clientY - context.startY,
            );
            if (distance < 6) {
                return;
            }
            this._fabDragActive = true;
        }
        this._fabDragPosition = this._clampFabDragPosition(
            event.clientY - context.offsetY,
            event.clientX - context.offsetX,
            context.width,
            context.height,
        );
        this._applyFabDragPosition(this.renderRoot?.querySelector('.fab'));
        event.preventDefault();
    }

    _onFabDragPointerUp(event) {
        const context = this._fabDragContext;
        if (context === null || event.pointerId !== context.pointerId) {
            return;
        }
        if (this._fabDragActive && this._fabDragPosition !== null) {
            writeLaraLauncherPosition(
                this.launcherStorageScope,
                this._fabPreferenceBranchId(),
                this._fabDragPosition,
            );
            this._suppressFabClick = true;
            this.requestUpdate();
        }
        this._stopFabDrag();
    }

    _onFabClick(event) {
        if (this._suppressFabClick) {
            this._suppressFabClick = false;
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        this._toggle();
    }

    _isMobileViewportForNativeFullscreen() {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return false;
        }
        return window.matchMedia('(max-width: 767px)').matches;
    }

    _fabBadgeText() {
        const n = this.fabUnreadCount;
        if (n < 1) {
            return '';
        }
        return n > 9 ? '9+' : String(n);
    }

    _fabOpenAriaLabel(L) {
        const n = this.fabUnreadCount;
        if (n < 1) {
            return L.fab_aria_open;
        }
        const tpl = L.fab_aria_open_unread || L.fab_aria_open;
        const c = n > 99 ? '99+' : String(n);
        return tpl.includes('{count}') ? tpl.replace(/\{count\}/g, c) : `${L.fab_aria_open} (${c})`;
    }

    _layerZIndex(step = 0) {
        return String(this._layerBaseZIndex + step);
    }

    _isPanelDraggable() {
        if (!this.open) {
            return false;
        }
        if (this.panelMaximized || this._panelNativeFullscreen || this._drawerOwnsNativeFullscreen) {
            return false;
        }
        return !this._isMobileViewportForNativeFullscreen();
    }

    _panelInlineStyle() {
        let style = `z-index:${this._layerZIndex(2)}`;
        if (this._panelDragPosition && !this.panelMaximized) {
            style += `;top:${this._panelDragPosition.top}px;left:${this._panelDragPosition.left}px;right:auto;bottom:auto`;
        }
        return style;
    }

    _bindPanelDragListeners() {
        window.addEventListener('pointermove', this._onPanelDragPointerMove);
        window.addEventListener('pointerup', this._onPanelDragPointerUp);
        window.addEventListener('pointercancel', this._onPanelDragPointerUp);
    }

    _unbindPanelDragListeners() {
        window.removeEventListener('pointermove', this._onPanelDragPointerMove);
        window.removeEventListener('pointerup', this._onPanelDragPointerUp);
        window.removeEventListener('pointercancel', this._onPanelDragPointerUp);
    }

    _stopPanelDrag() {
        this._panelDragContext = null;
        this._unbindPanelDragListeners();
        if (this._panelDragActive) {
            this._panelDragActive = false;
            this.requestUpdate();
        }
    }

    _clampPanelDragPosition(top, left, width, height) {
        const maxLeft = Math.max(0, window.innerWidth - width);
        const maxTop = Math.max(0, window.innerHeight - height);
        const clampedLeft = Math.min(Math.max(left, 0), maxLeft);
        const clampedTop = Math.min(Math.max(top, 0), maxTop);
        return { top: clampedTop, left: clampedLeft };
    }

    _syncPanelToViewport() {
        if (!this.open || this.panelMaximized) {
            return;
        }
        if (this._isMobileViewportForNativeFullscreen()) {
            this._stopPanelDrag();
            if (this._panelDragPosition) {
                this._panelDragPosition = null;
                this.requestUpdate();
            }
            return;
        }
        if (!this._panelDragPosition) {
            return;
        }
        const panel = this.renderRoot?.querySelector('.panel');
        if (!(panel instanceof HTMLElement)) {
            return;
        }
        const width = panel.offsetWidth;
        const height = panel.offsetHeight;
        if (width <= 0 || height <= 0) {
            return;
        }
        const clamped = this._clampPanelDragPosition(
            this._panelDragPosition.top,
            this._panelDragPosition.left,
            width,
            height,
        );
        if (clamped.top === this._panelDragPosition.top && clamped.left === this._panelDragPosition.left) {
            return;
        }
        this._panelDragPosition = clamped;
        this._applyPanelDragPosition(panel);
        this.requestUpdate();
    }

    _onViewportResize() {
        this._syncPanelToViewport();
        this._syncFabToViewport();
    }

    _applyPanelDragPosition(panel) {
        if (!(panel instanceof HTMLElement) || !this._panelDragPosition || this.panelMaximized) {
            return;
        }
        panel.style.top = `${this._panelDragPosition.top}px`;
        panel.style.left = `${this._panelDragPosition.left}px`;
        panel.style.right = 'auto';
        panel.style.bottom = 'auto';
    }

    _onPanelHeadPointerDown(event) {
        if (!this._isPanelDraggable()) {
            return;
        }
        if (event.button !== 0) {
            return;
        }
        const target = event.target;
        if (!(target instanceof Element)) {
            return;
        }
        if (target.closest('.panel-head-actions')) {
            return;
        }
        const panel = this.renderRoot?.querySelector('.panel');
        if (!(panel instanceof HTMLElement)) {
            return;
        }
        const rect = panel.getBoundingClientRect();
        const initial = this._clampPanelDragPosition(rect.top, rect.left, rect.width, rect.height);
        this._panelDragPosition = initial;
        this._panelDragContext = {
            pointerId: event.pointerId,
            offsetX: event.clientX - initial.left,
            offsetY: event.clientY - initial.top,
            width: rect.width,
            height: rect.height,
        };
        this._panelDragActive = true;
        this._bindPanelDragListeners();
        this._applyPanelDragPosition(panel);
        this.requestUpdate();
        event.preventDefault();
    }

    _onPanelDragPointerMove(event) {
        if (!this._panelDragContext) {
            return;
        }
        if (event.pointerId !== this._panelDragContext.pointerId) {
            return;
        }
        const nextLeft = event.clientX - this._panelDragContext.offsetX;
        const nextTop = event.clientY - this._panelDragContext.offsetY;
        this._panelDragPosition = this._clampPanelDragPosition(
            nextTop,
            nextLeft,
            this._panelDragContext.width,
            this._panelDragContext.height,
        );
        const panel = this.renderRoot?.querySelector('.panel');
        this._applyPanelDragPosition(panel);
    }

    _onPanelDragPointerUp(event) {
        if (!this._panelDragContext) {
            return;
        }
        if (event.pointerId !== this._panelDragContext.pointerId) {
            return;
        }
        this._stopPanelDrag();
    }

    _minimize() {
        this._stopPanelDrag();
        const panel = this.renderRoot?.querySelector('.panel');
        const fs = typeof document !== 'undefined' ? document.fullscreenElement : null;
        if (this._drawerOwnsNativeFullscreen || this._panelNativeFullscreen || (fs && panel && fs === panel)) {
            this._panelNativeFullscreen = false;
            this._drawerOwnsNativeFullscreen = false;
            if (typeof document !== 'undefined' && document.fullscreenElement) {
                document.exitFullscreen().catch(() => {});
            }
        }
        this.panelMaximized = false;
        this.open = false;
    }

    async _togglePanelFullscreen() {
        this._stopPanelDrag();
        const panel = this.renderRoot?.querySelector('.panel');
        if (!panel) {
            return;
        }
        const next = !this.panelMaximized;
        if (next) {
            this.panelMaximized = true;
            this.requestUpdate();
            await this.updateComplete;
            const el = this.renderRoot?.querySelector('.panel');
            if (
                this._isMobileViewportForNativeFullscreen() &&
                el &&
                typeof document !== 'undefined' &&
                document.fullscreenEnabled &&
                typeof el.requestFullscreen === 'function'
            ) {
                try {
                    await el.requestFullscreen();
                    this._drawerOwnsNativeFullscreen = true;
                    this._panelNativeFullscreen = true;
                } catch {
                    /* только CSS panel--maximized */
                }
            }
        } else {
            const fs = typeof document !== 'undefined' ? document.fullscreenElement : null;
            const shouldExitNative =
                this._drawerOwnsNativeFullscreen ||
                this._panelNativeFullscreen ||
                (fs && panel && fs === panel);
            if (shouldExitNative) {
                this._drawerOwnsNativeFullscreen = false;
                this._panelNativeFullscreen = false;
                if (typeof document !== 'undefined' && document.fullscreenElement) {
                    try {
                        await document.exitFullscreen();
                    } catch {
                        /* ignore */
                    }
                }
            }
            this.panelMaximized = false;
        }
    }

    /* ------------------------------------------------------------------ */
    /* Voice: TTS-only stream                                              */
    /* ------------------------------------------------------------------ */

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

    _voiceTtsContextReady() {
        if (this._resolvedVoiceHttpBaseForStream() === '') {
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

    _streamTtsAllowed() {
        return this.enableVoice === true && readTtsOutputEnabled();
    }

    _ttsOnlyAllowed() {
        return (
            this._streamTtsAllowed()
            && this._visible()
            && !this._voiceOn
            && this._voiceTtsContextReady()
        );
    }

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

    async _mergeTtsOnlyWsQuery() {
        let serverQuery = {};
        const fid = String(this.flowId || '').trim();
        const root = String(this.flowsBaseUrl || '').replace(/\/$/, '');
        if (fid !== '' && root !== '') {
            serverQuery = await fetchFlowVoiceSessionQueryDict({
                flowsApiRoot: root,
                flowId: fid,
                branchId: this.branchId,
                credentials: this._requestCredentials(),
                getHeaders: () => this._outboundFlowsRequestHeaders(),
            });
        }
        const wsQuery = { ...serverQuery };
        Object.assign(wsQuery, this._wsLanguageQueryForVoiceSession());
        return wsQuery;
    }

    _syncStreamTtsAfterPrefChange() {
        if (!this._streamTtsAllowed()) {
            this._ttsOnly.dispose();
            return;
        }
        if (this._visible() && !this._voiceOn) {
            void this._ttsOnly.ensure();
        }
    }

    _emitVoiceError(code, err) {
        this.dispatchEvent(
            new CustomEvent('humanitec-embed-voice-error', {
                bubbles: true,
                composed: true,
                detail: {
                    code,
                    detail: err instanceof Error ? err.message : String(err),
                },
            }),
        );
    }

    /**
     * Origin голосового шлюза для POST /api/v1/synthesize (кнопка озвучки).
     * @returns {string}
     */
    _assistantTtsVoiceBaseUrl() {
        if (!this._streamTtsAllowed()) {
            return '';
        }
        const flows = this.flowsBaseUrl != null ? String(this.flowsBaseUrl).trim() : '';
        if (flows !== '') {
            return resolveVoiceHttpOriginFromFlowsBaseUrl(flows);
        }
        return resolveVoiceHttpOrigin();
    }

    /* ------------------------------------------------------------------ */
    /* Voice: duplex (микрофон, VoiceAgentBridge)                          */
    /* ------------------------------------------------------------------ */

    _clearVoiceReconnectTimer() {
        if (this._voiceReconnectAfterCloseTimer !== null) {
            window.clearTimeout(this._voiceReconnectAfterCloseTimer);
            this._voiceReconnectAfterCloseTimer = null;
        }
    }

    _scheduleVoiceReconnectAfterUnexpectedClose() {
        this._clearVoiceReconnectTimer();
        this._voiceReconnectAfterCloseTimer = window.setTimeout(() => {
            this._voiceReconnectAfterCloseTimer = null;
            if (this._voiceDisconnectExpected) {
                return;
            }
            if (!this._visible() || this.voiceEnabled !== true) {
                return;
            }
            if (this._composerWsDuplex() !== true) {
                return;
            }
            if (this._voiceOn) {
                return;
            }
            this._startVoice().catch(() => { /* ошибки — humanitec-embed-voice-error */ });
        }, 500);
    }

    /** Микрофон в композере: WebSocket эфир, а не браузерная диктовка. */
    _composerWsDuplex() {
        return (
            this.enableVoice === true
            && this.voiceEnabled === true
            && this._voiceTtsContextReady() === true
        );
    }

    /** Запасной путь: Web Speech в textarea (нет инфраструктуры voice). */
    _composerBrowserDictation() {
        return (
            this.enableVoice === true
            && this.voiceEnabled === true
            && this._voiceTtsContextReady() !== true
        );
    }

    /** @param {'no_base_url'|'no_embed'|'no_company'|'no_a2a'} kind */
    _toastVoicePrepFailure(kind) {
        const L = this._mergedLabels();
        const key =
            kind === 'no_base_url'
                ? 'voice_err_no_base_url'
                : kind === 'no_embed'
                  ? 'voice_err_no_embed'
                  : kind === 'no_company'
                    ? 'voice_err_no_company'
                    : kind === 'no_a2a'
                      ? 'voice_err_no_flows'
                      : '';
        if (key === '') {
            throw new Error(`platform-chat: unknown voice prep kind ${kind}`);
        }
        const msg = L[key];
        if (typeof msg !== 'string' || msg.trim() === '') {
            throw new Error(`platform-chat: missing label ${key}`);
        }
        this.dispatchEvent(
            new CustomEvent('embed-toast', {
                bubbles: true,
                composed: true,
                detail: { message: msg.trim() },
            }),
        );
    }

    /** ISO-код для query language=; null — оставить значение из профиля flow. */
    _voiceSttLanguageOverlayOrNull() {
        const il = String(this.interfaceLocale || '').trim().toLowerCase();
        let raw = '';
        if (il === '' || il === 'auto') {
            raw =
                typeof document !== 'undefined'
                    ? String(document.documentElement.lang || '').trim()
                    : '';
            if (raw === '') {
                return null;
            }
        } else {
            raw = il;
        }
        try {
            return normalizeVoiceLocaleForWs(raw);
        } catch {
            return null;
        }
    }

    /**
     * Подготовка UI и metadata перед голосовым A2A-стримом (вызывает VoiceAgentBridge).
     * @param {string} userText
     */
    async prepareVoiceUserTurn(userText) {
        const message = typeof userText === 'string' ? userText.trim() : '';
        if (message === '') {
            throw new Error('platform-chat: empty voice text');
        }
        if (this._voiceStreamState !== null) {
            this.finalizeVoiceA2aStream();
        }
        if (this._controller.sending || this._runtimeState.streaming) {
            throw new Error('platform-chat: stream active');
        }
        if (!this.flowsBaseUrl || (!this.flowId && !this.embedId)) {
            throw new Error('platform-chat: missing flows config');
        }
        let contextId = this._runtimeState.currentContextId;
        if (typeof contextId !== 'string' || contextId.length === 0) {
            this._controller.initSession({});
            contextId = this._runtimeState.currentContextId;
        }
        this._controller.addUserMessage(contextId, {
            id: `u_${++mid}`,
            role: 'user',
            content: message,
            timestamp: new Date().toISOString(),
            files: [],
        });
        this._voiceStreamState = { contextId, taskId: null, taskPrimed: false };
        this._pendingAssistantReplyNotify = true;
        this._stickToBottom = true;
        this.requestUpdate();
        const { metadata, variables } = await this._composeSendMetadata();
        this._voicePendingStreamMetadata = metadata;
        this._emitChatRunEvent('flows/run/flow_started', {});
        this._emitAssistantEvent('context_requested', {
            flow_id: this.flowId || null,
            branch_id: this._branchId() || null,
            embed_id: this.embedId || null,
            variables,
        });
    }

    /** Metadata для очередного voice message/stream (после prepareVoiceUserTurn). */
    consumeVoiceStreamMetadata() {
        const m = this._voicePendingStreamMetadata;
        this._voicePendingStreamMetadata = null;
        return m;
    }

    /** Проброс SSE события A2A голосового моста в общий runtime. */
    applyVoiceA2aStreamEvent(event) {
        if (this._voiceStreamState === null) {
            return;
        }
        try {
            this._controller.relayA2aFrame(event, this._voiceStreamState);
        } catch (err) {
            this.failVoiceA2aStream(err instanceof Error ? err.message : String(err));
        }
    }

    /** Завершение голосового A2A (успех, abort или после ошибки с патчем). */
    finalizeVoiceA2aStream() {
        const streamState = this._voiceStreamState;
        this._voiceStreamState = null;
        if (streamState !== null) {
            this._controller.applyRuntimeVerb('send_succeeded', {
                task_id: streamState.taskId,
                context_id: streamState.contextId,
            });
            this._emitChatRunEvent('flows/run/flow_done', {});
        }
        this._notifyAssistantReplyCompleted();
        this.requestUpdate();
    }

    /** Ошибка голосового стрима: текст ошибки в пузырь ассистента. */
    failVoiceA2aStream(detail) {
        const streamState = this._voiceStreamState;
        if (streamState !== null && typeof streamState.taskId === 'string' && streamState.taskId !== '') {
            this._controller.applyRuntimeVerb('failed', {
                task_id: streamState.taskId,
                context_id: streamState.contextId,
                error: typeof detail === 'string' ? detail : String(detail || 'Error'),
            });
        }
        this.finalizeVoiceA2aStream();
    }

    async _startVoice() {
        if (this._voiceOn) return;
        if (this.voiceEnabled !== true) return;
        this._clearVoiceReconnectTimer();
        this._ttsOnly.dispose();
        const voiceBaseUrl = this._resolvedVoiceHttpBaseForStream();
        if (voiceBaseUrl === '') {
            this._toastVoicePrepFailure('no_base_url');
            return;
        }
        if (!this.embedId && !this.flowId) {
            this._toastVoicePrepFailure('no_embed');
            return;
        }
        const companyId = String(this.companyId || '').trim();
        if (companyId === '') {
            this._toastVoicePrepFailure('no_company');
            return;
        }
        const a2aBaseUrl = String(this.flowsBaseUrl || '').replace(/\/$/, '');
        if (a2aBaseUrl === '') {
            this._toastVoicePrepFailure('no_a2a');
            return;
        }
        const sessionId = `voice_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
        const wsBase = voiceBaseUrl.replace(/^http/, 'ws');
        const getHeaders = async () => this._outboundFlowsRequestHeaders();
        /** @type {Record<string, string>} */
        let wsQuery = {};
        if (String(this.flowId || '').trim() !== '') {
            try {
                wsQuery = await fetchFlowVoiceSessionQueryDict({
                    flowsApiRoot: a2aBaseUrl,
                    flowId: String(this.flowId).trim(),
                    branchId: this.branchId,
                    credentials: this._requestCredentials(),
                    getHeaders,
                });
            } catch (err) {
                this._voiceStatus = 'error';
                this._emitVoiceError('voice/session_query_failed', err);
                return;
            }
        }
        const langOverlay = this._voiceSttLanguageOverlayOrNull();
        if (langOverlay !== null) {
            wsQuery.language = langOverlay;
        }
        /** @type {{ baseUrl: string, sessionId: string, companyId: string, autoRecord: boolean, query?: Record<string, string> }} */
        const mediaOpts = {
            baseUrl: wsBase,
            sessionId,
            companyId,
            autoRecord: true,
        };
        if (Object.keys(wsQuery).length > 0) {
            Object.assign(mediaOpts, { query: wsQuery });
        }
        const media = new VoiceMediaSession(mediaOpts);
        const bridge = new VoiceAgentBridge({
            mediaSession: media,
            a2aBaseUrl,
            flowId: this.flowId || undefined,
            embedId: this.embedId || undefined,
            branchId: this.branchId || null,
            getHeaders,
            credentials: this._requestCredentials(),
            getContextId: () => {
                const id = this.getA2aContextId();
                return id.trim() !== '' ? id.trim() : null;
            },
            getStreamMetadata: async () => this.consumeVoiceStreamMetadata(),
            beforeA2aStream: async (text) => {
                await this.prepareVoiceUserTurn(text);
            },
            onA2aStreamEvent: (ev) => {
                this.applyVoiceA2aStreamEvent(ev);
            },
        });
        bridge.addEventListener('a2aSettled', () => {
            this.finalizeVoiceA2aStream();
        });
        bridge.addEventListener('error', (e) => {
            const raw =
                e.detail && typeof e.detail.detail === 'string'
                    ? e.detail.detail
                    : '';
            this.failVoiceA2aStream(raw !== '' ? raw : 'voice bridge error');
        });
        media.addEventListener('error', (e) => {
            this._voiceStatus = 'error';
            this.dispatchEvent(new CustomEvent('humanitec-embed-voice-error', {
                bubbles: true,
                composed: true,
                detail: e.detail,
            }));
        });
        media.addEventListener('closed', () => {
            this._voiceStatus = 'closed';
            this._voiceOn = false;
            if (this._voiceMedia === media) {
                this._voiceMedia = null;
            }
            if (this._voiceBridge === bridge) {
                this._voiceBridge = null;
            }
            if (!this._voiceDisconnectExpected) {
                this._scheduleVoiceReconnectAfterUnexpectedClose();
            }
            this.requestUpdate();
        });
        media.addEventListener('vad', (e) => {
            this._voiceStatus = e.detail.state === 'started' ? 'listening' : 'idle';
        });
        media.addEventListener('ttsState', (e) => {
            this._voiceStatus = e.detail.state === 'playing' ? 'speaking' : 'idle';
        });
        try {
            media.primePlaybackFromUserGesture();
            await media.connect();
        } catch (err) {
            this._voiceStatus = 'error';
            this._emitVoiceError('voice/connect_failed', err);
            return;
        }
        bridge.start();
        setStreamTtsTarget(media, readTtsOutputEnabled);
        this._voiceMedia = media;
        this._voiceBridge = bridge;
        this._voiceOn = true;
        this._voiceStatus = 'idle';
    }

    async _stopVoice() {
        this._clearVoiceReconnectTimer();
        this._voiceDisconnectExpected = true;
        try {
            const m = this._voiceMedia;
            const b = this._voiceBridge;
            await disposeVoiceMediaThenBridge(m, b);
        } finally {
            this._voiceDisconnectExpected = false;
        }
        this._voiceBridge = null;
        this._voiceMedia = null;
        this._voiceOn = false;
        this._voiceStatus = 'idle';
        if (this.voiceEnabled && readTtsOutputEnabled() && this._visible()) {
            void this._ttsOnly.ensure();
        }
    }

    _toggleVoice() {
        if (this._voiceOn) {
            void this._stopVoice();
        } else {
            this._startVoice().catch(() => { /* noop */ });
        }
    }

    /** Публичный API хоста: выключить голосовой дуплекс (поверхность скрыта, микрофон не нужен). */
    async stopVoice() {
        if (this._voiceOn) {
            await this._stopVoice();
        }
    }

    _toggleTtsOutput() {
        toggleTtsOutputEnabled();
        this.requestUpdate();
        this._syncStreamTtsAfterPrefChange();
    }

    _onVoiceBridgeUserStop() {
        const b = this._voiceBridge;
        if (b && typeof b.userStopActiveTurn === 'function') {
            b.userStopActiveTurn();
        }
    }

    /* ------------------------------------------------------------------ */
    /* Внешний контракт: assistant events, acks, ui_events, actions        */
    /* ------------------------------------------------------------------ */

    onAssistantEvent(handler) {
        if (typeof handler !== 'function') {
            throw new Error('onAssistantEvent expects a function');
        }
        this.addEventListener(this._assistantEventName(), handler);
        return () => this.offAssistantEvent(handler);
    }

    offAssistantEvent(handler) {
        if (typeof handler !== 'function') {
            throw new Error('offAssistantEvent expects a function');
        }
        this.removeEventListener(this._assistantEventName(), handler);
    }

    _assistantEventName() {
        return `${this._normalizedEventNamespace()}:event`;
    }

    _normalizedEventNamespace() {
        const raw = typeof this.eventNamespace === 'string' ? this.eventNamespace.trim() : '';
        return raw || 'assistant';
    }

    _newEventId() {
        return `${Date.now()}-${Math.random().toString(16).slice(2)}-${mid++}`;
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

    _buildAssistantEnvelope(type, payload = {}, overrides = {}) {
        const eventNamespace = this._normalizedEventNamespace();
        return {
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

    _uiEventDispatchKey(uiEvent, taskId) {
        const eventId =
            uiEvent.id != null && String(uiEvent.id).trim() ? String(uiEvent.id).trim() : 'no-id';
        const eventType = String(uiEvent.type || '').trim();
        const payload = uiEvent.payload && typeof uiEvent.payload === 'object' ? uiEvent.payload : {};
        return `${taskId || 'no-task'}|${eventType}|${eventId}|${JSON.stringify(payload)}`;
    }

    _onControllerUiEvent(uiEvent, meta) {
        const taskId = meta && typeof meta.taskId === 'string' ? meta.taskId : '';
        const payload = uiEvent.payload && typeof uiEvent.payload === 'object' ? uiEvent.payload : {};
        const payloadBlocks = Array.isArray(payload.blocks) ? payload.blocks : [];
        if (payloadBlocks.length > 0) {
            const validBlocks = payloadBlocks.filter(
                (b) => b && typeof b === 'object' && typeof b.type === 'string' && b.type.trim(),
            );
            if (validBlocks.length > 0) {
                const key = taskId || 'no-task';
                const current = Array.isArray(this._uiBlocksByTaskId[key]) ? this._uiBlocksByTaskId[key] : [];
                this._uiBlocksByTaskId = {
                    ...this._uiBlocksByTaskId,
                    [key]: [...current, ...validBlocks],
                };
                this.requestUpdate();
            }
        }
        const type = typeof uiEvent.type === 'string' ? uiEvent.type.trim() : '';
        if (!type) {
            return;
        }
        const dedupeKey = this._uiEventDispatchKey(uiEvent, taskId);
        if (this._uiEventDispatchKeys.has(dedupeKey)) {
            return;
        }
        this._uiEventDispatchKeys.add(dedupeKey);
        const detail = this._buildAssistantEnvelope(type, payload, {
            id: uiEvent.id || null,
            source: uiEvent.source || null,
            correlation_id: uiEvent.correlation_id || null,
        });
        this._dispatchAssistantEnvelope(detail);
    }

    _onActionConfigError = (e) => {
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
                    console.warn('platform-chat: action_invoked emit failed', err);
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
            console.warn('platform-chat: Lara default apply rejected', err);
            this._appendLocalAssistantEcho(`Ошибка применения действия: ${m}`);
        });
        queueMicrotask(() => {
            try {
                this._emitAssistantEvent('action_invoked', payload);
            } catch (err) {
                const m = err instanceof Error ? err.message : String(err);
                console.warn('platform-chat: action_invoked emit failed', err);
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
        let contextId = this._runtimeState.currentContextId;
        if (typeof contextId !== 'string' || contextId.length === 0) {
            this._controller.initSession({});
            contextId = this._runtimeState.currentContextId;
        }
        this._controller.applyRuntimeVerb('user_message_added', {
            contextId,
            message: {
                id: `echo_${++mid}`,
                role: 'assistant',
                content: text,
                streaming: false,
                toolCalls: [],
                toolResults: [],
                files: [],
                inputRequired: null,
                breakpoint: null,
            },
        });
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
        const contextId = this.getA2aContextId().trim();
        if (!contextId) {
            this._appendLocalAssistantEcho(
                'Нет идентификатора сессии чата — отправьте сообщение заново и снова нажмите «Создать заметку».',
            );
            return;
        }
        if (this._laraApplyInFlight) {
            return;
        }
        this._laraApplyInFlight = true;
        const url = `${root}/api/v1/lara/pending-actions/apply`;
        try {
            const heads = await this._outboundFlowsRequestHeaders();
            const resp = await fetch(url, {
                method: 'POST',
                credentials: this._requestCredentials(),
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
            this._laraApplyInFlight = false;
        }
    }

    /* ------------------------------------------------------------------ */
    /* Integration credentials badges                                      */
    /* ------------------------------------------------------------------ */

    async _loadEmbedCredentials() {
        if (!this.flowsBaseUrl || !this.useCredentials) {
            return;
        }
        if (typeof this.getAuthToken === 'function') {
            return;
        }
        const headers = await this._outboundFlowsRequestHeaders();
        const resp = await fetch(`${this.flowsBaseUrl}/api/v1/integrations/credentials`, {
            headers,
            credentials: this._requestCredentials(),
        });
        if (!resp.ok) {
            return;
        }
        const data = await resp.json();
        if (!data || typeof data !== 'object' || !Array.isArray(data.items)) {
            throw new Error('platform-chat credentials response must be ListResponse<CredentialInfo>');
        }
        this._credentials = data.items.map((item) => {
            if (
                !item ||
                typeof item !== 'object' ||
                typeof item.provider !== 'string' ||
                typeof item.service !== 'string' ||
                typeof item.created_at !== 'string'
            ) {
                throw new Error('platform-chat credential item contract violation');
            }
            return {
                provider: item.provider,
                service: item.service,
                created_at: item.created_at,
            };
        });
    }

    async _deleteEmbedCredential(provider, service) {
        if (!this.flowsBaseUrl || !this.useCredentials) {
            return;
        }
        if (typeof this.getAuthToken === 'function') {
            return;
        }
        const headers = await this._outboundFlowsRequestHeaders();
        await fetch(
            `${this.flowsBaseUrl}/api/v1/integrations/credentials/${encodeURIComponent(provider)}/${encodeURIComponent(service)}`,
            {
                method: 'DELETE',
                headers,
                credentials: this._requestCredentials(),
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

    /* ------------------------------------------------------------------ */
    /* Greeting / suggested prompts                                        */
    /* ------------------------------------------------------------------ */

    _greetingText() {
        const policyGreeting = this._viewConfig.greetingMessage;
        if (typeof policyGreeting === 'string' && policyGreeting.trim() !== '') {
            return policyGreeting.trim();
        }
        if (this.profile === 'embed_public' || this.profile === 'embed_preview') {
            return this._lb('greeting', '');
        }
        return '';
    }

    _startGreetingTypingIfNeeded() {
        if (this._greetingStarted || !this._visible()) {
            return;
        }
        const greetingText = this._greetingText();
        if (!greetingText) {
            return;
        }
        this._greetingStarted = true;
        this._stickToBottom = true;
        void this._animateGreetingTyping(greetingText);
    }

    async _animateGreetingTyping(text) {
        const greetingText = typeof text === 'string' ? text : '';
        if (!greetingText) {
            return;
        }
        const runId = ++this._greetingTypingRunId;
        this._greeting = { content: '', streaming: true };
        this.requestUpdate();
        const chunkSize = 3;
        const delayMs = 14;
        for (let cursor = 0; cursor < greetingText.length; cursor += chunkSize) {
            if (runId !== this._greetingTypingRunId) {
                return;
            }
            this._greeting = { content: greetingText.slice(0, cursor + chunkSize), streaming: true };
            this.requestUpdate();
            await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
        if (runId !== this._greetingTypingRunId) {
            return;
        }
        this._greeting = { content: greetingText, streaming: false };
        this.requestUpdate();
    }

    _hasUserMessages() {
        return this._currentMessages().some((m) => m && m.role === 'user');
    }

    _onSuggestedPromptClick(prompt) {
        void this._sendUserTurn(String(prompt || ''), []);
    }

    /* ------------------------------------------------------------------ */
    /* Send / stop / new chat                                              */
    /* ------------------------------------------------------------------ */

    /** Metadata верхнего уровня для message/stream: host hook (breakpoints и т.п.) + variables. */
    async _composeSendMetadata() {
        let hostMetadata = {};
        if (typeof this.getSendMetadata === 'function') {
            const raw = await this.getSendMetadata();
            if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
                hostMetadata = raw;
            }
        }
        const variables = await this._mergeSendMetadataVariables();
        return { metadata: { ...hostMetadata, variables }, variables };
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

    _onComposerSend(e) {
        e.stopPropagation();
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        const message = typeof detail.message === 'string' ? detail.message : '';
        const files = Array.isArray(detail.files) ? detail.files : [];
        void this._sendUserTurn(message, files);
    }

    /** @param {File} file @returns {Promise<{ data: string, name: string, mimeType: string }>} */
    _fileToBase64Part(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const base64 = String(reader.result).split(',')[1];
                resolve({ data: base64, name: file.name, mimeType: file.type });
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    _hasActiveBreakpoint() {
        return this._currentMessages().some(
            (message) => message
                && message.role === 'assistant'
                && message.breakpoint
                && typeof message.breakpoint === 'object',
        );
    }

    _onContinueBreakpoint(e) {
        e.stopPropagation();
        void this._sendResumeTurn();
    }

    _onBubbleViewBreakpointState(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('view-breakpoint-state', {
                detail: e.detail,
                bubbles: true,
                composed: true,
            }),
        );
    }

    async _sendResumeTurn() {
        if (this._isLoading() || !this._hasActiveBreakpoint()) {
            return;
        }
        if (!this.flowsBaseUrl || (!this.flowId && !this.embedId)) {
            throw new Error('platform-chat: flowsBaseUrl and (flowId or embedId) are required');
        }
        stopStreamTtsPlayback();
        if (this._streamTtsAllowed() && this._voiceTtsContextReady() && !this._voiceOn) {
            primeStreamTtsPlaybackFromUserGesture();
            this._ttsOnly.primeFromUserGesture();
            await this._ttsOnly.awaitReady();
        }
        const { metadata, variables } = await this._composeSendMetadata();
        this._emitAssistantEvent('context_requested', {
            flow_id: this.flowId || null,
            branch_id: this._branchId() || null,
            embed_id: this.embedId || null,
            variables,
        });
        this._pendingAssistantReplyNotify = true;
        this._stickToBottom = true;
        this._controller.setTarget(this._controllerTarget());
        this._controller.setCredentials(this._requestCredentials());
        try {
            await this._controller.sendResume({ metadata });
        } catch (err) {
            const m = err instanceof Error ? err.message : String(err);
            this._emitAssistantEvent('error', {
                message: m,
                flow_id: this.flowId || null,
                branch_id: this._branchId() || null,
                embed_id: this.embedId || null,
            });
        } finally {
            this._notifyAssistantReplyCompleted();
            this.requestUpdate();
        }
    }

    async _sendUserTurn(message, files) {
        if ((!message && files.length === 0) || this._isLoading()) {
            return;
        }
        if (this._isOperatorProfile()) {
            // operator_handoff: ask/complete через transport; live — tasks/resubscribe.
            this._stickToBottom = true;
            try {
                await this._controller.send({ message, files });
            } finally {
                this.requestUpdate();
            }
            return;
        }
        if (!this.flowsBaseUrl || (!this.flowId && !this.embedId)) {
            throw new Error('platform-chat: flowsBaseUrl and (flowId or embedId) are required');
        }
        stopStreamTtsPlayback();
        if (this.freshContextPerTurn) {
            this._newChat();
        }
        if (this._streamTtsAllowed() && this._voiceTtsContextReady() && !this._voiceOn) {
            primeStreamTtsPlaybackFromUserGesture();
            this._ttsOnly.primeFromUserGesture();
            await this._ttsOnly.awaitReady();
        }
        const fileParts = await Promise.all(files.map((f) => this._fileToBase64Part(f)));
        const { metadata, variables } = await this._composeSendMetadata();
        this._emitAssistantEvent('context_requested', {
            flow_id: this.flowId || null,
            branch_id: this._branchId() || null,
            embed_id: this.embedId || null,
            variables,
        });
        this._pendingAssistantReplyNotify = true;
        this._stickToBottom = true;
        this._controller.setTarget(this._controllerTarget());
        this._controller.setCredentials(this._requestCredentials());
        try {
            await this._controller.send({
                message,
                files: fileParts,
                metadata,
                userMessage: {
                    id: `u_${++mid}`,
                    role: 'user',
                    content: message,
                    timestamp: new Date().toISOString(),
                    files: [],
                    filesMeta: files.map((f) => ({ name: f.name, size: f.size })),
                },
            });
        } catch (err) {
            const m = err instanceof Error ? err.message : String(err);
            this._emitAssistantEvent('error', {
                message: m,
                flow_id: this.flowId || null,
                branch_id: this._branchId() || null,
                embed_id: this.embedId || null,
            });
        } finally {
            this._notifyAssistantReplyCompleted();
            this.requestUpdate();
        }
    }

    _notifyAssistantReplyCompleted() {
        if (!this._pendingAssistantReplyNotify) {
            return;
        }
        this._pendingAssistantReplyNotify = false;
        if (this.display === 'drawer' && !this.open) {
            this.fabUnreadCount += 1;
        }
        this.dispatchEvent(
            new CustomEvent('humanitec-embed-chat-assistant-reply-completed', {
                bubbles: true,
                composed: true,
            }),
        );
    }

    _onComposerStop(e) {
        e.stopPropagation();
        if (!this._viewConfig.allowCancel) {
            return;
        }
        if (!this._isLoading()) {
            return;
        }
        stopStreamTtsPlayback();
        if (this._voiceStreamState !== null) {
            this.dispatchEvent(
                new CustomEvent('humanitec-embed-voice-bridge-user-stop', {
                    bubbles: true,
                    composed: true,
                }),
            );
            this._onVoiceBridgeUserStop();
            return;
        }
        void this._controller.cancel();
    }

    _onComposeEdit(e) {
        if (e && typeof e.stopPropagation === 'function') {
            e.stopPropagation();
        }
        const detail = e.detail;
        const text = detail && typeof detail.text === 'string' ? detail.text : '';
        if (text === '') {
            return;
        }
        const input = this.renderRoot?.querySelector('flows-chat-input');
        if (!input || typeof input.setDraft !== 'function') {
            throw new Error('platform-chat: flows-chat-input.setDraft unavailable');
        }
        input.setDraft(text);
    }

    _onLocaleChange(e) {
        e.stopPropagation();
        const loc = e.detail?.locale;
        if (loc !== 'auto' && loc !== 'ru' && loc !== 'en') {
            return;
        }
        this.interfaceLocale = loc;
        this.requestUpdate();
    }

    _onComposerToast(e) {
        e.stopPropagation();
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        this.dispatchEvent(
            new CustomEvent('embed-toast', {
                detail: { message: typeof detail.message === 'string' ? detail.message : '' },
                bubbles: true,
                composed: true,
            }),
        );
    }

    _newChat() {
        this._pendingAssistantReplyNotify = false;
        this._greetingTypingRunId += 1;
        this._greeting = null;
        this._greetingStarted = false;
        this._uiEventDispatchKeys.clear();
        this._uiBlocksByTaskId = {};
        this._voiceStreamState = null;
        this._controller.newChat();
        this._stickToBottom = true;
        this.requestUpdate();
        this._startGreetingTypingIfNeeded();
    }

    /** Сброс диалога; публичный API хоста (кнопка панели / внешний код). */
    startNewChat() {
        this._newChat();
    }

    /* ------------------------------------------------------------------ */
    /* Render                                                              */
    /* ------------------------------------------------------------------ */

    _headDisplayTitle() {
        const a = this.assistantTitle != null ? String(this.assistantTitle).trim() : '';
        if (a) {
            return a;
        }
        return this._lb('title', 'Assistant');
    }

    static _SCROLL_STICK_PX = 56;

    _onScrollAreaScroll = (e) => {
        const el = e.currentTarget;
        if (!(el instanceof HTMLElement)) {
            return;
        }
        const gap = el.scrollHeight - el.scrollTop - el.clientHeight;
        this._stickToBottom = gap <= PlatformChat._SCROLL_STICK_PX;
    };

    _documentBaseUrl() {
        return (
            _normalizedPlatformUiOrigin(this.platformUiOrigin)
            || _platformApexOriginFromFlowsBaseUrl(this.flowsBaseUrl)
        );
    }

    _fileFromPanelBlock(block) {
        if (!block || typeof block !== 'object' || block.type !== 'file_card') {
            return null;
        }
        const normalized = normalizeFlowChatBlockForPlatformUrls(block);
        const document =
            normalized.document && typeof normalized.document === 'object' && !Array.isArray(normalized.document)
                ? normalized.document
                : null;
        const capabilities =
            normalized.capabilities && typeof normalized.capabilities === 'object' && !Array.isArray(normalized.capabilities)
                ? { ...normalized.capabilities }
                : {};
        const editorUrl = _chatString(normalized.editor_url);
        if (document) {
            capabilities.document = document;
        } else if (editorUrl.length > 0) {
            capabilities.document = {
                binding_id: _chatString(normalized.binding_id),
                file_id: _chatString(normalized.file_id),
                catalog_id: _chatString(normalized.catalog_id),
                document_type: _chatString(normalized.document_type),
                title: _chatString(normalized.name || normalized.original_name),
                namespace: _chatString(normalized.namespace),
                editor_url: editorUrl,
                editable: true,
            };
        }
        return {
            file_id: _chatString(normalized.file_id),
            original_name: _chatString(normalized.original_name || normalized.name),
            content_type: _chatString(normalized.content_type || normalized.mime_type),
            file_size: Number(normalized.file_size || normalized.size) || 0,
            url: _chatString(normalized.url || normalized.preview_url),
            capabilities,
            document: capabilities.document || null,
        };
    }

    _messageBlocks(m) {
        const ownBlocks = m && Array.isArray(m.blocks) ? m.blocks : [];
        const uiBlocks = m && typeof m.taskId === 'string' && this._uiBlocksByTaskId[m.taskId]
            ? this._uiBlocksByTaskId[m.taskId]
            : [];
        let blocks = [...ownBlocks, ...(Array.isArray(uiBlocks) ? uiBlocks : [])];
        for (const tr of Array.isArray(m.toolResults) ? m.toolResults : []) {
            blocks = mergeBlocksFromToolResult(blocks, tr);
        }
        return blocks;
    }

    _sessionFilesForSharedPanel(renderedMessages) {
        const state = this._runtimeState;
        const ctx = state.currentContextId;
        let files = [];
        if (typeof ctx === 'string' && ctx.length > 0) {
            const stateFiles = state.filesByContextId && Array.isArray(state.filesByContextId[ctx])
                ? state.filesByContextId[ctx]
                : [];
            files = _upsertPanelFiles(files, stateFiles);
        }
        for (const message of renderedMessages) {
            files = _upsertPanelFiles(files, Array.isArray(message.files) ? message.files : []);
            for (const fid of Array.isArray(message.fileIds) ? message.fileIds : []) {
                const id = _chatString(fid);
                if (id.length === 0) {
                    continue;
                }
                files = _upsertPanelFiles(files, [{
                    file_id: id,
                    original_name: this._lb('operator_files', 'Attached files'),
                    url: `${CANONICAL_FILES_DOWNLOAD_PREFIX}/${encodeURIComponent(id)}`,
                }]);
            }
            for (const block of Array.isArray(message.blocks) ? message.blocks : []) {
                const file = this._fileFromPanelBlock(block);
                if (file) {
                    files = _upsertPanelFiles(files, [file]);
                }
            }
        }
        return files.filter((file) => _panelFileKey(file).length > 0);
    }

    /** Проекция runtime-сообщения в props flows-chat-message с учётом viewConfig. */
    _projectMessage(m) {
        const vc = this._viewConfig;
        const projected = {
            ...m,
            blocks: m.role === 'assistant' ? this._messageBlocks(m) : [],
        };
        if (!vc.showReasoning) {
            projected.reasoning = '';
        }
        if (!vc.showActivity) {
            projected.activity = '';
        }
        if (!vc.showSkillLoads) {
            projected.skillLoads = [];
        }
        if (vc.toolCallsDisplay === 'hidden') {
            projected.toolCalls = [];
            projected.toolResults = [];
        }
        if (!vc.showBrowserPreviews) {
            projected.browserPreviews = [];
        }
        const rawError = typeof m.error === 'string' ? m.error : '';
        if (rawError && _isEmbedGuestLimitMessage(rawError)) {
            projected.error = '';
            projected.errorI18nKey = null;
            projected.inputRequired = {
                interruptKind: 'oauth_required',
                question: rawError,
                authUrl: '/login',
            };
        } else if (rawError && vc.errorsDisplay === 'generic') {
            projected.error = this._lb('error_generic', 'Request failed. Try again.');
            projected.errorI18nKey = null;
        }
        return projected;
    }

    /** ID последнего user-сообщения в ленте (для run trace на bubble). */
    _lastUserMessageId(messages) {
        if (!Array.isArray(messages)) {
            return '';
        }
        for (let index = messages.length - 1; index >= 0; index -= 1) {
            const message = messages[index];
            if (message && message.role === 'user' && typeof message.id === 'string' && message.id.length > 0) {
                return message.id;
            }
        }
        return '';
    }

    _sessionIdForRuntime() {
        const contextId = this._runtimeState.currentContextId;
        const flowId = this.flowId;
        if (typeof flowId !== 'string' || flowId.length === 0) {
            return '';
        }
        if (typeof contextId !== 'string' || contextId.length === 0) {
            return '';
        }
        return `${flowId}:${contextId}`;
    }

    _messageLocale() {
        const raw = String(this.interfaceLocale || '').trim().toLowerCase();
        if (raw === 'ru' || raw === 'en') {
            return raw;
        }
        return this._langForUiLabels();
    }

    _messageAuthor(message) {
        const role = typeof message?.role === 'string' ? message.role : 'assistant';
        const author = normalizeChatAuthor(message?.author, role);
        if (author.name.length > 0) {
            return author;
        }
        if (author.kind === 'agent') {
            return { ...author, name: this._headDisplayTitle() };
        }
        if (author.kind === 'subagent' && author.flowId.length > 0) {
            return { ...author, name: author.flowId };
        }
        return author;
    }

    _renderSurfaceMessage(m, surfaceContext) {
        const labels = this._mergedLabels();
        const flowsRoot = (this.flowsBaseUrl && String(this.flowsBaseUrl).trim()) || '';
        const vc = this._viewConfig;
        const ctx = surfaceContext && typeof surfaceContext === 'object' ? surfaceContext : {};
        const isLastUser = Boolean(ctx.isLastUser);
        const runTraceEntries = Array.isArray(ctx.runTraceEntries) ? ctx.runTraceEntries : [];
        const sessionId = typeof ctx.sessionId === 'string' ? ctx.sessionId : '';
        const traceTaskId = isLastUser && typeof ctx.traceTaskId === 'string' ? ctx.traceTaskId : '';
        return html`
            <flows-chat-message
                variant="embed"
                data-role=${m.role || 'assistant'}
                .role=${m.role || 'assistant'}
                .author=${this._messageAuthor(m)}
                .content=${m.content || ''}
                .timestamp=${m.timestamp || ''}
                .locale=${this._messageLocale()}
                ?streaming=${Boolean(m.streaming)}
                .reasoning=${m.reasoning || ''}
                .activity=${m.activity || ''}
                .toolCalls=${Array.isArray(m.toolCalls) ? m.toolCalls : []}
                .toolResults=${Array.isArray(m.toolResults) ? m.toolResults : []}
                .browserPreviews=${Array.isArray(m.browserPreviews) ? m.browserPreviews : []}
                .skillLoads=${Array.isArray(m.skillLoads) ? m.skillLoads : []}
                .inputRequired=${m.inputRequired || null}
                .handoff=${m.handoff || null}
                .handback=${m.handback || null}
                .operatorReply=${m.operatorReply || ''}
                .breakpoint=${m.breakpoint || null}
                .files=${Array.isArray(m.files) ? m.files : []}
                .filesMeta=${Array.isArray(m.filesMeta) ? m.filesMeta : []}
                .fileIds=${Array.isArray(m.fileIds) ? m.fileIds : []}
                .blocks=${Array.isArray(m.blocks) ? m.blocks : []}
                .taskId=${m.taskId || ''}
                .traceTaskId=${traceTaskId}
                .sessionId=${sessionId}
                .runTraceEntries=${isLastUser ? runTraceEntries : []}
                ?isLastUserMessage=${isLastUser}
                ?runTraceAvailable=${isLastUser && runTraceEntries.length > 0}
                .error=${typeof m.error === 'string' ? m.error : ''}
                .errorI18nKey=${typeof m.errorI18nKey === 'string' ? m.errorI18nKey : ''}
                .labels=${labels}
                .flowRoot=${flowsRoot}
                .useCredentials=${this.useCredentials}
                .voiceBaseUrl=${this._assistantTtsVoiceBaseUrl()}
                .getHeaders=${typeof this.getAuthToken === 'function' ? this.getAuthToken : null}
                .showAvatar=${false}
                .showHeader=${true}
                .headerCompact=${true}
                .showTraceControls=${vc.showTraceActions}
                .showRunTraceControls=${vc.showRunTrace && isLastUser}
                .showLogsAction=${vc.showTraceActions}
                .showDurableHistoryAction=${vc.showTraceActions}
                .showUserActions=${true}
                .showAssistantActions=${true}
                @compose-edit=${this._onComposeEdit}
                @show-tracing=${this._onBubbleShowTracing}
                @show-logs=${this._onBubbleShowLogs}
                @show-durable-history=${this._onBubbleShowDurableHistory}
                @continue-breakpoint=${this._onContinueBreakpoint}
                @view-breakpoint-state=${this._onBubbleViewBreakpointState}
            ></flows-chat-message>
        `;
    }

    _onBubbleShowTracing(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('show-tracing', {
                detail: e.detail,
                bubbles: true,
                composed: true,
            }),
        );
    }

    _onBubbleShowLogs(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('show-logs', {
                detail: e.detail,
                bubbles: true,
                composed: true,
            }),
        );
    }

    _onBubbleShowDurableHistory(e) {
        e.stopPropagation();
        this.dispatchEvent(
            new CustomEvent('show-durable-history', {
                detail: e.detail,
                bubbles: true,
                composed: true,
            }),
        );
    }

    _renderCredBadges() {
        if (this._credentials.length === 0) {
            return nothing;
        }
        return html`
            <div class="cred-badges">
                ${this._credentials.map((c) => {
                    const key = `${c.provider}:${c.service}`;
                    const letter = (c.service || '?')[0].toUpperCase();
                    const colors = { google: '#4285F4', yandex: '#FC3F1D' };
                    const bg = colors[c.provider] || '#666';
                    const title = this._lb('integration_badge_title', 'Connected')
                        .replace('{provider}', c.provider)
                        .replace('{service}', c.service);
                    return html`
                        <div class="cred-anchor">
                            <button
                                class="cred-badge"
                                style="background:${bg}"
                                title="${title}"
                                @click=${(e) => this._toggleCredPopover(key, e)}
                            >
                                ${letter}
                            </button>
                            ${this._credPopover === key
                                ? html`
                                      <div class="cred-popover" @click=${(e) => e.stopPropagation()}>
                                          <div class="cred-popover-title">
                                              ${c.provider} / ${c.service}
                                          </div>
                                          <button
                                              class="cred-disconnect"
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
        `;
    }

    _renderSuggestedPrompts() {
        const prompts = this._viewConfig.suggestedPrompts;
        if (!Array.isArray(prompts) || prompts.length === 0) {
            return nothing;
        }
        if (this._hasUserMessages() || this._isLoading()) {
            return nothing;
        }
        return html`
            <div class="suggested-prompts">
                ${prompts.map(
                    (p) => html`
                        <button
                            type="button"
                            class="suggested-prompt"
                            @click=${() => this._onSuggestedPromptClick(p)}
                        >
                            ${p}
                        </button>
                    `,
                )}
            </div>
        `;
    }

    _renderSurface({ showHeader }) {
        const vc = this._viewConfig;
        const loading = this._isLoading();
        const rawMessages = this._currentMessages();
        const messages = rawMessages.map((m) => this._projectMessage(m));
        const lastUserMessageId = this._lastUserMessageId(rawMessages);
        const contextId = this._runtimeState.currentContextId;
        const runTraceEntries =
            typeof contextId === 'string' && contextId.length > 0
                ? this._runtimeState.runTraceByContextId[contextId] || []
                : [];
        const sessionId = this._sessionIdForRuntime();
        const traceTaskId =
            typeof this._runtimeState.currentTaskId === 'string' ? this._runtimeState.currentTaskId : '';
        const surfaceContextBase = {
            runTraceEntries,
            sessionId,
            traceTaskId,
        };
        const files = vc.showFilesPanel ? this._sessionFilesForSharedPanel(messages) : [];
        const wsDuplex = this._composerWsDuplex();
        const dictation = this._composerBrowserDictation();
        const head = showHeader
            ? html`
                  <header class="surface-head">
                      <span>${this._headDisplayTitle()}</span>
                      <button type="button" class="link" @click=${this._newChat}>
                          ${this._lb('new_chat', 'New chat')}
                      </button>
                  </header>
              `
            : nothing;
        return html`
            ${head}
            <div class="surface">
                ${this._renderCredBadges()}
                ${files.length > 0
                    ? html`
                          <flows-chat-files-panel
                              .files=${files}
                              active-company-id=${this.companyId || ''}
                              document-base-url=${this._documentBaseUrl()}
                          ></flows-chat-files-panel>
                      `
                    : nothing}
                <div class="scroll" @scroll=${this._onScrollAreaScroll}>
                    ${this._greeting
                        ? this._renderSurfaceMessage(
                              {
                                  id: 'greeting',
                                  role: 'assistant',
                                  content: this._greeting.content,
                                  streaming: this._greeting.streaming,
                              },
                              surfaceContextBase,
                          )
                        : nothing}
                    ${messages.map((m) =>
                        this._renderSurfaceMessage(m, {
                            ...surfaceContextBase,
                            isLastUser:
                                m.role === 'user'
                                && typeof m.id === 'string'
                                && m.id.length > 0
                                && m.id === lastUserMessageId,
                        }),
                    )}
                </div>
                ${this._renderSuggestedPrompts()}
                ${this._composerVisible()
                    ? html`
                <div class="chat-composer">
                    <flows-chat-input
                        .loading=${loading}
                        .cancelBusy=${this._controller.cancelBusy || !vc.allowCancel}
                        .placeholder=${this._lb('placeholder', 'Message...')}
                        .labels=${this._mergedLabels()}
                        .showVoice=${wsDuplex || dictation}
                        .voiceDuplex=${wsDuplex}
                        .speechDictation=${dictation}
                        .voiceActive=${this._voiceOn}
                        .voiceStatus=${this._voiceStatus || 'idle'}
                        .showLocaleControl=${this.showLocaleControl}
                        .interfaceLocale=${this.interfaceLocale || 'auto'}
                        @send=${this._onComposerSend}
                        @stop=${this._onComposerStop}
                        @voice-toggle=${(e) => {
                            e.stopPropagation();
                            this._toggleVoice();
                        }}
                        @tts-output-toggle=${(e) => {
                            e.stopPropagation();
                            this._toggleTtsOutput();
                        }}
                        @locale-change=${this._onLocaleChange}
                        @toast=${this._onComposerToast}
                    ></flows-chat-input>
                </div>
                      `
                    : nothing}
            </div>
        `;
    }

    _renderDrawer() {
        const L = this._mergedLabels();
        const headTitle = this._headDisplayTitle();
        const fabAria = this.open ? L.fab_aria_close : this._fabOpenAriaLabel(L);
        const fsLabel = this.panelMaximized ? L.panel_exit_fullscreen : L.panel_fullscreen;
        const showLauncherButton = this.showLauncher && !this.open;
        const panelHeadClass = `panel-head ${this._isPanelDraggable() ? 'panel-head--draggable' : ''} ${
            this._panelDragActive ? 'panel-head--dragging' : ''
        }`;
        return html`
            ${showLauncherButton
                ? html`
                      <button
                          type="button"
                          class="fab"
                          style=${this._fabInlineStyle()}
                          aria-label=${fabAria}
                          @pointerdown=${this._onFabPointerDown}
                          @click=${this._onFabClick}
                      >
                          ${this.fabUnreadCount > 0
                              ? html`<span class="fab-badge" aria-hidden="true">${this._fabBadgeText()}</span>`
                              : nothing}
                          <img
                              class="fab-logo"
                              src="/static/core/assets/service_logos/linnex_spinner_logo.png"
                              alt=""
                              aria-hidden="true"
                          />
                      </button>
                  `
                : ''}

            <div
                class="panel ${this.panelMaximized ? 'panel--maximized' : ''} ${!this.open ? 'panel--collapsed' : ''}"
                style=${this._panelInlineStyle()}
                aria-hidden=${this.open ? 'false' : 'true'}
                ?inert=${!this.open}
            >
                <div class=${panelHeadClass} @pointerdown=${this._onPanelHeadPointerDown}>
                    <span class="panel-head-title">${headTitle}</span>
                    <div class="panel-head-actions">
                        <button
                            type="button"
                            class="close-btn"
                            title=${readTtsOutputEnabled() ? L.tts_output_disable : L.tts_output_enable}
                            aria-label=${readTtsOutputEnabled() ? L.tts_output_disable : L.tts_output_enable}
                            @click=${this._toggleTtsOutput}
                        >
                            ${readTtsOutputEnabled()
                                ? html`<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                      <path
                                          d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"
                                          fill="currentColor"
                                      />
                                  </svg>`
                                : html`<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                      <path
                                          d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73 9.27 8l-5-5zM12 4l-1.41 1.41L12 8.18V4z"
                                          fill="currentColor"
                                      />
                                  </svg>`}
                        </button>
                        <button
                            type="button"
                            class="close-btn"
                            title=${L.new_chat}
                            aria-label=${L.new_chat}
                            @click=${this._newChat}
                        >
                            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                <path
                                    d="M4 20h4l10-10-4-4L4 16v4Z"
                                    stroke="currentColor"
                                    stroke-width="2"
                                    stroke-linejoin="round"
                                />
                            </svg>
                        </button>
                        <button
                            type="button"
                            class="close-btn"
                            title=${fsLabel}
                            aria-label=${fsLabel}
                            @click=${this._togglePanelFullscreen}
                        >
                            ${this.panelMaximized
                                ? html`<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                      <path
                                          d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"
                                          stroke="currentColor"
                                          stroke-width="2"
                                          stroke-linecap="round"
                                          stroke-linejoin="round"
                                      />
                                  </svg>`
                                : html`<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                      <path
                                          d="M9 3H3v6M15 3h6v6M9 21H3v-6M15 21h6v-6"
                                          stroke="currentColor"
                                          stroke-width="2"
                                          stroke-linecap="round"
                                          stroke-linejoin="round"
                                      />
                                  </svg>`}
                        </button>
                        <button
                            type="button"
                            class="close-btn"
                            title=${L.panel_minimize}
                            aria-label=${L.panel_minimize}
                            @click=${this._minimize}
                        >
                            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                                <path
                                    d="M5 12h14"
                                    stroke="currentColor"
                                    stroke-width="2"
                                    stroke-linecap="round"
                                />
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="drawer-chat">${this._renderSurface({ showHeader: false })}</div>
            </div>
        `;
    }

    render() {
        if (this.display === 'drawer') {
            return this._renderDrawer();
        }
        return this._renderSurface({ showHeader: !this.hideHeader });
    }
}

customElements.define('platform-chat', PlatformChat);

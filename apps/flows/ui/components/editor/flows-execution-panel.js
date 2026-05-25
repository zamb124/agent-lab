/**
 * flows-execution-panel — плавающая панель «Запуск агента» в редакторе.
 *
 * Видна, пока `state.flowsEditor.executionPanelOpen === true`. Источники state:
 *   - useOp('flows/editor') — режим, currentBranchId, previewExecutionState.breakpoints;
 *   - useResource('flows/chat') — currentContextId/currentTaskId/streaming, сообщения;
 *   - useOp('flows/chat_send') / useOp('flows/chat_cancel') — SSE A2A
 *     (`POST /flows/api/v1/{flow_id}` с `message/stream` / `tasks/cancel`);
 *   - useSlice('flows/execution_ui') — persistContext.
 *
 * Вкладка Chat: лента `chat-message` из `flows/chat` (тот же bucket, что и SSE).
 * Разворот — кнопка в шапке: `position: fixed` + `nextModalLayerZIndex()`, иначе z-index
 * не выходит из `canvas-host` и панель свойств (`flows-floating-panel`, до 25100) перекрывает.
 * Снизу — `--flows-exec-fab-gutter`, чтобы поле ввода не заезжало на FAB embed-ассистента.
 * Кнопки State / Tracing открывают модалки `flows.state`, `flows.tracing`.
 * «Сбросить чат» вызывает `flows/chat` `resetSession` (и `tasks/cancel` при активном стриме).
 * Голосовой режим (микрофон у поля ввода): та же связка voice WS + A2A, что на странице чата,
 * через `apps/flows/ui/_helpers/flow-voice-session.js`.
 */

import { html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/glass-button.js';
import '../chat/flows-chat-run-trace.js';
import '../chat/chat-message.js';
import '../chat/chat-input.js';
import '../chat/chat-files-panel.js';
import {
    asArray,
    asObject,
    asString,
    authActiveCompanyId,
    deriveRunPanelStatus,
    isPlainObject,
} from '../../_helpers/flows-resolvers.js';
import { collectCurrentChatFiles } from '../../_helpers/chat-files.js';
import { resolveFlowsChatTaskId } from '../../_helpers/resolve-flows-chat-task-id.js';
import {
    createFlowVoiceSession,
    disposeFlowVoiceSession,
    fetchFlowVoiceWsQuery,
    flowsVoiceAuxiliaryHttpHeadersStub,
    formatFlowVoiceConnectErrorDetail,
    normalizeFlowVoiceSttLanguage,
    resolveFlowVoiceHttpOrigin,
} from '../../_helpers/flow-voice-session.js';
import { relayA2aVoiceStreamRpcFrame } from '../../_helpers/relay-voice-a2a-to-chat.js';
import {
    readTtsOutputEnabled,
    toggleTtsOutputEnabled,
    TTS_OUTPUT_CHANGED_EVENT,
    TTS_OUTPUT_STORAGE_KEY,
} from '@platform/lib/voice/tts-output-pref.js';
import { VoiceMediaSession } from '@platform/lib/voice/voice-media-session.js';
import {
    clearStreamTtsTarget,
    primeStreamTtsPlaybackFromUserGesture,
    setStreamTtsTarget,
    stopStreamTtsPlayback,
} from '@platform/lib/voice/stream-tts-registry.js';

const ACCEPT_FILE_TYPES = '*/*';
const EMPTY_TRACE = Object.freeze([]);
const PANEL_VIEWPORT_MARGIN = 12;
const PANEL_MIN_WIDTH = 360;
const PANEL_MIN_HEIGHT = 320;
const PANEL_DEFAULT_HEIGHT = 620;
const PANEL_COLLAPSED_HEIGHT = 64;

function _executionFileToUploadFile(raw) {
    if (typeof File === 'undefined') {
        throw new Error('flows-execution-panel: File API is unavailable');
    }
    if (!(raw instanceof File)) {
        throw new Error('flows-execution-panel: chat-input must pass File instances');
    }
    return raw;
}

export class FlowsExecutionPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        flowId: { type: String },
        branchId: { type: String },
        _panelTab: { type: String, state: true },
        _layoutExpanded: { type: Boolean, state: true },
        _collapsed: { type: Boolean, state: true },
        _voiceOn: { type: Boolean, state: true },
        _voiceStatus: { type: String, state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                /* Зазор под FAB embed-чата (56px + bottom 16px + запас), см. platform-embed-chat-drawer .fab */
                --flows-exec-fab-gutter: calc(56px + max(16px, env(safe-area-inset-bottom, 0px)) + 12px);
                position: absolute;
                top: 12px;
                right: 12px;
                bottom: calc(12px + var(--flows-exec-fab-gutter));
                left: auto;
                z-index: 5;
                display: flex;
                flex-direction: column;
                width: min(460px, calc(100% - 24px));
                max-width: none;
                min-height: 0;
                pointer-events: none;
            }
            :host([data-layout-expanded]) {
                position: fixed;
                top: 12px;
                right: 12px;
                bottom: calc(12px + var(--flows-exec-fab-gutter));
                left: 12px;
                width: auto;
            }
            :host([data-floating]) {
                right: auto;
                bottom: auto;
            }
            .panel {
                pointer-events: auto;
                position: relative;
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                overflow: hidden;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-2xl);
                box-shadow: var(--glass-shadow-medium);
                backdrop-filter: blur(20px);
            }
            .panel.is-collapsed {
                flex: 0 0 auto;
                gap: 0;
                padding: var(--space-3) var(--space-4);
            }
            .panel-header {
                flex-shrink: 0;
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-3);
                flex-wrap: wrap;
                cursor: grab;
                user-select: none;
                touch-action: none;
            }
            :host([data-dragging]) .panel-header {
                cursor: grabbing;
            }
            .panel.is-collapsed .panel-header {
                align-items: center;
            }
            .panel-header-main {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .panel-header-aside {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
                cursor: default;
            }
            .panel-title-row {
                display: flex;
                flex-direction: column;
                gap: 6px;
                min-width: 0;
            }
            .panel-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .status-badge {
                display: inline-flex;
                align-items: center;
                width: fit-content;
                padding: 2px 10px;
                border-radius: var(--radius-full);
                font-size: 11px;
                font-weight: var(--font-semibold);
                letter-spacing: 0.02em;
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }
            .status-badge[data-status='running'] {
                border-color: var(--warning-border, rgba(234, 179, 8, 0.45));
                background: var(--warning-bg, rgba(234, 179, 8, 0.12));
                color: var(--warning, #ca8a04);
                animation: execPanelPulse 1.4s ease-in-out infinite;
            }
            .status-badge[data-status='passed'] {
                border-color: var(--success-border);
                background: var(--success-bg);
                color: var(--success, #16a34a);
            }
            .status-badge[data-status='failed'] {
                border-color: var(--error-border);
                background: var(--error-bg);
                color: var(--error);
            }
            @keyframes execPanelPulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.72; }
            }
            .tabs {
                flex-shrink: 0;
                display: flex;
                gap: 2px;
                padding: 4px;
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                box-shadow: var(--glass-inner-glow-subtle);
            }
            .tab {
                flex: 1;
                min-height: 36px;
                padding: 8px 12px;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast), box-shadow var(--duration-fast);
            }
            .tab:hover {
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
            }
            .tab[data-active] {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-inner-glow-medium), var(--glass-shadow-subtle);
            }
            .tab-toolbar {
                flex-shrink: 0;
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                justify-content: flex-end;
            }
            .icon-btn-close {
                box-sizing: border-box;
                width: 36px;
                height: 36px;
                padding: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .icon-btn-close:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .resize-handle {
                position: absolute;
                right: 4px;
                bottom: 4px;
                width: 18px;
                height: 18px;
                padding: 0;
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-tertiary);
                cursor: nwse-resize;
                opacity: 0.65;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                touch-action: none;
            }
            .resize-handle::before,
            .resize-handle::after {
                content: '';
                position: absolute;
                right: 4px;
                bottom: 4px;
                width: 8px;
                height: 1px;
                border-radius: var(--radius-full);
                background: currentColor;
                transform: rotate(-45deg);
                transform-origin: right center;
            }
            .resize-handle::after {
                right: 3px;
                bottom: 8px;
                width: 5px;
            }
            .resize-handle:hover {
                opacity: 1;
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }
            :host([data-resizing]) .resize-handle {
                opacity: 1;
                color: var(--text-primary);
            }
            .panel.is-collapsed .resize-handle {
                display: none;
            }
            .panel-body {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow: hidden;
            }
            .tab-panel {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow: hidden;
            }
            .tab-panel[data-tab='chat'] .execution-chat-input {
                flex-shrink: 0;
                margin-top: auto;
            }
            chat-input.execution-chat-input {
                padding: 0;
            }
            .trace-panel-inner {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .trace-panel-inner flows-chat-run-trace {
                flex: 1;
                min-height: 0;
            }
            .state-tab {
                padding: var(--space-4);
                border-radius: var(--radius-xl);
                border: 1px dashed var(--glass-border-medium);
                background: var(--glass-solid-subtle);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                align-items: stretch;
            }
            .state-tab-hint {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.5;
                margin: 0;
            }
            .message-feed {
                flex: 1;
                min-height: 0;
                overflow-x: hidden;
                overflow-y: auto;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-2) 2px var(--space-2) 0;
            }
            .persist-wrap {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._panelTab = 'chat';
        this._editor = this.useOp('flows/editor');
        this._chat = this.useResource('flows/chat');
        this._send = this.useOp('flows/chat_send');
        this._cancel = this.useOp('flows/chat_cancel');
        this._upload = this.useOp('flows/file_upload');
        this._ui = this.useSlice('flows/execution_ui');
        this._lastChatCtx = '';
        this._lastChatLen = 0;
        this._layoutExpanded = false;
        this._collapsed = false;
        this._panelRect = null;
        this._dragState = null;
        this._resizeState = null;
        this._restorePanelHeight = 0;
        this._boundPanelPointerMove = (e) => this._onPanelPointerMove(e);
        this._boundPanelPointerUp = () => this._endPanelPointerInteraction();
        this._boundPanelViewportResize = () => this._clampFloatingPanelToViewport();
        this._voiceOn = false;
        this._voiceStatus = 'idle';
        /** @type {import('@platform/lib/voice/voice-media-session.js').VoiceMediaSession | null} */
        this._voiceMedia = null;
        /** @type {import('@platform/lib/voice/voice-agent-bridge.js').VoiceAgentBridge | null} */
        this._voiceBridge = null;
        /** @type {(() => void) | null} */
        this._voiceA2aSettledHandler = null;
        /** @type {((e: Event) => void) | null} */
        this._voiceA2aAbortedHandler = null;
        this._activeCompanySel = this.select((s) => authActiveCompanyId(s));
        this._localeSel = this.select((s) => s.i18n.locale);
        /** @type {InstanceType<typeof VoiceMediaSession> | null} */
        this._ttsOnlyMedia = null;
        this._ttsOnlyStreamStarting = false;
        this._onTtsExecPref = () => {
            if (!readTtsOutputEnabled()) {
                this._disposeTtsOnlyStream();
            }
            this.requestUpdate();
        };
        this._onTtsExecStorage = (e) => {
            if (e.storageArea === window.localStorage && e.key === TTS_OUTPUT_STORAGE_KEY) {
                if (!readTtsOutputEnabled()) {
                    this._disposeTtsOnlyStream();
                }
                this.requestUpdate();
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent('flows/chat/compose_edit', (ev) => {
            const p = ev.payload && typeof ev.payload === 'object' ? ev.payload : null;
            const text = p && typeof p.text === 'string' ? p.text : '';
            if (text === '') {
                return;
            }
            void this.updateComplete.then(() => {
                this._chatInputElement().setDraft(text);
            });
        });
        if (typeof window !== 'undefined') {
            window.addEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsExecPref);
            window.addEventListener('storage', this._onTtsExecStorage);
            window.addEventListener('resize', this._boundPanelViewportResize);
        }
    }

    disconnectedCallback() {
        this._endPanelPointerInteraction();
        this._disposeTtsOnlyStream();
        if (this._voiceOn) {
            const m = this._voiceMedia;
            const b = this._voiceBridge;
            this._voiceMedia = null;
            this._voiceBridge = null;
            this._voiceOn = false;
            this._voiceStatus = 'idle';
            void disposeFlowVoiceSession(m, b);
        }
        if (typeof window !== 'undefined') {
            window.removeEventListener(TTS_OUTPUT_CHANGED_EVENT, this._onTtsExecPref);
            window.removeEventListener('storage', this._onTtsExecStorage);
            window.removeEventListener('resize', this._boundPanelViewportResize);
        }
        super.disconnectedCallback();
    }

    _chatInputElement() {
        const input = this.renderRoot?.querySelector('chat-input');
        if (
            !input
            || typeof input.setDraft !== 'function'
            || typeof input.clear !== 'function'
        ) {
            throw new Error('flows-execution-panel: chat-input missing');
        }
        return input;
    }

    updated(changedProperties) {
        const editorStateForVoice = asObject(this._editor.state);
        if (!editorStateForVoice.executionPanelOpen && this._voiceOn) {
            void this._stopExecPanelVoice();
        }
        if (
            (changedProperties.has('flowId') || changedProperties.has('branchId')) &&
            this._voiceOn
        ) {
            void this._stopExecPanelVoice();
        }
        if ((changedProperties.has('flowId') || changedProperties.has('branchId')) && !this._voiceOn) {
            this._disposeTtsOnlyStream();
        }
        super.updated(changedProperties);
        if (this._panelTab !== 'chat') {
            return;
        }
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string' ? chatState.currentContextId : '';
        if (ctx !== this._lastChatCtx) {
            this._lastChatCtx = ctx;
            this._lastChatLen = this._panelChatMessages().length;
            this._scrollChatFeedBottom();
            return;
        }
        const n = this._panelChatMessages().length;
        const grew = n > this._lastChatLen;
        this._lastChatLen = n;
        if (grew || Boolean(chatState.streaming)) {
            this._scrollChatFeedBottom();
        }
    }

    _scrollChatFeedBottom() {
        requestAnimationFrame(() => {
            const root = this.renderRoot;
            if (!root || typeof root.querySelector !== 'function') {
                return;
            }
            const el = root.querySelector('.message-feed');
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    _panelChatMessages() {
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string' ? chatState.currentContextId : null;
        if (!ctx) {
            return [];
        }
        const bucket = chatState.messagesByContextId[ctx];
        if (!bucket || !Array.isArray(bucket.messages)) {
            return [];
        }
        return bucket.messages;
    }

    _ensureContextId() {
        const chatState = this._chat.state;
        const ctx = chatState && typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (ctx && ctx.length > 0) return ctx;
        this._chat.initSession({ flowId: this.flowId, contextId: `editor_${Date.now()}` });
        const after = this._chat.state;
        if (!after || typeof after.currentContextId !== 'string' || after.currentContextId.length === 0) {
            throw new Error('flows-execution-panel: failed to init chat context');
        }
        return after.currentContextId;
    }

    _lastAssistantMessage() {
        const chatState = this._chat.state;
        const ctx = chatState && typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (!ctx) return null;
        const bucket = chatState.messagesByContextId[ctx];
        if (!bucket || !Array.isArray(bucket.messages)) return null;
        for (let i = bucket.messages.length - 1; i >= 0; i--) {
            const m = bucket.messages[i];
            if (m && m.role === 'assistant') return m;
        }
        return null;
    }

    /** Ассистент текущего task_id (чтобы не показывать ответ прошлого запуска до первого чанка). */
    _activeAssistantMessage() {
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (!ctx) {
            return null;
        }
        const tid = typeof chatState.currentTaskId === 'string'
            ? chatState.currentTaskId
            : null;
        const bucket = chatState.messagesByContextId[ctx];
        if (!bucket || !Array.isArray(bucket.messages)) {
            return null;
        }
        if (tid) {
            for (let i = bucket.messages.length - 1; i >= 0; i -= 1) {
                const m = bucket.messages[i];
                if (m && m.role === 'assistant' && m.taskId === tid) {
                    return m;
                }
            }
        }
        return this._lastAssistantMessage();
    }

    _currentRunTrace() {
        const chatState = asObject(this._chat.state);
        const ctx = typeof chatState.currentContextId === 'string'
            ? chatState.currentContextId
            : null;
        if (!ctx) {
            return EMPTY_TRACE;
        }
        const byCtx = chatState.runTraceByContextId;
        if (!byCtx || typeof byCtx !== 'object') {
            return EMPTY_TRACE;
        }
        const list = byCtx[ctx];
        if (!Array.isArray(list)) {
            return EMPTY_TRACE;
        }
        return list;
    }

    _currentFiles() {
        return collectCurrentChatFiles(this._chat.state, this._panelChatMessages());
    }

    _onFilesPanelUpdated(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const files = asArray(detail.files);
        if (files.length === 0) {
            return;
        }
        const contextId = asString(this._chat.state?.currentContextId);
        if (contextId.length === 0) {
            return;
        }
        this._chat.updateFiles({ contextId, files });
    }

    _onPersistChange(e) {
        const value = Boolean(e.detail && e.detail.value);
        this._ui.togglePersistContext({ value });
    }

    _panelViewport() {
        if (typeof window === 'undefined') {
            return { width: 1024, height: 768 };
        }
        const doc = window.document && window.document.documentElement;
        return {
            width: window.innerWidth || (doc ? doc.clientWidth : 1024) || 1024,
            height: window.innerHeight || (doc ? doc.clientHeight : 768) || 768,
        };
    }

    _panelMinWidth() {
        const viewport = this._panelViewport();
        return Math.max(240, Math.min(PANEL_MIN_WIDTH, viewport.width - PANEL_VIEWPORT_MARGIN * 2));
    }

    _panelMinHeight(collapsed = this._collapsed) {
        if (collapsed) {
            return PANEL_COLLAPSED_HEIGHT;
        }
        const viewport = this._panelViewport();
        return Math.max(220, Math.min(PANEL_MIN_HEIGHT, viewport.height - PANEL_VIEWPORT_MARGIN * 2));
    }

    _clampPanelRect(rect, collapsed = this._collapsed) {
        const viewport = this._panelViewport();
        const margin = PANEL_VIEWPORT_MARGIN;
        const minWidth = this._panelMinWidth();
        const minHeight = this._panelMinHeight(collapsed);
        const maxWidth = Math.max(minWidth, viewport.width - margin * 2);
        const maxHeight = Math.max(minHeight, viewport.height - margin * 2);
        const width = Math.min(Math.max(Number(rect.width) || minWidth, minWidth), maxWidth);
        const rawHeight = collapsed ? PANEL_COLLAPSED_HEIGHT : Number(rect.height) || minHeight;
        const height = Math.min(Math.max(rawHeight, minHeight), maxHeight);
        const leftMax = Math.max(margin, viewport.width - width - margin);
        const topMax = Math.max(margin, viewport.height - height - margin);
        const left = Math.min(Math.max(Number(rect.left) || margin, margin), leftMax);
        const top = Math.min(Math.max(Number(rect.top) || margin, margin), topMax);
        return { left, top, width, height };
    }

    _defaultFloatingPanelRect(collapsed = this._collapsed) {
        const viewport = this._panelViewport();
        const margin = PANEL_VIEWPORT_MARGIN;
        const maxWidth = Math.max(this._panelMinWidth(), viewport.width - margin * 2);
        const width = Math.min(460, maxWidth);
        const height = collapsed
            ? PANEL_COLLAPSED_HEIGHT
            : Math.min(
                Math.max(this._panelMinHeight(false), PANEL_DEFAULT_HEIGHT),
                Math.max(this._panelMinHeight(false), viewport.height - margin * 2),
            );
        return this._clampPanelRect({
            left: viewport.width - width - margin,
            top: margin,
            width,
            height,
        }, collapsed);
    }

    _readCurrentPanelRect() {
        const rect = this.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            return this._clampPanelRect({
                left: rect.left,
                top: rect.top,
                width: rect.width,
                height: rect.height,
            });
        }
        return this._defaultFloatingPanelRect();
    }

    _bringPanelToFront() {
        this.style.zIndex = String(nextModalLayerZIndex());
    }

    _syncPanelHostAttributes() {
        if (this._collapsed) {
            this.setAttribute('data-collapsed', '');
        } else {
            this.removeAttribute('data-collapsed');
        }
    }

    _applyFloatingPanelRect(rect, { bringToFront = false } = {}) {
        const clamped = this._clampPanelRect(rect);
        this._panelRect = clamped;
        this._layoutExpanded = false;
        this.removeAttribute('data-layout-expanded');
        this.setAttribute('data-floating', '');
        this._syncPanelHostAttributes();
        if (bringToFront) {
            this._bringPanelToFront();
        }
        this.style.position = 'fixed';
        this.style.left = `${Math.round(clamped.left)}px`;
        this.style.top = `${Math.round(clamped.top)}px`;
        this.style.right = 'auto';
        this.style.bottom = 'auto';
        this.style.width = `${Math.round(clamped.width)}px`;
        this.style.height = `${Math.round(clamped.height)}px`;
    }

    _clearFloatingPanelRect({ keepZIndex = false } = {}) {
        this._panelRect = null;
        this.removeAttribute('data-floating');
        this.removeAttribute('data-dragging');
        this.removeAttribute('data-resizing');
        this.style.position = '';
        this.style.left = '';
        this.style.top = '';
        this.style.right = '';
        this.style.bottom = '';
        this.style.width = '';
        this.style.height = '';
        if (!keepZIndex) {
            this.style.zIndex = '';
        }
    }

    _ensureFloatingPanelRect({ fromDefault = false, bringToFront = false } = {}) {
        const rect = fromDefault || !this._panelRect
            ? (fromDefault ? this._defaultFloatingPanelRect() : this._readCurrentPanelRect())
            : this._panelRect;
        this._applyFloatingPanelRect(rect, { bringToFront });
        return this._panelRect;
    }

    _clampFloatingPanelToViewport() {
        if (!this._panelRect || this._layoutExpanded) {
            return;
        }
        this._applyFloatingPanelRect(this._panelRect);
    }

    _isPanelControlTarget(target) {
        if (!(target instanceof Element)) {
            return false;
        }
        return Boolean(target.closest([
            'button',
            'a',
            'input',
            'textarea',
            'select',
            'glass-button',
            'platform-switch',
            'platform-help-hint',
            'chat-files-panel',
            '.resize-handle',
        ].join(',')));
    }

    _onPanelHeaderPointerDown(e) {
        if (e.button !== 0 || this._isPanelControlTarget(e.target)) {
            return;
        }
        e.preventDefault();
        this._endPanelPointerInteraction();
        const rect = this._ensureFloatingPanelRect({
            fromDefault: this._layoutExpanded,
            bringToFront: true,
        });
        this._dragState = {
            startX: e.clientX,
            startY: e.clientY,
            startRect: { ...rect },
        };
        this.setAttribute('data-dragging', '');
        window.addEventListener('pointermove', this._boundPanelPointerMove);
        window.addEventListener('pointerup', this._boundPanelPointerUp);
        window.addEventListener('pointercancel', this._boundPanelPointerUp);
    }

    _onResizePointerDown(e) {
        if (e.button !== 0) {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        this._endPanelPointerInteraction();
        const rect = this._ensureFloatingPanelRect({
            fromDefault: this._layoutExpanded,
            bringToFront: true,
        });
        if (this._collapsed) {
            this._collapsed = false;
            this._syncPanelHostAttributes();
        }
        this._resizeState = {
            startX: e.clientX,
            startY: e.clientY,
            startRect: { ...rect },
        };
        this.setAttribute('data-resizing', '');
        window.addEventListener('pointermove', this._boundPanelPointerMove);
        window.addEventListener('pointerup', this._boundPanelPointerUp);
        window.addEventListener('pointercancel', this._boundPanelPointerUp);
    }

    _onPanelPointerMove(e) {
        if (this._dragState) {
            const dx = e.clientX - this._dragState.startX;
            const dy = e.clientY - this._dragState.startY;
            this._applyFloatingPanelRect({
                ...this._dragState.startRect,
                left: this._dragState.startRect.left + dx,
                top: this._dragState.startRect.top + dy,
            });
            return;
        }
        if (this._resizeState) {
            const dx = e.clientX - this._resizeState.startX;
            const dy = e.clientY - this._resizeState.startY;
            this._applyFloatingPanelRect({
                ...this._resizeState.startRect,
                width: this._resizeState.startRect.width + dx,
                height: this._resizeState.startRect.height + dy,
            });
        }
    }

    _endPanelPointerInteraction() {
        this._dragState = null;
        this._resizeState = null;
        this.removeAttribute('data-dragging');
        this.removeAttribute('data-resizing');
        if (typeof window !== 'undefined') {
            window.removeEventListener('pointermove', this._boundPanelPointerMove);
            window.removeEventListener('pointerup', this._boundPanelPointerUp);
            window.removeEventListener('pointercancel', this._boundPanelPointerUp);
        }
    }

    _toggleCollapsed() {
        const shouldCollapse = !this._collapsed;
        const fromExpanded = this._layoutExpanded;
        const currentRect = this._ensureFloatingPanelRect({
            fromDefault: fromExpanded,
            bringToFront: true,
        });

        if (shouldCollapse) {
            this._restorePanelHeight = Math.max(currentRect.height, this._panelMinHeight(false));
            this._collapsed = true;
            this._applyFloatingPanelRect({
                ...currentRect,
                height: PANEL_COLLAPSED_HEIGHT,
            });
        } else {
            this._collapsed = false;
            this._applyFloatingPanelRect({
                ...currentRect,
                height: Math.max(this._restorePanelHeight || PANEL_DEFAULT_HEIGHT, this._panelMinHeight(false)),
            });
        }
        this._syncPanelHostAttributes();
        this.requestUpdate();
    }

    _toggleLayoutExpanded() {
        this._layoutExpanded = !this._layoutExpanded;
        if (this._layoutExpanded) {
            this._collapsed = false;
            this._syncPanelHostAttributes();
            this._clearFloatingPanelRect({ keepZIndex: true });
            this.style.zIndex = String(nextModalLayerZIndex());
            this.setAttribute('data-layout-expanded', '');
        } else {
            this._clearFloatingPanelRect();
            this.removeAttribute('data-layout-expanded');
        }
    }

    async _uploadExecutionFiles(files) {
        if (!Array.isArray(files)) {
            throw new Error('flows-execution-panel: files must be an array');
        }
        const uploaded = [];
        for (const raw of files) {
            const file = _executionFileToUploadFile(raw);
            const result = await this._upload.run({ file, public: 'false' });
            if (!result || typeof result.file_id !== 'string' || result.file_id.length === 0) {
                throw new Error('flows execution: file_upload op must return file_id');
            }
            if (typeof result.original_name !== 'string' || result.original_name.length === 0) {
                throw new Error('flows execution: file_upload op must return original_name');
            }
            if (typeof result.content_type !== 'string' || result.content_type.length === 0) {
                throw new Error('flows execution: file_upload op must return content_type');
            }
            if (typeof result.file_size !== 'number') {
                throw new Error('flows execution: file_upload op must return file_size');
            }
            if (typeof result.url !== 'string' || result.url.length === 0) {
                throw new Error('flows execution: file_upload op must return url');
            }
            uploaded.push({
                file_id: result.file_id,
                original_name: result.original_name,
                url: result.url,
                content_type: result.content_type,
                file_size: result.file_size,
            });
        }
        return uploaded;
    }

    _uploadedFileToPart(file) {
        if (!file || typeof file.original_name !== 'string' || file.original_name.length === 0) {
            throw new Error('flows execution: uploaded file original_name is required');
        }
        if (typeof file.content_type !== 'string' || file.content_type.length === 0) {
            throw new Error('flows execution: uploaded file content_type is required');
        }
        if (typeof file.url !== 'string' || file.url.length === 0) {
            throw new Error('flows execution: uploaded file url is required');
        }
        return {
            kind: 'file',
            file: {
                name: file.original_name,
                mimeType: file.content_type,
                uri: file.url,
            },
        };
    }

    async _onRun(event) {
        if (!this.flowId) return;
        const editorState = asObject(this._editor.state);
        const chatStateBefore = asObject(this._chat.state);
        if (this._send.busy || editorState.agentExecutionRunning || chatStateBefore.streaming) {
            return;
        }

        const detail = event && typeof event === 'object' && isPlainObject(event.detail)
            ? event.detail
            : null;
        if (!detail || typeof detail.message !== 'string' || !Array.isArray(detail.files)) {
            throw new Error('flows-execution-panel: chat-input send detail required');
        }
        const ui = this._ui.value;
        const text = detail.message.trim();
        const files = detail.files;
        if (text.length === 0 && files.length === 0) return;

        const hasContext = Boolean(chatStateBefore.currentContextId);
        if (!ui.persistContext || !hasContext) {
            this._chat.resetSession({});
        }
        const contextId = this._ensureContextId();

        this._editor.setAgentExecutionRunning({ running: true });
        try {
            stopStreamTtsPlayback();

            const uploadedFiles = await this._uploadExecutionFiles(files);
            const fileParts = uploadedFiles.map((file) => this._uploadedFileToPart(file));
            const userMessage = {
                id: `user_${Date.now()}`,
                role: 'user',
                content: text,
                timestamp: new Date().toISOString(),
                files: uploadedFiles,
            };
            this._chat.addUserMessage({ contextId, message: userMessage });

            const parts = text.length > 0
                ? [{ kind: 'text', text }, ...fileParts]
                : fileParts;

            const a2aMessage = {
                messageId: `${Date.now()}_${Math.random().toString(36).slice(2, 11)}`,
                role: 'user',
                parts,
                contextId,
            };

            const metadata = {};
            if (this.branchId && this.branchId !== 'base') {
                metadata.branch = this.branchId;
            }
            const preview = editorState.previewExecutionState;
            const bps = preview && preview.breakpoints;
            if (Array.isArray(bps) && bps.length > 0) {
                metadata.breakpoints = bps;
            }
            const params = { message: a2aMessage };
            if (Object.keys(metadata).length > 0) {
                params.metadata = metadata;
            }

            if (readTtsOutputEnabled() && !this._voiceOn) {
                primeStreamTtsPlaybackFromUserGesture();
                this._primeExecTtsOnlyStreamFromUserGesture();
                await this._awaitExecTtsOnlyReady();
            }

            await this._send.run({ flow_id: this.flowId, params });
        } finally {
            this._editor.setAgentExecutionRunning({ running: false });
        }
    }

    _disposeTtsOnlyStream() {
        const m = this._ttsOnlyMedia;
        this._ttsOnlyMedia = null;
        this._ttsOnlyStreamStarting = false;
        clearStreamTtsTarget();
        if (m) {
            try {
                m.close();
            } catch {
                /* noop */
            }
        }
    }

    _primeExecTtsOnlyStreamFromUserGesture() {
        if (!readTtsOutputEnabled() || this._voiceOn) {
            return;
        }
        const companyId = asString(this._activeCompanySel.value);
        if (companyId === '' || !this.flowId) {
            return;
        }
        const localeRaw = asString(this._localeSel.value);
        if (this._ttsOnlyMedia !== null && this._ttsOnlyMedia.isConnected) {
            this._ttsOnlyMedia.primePlaybackFromUserGesture();
            setStreamTtsTarget(this._ttsOnlyMedia, readTtsOutputEnabled);
            return;
        }
        if (this._ttsOnlyStreamStarting) {
            const m = this._ttsOnlyMedia;
            if (m && typeof m.primePlaybackFromUserGesture === 'function') {
                m.primePlaybackFromUserGesture();
            }
            if (m) {
                setStreamTtsTarget(m, readTtsOutputEnabled);
            }
            return;
        }
        this._disposeTtsOnlyStream();
        this._ttsOnlyStreamStarting = true;
        const voiceBaseUrl = resolveFlowVoiceHttpOrigin();
        const wsBase = voiceBaseUrl.replace(/^http/, 'ws');
        const sessionId = `tts_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;

        void (async () => {
            /** @type {InstanceType<typeof VoiceMediaSession>|null} */
            let media = null;
            try {
                const serverQuery = await fetchFlowVoiceWsQuery({
                    flowId: this.flowId,
                    branchId: this.branchId,
                });
                /** @type {Record<string, string>} */
                const wsQuery = { ...serverQuery };
                if (localeRaw.trim() !== '') {
                    try {
                        wsQuery.language = normalizeFlowVoiceSttLanguage(localeRaw);
                    } catch {
                        /* noop */
                    }
                }
                const mediaOpts = {
                    baseUrl: wsBase,
                    sessionId,
                    companyId,
                    autoRecord: false,
                };
                if (Object.keys(wsQuery).length > 0) {
                    Object.assign(mediaOpts, { query: wsQuery });
                }
                media = new VoiceMediaSession(mediaOpts);
                media.addEventListener('error', (ev) => {
                    const d = ev.detail && typeof ev.detail === 'object' ? ev.detail : {};
                    const msg =
                        typeof d.detail === 'string' && d.detail.trim() !== ''
                            ? d.detail
                            : typeof d.code === 'string'
                              ? d.code
                              : this.t('platform_chat.toast_voice_ws_hint');
                    this.toast('flows:platform_chat.toast_voice_error', {
                        type: 'error',
                        vars: { detail: msg },
                    });
                });
                media.addEventListener('closed', () => {
                    if (this._ttsOnlyMedia === media) {
                        this._ttsOnlyMedia = null;
                        clearStreamTtsTarget();
                    }
                });
                this._ttsOnlyMedia = media;
                media.primePlaybackFromUserGesture();
                setStreamTtsTarget(media, readTtsOutputEnabled);
                await media.connect();
                if (this._ttsOnlyMedia !== media) {
                    try {
                        media.close();
                    } catch {
                        /* noop */
                    }
                    return;
                }
                if (this._voiceOn || !readTtsOutputEnabled()) {
                    this._ttsOnlyMedia = null;
                    clearStreamTtsTarget();
                    try {
                        media.close();
                    } catch {
                        /* noop */
                    }
                    return;
                }
                setStreamTtsTarget(media, readTtsOutputEnabled);
            } catch (err) {
                if (this._ttsOnlyMedia === media) {
                    this._ttsOnlyMedia = null;
                }
                clearStreamTtsTarget();
                if (media !== null) {
                    try {
                        media.close();
                    } catch {
                        /* noop */
                    }
                }
                this.toast('flows:platform_chat.toast_voice_error', {
                    type: 'error',
                    vars: {
                        detail: formatFlowVoiceConnectErrorDetail(err, (key) => this.t(key)),
                    },
                });
            } finally {
                this._ttsOnlyStreamStarting = false;
            }
        })();
    }

    async _awaitExecTtsOnlyReady() {
        const t0 = Date.now();
        const maxMs = 2500;
        while (Date.now() - t0 < maxMs) {
            if (this._voiceOn || !readTtsOutputEnabled()) {
                return;
            }
            if (!this._ttsOnlyStreamStarting && this._ttsOnlyMedia !== null && this._ttsOnlyMedia.isConnected) {
                return;
            }
            await new Promise((r) => setTimeout(r, 40));
        }
    }

    _onStop() {
        if (this._cancel.busy) return;
        const chatState = this._chat.state;
        const taskId = chatState && chatState.currentTaskId;
        if (typeof taskId !== 'string' || taskId.length === 0) return;
        void this._cancel.run({ flow_id: this.flowId, task_id: taskId });
    }

    _onClose() {
        this._endPanelPointerInteraction();
        this._layoutExpanded = false;
        this._collapsed = false;
        this._syncPanelHostAttributes();
        this._clearFloatingPanelRect();
        this.removeAttribute('data-layout-expanded');
        this._editor.setExecutionPanelOpen({ open: false });
        this._editor.setMode({ mode: 'edit' });
    }

    _buildSessionId() {
        const chatState = this._chat.state;
        const ctx = chatState && chatState.currentContextId;
        if (!this.flowId || typeof ctx !== 'string' || ctx.length === 0) return '';
        return `${this.flowId}:${ctx}`;
    }

    _openState() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        this.openModal('flows.state', { sessionId });
    }

    _openTracing() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        this.openModal('flows.tracing', { sessionId });
    }

    _openLogs() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        const chatState = asObject(this._chat.state);
        const taskId = resolveFlowsChatTaskId(chatState);
        const props = { sessionId };
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        this.openModal('flows.logs', props);
    }
    /**
     * Новая сессия чата: остановка текущей задачи при необходимости и сброс контекста.
     */
    async _onResetChat() {
        if (!this.flowId) {
            return;
        }
        this._disposeTtsOnlyStream();
        const chatState = asObject(this._chat.state);
        const taskId = typeof chatState.currentTaskId === 'string' ? chatState.currentTaskId : '';
        if (Boolean(chatState.streaming) && taskId.length > 0) {
            await this._cancel.run({ flow_id: this.flowId, task_id: taskId });
        }
        this._editor.setAgentExecutionRunning({ running: false });
        this._chat.resetSession({});
        this._chatInputElement().clear();
    }

    async _startExecPanelVoice() {
        if (this._voiceOn) return;
        this._disposeTtsOnlyStream();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) return;
        const companyId = asString(this._activeCompanySel.value);
        if (companyId === '') {
            this._voiceStatus = 'no_company';
            this.toast('flows:platform_chat.toast_voice_no_company', { type: 'warning' });
            return;
        }
        this._ensureContextId();
        const initialContextId =
            this._chat.state && typeof this._chat.state.currentContextId === 'string'
                ? this._chat.state.currentContextId
                : null;
        const localeRaw = asString(this._localeSel.value);
        const sttLanguage = normalizeFlowVoiceSttLanguage(localeRaw);
        /** @type {{ contextId: string|null, taskId: string|null, taskPrimed: boolean }} */
        const voiceStreamRelayState = {
            contextId: null,
            taskId: null,
            taskPrimed: false,
        };
        const { media, bridge } = await createFlowVoiceSession({
            flowId: this.flowId,
            branchId: this.branchId,
            companyId,
            sttLanguage,
            initialContextId,
            getVoiceWsQuery: async () =>
                fetchFlowVoiceWsQuery({
                    flowId: this.flowId,
                    branchId: this.branchId,
                }),
            getHeaders: flowsVoiceAuxiliaryHttpHeadersStub,
            getContextId: () => {
                const st = this._chat.state;
                const cid =
                    st && typeof st.currentContextId === 'string' ? st.currentContextId : null;
                return cid && cid.length > 0 ? cid : null;
            },
            getStreamMetadata: async () => {
                const meta = {};
                if (this.branchId && this.branchId !== 'base') {
                    meta.branch = this.branchId;
                }
                const editorState = asObject(this._editor.state);
                const preview = editorState.previewExecutionState;
                const bps = preview && preview.breakpoints;
                if (Array.isArray(bps) && bps.length > 0) {
                    meta.breakpoints = bps;
                }
                const keysCount = Object.keys(meta).length;
                if (keysCount === 0) return {};
                return meta;
            },
            beforeA2aStream: async (text) => {
                stopStreamTtsPlayback();
                const ctx = this._ensureContextId();
                voiceStreamRelayState.contextId = ctx;
                voiceStreamRelayState.taskId = null;
                voiceStreamRelayState.taskPrimed = false;
                const trimmed = typeof text === 'string' ? text.trim() : '';
                if (trimmed.length === 0) {
                    throw new Error('flows execution voice: пустой транскрипт');
                }
                const userMessage = {
                    id: `user_${Date.now()}`,
                    role: 'user',
                    content: trimmed,
                    timestamp: new Date().toISOString(),
                    files: [],
                };
                this._chat.addUserMessage({ contextId: ctx, message: userMessage });
                this.dispatch('flows/run/flow_started', {}, { source: 'http' });
            },
            onA2aStreamEvent: (frame) => {
                relayA2aVoiceStreamRpcFrame(
                    {
                        dispatch: (t, p, m) => {
                            this.dispatch(t, p, m);
                        },
                    },
                    voiceStreamRelayState,
                    frame,
                    null,
                );
            },
            onVad: (e) => {
                this._voiceStatus = e.detail.state === 'started' ? 'listening' : 'idle';
            },
            onTtsState: (e) => {
                this._voiceStatus = e.detail.state === 'playing' ? 'speaking' : 'idle';
            },
            onMediaError: (e) => {
                this._voiceStatus = 'error';
                const d = isPlainObject(e.detail) ? e.detail : {};
                const msg =
                    typeof d.detail === 'string' && d.detail.trim() !== ''
                        ? d.detail
                        : typeof d.code === 'string'
                          ? d.code
                          : this.t('platform_chat.toast_voice_ws_hint');
                this.toast('flows:platform_chat.toast_voice_error', {
                    type: 'error',
                    vars: { detail: msg },
                });
            },
            onClosed: () => {
                this._voiceMedia = null;
                this._voiceBridge = null;
                this._voiceOn = false;
                this._voiceStatus = 'closed';
            },
        });
        try {
            await media.connect();
        } catch (err) {
            await disposeFlowVoiceSession(media, bridge);
            this._voiceStatus = 'error';
            this.toast('flows:platform_chat.toast_voice_error', {
                type: 'error',
                vars: {
                    detail: formatFlowVoiceConnectErrorDetail(err, (key) => this.t(key)),
                },
            });
            return;
        }
        const onVoiceA2aSettled = () => {
            this.dispatch('flows/run/flow_done', {}, { source: 'http' });
        };
        const onVoiceA2aAborted = (ev) => {
            const ce = /** @type {CustomEvent<Record<string, unknown>>} */ (ev);
            const d =
                ce.detail !== null && typeof ce.detail === 'object'
                    ? /** @type {Record<string, unknown>} */ (ce.detail)
                    : null;
            const task_id =
                d && typeof d.task_id === 'string' ? d.task_id : null;
            const context_id =
                d && typeof d.context_id === 'string' ? d.context_id : null;
            this.dispatch('flows/chat/a2a_interrupted', { task_id, context_id }, { source: 'local' });
        };
        this._voiceA2aSettledHandler = onVoiceA2aSettled;
        this._voiceA2aAbortedHandler = onVoiceA2aAborted;
        bridge.addEventListener('a2aSettled', onVoiceA2aSettled);
        bridge.addEventListener('a2aAborted', onVoiceA2aAborted);
        bridge.start();
        setStreamTtsTarget(media, readTtsOutputEnabled);
        this._voiceMedia = media;
        this._voiceBridge = bridge;
        this._voiceOn = true;
        this._voiceStatus = 'idle';
    }

    async _stopExecPanelVoice() {
        if (this._voiceBridge && this._voiceA2aSettledHandler) {
            this._voiceBridge.removeEventListener('a2aSettled', this._voiceA2aSettledHandler);
            this._voiceA2aSettledHandler = null;
        }
        if (this._voiceBridge && this._voiceA2aAbortedHandler) {
            this._voiceBridge.removeEventListener('a2aAborted', this._voiceA2aAbortedHandler);
            this._voiceA2aAbortedHandler = null;
        }
        await disposeFlowVoiceSession(this._voiceMedia, this._voiceBridge);
        this._voiceMedia = null;
        this._voiceBridge = null;
        this._voiceOn = false;
        this._voiceStatus = 'idle';
    }

    _toggleExecPanelVoice() {
        if (this._voiceOn) {
            void this._stopExecPanelVoice();
        } else {
            void this._startExecPanelVoice();
        }
    }

    _toggleExecTtsOutput() {
        toggleTtsOutputEnabled();
        if (!readTtsOutputEnabled()) {
            this._disposeTtsOnlyStream();
        }
        this.requestUpdate();
    }

    _setPanelTab(tab) {
        if (tab !== 'chat' && tab !== 'trace' && tab !== 'state') {
            throw new Error('flows-execution-panel: invalid tab');
        }
        this._panelTab = tab;
    }

    render() {
        const editorState = asObject(this._editor.state);
        if (!editorState.executionPanelOpen) return nothing;

        const ui = this._ui.value;
        const chatState = asObject(this._chat.state);
        const streaming = Boolean(chatState.streaming);
        const sendBusy = this._send.busy;
        const agentRun = Boolean(editorState.agentExecutionRunning);
        const runInFlight = streaming || sendBusy || agentRun;
        const hasContext = typeof chatState.currentContextId === 'string'
            && chatState.currentContextId.length > 0;
        const lastAssistant = this._activeAssistantMessage();
        const inputRequired = Boolean(lastAssistant && lastAssistant.inputRequired);
        const placeholderKey = inputRequired
            ? 'execution_panel.placeholder_answer'
            : 'execution_panel.placeholder_message';

        const runTrace = this._currentRunTrace();
        const panelMessages = this._panelChatMessages();
        const files = this._currentFiles();
        const taskId = typeof chatState.currentTaskId === 'string'
            ? chatState.currentTaskId
            : null;
        const panelStatus = deriveRunPanelStatus({
            runInFlight,
            taskId,
            activeAssistant: lastAssistant,
            runTrace,
        });
        const statusLabelKey = `execution_panel.status_${panelStatus}`;
        const tab = this._panelTab;

        return html`
            <div
                class=${this._collapsed ? 'panel is-collapsed' : 'panel'}
                role="region"
                aria-label=${this.t('execution_panel.title')}
            >
                <div class="panel-header" @pointerdown=${this._onPanelHeaderPointerDown}>
                    <div class="panel-header-main">
                        <div class="panel-title-row">
                            <div class="panel-title">
                                <platform-icon name="play" size="14"></platform-icon>
                                ${this.t('execution_panel.title')}
                            </div>
                            <span class="status-badge" data-status=${panelStatus}>${this.t(statusLabelKey)}</span>
                        </div>
                    </div>
                    <div class="panel-header-aside">
                        <chat-files-panel
                            inline
                            .files=${files}
                            active-company-id=${asString(this._activeCompanySel.value)}
                            @files-updated=${this._onFilesPanelUpdated}
                        ></chat-files-panel>
                        <div class="persist-wrap">
                            <platform-switch
                                size="sm"
                                ?checked=${ui.persistContext}
                                @change=${this._onPersistChange}
                                aria-label=${this.t('execution_panel.persist_aria')}
                            ></platform-switch>
                            <platform-help-hint
                                label=${this.t('execution_panel.help_hint_label')}
                                text=${this.t('execution_panel.persist_context_help')}
                            ></platform-help-hint>
                        </div>
                        <button
                            class="icon-btn-close"
                            type="button"
                            title=${this._collapsed
                                ? this.t('execution_panel.restore_panel')
                                : this.t('execution_panel.minimize_panel')}
                            aria-expanded=${this._collapsed ? 'false' : 'true'}
                            @click=${this._toggleCollapsed}
                        >
                            <platform-icon
                                name=${this._collapsed ? 'fullscreen' : 'minus'}
                                size="14"
                            ></platform-icon>
                        </button>
                        <button
                            class="icon-btn-close"
                            type="button"
                            title=${this._layoutExpanded
                                ? this.t('execution_panel.collapse_panel')
                                : this.t('execution_panel.expand_panel')}
                            aria-expanded=${this._layoutExpanded ? 'true' : 'false'}
                            @click=${this._toggleLayoutExpanded}
                        >
                            <platform-icon
                                name=${this._layoutExpanded ? 'minimize' : 'fullscreen'}
                                size="14"
                            ></platform-icon>
                        </button>
                        <button
                            class="icon-btn-close"
                            type="button"
                            title=${this.t('execution_panel.close_panel')}
                            @click=${this._onClose}
                        >
                            <platform-icon name="close" size="14"></platform-icon>
                        </button>
                    </div>
                </div>

                ${this._collapsed ? nothing : html`
                <div class="tabs" role="tablist">
                    <button
                        type="button"
                        class="tab"
                        role="tab"
                        ?data-active=${tab === 'chat'}
                        aria-selected=${tab === 'chat' ? 'true' : 'false'}
                        @click=${() => { this._setPanelTab('chat'); }}
                    >${this.t('execution_panel.tab_chat')}</button>
                    <button
                        type="button"
                        class="tab"
                        role="tab"
                        ?data-active=${tab === 'trace'}
                        aria-selected=${tab === 'trace' ? 'true' : 'false'}
                        @click=${() => { this._setPanelTab('trace'); }}
                    >${this.t('execution_panel.tab_trace')}</button>
                    <button
                        type="button"
                        class="tab"
                        role="tab"
                        ?data-active=${tab === 'state'}
                        aria-selected=${tab === 'state' ? 'true' : 'false'}
                        @click=${() => { this._setPanelTab('state'); }}
                    >${this.t('execution_panel.tab_state')}</button>
                </div>

                ${tab === 'chat' || tab === 'trace'
                    ? html`
                        <div class="tab-toolbar">
                            ${tab === 'trace' ? html`
                                <glass-button
                                    variant="primary"
                                    size="sm"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.full_trace_title')}
                                    @click=${this._openTracing}
                                >${this.t('execution_panel.full_trace')}</glass-button>
                                <glass-button
                                    variant="secondary"
                                    size="sm"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.open_logs_title')}
                                    @click=${this._openLogs}
                                >${this.t('execution_panel.open_logs')}</glass-button>
                            ` : nothing}
                            ${tab === 'chat' ? html`
                                <glass-button
                                    variant="secondary"
                                    size="sm"
                                    title=${this.t('execution_panel.reset_chat_title')}
                                    @click=${() => { void this._onResetChat(); }}
                                >${this.t('execution_panel.reset_chat')}</glass-button>
                            ` : nothing}
                        </div>
                    `
                    : nothing}

                <div class="panel-body">
                    <div class="tab-panel" data-tab=${tab}>
                        ${tab === 'chat' ? html`
                            ${panelMessages.length > 0 ? html`
                                <div class="message-feed">
                                    ${repeat(
                                        panelMessages,
                                        (m, i) => {
                                            if (m && typeof m.id === 'string' && m.id.length > 0) {
                                                return m.id;
                                            }
                                            const role = m && typeof m.role === 'string' ? m.role : 'msg';
                                            const tid = m && typeof m.taskId === 'string' ? m.taskId : '';
                                            return `${role}_${tid}_${i}`;
                                        },
                                        (message) => html`
                                            <chat-message
                                                .role=${asString(message.role)}
                                                .content=${typeof message.content === 'string' ? message.content : ''}
                                                .timestamp=${asString(message.timestamp)}
                                                ?streaming=${Boolean(message.streaming)}
                                                .reasoning=${asString(message.reasoning)}
                                                .activity=${asString(message.activity)}
                                                .toolCalls=${asArray(message.toolCalls)}
                                                .toolResults=${asArray(message.toolResults)}
                                                .inputRequired=${message.inputRequired != null ? message.inputRequired : null}
                                                .operatorReply=${asString(message.operatorReply)}
                                                .breakpoint=${message.breakpoint != null ? message.breakpoint : null}
                                                .files=${asArray(message.files)}
                                                .fileIds=${asArray(message.fileIds)}
                                                .taskId=${asString(message.taskId)}
                                                .error=${asString(message.error)}
                                                .errorI18nKey=${message.errorI18nKey != null && typeof message.errorI18nKey === 'string'
                                                    ? message.errorI18nKey
                                                    : null}
                                                .voicePlayGetHeaders=${flowsVoiceAuxiliaryHttpHeadersStub}
                                            ></chat-message>
                                        `,
                                    )}
                                </div>
                            ` : nothing}
                            <chat-input
                                class="execution-chat-input"
                                .placeholder=${this.t(placeholderKey)}
                                .streaming=${runInFlight}
                                .disabled=${sendBusy}
                                .cancelBusy=${this._cancel.busy}
                                .showVoice=${typeof this.flowId === 'string' && this.flowId.length > 0}
                                .voiceActive=${this._voiceOn}
                                .voiceStatus=${this._voiceStatus}
                                .ttsOutputEnabled=${readTtsOutputEnabled()}
                                .accept=${ACCEPT_FILE_TYPES}
                                @send=${this._onRun}
                                @stop=${this._onStop}
                                @voice-toggle=${this._toggleExecPanelVoice}
                                @tts-output-toggle=${this._toggleExecTtsOutput}
                            ></chat-input>
                        ` : nothing}

                        ${tab === 'trace' ? html`
                            <div class="trace-panel-inner">
                                <flows-chat-run-trace
                                    .entries=${runTrace}
                                    compact
                                    .showSectionHeader=${false}
                                    .fillAvailable=${true}
                                ></flows-chat-run-trace>
                            </div>
                        ` : nothing}

                        ${tab === 'state' ? html`
                            <div class="state-tab">
                                <p class="state-tab-hint">${this.t('execution_panel.state_tab_hint')}</p>
                                <glass-button
                                    variant="secondary"
                                    size="sm"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.state_title')}
                                    @click=${this._openState}
                                >${this.t('execution_panel.open_state')}</glass-button>
                            </div>
                        ` : nothing}
                    </div>
                </div>
                `}
                ${this._collapsed ? nothing : html`
                    <button
                        class="resize-handle"
                        type="button"
                        title=${this.t('execution_panel.resize_panel')}
                        aria-label=${this.t('execution_panel.resize_panel')}
                        @pointerdown=${this._onResizePointerDown}
                    ></button>
                `}
            </div>
        `;
    }
}

customElements.define('flows-execution-panel', FlowsExecutionPanel);

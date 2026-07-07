/**
 * flows-execution-panel — плавающая панель «Запуск агента» в редакторе.
 *
 * Тонкий хост единого чат-компонента: вкладка Chat — это
 * `<platform-chat display="panel" profile="editor_test">` (весь чат, файлы,
 * voice/TTS и SSE A2A живут внутри компонента; в editor_test виден весь runtime
 * независимо от политики flow). Панель добавляет только editor-специфику:
 *   - useOp('flows/editor') — режим, currentBranchId, previewExecutionState.breakpoints;
 *   - useSlice('flows/execution_ui') — persistContext (→ fresh-context-per-turn);
 *   - breakpoints уходят metadata через `.getSendMetadata`;
 *   - события `chat-run-event` (flows/run/*) диспатчатся в bus — канвас
 *     подсвечивает ноды, agentExecutionRunning синхронизируется.
 *
 * Панель скрывается display:none (не unmount) — история чата живёт, пока открыт
 * редактор; голосовой дуплекс при скрытии останавливается.
 * Разворот — кнопка в шапке: `position: fixed` + `nextModalLayerZIndex()`, иначе z-index
 * не выходит из `canvas-host` и панель свойств (`flows-floating-panel`, до 25100) перекрывает.
 * Снизу — `--flows-exec-fab-gutter`, чтобы поле ввода не заезжало на FAB чат-виджета.
 * Кнопки State / Tracing открывают модалки `flows.state`, `flows.tracing`.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/chat/platform-chat.js';
import { resolveVoiceHttpOrigin } from '@platform/lib/voice/voice-http-origin.js';
import '@platform/lib/chat/chat-run-trace.js';
import {
    asObject,
    asString,
    authActiveCompanyId,
    deriveRunPanelStatus,
    isPlainObject,
} from '../../_helpers/flows-resolvers.js';
import { resolveFlowsChatTaskId } from '../../_helpers/resolve-flows-chat-task-id.js';

const EMPTY_TRACE = Object.freeze([]);
const PANEL_VIEWPORT_MARGIN = 12;
const PANEL_MIN_WIDTH = 360;
const PANEL_MIN_HEIGHT = 320;
const PANEL_DEFAULT_HEIGHT = 620;
const PANEL_COLLAPSED_HEIGHT = 64;

export class FlowsExecutionPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        flowId: { type: String },
        branchId: { type: String },
        _panelTab: { type: String, state: true },
        _layoutExpanded: { type: Boolean, state: true },
        _collapsed: { type: Boolean, state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                /* Зазор под FAB чат-виджета (56px + bottom 16px + запас), см. platform-chat display="drawer" .fab */
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
            :host([data-panel-closed]) {
                display: none;
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
                border-color: var(--warning-border);
                background: var(--warning-bg);
                color: var(--warning);
                animation: execPanelPulse 1.4s ease-in-out infinite;
            }
            .status-badge[data-status='passed'] {
                border-color: var(--success-border);
                background: var(--success-bg);
                color: var(--success);
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
            .panel-tabs {
                flex-shrink: 0;
            }
            .panel-tabs platform-segmented-control {
                width: 100%;
            }
            .tab-toolbar {
                flex-shrink: 0;
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                justify-content: flex-end;
            }
            .panel-header-actions {
                flex-shrink: 0;
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                align-items: center;
                justify-content: flex-end;
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
            .tab-panel[hidden] {
                display: none;
            }
            .tab-panel platform-chat {
                flex: 1;
                min-height: 0;
            }
            .trace-panel-inner {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            .trace-panel-inner chat-run-trace {
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
        this._ui = this.useSlice('flows/execution_ui');
        this._layoutExpanded = false;
        this._collapsed = false;
        this._panelRect = null;
        this._dragState = null;
        this._resizeState = null;
        this._restorePanelHeight = 0;
        this._boundPanelPointerMove = (e) => this._onPanelPointerMove(e);
        this._boundPanelPointerUp = () => this._endPanelPointerInteraction();
        this._boundPanelViewportResize = () => this._clampFloatingPanelToViewport();
        this._activeCompanySel = this.select((s) => authActiveCompanyId(s));
        this._localeSel = this.select((s) => s.i18n.locale);
        this._voiceBaseUrl =
            typeof window !== 'undefined' && typeof window.location !== 'undefined'
                ? resolveVoiceHttpOrigin()
                : '';
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined') {
            window.addEventListener('resize', this._boundPanelViewportResize);
        }
    }

    disconnectedCallback() {
        this._endPanelPointerInteraction();
        if (typeof window !== 'undefined') {
            window.removeEventListener('resize', this._boundPanelViewportResize);
        }
        super.disconnectedCallback();
    }

    /** @returns {import('@platform/lib/chat/platform-chat.js').PlatformChat|null} */
    _platformChat() {
        const el = this.renderRoot?.querySelector('platform-chat');
        return el || null;
    }

    _chatRuntimeState() {
        const chat = this._platformChat();
        return chat ? asObject(chat.runtimeState) : {};
    }

    updated(changedProperties) {
        const editorState = asObject(this._editor.state);
        const isOpen = Boolean(editorState.executionPanelOpen);
        if (isOpen) {
            this.removeAttribute('data-panel-closed');
        } else {
            this.setAttribute('data-panel-closed', '');
            const chat = this._platformChat();
            if (chat) {
                void chat.stopVoice();
            }
        }
        super.updated(changedProperties);
    }

    _onChatRunEvent(e) {
        const detail = isPlainObject(e.detail) ? e.detail : null;
        if (!detail || typeof detail.type !== 'string') {
            return;
        }
        const payload = isPlainObject(detail.payload) ? detail.payload : {};
        this.dispatch(detail.type, payload, { source: 'http' });
        if (detail.type === 'flows/run/flow_started') {
            this._editor.setAgentExecutionRunning({ running: true });
        }
        if (detail.type === 'flows/run/flow_done') {
            this._editor.setAgentExecutionRunning({ running: false });
        }
    }

    _onChatShowTracing(e) {
        this._openTracingModalFromDetail(e.detail);
    }

    _onChatShowLogs(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const sessionId = asString(detail.sessionId);
        if (sessionId.length === 0) {
            return;
        }
        const props = { sessionId };
        const taskId = asString(detail.taskId);
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        this.openModal('flows.logs', props);
    }

    _onChatShowDurableHistory(e) {
        const detail = isPlainObject(e.detail) ? e.detail : {};
        const sessionId = asString(detail.sessionId);
        if (sessionId.length === 0) {
            return;
        }
        this.openModal('flows.durable_history', { sessionId });
    }

    /** Вместо window.open (default поведение bubble) — платформенная модалка предпросмотра браузера. */
    _onBrowserPreviewOpen(e) {
        e.preventDefault();
        const detail = isPlainObject(e.detail) ? e.detail : {};
        this.openModal('flows.browser_preview', {
            viewerUrl: asString(detail.viewerUrl),
            sessionId: asString(detail.sessionId),
            currentUrl: asString(detail.currentUrl),
            status: asString(detail.status),
        });
    }

    /** metadata верхнего уровня A2A message/stream: breakpoints превью редактора. */
    _sendMetadataForRun() {
        const editorState = asObject(this._editor.state);
        const preview = editorState.previewExecutionState;
        const bps = preview && preview.breakpoints;
        if (Array.isArray(bps) && bps.length > 0) {
            return { breakpoints: bps };
        }
        return {};
    }

    _panelChatMessages() {
        const chatState = this._chatRuntimeState();
        const ctx = typeof chatState.currentContextId === 'string' ? chatState.currentContextId : null;
        if (!ctx || !isPlainObject(chatState.messagesByContextId)) {
            return [];
        }
        const bucket = chatState.messagesByContextId[ctx];
        if (!bucket || !Array.isArray(bucket.messages)) {
            return [];
        }
        return bucket.messages;
    }

    _lastAssistantMessage() {
        const messages = this._panelChatMessages();
        for (let i = messages.length - 1; i >= 0; i--) {
            const m = messages[i];
            if (m && m.role === 'assistant') return m;
        }
        return null;
    }

    /** Ассистент текущего task_id (чтобы не показывать ответ прошлого запуска до первого чанка). */
    _activeAssistantMessage() {
        const chatState = this._chatRuntimeState();
        const tid = typeof chatState.currentTaskId === 'string' ? chatState.currentTaskId : null;
        const messages = this._panelChatMessages();
        if (tid) {
            for (let i = messages.length - 1; i >= 0; i -= 1) {
                const m = messages[i];
                if (m && m.role === 'assistant' && m.taskId === tid) {
                    return m;
                }
            }
        }
        return this._lastAssistantMessage();
    }

    _currentRunTrace() {
        const chatState = this._chatRuntimeState();
        const ctx = typeof chatState.currentContextId === 'string' ? chatState.currentContextId : null;
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
            'a',
            'input',
            'textarea',
            'select',
            'platform-button',
            'platform-switch',
            'platform-help-hint',
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
        const chatState = this._chatRuntimeState();
        const ctx = chatState.currentContextId;
        if (!this.flowId || typeof ctx !== 'string' || ctx.length === 0) return '';
        return `${this.flowId}:${ctx}`;
    }

    _openState() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        this.openModal('flows.state', { sessionId });
    }

    _openTracing() {
        this._openTracingModalFromDetail(null);
    }

    _openTracingModalFromDetail(detail) {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        const props = { sessionId };
        const taskId =
            detail && typeof detail === 'object' && typeof detail.taskId === 'string' && detail.taskId.length > 0
                ? detail.taskId
                : '';
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        const traceId =
            detail && typeof detail === 'object' && typeof detail.traceId === 'string' && detail.traceId.length > 0
                ? detail.traceId
                : '';
        if (traceId.length > 0) {
            props.traceId = traceId;
        }
        this.openModal('flows.tracing', props);
    }

    _openLogs() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        const taskId = resolveFlowsChatTaskId(this._chatRuntimeState());
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
        const chat = this._platformChat();
        if (!chat) {
            return;
        }
        const chatState = asObject(chat.runtimeState);
        if (Boolean(chatState.streaming)) {
            await chat.cancelActiveTask();
        }
        this._editor.setAgentExecutionRunning({ running: false });
        chat.startNewChat();
    }

    _setPanelTab(tab) {
        if (tab !== 'chat' && tab !== 'trace' && tab !== 'state') {
            throw new Error('flows-execution-panel: invalid tab');
        }
        this._panelTab = tab;
    }

    render() {
        const editorState = asObject(this._editor.state);
        const ui = this._ui.value;
        const chatState = this._chatRuntimeState();
        const streaming = Boolean(chatState.streaming);
        const agentRun = Boolean(editorState.agentExecutionRunning);
        const runInFlight = streaming || agentRun;
        const hasContext = typeof chatState.currentContextId === 'string'
            && chatState.currentContextId.length > 0;
        const lastAssistant = this._activeAssistantMessage();
        const inputRequired = Boolean(lastAssistant && lastAssistant.inputRequired);
        const placeholderKey = inputRequired
            ? 'execution_panel.placeholder_answer'
            : 'execution_panel.placeholder_message';

        const runTrace = this._currentRunTrace();
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
        const companyId = asString(this._activeCompanySel.value);
        const locale = asString(this._localeSel.value);
        const voiceReady =
            typeof this.flowId === 'string' && this.flowId.length > 0
            && companyId !== ''
            && this._voiceBaseUrl !== '';

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
                        <div class="panel-header-actions">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this._collapsed
                                ? this.t('execution_panel.restore_panel')
                                : this.t('execution_panel.minimize_panel')}
                            @click=${this._toggleCollapsed}
                        >
                            <platform-icon
                                name=${this._collapsed ? 'fullscreen' : 'minus'}
                                size="14"
                            ></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this._layoutExpanded
                                ? this.t('execution_panel.collapse_panel')
                                : this.t('execution_panel.expand_panel')}
                            @click=${this._toggleLayoutExpanded}
                        >
                            <platform-icon
                                name=${this._layoutExpanded ? 'minimize' : 'fullscreen'}
                                size="14"
                            ></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('execution_panel.close_panel')}
                            @click=${this._onClose}
                        >
                            <platform-icon name="close" size="14"></platform-icon>
                        </platform-button>
                        </div>
                    </div>
                </div>

                ${this._collapsed ? nothing : html`
                <div class="panel-tabs">
                    <platform-segmented-control
                        full-width
                        density="compact"
                        .value=${tab}
                        .items=${[
                            { value: 'chat', label: this.t('execution_panel.tab_chat') },
                            { value: 'trace', label: this.t('execution_panel.tab_trace') },
                            { value: 'state', label: this.t('execution_panel.tab_state') },
                        ]}
                        aria-label=${this.t('execution_panel.tabs_aria')}
                        @change=${(e) => { this._setPanelTab(e.detail.value); }}
                    ></platform-segmented-control>
                </div>

                ${tab === 'chat' || tab === 'trace'
                    ? html`
                        <div class="tab-toolbar">
                            ${tab === 'trace' ? html`
                                <platform-button
                                    variant="primary"
                                    density="compact"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.full_trace_title')}
                                    @click=${this._openTracing}
                                >${this.t('execution_panel.full_trace')}</platform-button>
                                <platform-button
                                    variant="secondary"
                                    density="compact"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.open_logs_title')}
                                    @click=${this._openLogs}
                                >${this.t('execution_panel.open_logs')}</platform-button>
                            ` : nothing}
                            ${tab === 'chat' ? html`
                                <platform-button
                                    variant="secondary"
                                    density="compact"
                                    title=${this.t('execution_panel.reset_chat_title')}
                                    @click=${() => { void this._onResetChat(); }}
                                >${this.t('execution_panel.reset_chat')}</platform-button>
                            ` : nothing}
                        </div>
                    `
                    : nothing}

                <div class="panel-body">
                    <div class="tab-panel" data-tab="chat" ?hidden=${tab !== 'chat'}>
                        <platform-chat
                            display="panel"
                            profile="editor_test"
                            hide-header
                            flow-id=${this.flowId}
                            branch-id=${this.branchId}
                            .flowsBaseUrl=${'/flows'}
                            ?use-credentials=${true}
                            company-id=${companyId}
                            ?voice-enabled=${voiceReady}
                            voice-base-url=${this._voiceBaseUrl}
                            interface-locale=${locale || 'auto'}
                            ?fresh-context-per-turn=${!ui.persistContext}
                            .getSendMetadata=${() => this._sendMetadataForRun()}
                            .labels=${{ placeholder: this.t(placeholderKey) }}
                            @chat-state-changed=${() => this.requestUpdate()}
                            @chat-run-event=${this._onChatRunEvent}
                            @show-tracing=${this._onChatShowTracing}
                            @show-logs=${this._onChatShowLogs}
                            @show-durable-history=${this._onChatShowDurableHistory}
                            @browser-preview-open=${this._onBrowserPreviewOpen}
                        ></platform-chat>
                    </div>

                    ${tab === 'trace' ? html`
                        <div class="tab-panel" data-tab="trace">
                            <div class="trace-panel-inner">
                                <chat-run-trace
                                    .entries=${runTrace}
                                    compact
                                    .showSectionHeader=${false}
                                    .fillAvailable=${true}
                                ></chat-run-trace>
                            </div>
                        </div>
                    ` : nothing}

                    ${tab === 'state' ? html`
                        <div class="tab-panel" data-tab="state">
                            <div class="state-tab">
                                <p class="state-tab-hint">${this.t('execution_panel.state_tab_hint')}</p>
                                <platform-button
                                    variant="secondary"
                                    density="compact"
                                    ?disabled=${!hasContext}
                                    title=${this.t('execution_panel.state_title')}
                                    @click=${this._openState}
                                >${this.t('execution_panel.open_state')}</platform-button>
                            </div>
                        </div>
                    ` : nothing}
                </div>
                `}
                ${this._collapsed ? nothing : html`
                    <div
                        class="resize-handle"
                        role="separator"
                        aria-orientation="vertical"
                        tabindex="0"
                        title=${this.t('execution_panel.resize_panel')}
                        aria-label=${this.t('execution_panel.resize_panel')}
                        @pointerdown=${this._onResizePointerDown}
                    ></div>
                `}
            </div>
        `;
    }
}

customElements.define('flows-execution-panel', FlowsExecutionPanel);

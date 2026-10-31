/**
 * flows-execution-panel — плавающая панель «Запуск агента» в редакторе.
 *
 * Тонкий хост единого чат-компонента: вкладка Chat — это
 * `<platform-flow-ui display="panel" profile="editor_test">` (весь чат, файлы,
 * voice/TTS и SSE A2A живут внутри компонента; в editor_test виден весь runtime
 * независимо от политики flow). Панель добавляет только editor-специфику:
 *   - useOp('flows/editor') — режим, currentBranchId, breakpointNodeIds;
 *   - useSlice('flows/execution_ui') — persistContext (→ fresh-context-per-turn);
 *   - `flow-ui-submit-start` / `flow-ui-a2a-frame` / `flow-ui-submit-end` → bus
 *     `flows/run/*` — канвас читает только editor slice.
 *
 * `<platform-flow-ui>` не размонтируется при collapse: скрывается через `hidden`,
 * SSE продолжает приходить в slice.
 * Панель скрывается display:none (не unmount) — история чата живёт, пока открыт
 * редактор; голосовой дуплекс при скрытии останавливается.
 * Разворот — кнопка в шапке: `position: fixed` + `nextModalLayerZIndex()`, иначе z-index
 * не выходит из `canvas-host` и панель свойств (`flows-floating-panel`, до 25100) перекрывает.
 * Снизу — `--flows-exec-fab-gutter`, чтобы поле ввода не заезжало на FAB чат-виджета.
 * Кнопки State / Tracing открывают модалки `flows.state`, `flows.tracing`.
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, SliceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-button.js';
import { PlatformFlowUI } from '@platform/lib/flow-ui/components/platform-flow-ui.js';
import '@platform/lib/flow-ui/components/flow-ui-run-trace.js';
import {
    asString,
    deriveRunPanelStatus,
    isPlainObject,
} from '../../_helpers/flows-resolvers.js';
import { mapEditorA2aFrame } from '../../_helpers/flows-editor-a2a-run.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const PANEL_VIEWPORT_MARGIN = 12;
const PANEL_MIN_WIDTH = 360;
const PANEL_MIN_HEIGHT = 320;
const PANEL_DEFAULT_HEIGHT = 620;
const PANEL_COLLAPSED_HEIGHT = 64;

interface PanelRect {
    left: number;
    top: number;
    width: number;
    height: number;
}

interface PanelPointerState {
    startX: number;
    startY: number;
    startRect: PanelRect;
}

export class FlowsExecutionPanel extends PlatformElement {
    private _boundPanelPointerMove: (event: MouseEvent) => void;
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        flowId: { type: String },
        branchId: { type: String },
        _panelTab: { type: String, state: true },
        _layoutExpanded: { type: Boolean, state: true },
        _collapsed: { type: Boolean, state: true },
    }
    declare flowId: string;
    declare branchId: string;
    declare _panelTab: string;
    declare _layoutExpanded: boolean;
    declare _collapsed: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                /* Зазор под FAB чат-виджета (56px + bottom 16px + запас), см. flow-ui-drawer launcher */
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
            .tab-panel platform-flow-ui {
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
            .trace-panel-inner flow-ui-run-trace {
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
    private _editor: ControllerFor<'flows/editor'>;
    private _ui: ControllerFor<'flows/execution_ui'>;
    private _localeSel: SelectController<string>;
    private _panelRect: PanelRect | null;
    private _dragState: PanelPointerState | null;
    private _resizeState: PanelPointerState | null;
    private _restorePanelHeight: number;
    private _boundPanelPointerUp: () => void;
    private _panelPointerUnsubs: Array<() => void> = [];
    private _boundPanelViewportResize: () => void;

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
        this._boundPanelPointerMove = (e: MouseEvent) => this._onPanelPointerMove(e);
        this._boundPanelPointerUp = () => this._endPanelPointerInteraction();
        this._boundPanelViewportResize = () => this._clampFloatingPanelToViewport();
        this._localeSel = this.select((state) => {
            const loc = state.i18n.locale.trim();
            if (loc.length === 0) {
                throw new Error('flows-execution-panel: locale required');
            }
            return loc;
        });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useDomEvent(window, 'resize', this._boundPanelViewportResize);
    }

    override disconnectedCallback(): void {
        this._endPanelPointerInteraction();
        super.disconnectedCallback();
    }

    _platformChat(): PlatformFlowUI {
        const el = this.renderRoot?.querySelector('platform-flow-ui');
        if (!(el instanceof PlatformFlowUI)) {
            throw new Error('flows-execution-panel: platform-flow-ui host required');
        }
        return el;
    }

    _runSession(): Record<string, unknown> {
        const session = this._editor.state.runSession;
        if (!isPlainObject(session)) {
            throw new Error('flows-execution-panel: editor runSession required');
        }
        return session;
    }

    _requireRunTrace(): unknown[] {
        const runTrace = this._editor.state.runTrace;
        if (!Array.isArray(runTrace)) {
            throw new Error('flows-execution-panel: editor runTrace array required');
        }
        return runTrace;
    }

    override updated(changedProperties: PropertyValues): void {
        const isOpen = this._editor.state.executionPanelOpen === true;
        if (isOpen) {
            this.removeAttribute('data-panel-closed');
        } else {
            this.setAttribute('data-panel-closed', '');
            void this._platformChat().stopVoice();
        }
        super.updated(changedProperties);
    }

    _onFlowUiSubmitStart(e: CustomEvent) {
        const detail = isPlainObject(e.detail) ? e.detail : null;
        if (!detail || typeof detail.contextId !== 'string' || detail.contextId.length === 0) {
            throw new Error('flows-execution-panel: flow-ui-submit-start contextId required');
        }
        this.dispatch('flows/run/flow_started', { context_id: detail.contextId }, { source: 'http' });
    }

    _onFlowUiA2aFrame(e: CustomEvent) {
        const detail = isPlainObject(e.detail) ? e.detail : null;
        if (!detail) {
            throw new Error('flows-execution-panel: flow-ui-a2a-frame detail required');
        }
        if (typeof detail.contextId !== 'string' || detail.contextId.length === 0) {
            throw new Error('flows-execution-panel: flow-ui-a2a-frame contextId required');
        }
        const contextId = detail.contextId;
        const session = this._runSession();
        if (typeof session.contextId === 'string' && session.contextId.length > 0 && session.contextId !== contextId) {
            throw new Error('flows-execution-panel: a2a frame contextId does not match runSession');
        }
        const runTrace = this._requireRunTrace();
        const mapped = mapEditorA2aFrame(detail.frame, {
            contextId,
            currentTaskId: session.taskId,
            taskPrimed: session.taskPrimed === true,
            traceIndexBase: runTrace.length,
        });
        this.dispatch('flows/run/a2a_mapped', {
            context_id: contextId,
            runEvents: mapped.runEvents,
            traceEntries: mapped.traceEntries,
            terminal: mapped.terminal,
            nextTaskId: mapped.nextTaskId,
            taskPrimed: mapped.taskPrimed,
        }, { source: 'http' });
    }

    _onFlowUiSubmitEnd(e: CustomEvent) {
        const detail = isPlainObject(e.detail) ? e.detail : null;
        if (!detail) {
            throw new Error('flows-execution-panel: flow-ui-submit-end detail required');
        }
        if (typeof detail.contextId !== 'string' || detail.contextId.length === 0) {
            throw new Error('flows-execution-panel: flow-ui-submit-end contextId required');
        }
        if (this._editor.state.agentExecutionRunning !== true) {
            return;
        }
        const payload: Record<string, unknown> = { context_id: detail.contextId };
        if (typeof detail.taskId === 'string' && detail.taskId.length > 0) {
            payload.task_id = detail.taskId;
        }
        this.dispatch('flows/run/flow_done', payload, { source: 'http' });
    }

    /** Вместо window.open (default поведение bubble) — платформенная модалка предпросмотра браузера. */
    _onBrowserPreviewOpen(e: CustomEvent) {
        e.preventDefault();
        const detail = isPlainObject(e.detail) ? e.detail : {};
        this.openModal('flows.browser_preview', {
            viewerUrl: asString(detail.viewerUrl),
            sessionId: asString(detail.sessionId),
            currentUrl: asString(detail.currentUrl),
            status: asString(detail.status),
        });
    }

    _onPersistChange(e: CustomEvent) {
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

    _clampPanelRect(rect: PanelRect, collapsed = this._collapsed): PanelRect {
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

    _applyFloatingPanelRect(rect: PanelRect, { bringToFront = false } = {}): PanelRect {
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
        return clamped;
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
        const applied = this._panelRect;
        if (applied === null) {
            throw new Error('flows-execution-panel: panel rect required');
        }
        return applied;
    }

    _clampFloatingPanelToViewport() {
        if (!this._panelRect || this._layoutExpanded) {
            return;
        }
        this._applyFloatingPanelRect(this._panelRect);
    }

    _isPanelControlTarget(target: EventTarget | null) {
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

    _onPanelHeaderPointerDown(e: MouseEvent) {
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
        this._listenPanelPointer();
    }

    private _listenPanelPointer() {
        this._panelPointerUnsubs = [
            this.useDomEvent(window, 'pointermove', this._boundPanelPointerMove),
            this.useDomEvent(window, 'pointerup', this._boundPanelPointerUp),
            this.useDomEvent(window, 'pointercancel', this._boundPanelPointerUp),
        ];
    }

    _onResizePointerDown(e: MouseEvent) {
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
        this._listenPanelPointer();
    }

    _onPanelPointerMove(e: MouseEvent) {
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
            for (const unsub of this._panelPointerUnsubs) {
                unsub();
            }
            this._panelPointerUnsubs = [];
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

    _toggleCanvasRunResults() {
        const next = this._editor.state.showCanvasRunResults !== true;
        this._editor.toggleCanvasRunResults({ value: next });
    }

    _onClose() {
        this._endPanelPointerInteraction();
        this._layoutExpanded = false;
        this._collapsed = false;
        this._syncPanelHostAttributes();
        this._clearFloatingPanelRect();
        this.removeAttribute('data-layout-expanded');
        this._editor.setExecutionPanelOpen({ open: false });
    }

    _buildSessionId() {
        const session = this._runSession();
        const ctx = session.contextId;
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return '';
        }
        if (typeof ctx !== 'string' || ctx.length === 0) {
            return '';
        }
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

    _openTracingModalFromDetail(detail: unknown) {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        const record = isPlainObject(detail) ? detail : null;
        const props: Record<string, unknown> = { sessionId };
        const taskId = record !== null && typeof record.taskId === 'string' && record.taskId.length > 0
            ? record.taskId
            : '';
        if (taskId.length > 0) {
            props.taskId = taskId;
        }
        const traceId = record !== null && typeof record.traceId === 'string' && record.traceId.length > 0
            ? record.traceId
            : '';
        if (traceId.length > 0) {
            props.traceId = traceId;
        }
        this.openModal('flows.tracing', props);
    }

    _openLogs() {
        const sessionId = this._buildSessionId();
        if (!sessionId) return;
        const session = this._runSession();
        const props: Record<string, unknown> = { sessionId };
        if (typeof session.taskId === 'string' && session.taskId.length > 0) {
            props.taskId = session.taskId;
        }
        this.openModal('flows.logs', props);
    }

    /**
     * Новая сессия чата: остановка текущей задачи при необходимости и сброс контекста.
     */
    async _onResetChat() {
        const host = this._platformChat();
        if (host.store.taskRunning) {
            await host.cancelActiveTask();
        }
        this.dispatch('flows/run/session_cleared', {}, { source: 'http' });
        host.startNewContext();
    }

    _setPanelTab(tab: unknown) {
        if (tab !== 'chat' && tab !== 'trace' && tab !== 'state') {
            throw new Error('flows-execution-panel: invalid tab');
        }
        this._panelTab = tab;
    }

    override render(): TemplateResult {
        const ui = this._ui.value;
        const showCanvasRunResults = this._editor.state.showCanvasRunResults === true;
        const session = this._runSession();
        const runInFlight = this._editor.state.agentExecutionRunning === true;
        const hasContext = typeof session.contextId === 'string' && session.contextId.length > 0;
        const runTrace = this._requireRunTrace();
        const taskId = typeof session.taskId === 'string' && session.taskId.length > 0
            ? session.taskId
            : null;
        const panelStatus = deriveRunPanelStatus({
            runInFlight,
            taskId,
            activeAssistant: null,
            runTrace,
        });
        const statusLabelKey = `execution_panel.status_${panelStatus}`;
        const tab = this._panelTab;
        const locale = asString(this._localeSel.value);

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
                                ?checked=${ui?.persistContext}
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
                            aria-label=${this.t('execution_panel.toggle_canvas_results_aria')}
                            title=${this.t('execution_panel.toggle_canvas_results_aria')}
                            aria-pressed=${showCanvasRunResults ? 'true' : 'false'}
                            @click=${this._toggleCanvasRunResults}
                        >
                            <platform-icon name="workflow" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('execution_panel.reset_chat_title')}
                            title=${this.t('execution_panel.reset_chat_title')}
                            @click=${() => { void this._onResetChat(); }}
                        >
                            <platform-icon name="rotate-ccw" size="14"></platform-icon>
                        </platform-button>
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
                                name=${this._collapsed ? 'fullscreen' : 'minimize'}
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

                <div class="panel-tabs" ?hidden=${this._collapsed}>
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
                        @change=${(e: CustomEvent) => { this._setPanelTab(e.detail.value); }}
                    ></platform-segmented-control>
                </div>

                ${tab === 'trace'
                    ? html`
                        <div class="tab-toolbar" ?hidden=${this._collapsed}>
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
                        </div>
                    `
                    : nothing}

                <div class="panel-body" ?hidden=${this._collapsed}>
                    <div class="tab-panel" data-tab="chat" ?hidden=${tab !== 'chat'}>
                        <platform-flow-ui
                            display="panel"
                            profile="editor_test"
                            flow-id=${this.flowId}
                            branch-id=${this.branchId}
                            base-url="/flows"
                            theme="auto"
                            locale=${locale}
                            @flow-ui-submit-start=${this._onFlowUiSubmitStart}
                            @flow-ui-a2a-frame=${this._onFlowUiA2aFrame}
                            @flow-ui-submit-end=${this._onFlowUiSubmitEnd}
                            @browser-preview-open=${this._onBrowserPreviewOpen}
                        ></platform-flow-ui>
                    </div>

                    ${tab === 'trace' ? html`
                        <div class="tab-panel" data-tab="trace">
                            <div class="trace-panel-inner">
                                <flow-ui-run-trace
                                    .entries=${runTrace}
                                    compact
                                    .showSectionHeader=${false}
                                    .fillAvailable=${true}
                                ></flow-ui-run-trace>
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
                <div
                    class="resize-handle"
                    ?hidden=${this._collapsed}
                    role="separator"
                    aria-orientation="vertical"
                    tabindex="0"
                    title=${this.t('execution_panel.resize_panel')}
                    aria-label=${this.t('execution_panel.resize_panel')}
                    @pointerdown=${this._onResizePointerDown}
                ></div>
            </div>
        `;
    }
}

customElements.define('flows-execution-panel', FlowsExecutionPanel);

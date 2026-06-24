/**
 * flows-floating-panel — оболочка property/resource panel редактора flow.
 *
 * Большое окно поверх канваса; свёрнутый режим — компактный chip для нескольких панелей.
 * Drag за .panel-title, resize, collapse body. Rect — localStorage per panel-id.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import '@platform/lib/components/platform-icon.js';
import {
    readPropertyPanelRectPref,
    schedulePropertyPanelRectPersist,
    writePropertyPanelRectPref,
} from '../../_helpers/flows-editor-property-panel-prefs.js';

const PANEL_VIEWPORT_MARGIN = 12;
const PANEL_MIN_WIDTH = 480;
const PANEL_MIN_HEIGHT = 320;
const PANEL_MAX_WIDTH = 1200;
export const PANEL_COLLAPSED_WIDTH = 280;
export const PANEL_COLLAPSED_HEIGHT = 44;
const PANEL_BASE_Z_INDEX = 25100;

export class FlowsFloatingPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        panelId: { type: String, attribute: 'panel-id' },
        headerIcon: { type: String, attribute: 'header-icon' },
        headerTitle: { type: String, attribute: 'header-title' },
        colorToken: { type: String, attribute: 'color-token' },
        aiEnabled: { type: Boolean, attribute: 'ai-enabled' },
        aiActive: { type: Boolean, attribute: 'ai-active', reflect: true },
        showBackdrop: { type: Boolean, attribute: 'show-backdrop' },
        layout: { type: Object },
        _laraGlow: { state: true },
        _collapsed: { type: Boolean, state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: fixed;
                z-index: 25100;
                display: flex;
                flex-direction: column;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-xl);
                box-shadow: 0 32px 100px rgba(0, 0, 0, 0.45), 0 0 0 1px var(--glass-border-medium);
                overflow: hidden;
                pointer-events: auto;
                animation: slideInPanel 250ms cubic-bezier(0.22, 1, 0.36, 1);
            }

            :host([data-layout-ready]) {
                animation: none;
            }

            :host([data-collapsed]) {
                border-radius: var(--radius-lg);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18), 0 0 0 1px var(--glass-border-medium);
            }

            :host([data-dragging]) .panel-title {
                cursor: grabbing;
            }

            .panel-backdrop {
                position: fixed;
                inset: 0;
                z-index: 0;
                background: color-mix(in oklab, var(--bg-primary) 28%, transparent);
                pointer-events: auto;
            }

            .panel-shell {
                position: relative;
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                z-index: 1;
            }

            .panel-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                flex-shrink: 0;
                user-select: none;
            }

            :host([data-collapsed]) .panel-header {
                border-bottom: none;
                padding: var(--space-1) var(--space-2);
                gap: var(--space-1);
            }

            .panel-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                flex: 1;
                cursor: grab;
                touch-action: none;
            }

            :host([data-collapsed]) .panel-title {
                gap: var(--space-1);
            }

            .panel-icon {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                flex-shrink: 0;
            }

            :host([data-collapsed]) .panel-icon {
                width: 28px;
                height: 28px;
                border-radius: var(--radius-md);
            }

            .panel-name {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            :host([data-collapsed]) .panel-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }

            .panel-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
                cursor: default;
            }

            :host([data-collapsed]) .panel-actions {
                gap: 0;
            }

            .header-actions-host {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .header-actions-host:empty {
                display: none;
            }

            :host([data-collapsed]) .header-actions-host {
                display: none;
            }

            .panel-btn {
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: transparent;
                border: none;
                border-radius: var(--radius-lg);
                color: var(--text-tertiary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }

            :host([data-collapsed]) .panel-btn {
                width: 28px;
                height: 28px;
            }

            .panel-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .panel-btn.ai[aria-pressed="true"] {
                color: var(--accent);
                background: var(--accent-subtle);
            }

            .panel-btn.ai:hover {
                color: var(--accent);
            }

            :host([data-collapsed]) .panel-btn.ai {
                display: none;
            }

            .panel-body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: 0;
                position: relative;
                z-index: 1;
            }

            :host([data-collapsed]) .panel-body {
                display: none;
            }

            .panel-body[data-lara-glow] {
                animation: laraNodeGlow 3.2s ease-out;
            }

            .resize-handle {
                position: absolute;
                right: 2px;
                bottom: 2px;
                width: 28px;
                height: 28px;
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
                z-index: 3;
                touch-action: none;
            }

            .resize-handle::before,
            .resize-handle::after {
                content: '';
                position: absolute;
                right: 8px;
                bottom: 8px;
                width: 8px;
                height: 1px;
                border-radius: var(--radius-full);
                background: currentColor;
                transform: rotate(-45deg);
                transform-origin: right center;
            }

            .resize-handle::after {
                right: 7px;
                bottom: 12px;
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

            :host([data-collapsed]) .resize-handle {
                display: none;
            }

            @keyframes slideInPanel {
                from { opacity: 0; }
                to { opacity: 1; }
            }

            @keyframes laraNodeGlow {
                0% {
                    box-shadow: inset 0 0 0 1px var(--accent), inset 0 0 0 9999px var(--accent-subtle);
                    background: var(--accent-subtle);
                }
                40% {
                    box-shadow: inset 0 0 0 1px var(--accent), inset 0 0 0 9999px var(--accent-subtle);
                }
                100% {
                    box-shadow: inset 0 0 0 1px transparent, inset 0 0 0 9999px transparent;
                    background: transparent;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.panelId = '';
        this.headerIcon = 'box';
        this.headerTitle = '';
        this.colorToken = 'var(--accent)';
        this.aiEnabled = false;
        this.aiActive = false;
        this.showBackdrop = false;
        this.layout = null;
        this._laraGlow = false;
        this._collapsed = false;
        /** @type {{ left: number, top: number, width: number, height: number, expandedWidth?: number, expandedHeight?: number } | null} */
        this._panelRect = null;
        this._dragState = null;
        this._resizeState = null;
        this._titlePointerDown = null;
        /** @type {Element | null} */
        this._pointerCaptureEl = null;
        /** @type {number | null} */
        this._activePointerId = null;
        this._boundPanelPointerMove = (e) => this._onPanelPointerMove(e);
        this._boundPanelPointerUp = (e) => this._onPanelPointerUp(e);
        this._boundPanelViewportResize = () => this._clampFloatingPanelToViewport();
        this.useEvent('flows/lara/node_updated', () => {
            this._laraGlow = true;
            window.setTimeout(() => { this._laraGlow = false; }, 3200);
        });
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
        super.disconnectedCallback?.();
    }

    firstUpdated() {
        super.firstUpdated?.();
        this.setAttribute('data-layout-ready', '');
        this._initFloatingLayout();
        this._bringPanelToFront();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('layout') && this.hasAttribute('data-layout-ready')) {
            this._syncFromLayoutProperty();
        }
    }

    _resolvedPanelId() {
        if (typeof this.panelId === 'string' && this.panelId.length > 0) {
            return this.panelId;
        }
        return '__legacy__';
    }

    _panelViewport() {
        if (typeof window === 'undefined') {
            return { width: 1280, height: 800 };
        }
        return { width: window.innerWidth, height: window.innerHeight };
    }

    _panelMinWidth(collapsed = this._collapsed) {
        if (collapsed) {
            return PANEL_COLLAPSED_WIDTH;
        }
        const viewport = this._panelViewport();
        return Math.max(400, Math.min(PANEL_MIN_WIDTH, viewport.width - PANEL_VIEWPORT_MARGIN * 2));
    }

    _panelMinHeight(collapsed = this._collapsed) {
        if (collapsed) {
            return PANEL_COLLAPSED_HEIGHT;
        }
        const viewport = this._panelViewport();
        return Math.max(240, Math.min(PANEL_MIN_HEIGHT, viewport.height - PANEL_VIEWPORT_MARGIN * 2));
    }

    _clampPanelRect(rect, collapsed = this._collapsed) {
        const viewport = this._panelViewport();
        const margin = PANEL_VIEWPORT_MARGIN;
        if (collapsed) {
            const width = PANEL_COLLAPSED_WIDTH;
            const height = PANEL_COLLAPSED_HEIGHT;
            const leftMax = Math.max(margin, viewport.width - width - margin);
            const topMax = Math.max(margin, viewport.height - height - margin);
            const left = Math.min(Math.max(Number(rect.left) || margin, margin), leftMax);
            const top = Math.min(Math.max(Number(rect.top) || margin, margin), topMax);
            return { left, top, width, height };
        }
        const minWidth = this._panelMinWidth(false);
        const minHeight = this._panelMinHeight(false);
        const maxWidth = Math.max(minWidth, viewport.width - margin * 2);
        const maxHeight = Math.max(minHeight, viewport.height - margin * 2);
        const width = Math.min(Math.max(Number(rect.width) || minWidth, minWidth), maxWidth);
        const height = Math.min(Math.max(Number(rect.height) || minHeight, minHeight), maxHeight);
        const leftMax = Math.max(margin, viewport.width - width - margin);
        const topMax = Math.max(margin, viewport.height - height - margin);
        const left = Math.min(Math.max(Number(rect.left) || margin, margin), leftMax);
        const top = Math.min(Math.max(Number(rect.top) || margin, margin), topMax);
        return { left, top, width, height };
    }

    _defaultFloatingPanelRect(collapsed = this._collapsed) {
        const viewport = this._panelViewport();
        const margin = PANEL_VIEWPORT_MARGIN;
        if (collapsed) {
            return this._clampPanelRect({
                left: margin,
                top: margin,
                width: PANEL_COLLAPSED_WIDTH,
                height: PANEL_COLLAPSED_HEIGHT,
            }, true);
        }
        const maxWidth = Math.max(this._panelMinWidth(false), viewport.width - margin * 2);
        const width = Math.min(PANEL_MAX_WIDTH, Math.floor(viewport.width * 0.94), maxWidth);
        const height = Math.min(
            Math.floor(viewport.height * 0.94),
            Math.max(this._panelMinHeight(false), viewport.height - margin * 2),
        );
        const top = Math.max(margin, Math.floor(viewport.height * 0.03));
        return this._clampPanelRect({
            left: (viewport.width - width) / 2,
            top,
            width,
            height,
        }, false);
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

    _layoutSnapshot() {
        if (!this._panelRect) {
            return null;
        }
        return {
            left: this._panelRect.left,
            top: this._panelRect.top,
            width: this._panelRect.width,
            height: this._panelRect.height,
            collapsed: this._collapsed,
            expandedWidth: this._panelRect.expandedWidth,
            expandedHeight: this._panelRect.expandedHeight,
        };
    }

    _emitLayoutChange() {
        const snapshot = this._layoutSnapshot();
        if (!snapshot) {
            return;
        }
        this.emit('layout-change', snapshot);
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

    _applyFloatingPanelRect(rect, { bringToFront = false, emit = false } = {}) {
        const clamped = this._clampPanelRect(rect);
        this._panelRect = {
            ...clamped,
            expandedWidth: typeof rect.expandedWidth === 'number' ? rect.expandedWidth : this._panelRect?.expandedWidth,
            expandedHeight: typeof rect.expandedHeight === 'number' ? rect.expandedHeight : this._panelRect?.expandedHeight,
        };
        this._syncPanelHostAttributes();
        if (bringToFront) {
            this._bringPanelToFront();
        } else if (!this.style.zIndex) {
            this.style.zIndex = String(PANEL_BASE_Z_INDEX);
        }
        this.style.position = 'fixed';
        this.style.left = `${Math.round(clamped.left)}px`;
        this.style.top = `${Math.round(clamped.top)}px`;
        this.style.right = 'auto';
        this.style.bottom = 'auto';
        this.style.width = `${Math.round(clamped.width)}px`;
        this.style.height = `${Math.round(clamped.height)}px`;
        this.style.transform = '';
        if (emit) {
            this._emitLayoutChange();
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
        if (!this._panelRect) {
            return;
        }
        this._applyFloatingPanelRect(this._panelRect);
    }

    _persistPanelRect({ flush = false } = {}) {
        const snapshot = this._layoutSnapshot();
        if (!snapshot) {
            return;
        }
        const panelId = this._resolvedPanelId();
        if (flush) {
            writePropertyPanelRectPref(panelId, snapshot);
        } else {
            schedulePropertyPanelRectPersist(panelId, snapshot);
        }
    }

    _initFloatingLayout() {
        const layout = this.layout;
        if (layout && typeof layout === 'object') {
            this._syncFromLayoutProperty({ initial: true });
            return;
        }
        const saved = readPropertyPanelRectPref(this._resolvedPanelId());
        if (saved) {
            this._collapsed = saved.collapsed;
            this._applyFloatingPanelRect({
                ...saved,
                expandedWidth: saved.expandedWidth,
                expandedHeight: saved.expandedHeight,
            });
        } else {
            this._applyFloatingPanelRect(this._defaultFloatingPanelRect());
        }
        this._syncPanelHostAttributes();
    }

    _syncFromLayoutProperty({ initial = false } = {}) {
        const layout = this.layout;
        if (!layout || typeof layout !== 'object') {
            return;
        }
        const collapsed = layout.collapsed === true;
        this._collapsed = collapsed;
        const baseRect = this._panelRect ?? this._defaultFloatingPanelRect(collapsed);
        const nextRect = {
            left: typeof layout.left === 'number' ? layout.left : baseRect.left,
            top: typeof layout.top === 'number' ? layout.top : baseRect.top,
            width: typeof layout.width === 'number' ? layout.width : baseRect.width,
            height: typeof layout.height === 'number' ? layout.height : baseRect.height,
            expandedWidth: typeof layout.expandedWidth === 'number' ? layout.expandedWidth : baseRect.expandedWidth,
            expandedHeight: typeof layout.expandedHeight === 'number' ? layout.expandedHeight : baseRect.expandedHeight,
        };
        if (collapsed) {
            nextRect.width = PANEL_COLLAPSED_WIDTH;
            nextRect.height = PANEL_COLLAPSED_HEIGHT;
        }
        this._applyFloatingPanelRect(nextRect);
        if (initial) {
            this._syncPanelHostAttributes();
        }
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
            '.resize-handle',
        ].join(',')));
    }

    _capturePanelPointer(e) {
        if (!(e.currentTarget instanceof Element)) {
            throw new Error('flows-floating-panel: pointer capture target must be Element');
        }
        this._pointerCaptureEl = e.currentTarget;
        this._activePointerId = e.pointerId;
        this._pointerCaptureEl.setPointerCapture(e.pointerId);
    }

    _releasePanelPointerCapture() {
        if (
            this._pointerCaptureEl instanceof Element
            && this._activePointerId !== null
            && this._pointerCaptureEl.hasPointerCapture(this._activePointerId)
        ) {
            this._pointerCaptureEl.releasePointerCapture(this._activePointerId);
        }
        this._pointerCaptureEl = null;
        this._activePointerId = null;
    }

    _onPanelTitlePointerDown(e) {
        if (e.button !== 0 || this._isPanelControlTarget(e.target)) {
            return;
        }
        e.preventDefault();
        this._endPanelPointerInteraction();
        const rect = this._ensureFloatingPanelRect({ bringToFront: true });
        if (!rect) {
            throw new Error('flows-floating-panel: panel rect is required for drag');
        }
        this._titlePointerDown = { x: e.clientX, y: e.clientY };
        this._capturePanelPointer(e);
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
        const rect = this._ensureFloatingPanelRect({ bringToFront: true });
        if (!rect) {
            throw new Error('flows-floating-panel: panel rect is required for resize');
        }
        if (this._collapsed) {
            this._collapsed = false;
            this._syncPanelHostAttributes();
        }
        this._capturePanelPointer(e);
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
            this._persistPanelRect({ flush: false });
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
            this._persistPanelRect({ flush: false });
        }
    }

    _onPanelPointerUp(e) {
        const dragState = this._dragState;
        const titlePointerDown = this._titlePointerDown;
        this._endPanelPointerInteraction();
        if (
            dragState
            && titlePointerDown
            && this._collapsed
            && Math.abs(e.clientX - titlePointerDown.x) < 4
            && Math.abs(e.clientY - titlePointerDown.y) < 4
        ) {
            this.emit('activate');
        }
        this._titlePointerDown = null;
    }

    _endPanelPointerInteraction() {
        const hadInteraction = Boolean(this._dragState || this._resizeState);
        this._releasePanelPointerCapture();
        this._dragState = null;
        this._resizeState = null;
        this.removeAttribute('data-dragging');
        this.removeAttribute('data-resizing');
        if (typeof window !== 'undefined') {
            window.removeEventListener('pointermove', this._boundPanelPointerMove);
            window.removeEventListener('pointerup', this._boundPanelPointerUp);
            window.removeEventListener('pointercancel', this._boundPanelPointerUp);
        }
        if (hadInteraction) {
            this._persistPanelRect({ flush: true });
            this._emitLayoutChange();
        }
    }

    _toggleCollapsed() {
        const shouldCollapse = !this._collapsed;
        const currentRect = this._ensureFloatingPanelRect({ bringToFront: true });
        if (!currentRect) {
            throw new Error('flows-floating-panel: panel rect is required for collapse');
        }

        if (shouldCollapse) {
            this._collapsed = true;
            this._applyFloatingPanelRect({
                left: currentRect.left,
                top: currentRect.top,
                width: PANEL_COLLAPSED_WIDTH,
                height: PANEL_COLLAPSED_HEIGHT,
                expandedWidth: currentRect.width,
                expandedHeight: currentRect.height,
            }, { emit: true });
        } else {
            this._collapsed = false;
            const expandedWidth = typeof currentRect.expandedWidth === 'number'
                ? currentRect.expandedWidth
                : PANEL_MAX_WIDTH;
            const expandedHeight = typeof currentRect.expandedHeight === 'number'
                ? currentRect.expandedHeight
                : this._panelMinHeight(false);
            this._applyFloatingPanelRect({
                left: currentRect.left,
                top: currentRect.top,
                width: Math.max(expandedWidth, this._panelMinWidth(false)),
                height: Math.max(expandedHeight, this._panelMinHeight(false)),
                expandedWidth,
                expandedHeight,
            }, { emit: true });
        }
        this._syncPanelHostAttributes();
        this._persistPanelRect({ flush: true });
        this.requestUpdate();
    }

    _close() {
        this.emit('close');
    }

    _toggleNodeAiHelper() {
        this.emit('node-ai-helper-toggle', { open: !this.aiActive });
    }

    render() {
        const showBackdrop = this.showBackdrop && !this._collapsed;
        return html`
            ${showBackdrop ? html`<div class="panel-backdrop" @click=${this._close}></div>` : nothing}
            <div class="panel-shell">
                <div class="panel-header">
                    <div
                        class="panel-title"
                        title=${this.t('floating_panel.drag_hint')}
                        @pointerdown=${this._onPanelTitlePointerDown}
                    >
                        <div class="panel-icon" style=${`background: color-mix(in oklab, ${this.colorToken} 15%, transparent); color: ${this.colorToken};`}>
                            <platform-icon name=${this.headerIcon} size=${this._collapsed ? '14' : '18'}></platform-icon>
                        </div>
                        <div class="panel-name">${this.headerTitle}</div>
                    </div>
                    <div class="panel-actions">
                        <div class="header-actions-host"></div>
                        ${this.aiEnabled ? html`
                            <button
                                class="panel-btn ai"
                                type="button"
                                title=${this.t(this.aiActive ? 'floating_panel.close_node_ai' : 'floating_panel.open_node_ai')}
                                aria-label=${this.t(this.aiActive ? 'floating_panel.close_node_ai' : 'floating_panel.open_node_ai')}
                                aria-pressed=${this.aiActive ? 'true' : 'false'}
                                @click=${this._toggleNodeAiHelper}
                            >
                                <platform-icon name="ai" size="14"></platform-icon>
                            </button>
                        ` : ''}
                        <button
                            class="panel-btn"
                            type="button"
                            title=${this._collapsed
                                ? this.t('floating_panel.restore_panel')
                                : this.t('floating_panel.minimize_panel')}
                            aria-expanded=${this._collapsed ? 'false' : 'true'}
                            @click=${this._toggleCollapsed}
                        >
                            <platform-icon name=${this._collapsed ? 'fullscreen' : 'minus'} size="14"></platform-icon>
                        </button>
                        <button class="panel-btn" type="button" title=${this.t('floating_panel.close')} @click=${this._close}>
                            <platform-icon name="close" size="14"></platform-icon>
                        </button>
                    </div>
                </div>
                <div class="panel-body" ?data-lara-glow=${this._laraGlow}>
                    <slot></slot>
                </div>
                ${this._collapsed ? nothing : html`
                    <button
                        class="resize-handle"
                        type="button"
                        title=${this.t('floating_panel.resize_hint')}
                        aria-label=${this.t('floating_panel.resize_hint')}
                        @pointerdown=${this._onResizePointerDown}
                    ></button>
                `}
            </div>
        `;
    }
}

customElements.define('flows-floating-panel', FlowsFloatingPanel);

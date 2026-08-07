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
import '@platform/lib/components/platform-button.js';
import {
    ASSISTANT_COL_WIDTH_DEFAULT,
    ASSISTANT_COL_WIDTH_MAX,
    ASSISTANT_COL_WIDTH_MIN,
    normalizeAssistantWidth,
    readAssistantWidthPref,
    readPropertyPanelRectPref,
    scheduleAssistantWidthPersist,
    schedulePropertyPanelRectPersist,
    writeAssistantWidthPref,
    writePropertyPanelRectPref,
} from '../../_helpers/flows-editor-property-panel-prefs.js';

const PANEL_VIEWPORT_MARGIN = 12;
const PANEL_MIN_WIDTH = 480;
const PANEL_MIN_HEIGHT = 320;
const PANEL_MAX_WIDTH = 1200;
const PANEL_MAX_WIDTH_AI = 1580;
/** Минимальная ширина колонки editor при drag splitter'а ассистента. */
const EDITOR_COL_MIN_WIDTH = 360;
/** Ширина видимого gutter между editor и chat. */
const ASSISTANT_SPLITTER_GUTTER_PX = 10;
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
                box-shadow: var(--glass-shadow-ultra), 0 0 0 1px var(--glass-border-medium);
                overflow: hidden;
                pointer-events: auto;
                animation: slideInPanel 250ms cubic-bezier(0.22, 1, 0.36, 1);
                --panel-assistant-width: 380px;
            }

            :host([data-layout-ready]) {
                animation: none;
            }

            :host([data-geometry-transition]) {
                transition:
                    width var(--duration-slower) var(--easing-smooth),
                    left var(--duration-slower) var(--easing-smooth);
            }

            :host([data-dragging]),
            :host([data-resizing]),
            :host([data-assistant-resizing]) {
                transition: none;
            }

            :host([data-assistant-resizing]) .panel-body {
                transition: none;
            }

            :host([data-collapsed]) {
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-strong), 0 0 0 1px var(--glass-border-medium);
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

            :host([data-collapsed]) .panel-ai-btn {
                display: none;
            }

            .panel-body {
                flex: 1;
                min-height: 0;
                overflow: hidden;
                padding: 0;
                position: relative;
                z-index: 1;
                display: grid;
                grid-template-columns: minmax(0, 1fr) 0;
                grid-template-rows: minmax(0, 1fr);
                transition: grid-template-columns var(--duration-slower) var(--easing-smooth);
            }

            :host([ai-active]) .panel-body {
                grid-template-columns:
                    minmax(0, 1fr)
                    10px
                    var(--panel-assistant-width);
            }

            :host([data-collapsed]) .panel-body {
                display: none;
            }

            .panel-editor,
            .panel-assistant {
                min-width: 0;
                min-height: 0;
                height: 100%;
                overflow: hidden;
            }

            .panel-editor {
                overflow: auto;
            }

            .panel-assistant {
                display: flex;
                flex-direction: column;
                opacity: 0;
                transform: translateX(12px);
                transition:
                    opacity var(--duration-slow) var(--easing-smooth),
                    transform var(--duration-slower) var(--easing-smooth);
            }

            :host([ai-active]) .panel-assistant {
                opacity: 1;
                transform: translateX(0);
            }

            .panel-assistant ::slotted(*) {
                flex: 1 1 0;
                min-height: 0;
                height: 100%;
                overflow: hidden;
            }

            .assistant-resize-handle {
                z-index: 4;
                width: 100%;
                height: 100%;
                margin: 0;
                padding: 0;
                border: none;
                border-left: 1px solid var(--border-subtle);
                border-right: 1px solid var(--border-subtle);
                box-sizing: border-box;
                cursor: col-resize;
                touch-action: none;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 3px;
                background: color-mix(in oklab, var(--bg-secondary) 88%, var(--bg-primary));
                transition: background var(--duration-fast) var(--easing-default);
            }

            .assistant-resize-handle::before,
            .assistant-resize-handle::after {
                content: '';
                width: 3px;
                height: 3px;
                border-radius: var(--radius-full);
                background: var(--text-tertiary);
                opacity: 0.85;
                pointer-events: none;
                transition:
                    background var(--duration-fast) var(--easing-default),
                    opacity var(--duration-fast) var(--easing-default);
            }

            .assistant-resize-grip {
                width: 3px;
                height: 3px;
                border-radius: var(--radius-full);
                background: var(--text-tertiary);
                opacity: 0.85;
                pointer-events: none;
                transition:
                    background var(--duration-fast) var(--easing-default),
                    opacity var(--duration-fast) var(--easing-default);
            }

            .assistant-resize-handle:hover,
            :host([data-assistant-resizing]) .assistant-resize-handle {
                background: color-mix(in oklab, var(--accent) 16%, var(--bg-secondary));
            }

            .assistant-resize-handle:hover::before,
            .assistant-resize-handle:hover::after,
            .assistant-resize-handle:hover .assistant-resize-grip,
            :host([data-assistant-resizing]) .assistant-resize-handle::before,
            :host([data-assistant-resizing]) .assistant-resize-handle::after,
            :host([data-assistant-resizing]) .assistant-resize-handle .assistant-resize-grip {
                background: var(--accent);
                opacity: 1;
            }

            :host(:not([ai-active])) .assistant-resize-handle,
            :host([data-collapsed]) .assistant-resize-handle {
                display: none;
            }

            .panel-body[data-lara-glow] {
                animation: laraNodeGlow 3.2s ease-out;
            }

            @media (prefers-reduced-motion: reduce) {
                :host([data-geometry-transition]) {
                    transition: none;
                }

                .panel-body,
                .panel-assistant {
                    transition: none;
                }
            }

            .resize-handle {
                position: absolute;
                right: 2px;
                bottom: 2px;
                z-index: 3;
                opacity: 0.65;
                cursor: nwse-resize;
                touch-action: none;
                --platform-button-icon-size: var(--flows-micro-control-size);
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
                pointer-events: none;
            }

            .resize-handle::after {
                right: 7px;
                bottom: 12px;
                width: 5px;
            }

            .resize-handle:hover {
                opacity: 1;
            }

            :host([data-resizing]) .resize-handle {
                opacity: 1;
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
        /** @type {number | null} */
        this._widthBeforeAi = null;
        /** @type {number} */
        this._assistantWidth = ASSISTANT_COL_WIDTH_DEFAULT;
        this._dragState = null;
        this._resizeState = null;
        /** @type {{ startX: number, startAssistantWidth: number, panelWidth: number } | null} */
        this._assistantResizeState = null;
        this._titlePointerDown = null;
        /** @type {Element | null} */
        this._pointerCaptureEl = null;
        /** @type {number | null} */
        this._activePointerId = null;
        this._boundPanelPointerMove = (e) => this._onPanelPointerMove(e);
        this._boundPanelPointerUp = (e) => this._onPanelPointerUp(e);
        this._boundPanelViewportResize = () => this._clampFloatingPanelToViewport();
        this._boundGeometryTransitionEnd = (e) => this._onGeometryTransitionEnd(e);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined') {
            window.addEventListener('resize', this._boundPanelViewportResize);
        }
        this.addEventListener('transitionend', this._boundGeometryTransitionEnd);
    }

    disconnectedCallback() {
        this._endPanelPointerInteraction();
        this.removeEventListener('transitionend', this._boundGeometryTransitionEnd);
        if (typeof window !== 'undefined') {
            window.removeEventListener('resize', this._boundPanelViewportResize);
        }
        super.disconnectedCallback?.();
    }

    firstUpdated() {
        super.firstUpdated?.();
        this._loadAssistantWidth();
        this.setAttribute('data-layout-ready', '');
        this._initFloatingLayout();
        this._bringPanelToFront();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('layout') && this.hasAttribute('data-layout-ready')) {
            this._syncFromLayoutProperty();
        }
        if (changed.has('aiActive') && this.hasAttribute('data-layout-ready')) {
            this._syncAiPanelWidth(Boolean(changed.get('aiActive')));
        }
    }

    _resolvedPanelId() {
        if (typeof this.panelId === 'string' && this.panelId.length > 0) {
            return this.panelId;
        }
        return '__legacy__';
    }

    _assistantColumnWidth() {
        const normalized = normalizeAssistantWidth(this._assistantWidth);
        if (normalized === null) {
            return ASSISTANT_COL_WIDTH_DEFAULT;
        }
        return normalized;
    }

    _loadAssistantWidth() {
        const saved = readAssistantWidthPref();
        this._assistantWidth = saved === null ? ASSISTANT_COL_WIDTH_DEFAULT : saved;
        this._applyAssistantWidthCss();
    }

    _applyAssistantWidthCss() {
        this.style.setProperty('--panel-assistant-width', `${this._assistantColumnWidth()}px`);
    }

    _setAssistantWidth(width, { persist = false, flush = false } = {}) {
        const normalized = normalizeAssistantWidth(width);
        if (normalized === null) {
            throw new Error('flows-floating-panel: assistant width must be a finite number');
        }
        this._assistantWidth = normalized;
        this._applyAssistantWidthCss();
        if (!persist) {
            return;
        }
        if (flush) {
            writeAssistantWidthPref(normalized);
        } else {
            scheduleAssistantWidthPersist(normalized);
        }
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

    _panelCapWidth() {
        return this.aiActive ? PANEL_MAX_WIDTH_AI : PANEL_MAX_WIDTH;
    }

    _prefersReducedMotion() {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return false;
        }
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    _setGeometryTransition(enabled) {
        if (
            enabled
            && !this._dragState
            && !this._resizeState
            && !this._assistantResizeState
            && !this._prefersReducedMotion()
        ) {
            this.setAttribute('data-geometry-transition', '');
            return;
        }
        this.removeAttribute('data-geometry-transition');
    }

    _onGeometryTransitionEnd(e) {
        if (e.target !== this) {
            return;
        }
        if (e.propertyName !== 'width' && e.propertyName !== 'left') {
            return;
        }
        this._setGeometryTransition(false);
    }

    _persistWidthSnapshot(snapshot) {
        if (!this.aiActive || snapshot.collapsed) {
            return snapshot;
        }
        const assistantWidth = this._assistantColumnWidth();
        const baseWidth = Math.max(this._panelMinWidth(false), snapshot.width - assistantWidth);
        const next = {
            ...snapshot,
            width: baseWidth,
        };
        if (typeof snapshot.expandedWidth === 'number') {
            next.expandedWidth = Math.max(
                this._panelMinWidth(false),
                snapshot.expandedWidth - assistantWidth,
            );
        }
        return next;
    }

    _syncAiPanelWidth(wasActive) {
        if (this._collapsed || this._dragState || this._resizeState || this._assistantResizeState) {
            return;
        }
        const rect = this._panelRect ?? this._readCurrentPanelRect();
        if (!rect) {
            return;
        }
        const assistantWidth = this._assistantColumnWidth();
        const viewport = this._panelViewport();
        const margin = PANEL_VIEWPORT_MARGIN;
        const maxAllowed = Math.min(
            PANEL_MAX_WIDTH_AI,
            Math.max(this._panelMinWidth(false), viewport.width - margin * 2),
        );

        if (this.aiActive && !wasActive) {
            this._widthBeforeAi = rect.width;
            const nextWidth = Math.min(rect.width + assistantWidth, maxAllowed);
            let nextLeft = rect.left;
            if (nextLeft + nextWidth > viewport.width - margin) {
                nextLeft = Math.max(margin, viewport.width - margin - nextWidth);
            }
            this._setGeometryTransition(true);
            this._applyFloatingPanelRect({
                ...rect,
                left: nextLeft,
                width: nextWidth,
            }, { emit: true });
            this._persistPanelRect({ flush: false });
            return;
        }

        if (!this.aiActive && wasActive) {
            const widthBeforeAi = typeof this._widthBeforeAi === 'number'
                ? this._widthBeforeAi
                : this._panelMinWidth(false);
            const closeWidth = Math.max(
                this._panelMinWidth(false),
                Math.max(widthBeforeAi, rect.width - assistantWidth),
            );
            this._widthBeforeAi = null;
            this._setGeometryTransition(true);
            this._applyFloatingPanelRect({
                ...rect,
                width: Math.min(closeWidth, maxAllowed),
            }, { emit: true });
            this._persistPanelRect({ flush: false });
        }
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
        const width = Math.min(this._panelCapWidth(), Math.floor(viewport.width * 0.94), maxWidth);
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
        const toSave = this._persistWidthSnapshot(snapshot);
        const panelId = this._resolvedPanelId();
        if (flush) {
            writePropertyPanelRectPref(panelId, toSave);
        } else {
            schedulePropertyPanelRectPersist(panelId, toSave);
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
            'platform-button',
            'platform-switch',
            'platform-help-hint',
            '.resize-handle',
            '.assistant-resize-handle',
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

    _onAssistantResizePointerDown(e) {
        if (e.button !== 0 || !this.aiActive || this._collapsed) {
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        this._endPanelPointerInteraction();
        const rect = this._ensureFloatingPanelRect({ bringToFront: true });
        if (!rect) {
            throw new Error('flows-floating-panel: panel rect is required for assistant resize');
        }
        this._capturePanelPointer(e);
        this._assistantResizeState = {
            startX: e.clientX,
            startAssistantWidth: this._assistantColumnWidth(),
            panelWidth: rect.width,
        };
        this.setAttribute('data-assistant-resizing', '');
        this._setGeometryTransition(false);
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
        if (this._assistantResizeState) {
            const dx = e.clientX - this._assistantResizeState.startX;
            // Влево (dx < 0) → чат шире за счёт editor; вправо → уже. Outer panel не двигаем.
            const desiredAssistant = this._assistantResizeState.startAssistantWidth - dx;
            const panelWidth = this._assistantResizeState.panelWidth;
            const maxAssistant = Math.min(
                ASSISTANT_COL_WIDTH_MAX,
                Math.max(
                    ASSISTANT_COL_WIDTH_MIN,
                    panelWidth - EDITOR_COL_MIN_WIDTH - ASSISTANT_SPLITTER_GUTTER_PX,
                ),
            );
            const nextAssistant = Math.min(
                maxAssistant,
                Math.max(ASSISTANT_COL_WIDTH_MIN, Math.round(desiredAssistant)),
            );
            this._setAssistantWidth(nextAssistant, { persist: true, flush: false });
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
        const hadAssistantResize = Boolean(this._assistantResizeState);
        this._endPanelPointerInteraction();
        if (hadAssistantResize) {
            this._setAssistantWidth(this._assistantColumnWidth(), { persist: true, flush: true });
        }
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
        const hadInteraction = Boolean(
            this._dragState || this._resizeState || this._assistantResizeState,
        );
        this._releasePanelPointerCapture();
        this._dragState = null;
        this._resizeState = null;
        this._assistantResizeState = null;
        this.removeAttribute('data-dragging');
        this.removeAttribute('data-resizing');
        this.removeAttribute('data-assistant-resizing');
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
            const expandedWidth = this.aiActive
                ? Math.max(this._panelMinWidth(false), currentRect.width - this._assistantColumnWidth())
                : currentRect.width;
            this._applyFloatingPanelRect({
                left: currentRect.left,
                top: currentRect.top,
                width: PANEL_COLLAPSED_WIDTH,
                height: PANEL_COLLAPSED_HEIGHT,
                expandedWidth,
                expandedHeight: currentRect.height,
            }, { emit: true });
        } else {
            this._collapsed = false;
            const expandedWidth = typeof currentRect.expandedWidth === 'number'
                ? currentRect.expandedWidth
                : this._panelCapWidth();
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
                            <platform-button
                                class="panel-ai-btn"
                                variant=${this.aiActive ? 'secondary' : 'ghost'}
                                icon-only
                                density="dense"
                                aria-label=${this.t(this.aiActive ? 'floating_panel.close_node_ai' : 'floating_panel.open_node_ai')}
                                @click=${this._toggleNodeAiHelper}
                            >
                                <platform-icon name="ai" size="14"></platform-icon>
                            </platform-button>
                        ` : ''}
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this._collapsed
                                ? this.t('floating_panel.restore_panel')
                                : this.t('floating_panel.minimize_panel')}
                            @click=${this._toggleCollapsed}
                        >
                            <platform-icon name=${this._collapsed ? 'fullscreen' : 'minimize'} size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('floating_panel.close')}
                            @click=${this._close}
                        >
                            <platform-icon name="close" size="14"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <div class="panel-body" ?data-lara-glow=${this._laraGlow}>
                    <div class="panel-editor">
                        <slot name="editor"></slot>
                        <slot></slot>
                    </div>
                    ${this.aiActive && !this._collapsed ? html`
                        <div
                            class="assistant-resize-handle"
                            role="separator"
                            aria-orientation="vertical"
                            title=${this.t('floating_panel.resize_assistant')}
                            aria-label=${this.t('floating_panel.resize_assistant')}
                            tabindex="0"
                            @pointerdown=${this._onAssistantResizePointerDown}
                        >
                            <span class="assistant-resize-grip"></span>
                        </div>
                    ` : nothing}
                    <div class="panel-assistant">
                        <slot name="assistant"></slot>
                    </div>
                </div>
                ${this._collapsed ? nothing : html`
                    <platform-button
                        class="resize-handle"
                        variant="ghost"
                        icon-only
                        density="dense"
                        aria-label=${this.t('floating_panel.resize_hint')}
                        @pointerdown=${this._onResizePointerDown}
                    ></platform-button>
                `}
            </div>
        `;
    }
}

customElements.define('flows-floating-panel', FlowsFloatingPanel);

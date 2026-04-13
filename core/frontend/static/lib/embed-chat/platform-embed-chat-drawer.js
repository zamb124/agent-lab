import { LitElement, html, css, nothing } from 'lit';
import { embedChatLabelsForLang } from './embed-chat-default-labels.js';
import { readEmbedChatUrlParams, applyEmbedChatDrawerSizeVars } from './embed-chat-url-params.js';
import { resolveEmbedChatTheme } from './embed-chat-theme.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import '@platform/lib/components/platform-icon.js';
import './platform-embed-chat.js';

/**
 * Панель + FAB: только Lit + platform-embed-chat. Без PlatformElement;
 * кнопки шапки — platform-icon; иконка FAB — та же разметка, что в core/assets/icons/ai.svg (встроена, без отдельного fetch).
 * Переключение: клик по FAB или CustomEvent `humanitec-embed-chat-toggle` на window.
 * Тема: атрибут theme="light"|"dark"|"auto" (по умолчанию auto — как data-theme на documentElement).
 * Параметры URL страницы: см. embed-chat-url-params.js (embed_theme, embed_lang, embed_width, embed_assistant_name, …).
 * Имя в шапке: атрибут assistant-title или ?embed_assistant_name= / embed_chat_title= (UTF-8).
 * Закрытие панели скрывает её (panel--collapsed), экземпляр platform-embed-chat сохраняется.
 */
export class PlatformEmbedChatDrawer extends LitElement {
    static properties = {
        flowsBaseUrl: { type: String, attribute: 'flows-base-url' },
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
        useCredentials: { type: Boolean, attribute: 'use-credentials' },
        enableVoice: { type: Boolean, attribute: 'enable-voice' },
        /** ru | en | пусто — из document.documentElement.lang */
        locale: { type: String },
        open: { type: Boolean, reflect: true },
        /** light | dark | auto — auto синхронизируется с document.documentElement[data-theme] и theme-change */
        theme: { type: String },
        /** Поверх дефолтных строк (embed-chat-default-labels) */
        labels: { type: Object },
        getAuthToken: { type: Object },
        getExtraMetadataVariables: { type: Object },
        getContextVariables: { type: Object },
        eventNamespace: { type: String, attribute: 'event-namespace' },
        actionHandlers: { type: Object },
        /** Имя в шапке панели и для внутреннего чата; внешние сайты: атрибут assistant-title или ?embed_assistant_name= */
        assistantTitle: { type: String, attribute: 'assistant-title' },
        toggleEventName: { type: String, attribute: 'toggle-event-name' },
        /** Переключатель языка в композере; также embed_locale_control=1 в URL */
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        /** Развёрнутая панель на весь вьюпорт (кнопка в шапке). */
        panelMaximized: { type: Boolean, state: true },
        /** Непрочитанные ответы ассистента (панель закрыта), бейдж на FAB. */
        fabUnreadCount: { type: Number, state: true },
    };

    static styles = css`
        :host {
            display: contents;
            --embed-drawer-radius: 25px;
        }

        .fab {
            position: fixed;
            z-index: 25000;
            right: max(16px, env(safe-area-inset-right, 0px));
            bottom: max(16px, env(safe-area-inset-bottom, 0px));
            width: 56px;
            height: 56px;
            border-radius: 50%;
            border: 1px solid var(--embed-drawer-fab-border, rgba(255, 255, 255, 0.14));
            background: var(--embed-drawer-fab-bg, #99a6f9);
            color: var(--embed-drawer-fab-fg, #0f0f12);
            box-shadow: 0 10px 32px rgba(0, 0, 0, 0.35);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0;
            box-sizing: border-box;
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
            background: var(--embed-drawer-fab-bg-hover, #8794f0);
        }

        .fab svg {
            width: 26px;
            height: 26px;
            display: block;
        }

        @media (max-width: 767px) {
            .fab {
                width: 52px;
                height: 52px;
                right: max(12px, env(safe-area-inset-right, 0px));
                bottom: max(12px, env(safe-area-inset-bottom, 0px));
            }
        }

        :host([data-embed-theme='light']) .fab {
            --embed-drawer-fab-border: rgba(109, 98, 232, 0.35);
            --embed-drawer-fab-bg: linear-gradient(145deg, #f0edff 0%, #e2e8ff 100%);
            --embed-drawer-fab-bg-hover: linear-gradient(145deg, #e6e2fc 0%, #d8e0fc 100%);
            --embed-drawer-fab-fg: #1c1f2e;
            box-shadow: 0 10px 32px rgba(60, 50, 140, 0.18);
        }

        .backdrop {
            position: fixed;
            inset: 0;
            z-index: 24990;
            background: rgba(0, 0, 0, 0.45);
            opacity: 1;
            visibility: visible;
            transition:
                opacity 0.34s cubic-bezier(0.22, 1, 0.36, 1),
                visibility 0s linear 0s;
        }

        .backdrop.backdrop--hidden {
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
            transition:
                opacity 0.28s cubic-bezier(0.22, 1, 0.36, 1),
                visibility 0s linear 0.28s;
        }

        :host([data-embed-theme='light']) .backdrop {
            background: rgba(22, 26, 38, 0.28);
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
            border-radius: var(--embed-drawer-radius);
            background: var(--embed-drawer-panel-bg, rgba(24, 26, 34, 0.97));
            border: 1px solid var(--embed-drawer-panel-border, rgba(255, 255, 255, 0.1));
            box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45);
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

        :host([data-embed-theme='light']) .panel {
            --embed-drawer-panel-bg: rgba(255, 255, 255, 0.98);
            --embed-drawer-panel-border: rgba(28, 31, 46, 0.08);
            box-shadow: 0 24px 64px rgba(22, 26, 38, 0.12);
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

        @media (prefers-reduced-motion: reduce) {
            .backdrop,
            .backdrop.backdrop--hidden,
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
            border-bottom: 1px solid var(--embed-drawer-panel-border, rgba(255, 255, 255, 0.1));
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
            color: rgba(255, 255, 255, 0.92);
        }

        :host([data-embed-theme='light']) .panel-head-title {
            color: #1c1f2e;
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
            border-radius: var(--embed-drawer-radius);
            border: 1px solid var(--embed-drawer-panel-border, rgba(255, 255, 255, 0.12));
            background: var(--embed-drawer-close-bg, transparent);
            color: var(--embed-drawer-close-fg, rgba(255, 255, 255, 0.85));
            cursor: pointer;
            padding: 0;
        }

        :host([data-embed-theme='light']) .close-btn {
            --embed-drawer-close-bg: rgba(28, 31, 46, 0.04);
            --embed-drawer-close-fg: rgba(28, 31, 46, 0.75);
        }

        .close-btn:hover {
            background: var(--embed-drawer-close-hover, rgba(255, 255, 255, 0.08));
        }

        :host([data-embed-theme='light']) .close-btn:hover {
            --embed-drawer-close-hover: rgba(28, 31, 46, 0.08);
        }

        .close-btn svg,
        .close-btn platform-icon {
            width: 18px;
            height: 18px;
            display: block;
        }

        platform-embed-chat {
            flex: 1;
            min-height: 0;
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
                border-radius: min(var(--embed-drawer-radius), 20px);
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
                border-radius: min(var(--embed-drawer-radius), 20px);
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
        this.flowsBaseUrl = '';
        this.flowId = '';
        this.skillId = '';
        this.useCredentials = false;
        this.enableVoice = true;
        this.locale = '';
        this.open = false;
        this.theme = 'auto';
        this.labels = {};
        this.getAuthToken = undefined;
        this.getExtraMetadataVariables = undefined;
        this.getContextVariables = undefined;
        this.eventNamespace = 'assistant';
        this.actionHandlers = {};
        this.toggleEventName = 'humanitec-embed-chat-toggle';
        this.showLocaleControl = false;
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
        /** Нативный fullscreen именно для .panel (чтобы не сбрасывать CSS-maximize при чужом FS). */
        this._panelNativeFullscreen = false;
        /** После успешного requestFullscreen на панели — выход без сравнения узлов (Lit / shadow). */
        this._drawerOwnsNativeFullscreen = false;
        this.panelMaximized = false;
        this.fabUnreadCount = 0;
        this._layerBaseZIndex = nextModalLayerZIndex();
        this._panelDragActive = false;
        this._panelDragPosition = null;
        this._panelDragContext = null;
        this._onPanelDragPointerMove = this._onPanelDragPointerMove.bind(this);
        this._onPanelDragPointerUp = this._onPanelDragPointerUp.bind(this);
        this._onViewportResize = this._onViewportResize.bind(this);
    }

    _applyEmbedUrlParams() {
        const p = readEmbedChatUrlParams();
        if (p.theme) {
            this.theme = p.theme;
        }
        if (p.locale) {
            this.locale = p.locale;
        }
        if (p.showLocaleControl !== undefined) {
            this.showLocaleControl = p.showLocaleControl;
        }
        if (p.assistantTitle) {
            this.assistantTitle = p.assistantTitle;
        }
        if (p.skillId) {
            this.skillId = p.skillId;
        }
        applyEmbedChatDrawerSizeVars(this, p);
    }

    connectedCallback() {
        super.connectedCallback();
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

    disconnectedCallback() {
        this._stopPanelDrag();
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
        super.disconnectedCallback();
    }

    firstUpdated(changed) {
        super.firstUpdated(changed);
        this._bindToggleListener();
    }

    updated(changed) {
        if (changed.has('toggleEventName')) {
            this._bindToggleListener();
        }
        if ((changed.has('open') && !this.open) || (changed.has('panelMaximized') && this.panelMaximized)) {
            this._stopPanelDrag();
        }
        if (changed.has('open') && this.open) {
            this.updateComplete.then(() => this._syncPanelToViewport());
        }
        const resolved = resolveEmbedChatTheme(this.theme);
        if (this.getAttribute('data-embed-theme') !== resolved) {
            this.setAttribute('data-embed-theme', resolved);
        }
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

    _resolvedLabels() {
        const lang = this.locale || document.documentElement.lang || 'ru';
        const base = embedChatLabelsForLang(lang);
        const extra = this.labels && typeof this.labels === 'object' ? this.labels : {};
        return { ...base, ...extra };
    }

    _interfaceLocaleForChat() {
        const r = String(this.locale || '').trim().toLowerCase();
        if (!r || r === 'auto') {
            return 'auto';
        }
        const p = r.split(/[-_]/)[0];
        if (p === 'en' || p === 'ru') {
            return p;
        }
        return 'auto';
    }

    /** Заголовок шапки: явное имя ассистента или строка title из labels/локали. */
    _panelAssistantHeadTitle(L) {
        const custom = this.assistantTitle != null ? String(this.assistantTitle).trim() : '';
        if (custom) {
            return custom;
        }
        return L.title;
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

    _isMobileViewportForNativeFullscreen() {
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return false;
        }
        return window.matchMedia('(max-width: 767px)').matches;
    }

    _onEmbedAssistantReplyCompleted() {
        if (this.open) {
            return;
        }
        this.fabUnreadCount += 1;
        this.requestUpdate();
    }

    _assistantEventName() {
        const raw = typeof this.eventNamespace === 'string' ? this.eventNamespace.trim() : '';
        const ns = raw || 'assistant';
        return `${ns}:event`;
    }

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

    onLaraEvent(handler) {
        return this.onAssistantEvent(handler);
    }

    offLaraEvent(handler) {
        this.offAssistantEvent(handler);
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

    _close() {
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

    _onNewChat() {
        const el = this.renderRoot?.querySelector('platform-embed-chat');
        if (el && typeof el.startNewChat === 'function') {
            el.startNewChat();
        }
    }

    render() {
        const L = this._resolvedLabels();
        const headTitle = this._panelAssistantHeadTitle(L);
        const fabAria = this.open ? L.fab_aria_close : this._fabOpenAriaLabel(L);
        const embedTheme = resolveEmbedChatTheme(this.theme);
        const fsLabel = this.panelMaximized ? L.panel_exit_fullscreen : L.panel_fullscreen;
        const panelHeadClass = `panel-head ${this._isPanelDraggable() ? 'panel-head--draggable' : ''} ${
            this._panelDragActive ? 'panel-head--dragging' : ''
        }`;

        return html`
            ${!this.open
                ? html`
                      <button
                          type="button"
                          class="fab"
                          style="z-index:${this._layerZIndex(3)}"
                          aria-label=${fabAria}
                          @click=${this._toggle}
                      >
                ${this.fabUnreadCount > 0
                    ? html`<span class="fab-badge" aria-hidden="true">${this._fabBadgeText()}</span>`
                    : nothing}
                <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <defs>
                        <linearGradient id="pecd-ai-g1" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#4285f4;stop-opacity:1" />
                            <stop offset="100%" style="stop-color:#9c27b0;stop-opacity:1" />
                        </linearGradient>
                        <linearGradient id="pecd-ai-g2" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#34a853;stop-opacity:1" />
                            <stop offset="100%" style="stop-color:#4285f4;stop-opacity:1" />
                        </linearGradient>
                        <linearGradient id="pecd-ai-g3" x1="0%" y1="0%" x2="100%" y2="100%">
                            <stop offset="0%" style="stop-color:#9c27b0;stop-opacity:1" />
                            <stop offset="100%" style="stop-color:#ea4335;stop-opacity:1" />
                        </linearGradient>
                    </defs>
                    <g transform="scale(0.24) translate(0, 0)">
                        <path
                            d="m90.64,59.09l-16.25-7.09c-3.93-1.71-7.06-4.85-8.77-8.77l-7.09-16.25c-.55-1.26-2.34-1.26-2.89,0l-7.09,16.25c-1.71,3.93-4.85,7.06-8.77,8.77l-16.27,7.1c-1.26.55-1.26,2.33,0,2.88l16.55,7.32c3.92,1.73,7.04,4.88,8.73,8.82l6.86,15.94c.54,1.27,2.34,1.27,2.89,0l7.08-16.22c1.71-3.93,4.85-7.06,8.77-8.77l16.25-7.09c1.26-.55,1.26-2.34,0-2.89Z"
                            fill="url(#pecd-ai-g1)"
                            opacity="0.9"
                        />
                        <path
                            d="m25.28,48.51l3.32-7.61c.8-1.84,2.27-3.31,4.11-4.11l7.62-3.32c.59-.26.59-1.1,0-1.35l-7.62-3.32c-1.84-.8-3.31-2.27-4.11-4.11l-3.32-7.62c-.26-.59-1.1-.59-1.35,0l-3.32,7.62c-.8,1.84-2.27,3.31-4.11,4.11l-7.63,3.33c-.59.26-.59,1.09,0,1.35l7.76,3.43c1.84.81,3.3,2.29,4.09,4.13l3.22,7.47c.26.59,1.1.6,1.35,0Z"
                            fill="url(#pecd-ai-g2)"
                            opacity="0.8"
                        />
                        <path
                            d="m39.89,13.95l4.12,1.82c.98.43,1.75,1.22,2.17,2.19l1.71,3.97c.14.32.58.32.72,0l1.76-4.04c.43-.98,1.21-1.76,2.18-2.18l4.04-1.76c.31-.14.31-.58,0-.72l-4.04-1.76c-.98-.43-1.76-1.21-2.18-2.18l-1.76-4.04c-.14-.31-.58-.31-.72,0l-1.76,4.04c-.43.98-1.21,1.76-2.18,2.18l-4.05,1.77c-.31.14-.31.58,0,.72Z"
                            fill="url(#pecd-ai-g3)"
                            opacity="0.7"
                        />
                    </g>
                </svg>
                      </button>
                  `
                : ''}

            <div
                class="backdrop ${this.open ? '' : 'backdrop--hidden'}"
                style="z-index:${this._layerZIndex(1)}"
                aria-hidden="true"
                @click=${this._close}
            ></div>
            <div
                class="panel ${this.panelMaximized ? 'panel--maximized' : ''} ${!this.open ? 'panel--collapsed' : ''}"
                style=${this._panelInlineStyle()}
                aria-hidden=${this.open ? 'false' : 'true'}
                ?inert=${!this.open}
                @click=${(e) => e.stopPropagation()}
            >
                <div class=${panelHeadClass} @pointerdown=${this._onPanelHeadPointerDown}>
                    <span class="panel-head-title">${headTitle}</span>
                    <div class="panel-head-actions">
                        <button
                            type="button"
                            class="close-btn"
                            title=${L.new_chat}
                            aria-label=${L.new_chat}
                            @click=${this._onNewChat}
                        >
                            <platform-icon name="edit" size="18" aria-hidden="true"></platform-icon>
                        </button>
                        <button
                            type="button"
                            class="close-btn"
                            title=${fsLabel}
                            aria-label=${fsLabel}
                            @click=${this._togglePanelFullscreen}
                        >
                            ${this.panelMaximized
                                ? html`<platform-icon name="minimize" size="18" aria-hidden="true"></platform-icon>`
                                : html`<platform-icon name="fullscreen" size="18" aria-hidden="true"></platform-icon>`}
                        </button>
                        <button
                            type="button"
                            class="close-btn"
                            title=${L.panel_close}
                            aria-label=${L.panel_close}
                            @click=${this._close}
                        >
                            <platform-icon name="close" size="18" aria-hidden="true"></platform-icon>
                        </button>
                    </div>
                </div>
                <platform-embed-chat
                    @humanitec-embed-chat-assistant-reply-completed=${this._onEmbedAssistantReplyCompleted}
                    ?hide-header=${true}
                    embed-theme=${embedTheme}
                    interface-locale=${this._interfaceLocaleForChat()}
                    ?show-locale-control=${this.showLocaleControl}
                    .flowsBaseUrl=${this.flowsBaseUrl}
                    flow-id=${this.flowId || ''}
                    skill-id=${this.skillId || ''}
                    .assistantTitle=${headTitle}
                    .title=${headTitle}
                    .labels=${this.labels && typeof this.labels === 'object' ? this.labels : {}}
                    ?use-credentials=${this.useCredentials}
                    ?enable-voice=${this.enableVoice}
                    .getAuthToken=${this.getAuthToken}
                    .getExtraMetadataVariables=${this.getExtraMetadataVariables}
                    .getContextVariables=${this.getContextVariables}
                    .eventNamespace=${this.eventNamespace || 'assistant'}
                    .actionHandlers=${this.actionHandlers && typeof this.actionHandlers === 'object'
                        ? this.actionHandlers
                        : {}}
                ></platform-embed-chat>
            </div>
        `;
    }
}

customElements.define('platform-embed-chat-drawer', PlatformEmbedChatDrawer);

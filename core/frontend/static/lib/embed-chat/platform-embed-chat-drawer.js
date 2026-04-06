import { LitElement, html, css } from 'lit';
import { embedChatLabelsForLang } from './embed-chat-default-labels.js';
import { readEmbedChatUrlParams, applyEmbedChatDrawerSizeVars } from './embed-chat-url-params.js';
import { resolveEmbedChatTheme } from './embed-chat-theme.js';
import './platform-embed-chat.js';

/**
 * Панель + FAB: только Lit + platform-embed-chat. Без PlatformElement, без platform-icon;
 * иконка FAB — та же разметка, что в core/assets/icons/ai.svg (встроена, без отдельного fetch).
 * Переключение: клик по FAB или CustomEvent `humanitec-embed-chat-toggle` на window.
 * Тема: атрибут theme="light"|"dark"|"auto" (по умолчанию auto — как data-theme на documentElement).
 * Параметры URL страницы: см. embed-chat-url-params.js (embed_theme, embed_lang, embed_width, embed_assistant_name, …).
 * Имя в шапке: атрибут assistant-title или ?embed_assistant_name= / embed_chat_title= (UTF-8).
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
        actionHandlers: { type: Object },
        /** Имя в шапке панели и для внутреннего чата; внешние сайты: атрибут assistant-title или ?embed_assistant_name= */
        assistantTitle: { type: String, attribute: 'assistant-title' },
        toggleEventName: { type: String, attribute: 'toggle-event-name' },
        /** Переключатель языка в композере; также embed_locale_control=1 в URL */
        showLocaleControl: { type: Boolean, attribute: 'show-locale-control' },
        /** Развёрнутая панель на весь вьюпорт (кнопка в шапке). */
        panelMaximized: { type: Boolean, state: true },
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
        }

        .fab:hover {
            background: var(--embed-drawer-fab-bg-hover, #8794f0);
        }

        .fab svg {
            width: 26px;
            height: 26px;
            display: block;
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
        }

        :host([data-embed-theme='light']) .panel {
            --embed-drawer-panel-bg: rgba(255, 255, 255, 0.98);
            --embed-drawer-panel-border: rgba(28, 31, 46, 0.08);
            box-shadow: 0 24px 64px rgba(22, 26, 38, 0.12);
        }

        .panel-head {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-shrink: 0;
            padding: 4px 4px 12px 8px;
            border-bottom: 1px solid var(--embed-drawer-panel-border, rgba(255, 255, 255, 0.1));
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

        .close-btn svg {
            width: 18px;
            height: 18px;
            display: block;
        }

        platform-embed-chat {
            flex: 1;
            min-height: 0;
        }

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
        this.panelMaximized = false;
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
        applyEmbedChatDrawerSizeVars(this, p);
    }

    connectedCallback() {
        super.connectedCallback();
        this._applyEmbedUrlParams();
        this._onPopStateEmbedParams = () => this._applyEmbedUrlParams();
        window.addEventListener('popstate', this._onPopStateEmbedParams);
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
                this._panelNativeFullscreen = true;
                return;
            }
            if (this._panelNativeFullscreen) {
                this._panelNativeFullscreen = false;
                if (this.panelMaximized) {
                    this.panelMaximized = false;
                    this.requestUpdate();
                }
            }
        };
        document.addEventListener('fullscreenchange', this._onFullscreenChange);
    }

    disconnectedCallback() {
        if (this._onPopStateEmbedParams) {
            window.removeEventListener('popstate', this._onPopStateEmbedParams);
            this._onPopStateEmbedParams = null;
        }
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
        this._boundToggle = () => {
            this.open = !this.open;
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
        this.open = !this.open;
    }

    _close() {
        const panel = this.renderRoot?.querySelector('.panel');
        if (panel && document.fullscreenElement === panel) {
            this._panelNativeFullscreen = false;
            document.exitFullscreen().catch(() => {});
        }
        this.panelMaximized = false;
        this.open = false;
    }

    async _togglePanelFullscreen() {
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
                el &&
                typeof document !== 'undefined' &&
                document.fullscreenEnabled &&
                typeof el.requestFullscreen === 'function'
            ) {
                try {
                    await el.requestFullscreen();
                } catch {
                    /* только CSS panel--maximized */
                }
            }
        } else {
            if (document.fullscreenElement === panel) {
                this._panelNativeFullscreen = false;
                try {
                    await document.exitFullscreen();
                } catch {
                    /* ignore */
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
        const fabLabel = this.open ? L.fab_aria_close : L.fab_aria_open;
        const embedTheme = resolveEmbedChatTheme(this.theme);
        const fsLabel = this.panelMaximized ? L.panel_exit_fullscreen : L.panel_fullscreen;

        return html`
            ${!this.open
                ? html`
                      <button type="button" class="fab" aria-label=${fabLabel} @click=${this._toggle}>
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

            ${this.open
                ? html`
                      <div class="backdrop" @click=${this._close}></div>
                      <div
                          class="panel ${this.panelMaximized ? 'panel--maximized' : ''}"
                          @click=${(e) => e.stopPropagation()}
                      >
                          <div class="panel-head">
                              <span class="panel-head-title">${headTitle}</span>
                              <div class="panel-head-actions">
                                  <button
                                      type="button"
                                      class="close-btn"
                                      title=${L.new_chat}
                                      aria-label=${L.new_chat}
                                      @click=${this._onNewChat}
                                  >
                                      <svg viewBox="0 0 24 24" aria-hidden="true">
                                          <path
                                              fill="none"
                                              stroke="currentColor"
                                              stroke-width="2"
                                              stroke-linecap="round"
                                              stroke-linejoin="round"
                                              d="M12 20h9M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"
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
                                          ? html`<svg viewBox="0 0 24 24" aria-hidden="true">
                                                <path
                                                    fill="none"
                                                    stroke="currentColor"
                                                    stroke-width="2"
                                                    stroke-linecap="round"
                                                    stroke-linejoin="round"
                                                    d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"
                                                />
                                            </svg>`
                                          : html`<svg viewBox="0 0 24 24" aria-hidden="true">
                                                <path
                                                    fill="none"
                                                    stroke="currentColor"
                                                    stroke-width="2"
                                                    stroke-linecap="round"
                                                    stroke-linejoin="round"
                                                    d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7M9 9H3V3M21 21h-6v-6"
                                                />
                                            </svg>`}
                                  </button>
                                  <button
                                      type="button"
                                      class="close-btn"
                                      title=${L.panel_close}
                                      aria-label=${L.panel_close}
                                      @click=${this._close}
                                  >
                                      <svg viewBox="0 0 24 24" aria-hidden="true">
                                          <path
                                              fill="none"
                                              stroke="currentColor"
                                              stroke-width="2"
                                              stroke-linecap="round"
                                              d="M6 6l12 12M18 6L6 18"
                                          />
                                      </svg>
                                  </button>
                              </div>
                          </div>
                          <platform-embed-chat
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
                              .actionHandlers=${this.actionHandlers && typeof this.actionHandlers === 'object'
                                  ? this.actionHandlers
                                  : {}}
                          ></platform-embed-chat>
                      </div>
                  `
                : ''}
        `;
    }
}

customElements.define('platform-embed-chat-drawer', PlatformEmbedChatDrawer);

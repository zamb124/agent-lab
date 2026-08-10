import { LitElement, css, html } from '../../lit-shim.js';
import '../components/platform-flow-ui.js';
import { FLOW_UI_TOGGLE_EVENT } from './preferences.js';

const BRAND_LOGO_SRC = '/static/core/assets/service_logos/linnex_spinner_logo.png';

export class FlowUIDrawer extends LitElement {
    static properties = {
        open: { type: Boolean, reflect: true },
        expanded: { type: Boolean, reflect: true },
        config: { attribute: false },
    };

    static styles = css`
        :host { position: fixed; inset: auto 22px 22px auto; z-index: 2147483000; font-family: system-ui; }
        :host([data-embed-position="bottom-left"]) { inset: auto auto 22px 22px; }
        .launcher {
            width: 58px; height: 58px; padding: 0; border: 1px solid var(--flow-ui-logo-disc-border, rgba(255, 255, 255, 0.14));
            border-radius: 50%; cursor: pointer; display: grid; place-items: center;
            background: var(--flow-ui-logo-disc-bg, #0c0c0f);
            box-shadow: var(
                --flow-ui-logo-disc-shadow,
                0 1px 0 rgba(255, 255, 255, 0.1) inset,
                0 14px 36px rgba(0, 0, 0, 0.45),
                0 4px 12px rgba(0, 0, 0, 0.3)
            );
            overflow: hidden;
        }
        .launcher img {
            width: 34px; height: 34px; object-fit: contain; display: block; pointer-events: none;
        }
        .panel {
            position: absolute; right: 0; bottom: 70px; width: min(430px, calc(100vw - 24px));
            height: min(720px, calc(100vh - 110px)); transform-origin: bottom right;
            transition: opacity .18s ease, transform .18s ease;
            display: flex;
            flex-direction: column;
            min-height: 0;
            /* overflow must stay visible: platform-flow-ui owns the soft shadow.
             * Square overflow:hidden here clipped that shadow into dark corner nicks. */
            overflow: visible;
            border-radius: 22px;
        }
        :host([data-embed-position="bottom-left"]) .panel { right: auto; left: 0; transform-origin: bottom left; }
        :host(:not([open])) .panel { opacity: 0; transform: translateY(12px) scale(.98); pointer-events: none; }
        :host([expanded][open]) {
            inset: 0;
        }
        :host([expanded][open]) .panel {
            position: fixed;
            inset: 0;
            right: 0;
            left: 0;
            bottom: 0;
            width: 100vw;
            height: 100dvh;
            max-width: none;
            max-height: none;
            border-radius: 0;
            transform: none;
        }
        :host([expanded][open]) platform-flow-ui {
            border-radius: 0;
        }
        platform-flow-ui {
            flex: 1 1 0;
            min-height: 0;
            height: 100%;
            border: 1px solid var(--flow-ui-border, rgba(149, 163, 194, 0.2));
            border-radius: 22px;
        }
        @media (max-width: 520px) {
            :host { inset: auto 10px 10px 10px; }
            .panel { position: fixed; inset: 0; width: 100vw; height: 100dvh; }
            .launcher { margin-left: auto; display: grid; }
        }
        @media (prefers-reduced-motion: reduce) { .panel { transition: none; } }
    `;

    constructor() {
        super();
        this.open = false;
        this.expanded = false;
        this.config = {};
        this._boundToggleEventName = null;
        this._toggle = (event) => {
            if (event?.detail && Object.prototype.hasOwnProperty.call(event.detail, 'open')) {
                this.open = event.detail.open === true;
                return;
            }
            this.open = !this.open;
        };
        this._onExpandToggle = (event) => {
            const detail = event?.detail;
            if (detail && Object.prototype.hasOwnProperty.call(detail, 'expanded')) {
                this.expanded = detail.expanded === true;
                return;
            }
            this.expanded = !this.expanded;
        };
    }

    connectedCallback() {
        super.connectedCallback();
        this._bindToggleListener();
        this.addEventListener('flow-ui-drawer-expand-toggle', this._onExpandToggle);
    }

    disconnectedCallback() {
        this.removeEventListener('flow-ui-drawer-expand-toggle', this._onExpandToggle);
        this._unbindToggleListener();
        super.disconnectedCallback();
    }

    updated(changedProperties) {
        if (changedProperties.has('config')) {
            this._bindToggleListener();
        }
        if (changedProperties.has('open')) {
            if (this.open !== true) {
                this.expanded = false;
            }
            this.dispatchEvent(new CustomEvent('flow-ui-drawer-open-changed', {
                detail: { open: this.open === true },
                bubbles: true,
                composed: true,
            }));
        }
        if (changedProperties.has('expanded')) {
            this.dispatchEvent(new CustomEvent('flow-ui-drawer-expanded-changed', {
                detail: { expanded: this.expanded === true },
                bubbles: true,
                composed: true,
            }));
        }
    }

    _toggleEventName() {
        const name = this.config?.toggleEventName;
        if (name === null || name === undefined || name === '') {
            return FLOW_UI_TOGGLE_EVENT;
        }
        if (typeof name !== 'string') {
            throw new Error('flow-ui-drawer: config.toggleEventName must be a string');
        }
        return name;
    }

    _unbindToggleListener() {
        if (this._boundToggleEventName === null) {
            return;
        }
        globalThis.removeEventListener(this._boundToggleEventName, this._toggle);
        this._boundToggleEventName = null;
    }

    _bindToggleListener() {
        if (!this.isConnected) {
            return;
        }
        const next = this._toggleEventName();
        if (this._boundToggleEventName === next) {
            return;
        }
        this._unbindToggleListener();
        this._boundToggleEventName = next;
        globalThis.addEventListener(next, this._toggle);
    }

    _credentials(config) {
        if (typeof config.credentials !== 'string' || config.credentials.trim() === '') {
            return 'include';
        }
        return config.credentials;
    }

    render() {
        const c = this.config;
        if (!c || typeof c !== 'object') {
            throw new Error('flow-ui-drawer: config is required');
        }
        if (typeof c.baseUrl !== 'string' || c.baseUrl.trim() === '') {
            throw new Error('flow-ui-drawer: config.baseUrl is required');
        }
        const position = c.launcherPosition === 'bottom-left' ? 'bottom-left' : 'bottom-right';
        if (this.getAttribute('data-embed-position') !== position) {
            this.setAttribute('data-embed-position', position);
        }
        const companyId = typeof c.companyId === 'string' ? c.companyId : '';
        const voiceBaseUrl = typeof c.voiceBaseUrl === 'string' ? c.voiceBaseUrl : '';
        return html`<div class="panel"><platform-flow-ui
            embed-id=${c.embedId || ''}
            flow-id=${c.flowId || ''}
            branch-id=${c.branchId || 'default'}
            base-url=${c.baseUrl}
            context-id=${c.contextId || ''}
            company-id=${companyId}
            voice-base-url=${voiceBaseUrl}
            display="drawer"
            profile=${c.profile || 'embed_public'}
            theme=${c.theme || 'auto'}
            locale=${c.locale || 'ru'}
            credentials=${this._credentials(c)}
            ?drawer-expanded=${this.expanded === true}
            .getRequestHeaders=${c.getRequestHeaders}
            .getExtraMetadataVariables=${c.getExtraMetadataVariables}
        ></platform-flow-ui></div>${c.showLauncher === false
            ? html``
            : html`<button
                type="button"
                class="launcher"
                aria-label=${this.open ? 'Close assistant' : 'Open assistant'}
                @click=${() => { this.open = !this.open; }}
            ><img src=${BRAND_LOGO_SRC} alt="" aria-hidden="true"></button>`}`;
    }
}

if (!customElements.get('flow-ui-drawer')) customElements.define('flow-ui-drawer', FlowUIDrawer);

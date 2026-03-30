import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const TOOLBAR_ICONS = {
    fit: html`<svg viewBox="0 0 24 24"><path d="M8 3H3v5"/><path d="M3 3l6 6"/><path d="M16 3h5v5"/><path d="M21 3l-6 6"/><path d="M8 21H3v-5"/><path d="M3 21l6-6"/><path d="M16 21h5v-5"/><path d="M21 21l-6-6"/></svg>`,
    path_mode: html`<svg viewBox="0 0 24 24"><circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 17c4-6 5-9 10-10"/></svg>`,
    swap_path: html`<svg viewBox="0 0 24 24"><path d="M4 7h14"/><path d="M14 3l4 4-4 4"/><path d="M20 17H6"/><path d="M10 13l-4 4 4 4"/></svg>`,
    reset_path: html`<svg viewBox="0 0 24 24"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M7 6l1 14h8l1-14"/></svg>`,
    depth_plus: html`<svg viewBox="0 0 24 24"><path d="M4 12h16"/><path d="M12 4v16"/></svg>`,
    depth_minus: html`<svg viewBox="0 0 24 24"><path d="M4 12h16"/></svg>`,
    filter_rel_type: html`<svg viewBox="0 0 24 24"><path d="M4 5h16"/><path d="M7 12h10"/><path d="M10 19h4"/></svg>`,
    labels_mode: html`<svg viewBox="0 0 24 24"><path d="M4 18l4-12h2l4 12"/><path d="M6 13h6"/><path d="M16 8h4"/><path d="M18 8v10"/></svg>`,
    reset_view: html`<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 3v5h5"/></svg>`,
    toggle_search: html`<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>`,
    toggle_timeline: html`<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M8 7l4-4 4 4"/><path d="M8 17l4 4 4-4"/></svg>`,
    toggle_legend: html`<svg viewBox="0 0 24 24"><path d="M4 6h16"/><path d="M4 12h10"/><path d="M4 18h6"/></svg>`,
    toggle_meta: html`<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M12 12v4"/></svg>`,
};

export class GraphToolbar extends PlatformElement {
    static properties = {
        actions: { type: Array },
        toggles: { type: Array },
        labelMode: { type: String, attribute: 'label-mode' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: relative;
                z-index: 14;
                display: flex;
                flex-direction: column;
                gap: 4px;
                padding: 6px;
                border-radius: 12px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                backdrop-filter: blur(6px);
                pointer-events: auto;
                max-height: calc(100% - 32px);
                overflow-y: auto;
                scrollbar-width: none;
            }

            :host::-webkit-scrollbar {
                display: none;
            }

            .separator {
                width: 20px;
                height: 2px;
                background: var(--accent);
                opacity: 0.4;
                border-radius: 1px;
                margin: 4px auto;
            }

            .icon-btn {
                width: 28px;
                height: 28px;
                border-radius: 7px;
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-medium);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                cursor: pointer;
                transition: background 0.16s ease, transform 0.16s ease;
            }

            .icon-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
                transform: translateY(-1px);
            }

            .icon-btn.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
                color: var(--text-primary);
            }

            .icon-btn svg {
                width: 14px;
                height: 14px;
                fill: none;
                stroke: currentColor;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            .toggle-btn {
                border-style: dashed;
                border-color: var(--glass-border-medium);
            }

            .toggle-btn.active {
                border-style: solid;
                border-color: var(--accent);
            }

            @media (max-width: 767px) {
                :host {
                    padding: 4px;
                    gap: 4px;
                }

                .icon-btn {
                    width: 28px;
                    height: 28px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.actions = [];
        this.toggles = [];
        this.labelMode = 'fixed';
    }

    _getIcon(actionId) {
        const icon = TOOLBAR_ICONS[actionId];
        if (!icon) {
            throw new Error(`Unknown toolbar icon: ${actionId}`);
        }
        return icon;
    }

    _isActionActive(actionId) {
        return actionId === 'labels_mode' && this.labelMode === 'adaptive';
    }

    _onAction(actionId) {
        this.emit('toolbar-action', { actionId });
    }

    _onToggle(panelId) {
        this.emit('panel-toggle', { panelId });
    }

    render() {
        return html`
            ${this.actions.map((action) => html`
                <button
                    class="icon-btn ${this._isActionActive(action.id) ? 'active' : ''}"
                    type="button"
                    title=${action.label}
                    aria-label=${action.label}
                    @click=${() => this._onAction(action.id)}
                >
                    ${this._getIcon(action.id)}
                </button>
            `)}
            <div class="separator"></div>
            ${this.toggles.map((toggle) => html`
                <button
                    class="icon-btn toggle-btn ${toggle.active ? 'active' : ''}"
                    type="button"
                    title=${toggle.label}
                    aria-label=${toggle.label}
                    @click=${() => this._onToggle(toggle.id)}
                >
                    ${this._getIcon(`toggle_${toggle.id}`)}
                </button>
            `)}
        `;
    }
}

customElements.define('graph-toolbar', GraphToolbar);

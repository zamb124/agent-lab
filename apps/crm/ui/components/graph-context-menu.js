import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const CTX_ICONS = {
    'open-entity': html`<svg viewBox="0 0 24 24"><path d="M15 3h6v6"/><path d="M10 14L21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>`,
    'focus': html`<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/></svg>`,
    'path-from': html`<svg viewBox="0 0 24 24"><circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 17c4-6 5-9 10-10"/></svg>`,
    'graph-from': html`<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M8 7l4-4 4 4"/></svg>`,
};

export class GraphContextMenu extends PlatformElement {
    static properties = {
        x: { type: Number },
        y: { type: Number },
        nodeId: { type: String, attribute: 'node-id' },
        edgeId: { type: String, attribute: 'edge-id' },
        visible: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                z-index: 20;
                display: none;
                min-width: 160px;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: 10px;
                backdrop-filter: blur(12px);
                padding: 4px;
                box-shadow: var(--glass-shadow-medium);
                pointer-events: auto;
            }

            :host([visible]) {
                display: block;
            }

            .ctx-item {
                display: flex;
                align-items: center;
                gap: 8px;
                width: 100%;
                padding: 7px 12px;
                border: none;
                border-radius: 7px;
                background: none;
                color: var(--text-primary);
                font-size: 13px;
                cursor: pointer;
                text-align: left;
            }

            .ctx-item:hover {
                background: var(--glass-solid-medium);
            }

            .ctx-item svg {
                width: 14px;
                height: 14px;
                fill: none;
                stroke: currentColor;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
                flex-shrink: 0;
            }

            .separator {
                height: 1px;
                background: var(--glass-border-subtle);
                margin: 3px 8px;
            }
        `,
    ];

    constructor() {
        super();
        this.x = 0;
        this.y = 0;
        this.nodeId = '';
        this.edgeId = '';
        this.visible = false;
    }

    updated(changed) {
        if (changed.has('x') || changed.has('y')) {
            this.style.left = `${this.x}px`;
            this.style.top = `${this.y}px`;
        }
    }

    _onAction(action) {
        this.emit('ctx-action', {
            action,
            nodeId: this.nodeId,
            edgeId: this.edgeId,
        });
    }

    render() {
        if (!this.nodeId && !this.edgeId) {
            return html``;
        }

        return html`
            ${this.nodeId ? html`
                <button class="ctx-item" @click=${() => this._onAction('open-entity')}>
                    ${CTX_ICONS['open-entity']}
                    ${this.i18n.t('graph.context_open_entity')}
                </button>
                <button class="ctx-item" @click=${() => this._onAction('focus')}>
                    ${CTX_ICONS['focus']}
                    ${this.i18n.t('graph.zoom_in')}
                </button>
                <div class="separator"></div>
                <button class="ctx-item" @click=${() => this._onAction('path-from')}>
                    ${CTX_ICONS['path-from']}
                    ${this.i18n.t('graph.context_path_from')}
                </button>
                <button class="ctx-item" @click=${() => this._onAction('graph-from')}>
                    ${CTX_ICONS['graph-from']}
                    ${this.i18n.t('graph.context_graph_from')}
                </button>
            ` : ''}
        `;
    }
}

customElements.define('graph-context-menu', GraphContextMenu);

/**
 * flows-canvas-context-menu — inline меню по правому клику на канвасе.
 *
 * Меню зависит от target:
 *   - `node`: open / toggle entry / toggle breakpoint / duplicate / delete /
 *     advanced (incoming-policy);
 *   - `edge`: edit condition / delete connection;
 *   - `background`: add sticky note / fit view / reset zoom / select all /
 *     show shortcuts.
 *
 * Все действия — это `this.emit('action', { kind, ... })` на родителя.
 * Закрытие — `this.emit('close')`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

const NODE_ITEMS = Object.freeze([
    { kind: 'open_properties', icon: 'edit' },
    { kind: 'toggle_entry',    icon: 'play' },
    { kind: 'toggle_breakpoint', icon: 'breakpoint' },
    { kind: 'duplicate',       icon: 'copy' },
    { kind: 'separator' },
    { kind: 'delete',          icon: 'trash', danger: true },
    { kind: 'separator' },
    { kind: 'advanced_incoming_policy', icon: 'settings' },
]);

const EDGE_ITEMS = Object.freeze([
    { kind: 'edit_condition', icon: 'edit' },
    { kind: 'delete_edge',    icon: 'trash', danger: true },
]);

const BACKGROUND_ITEMS = Object.freeze([
    { kind: 'add_sticky',      icon: 'text-fields' },
    { kind: 'fit_view',        icon: 'fullscreen' },
    { kind: 'reset_zoom',      icon: 'search' },
    { kind: 'select_all',      icon: 'checklist' },
    { kind: 'separator' },
    { kind: 'show_shortcuts',  icon: 'help' },
]);

export class FlowsCanvasContextMenu extends PlatformElement {
    static properties = {
        x: { type: Number },
        y: { type: Number },
        target: { type: String },
        targetId: { type: String, attribute: 'target-id' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                z-index: 50;
                min-width: 220px;
                padding: var(--space-1) 0;
                border-radius: var(--radius-md);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-strong);
                border: 1px solid var(--glass-border-medium);
                color: var(--text-primary);
                user-select: none;
            }
            .item {
                display: flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background var(--duration-fast);
            }
            .item:hover { background: var(--glass-solid-medium); }
            .item[data-danger] { color: var(--error); }
            .item[data-danger]:hover { background: var(--error-bg); }
            .separator {
                height: 1px;
                margin: var(--space-1) 0;
                background: var(--border-subtle);
            }
            .label { flex: 1; }
        `,
    ];

    constructor() {
        super();
        this.x = 0;
        this.y = 0;
        this.target = 'background';
        this.targetId = '';
    }

    _items() {
        if (this.target === 'node') return NODE_ITEMS;
        if (this.target === 'edge') return EDGE_ITEMS;
        return BACKGROUND_ITEMS;
    }

    _label(kind) {
        return this.t(`canvas.context_menu.${kind}`);
    }

    _activate(item) {
        if (item.kind === 'separator') return;
        this.emit('action', { kind: item.kind, target: this.target, targetId: this.targetId });
        this.emit('close');
    }

    connectedCallback() {
        super.connectedCallback();
        this.style.left = `${this.x}px`;
        this.style.top = `${this.y}px`;
    }

    render() {
        return html`
            ${this._items().map((item) => item.kind === 'separator'
                ? html`<div class="separator"></div>`
                : html`
                    <div
                        class="item"
                        ?data-danger=${item.danger === true}
                        @click=${() => this._activate(item)}
                    >
                        <platform-icon name=${item.icon} size="14"></platform-icon>
                        <span class="label">${this._label(item.kind)}</span>
                    </div>
                `)}
        `;
    }
}

customElements.define('flows-canvas-context-menu', FlowsCanvasContextMenu);

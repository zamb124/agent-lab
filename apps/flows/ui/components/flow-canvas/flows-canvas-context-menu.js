/**
 * flows-canvas-context-menu — inline меню по правому клику на канвасе.
 *
 * Меню зависит от target:
 *   - `node`: открыть / переключить entry / переключить breakpoint / дублировать / удалить /
 *     расширенное (incoming-policy);
 *   - `edge`: редактировать условие / удалить связь;
 *   - `background`: добавить стикер / fit view / сброс zoom / выделить всё /
 *     показать горячие клавиши.
 *
 * Все действия — это `this.emit('action', { kind, ... })` на родителя.
 * Закрытие — `this.emit('close')`.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

const RESOURCE_NODE_MENU_EXCLUDE = new Set(['toggle_entry', 'advanced_incoming_policy']);

function collapseContextMenuSeparators(items) {
    const out = [];
    for (let i = 0; i < items.length; i += 1) {
        const item = items[i];
        if (item.kind === 'separator') {
            if (out.length === 0 || out[out.length - 1].kind === 'separator') {
                continue;
            }
        }
        out.push(item);
    }
    while (out.length > 0 && out[out.length - 1].kind === 'separator') {
        out.pop();
    }
    return out;
}

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
        resourceNode: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: fixed;
                left: 0;
                top: 0;
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
        this.resourceNode = false;
        this._onDocPointerDown = this._onDocPointerDown.bind(this);
        this._onDocKeyDown = this._onDocKeyDown.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._onDocPointerDown, true);
        document.addEventListener('contextmenu', this._onDocPointerDown, true);
        document.addEventListener('keydown', this._onDocKeyDown, true);
    }

    disconnectedCallback() {
        document.removeEventListener('pointerdown', this._onDocPointerDown, true);
        document.removeEventListener('contextmenu', this._onDocPointerDown, true);
        document.removeEventListener('keydown', this._onDocKeyDown, true);
        super.disconnectedCallback();
    }

    _onDocPointerDown(e) {
        const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
        if (path.includes(this)) return;
        this.emit('close');
    }

    _onDocKeyDown(e) {
        if (e.key === 'Escape') this.emit('close');
    }

    _items() {
        if (this.target === 'node') {
            const base = this.resourceNode
                ? NODE_ITEMS.filter((i) => !RESOURCE_NODE_MENU_EXCLUDE.has(i.kind))
                : NODE_ITEMS;
            return collapseContextMenuSeparators(base);
        }
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

    updated() {
        const rect = this.getBoundingClientRect();
        const w = rect.width || this.offsetWidth || 220;
        const h = rect.height || this.offsetHeight || 0;
        const margin = 8;
        const maxX = Math.max(margin, window.innerWidth - w - margin);
        const maxY = Math.max(margin, window.innerHeight - h - margin);
        const left = Math.min(Math.max(this.x, margin), maxX);
        const top = Math.min(Math.max(this.y, margin), maxY);
        this.style.left = `${left}px`;
        this.style.top = `${top}px`;
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

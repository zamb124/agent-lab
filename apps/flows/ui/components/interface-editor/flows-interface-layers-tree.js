/**
 * Layers tree: select (multi via shift), rename by double click, hide/lock,
 * drag to reorder or reparent (drop before/after/inside).
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FLOW_UI_CATALOG_MANIFEST } from '@platform/lib/flow-ui/catalog/manifest.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsInterfaceLayersTree extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        surface: { attribute: false },
        selectedIds: { attribute: false },
        hoveredId: { attribute: false },
        lockedIds: { attribute: false },
        _collapsed: { state: true },
        _renamingId: { state: true },
        _dropHint: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: block; }
        .title {
            font-size: 11px;
            color: var(--text-tertiary);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            margin: 14px 8px 6px;
        }
        .row {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 5px 6px 5px 0;
            min-height: 28px;
            border-radius: var(--radius-sm, 7px);
            cursor: pointer;
            font-size: 12px;
            min-width: 0;
            position: relative;
            box-sizing: border-box;
        }
        .row:hover { background: var(--glass-solid-subtle); }
        .row[data-selected="true"] {
            background: var(--accent-subtle);
            color: var(--accent);
        }
        .row[data-hovered="true"]:not([data-selected="true"]) {
            background: var(--glass-solid-subtle);
        }
        .row[data-hidden="true"] .label { opacity: .45; }
        .row[data-drop="before"]::before,
        .row[data-drop="after"]::after {
            content: '';
            position: absolute;
            left: 6px; right: 6px;
            height: 2px;
            background: var(--accent);
            border-radius: 2px;
        }
        .row[data-drop="before"]::before { top: -1px; }
        .row[data-drop="after"]::after { bottom: -1px; }
        .row[data-drop="inside"] { outline: 1.5px solid var(--accent); outline-offset: -1px; }
        .chevron {
            width: 16px;
            height: 16px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            color: var(--text-tertiary);
            cursor: pointer;
        }
        .chevron[data-collapsed="true"] { transform: rotate(-90deg); }
        .type-icon { flex-shrink: 0; color: var(--text-tertiary); }
        .row[data-selected="true"] .type-icon { color: var(--accent); }
        .label {
            flex: 1;
            min-width: 0;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .label .cid { opacity: .5; margin-left: 4px; font-size: 11px; }
        .rename-input {
            flex: 1;
            min-width: 0;
            height: 22px;
            border: 1px solid var(--accent);
            border-radius: 6px;
            background: var(--bg-elevated);
            color: inherit;
            font: inherit;
            font-size: 12px;
            padding: 0 4px;
        }
        .tool {
            width: 20px;
            height: 20px;
            display: none;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            border-radius: 5px;
            color: var(--text-tertiary);
            cursor: pointer;
        }
        .row:hover .tool, .tool[data-on="true"] { display: inline-flex; }
        .tool:hover { color: var(--text-primary); background: var(--glass-solid-medium); }
        .tool:focus-visible, .chevron:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
    `];

    constructor() {
        super();
        this.surface = null;
        this.selectedIds = [];
        this.hoveredId = '';
        this.lockedIds = [];
        this._collapsed = new Set();
        this._renamingId = '';
        this._dropHint = null;
    }

    _iconFor(component) {
        const entry = FLOW_UI_CATALOG_MANIFEST.components[component.type];
        return entry ? entry.editor.icon : 'box';
    }

    _toggleCollapse(id) {
        const next = new Set(this._collapsed);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        this._collapsed = next;
    }

    _commitRename(component, raw) {
        this._renamingId = '';
        const nextId = String(raw || '').trim();
        if (!nextId || nextId === component.component_id) return;
        this.emit('component-rename', { componentId: component.component_id, nextId });
    }

    _dropPosition(event) {
        const row = event.currentTarget;
        const rect = row.getBoundingClientRect();
        const ratio = (event.clientY - rect.top) / rect.height;
        const component = this.surface?.components?.[row.dataset.id];
        if (component?.kind === 'container' && ratio > 0.3 && ratio < 0.7) return 'inside';
        return ratio < 0.5 ? 'before' : 'after';
    }

    _onDragOver(event, id) {
        if (!event.dataTransfer.types.includes('application/x-flow-ui-move')) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
        this._dropHint = { id, position: this._dropPosition(event) };
    }

    _onDrop(event, id) {
        const movedId = event.dataTransfer.getData('application/x-flow-ui-move');
        const hint = this._dropHint;
        this._dropHint = null;
        if (!movedId || !hint || hint.id !== id || movedId === id) return;
        event.preventDefault();
        this.emit('layers-move', {
            componentId: movedId,
            targetId: id,
            position: hint.position,
        });
    }

    _tool({ on, labelKey, icon, action }) {
        const label = this.t(labelKey);
        return html`<span
            class="tool"
            role="button"
            tabindex="0"
            data-on=${on ? 'true' : 'false'}
            title=${label}
            aria-label=${label}
            @click=${(event) => { event.stopPropagation(); action(); }}
            @keydown=${(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    event.stopPropagation();
                    action();
                }
            }}
        ><platform-icon name=${icon} size="12"></platform-icon></span>`;
    }

    _row(id, depth) {
        const component = this.surface?.components?.[id];
        if (!component) return nothing;
        const selected = (this.selectedIds || []).includes(id);
        const locked = (this.lockedIds || []).includes(id);
        const hidden = component.visibility === false
            || component.visibility?.visible === false;
        const collapsed = this._collapsed.has(id);
        const isContainer = component.kind === 'container';
        const renaming = this._renamingId === id;
        const drop = this._dropHint?.id === id ? this._dropHint.position : '';
        return html`
            <div
                class="row"
                style=${`padding-left:${6 + depth * 14}px`}
                data-id=${id}
                data-selected=${selected ? 'true' : 'false'}
                data-hovered=${this.hoveredId === id ? 'true' : 'false'}
                data-hidden=${hidden ? 'true' : 'false'}
                data-drop=${drop}
                draggable=${id === (this.surface?.root_component_id || 'root') ? 'false' : 'true'}
                @click=${(event) => this.emit('component-select', {
                    componentId: id,
                    additive: event.shiftKey === true,
                })}
                @mouseenter=${() => this.emit('component-hover', { componentId: id })}
                @mouseleave=${() => this.emit('component-hover', { componentId: '' })}
                @dragstart=${(event) => {
                    event.dataTransfer.setData('application/x-flow-ui-move', id);
                    event.dataTransfer.effectAllowed = 'move';
                }}
                @dragover=${(event) => this._onDragOver(event, id)}
                @dragleave=${() => { if (this._dropHint?.id === id) this._dropHint = null; }}
                @drop=${(event) => this._onDrop(event, id)}
            >
                ${isContainer ? html`<span
                    class="chevron"
                    role="button"
                    tabindex="0"
                    data-collapsed=${collapsed ? 'true' : 'false'}
                    aria-label=${this.t('interface_editor.layers_toggle')}
                    aria-expanded=${collapsed ? 'false' : 'true'}
                    @click=${(event) => { event.stopPropagation(); this._toggleCollapse(id); }}
                    @keydown=${(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault();
                            event.stopPropagation();
                            this._toggleCollapse(id);
                        }
                    }}
                ><platform-icon name="chevron-down" size="12"></platform-icon></span>` : html`<span class="chevron"></span>`}
                <platform-icon class="type-icon" name=${this._iconFor(component)} size="13"></platform-icon>
                ${renaming
                    ? html`<input
                        class="rename-input"
                        data-canon="inline-edit"
                        .value=${id}
                        @click=${(event) => event.stopPropagation()}
                        @keydown=${(event) => {
                            if (event.key === 'Enter') this._commitRename(component, event.target.value);
                            if (event.key === 'Escape') this._renamingId = '';
                        }}
                        @blur=${(event) => this._commitRename(component, event.target.value)}
                    >`
                    : html`<span
                        class="label"
                        @dblclick=${(event) => {
                            event.stopPropagation();
                            this._renamingId = id;
                            this.updateComplete.then(() => {
                                this.renderRoot.querySelector('.rename-input')?.focus();
                            });
                        }}
                    >${component.type}<span class="cid">${id}</span></span>`}
                ${this._tool({
                    on: hidden,
                    labelKey: hidden ? 'interface_editor.layers_show' : 'interface_editor.layers_hide',
                    icon: 'eye',
                    action: () => this.emit('component-visibility', { componentId: id, visible: hidden }),
                })}
                ${this._tool({
                    on: locked,
                    labelKey: locked ? 'interface_editor.layers_unlock' : 'interface_editor.layers_lock',
                    icon: locked ? 'lock' : 'unlock',
                    action: () => this.emit('component-lock', { componentId: id }),
                })}
            </div>
            ${isContainer && !collapsed
                ? (component.children || []).map((childId) => this._row(childId, depth + 1))
                : nothing}
        `;
    }

    render() {
        return html`
            <div class="title">${this.t('interface_editor.layers_title')}</div>
            ${this._row(this.surface?.root_component_id || 'root', 0)}
        `;
    }
}

if (!customElements.get('flows-interface-layers-tree')) {
    customElements.define('flows-interface-layers-tree', FlowsInterfaceLayersTree);
}

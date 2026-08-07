/**
 * Insert panel: every catalog component from the manifest, grouped, searchable,
 * insertable by click or drag onto the canvas.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import {
    FLOW_UI_EDITOR_GROUPS,
    FLOW_UI_PALETTE_PSEUDO_ENTRIES,
    flowUIPaletteComponentEntries,
} from '@platform/lib/flow-ui/catalog/manifest.js';
import '@platform/lib/components/platform-icon.js';

export const FLOW_UI_DND_MIME = 'application/x-flow-ui-component';

export class FlowsInterfacePalette extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        query: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: block; }
        .search { padding: 4px 4px 0; }
        .search input {
            width: 100%;
            box-sizing: border-box;
            height: 30px;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: var(--bg-elevated);
            color: inherit;
            padding: 0 8px;
            font: inherit;
            font-size: 12px;
        }
        .search input:focus { outline: 2px solid var(--accent-subtle); }
        .title {
            font-size: 11px;
            color: var(--text-tertiary);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            margin: 14px 8px 6px;
        }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; padding: 0 4px; }
        .item {
            display: flex;
            align-items: center;
            gap: 7px;
            border: 1px solid var(--border-subtle);
            background: var(--bg-elevated);
            color: inherit;
            border-radius: var(--radius-md);
            padding: 8px;
            text-align: left;
            font-size: 12px;
            cursor: grab;
            min-width: 0;
            box-sizing: border-box;
        }
        .item span {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .item platform-icon { flex-shrink: 0; color: var(--text-tertiary); }
        .item:hover { border-color: var(--accent); background: var(--glass-solid-subtle); }
        .item:hover platform-icon { color: var(--accent); }
        .item:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .empty { padding: 14px 8px; color: var(--text-tertiary); font-size: 12px; }
    `];

    constructor() {
        super();
        this.query = '';
    }

    _groupLabel(group) {
        if (group === 'layout') return this.t('interface_editor.group_layout');
        if (group === 'content') return this.t('interface_editor.group_content');
        if (group === 'input') return this.t('interface_editor.group_input');
        if (group === 'action') return this.t('interface_editor.group_action');
        if (group === 'data') return this.t('interface_editor.group_data');
        return this.t('interface_editor.group_platform');
    }

    _locale() {
        return this.select((state) => state.i18n.locale).value === 'ru' ? 'ru' : 'en';
    }

    /** Human name of an entry; the type id stays in the tooltip for orientation. */
    _label(entry) {
        return entry.editor.label[this._locale()];
    }

    _items() {
        const query = this.query.trim().toLowerCase();
        const byGroup = new Map(FLOW_UI_EDITOR_GROUPS.map((group) => [group, []]));
        // Pseudo entries (Submit, Columns(N)) come from the catalog too, so chrome
        // never carries its own list of types, icons or names.
        const entries = [...flowUIPaletteComponentEntries(), ...FLOW_UI_PALETTE_PSEUDO_ENTRIES];
        for (const entry of entries) {
            if (query
                && !entry.type.toLowerCase().includes(query)
                && !this._label(entry).toLowerCase().includes(query)) {
                continue;
            }
            byGroup.get(entry.editor.group)?.push(entry);
        }
        return byGroup;
    }

    _dragStart(event, type) {
        event.dataTransfer.setData(FLOW_UI_DND_MIME, type);
        // `dragover` may read types but not values, and the canvas needs the type to
        // preview the exact drop cell with that component's default column span.
        event.dataTransfer.setData(`${FLOW_UI_DND_MIME}:${type.toLowerCase()}`, type);
        event.dataTransfer.effectAllowed = 'copy';
    }

    render() {
        const byGroup = this._items();
        const hasAny = [...byGroup.values()].some((items) => items.length > 0);
        return html`
            <div class="search">
                <input
                    type="search"
                    .value=${this.query}
                    placeholder=${this.t('interface_editor.palette_search')}
                    @input=${(event) => { this.query = event.target.value; }}
                >
            </div>
            ${hasAny ? FLOW_UI_EDITOR_GROUPS.map((group) => {
                const items = byGroup.get(group) || [];
                if (!items.length) return nothing;
                return html`
                    <div class="title">${this._groupLabel(group)}</div>
                    <div class="grid">${items.map((entry) => html`
                        <article
                            class="item"
                            role="button"
                            tabindex="0"
                            draggable="true"
                            title=${`${this._label(entry)} · ${entry.type}`}
                            @dragstart=${(event) => this._dragStart(event, entry.type)}
                            @click=${() => this.emit('component-add', { type: entry.type })}
                            @keydown=${(event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                    event.preventDefault();
                                    this.emit('component-add', { type: entry.type });
                                }
                            }}
                        >
                            <platform-icon name=${entry.editor.icon} size="14"></platform-icon>
                            <span>${this._label(entry)}</span>
                        </article>
                    `)}</div>
                `;
            }) : html`<div class="empty">${this.t('interface_editor.palette_empty')}</div>`}
        `;
    }
}

if (!customElements.get('flows-interface-palette')) {
    customElements.define('flows-interface-palette', FlowsInterfacePalette);
}

/**
 * Палитра «Добавить»: блоки грамматики из JSON Schema по группам, поиск, перетаскивание на холст
 * (payload ``application/x-flow-ui-block``) или клик — в выбранный контейнер, иначе в конец страницы.
 *
 * Событие: ``block-add {type, columns}``.
 */

import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { BLOCK_TYPE_MIME } from '@platform/lib/flow-ui/editor/drop-zones.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-modal-search-field.js';

const GROUP_ORDER = Object.freeze(['layout', 'content', 'input', 'action', 'data', 'platform', 'custom']);

export class FlowsInterfaceAddPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        catalog: { attribute: false },
        _query: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0; }
        .search { padding: 10px 12px 6px; }
        .groups { overflow: auto; padding: 4px 12px 16px; }
        .group-title { margin: 12px 0 6px; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-tertiary); }
        .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
        .item { display: flex; align-items: center; gap: 8px; margin: 0; padding: 8px 9px; border: 1px solid var(--border-subtle); border-radius: 10px; background: var(--glass-solid-subtle); color: var(--text-primary); font-size: 12.5px; text-align: left; cursor: grab; min-width: 0; user-select: none; }
        .item:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .item:hover { border-color: var(--accent); background: var(--glass-solid-medium); }
        .item:active { cursor: grabbing; }
        .item platform-icon { flex: none; color: var(--text-secondary); }
        .item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .empty { padding: 24px 12px; text-align: center; color: var(--text-tertiary); font-size: 12.5px; }
    `];

    constructor() {
        super();
        this.catalog = [];
        this._query = '';
    }

    /** Элементы палитры: каждый блок грамматики, а ``columns`` — как «Колонки 2» и «Колонки 3». */
    _items() {
        const items = [];
        for (const entry of this.catalog) {
            if (entry.type === 'columns') {
                items.push({ key: 'columns-2', type: 'columns', columns: 2, group: entry.group, icon: entry.icon, label: this.t('interface_editor.palette_columns', { count: 2 }) });
                items.push({ key: 'columns-3', type: 'columns', columns: 3, group: entry.group, icon: entry.icon, label: this.t('interface_editor.palette_columns', { count: 3 }) });
                continue;
            }
            items.push({ key: entry.type, type: entry.type, columns: null, group: entry.group, icon: entry.icon, label: this.t(`interface_editor.block_${entry.type}`) });
        }
        const query = this._query.trim().toLowerCase();
        return query === '' ? items : items.filter((item) => item.label.toLowerCase().includes(query) || item.type.includes(query));
    }

    _onDragStart(event, item) {
        event.dataTransfer.setData(BLOCK_TYPE_MIME, JSON.stringify({ type: item.type, columns: item.columns }));
        event.dataTransfer.effectAllowed = 'copy';
    }

    render() {
        const items = this._items();
        const groups = GROUP_ORDER.filter((group) => items.some((item) => item.group === group));
        return html`
            <div class="search">
                <platform-modal-search-field layout="fill" .value=${this._query} placeholder=${this.t('interface_editor.palette_search')}
                    @change=${(event) => { this._query = event.detail.value; }}></platform-modal-search-field>
            </div>
            <div class="groups">
                ${groups.length === 0 ? html`<div class="empty">${this.t('interface_editor.palette_empty')}</div>` : nothing}
                ${groups.map((group) => html`
                    <div class="group-title">${this.t(`interface_editor.group_${group}`)}</div>
                    <div class="grid">
                        ${items.filter((item) => item.group === group).map((item) => html`
                            <article role="button" tabindex="0" class="item" draggable="true" title=${item.label}
                                @dragstart=${(event) => this._onDragStart(event, item)}
                                @click=${() => this.emit('block-add', { type: item.type, columns: item.columns })}
                                @keydown=${(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this.emit('block-add', { type: item.type, columns: item.columns }); } }}>
                                <platform-icon name=${item.icon} size="15"></platform-icon><span>${item.label}</span>
                            </article>
                        `)}
                    </div>
                `)}
            </div>
        `;
    }
}

if (!customElements.get('flows-interface-add-panel')) customElements.define('flows-interface-add-panel', FlowsInterfaceAddPanel);

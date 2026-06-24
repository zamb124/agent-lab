/**
 * platform-file-table — таблица файлов с заголовком колонок и sortable headers.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

export class PlatformFileTable extends PlatformElement {
    static properties = {
        columns: { type: Array },
        sortKey: { type: String, attribute: 'sort-key' },
        sortDir: { type: String, attribute: 'sort-dir' },
        selectable: { type: Boolean, reflect: true },
        allSelected: { type: Boolean, attribute: 'all-selected' },
        ariaLabel: { type: String, attribute: 'aria-label' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-width: 0;
                min-height: 0;
            }
            .table-wrap {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                overflow: visible;
                background: var(--glass-solid-subtle);
            }
            .head-row {
                display: grid;
                grid-template-columns: var(--platform-file-row-columns, 2rem 1fr 6rem 8rem 8rem 6rem 2.5rem);
                gap: var(--space-3);
                align-items: center;
                min-height: 2.5rem;
                padding: 0 var(--space-3);
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--glass-border-medium);
            }
            .head-cell {
                font-size: var(--text-xs);
                font-weight: 600;
                color: var(--text-tertiary);
                text-align: left;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                min-width: 0;
            }
            .head-cell.sortable {
                cursor: pointer;
                user-select: none;
            }
            .head-cell.sortable:hover {
                color: var(--text-secondary);
            }
            .head-cell .sort-icon {
                margin-left: var(--space-1);
                vertical-align: middle;
                opacity: 0.5;
            }
            .head-cell.sorted .sort-icon {
                opacity: 1;
                color: var(--accent);
            }
            .body {
                display: block;
                flex: 1;
                min-width: 0;
                min-height: 0;
            }
            @media (max-width: 767px) {
                .head-row {
                    grid-template-columns: var(--platform-file-row-columns-mobile, 2rem 1fr 2.5rem);
                }
                .cell-hide-mobile {
                    display: none;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.columns = [];
        this.sortKey = 'updated_at';
        this.sortDir = 'desc';
        this.selectable = false;
        this.allSelected = false;
        this.ariaLabel = '';
    }

    _onSort(key) {
        if (typeof key !== 'string' || key.length === 0) {
            return;
        }
        let nextDir = 'asc';
        if (this.sortKey === key && this.sortDir === 'asc') {
            nextDir = 'desc';
        }
        this.emit('sort-change', { sortKey: key, sortDir: nextDir });
    }

    _onSelectAll(e) {
        this.emit('select-all-toggle', { selected: e.target.checked });
    }

    _renderHeaderCell(col) {
        const sortable = col.sortable === true && typeof col.key === 'string';
        const sorted = sortable && this.sortKey === col.key;
        const hideMobile = col.hideMobile === true ? 'cell-hide-mobile' : '';
        if (!sortable) {
            return html`
                <div class="head-cell ${hideMobile}" role="columnheader">${col.label}</div>
            `;
        }
        const icon = sorted
            ? (this.sortDir === 'asc' ? 'chevron-up' : 'chevron-down')
            : 'chevron-down';
        return html`
            <div
                class="head-cell sortable ${sorted ? 'sorted' : ''} ${hideMobile}"
                role="columnheader"
                @click=${() => this._onSort(col.key)}
            >
                ${col.label}
                <platform-icon class="sort-icon" name=${icon} size="12"></platform-icon>
            </div>
        `;
    }

    render() {
        const cols = Array.isArray(this.columns) ? this.columns : [];
        return html`
            <div class="table-wrap" role="grid" aria-label=${this.ariaLabel}>
                <div class="head-row" role="row">
                    <div class="head-cell checkbox-col" role="columnheader">
                        ${this.selectable ? html`
                            <input
                                type="checkbox"
                                .checked=${this.allSelected}
                                @change=${this._onSelectAll}
                                aria-label="Select all"
                            />
                        ` : ''}
                    </div>
                    ${cols.map((col) => this._renderHeaderCell(col))}
                    <div class="head-cell actions-col cell-hide-mobile" role="columnheader"></div>
                </div>
                <div class="body" role="rowgroup">
                    <slot></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-file-table', PlatformFileTable);

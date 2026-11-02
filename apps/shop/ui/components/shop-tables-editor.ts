/**
 * ShopTablesEditor — столы зала для заказа «в заведении».
 *
 * Каждая строка — метка стола («Стол 5», «У окна»), ссылка на его QR
 * (витрина откроется с предвыбранным типом «В заведении») и удаление.
 * Данные живут в ops `shop/tables_*`, владелец перезагружает список сам.
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

interface ShopTableRow {
    shop_table_id: string;
    label: string;
}

export class ShopTablesEditor extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        shopId: { type: String, attribute: 'shop-id' },
        shopSlug: { type: String, attribute: 'shop-slug' },
        _tables: { state: true },
        _newLabel: { state: true },
    };

    declare shopId: string;
    declare shopSlug: string;
    declare _tables: ShopTableRow[];
    declare _newLabel: string;

    private _listOp: OpController;
    private _createOp: OpController;
    private _removeOp: OpController;

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; gap: var(--space-3); }
            .tables { display: flex; flex-direction: column; }
            .table-row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) 0;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .table-row + .table-row {
                border-top: 1px solid color-mix(in srgb, var(--text-primary) 6%, transparent);
            }
            .table-label { flex: 1; min-width: 0; }
            .icon-btn {
                border: 0;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border-radius: var(--radius-sm);
                padding: 0;
                text-decoration: none;
            }
            .icon-btn:hover { color: var(--accent); }
            .icon-btn.danger:hover { color: var(--danger); }
            .add-row { display: flex; gap: var(--space-3); align-items: center; }
            .add-row > platform-field { flex: 1; min-width: 0; }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.5; }
        `,
    ];

    constructor() {
        super();
        this.shopId = '';
        this.shopSlug = '';
        this._tables = [];
        this._newLabel = '';
        this._listOp = this.useOp('shop/tables_list');
        this._createOp = this.useOp('shop/table_create');
        this._removeOp = this.useOp('shop/table_remove');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._load();
    }

    private async _load(): Promise<void> {
        if (this.shopId === '') return;
        const result = await this._listOp.run({ shop_id: this.shopId });
        const items = result !== null && typeof result === 'object'
            ? (result as { items?: unknown }).items
            : undefined;
        this._tables = Array.isArray(items) ? (items as ShopTableRow[]) : [];
    }

    private _tableQrUrl(tableId: string): string {
        return `/shop/api/v1/public/storefront/${encodeURIComponent(this.shopSlug)}/tables/${encodeURIComponent(tableId)}/qr.svg`;
    }

    private async _add() {
        const label = this._newLabel.trim();
        if (label === '') return;
        const result = await this._createOp.run({ shop_id: this.shopId, label });
        if (result !== null) {
            this._newLabel = '';
            await this._load();
        }
    }

    private async _remove(table: ShopTableRow) {
        const result = await this._removeOp.run({
            shop_id: this.shopId,
            shop_table_id: table.shop_table_id,
        });
        if (result !== null) await this._load();
    }

    override render(): TemplateResult {
        return html`
            <div class="hint">${this.t('settings.tables_hint')}</div>
            ${this._tables.length > 0
                ? html`
                    <div class="tables">
                        ${this._tables.map((table) => html`
                            <div class="table-row">
                                <platform-icon name="qr-code" size="15"></platform-icon>
                                <span class="table-label">${table.label}</span>
                                <a class="icon-btn" href=${this._tableQrUrl(table.shop_table_id)}
                                    download=${`table-qr-${encodeURIComponent(table.label)}.svg`}
                                    title=${this.t('settings.table_qr')}>
                                    <platform-icon name="download" size="14"></platform-icon>
                                </a>
                                <button class="icon-btn danger" title=${this.t('settings.table_remove')}
                                    @click=${() => this._remove(table)}>
                                    <platform-icon name="trash" size="14"></platform-icon>
                                </button>
                            </div>
                        `)}
                    </div>`
                : html`<div class="hint">${this.t('settings.tables_empty')}</div>`}
            <div class="add-row">
                <platform-field type="string" mode="edit" label=${this.t('settings.field_table')} .value=${this._newLabel}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._newLabel = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-button size="sm" variant="secondary" ?busy=${this._createOp.busy}
                    ?disabled=${this._newLabel.trim() === ''} @click=${() => this._add()}>
                    ${this.t('settings.table_add')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('shop-tables-editor', ShopTablesEditor);

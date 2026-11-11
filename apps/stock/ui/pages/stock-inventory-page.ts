/**
 * «Инвентаризация» — ячейки к пересчёту (`stock/locations_count_due`,
 * подсветка просрочки), выбор ячейки → её quants с колонкой «Факт»,
 * запись через `stock/quant_inventory_set` и применение разницы
 * `stock/quant_inventory_apply`.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import type { StockLocation, StockQuant } from '@platform/lib/events/wire/stock.gen.js';
import { usageIcon } from '../_helpers/stock-location-tree.js';
import '@platform/lib/components/platform-resizable-split.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';

export class StockInventoryPage extends PlatformPage {
    static override properties = {
        _warehouseId: { state: true },
        _selectedId: { state: true },
        _counts: { state: true },
    };
    declare private _warehouseId: string;
    declare private _selectedId: string;
    declare private _counts: Map<string, string>;

    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow: hidden; }
            .side { display: flex; flex-direction: column; height: 100%; padding: var(--space-3); gap: var(--space-2); overflow-y: auto; }
            .due { padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); cursor: pointer; font-size: var(--text-sm); color: var(--text-primary); display: flex; align-items: center; gap: var(--space-2); }
            .due:hover { background: var(--surface-2); }
            .due.active { background: var(--accent-primary-bg, var(--surface-2)); font-weight: var(--font-medium); }
            .due .days { margin-left: auto; font-size: var(--text-xs); color: var(--color-danger-text, #a02622); }
            .main { height: 100%; overflow-y: auto; padding: var(--space-5); }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); margin-top: var(--space-3); }
            th, td { padding: var(--space-2) var(--space-3); text-align: left; border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
            .hint { color: var(--text-tertiary); margin-top: var(--space-6); text-align: center; }
            .section { color: var(--text-tertiary); font-size: var(--text-xs); text-transform: uppercase; letter-spacing: 0.05em; margin: var(--space-2) 0; }
            platform-field { min-width: 110px; }
        `,
    ];

    private _due: OpController;
    private _quants: ResourceController;
    private _setOp: OpController;
    private _applyOp: OpController;
    private _warehouses: ResourceController;
    private _products: ResourceController;

    constructor() {
        super();
        this._warehouseId = '';
        this._selectedId = '';
        this._counts = new Map();
        this._due = this.useOp('stock/locations_count_due');
        this._quants = this.useResource('stock/quants');
        this._setOp = this.useOp('stock/quant_inventory_set');
        this._applyOp = this.useOp('stock/quant_inventory_apply');
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._products = this.useResource('stock/products', { autoload: true });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._reloadDue();
    }

    private _reloadDue() {
        this._due.run(this._warehouseId !== '' ? { warehouse_id: this._warehouseId } : { warehouse_id: this._firstWarehouseId() });
    }

    private _firstWarehouseId(): string {
        const w = this._warehouses.items.find(isPlainRecord);
        return w !== undefined && typeof w.warehouse_id === 'string' ? w.warehouse_id : '';
    }

    private _dueItems(): StockLocation[] {
        const result = this._due.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isPlainRecord) as unknown as StockLocation[];
    }

    private _daysOverdue(loc: StockLocation): number | null {
        if (typeof loc.last_count_at !== 'string' || loc.last_count_at === '') return null;
        const days = Math.floor((Date.now() - Date.parse(loc.last_count_at)) / 86_400_000);
        return days;
    }

    private _select(id: string) {
        this._selectedId = id;
        this._counts = new Map();
        if (id !== '') this._quants.load({ location_id: id });
    }

    private _quantsFor(): StockQuant[] {
        return this._quants.items.filter(isPlainRecord) as unknown as StockQuant[];
    }

    private _productName(id: string): string {
        const row = this._products.items.find((r) => isPlainRecord(r) && r.product_id === id);
        if (!isPlainRecord(row)) return id;
        return typeof row.name === 'string' && row.name !== '' ? row.name : id;
    }

    private _setCount(q: StockQuant) {
        const raw = this._counts.get(q.quant_id);
        if (raw === undefined || raw.trim() === '') return;
        const n = Number(raw);
        if (!Number.isFinite(n)) return;
        this._setOp.run({ quant_id: q.quant_id, inventory_quantity: n });
    }

    private async _applyAll() {
        const ok = await platformConfirm(this.t('inventory.confirm_apply'), { confirmText: this.t('inventory.apply') });
        if (ok !== true) return;
        for (const q of this._quantsFor()) {
            const raw = this._counts.get(q.quant_id);
            if (raw !== undefined && raw.trim() !== '' && Number.isFinite(Number(raw))) {
                await this._setOp.run({ quant_id: q.quant_id, inventory_quantity: Number(raw) });
            }
        }
        for (const q of this._quantsFor()) {
            if (q.inventory_quantity !== null && q.inventory_quantity !== undefined) {
                await this._applyOp.run({ quant_id: q.quant_id });
            }
        }
    }

    private _renderSide() {
        const whOptions = this._warehouses.items.filter(isPlainRecord).map((w) => ({ value: w.warehouse_id as string, label: w.name as string }));
        const due = this._dueItems();
        return html`
            <platform-searchable-combobox
                .label=${this.t('report.warehouse')}
                .value=${this._warehouseId}
                .options=${whOptions}
                @change=${(e: CustomEvent) => {
                    this._warehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                    this._reloadDue();
                }}
            ></platform-searchable-combobox>
            <div class="section">${this.t('inventory.due_section')}</div>
            ${due.length === 0
                ? html`<platform-empty-state .message=${this.t('inventory.empty_due')}></platform-empty-state>`
                : due.map((l) => {
                    const days = this._daysOverdue(l);
                    return html`
                        <div class="due ${l.location_id === this._selectedId ? 'active' : ''}" @click=${() => this._select(l.location_id)}>
                            <platform-icon name=${usageIcon(l.usage)} size="16"></platform-icon>
                            ${l.complete_name || l.name}
                            ${days !== null ? html`<span class="days">${this.t('inventory.due_days', { days })}</span>` : ''}
                        </div>
                    `;
                })}
        `;
    }

    private _renderMain() {
        if (this._selectedId === '') return html`<div class="hint">${this.t('inventory.select_hint')}</div>`;
        const quants = this._quantsFor();
        return html`
            ${quants.length === 0
                ? html`<platform-empty-state .message=${this.t('explorer.empty_contents')}></platform-empty-state>`
                : html`<table><thead><tr>
                    <th>${this.t('report.col_product')}</th>
                    <th>${this.t('explorer.col_lot')}</th>
                    <th class="num">${this.t('explorer.col_qty')}</th>
                    <th class="num">${this.t('inventory.fact')}</th>
                    <th></th>
                </tr></thead><tbody>
                    ${quants.map((q) => html`<tr>
                        <td>${this._productName(q.product_id)}</td>
                        <td>${q.lot_id ?? '—'}</td>
                        <td class="num">${q.quantity}</td>
                        <td class="num">
                            <platform-field
                                type="number" mode="edit"
                                .value=${this._counts.get(q.quant_id) ?? (q.inventory_quantity !== null && q.inventory_quantity !== undefined ? String(q.inventory_quantity) : '')}
                                data-count-input
                                @change=${(e: CustomEvent) => {
                                    const next = new Map(this._counts);
                                    next.set(q.quant_id, String(e.detail.value ?? ''));
                                    this._counts = next;
                                }}
                            ></platform-field>
                        </td>
                        <td><platform-button variant="secondary" density="compact"
                            @click=${() => this._setCount(q)}
                        ><platform-icon name="check" size="14"></platform-icon> ${this.t('inventory.set_count')}</platform-button></td>
                    </tr>`)}
                </tbody></table>
                <div style="margin-top: var(--space-3)">
                    <platform-button variant="primary" ?loading=${this._applyOp.busy} @click=${() => this._applyAll()}>
                        <platform-icon name="check" size="14"></platform-icon> ${this.t('inventory.apply')}
                    </platform-button>
                </div>`}
        `;
    }

    override render() {
        return html`
            <platform-resizable-split storage-key="inventory" storage-scope="stock" min-size="240" max-size="420">
                <div class="side" slot="side">${this._renderSide()}</div>
                <div class="main">${this._renderMain()}</div>
            </platform-resizable-split>
        `;
    }
}

customElements.define('stock-inventory-page', StockInventoryPage);

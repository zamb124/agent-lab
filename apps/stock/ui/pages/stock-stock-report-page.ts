/**
 * «Остатки по локациям» — Odoo-style отчёт: quants склада, сгруппированные
 * склад → зона → строки или товар → строки локаций, сворачиваемые группы
 * с субсуммами qty/reserved/available, опционально пустые ячейки.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { groupQuants } from '../_helpers/stock-location-tree.js';
import type { StockLocation, StockQuant } from '@platform/lib/events/wire/stock.gen.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';

type GroupMode = 'location' | 'product';

interface GroupBlock {
    key: string;
    label: string;
    rows: StockQuant[];
    qty: number;
    reserved: number;
    available: number;
}

export class StockStockReportPage extends PlatformPage {
    static override properties = {
        _warehouseId: { state: true },
        _productId: { state: true },
        _mode: { state: true },
        _includeEmpty: { state: true },
        _collapsed: { state: true },
    };
    declare private _warehouseId: string;
    declare private _productId: string;
    declare private _mode: GroupMode;
    declare private _includeEmpty: boolean;
    declare private _collapsed: Set<string>;

    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1200px; margin: 0 auto; padding: var(--space-5); }
            .toolbar { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; margin-bottom: var(--space-4); }
            .toolbar platform-searchable-combobox { min-width: 220px; }
            .toggle { display: inline-flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--text-secondary); cursor: pointer; }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td { padding: var(--space-2) var(--space-3); text-align: left; border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
            tr.group { cursor: pointer; background: var(--surface-2); font-weight: var(--font-medium); }
            tr.group td { padding: var(--space-3); }
            tr.subtotal td { color: var(--text-secondary); font-style: italic; border-top: 1px dashed var(--glass-border-subtle); }
            tr.total td { font-weight: var(--font-semibold); border-top: 2px solid var(--glass-border-subtle); }
            a.link { color: var(--accent-primary); cursor: pointer; text-decoration: none; }
        `,
    ];

    private _quants: ResourceController;
    private _locations: ResourceController;
    private _warehouses: ResourceController;
    private _products: ResourceController;

    constructor() {
        super();
        this._warehouseId = '';
        this._productId = '';
        this._mode = 'location';
        this._includeEmpty = false;
        this._collapsed = new Set();
        this._quants = this.useResource('stock/quants');
        this._locations = this.useResource('stock/locations', { autoload: true });
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._products = this.useResource('stock/products', { autoload: true });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const search = new URLSearchParams(window.location.search);
        const productId = search.get('product_id');
        if (productId !== null && productId !== '') this._productId = productId;
        this._load();
    }

    private _load() {
        const query: Record<string, unknown> = { limit: 500 };
        if (this._warehouseId !== '') query.warehouse_id = this._warehouseId;
        if (this._productId !== '') query.product_id = this._productId;
        this._quants.load(query);
    }

    private _locationById(): Map<string, StockLocation> {
        const map = new Map<string, StockLocation>();
        for (const row of this._locations.items) {
            if (isPlainRecord(row) && typeof row.location_id === 'string') {
                map.set(row.location_id, row as unknown as StockLocation);
            }
        }
        return map;
    }

    private _productName(productId: string): string {
        const row = this._products.items.find((r) => isPlainRecord(r) && r.product_id === productId);
        if (!isPlainRecord(row)) return productId;
        return typeof row.name === 'string' && row.name !== '' ? row.name : productId;
    }

    private _locationName(id: string): string {
        const loc = this._locationById().get(id);
        return loc === undefined ? id : (loc.complete_name || loc.name);
    }

    private _groups(quants: StockQuant[]): GroupBlock[] {
        const byLocation = this._mode === 'location';
        return groupQuants(quants, (q) => byLocation ? q.location_id : q.product_id)
            .map((g) => ({
                key: g.key,
                label: byLocation ? this._locationName(g.key) : this._productName(g.key),
                rows: g.items, qty: g.qty, reserved: g.reserved, available: g.available,
            }))
            .sort((a, b) => a.label.localeCompare(b.label));
    }

    private _emptyBinRows(locById: Map<string, StockLocation>): GroupBlock[] {
        const withQuants = new Set(this._quants.items.filter(isPlainRecord).map((q) => q.location_id));
        const bins = [...locById.values()].filter((l) =>
            (l.usage === 'bin' || l.usage === 'container')
            && !withQuants.has(l.location_id)
            && (this._warehouseId === '' || l.warehouse_id === this._warehouseId)
            && l.is_active !== false);
        return bins.map((b) => ({
            key: `empty:${b.location_id}`,
            label: b.complete_name || b.name,
            rows: [], qty: 0, reserved: 0, available: 0,
        }));
    }

    private _renderToolbar() {
        const whOptions = this._warehouses.items.filter(isPlainRecord).map((w) => ({
            value: w.warehouse_id as string, label: w.name as string,
        }));
        const prodOptions = this._products.items.filter(isPlainRecord).map((p) => ({
            value: p.product_id as string,
            label: typeof p.name === 'string' && p.name !== '' ? p.name : (p.product_id as string),
        }));
        return html`
            <div class="toolbar">
                <platform-searchable-combobox
                    .label=${this.t('report.warehouse')}
                    .placeholder=${this.t('report.all_warehouses')}
                    .value=${this._warehouseId}
                    .options=${[{ value: '', label: this.t('report.all_warehouses') }, ...whOptions]}
                    @change=${(e: CustomEvent) => {
                        this._warehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._load();
                    }}
                ></platform-searchable-combobox>
                <platform-searchable-combobox
                    .label=${this.t('report.product')}
                    .placeholder=${this.t('report.all_products')}
                    .value=${this._productId}
                    .options=${[{ value: '', label: this.t('report.all_products') }, ...prodOptions]}
                    @change=${(e: CustomEvent) => {
                        this._productId = typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._load();
                    }}
                ></platform-searchable-combobox>
                <platform-segmented-control
                    density="compact"
                    .value=${this._mode}
                    .items=${[
                        { value: 'location', label: this.t('report.group_location') },
                        { value: 'product', label: this.t('report.group_product') },
                    ]}
                    @change=${(e: CustomEvent) => { this._mode = e.detail.value === 'product' ? 'product' : 'location'; }}
                ></platform-segmented-control>
                <label class="toggle">
                    <input type="checkbox" ?checked=${this._includeEmpty}
                        @change=${(e: Event) => { this._includeEmpty = (e.target as HTMLInputElement).checked; }} />
                    ${this.t('report.include_empty')}
                </label>
            </div>
        `;
    }

    private _renderRow(q: StockQuant) {
        const locCell = this._mode === 'product'
            ? html`<td><a class="link" @click=${() => this.navigate('stock_location', { locationId: q.location_id })}>${this._locationName(q.location_id)}</a></td>`
            : '';
        const prodCell = this._mode === 'location'
            ? html`<td>${this._productName(q.product_id)}</td>`
            : '';
        return html`<tr>
            ${locCell}${prodCell}
            <td>${q.lot_id ?? '—'}</td>
            <td>${q.owner_entity_id ?? '—'}</td>
            <td class="num">${q.quantity}</td>
            <td class="num">${q.reserved_quantity}</td>
            <td class="num">${Number(q.quantity) - Number(q.reserved_quantity)}</td>
        </tr>`;
    }

    override render() {
        const locById = this._locationById();
        const quants = this._quants.items.filter(isPlainRecord) as unknown as StockQuant[];
        const groups = this._groups(quants);
        const allGroups = this._includeEmpty ? [...groups, ...this._emptyBinRows(locById)] : groups;
        const totals = allGroups.reduce((s, g) => ({ qty: s.qty + g.qty, res: s.res + g.reserved, av: s.av + g.available }), { qty: 0, res: 0, av: 0 });
        return html`
            <div class="wrap">
                <h1 style="margin: 0 0 var(--space-4); font-size: var(--text-2xl); color: var(--text-primary);">${this.t('report.title')}</h1>
                ${this._renderToolbar()}
                ${allGroups.length === 0
                    ? html`<platform-empty-state .message=${this.t('report.empty')}></platform-empty-state>`
                    : html`<table><thead><tr>
                        ${this._mode === 'product' ? html`<th>${this.t('report.col_location')}</th>` : html`<th>${this.t('report.col_product')}</th>`}
                        <th>Lot</th><th>Owner</th>
                        <th class="num">${this.t('report.col_qty')}</th>
                        <th class="num">${this.t('report.col_reserved')}</th>
                        <th class="num">${this.t('report.col_available')}</th>
                    </tr></thead><tbody>
                        ${allGroups.map((g) => {
                            const open = !this._collapsed.has(g.key);
                            return html`
                                <tr class="group" @click=${() => {
                                    const next = new Set(this._collapsed);
                                    if (open) next.add(g.key); else next.delete(g.key);
                                    this._collapsed = next;
                                }}>
                                    <td colspan="3">
                                        <platform-icon name=${open ? 'chevron-down' : 'chevron-right'} size="14"></platform-icon>
                                        ${g.label}
                                    </td>
                                    <td class="num">${g.qty}</td>
                                    <td class="num">${g.reserved}</td>
                                    <td class="num">${g.available}</td>
                                </tr>
                                ${open ? g.rows.map((q) => this._renderRow(q)) : ''}
                            `;
                        })}
                        <tr class="total">
                            <td colspan="3">${this.t('report.total')}</td>
                            <td class="num">${totals.qty}</td>
                            <td class="num">${totals.res}</td>
                            <td class="num">${totals.av}</td>
                        </tr>
                    </tbody></table>`}
            </div>
        `;
    }
}

customElements.define('stock-stock-report-page', StockStockReportPage);

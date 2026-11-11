/**
 * «Тара и контейнеры» — список контейнеров (`usage=container`) слева,
 * карточка тары справа: тип, текущее место, содержимое (quants + вложенная
 * тара) из `stock/containers/item`, действие «Переместить».
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { StockLocation, StockQuant } from '@platform/lib/events/wire/stock.gen.js';
import { usageIcon } from '../_helpers/stock-location-tree.js';
import '@platform/lib/components/platform-resizable-split.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

export class StockPackagesPage extends PlatformPage {
    static override properties = {
        _selectedId: { state: true },
        _warehouseId: { state: true },
        _moveOpen: { state: true },
        _moveDest: { state: true },
    };
    declare private _selectedId: string;
    declare private _warehouseId: string;
    declare private _moveOpen: boolean;
    declare private _moveDest: string;

    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow: hidden; }
            .side { display: flex; flex-direction: column; height: 100%; padding: var(--space-3); gap: var(--space-2); overflow-y: auto; }
            .pkg { padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); cursor: pointer; font-size: var(--text-sm); color: var(--text-primary); display: flex; align-items: center; gap: var(--space-2); }
            .pkg:hover { background: var(--surface-2); }
            .pkg.active { background: var(--accent-primary-bg, var(--surface-2)); font-weight: var(--font-medium); }
            .pkg .where { color: var(--text-tertiary); font-size: var(--text-xs); margin-left: auto; }
            .main { height: 100%; overflow-y: auto; padding: var(--space-5); }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); margin-top: var(--space-3); }
            th, td { padding: var(--space-2) var(--space-3); text-align: left; border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
            .hint { color: var(--text-tertiary); margin-top: var(--space-6); text-align: center; }
            .move-bar { display: flex; gap: var(--space-2); align-items: center; margin-top: var(--space-3); padding: var(--space-3); border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-md); }
            .move-bar platform-searchable-combobox { flex: 1; }
            .meta { color: var(--text-secondary); font-size: var(--text-sm); display: flex; gap: var(--space-4); flex-wrap: wrap; }
        `,
    ];

    private _containers: OpController;
    private _item: OpController;
    private _moveOp: OpController;
    private _locations: ResourceController;
    private _warehouses: ResourceController;
    private _products: ResourceController;

    constructor() {
        super();
        this._selectedId = '';
        this._warehouseId = '';
        this._moveOpen = false;
        this._moveDest = '';
        this._containers = this.useOp('stock/containers_list');
        this._item = this.useOp('stock/container_item');
        this._moveOp = this.useOp('stock/container_move');
        this._locations = this.useResource('stock/locations', { autoload: true });
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._products = this.useResource('stock/products', { autoload: true });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._containers.run({});
    }

    private _containerItems(): StockLocation[] {
        const result = this._containers.lastResult;
        if (!isPlainRecord(result) || !Array.isArray(result.items)) return [];
        return result.items.filter(isPlainRecord) as unknown as StockLocation[];
    }

    private _locationName(id: string | null | undefined): string {
        if (id === null || id === undefined || id === '') return '—';
        const row = this._locations.items.find((r) => isPlainRecord(r) && r.location_id === id);
        if (!isPlainRecord(row)) return id;
        const loc = row as unknown as StockLocation;
        return loc.complete_name || loc.name;
    }

    private _productName(id: string): string {
        const row = this._products.items.find((r) => isPlainRecord(r) && r.product_id === id);
        if (!isPlainRecord(row)) return id;
        return typeof row.name === 'string' && row.name !== '' ? row.name : id;
    }

    private _select(id: string) {
        this._selectedId = id;
        if (id !== '') this._item.run({ container_id: id });
    }

    private _contents(): { quants: StockQuant[]; nested: StockLocation[] } {
        const result = this._item.lastResult;
        if (!isPlainRecord(result)) return { quants: [], nested: [] };
        const quants = Array.isArray(result.quants) ? result.quants.filter(isPlainRecord) as unknown as StockQuant[] : [];
        const nested = Array.isArray(result.children) ? result.children.filter(isPlainRecord) as unknown as StockLocation[] : [];
        return { quants, nested };
    }

    private _renderSide() {
        const whOptions = this._warehouses.items.filter(isPlainRecord).map((w) => ({ value: w.warehouse_id as string, label: w.name as string }));
        const containers = this._containerItems().filter((c) => this._warehouseId === '' || c.warehouse_id === this._warehouseId);
        return html`
            <platform-searchable-combobox
                .label=${this.t('report.warehouse')}
                .value=${this._warehouseId}
                .options=${[{ value: '', label: this.t('report.all_warehouses') }, ...whOptions]}
                @change=${(e: CustomEvent) => { this._warehouseId = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
            ></platform-searchable-combobox>
            ${containers.length === 0
                ? html`<platform-empty-state .message=${this.t('packages.empty')}></platform-empty-state>`
                : containers.map((c) => html`
                    <div class="pkg ${c.location_id === this._selectedId ? 'active' : ''}" @click=${() => this._select(c.location_id)}>
                        <platform-icon name="box" size="16"></platform-icon>
                        ${c.name}
                        <span class="where">${this._locationName(c.parent_id)}</span>
                    </div>
                `)}
        `;
    }

    private _renderMain() {
        if (this._selectedId === '') return html`<div class="hint">${this.t('packages.select_hint')}</div>`;
        const c = this._containerItems().find((x) => x.location_id === this._selectedId);
        const { quants, nested } = this._contents();
        const locOptions = this._locations.items.filter(isPlainRecord)
            .map((r) => r as unknown as StockLocation)
            .filter((l) => l.usage === 'view' || l.usage === 'bin')
            .map((l) => ({ value: l.location_id, label: l.complete_name || l.name }));
        return html`
            <h1 style="margin: 0 0 var(--space-3); font-size: var(--text-xl); color: var(--text-primary);">
                <platform-icon name="box" size="20"></platform-icon> ${c?.name ?? this._selectedId}
            </h1>
            <div class="meta">
                <span>${this.t('packages.current_location')}: ${this._locationName(c?.parent_id)}</span>
            </div>
            <div style="margin-top: var(--space-3); display:flex; gap: var(--space-2);">
                <platform-button variant="secondary" density="compact" @click=${() => { this._moveOpen = !this._moveOpen; }}>
                    <platform-icon name="truck" size="14"></platform-icon> ${this.t('packages.move')}
                </platform-button>
            </div>
            ${this._moveOpen ? html`
                <div class="move-bar">
                    <platform-searchable-combobox
                        .label=${this.t('packages.move_dest')}
                        .value=${this._moveDest}
                        .options=${locOptions}
                        @change=${(e: CustomEvent) => { this._moveDest = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                    ></platform-searchable-combobox>
                    <platform-button variant="primary" ?disabled=${this._moveDest === ''} ?loading=${this._moveOp.busy}
                        @click=${() => { this._moveOp.run({ container_id: this._selectedId, dest_location_id: this._moveDest }); this._moveOpen = false; }}>
                        <platform-icon name="truck" size="14"></platform-icon> ${this.t('packages.move')}
                    </platform-button>
                </div>
            ` : ''}
            <h2 style="font-size: var(--text-base); color: var(--text-secondary); margin: var(--space-4) 0 0;">${this.t('packages.contents')}</h2>
            ${quants.length === 0 && nested.length === 0
                ? html`<platform-empty-state .message=${this.t('packages.empty_contents')}></platform-empty-state>`
                : html`<table><thead><tr>
                    <th>${this.t('report.col_product')}</th>
                    <th class="num">${this.t('report.col_qty')}</th>
                    <th class="num">${this.t('report.col_reserved')}</th>
                </tr></thead><tbody>
                    ${quants.map((q) => html`<tr>
                        <td>${this._productName(q.product_id)}</td>
                        <td class="num">${q.quantity}</td>
                        <td class="num">${q.reserved_quantity}</td>
                    </tr>`)}
                    ${nested.map((n) => html`<tr>
                        <td colspan="3"><platform-icon name=${usageIcon(n.usage)} size="14"></platform-icon> ${n.name} <span style="color:var(--text-tertiary)">(${this.t('packages.nested')})</span></td>
                    </tr>`)}
                </tbody></table>`}
        `;
    }

    override render() {
        return html`
            <platform-resizable-split storage-key="packages" storage-scope="stock" min-size="220" max-size="420">
                <div class="side" slot="side">${this._renderSide()}</div>
                <div class="main">${this._renderMain()}</div>
            </platform-resizable-split>
        `;
    }
}

customElements.define('stock-packages-page', StockPackagesPage);

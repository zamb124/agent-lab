/**
 * «Движения» — журнал StockMove: фильтры склад/локация(+поддерево)/товар/
 * состояние, курсорная лента `stock/moves` с «Показать ещё», deep-links
 * `?location_id=` / `?product_id=` из эксплорера и отчёта.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { CursorListController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { StockLocation, StockMove } from '@platform/lib/events/wire/stock.gen.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-empty-state.js';

const STATES = ['all', 'draft', 'confirmed', 'assigned', 'done', 'cancel'] as const;

export class StockMovesPage extends PlatformPage {
    static override properties = {
        _state: { state: true },
        _subtree: { state: true },
    };
    declare private _state: string;
    declare private _subtree: boolean;

    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1200px; margin: 0 auto; padding: var(--space-5); }
            .toolbar { display: flex; gap: var(--space-3); align-items: center; flex-wrap: wrap; margin-bottom: var(--space-4); }
            .toolbar platform-searchable-combobox { min-width: 200px; }
            .toggle { display: inline-flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--text-secondary); cursor: pointer; }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td { padding: var(--space-2) var(--space-3); text-align: left; border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
            .badge { padding: 2px 8px; border-radius: var(--radius-full); font-size: var(--text-xs); background: var(--surface-2); color: var(--text-secondary); }
            .badge.done { background: var(--color-success-bg, #d4edda); color: var(--color-success-text, #1e7e34); }
            .badge.cancel { background: var(--color-danger-bg, #f8d7da); color: var(--color-danger-text, #a02622); }
            .more { display: block; margin: var(--space-4) auto; padding: var(--space-2) var(--space-5); border-radius: var(--radius-md); border: 1px solid var(--glass-border-subtle); background: var(--surface-1); color: var(--text-primary); cursor: pointer; }
            a.link { color: var(--accent-primary); cursor: pointer; text-decoration: none; }
        `,
    ];

    private _moves: CursorListController<StockMove>;
    private _locations: ResourceController;
    private _warehouses: ResourceController;
    private _products: ResourceController;

    constructor() {
        super();
        this._state = 'all';
        this._subtree = false;
        this._moves = this.useCursorList('stock/moves');
        this._locations = this.useResource('stock/locations', { autoload: true });
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._products = this.useResource('stock/products', { autoload: true });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const search = new URLSearchParams(window.location.search);
        const filters: Record<string, unknown> = {};
        for (const key of ['location_id', 'product_id', 'warehouse_id']) {
            const v = search.get(key);
            if (v !== null && v !== '') filters[key] = v;
        }
        this._moves.load(filters);
    }

    private _apply(patch: Record<string, unknown>) {
        const next = { ...this._moves.filters, ...patch };
        if (this._state !== 'all') next.state = this._state; else delete next.state;
        next.subtree = this._subtree;
        this._moves.load(next);
    }

    private _productName(id: string): string {
        const row = this._products.items.find((r) => isPlainRecord(r) && r.product_id === id);
        if (!isPlainRecord(row)) return id;
        return typeof row.name === 'string' && row.name !== '' ? row.name : id;
    }

    private _locationName(id: string | null): string {
        if (id === null) return '';
        const row = this._locations.items.find((r) => isPlainRecord(r) && r.location_id === id);
        if (!isPlainRecord(row)) return id;
        const loc = row as unknown as StockLocation;
        return loc.complete_name || loc.name;
    }

    private _combo(items: readonly unknown[], idField: string): { value: string; label: string }[] {
        return items.filter(isPlainRecord).map((r) => ({
            value: r[idField] as string,
            label: (typeof r.complete_name === 'string' && r.complete_name !== '' ? r.complete_name : r.name) as string,
        }));
    }

    override render() {
        const f = this._moves.filters;
        const str = (k: string) => (typeof f[k] === 'string' ? (f[k] as string) : '');
        return html`
            <div class="wrap">
                <h1 style="margin: 0 0 var(--space-4); font-size: var(--text-2xl); color: var(--text-primary);">${this.t('moves.title')}</h1>
                <div class="toolbar">
                    <platform-searchable-combobox
                        .label=${this.t('report.warehouse')}
                        .value=${str('warehouse_id')}
                        .options=${[{ value: '', label: this.t('report.all_warehouses') }, ...this._combo(this._warehouses.items, 'warehouse_id')]}
                        @change=${(e: CustomEvent) => this._apply({ warehouse_id: typeof e.detail.value === 'string' && e.detail.value !== '' ? e.detail.value : null })}
                    ></platform-searchable-combobox>
                    <platform-searchable-combobox
                        .label=${this.t('moves.location')}
                        .value=${str('location_id')}
                        .options=${[{ value: '', label: '—' }, ...this._combo(this._locations.items, 'location_id')]}
                        @change=${(e: CustomEvent) => this._apply({ location_id: typeof e.detail.value === 'string' && e.detail.value !== '' ? e.detail.value : null })}
                    ></platform-searchable-combobox>
                    <platform-searchable-combobox
                        .label=${this.t('report.product')}
                        .value=${str('product_id')}
                        .options=${[{ value: '', label: this.t('report.all_products') }, ...this._combo(this._products.items, 'product_id')]}
                        @change=${(e: CustomEvent) => this._apply({ product_id: typeof e.detail.value === 'string' && e.detail.value !== '' ? e.detail.value : null })}
                    ></platform-searchable-combobox>
                    <platform-segmented-control
                        density="compact"
                        .value=${this._state}
                        .items=${STATES.map((s) => ({ value: s, label: this.t(`moves.state_${s}`) }))}
                        @change=${(e: CustomEvent) => {
                            this._state = typeof e.detail.value === 'string' ? e.detail.value : 'all';
                            this._apply({});
                        }}
                    ></platform-segmented-control>
                    <label class="toggle">
                        <input type="checkbox" ?checked=${this._subtree}
                            @change=${(e: Event) => { this._subtree = (e.target as HTMLInputElement).checked; this._apply({}); }} />
                        ${this.t('moves.include_subtree')}
                    </label>
                </div>
                ${this._moves.items.length === 0 && !this._moves.loading
                    ? html`<platform-empty-state .message=${this.t('moves.empty')}></platform-empty-state>`
                    : html`<table><thead><tr>
                        <th>${this.t('moves.col_date')}</th>
                        <th>${this.t('moves.col_product')}</th>
                        <th>${this.t('moves.col_from_to')}</th>
                        <th class="num">${this.t('moves.col_qty')}</th>
                        <th>${this.t('moves.col_state')}</th>
                        <th>${this.t('moves.col_transfer')}</th>
                    </tr></thead><tbody>
                        ${this._moves.items.map((m) => html`<tr>
                            <td>${String(m.date).slice(0, 16).replace('T', ' ')}</td>
                            <td>${this._productName(m.product_id)}</td>
                            <td>${this._locationName(m.location_id)} → ${this._locationName(m.location_dest_id)}</td>
                            <td class="num">${m.product_qty}</td>
                            <td><span class="badge ${m.state === 'done' ? 'done' : m.state === 'cancel' ? 'cancel' : ''}">${this.t(`moves.state_${m.state ?? 'draft'}`)}</span></td>
                            <td>${typeof m.transfer_id === 'string' && m.transfer_id !== '' ? html`<a class="link" @click=${() => this.navigate('stock_transfer', { transferId: m.transfer_id ?? '' })}>${m.transfer_id.slice(0, 8)}</a>` : '—'}</td>
                        </tr>`)}
                    </tbody></table>`}
                ${this._moves.hasMore ? html`<button class="more" ?disabled=${this._moves.loadingMore} @click=${() => this._moves.loadMore()}>${this.t('moves.load_more')}</button>` : ''}
            </div>
        `;
    }
}

customElements.define('stock-moves-page', StockMovesPage);

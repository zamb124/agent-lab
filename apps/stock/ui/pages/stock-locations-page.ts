/**
 * «Карта склада» — WMS-эксплорер: дерево склад → зоны → ячейки → тара
 * слева, карточка выбранной локации (KPI, содержимое, дочерние, движения,
 * действия CRUD) справа. Маршруты `stock_locations` / `stock_location`.
 */

import { html, css } from 'lit';
import type { PropertyValues } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { CursorListController, ResourceController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { PlatformTreeNode } from '@platform/lib/components/platform-tree.js';
import type { StockLocation, StockMove, StockQuant } from '@platform/lib/events/wire/stock.gen.js';
import {
    buildLocationTree, filterTree, subtreeIds, usageIcon,
} from '../_helpers/stock-location-tree.js';
import { StockLocationModal } from '../modals/stock-location-modal.js';
import '@platform/lib/components/platform-tree.js';
import '@platform/lib/components/platform-resizable-split.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-metric-card.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

export class StockLocationsPage extends PlatformPage {
    static override properties = {
        locationId: { type: String, attribute: 'location-id' },
        _query: { state: true },
        _tab: { state: true },
    };
    declare locationId: string;
    declare private _query: string;
    declare private _tab: 'contents' | 'children' | 'moves';

    static i18nNamespace = 'stock';

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow: hidden; }
            .side { display: flex; flex-direction: column; height: 100%; padding: var(--space-3); gap: var(--space-2); overflow: hidden; }
            .tree-scroll { flex: 1; overflow-y: auto; }
            .main { height: 100%; overflow-y: auto; padding: var(--space-5); }
            .loc-header { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; margin-bottom: var(--space-4); }
            .loc-header h1 { margin: 0; font-size: var(--text-xl); color: var(--text-primary); }
            .loc-path { color: var(--text-tertiary); font-size: var(--text-sm); }
            .badges { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .badge { padding: 2px 8px; border-radius: var(--radius-full); font-size: var(--text-xs); background: var(--surface-2); color: var(--text-secondary); }
            .badge.warn { background: var(--color-warning-bg, #fff3cd); color: var(--color-warning-text, #8a6d00); }
            .badge.off { opacity: 0.6; }
            .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--space-3); margin-bottom: var(--space-4); }
            .actions { display: flex; gap: var(--space-2); margin-bottom: var(--space-4); flex-wrap: wrap; }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td { padding: var(--space-2) var(--space-3); text-align: left; border-bottom: 1px solid var(--glass-border-subtle); color: var(--text-primary); }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
            .hint { color: var(--text-tertiary); margin-top: var(--space-6); text-align: center; }
            .meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--space-2) var(--space-4); margin-bottom: var(--space-4); font-size: var(--text-sm); }
            .meta-grid dt { color: var(--text-tertiary); }
            .meta-grid dd { margin: 0; color: var(--text-primary); }
            a.link { color: var(--accent-primary); cursor: pointer; text-decoration: none; }
        `,
    ];

    private _locations: ResourceController;
    private _warehouses: ResourceController;
    private _quants: ResourceController;
    private _products: ResourceController;
    private _moves: CursorListController<StockMove>;

    constructor() {
        super();
        this.locationId = '';
        this._query = '';
        this._tab = 'contents';
        this._locations = this.useResource('stock/locations', { autoload: true });
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._quants = this.useResource('stock/quants');
        this._moves = this.useCursorList('stock/moves');
        this._products = this.useResource('stock/products', { autoload: true });
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('locationId') && this.locationId !== '') {
            const loc = this._location(this.locationId);
            const subtree = loc !== null && loc.usage === 'view';
            this._quants.load(subtree ? { subtree_location_id: this.locationId } : { location_id: this.locationId });
            this._moves.load({ location_id: this.locationId });
        }
    }

    private _location(id: string): StockLocation | null {
        const row = this._locations.items.find((r) => isPlainRecord(r) && r.location_id === id);
        if (!isPlainRecord(row)) return null;
        return row as unknown as StockLocation;
    }

    private _locationsOf(predicate: (l: StockLocation) => boolean): StockLocation[] {
        const out: StockLocation[] = [];
        for (const row of this._locations.items) {
            if (isPlainRecord(row)) out.push(row as unknown as StockLocation);
        }
        return out.filter(predicate);
    }

    private _treeData() {
        const locations = this._locationsOf(() => true);
        const warehouses = this._warehouses.items.filter(isPlainRecord);
        return buildLocationTree(locations, warehouses as never, (k) => this.t(k));
    }

    private _onPick(e: CustomEvent) {
        const id = isPlainRecord(e.detail) && typeof e.detail.id === 'string' ? e.detail.id : '';
        if (id === '' || id.startsWith('wh:') || id === 'virtual') return;
        this.navigate('stock_location', { locationId: id });
    }

    private _childrenOf(id: string): StockLocation[] {
        return this._locationsOf((l) => l.parent_id === id);
    }

    private _renderSide() {
        const { nodes } = this._treeData();
        const shown = filterTree(nodes, this._query);
        return html`
            <platform-modal-search-field
                layout="fill"
                .placeholder=${this.t('explorer.search_placeholder')}
                .value=${this._query}
                @change=${(e: CustomEvent) => { this._query = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
            ></platform-modal-search-field>
            <div class="tree-scroll">
                <platform-tree
                    .nodes=${shown as PlatformTreeNode[]}
                    ?expand-all=${this._query.trim() !== ''}
                    @tree-select=${this._onPick}
                ></platform-tree>
            </div>
        `;
    }

    private _usageLabel(usage: string): string {
        const key = `explorer.usage_${usage}`;
        const label = this.t(key);
        return label === key ? usage : label;
    }

    private _quantsFor(loc: StockLocation): StockQuant[] {
        const ids = new Set<string>([loc.location_id]);
        if (loc.usage === 'view') {
            const childrenOf = new Map<string, StockLocation[]>();
            for (const l of this._locationsOf(() => true)) {
                const p = l.parent_id ?? '';
                const bucket = childrenOf.get(p) ?? [];
                bucket.push(l);
                childrenOf.set(p, bucket);
            }
            for (const id of subtreeIds(loc.location_id, childrenOf)) ids.add(id);
        }
        return this._quants.items.filter((q) => isPlainRecord(q) && ids.has(q.location_id as string)) as unknown as StockQuant[];
    }

    private _productName(productId: string): string {
        const row = this._products.items.find((r) => isPlainRecord(r) && r.product_id === productId);
        if (!isPlainRecord(row)) return productId;
        const name = row.name;
        const sku = row.sku;
        const base = typeof name === 'string' && name !== '' ? name : productId;
        return typeof sku === 'string' && sku !== '' ? `${base} · ${sku}` : base;
    }

    private _locationName(id: string | null): string {
        if (id === null) return '';
        const loc = this._location(id);
        return loc === null ? id : (loc.complete_name || loc.name);
    }

    private _renderKpis(quants: StockQuant[]) {
        const positions = quants.length;
        const qty = quants.reduce((s, q) => s + Number(q.quantity), 0);
        const reserved = quants.reduce((s, q) => s + Number(q.reserved_quantity), 0);
        const skus = new Set(quants.map((q) => q.product_id)).size;
        return html`
            <div class="kpis">
                <platform-metric-card .label=${this.t('explorer.kpi_positions')} .value=${String(positions)}></platform-metric-card>
                <platform-metric-card .label=${this.t('explorer.kpi_qty')} .value=${String(qty)}></platform-metric-card>
                <platform-metric-card .label=${this.t('explorer.kpi_reserved')} .value=${String(reserved)}></platform-metric-card>
                <platform-metric-card .label=${this.t('explorer.kpi_sku')} .value=${String(skus)}></platform-metric-card>
            </div>
        `;
    }

    private _renderContents(quants: StockQuant[]) {
        if (this._quants.loading) return html`<div class="hint">${this.t('settings.loading')}</div>`;
        if (quants.length === 0) return html`<platform-empty-state .message=${this.t('explorer.empty_contents')}></platform-empty-state>`;
        return html`
            <table><thead><tr>
                <th>${this.t('explorer.col_product')}</th>
                <th>${this.t('explorer.col_lot')}</th>
                <th>${this.t('explorer.col_owner')}</th>
                <th class="num">${this.t('explorer.col_qty')}</th>
                <th class="num">${this.t('explorer.col_reserved')}</th>
                <th class="num">${this.t('explorer.col_available')}</th>
                <th>${this.t('explorer.col_in_date')}</th>
            </tr></thead><tbody>
                ${quants.map((q) => html`<tr>
                    <td>${this._productName(q.product_id)}</td>
                    <td>${q.lot_id ?? '—'}</td>
                    <td>${q.owner_entity_id ?? '—'}</td>
                    <td class="num">${q.quantity}</td>
                    <td class="num">${q.reserved_quantity}</td>
                    <td class="num">${Number(q.quantity) - Number(q.reserved_quantity)}</td>
                    <td>${q.in_date ?? '—'}</td>
                </tr>`)}
            </tbody></table>
        `;
    }

    private _renderChildren(loc: StockLocation) {
        const kids = this._childrenOf(loc.location_id);
        if (kids.length === 0) return html`<platform-empty-state .message=${this.t('explorer.empty_children')}></platform-empty-state>`;
        return html`
            <table><tbody>
                ${kids.map((k) => html`<tr>
                    <td style="width:32px"><platform-icon name=${usageIcon(k.usage)} size="16"></platform-icon></td>
                    <td><a class="link" @click=${() => this.navigate('stock_location', { locationId: k.location_id })}>${k.complete_name || k.name}</a></td>
                    <td>${this._usageLabel(k.usage)}</td>
                </tr>`)}
            </tbody></table>
        `;
    }

    private _renderMoves() {
        const items = this._moves.items;
        const body = items.length === 0
            ? html`<platform-empty-state .message=${this.t('explorer.empty_moves')}></platform-empty-state>`
            : html`<table><thead><tr>
                    <th>${this.t('moves.col_date')}</th>
                    <th>${this.t('moves.col_product')}</th>
                    <th>${this.t('moves.col_from_to')}</th>
                    <th class="num">${this.t('moves.col_qty')}</th>
                    <th>${this.t('moves.col_state')}</th>
                </tr></thead><tbody>
                    ${items.slice(0, 10).map((m) => html`<tr>
                        <td>${String(m.date).slice(0, 16).replace('T', ' ')}</td>
                        <td>${this._productName(m.product_id)}</td>
                        <td>${this._locationName(m.location_id)} → ${this._locationName(m.location_dest_id)}</td>
                        <td class="num">${m.product_qty}</td>
                        <td>${this.t(`moves.state_${m.state ?? 'draft'}`)}</td>
                    </tr>`)}
                </tbody></table>`;
        return html`
            ${body}
            <div style="margin-top: var(--space-3)">
                <a class="link" @click=${() => this.navigate('stock_moves', {}, { search: `?location_id=${this.locationId}` })}>${this.t('explorer.all_moves')}</a>
            </div>
        `;
    }

    private _renderDetail() {
        const loc = this._location(this.locationId);
        if (loc === null) {
            return html`<div class="hint">${this.t('explorer.select_hint')}</div>`;
        }
        const quants = this._quantsFor(loc);
        const tab = this._tab;
        return html`
            <div class="loc-header">
                <h1><platform-icon name=${usageIcon(loc.usage)} size="20"></platform-icon> ${loc.name}</h1>
                <span class="loc-path">${loc.complete_name}</span>
                <div class="badges">
                    <span class="badge">${this._usageLabel(loc.usage)}</span>
                    ${loc.putaway_blocked ? html`<span class="badge warn">${this.t('explorer.blocked_putaway')}</span>` : ''}
                    ${loc.removal_blocked ? html`<span class="badge warn">${this.t('explorer.blocked_removal')}</span>` : ''}
                    ${loc.is_active === false ? html`<span class="badge off">${this.t('explorer.inactive')}</span>` : ''}
                    ${loc.allow_negative ? html`<span class="badge">${this.t('explorer.allow_negative')}</span>` : ''}
                </div>
            </div>
            <div class="actions">
                <platform-button variant="primary" density="compact"
                    @click=${() => this.openModal(StockLocationModal, { parentId: loc.location_id })}
                ><platform-icon name="plus" size="14"></platform-icon> ${this.t('explorer.create_child')}</platform-button>
                <platform-button variant="secondary" density="compact"
                    @click=${() => this.openModal(StockLocationModal, { locationId: loc.location_id })}
                ><platform-icon name="edit" size="14"></platform-icon> ${this.t('explorer.edit')}</platform-button>
            </div>
            ${this._renderKpis(quants)}
            <dl class="meta-grid">
                <div><dt>${this.t('explorer.pick_sequence')}</dt><dd>${loc.pick_sequence}</dd></div>
                <div><dt>${this.t('explorer.level')}</dt><dd>${loc.level}</dd></div>
            </dl>
            <platform-segmented-control
                density="compact"
                .value=${tab}
                .items=${[
                    { value: 'contents', label: this.t('explorer.tab_contents') },
                    { value: 'children', label: this.t('explorer.tab_children') },
                    { value: 'moves', label: this.t('explorer.tab_moves') },
                ]}
                @change=${(e: CustomEvent) => { this._tab = e.detail.value as typeof this._tab; }}
            ></platform-segmented-control>
            <div style="margin-top: var(--space-3)">
                ${tab === 'contents' ? this._renderContents(quants) : tab === 'children' ? this._renderChildren(loc) : this._renderMoves()}
            </div>
        `;
    }

    override render() {
        return html`
            <platform-resizable-split storage-key="locations" storage-scope="stock" min-size="240" max-size="520">
                <div class="side" slot="side">${this._renderSide()}</div>
                <div class="main">${this._renderDetail()}</div>
            </platform-resizable-split>
        `;
    }
}

customElements.define('stock-locations-page', StockLocationsPage);

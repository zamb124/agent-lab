/**
 * FIFO-партии: открытые приходные слои (`remaining_quantity > 0`).
 *
 * Отвечает на вопрос «из каких партий состоит остаток»: каждая строка —
 * приход с датой, документом и прогрессом «сколько партии ещё не списано».
 * Порядок — по журналу (entry_no): сверху самые старые партии, они
 * списываются первыми.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { ComboboxOption } from '@platform/lib/components/platform-searchable-combobox.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import {
    formatLayerDate,
    formatMoney,
    formatQty,
    formatUnitCost,
    parseDecimal,
    readLayersPage,
} from '../_helpers/valuation.js';
import type { StockValueLayer } from '@platform/lib/events/wire/stock.gen.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

const PAGE_SIZE = 100;

export class StockValuationBatchesPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _layers: OpController;
    private _warehouses: ResourceController;
    private _locale: SelectController<string>;
    private _search: string;
    private _warehouseId: string;
    private _limit: number;
    private _searchTimer: number | null;

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1100px; margin: 0 auto; padding: var(--space-6); }
            .toolbar {
                display: flex;
                gap: var(--space-3);
                align-items: center;
                margin-bottom: var(--space-4);
                flex-wrap: wrap;
            }
            .table-card {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                overflow: hidden;
            }
            .scroll { overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td {
                padding: var(--space-2) var(--space-3);
                text-align: left;
                border-bottom: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
                vertical-align: middle;
            }
            th {
                color: var(--text-tertiary);
                font-weight: var(--font-medium);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                white-space: nowrap;
            }
            tbody tr:last-child td { border-bottom: none; }
            .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
            .muted { color: var(--text-tertiary); }
            .cell-main { display: flex; flex-direction: column; }
            .cell-sub { font-size: var(--text-xs); color: var(--text-tertiary); }
            .doc-link {
                border: none;
                background: transparent;
                color: var(--accent);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                padding: 0;
                text-align: left;
            }
            .doc-link:hover { text-decoration: underline; }
            .progress {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 140px;
            }
            .track {
                flex: 1;
                height: 6px;
                border-radius: var(--radius-full);
                background: var(--glass-tint-medium);
                overflow: hidden;
            }
            .fill {
                height: 100%;
                border-radius: var(--radius-full);
                background: var(--accent);
                transition: width var(--motion-duration-layout) var(--motion-ease-standard);
            }
            .progress-label {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                white-space: nowrap;
                font-variant-numeric: tabular-nums;
            }
            .more {
                display: flex;
                justify-content: center;
                padding: var(--space-3);
            }
            platform-empty-state { margin-top: var(--space-8); }
            @media (max-width: 767px) {
                .wrap { padding: var(--space-3); }
            }
        `,
    ];

    constructor() {
        super();
        this._layers = this.useOp('stock/valuation_layers_list');
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._locale = this.select((s) => {
            const locale = s.i18n.locale;
            if (locale.length === 0) {
                throw new Error('stock-valuation-batches: locale required');
            }
            return locale;
        });
        this._search = '';
        this._warehouseId = '';
        this._limit = PAGE_SIZE;
        this._searchTimer = null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._load();
    }

    override disconnectedCallback(): void {
        if (this._searchTimer !== null) {
            clearTimeout(this._searchTimer);
            this._searchTimer = null;
        }
        super.disconnectedCallback();
    }

    private _load() {
        void this._layers.run({
            warehouse_id: this._warehouseId === '' ? null : this._warehouseId,
            open_only: true,
            search: this._search.trim() === '' ? null : this._search.trim(),
            limit: this._limit,
            offset: 0,
        });
    }

    private _onSearchInput(e: CustomEvent<{ value: string }>) {
        this._search = e.detail.value;
        if (this._searchTimer !== null) clearTimeout(this._searchTimer);
        this._searchTimer = window.setTimeout(() => {
            this._searchTimer = null;
            this._limit = PAGE_SIZE;
            this._load();
        }, 300);
    }

    private _warehouseOptions(): ComboboxOption[] {
        const options: ComboboxOption[] = [{ value: '', label: this.t('valuation.all_warehouses') }];
        for (const item of this._warehouses.items) {
            if (isPlainRecord(item) && typeof item.warehouse_id === 'string') {
                const code = typeof item.code === 'string' && item.code !== '' ? `${item.code} · ` : '';
                const name = typeof item.name === 'string' ? item.name : item.warehouse_id;
                options.push({ value: item.warehouse_id, label: `${code}${name}` });
            }
        }
        return options;
    }

    private _renderRow(layer: StockValueLayer, page: ReturnType<typeof readLayersPage>) {
        const locale = this._locale.value;
        const received = parseDecimal(layer.quantity);
        const remaining = parseDecimal(layer.remaining_quantity);
        const pct = received > 0 ? Math.max(0, Math.min(100, (remaining / received) * 100)) : 0;
        const productName = page.product_names[layer.product_id] ?? layer.product_id;
        const sku = page.product_skus[layer.product_id];
        const doc = typeof layer.transfer_id === 'string'
            ? (page.transfer_names[layer.transfer_id] ?? layer.transfer_id)
            : '';
        return html`
            <tr data-entry=${layer.entry_no}>
                <td>
                    <div class="cell-main">
                        <span class="muted">#${layer.entry_no}</span>
                        <span class="cell-sub">${formatLayerDate(layer.created_at, locale)}</span>
                    </div>
                </td>
                <td>
                    <div class="cell-main">
                        <span>${productName}</span>
                        ${typeof sku === 'string' && sku !== '' ? html`<span class="cell-sub">${sku}</span>` : ''}
                    </div>
                </td>
                <td>
                    ${typeof layer.transfer_id === 'string' && layer.transfer_id !== ''
                        ? html`<button
                                type="button"
                                class="doc-link"
                                @click=${() => { const id = layer.transfer_id; if (typeof id === 'string') this.navigate('stock_transfer', { transferId: id }); }}
                            >${doc}</button>`
                        : html`<span class="muted">${this.t('valuation.manual_entry')}</span>`}
                </td>
                <td class="num">${formatUnitCost(layer.unit_cost, locale)}</td>
                <td class="num muted">${formatQty(received, locale)}</td>
                <td>
                    <div class="progress">
                        <div class="track"><div class="fill" style="width: ${pct}%"></div></div>
                        <span class="progress-label">${this.t('valuation.batch_progress', {
                            remaining: formatQty(remaining, locale),
                            received: formatQty(received, locale),
                        })}</span>
                    </div>
                </td>
                <td class="num">${formatMoney(layer.remaining_value, locale)}</td>
            </tr>
        `;
    }

    override render() {
        const page = readLayersPage(this._layers.lastResult);
        return html`
            <div class="wrap">
                <page-header
                    title=${this.t('valuation.batches_title')}
                    subtitle=${this.t('valuation.batches_subtitle')}
                    dense
                ></page-header>

                <div class="toolbar">
                    <platform-modal-search-field
                        layout="toolbar"
                        data-valuation-search
                        .placeholder=${this.t('valuation.search_placeholder')}
                        .value=${this._search}
                        @change=${(e: CustomEvent) => this._onSearchInput(e)}
                    ></platform-modal-search-field>
                    <platform-searchable-combobox
                        compact
                        .value=${this._warehouseId}
                        .options=${this._warehouseOptions()}
                        .placeholder=${this.t('valuation.filter_warehouse')}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            this._warehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                            this._limit = PAGE_SIZE;
                            this._load();
                        }}
                    ></platform-searchable-combobox>
                </div>

                ${this._layers.busy && page.items.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : page.items.length === 0
                    ? html`<platform-empty-state icon="layers" title=${this.t('valuation.empty')}></platform-empty-state>`
                    : html`
                        <div class="table-card"><div class="scroll">
                            <table>
                                <thead><tr>
                                    <th>${this.t('valuation.col_entry')}</th>
                                    <th>${this.t('valuation.col_product')}</th>
                                    <th>${this.t('valuation.col_document')}</th>
                                    <th class="num">${this.t('valuation.col_unit_cost')}</th>
                                    <th class="num">${this.t('valuation.col_received')}</th>
                                    <th>${this.t('valuation.col_remaining')}</th>
                                    <th class="num">${this.t('valuation.col_left_value')}</th>
                                </tr></thead>
                                <tbody>
                                    ${page.items.map((layer) => this._renderRow(layer, page))}
                                </tbody>
                            </table>
                        </div></div>
                        ${page.items.length < page.total
                            ? html`
                                <div class="more">
                                    <platform-button
                                        variant="secondary"
                                        data-valuation-more
                                        ?loading=${this._layers.busy}
                                        @click=${() => { this._limit += PAGE_SIZE; this._load(); }}
                                    >${this.t('valuation.show_more')} · ${this.t('valuation.showing_of', { shown: page.items.length, total: page.total })}</platform-button>
                                </div>
                            ` : ''}
                    `}
            </div>
        `;
    }
}

customElements.define('stock-valuation-batches-page', StockValuationBatchesPage);

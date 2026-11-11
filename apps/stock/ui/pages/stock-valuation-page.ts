/**
 * Отчёт «Стоимость запасов»: остаток каждого товара в деньгах.
 *
 * Отвечает на вопрос «сколько стоит склад»: KPI-сводка, топ-позиции
 * с долей в сумме, переход в журнал по товару и переоценка.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { ComboboxOption } from '@platform/lib/components/platform-searchable-combobox.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import { formatMoney, formatQty, formatUnitCost, parseDecimal } from '../_helpers/valuation.js';
import { StockValuationRevalueModal } from '../modals/stock-valuation-revalue-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

const PAGE_SIZE = 100;

interface ReportRow {
    product_id: string;
    name: string;
    sku: string;
    quantity: number;
    avg_cost: number;
    value: number;
}

interface ReportResult {
    items: ReportRow[];
    total_value: number;
    products_count: number;
}

const EMPTY_REPORT: ReportResult = { items: [], total_value: 0, products_count: 0 };

function _decimalField(row: Record<string, unknown>, field: string): number {
    const value = row[field];
    if (typeof value !== 'number' && typeof value !== 'string') {
        throw new Error(`valuation: malformed ${field} in report row`);
    }
    return parseDecimal(value);
}

/** lastResult отчёта → типизированная сводка. Пустой `lastResult` — «ещё не грузили»; кривая форма — `throw`. */
function _readReport(result: unknown): ReportResult {
    if (result === undefined || result === null) return EMPTY_REPORT;
    if (!isPlainRecord(result) || !Array.isArray(result.items)) {
        throw new Error('valuation: malformed report payload');
    }
    if (typeof result.total_value !== 'number' && typeof result.total_value !== 'string') {
        throw new Error('valuation: malformed total_value in report');
    }
    if (typeof result.products_count !== 'number') {
        throw new Error('valuation: malformed products_count in report');
    }
    const items = result.items.map((row) => {
        if (!isPlainRecord(row) || typeof row.product_id !== 'string' || typeof row.name !== 'string') {
            throw new Error('valuation: malformed report row');
        }
        if (row.sku !== null && typeof row.sku !== 'string') {
            throw new Error('valuation: malformed sku in report row');
        }
        return {
            product_id: row.product_id,
            name: row.name,
            sku: row.sku === null ? '' : row.sku,
            quantity: _decimalField(row, 'quantity'),
            avg_cost: _decimalField(row, 'avg_cost'),
            value: _decimalField(row, 'value'),
        };
    });
    return {
        items,
        total_value: parseDecimal(result.total_value),
        products_count: result.products_count,
    };
}

export class StockValuationPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _report: OpController;
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
            .kpis {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: var(--space-3);
                margin-bottom: var(--space-5);
            }
            .kpi {
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
            .kpi-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .kpi-value {
                margin-top: var(--space-2);
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                font-variant-numeric: tabular-nums;
            }
            .kpi-extra {
                margin-top: 2px;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
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
                padding: var(--space-2) var(--space-4);
                text-align: left;
                border-bottom: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
            }
            th {
                color: var(--text-tertiary);
                font-weight: var(--font-medium);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            tbody tr:last-child td { border-bottom: none; }
            tr.row {
                cursor: pointer;
                background: linear-gradient(
                    to right,
                    var(--accent-subtle) var(--share, 0%),
                    transparent var(--share, 0%)
                );
            }
            tr.row:hover td { background: transparent; }
            tr.row:hover { filter: brightness(1.05); }
            .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
            .product { display: flex; flex-direction: column; }
            .product-name { font-weight: var(--font-medium); }
            .product-sku { font-size: var(--text-xs); color: var(--text-tertiary); }
            .value-cell { font-weight: var(--font-semibold); }
            .row-actions { display: flex; gap: var(--space-1); justify-content: flex-end; }
            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 0;
            }
            .icon-btn:hover { background: var(--glass-tint-medium); color: var(--text-primary); }
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
        this._report = this.useOp('stock/valuation_report');
        this._warehouses = this.useResource('stock/warehouses', { autoload: true });
        this._locale = this.select((s) => {
            const locale = s.i18n.locale;
            if (locale.length === 0) {
                throw new Error('stock-valuation-page: locale required');
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
        void this._report.run({
            warehouse_id: this._warehouseId === '' ? null : this._warehouseId,
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

    private _onWarehouseChange(e: CustomEvent<{ value?: unknown }>) {
        const value = e.detail.value;
        this._warehouseId = typeof value === 'string' ? value : '';
        this._limit = PAGE_SIZE;
        this._load();
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

    private _openJournal(row: ReportRow) {
        this.navigate('stock_valuation_journal', {}, { search: `?product=${row.product_id}` });
    }

    private _openRevalue(row: ReportRow | null) {
        this.openModal(StockValuationRevalueModal, row === null ? {} : { productId: row.product_id });
    }

    override render() {
        const report = _readReport(this._report.lastResult);
        const locale = this._locale.value;
        const first = report.items.length > 0 ? report.items[0] : undefined;
        const top = first === undefined ? null : first;
        const topShare = top !== null && report.total_value > 0
            ? Math.round((top.value / report.total_value) * 100)
            : 0;
        return html`
            <div class="wrap">
                <page-header
                    title=${this.t('valuation.report_title')}
                    subtitle=${this.t('valuation.report_subtitle')}
                    dense
                >
                    <platform-button
                        slot="actions"
                        variant="primary"
                        data-valuation-revalue
                        @click=${() => this._openRevalue(null)}
                    >${this.t('valuation.action_revalue')}</platform-button>
                </page-header>

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
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onWarehouseChange(e)}
                    ></platform-searchable-combobox>
                </div>

                <div class="kpis">
                    <div class="kpi">
                        <div class="kpi-label">${this.t('valuation.kpi_total_value')}</div>
                        <div class="kpi-value">${formatMoney(report.total_value, locale)}</div>
                    </div>
                    <div class="kpi">
                        <div class="kpi-label">${this.t('valuation.kpi_products')}</div>
                        <div class="kpi-value">${report.products_count}</div>
                    </div>
                    ${top !== null ? html`
                        <div class="kpi">
                            <div class="kpi-label">${this.t('valuation.kpi_top')}</div>
                            <div class="kpi-value">${formatMoney(top.value, locale)}</div>
                            <div class="kpi-extra">${top.name} · ${topShare}%</div>
                        </div>
                    ` : ''}
                </div>

                ${this._report.busy && report.items.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : report.items.length === 0
                    ? html`<platform-empty-state icon="chart" title=${this.t('valuation.empty')}></platform-empty-state>`
                    : html`
                        <div class="table-card"><div class="scroll">
                            <table>
                                <thead><tr>
                                    <th>${this.t('valuation.col_product')}</th>
                                    <th class="num">${this.t('valuation.col_qty')}</th>
                                    <th class="num">${this.t('valuation.col_unit_cost')}</th>
                                    <th class="num">${this.t('valuation.col_value')}</th>
                                    <th></th>
                                </tr></thead>
                                <tbody>
                                    ${report.items.map((row) => {
                                        const share = report.total_value > 0
                                            ? Math.max(1, Math.round((row.value / report.total_value) * 100))
                                            : 0;
                                        return html`
                                            <tr
                                                class="row"
                                                style="--share: ${share}%"
                                                data-product=${row.product_id}
                                                @click=${() => this._openJournal(row)}
                                            >
                                                <td>
                                                    <div class="product">
                                                        <span class="product-name">${row.name}</span>
                                                        ${row.sku !== '' ? html`<span class="product-sku">${row.sku}</span>` : ''}
                                                    </div>
                                                </td>
                                                <td class="num">${formatQty(row.quantity, locale)}</td>
                                                <td class="num">${formatUnitCost(row.avg_cost, locale)}</td>
                                                <td class="num value-cell">${formatMoney(row.value, locale)}</td>
                                                <td class="num">
                                                    <div class="row-actions">
                                                        <button
                                                            type="button"
                                                            class="icon-btn"
                                                            title=${this.t('valuation.open_journal')}
                                                            @click=${(e: Event) => { e.stopPropagation(); this._openJournal(row); }}
                                                        ><platform-icon name="scroll-text" size="16"></platform-icon></button>
                                                        <button
                                                            type="button"
                                                            class="icon-btn"
                                                            title=${this.t('valuation.action_revalue')}
                                                            data-revalue=${row.product_id}
                                                            @click=${(e: Event) => { e.stopPropagation(); this._openRevalue(row); }}
                                                        ><platform-icon name="adjustment" size="16"></platform-icon></button>
                                                    </div>
                                                </td>
                                            </tr>
                                        `;
                                    })}
                                </tbody>
                            </table>
                        </div></div>
                        ${report.items.length < report.products_count
                            ? html`
                                <div class="more">
                                    <platform-button
                                        variant="secondary"
                                        data-valuation-more
                                        ?loading=${this._report.busy}
                                        @click=${() => { this._limit += PAGE_SIZE; this._load(); }}
                                    >${this.t('valuation.show_more')} · ${this.t('valuation.showing_of', { shown: report.items.length, total: report.products_count })}</platform-button>
                                </div>
                            ` : ''}
                    `}
            </div>
        `;
    }
}

customElements.define('stock-valuation-page', StockValuationPage);

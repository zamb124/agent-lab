/**
 * Журнал проводок оценки: append-only лента `StockValueLayer` как отчёт.
 *
 * Инструменты исследования: умный поиск (товар/документ/описание),
 * фильтры по виду операции, складу и периоду, группировки с субтоталами.
 * Корректировка записи — через модалку сторно (новый слой, история не правится).
 */

import { html, css } from 'lit';
import type { PropertyValues, TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { ComboboxOption } from '@platform/lib/components/platform-searchable-combobox.js';
import type { SegmentItem } from '@platform/lib/components/platform-segmented-control.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import {
    VALUE_ENTRY_KINDS,
    formatLayerDate,
    formatLayerDateTime,
    formatMoney,
    formatSignedMoney,
    formatSignedQty,
    parseDecimal,
    readLayersPage,
    valueEntryKindIcon,
    valueEntryKindTone,
} from '../_helpers/valuation.js';
import type { StockValueLayer, ValueEntryKind } from '@platform/lib/events/wire/stock.gen.js';
import { StockValuationCorrectionModal } from '../modals/stock-valuation-correction-modal.js';
import { StockValuationRevalueModal } from '../modals/stock-valuation-revalue-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-searchable-combobox.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-date-picker.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';

const PAGE_SIZE = 100;

type GroupBy = 'none' | 'product' | 'document' | 'kind' | 'day';

interface JournalGroup {
    key: string;
    label: string;
    sublabel: string;
    sum: number;
    count: number;
    items: StockValueLayer[];
}

export class StockValuationJournalPage extends PlatformPage {
    static i18nNamespace = 'stock';

    private _layers: OpController;
    private _warehouses: ResourceController;
    private _locale: SelectController<string>;
    private _routeSearch: SelectController<string>;
    private _search: string;
    private _kind: string;
    private _warehouseId: string;
    private _dateFrom: string;
    private _dateTo: string;
    private _groupBy: GroupBy;
    private _limit: number;
    private _productId: string;
    private _appliedRouteSearch: string;
    private _searchTimer: number | null;

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1280px; margin: 0 auto; padding: var(--space-6); }
            .toolbar {
                display: flex;
                gap: var(--space-3);
                align-items: center;
                margin-bottom: var(--space-3);
                flex-wrap: wrap;
            }
            .grouping {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
                flex-wrap: wrap;
            }
            .grouping-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--accent-subtle);
                color: var(--text-primary);
                font-size: var(--text-xs);
                border: none;
                cursor: pointer;
            }
            .chip:hover { background: var(--glass-tint-medium); }
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
            .group-head td {
                background: var(--glass-tint-subtle);
                border-bottom: 1px solid var(--glass-border-subtle);
                padding: var(--space-2) var(--space-3);
            }
            .group-title {
                display: flex;
                align-items: baseline;
                gap: var(--space-3);
                font-weight: var(--font-semibold);
            }
            .group-sub { font-size: var(--text-xs); color: var(--text-tertiary); font-weight: var(--font-normal); }
            .group-sum {
                margin-left: auto;
                font-variant-numeric: tabular-nums;
                font-weight: var(--font-semibold);
            }
            .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
            .pos { color: var(--success); }
            .neg { color: var(--error); }
            .muted { color: var(--text-tertiary); }
            .cell-main { display: flex; flex-direction: column; }
            .cell-sub { font-size: var(--text-xs); color: var(--text-tertiary); }
            .kind-badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                white-space: nowrap;
            }
            .kind-badge.tone-in { background: var(--success-bg); color: var(--success); }
            .kind-badge.tone-out { background: var(--error-bg); color: var(--error); }
            .kind-badge.tone-adj { background: var(--info-bg); color: var(--info); }
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
            platform-date-picker { min-width: 220px; }
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
                throw new Error('stock-valuation-journal: locale required');
            }
            return locale;
        });
        this._routeSearch = this.select((s) => s.router.search);
        this._search = '';
        this._kind = '';
        this._warehouseId = '';
        this._dateFrom = '';
        this._dateTo = '';
        this._groupBy = 'none';
        this._limit = PAGE_SIZE;
        this._productId = '';
        this._appliedRouteSearch = '';
        this._searchTimer = null;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._syncProductFromRoute(this._routeSearch.value);
        this._load();
    }

    override disconnectedCallback(): void {
        if (this._searchTimer !== null) {
            clearTimeout(this._searchTimer);
            this._searchTimer = null;
        }
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        const routeSearch = this._routeSearch.value;
        if (routeSearch !== this._appliedRouteSearch) {
            this._syncProductFromRoute(routeSearch);
            this._limit = PAGE_SIZE;
            this._load();
        }
    }

    /** Переход из отчёта: `?product=<id>` фиксирует журнал на одном товаре. */
    private _syncProductFromRoute(routeSearch: string) {
        this._appliedRouteSearch = routeSearch;
        const params = new URLSearchParams(routeSearch.startsWith('?') ? routeSearch.slice(1) : routeSearch);
        this._productId = params.get('product') ?? '';
    }

    private _clearProduct() {
        this.navigate('stock_valuation_journal', {});
    }

    private _entryKindsPayload(): ValueEntryKind[] | null {
        if (this._kind === '') return null;
        if (!VALUE_ENTRY_KINDS.includes(this._kind as ValueEntryKind)) {
            throw new Error(`stock-valuation-journal: unknown kind ${this._kind}`);
        }
        return [this._kind as ValueEntryKind];
    }

    private _payload() {
        return {
            product_id: this._productId === '' ? null : this._productId,
            warehouse_id: this._warehouseId === '' ? null : this._warehouseId,
            entry_kinds: this._entryKindsPayload(),
            date_from: this._dateFrom === '' ? null : new Date(`${this._dateFrom}T00:00:00`).toISOString(),
            date_to: this._dateTo === '' ? null : new Date(`${this._dateTo}T23:59:59.999`).toISOString(),
            open_only: false,
            search: this._search.trim() === '' ? null : this._search.trim(),
            limit: this._limit,
            offset: 0,
        };
    }

    private _load() {
        void this._layers.run(this._payload());
    }

    private _resetAndLoad() {
        this._limit = PAGE_SIZE;
        this._load();
    }

    private _onSearchInput(e: CustomEvent<{ value: string }>) {
        this._search = e.detail.value;
        if (this._searchTimer !== null) clearTimeout(this._searchTimer);
        this._searchTimer = window.setTimeout(() => {
            this._searchTimer = null;
            this._resetAndLoad();
        }, 300);
    }

    private _kindOptions(): ComboboxOption[] {
        const options: ComboboxOption[] = [{ value: '', label: this.t('valuation.all_kinds') }];
        for (const kind of VALUE_ENTRY_KINDS) {
            options.push({ value: kind, label: this.t(`valuation.kind_${kind}`) });
        }
        return options;
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

    private _groupOptions(): Array<Partial<SegmentItem>> {
        return [
            { value: 'none', label: this.t('valuation.group_none') },
            { value: 'product', label: this.t('valuation.group_product') },
            { value: 'document', label: this.t('valuation.group_document') },
            { value: 'kind', label: this.t('valuation.group_kind') },
            { value: 'day', label: this.t('valuation.group_day') },
        ];
    }

    private _onRangeChange(e: CustomEvent<{ value?: unknown }>) {
        const value = e.detail.value;
        if (!isPlainRecord(value)) {
            this._dateFrom = '';
            this._dateTo = '';
        } else {
            this._dateFrom = typeof value.start === 'string' ? value.start : '';
            this._dateTo = typeof value.end === 'string' ? value.end : '';
        }
        this._resetAndLoad();
    }

    private _productName(page: ReturnType<typeof readLayersPage>, productId: string): string {
        const name = page.product_names[productId];
        if (typeof name === 'string' && name.length > 0) return name;
        return productId;
    }

    private _documentName(page: ReturnType<typeof readLayersPage>, layer: StockValueLayer): string {
        if (typeof layer.transfer_id === 'string' && layer.transfer_id.length > 0) {
            const name = page.transfer_names[layer.transfer_id];
            if (typeof name === 'string' && name.length > 0) return name;
            return layer.transfer_id;
        }
        if (typeof layer.origin_document_id === 'string' && layer.origin_document_id.length > 0) {
            return layer.origin_document_id;
        }
        return '';
    }

    private _groupLabel(page: ReturnType<typeof readLayersPage>, layer: StockValueLayer): { key: string; label: string; sublabel: string } {
        const locale = this._locale.value;
        switch (this._groupBy) {
            case 'product': {
                const name = this._productName(page, layer.product_id);
                const sku = page.product_skus[layer.product_id];
                return {
                    key: `product:${layer.product_id}`,
                    label: name,
                    sublabel: typeof sku === 'string' && sku !== '' ? sku : '',
                };
            }
            case 'document': {
                const doc = this._documentName(page, layer);
                return {
                    key: `doc:${typeof layer.transfer_id === 'string' ? layer.transfer_id : 'manual'}`,
                    label: doc === '' ? this.t('valuation.manual_entry') : doc,
                    sublabel: '',
                };
            }
            case 'kind':
                return {
                    key: `kind:${layer.entry_kind}`,
                    label: this.t(`valuation.kind_${layer.entry_kind}`),
                    sublabel: '',
                };
            case 'day':
                return {
                    key: `day:${typeof layer.created_at === 'string' ? layer.created_at.slice(0, 10) : ''}`,
                    label: formatLayerDate(layer.created_at, locale),
                    sublabel: '',
                };
            case 'none':
                return { key: 'all', label: '', sublabel: '' };
        }
    }

    private _groups(items: StockValueLayer[], page: ReturnType<typeof readLayersPage>): JournalGroup[] {
        const groups: JournalGroup[] = [];
        const byKey = new Map<string, JournalGroup>();
        for (const layer of items) {
            const g = this._groupLabel(page, layer);
            let group = byKey.get(g.key);
            if (group === undefined) {
                group = { key: g.key, label: g.label, sublabel: g.sublabel, sum: 0, count: 0, items: [] };
                byKey.set(g.key, group);
                groups.push(group);
            }
            group.items.push(layer);
            group.count += 1;
            group.sum += parseDecimal(layer.value);
        }
        return groups;
    }

    private _renderKindBadge(layer: StockValueLayer) {
        const tone = valueEntryKindTone(layer.entry_kind);
        return html`
            <span class="kind-badge tone-${tone}">
                <platform-icon name=${valueEntryKindIcon(layer.entry_kind)} size="12"></platform-icon>
                ${this.t(`valuation.kind_${layer.entry_kind}`)}
            </span>
        `;
    }

    private _renderRow(layer: StockValueLayer, page: ReturnType<typeof readLayersPage>) {
        const locale = this._locale.value;
        const qty = parseDecimal(layer.quantity);
        const value = parseDecimal(layer.value);
        const doc = this._documentName(page, layer);
        const warehouse = typeof layer.warehouse_id === 'string'
            ? (page.warehouse_names[layer.warehouse_id] ?? layer.warehouse_id)
            : '';
        return html`
            <tr data-entry=${layer.entry_no}>
                <td>
                    <div class="cell-main">
                        <span class="muted">#${layer.entry_no}</span>
                        <span class="cell-sub">${formatLayerDateTime(layer.created_at, locale)}</span>
                    </div>
                </td>
                <td>${this._renderKindBadge(layer)}</td>
                <td>
                    <div class="cell-main">
                        <span>${this._productName(page, layer.product_id)}</span>
                        ${typeof page.product_skus[layer.product_id] === 'string' && page.product_skus[layer.product_id] !== ''
                            ? html`<span class="cell-sub">${page.product_skus[layer.product_id]}</span>` : ''}
                    </div>
                </td>
                <td>
                    <div class="cell-main">
                        ${typeof layer.transfer_id === 'string' && layer.transfer_id !== ''
                            ? html`<button
                                    type="button"
                                    class="doc-link"
                                    data-transfer=${layer.transfer_id}
                                    @click=${() => { const id = layer.transfer_id; if (typeof id === 'string') this.navigate('stock_transfer', { transferId: id }); }}
                                >${doc}</button>`
                            : html`<span class="muted">${doc === '' ? this.t('valuation.manual_entry') : doc}</span>`}
                        ${warehouse !== '' ? html`<span class="cell-sub">${warehouse}</span>` : ''}
                    </div>
                </td>
                <td class="num ${qty > 0 ? 'pos' : qty < 0 ? 'neg' : ''}">${formatSignedQty(layer.quantity, locale)}</td>
                <td class="num ${value > 0 ? 'pos' : value < 0 ? 'neg' : ''}">${formatSignedMoney(layer.value, locale)}</td>
                <td class="num muted">${formatMoney(layer.value_after, locale)}</td>
                <td class="num">
                    <button
                        type="button"
                        class="icon-btn"
                        title=${this.t('valuation.action_correct')}
                        data-correct=${layer.layer_id}
                        @click=${() => this._openCorrection(layer, page)}
                    ><platform-icon name="edit" size="14"></platform-icon></button>
                </td>
            </tr>
        `;
    }

    private _openCorrection(layer: StockValueLayer, page: ReturnType<typeof readLayersPage>) {
        this.openModal(StockValuationCorrectionModal, {
            layer,
            productName: this._productName(page, layer.product_id),
        });
    }

    override render() {
        const page = readLayersPage(this._layers.lastResult);
        const locale = this._locale.value;
        const groups = this._groups(page.items, page);
        const productChip = this._productId !== '';
        return html`
            <div class="wrap">
                <page-header
                    title=${this.t('valuation.journal_title')}
                    subtitle=${this.t('valuation.journal_subtitle')}
                    dense
                >
                    <platform-button
                        slot="actions"
                        variant="secondary"
                        data-valuation-revalue
                        @click=${() => this.openModal(StockValuationRevalueModal, {})}
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
                        .value=${this._kind}
                        .options=${this._kindOptions()}
                        .placeholder=${this.t('valuation.filter_kind')}
                        data-kind-filter
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            this._kind = typeof e.detail.value === 'string' ? e.detail.value : '';
                            this._resetAndLoad();
                        }}
                    ></platform-searchable-combobox>
                    <platform-searchable-combobox
                        compact
                        .value=${this._warehouseId}
                        .options=${this._warehouseOptions()}
                        .placeholder=${this.t('valuation.filter_warehouse')}
                        data-warehouse-filter
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            this._warehouseId = typeof e.detail.value === 'string' ? e.detail.value : '';
                            this._resetAndLoad();
                        }}
                    ></platform-searchable-combobox>
                    <platform-date-picker
                        mode="date"
                        selection="range"
                        value-format="date"
                        .placeholder=${this.t('valuation.dates_placeholder')}
                        .value=${{ start: this._dateFrom === '' ? null : this._dateFrom, end: this._dateTo === '' ? null : this._dateTo }}
                        data-date-filter
                        @change=${(e: CustomEvent<{ value?: unknown }>) => this._onRangeChange(e)}
                    ></platform-date-picker>
                </div>

                <div class="grouping">
                    <span class="grouping-label">${this.t('valuation.group_by')}</span>
                    <platform-segmented-control
                        density="compact"
                        .value=${this._groupBy}
                        .items=${this._groupOptions()}
                        data-group-by
                        @change=${(e: CustomEvent<{ value?: unknown }>) => {
                            const value = e.detail.value;
                            if (typeof value === 'string' && ['none', 'product', 'document', 'kind', 'day'].includes(value)) {
                                this._groupBy = value as GroupBy;
                            }
                        }}
                    ></platform-segmented-control>
                    ${productChip ? html`
                        <button type="button" class="chip" data-product-chip @click=${() => this._clearProduct()}>
                            ${this._productName(page, this._productId)}
                            <platform-icon name="close" size="12"></platform-icon>
                        </button>
                    ` : ''}
                </div>

                ${this._layers.busy && page.items.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : page.items.length === 0
                    ? html`<platform-empty-state icon="scroll-text" title=${this.t('valuation.empty')}></platform-empty-state>`
                    : html`
                        <div class="table-card"><div class="scroll">
                            <table>
                                <thead><tr>
                                    <th>${this.t('valuation.col_entry')}</th>
                                    <th>${this.t('valuation.col_operation')}</th>
                                    <th>${this.t('valuation.col_product')}</th>
                                    <th>${this.t('valuation.col_document')}</th>
                                    <th class="num">${this.t('valuation.col_qty')}</th>
                                    <th class="num">${this.t('valuation.col_value')}</th>
                                    <th class="num">${this.t('valuation.col_balance')}</th>
                                    <th></th>
                                </tr></thead>
                                ${groups.map((group) => html`
                                    <tbody>
                                        ${this._groupBy !== 'none' ? html`
                                            <tr class="group-head">
                                                <td colspan="8">
                                                    <div class="group-title">
                                                        <span>${group.label}</span>
                                                        ${group.sublabel !== '' ? html`<span class="group-sub">${group.sublabel}</span>` : ''}
                                                        <span class="group-sub">${this.t('valuation.entries_count', { count: group.count })}</span>
                                                        <span class="group-sum ${group.sum > 0 ? 'pos' : group.sum < 0 ? 'neg' : ''}">${formatSignedMoney(group.sum, locale)}</span>
                                                    </div>
                                                </td>
                                            </tr>
                                        ` : ''}
                                        ${group.items.map((layer) => this._renderRow(layer, page))}
                                    </tbody>
                                `)}
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

customElements.define('stock-valuation-journal-page', StockValuationJournalPage);

/**
 * Каталог блюд заведения: единственный источник карточки блюда.
 *
 * Таблица блюд с фильтрами (AI-черновики, похожие, без фото, скрытые),
 * массовой проверкой и обогащением агентом, редактор меток магазина.
 * Карточка — ShopProductModal, объединение дублей — ShopProductMergeModal,
 * импорт в каталог — ShopMenuImportModal с целью `catalog`. Список
 * перечитывает фабрика по push `shop/catalog/changed`.
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues, TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { ShopBadgeResponse, ShopProductResponse } from '@platform/lib/events/wire/shop.gen.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/shop-agent-jobs-banner.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';
import type { ShopHeadRow } from '../components/shop-page-head.js';
import { formatShopMeasure, formatShopPrice, shopBadgeSvg, shopFileUrl } from '../_helpers/shop-format.js';

type CatalogFilter = 'all' | 'ai' | 'similar' | 'no_photo' | 'unavailable';

const CATALOG_FILTERS: readonly CatalogFilter[] = ['all', 'ai', 'similar', 'no_photo', 'unavailable'];

function isCatalogFilter(value: unknown): value is CatalogFilter {
    return typeof value === 'string' && CATALOG_FILTERS.some((filter) => filter === value);
}

function matchesFilter(product: ShopProductResponse, filter: CatalogFilter): boolean {
    switch (filter) {
        case 'all':
            return true;
        case 'ai':
            return product.ai_unverified;
        case 'similar':
            return product.similar_shop_product_id !== null;
        case 'no_photo':
            return product.photo_file_id === null;
        case 'unavailable':
            return !product.is_available;
    }
}

export class ShopCatalogPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ControllerFor<'shop/shops'>;
    private _shopUpdate: ControllerFor<'shop/shop_update'>;
    private _badgeIconsOp: ControllerFor<'shop/badge_icons_list'>;
    private _products: ControllerFor<'shop/products_list'>;
    private _productUpdate: ControllerFor<'shop/product_update'>;
    private _productRemove: ControllerFor<'shop/product_remove'>;
    private _productVerify: ControllerFor<'shop/product_verify'>;
    private _productsEnrich: ControllerFor<'shop/products_enrich'>;
    private _locale: SelectController<string>;

    declare _query: string;
    declare _filter: CatalogFilter;
    declare _selectedIds: string[];
    declare _bulkVerifying: boolean;
    declare _badgeEditorOpen: boolean;
    declare _newBadgeLabel: string;
    declare _newBadgeIcon: string;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        _query: { state: true },
        _filter: { state: true },
        _selectedIds: { state: true },
        _bulkVerifying: { state: true },
        _badgeEditorOpen: { state: true },
        _newBadgeLabel: { state: true },
        _newBadgeIcon: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { padding: var(--space-5) var(--space-6) var(--space-10); }
            .head-actions { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }

            .toolbar {
                display: flex; gap: var(--space-3); align-items: flex-end; flex-wrap: wrap;
                margin-bottom: var(--space-3);
            }
            .toolbar platform-field { flex: 1 1 240px; max-width: 360px; }

            .bulk {
                display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--accent) 8%, var(--bg-surface));
                margin-bottom: var(--space-3);
                font-size: var(--text-sm); color: var(--text-primary);
            }
            .bulk .count { font-weight: var(--font-semibold); margin-right: auto; }

            .table {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                overflow: hidden;
            }
            .row {
                display: grid;
                grid-template-columns: 28px 48px minmax(0, 1fr) 96px 104px 48px 168px;
                gap: var(--space-3);
                align-items: center;
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--glass-border-subtle);
            }
            .row:first-child { border-top: none; }
            .row.head {
                color: var(--text-tertiary); font-size: var(--text-xs); font-weight: var(--font-medium);
                text-transform: uppercase; letter-spacing: 0.04em;
            }
            .row.similar { background: color-mix(in srgb, var(--warning) 7%, transparent); }
            .row.off .info, .row.off .thumb { opacity: 0.55; }
            .thumb {
                width: 48px; height: 48px; border-radius: var(--radius-md);
                object-fit: cover; display: block;
            }
            .thumb-empty {
                width: 48px; height: 48px; border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--text-primary) 5%, transparent);
                display: flex; align-items: center; justify-content: center;
                color: var(--text-tertiary);
            }
            .info { min-width: 0; }
            .name {
                display: flex; align-items: center; gap: var(--space-1); flex-wrap: wrap;
                font-weight: var(--font-semibold); color: var(--text-primary);
                font-size: var(--text-sm); line-height: 1.3;
            }
            .desc {
                color: var(--text-tertiary); font-size: var(--text-xs); line-height: 1.45;
                margin-top: 2px;
                display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden;
            }
            .flag {
                display: inline-flex; align-items: center; gap: 2px; padding: 1px var(--space-2);
                border-radius: var(--radius-full); font-size: 10px; font-weight: var(--font-bold);
                border: none; cursor: default; font-family: inherit;
            }
            .flag.ai { background: color-mix(in srgb, var(--accent) 14%, transparent); color: var(--accent); }
            .flag.similar {
                background: color-mix(in srgb, var(--warning) 16%, transparent); color: var(--warning);
                cursor: pointer;
            }
            .ptag {
                display: inline-flex; align-items: center; padding: 1px var(--space-1);
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent);
            }
            .ptag svg { width: 11px; height: 11px; fill: currentColor; }
            .measure { color: var(--text-secondary); font-size: var(--text-xs); white-space: nowrap; }
            .price {
                font-variant-numeric: tabular-nums; font-weight: var(--font-semibold);
                color: var(--text-primary); white-space: nowrap; text-align: right;
            }
            .price::after { content: ' ₽'; font-weight: var(--font-normal); color: var(--text-tertiary); }
            .ops { display: flex; gap: 2px; justify-content: flex-end; }

            .badges { display: flex; flex-wrap: wrap; gap: var(--space-1); }
            .bchip {
                display: inline-flex; align-items: center; gap: var(--space-1);
                padding: var(--space-1) var(--space-2); border-radius: var(--radius-full);
                border: 1px solid var(--border-default); background: var(--surface-secondary);
                color: var(--text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium);
            }
            .bchip svg { width: 13px; height: 13px; fill: currentColor; }
            .bchip .x { cursor: pointer; display: inline-flex; opacity: 0.6; background: none; border: none; color: inherit; padding: 0; }
            .bchip .x:hover { opacity: 1; }

            .panel {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-4);
                margin-bottom: var(--space-4);
                display: flex; flex-direction: column; gap: var(--space-3);
            }
            .panel-title { font-weight: var(--font-semibold); color: var(--text-primary); }
            .panel-hint { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.5; }
            .badge-add { display: flex; gap: var(--space-3); align-items: flex-end; flex-wrap: wrap; }
            .badge-add platform-field { min-width: 200px; }
            .icon-grid { display: flex; flex-wrap: wrap; gap: var(--space-1); max-width: 340px; }
            .icon-pick {
                width: 30px; height: 30px; border-radius: var(--radius-md);
                border: 1px solid var(--border-default); background: var(--bg-surface);
                color: var(--text-secondary); cursor: pointer; display: inline-flex;
                align-items: center; justify-content: center;
            }
            .icon-pick.on { border-color: var(--accent); color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
            .icon-pick svg { width: 14px; height: 14px; fill: currentColor; }

            platform-empty-state { margin-top: var(--space-8); }

            @media (max-width: 900px) {
                .row { grid-template-columns: 28px 48px minmax(0, 1fr) 88px 48px; }
                .row .measure, .row .ops-cell { display: none; }
                .row.head .measure-h, .row.head .ops-h { display: none; }
            }
        `,
    ];

    constructor() {
        super();
        this.shopId = '';
        this._query = '';
        this._filter = 'all';
        this._selectedIds = [];
        this._bulkVerifying = false;
        this._badgeEditorOpen = false;
        this._newBadgeLabel = '';
        this._newBadgeIcon = '';
        this._shops = this.useResource('shop/shops');
        this._shopUpdate = this.useOp('shop/shop_update');
        this._badgeIconsOp = this.useOp('shop/badge_icons_list');
        this._products = this.useOp('shop/products_list');
        this._productUpdate = this.useOp('shop/product_update');
        this._productRemove = this.useOp('shop/product_remove');
        this._productVerify = this.useOp('shop/product_verify');
        this._productsEnrich = this.useOp('shop/products_enrich');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('shopId') && this.shopId !== '') {
            this._selectedIds = [];
            this._shops.load();
            void this._products.run({ shop_id: this.shopId });
        }
    }

    private get _rows(): ShopProductResponse[] {
        const result = this._products.lastResult;
        if (result === null) {
            return [];
        }
        return result.items.filter((product) => product.shop_id === this.shopId);
    }

    private _shopHead(): ShopHeadRow | null {
        return shopHeadRow(this._shops.items.find((shop) => shop.shop_id === this.shopId));
    }

    private _badgeDefs(): ShopBadgeResponse[] {
        const shop = this._shops.items.find((row) => row.shop_id === this.shopId);
        return shop === undefined ? [] : shop.badges;
    }

    private _visibleRows(): ShopProductResponse[] {
        const query = this._query.trim().toLocaleLowerCase();
        return this._rows.filter((product) =>
            matchesFilter(product, this._filter)
            && (query === '' || product.name.toLocaleLowerCase().includes(query)));
    }

    private _filterItems(): { value: CatalogFilter; label: string }[] {
        const rows = this._rows;
        const count = (filter: CatalogFilter) => rows.filter((product) => matchesFilter(product, filter)).length;
        return [
            { value: 'all', label: `${this.t('catalog.filter_all')} · ${rows.length}` },
            { value: 'ai', label: `${this.t('catalog.filter_ai')} · ${count('ai')}` },
            { value: 'similar', label: `${this.t('catalog.filter_similar')} · ${count('similar')}` },
            { value: 'no_photo', label: `${this.t('catalog.filter_no_photo')} · ${count('no_photo')}` },
            { value: 'unavailable', label: `${this.t('catalog.filter_unavailable')} · ${count('unavailable')}` },
        ];
    }

    private _selectedRows(): ShopProductResponse[] {
        const selected = new Set(this._selectedIds);
        return this._rows.filter((product) => selected.has(product.shop_product_id));
    }

    private _toggleSelected(productId: string, checked: boolean): void {
        this._selectedIds = checked
            ? [...new Set([...this._selectedIds, productId])]
            : this._selectedIds.filter((id) => id !== productId);
    }

    private _toggleAllVisible(checked: boolean): void {
        const visibleIds = this._visibleRows().map((product) => product.shop_product_id);
        this._selectedIds = checked
            ? [...new Set([...this._selectedIds, ...visibleIds])]
            : this._selectedIds.filter((id) => !visibleIds.includes(id));
    }

    private async _toggleBadgeEditor(): Promise<void> {
        this._badgeEditorOpen = !this._badgeEditorOpen;
        if (this._badgeEditorOpen && this._badgeIconsOp.lastResult === null) {
            await this._badgeIconsOp.run({});
        }
    }

    private async _saveBadgeDefs(badges: { key?: string; label: string; icon: string }[]): Promise<void> {
        await this._shopUpdate.run({ shop_id: this.shopId, badges });
    }

    private async _addBadgeDef(): Promise<void> {
        const label = this._newBadgeLabel.trim();
        if (label === '' || this._newBadgeIcon === '') return;
        const current = this._badgeDefs().map((badge) => ({ key: badge.key, label: badge.label, icon: badge.icon }));
        await this._saveBadgeDefs([...current, { label, icon: this._newBadgeIcon }]);
        this._newBadgeLabel = '';
        this._newBadgeIcon = '';
    }

    private async _removeBadgeDef(key: string): Promise<void> {
        await this._saveBadgeDefs(
            this._badgeDefs()
                .filter((badge) => badge.key !== key)
                .map((badge) => ({ key: badge.key, label: badge.label, icon: badge.icon })),
        );
    }

    private _openProduct(product: ShopProductResponse | null): void {
        this.openModal('shop.product', {
            shopId: this.shopId,
            product,
            badgeDefs: this._badgeDefs(),
        });
    }

    private _openMerge(product: ShopProductResponse): void {
        this.openModal('shop.product_merge', { shopId: this.shopId, product });
    }

    private _openModifiers(product: ShopProductResponse): void {
        this.openModal('shop.modifiers', {
            shopId: this.shopId,
            productId: product.shop_product_id,
            productName: product.name,
        });
    }

    private _openImport(): void {
        this.openModal('shop.menu_import', { shopId: this.shopId, target: 'catalog', shopMenuId: null });
    }

    private async _toggleAvailable(product: ShopProductResponse, enabled: boolean): Promise<void> {
        await this._productUpdate.run({
            shop_id: this.shopId,
            shop_product_id: product.shop_product_id,
            is_available: enabled,
        });
    }

    private async _verify(product: ShopProductResponse): Promise<void> {
        await this._productVerify.run({ shop_id: this.shopId, shop_product_id: product.shop_product_id });
    }

    private async _remove(product: ShopProductResponse): Promise<void> {
        const confirmed = await platformConfirm(this.t('catalog.remove_confirm', { name: product.name }), {
            title: this.t('catalog.remove_title'),
            variant: 'warning',
            confirmText: this.t('catalog.remove'),
            cancelText: this.t('common.cancel'),
        });
        if (confirmed !== true) return;
        await this._productRemove.run({ shop_id: this.shopId, shop_product_id: product.shop_product_id });
        this._selectedIds = this._selectedIds.filter((id) => id !== product.shop_product_id);
    }

    private async _bulkVerify(): Promise<void> {
        const targets = this._selectedRows().filter((product) => product.ai_unverified);
        if (targets.length === 0) return;
        this._bulkVerifying = true;
        try {
            for (const product of targets) {
                await this._productVerify.run({ shop_id: this.shopId, shop_product_id: product.shop_product_id });
            }
        } finally {
            this._bulkVerifying = false;
        }
        this._selectedIds = [];
    }

    private async _enrich(productIds: string[]): Promise<void> {
        const workItem = await this._productsEnrich.run({ shop_id: this.shopId, shop_product_ids: productIds });
        if (workItem !== null) {
            this._selectedIds = [];
        }
    }

    private _renderBadgeEditor(): TemplateResult | typeof nothing {
        if (!this._badgeEditorOpen) return nothing;
        const icons = this._badgeIconsOp.lastResult;
        return html`
            <div class="panel">
                <div class="panel-title">${this.t('catalog.badges_title')}</div>
                <div class="panel-hint">${this.t('catalog.badges_hint')}</div>
                <div class="badges">
                    ${this._badgeDefs().map((badge) => html`
                        <span class="bchip">${shopBadgeSvg(badge.icon_path)} ${badge.label}
                            <button type="button" class="x" title=${this.t('catalog.badge_remove')}
                                @click=${() => this._removeBadgeDef(badge.key)}
                            ><platform-icon name="close" size="11"></platform-icon></button>
                        </span>`)}
                </div>
                <div class="badge-add">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('catalog.badge_label')}
                        .value=${this._newBadgeLabel}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            this._newBadgeLabel = typeof event.detail.value === 'string' ? event.detail.value : '';
                        }}
                    ></platform-field>
                    <span class="icon-grid">
                        ${icons === null ? nothing : Object.entries(icons.icons).map(([name, path]) => html`
                            <button type="button" class="icon-pick ${this._newBadgeIcon === name ? 'on' : ''}"
                                title=${name} @click=${() => { this._newBadgeIcon = name; }}
                            >${shopBadgeSvg(path)}</button>`)}
                    </span>
                    <platform-button size="sm" variant="primary" ?loading=${this._shopUpdate.busy}
                        ?disabled=${this._newBadgeLabel.trim() === '' || this._newBadgeIcon === ''}
                        @click=${() => this._addBadgeDef()}
                    >${this.t('catalog.badge_add')}</platform-button>
                </div>
            </div>
        `;
    }

    private _renderBulkBar(): TemplateResult | typeof nothing {
        const selected = this._selectedRows();
        if (selected.length === 0) return nothing;
        const unverified = selected.filter((product) => product.ai_unverified).length;
        return html`
            <div class="bulk" role="toolbar" aria-label=${this.t('catalog.bulk_label')}>
                <span class="count">${this.t('catalog.selected', { count: selected.length })}</span>
                <platform-button size="sm" variant="secondary" ?loading=${this._bulkVerifying} ?disabled=${unverified === 0}
                    @click=${() => this._bulkVerify()}>
                    <platform-icon name="check" size="14"></platform-icon> ${this.t('catalog.bulk_verify')} · ${unverified}
                </platform-button>
                <platform-button size="sm" variant="accent" ?loading=${this._productsEnrich.busy}
                    @click=${() => this._enrich(selected.map((product) => product.shop_product_id))}>
                    <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('catalog.bulk_enrich')}
                </platform-button>
                <platform-button size="sm" variant="ghost" @click=${() => { this._selectedIds = []; }}>
                    ${this.t('catalog.bulk_clear')}
                </platform-button>
            </div>
        `;
    }

    private _renderRow(product: ShopProductResponse, badgeDefs: ShopBadgeResponse[], byId: Map<string, ShopProductResponse>): TemplateResult {
        const selected = this._selectedIds.includes(product.shop_product_id);
        const similar = product.similar_shop_product_id === null ? undefined : byId.get(product.similar_shop_product_id);
        const measure = formatShopMeasure(product.measure, product.measure_unit, (key, vars) => this.t(key, vars));
        return html`
            <div class="row ${product.is_available ? '' : 'off'} ${product.similar_shop_product_id !== null ? 'similar' : ''}">
                <input type="checkbox" .checked=${selected} aria-label=${this.t('catalog.select', { name: product.name })}
                    @change=${(event: Event) => this._toggleSelected(product.shop_product_id, (event.target as HTMLInputElement).checked)}>
                ${product.photo_file_id !== null
                    ? html`<img class="thumb" src=${shopFileUrl(product.photo_file_id)} alt="" loading="lazy">`
                    : html`<span class="thumb-empty"><platform-icon name="image" size="18"></platform-icon></span>`}
                <div class="info">
                    <div class="name">
                        ${product.name}
                        ${product.ai_unverified
                            ? html`<span class="flag ai" title=${this.t('catalog.ai_hint')}>${this.t('catalog.ai_badge')}</span>`
                            : nothing}
                        ${product.similar_shop_product_id !== null
                            ? html`<button type="button" class="flag similar" title=${this.t('catalog.similar_hint')}
                                @click=${() => this._openMerge(product)}>
                                <platform-icon name="copy" size="10"></platform-icon>
                                ${similar === undefined ? this.t('catalog.similar_badge') : this.t('catalog.similar_to', { name: similar.name })}
                            </button>`
                            : nothing}
                        ${product.badges.map((key) => {
                            const def = badgeDefs.find((badge) => badge.key === key);
                            return def === undefined ? nothing : html`<span class="ptag" title=${def.label}>${shopBadgeSvg(def.icon_path)}</span>`;
                        })}
                    </div>
                    ${product.description.trim() !== '' ? html`<div class="desc">${product.description}</div>` : nothing}
                </div>
                <span class="measure">${measure}</span>
                <span class="price">${formatShopPrice(product.price_minor, this._locale.value)}</span>
                <platform-switch
                    title=${this.t('catalog.col_available')}
                    ?checked=${product.is_available}
                    @change=${(event: CustomEvent<{ value?: unknown }>) => this._toggleAvailable(product, event.detail.value === true)}
                ></platform-switch>
                <div class="ops ops-cell">
                    ${product.ai_unverified
                        ? html`<platform-button icon-only density="compact" variant="ghost" title=${this.t('catalog.verify')}
                            @click=${() => this._verify(product)}
                        ><platform-icon name="check" size="14"></platform-icon></platform-button>`
                        : nothing}
                    ${product.similar_shop_product_id !== null
                        ? html`<platform-button icon-only density="compact" variant="ghost" title=${this.t('catalog.merge')}
                            @click=${() => this._openMerge(product)}
                        ><platform-icon name="link" size="14"></platform-icon></platform-button>`
                        : nothing}
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('catalog.modifiers')}
                        @click=${() => this._openModifiers(product)}
                    ><platform-icon name="list-check" size="14"></platform-icon></platform-button>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('catalog.edit')}
                        @click=${() => this._openProduct(product)}
                    ><platform-icon name="edit" size="14"></platform-icon></platform-button>
                    <platform-button icon-only density="compact" variant="ghost-danger" title=${this.t('catalog.remove')}
                        @click=${() => this._remove(product)}
                    ><platform-icon name="trash" size="14"></platform-icon></platform-button>
                </div>
            </div>
        `;
    }

    private _renderTable(): TemplateResult {
        const rows = this._visibleRows();
        if (this._products.lastResult === null || (this._products.busy && this._rows.length === 0)) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        if (this._rows.length === 0) {
            return html`
                <platform-empty-state icon="book-open" title=${this.t('catalog.empty')} hint=${this.t('catalog.empty_hint')}>
                </platform-empty-state>`;
        }
        if (rows.length === 0) {
            return html`<platform-empty-state icon="search" title=${this.t('catalog.empty_filtered')}></platform-empty-state>`;
        }
        const badgeDefs = this._badgeDefs();
        const byId = new Map(this._rows.map((product) => [product.shop_product_id, product]));
        const allSelected = rows.every((product) => this._selectedIds.includes(product.shop_product_id));
        return html`
            <div class="table" role="table">
                <div class="row head" role="row">
                    <input type="checkbox" .checked=${allSelected} aria-label=${this.t('catalog.select_all')}
                        @change=${(event: Event) => this._toggleAllVisible((event.target as HTMLInputElement).checked)}>
                    <span></span>
                    <span>${this.t('catalog.col_name')}</span>
                    <span class="measure-h">${this.t('catalog.col_measure')}</span>
                    <span class="price-h">${this.t('catalog.col_price')}</span>
                    <span>${this.t('catalog.col_available')}</span>
                    <span class="ops-h"></span>
                </div>
                ${rows.map((product) => this._renderRow(product, badgeDefs, byId))}
            </div>
        `;
    }

    override render(): TemplateResult {
        return html`
            <div class="wrap">
                <shop-page-head .shop=${this._shopHead()} shop-id=${this.shopId} section=${this.t('routes.shop_catalog')}>
                    <div slot="actions" class="head-actions">
                        <platform-button size="sm" variant="secondary" @click=${() => this._toggleBadgeEditor()}>
                            <platform-icon name="tag" size="14"></platform-icon> ${this.t('catalog.badges_title')}
                        </platform-button>
                        <platform-button size="sm" variant="accent" ?loading=${this._productsEnrich.busy}
                            title=${this.t('catalog.enrich_all_hint')} @click=${() => this._enrich([])}>
                            <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('catalog.enrich_all')}
                        </platform-button>
                        <platform-button size="sm" variant="secondary" @click=${() => this._openImport()}>
                            <platform-icon name="import" size="14"></platform-icon> ${this.t('catalog.import')}
                        </platform-button>
                        <platform-button size="sm" variant="primary" @click=${() => this._openProduct(null)}>
                            <platform-icon name="plus" size="14"></platform-icon> ${this.t('catalog.add_product')}
                        </platform-button>
                    </div>
                </shop-page-head>
                <shop-agent-jobs-banner shop-id=${this.shopId}></shop-agent-jobs-banner>
                ${this._renderBadgeEditor()}
                <div class="toolbar">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('catalog.search')}
                        .value=${this._query}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            this._query = typeof event.detail.value === 'string' ? event.detail.value : '';
                        }}
                    ></platform-field>
                    <platform-segmented-control
                        density="compact"
                        .value=${this._filter}
                        .items=${this._filterItems()}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            if (isCatalogFilter(event.detail.value)) this._filter = event.detail.value;
                        }}
                    ></platform-segmented-control>
                </div>
                ${this._renderBulkBar()}
                ${this._renderTable()}
            </div>
        `;
    }
}

customElements.define('shop-catalog-page', ShopCatalogPage);

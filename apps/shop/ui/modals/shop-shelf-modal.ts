/**
 * ShopShelfModal — редактор полки витринной ленты.
 *
 * Директор выбирает источник (ручная подборка / раздел каталога /
 * системные «новинки», «хиты», «вернулось в меню», «как всегда»,
 * апсейл корзины), раскладку карточек и место показа. Для ручных
 * источников — чипы-выбор позиций; для категорийной — раздел.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

const KINDS = ['manual', 'category', 'new', 'hits', 'comeback', 'usual', 'favorites', 'upsell'] as const;
type ShelfKind = (typeof KINDS)[number];

const LAYOUTS = ['rail', 'rows', 'grid', 'hero'] as const;
type ShelfLayout = (typeof LAYOUTS)[number];

const PLACEMENTS = ['feed', 'cart'] as const;
type ShelfPlacement = (typeof PLACEMENTS)[number];

export interface ShelfDraft {
    shop_shelf_id?: string;
    kind: ShelfKind;
    layout: ShelfLayout;
    placement: ShelfPlacement;
    title: string;
    subtitle: string;
    product_ids: string[];
    category_id: string | null;
    limit: number;
    is_active: boolean;
}

interface ProductRow {
    shop_product_id: string;
    name: string;
}

interface CategoryRow {
    shop_category_id: string;
    name: string;
}

function _str(e: CustomEvent<{ value?: unknown }>): string {
    const v = e.detail.value;
    return typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';
}

export class ShopShelfModal extends PlatformModal {
    static modalKind = 'shop.shelf';
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare shelf: ShelfDraft | null;

    private _createOp: OpController;
    private _updateOp: OpController;
    private _productsOp: OpController;
    private _categoriesOp: OpController;

    declare _kind: ShelfKind;
    declare _layout: ShelfLayout;
    declare _placement: ShelfPlacement;
    declare _title: string;
    declare _subtitle: string;
    declare _productIds: string[];
    declare _categoryId: string;
    declare _limit: string;
    declare _isActive: boolean;
    declare _products: ProductRow[];
    declare _categories: CategoryRow[];

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        shelf: { attribute: false },
        _kind: { state: true },
        _layout: { state: true },
        _placement: { state: true },
        _title: { state: true },
        _subtitle: { state: true },
        _productIds: { state: true },
        _categoryId: { state: true },
        _limit: { state: true },
        _isActive: { state: true },
        _products: { state: true },
        _categories: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
            .grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
            .chips { display: flex; gap: var(--space-1); flex-wrap: wrap; max-height: 200px; overflow-y: auto; }
            .chip {
                border: 1px solid var(--glass-border-subtle); border-radius: 999px;
                padding: 4px 12px; font-size: var(--text-xs); cursor: pointer;
                background: transparent; color: var(--text-secondary); font: inherit;
            }
            .chip.on { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
            .sec-title { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
            .toggle-row { display: flex; align-items: center; gap: var(--space-2); }
            .toggle-row span { font-size: var(--text-sm); color: var(--text-primary); }
            .actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.5; }
        `,
    ];

    constructor() {
        super();
        this._kind = 'manual';
        this._layout = 'rail';
        this._placement = 'feed';
        this._title = '';
        this._subtitle = '';
        this._productIds = [];
        this._categoryId = '';
        this._limit = '10';
        this._isActive = true;
        this._products = [];
        this._categories = [];
        this._createOp = this.useOp('shop/shelf_create');
        this._updateOp = this.useOp('shop/shelf_update');
        this._productsOp = this.useOp('shop/products_list');
        this._categoriesOp = this.useOp('shop/categories_list');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.shopId !== 'string' || this.shopId.length === 0) {
            throw new Error('ShopShelfModal: prop "shopId" required');
        }
        const s = this.shelf;
        if (s !== null && s !== undefined) {
            this._kind = s.kind;
            this._layout = s.layout;
            this._placement = s.placement;
            this._title = s.title;
            this._subtitle = s.subtitle;
            this._productIds = [...s.product_ids];
            this._categoryId = s.category_id ?? '';
            this._limit = String(s.limit);
            this._isActive = s.is_active;
        }
        void this._load();
    }

    private async _load(): Promise<void> {
        const [products, categories] = await Promise.all([
            this._productsOp.run({ shop_id: this.shopId, limit: 500 }),
            this._categoriesOp.run({ shop_id: this.shopId }),
        ]);
        const pItems = (products as { items?: unknown } | null)?.items;
        this._products = Array.isArray(pItems) ? (pItems as ProductRow[]) : [];
        const cItems = (categories as { items?: unknown } | null)?.items;
        this._categories = Array.isArray(cItems) ? (cItems as CategoryRow[]) : [];
    }

    private get _editing(): boolean {
        return this.shelf !== null && this.shelf !== undefined && typeof this.shelf.shop_shelf_id === 'string';
    }

    private get _needsProducts(): boolean {
        return this._kind === 'manual' || this._kind === 'upsell';
    }

    private get _needsCategory(): boolean {
        return this._kind === 'category';
    }

    private _toggleProduct(id: string) {
        this._productIds = this._productIds.includes(id)
            ? this._productIds.filter((x) => x !== id)
            : [...this._productIds, id];
    }

    private get _valid(): boolean {
        if (this._needsProducts && this._productIds.length === 0) return false;
        if (this._needsCategory && this._categoryId === '') return false;
        const limit = parseInt(this._limit, 10);
        return Number.isFinite(limit) && limit >= 1 && limit <= 50;
    }

    private async _save() {
        if (!this._valid || this._createOp.busy || this._updateOp.busy) return;
        const body: Record<string, unknown> = {
            layout: this._layout,
            placement: this._placement,
            title: this._title.trim(),
            subtitle: this._subtitle.trim(),
            product_ids: this._needsProducts ? this._productIds : [],
            category_id: this._needsCategory && this._categoryId !== '' ? this._categoryId : null,
            limit: parseInt(this._limit, 10),
        };
        const result = this._editing && this.shelf !== null && this.shelf.shop_shelf_id !== undefined
            ? await this._updateOp.run({
                shop_id: this.shopId,
                shop_shelf_id: this.shelf.shop_shelf_id,
                ...body,
                is_active: this._isActive,
            })
            : await this._createOp.run({ shop_id: this.shopId, kind: this._kind, ...body });
        if (result !== null) this.close();
    }

    override renderHeader(): string {
        return this._editing ? this.t('feed.shelf_edit') : this.t('feed.shelf_new');
    }

    override renderBody(): TemplateResult {
        return html`
            <div class="body">
                <div class="grid">
                    <platform-field type="enum" mode="edit" label=${this.t('feed.field_kind')} .value=${this._kind}
                        ?disabled=${this._editing}
                        .config=${{ values: KINDS.map((k) => ({ value: k, label: this.t(`feed.kind.${k}`) })) }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._kind = _str(e) as ShelfKind; }}></platform-field>
                    <platform-field type="enum" mode="edit" label=${this.t('feed.field_layout')} .value=${this._layout}
                        .config=${{ values: LAYOUTS.map((l) => ({ value: l, label: this.t(`feed.layout.${l}`) })) }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._layout = _str(e) as ShelfLayout; }}></platform-field>
                    <platform-field type="enum" mode="edit" label=${this.t('feed.field_placement')} .value=${this._placement}
                        .config=${{ values: PLACEMENTS.map((p) => ({ value: p, label: this.t(`feed.placement.${p}`) })) }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._placement = _str(e) as ShelfPlacement; }}></platform-field>
                    <platform-field type="number" mode="edit" label=${this.t('feed.field_limit')} .value=${this._limit}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._limit = _str(e); }}></platform-field>
                </div>
                <platform-field type="string" mode="edit" label=${this.t('feed.field_title')} .value=${this._title}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._title = _str(e); }}></platform-field>
                <platform-field type="string" mode="edit" label=${this.t('feed.field_subtitle')} .value=${this._subtitle}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._subtitle = _str(e); }}></platform-field>
                ${this._needsCategory ? html`
                    <platform-field type="enum" mode="edit" label=${this.t('feed.field_category')} .value=${this._categoryId}
                        .config=${{ values: this._categories.map((c) => ({ value: c.shop_category_id, label: c.name })) }}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._categoryId = _str(e); }}></platform-field>
                ` : nothing}
                ${this._needsProducts ? html`
                    <div class="sec-title">${this.t('feed.products_title')}</div>
                    <div class="chips">
                        ${this._products.map((p) => html`
                            <button class="chip ${this._productIds.includes(p.shop_product_id) ? 'on' : ''}"
                                @click=${() => this._toggleProduct(p.shop_product_id)}>${p.name}</button>
                        `)}
                    </div>
                ` : nothing}
                ${this._kind !== 'manual' && this._kind !== 'category' && this._kind !== 'upsell' ? html`
                    <div class="hint">${this.t(`feed.hint_${this._kind}`)}</div>
                ` : nothing}
                ${this._editing ? html`
                    <div class="toggle-row">
                        <platform-switch ?checked=${this._isActive}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._isActive = Boolean(e.detail.value); }}></platform-switch>
                        <span>${this.t('feed.field_active')}</span>
                    </div>
                ` : nothing}
                <div class="actions">
                    <platform-button variant="secondary" @click=${() => this.close()}>${this.t('menu.cancel')}</platform-button>
                    <platform-button variant="primary" ?loading=${this._createOp.busy || this._updateOp.busy}
                        ?disabled=${!this._valid} @click=${() => this._save()}>${this.t('menu.save')}</platform-button>
                </div>
            </div>`;
    }
}

customElements.define('shop-shelf-modal', ShopShelfModal);
registerModalKind(ShopShelfModal.modalKind, 'shop-shelf-modal');

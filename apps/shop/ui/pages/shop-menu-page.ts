/**
 * Конструктор меню: рейка категорий слева + карточки позиций.
 * Создание и редактирование позиции — ShopProductModal; метки и импорт —
 * раскрывающиеся панели над списком.
 */

import { html, css, nothing } from 'lit';
import type { PropertyValues } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import type { ProductDraft } from '../modals/shop-product-modal.js';
import { PlatformCatalogProductPicker } from '@platform/lib/catalog/product-picker.js';
import type { CatalogProductPick } from '@platform/lib/catalog/product-picker.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import '../components/shop-category-tree.js';
import type { ShopTreeReorderItem } from '../components/shop-category-tree.js';
import '../components/shop-page-head.js';
import { shopHeadRow } from '../components/shop-page-head.js';
import type { ShopHeadRow } from '../components/shop-page-head.js';

const PRODUCT_MIME = 'application/x-shop-product-id';

interface CategoryRow {
    shop_category_id: string;
    parent_id: string | null;
    name: string;
    sort: number;
    is_active: boolean;
}

interface ProductRow {
    product_id: string;
    category_id: string | null;
    name: string;
    description: string;
    price_minor: number;
    photo_file_id: string | null;
    nutrition: { kcal?: number; protein_g?: number; fat_g?: number; carb_g?: number };
    ingredients: string[];
    allergens: string[];
    is_available: boolean;
    is_archived: boolean;
    portion: string;
    badges: string[];
    sort: number;
    sources: Record<string, string>;
}

interface ShopBadgeDef {
    key: string;
    label: string;
    icon: string;
    icon_path: string;
}

const IMPORT_ALLERGENS = [
    'gluten', 'dairy', 'egg', 'fish', 'shellfish', 'nuts', 'peanuts',
    'soy', 'sesame', 'mustard', 'celery', 'lupin', 'molluscs', 'sulphites',
] as const;

interface MenuImportNutrition {
    kcal?: number;
    protein_g?: number;
    fat_g?: number;
    carb_g?: number;
}

interface MenuImportItemRow {
    item_id: string;
    section_name: string;
    name: string;
    description: string;
    price_minor: number;
    portion: string;
    nutrition: MenuImportNutrition;
    nutrition_is_per_100g: boolean;
    ingredients: string[];
    allergens: string[];
    photo_file_id: string | null;
    matched_product_id: string | null;
}

interface MenuImportDraftRow {
    shop_id: string;
    status: 'parsing' | 'ready' | 'failed';
    failure_reason: string;
    items: MenuImportItemRow[];
}

function _eventString(event: CustomEvent<{ value?: unknown }>): string {
    const value = event.detail.value;
    return typeof value === 'string' ? value : typeof value === 'number' ? String(value) : '';
}

function _stringList(value: unknown): string[] {
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is string => typeof item === 'string');
}

function _nutrition(value: unknown): MenuImportNutrition {
    if (typeof value !== 'object' || value === null) return {};
    const raw = value as Record<string, unknown>;
    const nutrition: MenuImportNutrition = {};
    for (const key of ['kcal', 'protein_g', 'fat_g', 'carb_g'] as const) {
        const number = raw[key];
        if (typeof number === 'number') nutrition[key] = number;
    }
    return nutrition;
}

function _menuImportItem(value: unknown): MenuImportItemRow | null {
    if (typeof value !== 'object' || value === null) return null;
    const raw = value as Record<string, unknown>;
    if (typeof raw.item_id !== 'string' || typeof raw.name !== 'string') return null;
    if (typeof raw.price_minor !== 'number') return null;
    return {
        item_id: raw.item_id,
        section_name: typeof raw.section_name === 'string' ? raw.section_name : '',
        name: raw.name,
        description: typeof raw.description === 'string' ? raw.description : '',
        price_minor: raw.price_minor,
        portion: typeof raw.portion === 'string' ? raw.portion : '',
        nutrition: _nutrition(raw.nutrition),
        nutrition_is_per_100g: raw.nutrition_is_per_100g === true,
        ingredients: _stringList(raw.ingredients),
        allergens: _stringList(raw.allergens),
        photo_file_id: typeof raw.photo_file_id === 'string' ? raw.photo_file_id : null,
        matched_product_id: typeof raw.matched_product_id === 'string' ? raw.matched_product_id : null,
    };
}

function _menuImportDraft(value: unknown): MenuImportDraftRow | null {
    if (typeof value !== 'object' || value === null) return null;
    const raw = value as Record<string, unknown>;
    if (raw.status !== 'parsing' && raw.status !== 'ready' && raw.status !== 'failed') return null;
    if (typeof raw.shop_id !== 'string' || !Array.isArray(raw.items)) return null;
    const items: MenuImportItemRow[] = [];
    for (const item of raw.items) {
        const parsed = _menuImportItem(item);
        if (parsed === null) return null;
        items.push(parsed);
    }
    return {
        shop_id: raw.shop_id,
        status: raw.status,
        failure_reason: typeof raw.failure_reason === 'string' ? raw.failure_reason : '',
        items,
    };
}

interface ShopRow extends ShopHeadRow {
    badges: ShopBadgeDef[];
    features?: Record<string, unknown>;
}

export class ShopMenuPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _shops: ResourceController;
    private _shopUpdateOp: OpController;
    private _badgeIconsOp: OpController;
    private _categoriesOp: OpController;
    private _productsOp: OpController;
    private _categoryCreateOp: OpController;
    private _categoryUpdateOp: OpController;
    private _categoryRemoveOp: OpController;
    private _categoryReorderOp: OpController;
    private _productUpdateOp: OpController;
    private _productRemoveOp: OpController;
    private _productReorderOp: OpController;
    private _importGetOp: OpController;
    private _importStartOp: OpController;
    private _importUpdateOp: OpController;
    private _importPublishOp: OpController;
    private _importDiscardOp: OpController;
    private _aiDescribeBatchOp: OpController;
    private _aiEnhanceOp: OpController;
    private _aiGenerateOp: OpController;
    private _uploadOp: OpController;
    private _locale: SelectController<string>;

    declare _badgeIcons: Record<string, string>;
    declare _badgeEditorOpen: boolean;
    declare _newBadgeLabel: string;
    declare _newBadgeIcon: string;
    declare _activeCategory: string | null;
    declare _expandedIds: string[];
    declare _importOpen: boolean;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        _badgeIcons: { state: true },
        _badgeEditorOpen: { state: true },
        _newBadgeLabel: { state: true },
        _newBadgeIcon: { state: true },
        _activeCategory: { state: true },
        _expandedIds: { state: true },
        _importOpen: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { padding: var(--space-5) var(--space-6) var(--space-10); }

            .head-actions { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }

            .layout { display: grid; grid-template-columns: 232px minmax(0, 1fr); gap: var(--space-5); align-items: start; }

            .rail {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-2);
                position: sticky;
                top: var(--space-4);
                min-width: 0;
            }
            .rail shop-category-tree { display: block; }
            .card[draggable="true"] { cursor: grab; }
            .card.dragging { opacity: 0.4; }

            .list { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: var(--space-3); min-width: 0; }
            .card {
                display: flex; align-items: center; gap: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-3);
                flex-wrap: wrap;
            }
            .card:hover { border-color: color-mix(in srgb, var(--text-primary) 18%, transparent); }
            .card.off { opacity: 0.55; }
            .card.archived { opacity: 0.45; border-style: dashed; }
            .atag {
                display: inline-flex; align-items: center; gap: 3px; padding: 1px var(--space-2);
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--text-primary) 10%, transparent);
                color: var(--text-secondary); font-size: 10px; font-weight: var(--font-bold);
            }
            .atag platform-icon { color: var(--text-secondary); }
            .thumb {
                width: 56px; height: 56px; border-radius: var(--radius-md);
                object-fit: cover; display: block; flex-shrink: 0;
            }
            .thumb-empty {
                width: 56px; height: 56px; border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--text-primary) 5%, transparent);
                display: flex; align-items: center; justify-content: center;
                color: var(--text-tertiary); flex-shrink: 0;
            }
            .pinfo { flex: 1; min-width: 0; }
            .pname {
                display: flex; align-items: center; gap: var(--space-1); flex-wrap: wrap;
                font-weight: var(--font-semibold); color: var(--text-primary);
                font-size: var(--text-sm); line-height: 1.3;
            }
            .portion { color: var(--text-tertiary); font-size: var(--text-xs); font-weight: var(--font-normal); }
            .pdesc {
                color: var(--text-tertiary); font-size: var(--text-xs); line-height: 1.45;
                margin-top: 2px;
                display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
            }
            .ptag {
                display: inline-flex; align-items: center; padding: 1px var(--space-2);
                border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent); font-size: 10px; font-weight: var(--font-bold);
            }
            .ptag svg { width: 11px; height: 11px; fill: currentColor; }
            .price { font-variant-numeric: tabular-nums; font-weight: var(--font-semibold); color: var(--text-primary); white-space: nowrap; }
            .price::after { content: ' ₽'; font-weight: var(--font-normal); color: var(--text-tertiary); }
            .ops { display: flex; gap: 2px; align-items: center; opacity: 0; transition: opacity 0.15s; margin-left: auto; }
            .card:hover .ops, .card:focus-within .ops { opacity: 1; }

            .badges { display: flex; flex-wrap: wrap; gap: var(--space-1); }
            .bchip {
                display: inline-flex; align-items: center; gap: var(--space-1);
                padding: var(--space-1) var(--space-2); border-radius: var(--radius-full);
                border: 1px solid var(--border-default); background: var(--surface-secondary);
                color: var(--text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium);
            }
            .bchip svg { width: 13px; height: 13px; fill: currentColor; }
            .bchip .x { cursor: pointer; display: inline-flex; opacity: 0.6; }
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
            .import-stats { display: flex; gap: var(--space-4); font-size: var(--text-sm); }
            .import-stats .ok { color: var(--success); }
            .import-stats .bad { color: var(--warning); }
            .import-groups { display: flex; flex-direction: column; gap: var(--space-5); }
            .import-groups > section { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
            .sec-title { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
            .import-heading {
                font-size: var(--text-lg); font-weight: var(--font-semibold);
                color: var(--text-primary); line-height: 1.3;
            }
            .import-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
                gap: var(--space-3);
            }
            .import-card {
                display: flex; flex-direction: column; min-width: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                overflow: hidden;
            }
            .import-photo {
                position: relative; width: 100%; aspect-ratio: 16 / 10;
                background: color-mix(in srgb, var(--text-primary) 6%, transparent);
            }
            .import-photo img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; display: block; }
            .import-photo-empty {
                position: absolute; inset: 0;
                display: flex; align-items: center; justify-content: center;
                color: var(--text-tertiary);
            }
            .import-flag {
                position: absolute; top: var(--space-2); left: var(--space-2);
                padding: 2px var(--space-2); border-radius: var(--radius-full);
                background: color-mix(in srgb, var(--bg-surface) 88%, transparent);
                color: var(--success); font-size: var(--text-xs); font-weight: var(--font-semibold);
            }
            .import-body {
                display: flex; flex-direction: column; gap: var(--space-3);
                padding: var(--space-3); min-width: 0;
            }
            .import-body platform-field { display: block; width: 100%; min-width: 0; }
            .import-pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr); gap: var(--space-2); }
            .import-nutri { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-2); }
            .import-note { color: var(--warning); font-size: var(--text-xs); line-height: 1.4; }
            .import-actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
            button.bchip { cursor: pointer; font: inherit; }
            button.bchip.on {
                border-color: var(--accent);
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent);
            }
            .panel-actions { display: flex; gap: var(--space-2); justify-content: flex-end; }

            platform-empty-state { margin-top: var(--space-8); }

            @media (max-width: 900px) {
                .layout { grid-template-columns: 1fr; }
                .rail { position: static; }
            }
            @media (max-width: 640px) {
                .card { flex-wrap: wrap; }
                .ops { opacity: 1; }
            }
        `,
    ];

    constructor() {
        super();
        this._badgeIcons = {};
        this._badgeEditorOpen = false;
        this._newBadgeLabel = '';
        this._newBadgeIcon = '';
        this._activeCategory = null;
        this._expandedIds = [];
        this._importOpen = false;
        this._shops = this.useResource('shop/shops');
        this._shopUpdateOp = this.useOp('shop/shop_update');
        this._badgeIconsOp = this.useOp('shop/badge_icons_list');
        this._categoriesOp = this.useOp('shop/categories_list');
        this._productsOp = this.useOp('shop/products_list');
        this._categoryCreateOp = this.useOp('shop/category_create');
        this._categoryUpdateOp = this.useOp('shop/category_update');
        this._categoryRemoveOp = this.useOp('shop/category_remove');
        this._categoryReorderOp = this.useOp('shop/categories_reorder');
        this._productUpdateOp = this.useOp('shop/product_update');
        this._productRemoveOp = this.useOp('shop/product_remove');
        this._productReorderOp = this.useOp('shop/products_reorder');
        this._importGetOp = this.useOp('shop/menu_import_get');
        this._importStartOp = this.useOp('shop/menu_import_start');
        this._importUpdateOp = this.useOp('shop/menu_import_update');
        this._importPublishOp = this.useOp('shop/menu_import_publish');
        this._importDiscardOp = this.useOp('shop/menu_import_discard');
        this._aiDescribeBatchOp = this.useOp('shop/ai_describe_batch');
        this._aiEnhanceOp = this.useOp('shop/ai_enhance_photo');
        this._aiGenerateOp = this.useOp('shop/ai_generate_photo');
        this._uploadOp = this.useOp('platform/file_create');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._reload();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const prevShopId = changed.get('shopId');
        if (typeof prevShopId === 'string' && prevShopId !== this.shopId) {
            this._activeCategory = null;
            this._expandedIds = [];
            void this._reload();
        }
    }

    /** Списки читаются из lastResult опов — push-перезапуски обновляют
     * страницу реактивно, без локальных копий. */
    private get _categories(): CategoryRow[] {
        return this._rows<CategoryRow>(this._categoriesOp.lastResult);
    }

    private get _products(): ProductRow[] {
        return this._rows<ProductRow>(this._productsOp.lastResult);
    }

    private async _reload() {
        if (this.shopId === '') return;
        await Promise.all([
            this._categoriesOp.run({ shop_id: this.shopId }),
            this._productsOp.run({ shop_id: this.shopId }),
            this._shops.load(),
        ]);
        const first = this._categories.find((c) => c.parent_id === null);
        if (this._activeCategory === null && first !== undefined) {
            this._activeCategory = first.shop_category_id;
        }
        const ids = this._categories.map((c) => c.shop_category_id);
        const expanded = new Set(this._expandedIds);
        if (ids.some((id) => !expanded.has(id))) {
            this._expandedIds = [...expanded, ...ids];
        }
    }

    private _shop(): ShopRow | null {
        const raw = this._shops.items.find((s) => (s as { shop_id?: string }).shop_id === this.shopId);
        const head = shopHeadRow(raw);
        if (head === null) return null;
        const badges = (raw as { badges?: unknown }).badges;
        const features = (raw as { features?: unknown }).features;
        return {
            ...head,
            badges: Array.isArray(badges) ? (badges as ShopBadgeDef[]) : [],
            features: typeof features === 'object' && features !== null ? (features as Record<string, unknown>) : {},
        };
    }

    private _shopBadges(): ShopBadgeDef[] {
        return this._shop()?.badges ?? [];
    }

    private _nutritionEnabled(): boolean {
        return this._shop()?.features?.nutrition === true;
    }

    private async _openBadgeEditor() {
        this._badgeEditorOpen = !this._badgeEditorOpen;
        if (this._badgeEditorOpen && Object.keys(this._badgeIcons).length === 0) {
            const result = await this._badgeIconsOp.run({});
            if (result !== null && typeof result === 'object' && 'icons' in (result as Record<string, unknown>)) {
                this._badgeIcons = (result as { icons?: Record<string, string> }).icons ?? {};
            }
        }
    }

    private _iconSvg(path: string) {
        return unsafeHTML(`<svg viewBox="0 -960 960 960"><path d="${path}"/></svg>`);
    }

    private async _saveBadgeDefs(badges: Array<{ key?: string; label: string; icon: string }>) {
        await this._shopUpdateOp.run({ shop_id: this.shopId, badges });
        await this._shops.load();
    }

    private async _addBadgeDef() {
        const label = this._newBadgeLabel.trim();
        if (label === '' || this._newBadgeIcon === '') return;
        const current = this._shopBadges().map((b) => ({ key: b.key, label: b.label, icon: b.icon }));
        await this._saveBadgeDefs([...current, { label, icon: this._newBadgeIcon }]);
        this._newBadgeLabel = '';
        this._newBadgeIcon = '';
    }

    private async _removeBadgeDef(key: string) {
        await this._saveBadgeDefs(
            this._shopBadges()
                .filter((b) => b.key !== key)
                .map((b) => ({ key: b.key, label: b.label, icon: b.icon })),
        );
    }

    private _rows<T>(result: unknown): T[] {
        if (result !== null && typeof result === 'object' && 'items' in (result as Record<string, unknown>)) {
            const items = (result as { items?: unknown }).items;
            if (Array.isArray(items)) return items as T[];
        }
        return [];
    }

    private _money(minor: number): string {
        return formatPlatformNumber(minor / 100, this._locale.value, { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    }

    /** id узла и всех потомков — фильтр списка товаров по поддереву. */
    private _subtreeIds(id: string): Set<string> {
        const out = new Set<string>([id]);
        const queue = [id];
        while (queue.length > 0) {
            const parent = queue.shift();
            for (const c of this._categories) {
                if (c.parent_id === parent && !out.has(c.shop_category_id)) {
                    out.add(c.shop_category_id);
                    queue.push(c.shop_category_id);
                }
            }
        }
        return out;
    }

    /** Товары в поддереве каждой категории — счётчики строк дерева. */
    private _subtreeCounts(): Record<string, number> {
        const counts: Record<string, number> = {};
        for (const c of this._categories) {
            counts[c.shop_category_id] = this._products.filter(
                (p) => p.category_id !== null && this._subtreeIds(c.shop_category_id).has(p.category_id),
            ).length;
        }
        return counts;
    }

    private async _createCategory(parentId: string | null, name: string) {
        const result = await this._categoryCreateOp.run({ shop_id: this.shopId, name, parent_id: parentId });
        if (result !== null) {
            await this._reload();
        }
    }

    private async _renameCategory(categoryId: string, name: string) {
        await this._categoryUpdateOp.run({
            shop_id: this.shopId,
            shop_category_id: categoryId,
            name,
        });
        await this._reload();
    }

    private async _reorderTree(items: ShopTreeReorderItem[]) {
        await this._categoryReorderOp.run({ shop_id: this.shopId, items });
        await this._reload();
    }

    private async _dropProduct(productId: string, categoryId: string | null) {
        await this._productUpdateOp.run({
            shop_id: this.shopId,
            product_id: productId,
            category_id: categoryId,
        });
        await this._reload();
    }

    private async _removeCategory(categoryId: string) {
        await this._categoryRemoveOp.run({ shop_id: this.shopId, shop_category_id: categoryId });
        if (this._activeCategory !== null && this._subtreeIds(categoryId).has(this._activeCategory)) {
            this._activeCategory = null;
        }
        await this._reload();
    }

    private _onProductDragStart(e: DragEvent, productId: string): void {
        e.dataTransfer?.setData(PRODUCT_MIME, productId);
        if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
        (e.currentTarget as HTMLElement).classList.add('dragging');
    }

    private _onProductDragEnd(e: DragEvent): void {
        (e.currentTarget as HTMLElement).classList.remove('dragging');
    }

    private _openProductModal(product?: ProductRow) {
        if (product === undefined) {
            this.openModal(PlatformCatalogProductPicker, {
                suggestOpName: 'shop/catalog_products_suggest',
                onPick: (item: CatalogProductPick) => {
                    this.openModal('shop.product', {
                        shopId: this.shopId,
                        categoryId: this._activeCategory,
                        product: null,
                        attachProduct: item,
                        badgeDefs: this._shopBadges(),
                        nutritionEnabled: this._nutritionEnabled(),
                        onSaved: () => void this._reload(),
                    });
                },
                onCreateNew: (initialName: string) => {
                    this.openModal('shop.product', {
                        shopId: this.shopId,
                        categoryId: this._activeCategory,
                        product: null,
                        initialName,
                        badgeDefs: this._shopBadges(),
                        nutritionEnabled: this._nutritionEnabled(),
                        onSaved: () => void this._reload(),
                    });
                },
            });
            return;
        }
        const draft: ProductDraft = {
            product_id: product.product_id,
            name: product.name,
            description: product.description,
            price_minor: product.price_minor,
            portion: product.portion,
            badges: [...product.badges],
            photo_file_id: product.photo_file_id,
            nutrition: { ...product.nutrition },
            ingredients: [...product.ingredients],
            allergens: [...product.allergens],
            is_available: product.is_available,
            sources: { ...product.sources },
        };
        this.openModal('shop.product', {
            shopId: this.shopId,
            categoryId: product.category_id,
            product: draft,
            badgeDefs: this._shopBadges(),
            nutritionEnabled: this._nutritionEnabled(),
            onSaved: () => void this._reload(),
        });
    }

    private async _uploadProductPhoto(p: ProductRow, event: Event) {
        const input = event.target as HTMLInputElement;
        const file = input.files && input.files[0];
        if (!file) return;
        const result = await this._uploadOp.run({
            file,
            spec: buildShopProductFileCreateSpecJson({ shopId: this.shopId, productId: p.product_id }),
        });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                await this._productUpdateOp.run({
                    shop_id: this.shopId,
                    product_id: p.product_id,
                    photo_file_id: fileId,
                });
                await this._reload();
            }
        }
        input.value = '';
    }

    private async _enhancePhoto(product: ProductRow) {
        if (!product.photo_file_id) return;
        const result = await this._aiEnhanceOp.run({ shop_id: this.shopId, file_id: product.photo_file_id });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                await this._productUpdateOp.run({
                    shop_id: this.shopId,
                    product_id: product.product_id,
                    photo_file_id: fileId,
                });
                await this._reload();
            }
        }
    }

    private async _generatePhoto(product: ProductRow) {
        const result = await this._aiGenerateOp.run({ shop_id: this.shopId, name: product.name, description: product.description });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                await this._productUpdateOp.run({
                    shop_id: this.shopId,
                    product_id: product.product_id,
                    photo_file_id: fileId,
                });
                await this._reload();
            }
        }
    }

    private async _toggleAvailable(product: ProductRow, enabled: boolean) {
        await this._productUpdateOp.run({
            shop_id: this.shopId,
            product_id: product.product_id,
            is_available: enabled,
        });
        await this._reload();
    }

    private async _runAiBatch() {
        const missing = this._products.filter((p) => !p.description?.trim()).length;
        if (missing === 0) return;
        await this._aiDescribeBatchOp.run({ shop_id: this.shopId });
    }

    private _importDraft(): MenuImportDraftRow | null {
        return _menuImportDraft(this._importGetOp.lastResult);
    }

    private async _toggleImport() {
        this._importOpen = !this._importOpen;
        if (this._importOpen) {
            await this._importGetOp.run({ shop_id: this.shopId });
        }
    }

    private async _refreshImport() {
        await this._importGetOp.run({ shop_id: this.shopId });
    }

    private async _startImport(event: Event) {
        const input = event.target as HTMLInputElement;
        const selected = input.files;
        if (selected === null || selected.length === 0) return;
        const fileIds: string[] = [];
        for (const file of Array.from(selected)) {
            const uploaded = await this._uploadOp.run({
                file,
                spec: buildShopProductFileCreateSpecJson({ shopId: this.shopId }),
            });
            if (uploaded === null || typeof uploaded !== 'object' || !('file_id' in uploaded)) {
                input.value = '';
                return;
            }
            const fileId = (uploaded as { file_id?: unknown }).file_id;
            if (typeof fileId !== 'string' || fileId === '') {
                input.value = '';
                return;
            }
            fileIds.push(fileId);
        }
        input.value = '';
        const started = await this._importStartOp.run({ shop_id: this.shopId, file_ids: fileIds });
        if (started !== null) await this._refreshImport();
    }

    private async _saveImportItem(item: MenuImportItemRow, patch: Partial<MenuImportItemRow>) {
        const next: MenuImportItemRow = { ...item, ...patch };
        const saved = await this._importUpdateOp.run({
            shop_id: this.shopId,
            item_id: next.item_id,
            section_name: next.section_name,
            name: next.name,
            description: next.description,
            price_minor: next.price_minor,
            portion: next.portion,
            nutrition: next.nutrition,
            nutrition_is_per_100g: next.nutrition_is_per_100g,
            ingredients: next.ingredients,
            allergens: next.allergens,
            photo_file_id: next.photo_file_id,
        });
        if (saved !== null) await this._refreshImport();
    }

    private async _publishImport(itemIds: string[]) {
        const published = await this._importPublishOp.run({
            shop_id: this.shopId,
            item_ids: itemIds,
        });
        if (published !== null) {
            await this._refreshImport();
            await this._reload();
        }
    }

    private async _discardImport(itemId: string | null) {
        const discarded = await this._importDiscardOp.run({
            shop_id: this.shopId,
            item_id: itemId,
        });
        if (discarded !== null) await this._refreshImport();
    }

    private _allergenLabel(code: string): string {
        switch (code) {
            case 'gluten': return this.t('menu.allergen_gluten');
            case 'dairy': return this.t('menu.allergen_dairy');
            case 'egg': return this.t('menu.allergen_egg');
            case 'fish': return this.t('menu.allergen_fish');
            case 'shellfish': return this.t('menu.allergen_shellfish');
            case 'nuts': return this.t('menu.allergen_nuts');
            case 'peanuts': return this.t('menu.allergen_peanuts');
            case 'soy': return this.t('menu.allergen_soy');
            case 'sesame': return this.t('menu.allergen_sesame');
            case 'mustard': return this.t('menu.allergen_mustard');
            case 'celery': return this.t('menu.allergen_celery');
            case 'lupin': return this.t('menu.allergen_lupin');
            case 'molluscs': return this.t('menu.allergen_molluscs');
            case 'sulphites': return this.t('menu.allergen_sulphites');
            default: throw new Error(`ShopMenuPage: unknown allergen ${code}`);
        }
    }

    private _importGroups(items: MenuImportItemRow[]): Array<{ name: string; items: MenuImportItemRow[] }> {
        const names: string[] = [];
        const byName = new Map<string, MenuImportItemRow[]>();
        for (const item of items) {
            const bucket = byName.get(item.section_name);
            if (bucket === undefined) {
                names.push(item.section_name);
                byName.set(item.section_name, [item]);
            } else {
                bucket.push(item);
            }
        }
        return names.map((name) => {
            const grouped = byName.get(name);
            if (grouped === undefined) {
                throw new Error(`ShopMenuPage: import section ${name} disappeared`);
            }
            return { name, items: grouped };
        });
    }

    private _renderImportItem(item: MenuImportItemRow) {
        const price = (item.price_minor / 100).toString();
        const nutrition = item.nutrition;
        return html`
            <article class="import-card">
                <div class="import-photo">
                    ${item.photo_file_id !== null
                        ? html`<img src="/shop/api/v1/files/download/${item.photo_file_id}?v=lg" alt="">`
                        : html`<span class="import-photo-empty"><platform-icon name="image" size="28"></platform-icon></span>`}
                    ${item.matched_product_id !== null
                        ? html`<span class="import-flag">${this.t('menu.import_already')}</span>`
                        : nothing}
                </div>
                <div class="import-body">
                    <platform-field type="string" mode="edit" pill-density="compact" label=${this.t('menu.field_name')} .value=${item.name}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            const name = _eventString(event);
                            if (name !== '') void this._saveImportItem(item, { name });
                        }}></platform-field>
                    <div class="import-pair">
                        <platform-field type="number" mode="edit" pill-density="compact" label=${this.t('menu.field_price')} .value=${price}
                            @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                const major = parseFloat(_eventString(event).replace(',', '.'));
                                if (!Number.isFinite(major) || major < 0) return;
                                void this._saveImportItem(item, { price_minor: Math.round(major * 100) });
                            }}></platform-field>
                        <platform-field type="string" mode="edit" pill-density="compact" label=${this.t('menu.field_portion')} .value=${item.portion}
                            @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                void this._saveImportItem(item, { portion: _eventString(event) });
                            }}></platform-field>
                    </div>
                    <platform-field type="text" mode="edit" pill-density="compact" label=${this.t('menu.field_description')} .value=${item.description}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            void this._saveImportItem(item, { description: _eventString(event) });
                        }}></platform-field>
                    <platform-field type="string" mode="edit" pill-density="compact" label=${this.t('menu.import_section')} .value=${item.section_name}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            void this._saveImportItem(item, { section_name: _eventString(event) });
                        }}></platform-field>
                    <platform-field type="array" mode="edit" pill-density="compact" label=${this.t('menu.field_ingredients')}
                        .value=${item.ingredients}
                        .config=${{ preserve_case: true }}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            const value = event.detail.value;
                            const ingredients = Array.isArray(value)
                                ? value.filter((entry): entry is string => typeof entry === 'string')
                                : [];
                            void this._saveImportItem(item, { ingredients });
                        }}></platform-field>
                    <div class="sec-title">${this.t('menu.field_allergens')}</div>
                    <div class="badges">
                        ${IMPORT_ALLERGENS.map((code) => html`
                            <button type="button" class="bchip ${item.allergens.includes(code) ? 'on' : ''}"
                                @click=${() => {
                                    const allergens = item.allergens.includes(code)
                                        ? item.allergens.filter((entry) => entry !== code)
                                        : [...item.allergens, code];
                                    void this._saveImportItem(item, { allergens });
                                }}>${this._allergenLabel(code)}</button>`)}
                    </div>
                    <div class="sec-title">${this.t('menu.nutrition_title')}</div>
                    ${item.nutrition_is_per_100g
                        ? html`<div class="import-note">${this.t('menu.import_nutrition_per_100')}</div>`
                        : nothing}
                    <div class="import-nutri">
                        ${(['kcal', 'protein_g', 'fat_g', 'carb_g'] as const).map((key) => html`
                            <platform-field type="number" mode="edit" pill-density="compact" label=${this._nutriLabel(key)}
                                .value=${nutrition[key] === undefined ? '' : String(nutrition[key])}
                                @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                    const raw = _eventString(event);
                                    const next = { ...nutrition };
                                    if (raw.trim() === '') {
                                        delete next[key];
                                    } else {
                                        const number = parseFloat(raw.replace(',', '.'));
                                        if (!Number.isFinite(number) || number < 0) return;
                                        next[key] = number;
                                    }
                                    void this._saveImportItem(item, {
                                        nutrition: next,
                                        nutrition_is_per_100g: false,
                                    });
                                }}></platform-field>`)}
                    </div>
                    <div class="import-actions">
                        <platform-button density="compact" variant="primary" ?loading=${this._importPublishOp.busy}
                            @click=${() => this._publishImport([item.item_id])}>${this.t('menu.import_publish_one')}</platform-button>
                        <platform-button density="compact" variant="secondary" ?loading=${this._importDiscardOp.busy}
                            @click=${() => this._discardImport(item.item_id)}>${this.t('menu.import_discard')}</platform-button>
                    </div>
                </div>
            </article>`;
    }

    private _nutriLabel(key: 'kcal' | 'protein_g' | 'fat_g' | 'carb_g'): string {
        switch (key) {
            case 'kcal': return this.t('menu.nutri_kcal');
            case 'protein_g': return this.t('menu.nutri_protein');
            case 'fat_g': return this.t('menu.nutri_fat');
            case 'carb_g': return this.t('menu.nutri_carb');
        }
    }

    private _renderImportPanel() {
        const draft = this._importDraft();
        const parsing = draft !== null && draft.status === 'parsing';
        const failed = draft !== null && draft.status === 'failed';
        return html`
            <div class="panel">
                <div class="panel-title">${this.t('menu.import_button')}</div>
                <div class="panel-hint">${this.t('menu.import_capabilities')}</div>
                <div class="panel-actions">
                    <platform-button density="compact" variant="accent" ?loading=${this._uploadOp.busy || this._importStartOp.busy || parsing}
                        @click=${() => this.renderRoot.querySelector<HTMLInputElement>('#menu-import-files')?.click()}>
                        ${this.t('menu.import_start')}
                    </platform-button>
                    <input id="menu-import-files" type="file" multiple
                        accept="image/*,application/pdf,.csv,.tsv,.xls,.xlsx,.doc,.docx"
                        style="display:none" @change=${(event: Event) => this._startImport(event)}>
                    ${draft !== null && draft.items.length > 0 ? html`
                        <platform-button density="compact" variant="primary" ?loading=${this._importPublishOp.busy}
                            @click=${() => this._publishImport([])}>${this.t('menu.import_publish_all')} · ${draft.items.length}</platform-button>
                        <platform-button density="compact" variant="secondary" ?loading=${this._importDiscardOp.busy}
                            @click=${() => this._discardImport(null)}>${this.t('menu.import_discard_all')}</platform-button>
                    ` : nothing}
                    <platform-button density="compact" variant="secondary" @click=${() => { this._importOpen = false; }}>${this.t('menu.import_close')}</platform-button>
                </div>
                ${parsing ? html`<div class="panel-hint">${this.t('menu.import_parsing')}</div>` : nothing}
                ${failed ? html`<div class="panel-hint">${draft.failure_reason === 'menu_unreadable' ? this.t('menu.import_failed') : draft.failure_reason}</div>` : nothing}
                ${draft !== null && draft.status === 'ready' && draft.items.length === 0
                    ? html`<div class="panel-hint">${this.t('menu.import_empty_draft')}</div>`
                    : nothing}
                ${draft !== null ? html`
                    <div class="import-groups">
                        ${this._importGroups(draft.items).map((group) => html`
                            <section>
                                <div class="import-heading">${group.name.trim() === '' ? this.t('menu.import_untitled_section') : group.name}</div>
                                <div class="import-grid">
                                    ${group.items.map((item) => this._renderImportItem(item))}
                                </div>
                            </section>
                        `)}
                    </div>
                ` : nothing}
            </div>`;
    }

    private _openModifiers(product: ProductRow) {
        this.openModal('shop.modifiers', {
            shopId: this.shopId,
            productId: product.product_id,
            productName: product.name,
            nutritionEnabled: this._nutritionEnabled(),
        });
    }

    private async _move(product: ProductRow, dir: -1 | 1) {
        const list = this._activeCategory === null
            ? this._products
            : this._products.filter((p) => p.category_id === this._activeCategory);
        const idx = list.findIndex((p) => p.product_id === product.product_id);
        const swap = list[idx + dir];
        if (idx < 0 || swap === undefined) return;
        const ids = list.map((p) => p.product_id);
        const idA = ids[idx];
        const idB = ids[idx + dir];
        if (idA === undefined || idB === undefined) return;
        ids[idx] = idB;
        ids[idx + dir] = idA;
        await this._productReorderOp.run({ shop_id: this.shopId, product_ids: ids });
        await this._reload();
    }

    private async _removeProduct(product: ProductRow) {
        await this._productRemoveOp.run({
            shop_id: this.shopId,
            product_id: product.product_id,
        });
        await this._reload();
    }

    private _renderProduct(p: ProductRow, index: number, total: number) {
        const badgeDefs = this._shopBadges();
        return html`
            <div class="card ${p.is_available ? '' : 'off'} ${p.is_archived ? 'archived' : ''}"
                draggable="true"
                @dragstart=${(e: DragEvent) => this._onProductDragStart(e, p.product_id)}
                @dragend=${(e: DragEvent) => this._onProductDragEnd(e)}>
                ${p.photo_file_id
                    ? html`<img class="thumb" src="/shop/api/v1/files/download/${p.photo_file_id}?v=sm!sq" alt="" loading="lazy">`
                    : html`<span class="thumb-empty"><platform-icon name="image" size="18"></platform-icon></span>`}
                <div class="pinfo">
                    <div class="pname">
                        ${p.name}
                        ${p.is_archived
                            ? html`<span class="atag"><platform-icon name="box" size="11"></platform-icon>${this.t('menu.archived')}</span>`
                            : nothing}
                        ${p.portion !== '' ? html`<span class="portion">${p.portion}</span>` : nothing}
                        ${p.badges.map((b) => {
                            const d = badgeDefs.find((x) => x.key === b);
                            return d !== undefined ? html`<span class="ptag" title=${d.label}>${this._iconSvg(d.icon_path)}</span>` : nothing;
                        })}
                    </div>
                    ${p.description.trim() !== '' ? html`<div class="pdesc">${p.description}</div>` : nothing}
                </div>
                <span class="price">${this._money(p.price_minor)}</span>
                <platform-switch
                    size="sm"
                    title=${this.t('menu.col_available')}
                    ?checked=${p.is_available && !p.is_archived}
                    ?disabled=${p.is_archived}
                    @change=${(event: CustomEvent<{ value?: unknown }>) => this._toggleAvailable(p, Boolean(event.detail.value))}
                ></platform-switch>
                <div class="ops">
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu.move_up')}
                        ?loading=${this._productReorderOp.busy} ?disabled=${index === 0}
                        @click=${() => this._move(p, -1)}
                    ><platform-icon name="chevron-up" size="14"></platform-icon></platform-button>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu.move_down')}
                        ?loading=${this._productReorderOp.busy} ?disabled=${index === total - 1}
                        @click=${() => this._move(p, 1)}
                    ><platform-icon name="chevron-down" size="14"></platform-icon></platform-button>
                    <input type="file" accept="image/*" style="display:none"
                        @change=${(e: Event) => this._uploadProductPhoto(p, e)}>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu.photo_pick')}
                        ?loading=${this._uploadOp.busy}
                        @click=${(e: Event) => ((e.currentTarget as HTMLElement).previousElementSibling as HTMLInputElement | null)?.click()}
                    ><platform-icon name="image" size="14"></platform-icon></platform-button>
                    ${p.photo_file_id
                        ? html`<platform-button icon-only density="compact" variant="ghost" title=${this.t('menu.ai_enhance')}
                            ?loading=${this._aiEnhanceOp.busy} @click=${() => this._enhancePhoto(p)}
                        ><platform-icon name="sparkle" size="14"></platform-icon></platform-button>`
                        : html`<platform-button icon-only density="compact" variant="ghost" title=${this.t('menu.ai_generate')}
                            ?loading=${this._aiGenerateOp.busy} @click=${() => this._generatePhoto(p)}
                        ><platform-icon name="sparkle" size="14"></platform-icon></platform-button>`}
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu.modifiers')} @click=${() => this._openModifiers(p)}>
                        <platform-icon name="list-check" size="14"></platform-icon>
                    </platform-button>
                    <platform-button icon-only density="compact" variant="ghost" title=${this.t('menu.edit')} @click=${() => this._openProductModal(p)}>
                        <platform-icon name="edit" size="14"></platform-icon>
                    </platform-button>
                    <platform-button icon-only density="compact" variant="ghost-danger" title=${this.t('menu.remove')} @click=${() => this._removeProduct(p)}>
                        <platform-icon name="trash" size="14"></platform-icon>
                    </platform-button>
                </div>
            </div>`;
    }

    override render() {
        const subtree = this._activeCategory === null ? null : this._subtreeIds(this._activeCategory);
        const filtered = subtree === null
            ? this._products
            : this._products.filter((p) => p.category_id !== null && subtree.has(p.category_id));
        const busy = this._categoriesOp.busy || this._productsOp.busy;
        const missingDesc = this._products.filter((p) => !p.description?.trim()).length;
        return html`
            <div class="wrap">
                <shop-page-head
                    .shop=${this._shop()}
                    shop-id=${this.shopId}
                    section=${this.t('routes.shop_menu')}
                >
                    <div slot="actions" class="head-actions">
                        ${missingDesc > 0 ? html`
                            <platform-button density="compact" variant="accent" ?loading=${this._aiDescribeBatchOp.busy}
                                @click=${() => this._runAiBatch()}>
                                <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menu.ai_fill')} · ${missingDesc}
                            </platform-button>
                        ` : nothing}
                        <platform-button density="compact" variant="secondary" @click=${() => this._openBadgeEditor()}>
                            <platform-icon name="tag" size="14"></platform-icon> ${this.t('menu.badges_title')}
                        </platform-button>
                        <platform-button density="compact" variant="secondary" @click=${() => this._toggleImport()}>
                            <platform-icon name="import" size="14"></platform-icon> ${this.t('menu.import_button')}
                        </platform-button>
                        <platform-button density="compact" variant="primary" @click=${() => this._openProductModal()}>
                            <platform-icon name="plus" size="14"></platform-icon> ${this.t('menu.add_product')}
                        </platform-button>
                    </div>
                </shop-page-head>
                ${this._importOpen ? this._renderImportPanel() : nothing}
                ${this._badgeEditorOpen ? html`
                    <div class="panel">
                        <div class="panel-title">${this.t('menu.badges_title')}</div>
                        <div class="panel-hint">${this.t('menu.badges_hint')}</div>
                        <div class="badges">
                            ${this._shopBadges().map((b) => html`
                                <span class="bchip">${this._iconSvg(b.icon_path)} ${b.label}
                                    <span class="x" title=${this.t('menu.badge_remove')} @click=${() => this._removeBadgeDef(b.key)}><platform-icon name="close" size="11"></platform-icon></span>
                                </span>`)}
                        </div>
                        <div class="badge-add">
                            <platform-field
                                type="string"
                                mode="edit" pill-density="compact"
                                label=${this.t('menu.badge_label')}
                                .value=${this._newBadgeLabel}
                                @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                    this._newBadgeLabel = typeof event.detail.value === 'string' ? event.detail.value : '';
                                }}
                            ></platform-field>
                            <span class="icon-grid">
                                ${Object.entries(this._badgeIcons).map(([name, path]) => html`
                                    <button type="button" class="icon-pick ${this._newBadgeIcon === name ? 'on' : ''}"
                                        title=${name} @click=${() => { this._newBadgeIcon = name; }}
                                    >${this._iconSvg(path)}</button>`)}
                            </span>
                            <platform-button density="compact" variant="primary" ?loading=${this._shopUpdateOp.busy}
                                ?disabled=${this._newBadgeLabel.trim() === '' || this._newBadgeIcon === ''}
                                @click=${() => this._addBadgeDef()}
                            >${this.t('menu.badge_add')}</platform-button>
                        </div>
                    </div>
                ` : nothing}
                <div class="layout">
                    <div class="rail">
                        <shop-category-tree
                            .categories=${this._categories}
                            .counts=${this._subtreeCounts()}
                            .allCount=${this._products.length}
                            .activeId=${this._activeCategory}
                            .expandedIds=${this._expandedIds}
                            @tree-select=${(e: CustomEvent<{ id: string | null }>) => { this._activeCategory = e.detail.id; }}
                            @tree-toggle=${(e: CustomEvent<{ id: string; expanded: boolean }>) => {
                                const { id, expanded } = e.detail;
                                this._expandedIds = expanded
                                    ? [...new Set([...this._expandedIds, id])]
                                    : this._expandedIds.filter((x) => x !== id);
                            }}
                            @tree-create=${(e: CustomEvent<{ parentId: string | null; name: string }>) => {
                                void this._createCategory(e.detail.parentId, e.detail.name);
                            }}
                            @tree-rename=${(e: CustomEvent<{ id: string; name: string }>) => {
                                void this._renameCategory(e.detail.id, e.detail.name);
                            }}
                            @tree-remove=${(e: CustomEvent<{ id: string }>) => {
                                void this._removeCategory(e.detail.id);
                            }}
                            @tree-change=${(e: CustomEvent<{ items: ShopTreeReorderItem[] }>) => {
                                void this._reorderTree(e.detail.items);
                            }}
                            @product-drop=${(e: CustomEvent<{ productId: string; categoryId: string | null }>) => {
                                void this._dropProduct(e.detail.productId, e.detail.categoryId);
                            }}
                        ></shop-category-tree>
                    </div>
                    <div class="list">
                        ${busy && filtered.length === 0
                            ? html`<platform-empty-state loading></platform-empty-state>`
                            : filtered.length === 0
                            ? html`<platform-empty-state icon="tag" title=${this.t('menu.empty')}></platform-empty-state>`
                            : filtered.map((p, i) => this._renderProduct(p, i, filtered.length))}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('shop-menu-page', ShopMenuPage);

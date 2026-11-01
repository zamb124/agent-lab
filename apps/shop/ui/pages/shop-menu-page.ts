/**
 * Конструктор меню: рейка категорий слева + карточки позиций.
 * Создание и редактирование позиции — ShopProductModal; метки и импорт —
 * раскрывающиеся панели над списком.
 */

import { html, css, nothing } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
import type { ProductDraft } from '../modals/shop-product-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

interface CategoryRow {
    shop_category_id: string;
    name: string;
    sort: number;
    is_active: boolean;
}

interface ProductRow {
    shop_product_id: string;
    category_id: string | null;
    name: string;
    description: string;
    price_minor: number;
    photo_file_id: string | null;
    is_available: boolean;
    portion: string;
    badges: string[];
    sort: number;
}

interface ShopBadgeDef {
    key: string;
    label: string;
    icon: string;
    icon_path: string;
}

interface ShopRow {
    shop_id: string;
    badges: ShopBadgeDef[];
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
    private _categoryRemoveOp: OpController;
    private _categoryReorderOp: OpController;
    private _productUpdateOp: OpController;
    private _productRemoveOp: OpController;
    private _productReorderOp: OpController;
    private _importOp: OpController;
    private _aiParseOp: OpController;
    private _aiDescribeBatchOp: OpController;
    private _aiEnhanceOp: OpController;
    private _aiGenerateOp: OpController;
    private _uploadOp: OpController;
    private _locale: SelectController<string>;

    private _categories: CategoryRow[] = [];
    private _products: ProductRow[] = [];
    private _badgeIcons: Record<string, string> = {};
    private _badgeEditorOpen = false;
    private _newBadgeLabel = '';
    private _newBadgeIcon = '';
    private _activeCategory: string | null = null;
    private _newCategory = '';
    private _importOpen = false;
    private _importText = '';
    private _aiItems: Array<{ name: string; description: string; portion: string; price_minor: number }> | null = null;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        _categories: { state: true },
        _products: { state: true },
        _badgeIcons: { state: true },
        _badgeEditorOpen: { state: true },
        _newBadgeLabel: { state: true },
        _newBadgeIcon: { state: true },
        _activeCategory: { state: true },
        _newCategory: { state: true },
        _importOpen: { state: true },
        _importText: { state: true },
        _aiItems: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 1180px; margin: 0 auto; padding: var(--space-6) var(--space-6) var(--space-10); }

            .page-head { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-5); flex-wrap: wrap; }
            .page-head h1 { margin: 0; font-size: var(--text-2xl); color: var(--text-primary); flex: 1; }
            .head-actions { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }

            .layout { display: grid; grid-template-columns: 232px minmax(0, 1fr); gap: var(--space-5); align-items: start; }

            .rail {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-2);
                position: sticky;
                top: var(--space-4);
            }
            .rail-title {
                font-size: var(--text-xs); font-weight: var(--font-semibold);
                color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em;
                padding: var(--space-2) var(--space-2) var(--space-1);
            }
            .cat {
                width: 100%;
                display: flex; align-items: center; gap: var(--space-2);
                border: 0; border-radius: var(--radius-md);
                padding: var(--space-2) var(--space-2);
                background: transparent; color: var(--text-secondary);
                font-size: var(--text-sm); cursor: pointer; text-align: left;
            }
            .cat:hover { background: color-mix(in srgb, var(--text-primary) 5%, transparent); color: var(--text-primary); }
            .cat.active { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); font-weight: var(--font-semibold); }
            .cat .name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
            .cat .count { font-size: var(--text-xs); color: var(--text-tertiary); font-variant-numeric: tabular-nums; }
            .cat.active .count { color: var(--accent); }
            .cat .cat-ops { display: none; align-items: center; }
            .cat:hover .cat-ops, .cat.active .cat-ops { display: inline-flex; }
            .cat:hover .count, .cat.active:hover .count { display: none; }
            .cat-ops platform-button { --platform-button-padding: 2px; }
            .cat-add { display: flex; gap: var(--space-1); padding: var(--space-2) var(--space-1) var(--space-1); align-items: end; }
            .cat-add platform-field { flex: 1; min-width: 0; }

            .list { display: flex; flex-direction: column; gap: var(--space-2); min-width: 0; }
            .card {
                display: flex; align-items: center; gap: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-3);
            }
            .card:hover { border-color: color-mix(in srgb, var(--text-primary) 18%, transparent); }
            .card.off { opacity: 0.55; }
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
            .ops { display: flex; gap: 2px; align-items: center; opacity: 0; transition: opacity 0.15s; }
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
            .panel-actions { display: flex; gap: var(--space-2); justify-content: flex-end; }

            platform-empty-state { margin-top: var(--space-8); }

            @media (max-width: 900px) {
                .layout { grid-template-columns: 1fr; }
                .rail { position: static; display: flex; flex-wrap: wrap; gap: var(--space-1); }
                .rail-title { width: 100%; }
                .cat { width: auto; }
                .cat-add { width: 100%; }
            }
            @media (max-width: 640px) {
                .card { flex-wrap: wrap; }
                .ops { opacity: 1; }
            }
        `,
    ];

    constructor() {
        super();
        this._shops = this.useResource('shop/shops');
        this._shopUpdateOp = this.useOp('shop/shop_update');
        this._badgeIconsOp = this.useOp('shop/badge_icons_list');
        this._categoriesOp = this.useOp('shop/categories_list');
        this._productsOp = this.useOp('shop/products_list');
        this._categoryCreateOp = this.useOp('shop/category_create');
        this._categoryRemoveOp = this.useOp('shop/category_remove');
        this._categoryReorderOp = this.useOp('shop/categories_reorder');
        this._productUpdateOp = this.useOp('shop/product_update');
        this._productRemoveOp = this.useOp('shop/product_remove');
        this._productReorderOp = this.useOp('shop/products_reorder');
        this._importOp = this.useOp('shop/products_import');
        this._aiParseOp = this.useOp('shop/ai_parse_menu');
        this._aiDescribeBatchOp = this.useOp('shop/ai_describe_batch');
        this._aiEnhanceOp = this.useOp('shop/ai_enhance_photo');
        this._aiGenerateOp = this.useOp('shop/ai_generate_photo');
        this._uploadOp = this.useOp('platform/file_create');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    async onRouteActive(): Promise<void> {
        await this._reload();
    }

    private async _reload() {
        if (this.shopId === '') return;
        const [cats, products] = await Promise.all([
            this._categoriesOp.run({ shop_id: this.shopId }),
            this._productsOp.run({ shop_id: this.shopId }),
            this._shops.load(),
        ]);
        this._categories = this._rows<CategoryRow>(cats);
        this._products = this._rows<ProductRow>(products);
        const first = this._categories[0];
        if (this._activeCategory === null && first !== undefined) {
            this._activeCategory = first.shop_category_id;
        }
    }

    private _shop(): ShopRow | null {
        const row = this._shops.items.find((s) => (s as { shop_id?: string }).shop_id === this.shopId);
        return row === undefined ? null : (row as unknown as ShopRow);
    }

    private _shopBadges(): ShopBadgeDef[] {
        return this._shop()?.badges ?? [];
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

    private async _addCategory() {
        const name = this._newCategory.trim();
        if (name === '') return;
        const result = await this._categoryCreateOp.run({ shop_id: this.shopId, name });
        if (result !== null) {
            this._newCategory = '';
            await this._reload();
        }
    }

    private async _moveCategory(categoryId: string, dir: -1 | 1) {
        const idx = this._categories.findIndex((c) => c.shop_category_id === categoryId);
        const swap = this._categories[idx + dir];
        if (idx < 0 || swap === undefined) return;
        const ids = this._categories.map((c) => c.shop_category_id);
        const cur = ids[idx], nxt = ids[idx + dir];
        if (cur === undefined || nxt === undefined) return;
        ids[idx] = nxt;
        ids[idx + dir] = cur;
        await this._categoryReorderOp.run({ shop_id: this.shopId, category_ids: ids });
        await this._reload();
    }

    private async _removeCategory(categoryId: string) {
        await this._categoryRemoveOp.run({ shop_id: this.shopId, shop_category_id: categoryId });
        if (this._activeCategory === categoryId) this._activeCategory = null;
        await this._reload();
    }

    private _openProductModal(product?: ProductRow) {
        const draft: ProductDraft | null = product === undefined
            ? null
            : {
                shop_product_id: product.shop_product_id,
                name: product.name,
                description: product.description,
                price_minor: product.price_minor,
                portion: product.portion,
                badges: [...product.badges],
                photo_file_id: product.photo_file_id,
            };
        this.openModal('shop.product', {
            shopId: this.shopId,
            categoryId: product === undefined ? this._activeCategory : product.category_id,
            product: draft,
            badgeDefs: this._shopBadges(),
            onSaved: () => void this._reload(),
        });
    }

    private async _uploadProductPhoto(p: ProductRow, event: Event) {
        const input = event.target as HTMLInputElement;
        const file = input.files && input.files[0];
        if (!file) return;
        const result = await this._uploadOp.run({
            file,
            spec: buildShopProductFileCreateSpecJson({ shopId: this.shopId, productId: p.shop_product_id }),
        });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                await this._productUpdateOp.run({
                    shop_id: this.shopId,
                    shop_product_id: p.shop_product_id,
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
                    shop_product_id: product.shop_product_id,
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
                    shop_product_id: product.shop_product_id,
                    photo_file_id: fileId,
                });
                await this._reload();
            }
        }
    }

    private async _toggleAvailable(product: ProductRow, enabled: boolean) {
        await this._productUpdateOp.run({
            shop_id: this.shopId,
            shop_product_id: product.shop_product_id,
            is_available: enabled,
        });
        await this._reload();
    }

    private _parseImport(): { items: Array<{ name: string; description: string; price_minor: number }>; invalid: number } {
        const items: Array<{ name: string; description: string; price_minor: number }> = [];
        let invalid = 0;
        for (const raw of this._importText.split('\n')) {
            const line = raw.trim();
            if (line === '') continue;
            const parts = line.split(';').map((p) => p.trim());
            const name = parts[0] ?? '';
            const priceText = (parts[1] ?? '').replace(/[^\d.,-]/g, '').replace(',', '.');
            const price = parts.length >= 2 ? Math.round(parseFloat(priceText) * 100) : NaN;
            if (name === '' || !Number.isFinite(price) || price < 0) {
                invalid += 1;
                continue;
            }
            items.push({ name, description: parts.slice(2).join('; '), price_minor: price });
        }
        return { items, invalid };
    }

    private async _runAiBatch() {
        const missing = this._products.filter((p) => !p.description?.trim()).length;
        if (missing === 0) return;
        await this._aiDescribeBatchOp.run({ shop_id: this.shopId });
    }

    private async _runAiParse() {
        const text = this._importText.trim();
        if (text.length < 3) return;
        const result = await this._aiParseOp.run({ shop_id: this.shopId, text });
        if (result !== null && typeof result === 'object' && 'items' in (result as Record<string, unknown>)) {
            const items = (result as { items?: unknown }).items;
            if (Array.isArray(items)) {
                this._aiItems = items
                    .filter((item): item is { name: string; description: string; portion: string; price_minor: number; category?: string } =>
                        typeof item === 'object' && item !== null && 'name' in item && 'price_minor' in item)
                    .map((item) => ({
                        name: String(item.name),
                        description: typeof item.description === 'string' ? item.description : '',
                        portion: typeof item.portion === 'string' ? item.portion : '',
                        price_minor: Number(item.price_minor),
                    }));
            }
        }
    }

    private async _runImport() {
        const items = this._aiItems ?? this._parseImport().items;
        if (items.length === 0) return;
        const result = await this._importOp.run({
            shop_id: this.shopId,
            category_id: this._activeCategory,
            items,
        });
        if (result !== null) {
            this._importText = '';
            this._aiItems = null;
            this._importOpen = false;
            await this._reload();
        }
    }

    private _openModifiers(product: ProductRow) {
        this.openModal('shop.modifiers', {
            shopId: this.shopId,
            productId: product.shop_product_id,
            productName: product.name,
        });
    }

    private async _move(product: ProductRow, dir: -1 | 1) {
        const list = this._activeCategory === null
            ? this._products
            : this._products.filter((p) => p.category_id === this._activeCategory);
        const idx = list.findIndex((p) => p.shop_product_id === product.shop_product_id);
        const swap = list[idx + dir];
        if (idx < 0 || swap === undefined) return;
        const ids = list.map((p) => p.shop_product_id);
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
            shop_product_id: product.shop_product_id,
        });
        await this._reload();
    }

    private _renderCategory(cat: CategoryRow, index: number) {
        const count = this._products.filter((p) => p.category_id === cat.shop_category_id).length;
        const active = this._activeCategory === cat.shop_category_id;
        return html`
            <button class="cat ${active ? 'active' : ''}" @click=${() => { this._activeCategory = cat.shop_category_id; }}>
                <span class="name">${cat.name}</span>
                <span class="count">${count}</span>
                <span class="cat-ops">
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.move_up')}
                        ?disabled=${index === 0}
                        @click=${(e: Event) => { e.stopPropagation(); void this._moveCategory(cat.shop_category_id, -1); }}
                    ><platform-icon name="chevron-up" size="12"></platform-icon></platform-button>
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.move_down')}
                        ?disabled=${index === this._categories.length - 1}
                        @click=${(e: Event) => { e.stopPropagation(); void this._moveCategory(cat.shop_category_id, 1); }}
                    ><platform-icon name="chevron-down" size="12"></platform-icon></platform-button>
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.category_remove')}
                        @click=${(e: Event) => { e.stopPropagation(); void this._removeCategory(cat.shop_category_id); }}
                    ><platform-icon name="close" size="12"></platform-icon></platform-button>
                </span>
            </button>`;
    }

    private _renderProduct(p: ProductRow, index: number, total: number) {
        const badgeDefs = this._shopBadges();
        return html`
            <div class="card ${p.is_available ? '' : 'off'}">
                ${p.photo_file_id
                    ? html`<img class="thumb" src="/shop/api/v1/files/download/${p.photo_file_id}" alt="" loading="lazy">`
                    : html`<span class="thumb-empty"><platform-icon name="image" size="18"></platform-icon></span>`}
                <div class="pinfo">
                    <div class="pname">
                        ${p.name}
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
                    title=${this.t('menu.col_available')}
                    ?checked=${p.is_available}
                    @change=${(event: CustomEvent<{ value?: unknown }>) => this._toggleAvailable(p, Boolean(event.detail.value))}
                ></platform-switch>
                <div class="ops">
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.move_up')}
                        ?busy=${this._productReorderOp.busy} ?disabled=${index === 0}
                        @click=${() => this._move(p, -1)}
                    ><platform-icon name="chevron-up" size="14"></platform-icon></platform-button>
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.move_down')}
                        ?busy=${this._productReorderOp.busy} ?disabled=${index === total - 1}
                        @click=${() => this._move(p, 1)}
                    ><platform-icon name="chevron-down" size="14"></platform-icon></platform-button>
                    <input type="file" accept="image/*" style="display:none"
                        @change=${(e: Event) => this._uploadProductPhoto(p, e)}>
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.photo_pick')}
                        ?busy=${this._uploadOp.busy}
                        @click=${(e: Event) => ((e.currentTarget as HTMLElement).previousElementSibling as HTMLInputElement | null)?.click()}
                    ><platform-icon name="image" size="14"></platform-icon></platform-button>
                    ${p.photo_file_id
                        ? html`<platform-button size="sm" variant="ghost" title=${this.t('menu.ai_enhance')}
                            ?busy=${this._aiEnhanceOp.busy} @click=${() => this._enhancePhoto(p)}
                        ><platform-icon name="sparkle" size="14"></platform-icon></platform-button>`
                        : html`<platform-button size="sm" variant="ghost" title=${this.t('menu.ai_generate')}
                            ?busy=${this._aiGenerateOp.busy} @click=${() => this._generatePhoto(p)}
                        ><platform-icon name="sparkle" size="14"></platform-icon></platform-button>`}
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.modifiers')} @click=${() => this._openModifiers(p)}>
                        <platform-icon name="list-check" size="14"></platform-icon>
                    </platform-button>
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.edit')} @click=${() => this._openProductModal(p)}>
                        <platform-icon name="edit" size="14"></platform-icon>
                    </platform-button>
                    <platform-button size="sm" variant="ghost" title=${this.t('menu.remove')} @click=${() => this._removeProduct(p)}>
                        <platform-icon name="trash" size="14"></platform-icon>
                    </platform-button>
                </div>
            </div>`;
    }

    override render() {
        const filtered = this._activeCategory === null
            ? this._products
            : this._products.filter((p) => p.category_id === this._activeCategory);
        const busy = this._categoriesOp.busy || this._productsOp.busy;
        const parsed = this._importOpen ? this._parseImport() : { items: [], invalid: 0 };
        const importItems = this._aiItems ?? parsed.items;
        const missingDesc = this._products.filter((p) => !p.description?.trim()).length;
        return html`
            <div class="wrap">
                <div class="page-head">
                    <h1>${this.t('menu.title')}</h1>
                    <div class="head-actions">
                        ${missingDesc > 0 ? html`
                            <platform-button size="sm" ?busy=${this._aiDescribeBatchOp.busy}
                                @click=${() => this._runAiBatch()}>
                                <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menu.ai_fill')} · ${missingDesc}
                            </platform-button>
                        ` : nothing}
                        <platform-button size="sm" @click=${() => this._openBadgeEditor()}>
                            <platform-icon name="tag" size="14"></platform-icon> ${this.t('menu.badges_title')}
                        </platform-button>
                        <platform-button size="sm" @click=${() => { this._importOpen = !this._importOpen; }}>
                            <platform-icon name="import" size="14"></platform-icon> ${this.t('menu.import_button')}
                        </platform-button>
                        <platform-button size="sm" variant="primary" @click=${() => this._openProductModal()}>
                            <platform-icon name="plus" size="14"></platform-icon> ${this.t('menu.add_product')}
                        </platform-button>
                    </div>
                </div>
                ${this._importOpen ? html`
                    <div class="panel">
                        <div class="panel-title">${this.t('menu.import_title')}</div>
                        <div class="panel-hint">${this.t('menu.import_hint')}</div>
                        <platform-field
                            type="text"
                            mode="edit"
                            label=${this.t('menu.import_placeholder')}
                            .value=${this._importText}
                            @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                this._importText = typeof event.detail.value === 'string' ? event.detail.value : '';
                                this._aiItems = null;
                            }}
                        ></platform-field>
                        <div class="import-stats">
                            <span class="ok">${this.t('menu.import_preview')} ${importItems.length}${this._aiItems !== null ? html` · ${this.t('menu.import_ai_ready')}` : nothing}</span>
                            ${parsed.invalid > 0 && this._aiItems === null ? html`<span class="bad">${parsed.invalid} ${this.t('menu.import_invalid')}</span>` : nothing}
                        </div>
                        <div class="panel-actions">
                            <platform-button size="sm" ?busy=${this._aiParseOp.busy}
                                ?disabled=${this._importText.trim().length < 3}
                                title=${this.t('menu.import_ai_hint')}
                                @click=${() => this._runAiParse()}
                            ><platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menu.import_ai')}</platform-button>
                            <platform-button size="sm" @click=${() => { this._importOpen = false; this._aiItems = null; }}>${this.t('menu.import_close')}</platform-button>
                            <platform-button size="sm" variant="primary" ?busy=${this._importOp.busy}
                                ?disabled=${importItems.length === 0}
                                @click=${() => this._runImport()}
                            >${this.t('menu.import_run')} · ${importItems.length}</platform-button>
                        </div>
                    </div>
                ` : nothing}
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
                                mode="edit"
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
                            <platform-button size="sm" variant="primary" ?busy=${this._shopUpdateOp.busy}
                                ?disabled=${this._newBadgeLabel.trim() === '' || this._newBadgeIcon === ''}
                                @click=${() => this._addBadgeDef()}
                            >${this.t('menu.badge_add')}</platform-button>
                        </div>
                    </div>
                ` : nothing}
                <div class="layout">
                    <div class="rail">
                        <div class="rail-title">${this.t('menu.categories_title')}</div>
                        <button class="cat ${this._activeCategory === null ? 'active' : ''}"
                            @click=${() => { this._activeCategory = null; }}>
                            <span class="name">${this.t('menu.all_products')}</span>
                            <span class="count">${this._products.length}</span>
                        </button>
                        ${this._categories.map((cat, i) => this._renderCategory(cat, i))}
                        <div class="cat-add">
                            <platform-field
                                type="string"
                                mode="edit"
                                label=${this.t('menu.new_category')}
                                .value=${this._newCategory}
                                @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                    this._newCategory = typeof event.detail.value === 'string' ? event.detail.value : '';
                                }}
                            ></platform-field>
                            <platform-button size="sm" ?disabled=${this._newCategory.trim() === ''} @click=${() => this._addCategory()}>
                                <platform-icon name="plus" size="16"></platform-icon>
                            </platform-button>
                        </div>
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

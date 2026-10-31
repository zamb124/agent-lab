/**
 * Конструктор меню: категории чипсами + товары таблицей с inline-добавлением.
 * Директор ресторана: выбрал категорию → имя, цена, описание → готово.
 * Кнопка «AI» генерирует описание (оп добавляется backend'ом).
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';
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
    sort: number;
}

export class ShopMenuPage extends PlatformPage {
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _categoriesOp: OpController;
    private _productsOp: OpController;
    private _categoryCreateOp: OpController;
    private _categoryRemoveOp: OpController;
    private _productCreateOp: OpController;
    private _productUpdateOp: OpController;
    private _productRemoveOp: OpController;
    private _productReorderOp: OpController;
    private _importOp: OpController;
    private _aiParseOp: OpController;
    private _aiDescribeOp: OpController;
    private _aiDescribeBatchOp: OpController;
    private _aiEnhanceOp: OpController;
    private _aiGenerateOp: OpController;
    private _uploadOp: OpController;
    private _locale: SelectController<string>;

    private _categories: CategoryRow[] = [];
    private _products: ProductRow[] = [];
    private _activeCategory: string | null = null;
    private _newCategory = '';
    private _newName = '';
    private _newPrice = '';
    private _newDescription = '';
    private _newPhotoFileId = '';
    private _newPhotoPreview = '';
    private _editingId = '';
    private _editName = '';
    private _editPrice = '';
    private _editDescription = '';
    private _importOpen = false;
    private _importText = '';
    private _aiItems: Array<{ name: string; description: string; price_minor: number }> | null = null;

    static override properties = {
        shopId: { type: String, attribute: 'shop-id' },
        _categories: { state: true },
        _products: { state: true },
        _activeCategory: { state: true },
        _newCategory: { state: true },
        _newName: { state: true },
        _newPrice: { state: true },
        _newDescription: { state: true },
        _newPhotoFileId: { state: true },
        _newPhotoPreview: { state: true },
        _editingId: { state: true },
        _editName: { state: true },
        _editPrice: { state: true },
        _editDescription: { state: true },
        _importOpen: { state: true },
        _importText: { state: true },
        _aiItems: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: block; height: 100%; overflow-y: auto; }
            .wrap { max-width: 960px; margin: 0 auto; padding: var(--space-6); }
            h1 { margin: 0 0 var(--space-4); font-size: var(--text-2xl); color: var(--text-primary); }
            .chips { display: flex; gap: var(--space-2); flex-wrap: wrap; margin-bottom: var(--space-4); align-items: center; }
            .chip {
                border: 1px solid var(--glass-border-subtle);
                border-radius: 999px;
                padding: var(--space-1) var(--space-3);
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
            }
            .chip.active {
                background: var(--accent);
                border-color: var(--accent);
                color: var(--text-inverse);
            }
            .chip .x { margin-left: var(--space-1); opacity: 0.6; }
            .chip-add {
                display: flex;
                gap: var(--space-2);
                align-items: center;
                min-width: 220px;
            }
            .add-row {
                display: grid;
                grid-template-columns: 64px 2fr 110px 3fr auto;
                gap: var(--space-2);
                align-items: end;
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                margin-bottom: var(--space-4);
            }
            table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
            th, td {
                padding: var(--space-2) var(--space-3);
                text-align: left;
                border-bottom: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
                vertical-align: top;
            }
            th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            .num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
            .desc { color: var(--text-tertiary); font-size: var(--text-xs); max-width: 320px; }
            .desc-cell { display: flex; gap: var(--space-2); align-items: end; }
            .desc-cell > platform-field { flex: 1; }
            .photo-pick {
                width: 56px;
                height: 56px;
                border-radius: var(--radius-md);
                border: 1px dashed var(--glass-border-subtle);
                background: transparent;
                cursor: pointer;
                overflow: hidden;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--text-tertiary);
                font-size: 20px;
            }
            .photo-pick img { width: 100%; height: 100%; object-fit: cover; }
            .photo-stack { display: flex; flex-direction: column; gap: var(--space-2); align-items: center; }
            .photo-stack platform-button { width: 56px; }
            .thumb { width: 44px; height: 44px; border-radius: var(--radius-sm); object-fit: cover; display: block; }
            .thumb-empty { width: 44px; height: 44px; border-radius: var(--radius-sm); background: color-mix(in srgb, var(--text-primary) 6%, transparent); display: block; }
            .edit-row {
                display: grid;
                grid-template-columns: 2fr 110px 3fr auto;
                gap: var(--space-2);
                align-items: end;
                padding: var(--space-2) var(--space-3);
                background: color-mix(in srgb, var(--accent) 6%, transparent);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            @media (max-width: 767px) {
                .edit-row { grid-template-columns: 1fr; }
            }
            .row-actions { display: flex; gap: var(--space-2); align-items: center; justify-content: flex-end; }
            platform-empty-state { margin-top: var(--space-8); }
            @media (max-width: 767px) {
                .add-row { grid-template-columns: 1fr; }
            }
            .page-head { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-4); }
            .page-head h1 { margin: 0; flex: 1; }
            .import-panel {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                padding: var(--space-4);
                margin-bottom: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .import-title { font-weight: var(--font-semibold); color: var(--text-primary); }
            .import-hint { font-size: var(--text-xs); color: var(--text-tertiary); line-height: 1.5; }
            .import-panel platform-field::part(field-pill-textarea),
            .import-panel platform-field {
                min-height: 150px;
            }
            .import-stats { display: flex; gap: var(--space-4); font-size: var(--text-sm); }
            .import-stats .ok { color: var(--success); }
            .import-stats .bad { color: var(--warning); }
            .import-actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
        `,
    ];

    constructor() {
        super();
        this._categoriesOp = this.useOp('shop/categories_list');
        this._productsOp = this.useOp('shop/products_list');
        this._categoryCreateOp = this.useOp('shop/category_create');
        this._categoryRemoveOp = this.useOp('shop/category_remove');
        this._productCreateOp = this.useOp('shop/product_create');
        this._productUpdateOp = this.useOp('shop/product_update');
        this._productRemoveOp = this.useOp('shop/product_remove');
        this._productReorderOp = this.useOp('shop/products_reorder');
        this._importOp = this.useOp('shop/products_import');
        this._aiParseOp = this.useOp('shop/ai_parse_menu');
        this._aiDescribeOp = this.useOp('shop/ai_describe');
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
        ]);
        this._categories = this._rows<CategoryRow>(cats);
        this._products = this._rows<ProductRow>(products);
        const first = this._categories[0];
        if (this._activeCategory === null && first !== undefined) {
            this._activeCategory = first.shop_category_id;
        }
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

    private async _removeCategory(categoryId: string) {
        await this._categoryRemoveOp.run({ shop_id: this.shopId, shop_category_id: categoryId });
        if (this._activeCategory === categoryId) this._activeCategory = null;
        await this._reload();
    }

    private async _pickPhoto() {
        const input = this.renderRoot?.querySelector<HTMLInputElement>('#new-photo-input');
        input?.click();
    }

    private async _uploadPhoto(event: Event) {
        const input = event.target as HTMLInputElement;
        const file = input.files && input.files[0];
        if (!file) return;
        const result = await this._uploadOp.run({
            file,
            spec: buildShopProductFileCreateSpecJson({ shopId: this.shopId }),
        });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                this._newPhotoFileId = fileId;
                this._newPhotoPreview = `/shop/api/v1/files/download/${fileId}`;
            }
        }
        input.value = '';
    }

    private _startEdit(p: ProductRow) {
        this._editingId = p.shop_product_id;
        this._editName = p.name;
        this._editPrice = (p.price_minor / 100).toString();
        this._editDescription = p.description;
    }

    private _cancelEdit() {
        this._editingId = '';
    }

    private async _saveEdit(p: ProductRow) {
        const price = Math.round(parseFloat(this._editPrice.replace(',', '.')) * 100);
        const payload: Record<string, unknown> = {
            shop_id: this.shopId,
            shop_product_id: p.shop_product_id,
        };
        const name = this._editName.trim();
        if (name !== '' && name !== p.name) payload.name = name;
        if (Number.isFinite(price) && price >= 0 && price !== p.price_minor) payload.price_minor = price;
        if (this._editDescription !== p.description) payload.description = this._editDescription;
        if (Object.keys(payload).length > 2) {
            await this._productUpdateOp.run(payload);
        }
        this._editingId = '';
        await this._reload();
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
        const result = await this._aiEnhanceOp.run({
            shop_id: this.shopId,
            file_id: product.photo_file_id,
        });
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

    private async _applyGeneratedPhoto(fileId: string, product?: ProductRow) {
        if (product === undefined) {
            this._newPhotoFileId = fileId;
            this._newPhotoPreview = `/shop/api/v1/files/download/${fileId}`;
            return;
        }
        await this._productUpdateOp.run({
            shop_id: this.shopId,
            shop_product_id: product.shop_product_id,
            photo_file_id: fileId,
        });
        await this._reload();
    }

    private async _generatePhoto(product?: ProductRow) {
        const name = product !== undefined ? product.name : this._newName.trim();
        if (name === '') return;
        const description = product !== undefined ? product.description : this._newDescription.trim();
        const result = await this._aiGenerateOp.run({ shop_id: this.shopId, name, description });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') await this._applyGeneratedPhoto(fileId, product);
        }
    }

    private async _describeWithAi() {
        const name = this._newName.trim();
        if (name === '') return;
        const category = this._categories.find((c) => c.shop_category_id === this._activeCategory);
        const result = await this._aiDescribeOp.run({
            shop_id: this.shopId,
            name,
            category_name: category !== undefined ? category.name : null,
        });
        if (result !== null && typeof result === 'object' && 'text' in (result as Record<string, unknown>)) {
            const text = (result as { text?: unknown }).text;
            if (typeof text === 'string') this._newDescription = text;
        }
    }

    private async _addProduct() {
        const name = this._newName.trim();
        const price = Math.round(parseFloat(this._newPrice.replace(',', '.')) * 100);
        if (name === '' || !Number.isFinite(price) || price < 0) return;
        const result = await this._productCreateOp.run({
            shop_id: this.shopId,
            category_id: this._activeCategory,
            name,
            description: this._newDescription.trim(),
            price_minor: price,
            photo_file_id: this._newPhotoFileId === '' ? null : this._newPhotoFileId,
        });
        if (result !== null) {
            this._newName = '';
            this._newPrice = '';
            this._newDescription = '';
            this._newPhotoFileId = '';
            this._newPhotoPreview = '';
            await this._reload();
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
                    .filter((item): item is { name: string; description: string; price_minor: number; category?: string } =>
                        typeof item === 'object' && item !== null && 'name' in item && 'price_minor' in item)
                    .map((item) => ({
                        name: String(item.name),
                        description: typeof item.description === 'string' ? item.description : '',
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

    override render() {
        const filtered = this._activeCategory === null
            ? this._products
            : this._products.filter((p) => p.category_id === this._activeCategory);
        const busy = this._categoriesOp.busy || this._productsOp.busy;
        const parsed = this._importOpen ? this._parseImport() : { items: [], invalid: 0 };
        const importItems = this._aiItems ?? parsed.items;
        return html`
            <div class="wrap">
                <div class="page-head">
                    <h1>${this.t('menu.title')}</h1>
                    <div class="head-actions">
                        ${(() => {
                            const missing = this._products.filter((p) => !p.description?.trim()).length;
                            return missing > 0 ? html`
                                <platform-button size="sm" variant="primary" ?busy=${this._aiDescribeBatchOp.busy}
                                    @click=${() => this._runAiBatch()}>
                                    <platform-icon name="sparkles" size="14"></platform-icon> ${this.t('menu.ai_fill')} · ${missing}
                                </platform-button>
                            ` : html``;
                        })()}
                        <platform-button size="sm" @click=${() => { this._importOpen = !this._importOpen; }}>
                            <platform-icon name="upload" size="14"></platform-icon> ${this.t('menu.import_button')}
                        </platform-button>
                    </div>
                </div>
                ${this._importOpen ? html`
                    <div class="import-panel">
                        <div class="import-title">${this.t('menu.import_title')}</div>
                        <div class="import-hint">${this.t('menu.import_hint')}</div>
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
                            <span class="ok">${this.t('menu.import_preview')} ${importItems.length}${this._aiItems !== null ? html` · ${this.t('menu.import_ai_ready')}` : ''}</span>
                            ${parsed.invalid > 0 && this._aiItems === null ? html`<span class="bad">${parsed.invalid} ${this.t('menu.import_invalid')}</span>` : html``}
                        </div>
                        <div class="import-actions">
                            <platform-button
                                size="sm"
                                ?busy=${this._aiParseOp.busy}
                                ?disabled=${this._importText.trim().length < 3}
                                title=${this.t('menu.import_ai_hint')}
                                @click=${() => this._runAiParse()}
                            ><platform-icon name="sparkles" size="14"></platform-icon> ${this.t('menu.import_ai')}</platform-button>
                            <platform-button size="sm" @click=${() => { this._importOpen = false; this._aiItems = null; }}>${this.t('menu.import_close')}</platform-button>
                            <platform-button
                                size="sm"
                                variant="primary"
                                ?busy=${this._importOp.busy}
                                ?disabled=${importItems.length === 0}
                                @click=${() => this._runImport()}
                            >${this.t('menu.import_run')} · ${importItems.length}</platform-button>
                        </div>
                    </div>
                ` : html``}
                <div class="chips">
                    ${this._categories.map((cat) => html`
                        <button
                            class="chip ${this._activeCategory === cat.shop_category_id ? 'active' : ''}"
                            @click=${() => { this._activeCategory = cat.shop_category_id; }}
                        >
                            ${cat.name}
                            <span class="x" @click=${(e: Event) => { e.stopPropagation(); this._removeCategory(cat.shop_category_id); }}><platform-icon name="x" size="12"></platform-icon></span>
                        </button>
                    `)}
                    <span class="chip-add">
                        <platform-field
                            type="text"
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
                    </span>
                </div>
                <div class="add-row">
                    <input id="new-photo-input" type="file" accept="image/*" style="display:none" @change=${(e: Event) => this._uploadPhoto(e)}>
                    <span class="photo-stack">
                        <button class="photo-pick" title=${this.t('menu.photo_pick')} ?disabled=${this._uploadOp.busy} @click=${() => this._pickPhoto()}>
                            ${this._newPhotoPreview === ''
                                ? html`<platform-icon name="photo" size="20"></platform-icon>`
                                : html`<img src=${this._newPhotoPreview} alt="">`}
                        </button>
                        <platform-button
                            size="sm"
                            title=${this.t('menu.ai_generate_hint')}
                            ?busy=${this._aiGenerateOp.busy}
                            ?disabled=${this._newName.trim() === ''}
                            @click=${() => this._generatePhoto()}
                        ><platform-icon name="sparkles" size="14"></platform-icon></platform-button>
                    </span>
                    <platform-field
                        type="text"
                        mode="edit"
                        label=${this.t('menu.field_name')}
                        .value=${this._newName}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            this._newName = typeof event.detail.value === 'string' ? event.detail.value : '';
                        }}
                    ></platform-field>
                    <platform-field
                        type="number"
                        mode="edit"
                        label=${this.t('menu.field_price')}
                        .value=${this._newPrice}
                        @change=${(event: CustomEvent<{ value?: unknown }>) => {
                            this._newPrice = typeof event.detail.value === 'string' ? String(event.detail.value) : '';
                        }}
                    ></platform-field>
                    <span class="desc-cell">
                        <platform-field
                            type="text"
                            mode="edit"
                            label=${this.t('menu.field_description')}
                            .value=${this._newDescription}
                            @change=${(event: CustomEvent<{ value?: unknown }>) => {
                                this._newDescription = typeof event.detail.value === 'string' ? event.detail.value : '';
                            }}
                        ></platform-field>
                        <platform-button
                            size="sm"
                            title=${this.t('menu.ai_describe')}
                            ?busy=${this._aiDescribeOp.busy}
                            ?disabled=${this._newName.trim() === ''}
                            @click=${() => this._describeWithAi()}
                        ><platform-icon name="sparkles" size="14"></platform-icon> ${this.t('menu.ai_describe')}</platform-button>
                    </span>
                    <platform-button
                        variant="primary"
                        ?busy=${this._productCreateOp.busy}
                        ?disabled=${this._newName.trim() === '' || this._newPrice.trim() === ''}
                        @click=${() => this._addProduct()}
                    >${this.t('menu.add_product')}</platform-button>
                </div>
                ${busy && filtered.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : filtered.length === 0
                    ? html`<platform-empty-state icon="tag" title=${this.t('menu.empty')}></platform-empty-state>`
                    : html`
                        <table>
                            <thead><tr>
                                <th></th>
                                <th>${this.t('menu.col_name')}</th>
                                <th>${this.t('menu.col_description')}</th>
                                <th class="num">${this.t('menu.col_price')}</th>
                                <th class="num">${this.t('menu.col_available')}</th>
                                <th></th>
                            </tr></thead>
                            <tbody>
                                ${filtered.map((p) => this._editingId === p.shop_product_id
                                    ? html`
                                    <tr>
                                        <td colspan="6">
                                            <div class="edit-row">
                                                <platform-field type="text" mode="edit" label=${this.t('menu.field_name')} .value=${this._editName}
                                                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._editName = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                                                ></platform-field>
                                                <platform-field type="number" mode="edit" label=${this.t('menu.field_price')} .value=${this._editPrice}
                                                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._editPrice = typeof e.detail.value === 'string' ? String(e.detail.value) : ''; }}
                                                ></platform-field>
                                                <platform-field type="text" mode="edit" label=${this.t('menu.field_description')} .value=${this._editDescription}
                                                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._editDescription = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                                                ></platform-field>
                                                <span class="row-actions">
                                                    <platform-button size="sm" variant="primary" ?busy=${this._productUpdateOp.busy} @click=${() => this._saveEdit(p)}>${this.t('menu.save')}</platform-button>
                                                    <platform-button size="sm" @click=${() => this._cancelEdit()}>${this.t('menu.cancel')}</platform-button>
                                                </span>
                                            </div>
                                        </td>
                                    </tr>`
                                    : html`
                                    <tr>
                                        <td>
                                            ${p.photo_file_id
                                                ? html`<img class="thumb" src="/shop/api/v1/files/download/${p.photo_file_id}" alt="" loading="lazy">`
                                                : html`<span class="thumb-empty"></span>`}
                                        </td>
                                        <td>${p.name}</td>
                                        <td class="desc">${p.description}</td>
                                        <td class="num">${this._money(p.price_minor)}</td>
                                        <td class="num">
                                            <platform-switch
                                                ?checked=${p.is_available}
                                                @change=${(event: CustomEvent<{ value?: unknown }>) => this._toggleAvailable(p, Boolean(event.detail.value))}
                                            ></platform-switch>
                                        </td>
                                        <td>
                                            <div class="row-actions">
                                                <platform-button size="sm" title=${this.t('menu.move_up')}
                                                    ?busy=${this._productReorderOp.busy}
                                                    @click=${() => this._move(p, -1)}
                                                ><platform-icon name="chevron-up" size="14"></platform-icon></platform-button>
                                                <platform-button size="sm" title=${this.t('menu.move_down')}
                                                    ?busy=${this._productReorderOp.busy}
                                                    @click=${() => this._move(p, 1)}
                                                ><platform-icon name="chevron-down" size="14"></platform-icon></platform-button>
                                                <input type="file" accept="image/*" style="display:none" data-photo-input=${p.shop_product_id}
                                                    @change=${(e: Event) => this._uploadProductPhoto(p, e)}>
                                                <platform-button
                                                    size="sm"
                                                    title=${this.t('menu.photo_pick')}
                                                    ?busy=${this._uploadOp.busy}
                                                    @click=${(e: Event) => (e.currentTarget as HTMLElement).parentElement?.querySelector<HTMLInputElement>('input[type=file]')?.click()}
                                                ><platform-icon name="photo" size="14"></platform-icon></platform-button>
                                                ${p.photo_file_id
                                                    ? html`<platform-button
                                                        size="sm"
                                                        title=${this.t('menu.ai_enhance')}
                                                        ?busy=${this._aiEnhanceOp.busy}
                                                        @click=${() => this._enhancePhoto(p)}
                                                    ><platform-icon name="sparkles" size="14"></platform-icon></platform-button>`
                                                    : html`<platform-button
                                                        size="sm"
                                                        title=${this.t('menu.ai_generate')}
                                                        ?busy=${this._aiGenerateOp.busy}
                                                        @click=${() => this._generatePhoto(p)}
                                                    ><platform-icon name="sparkles" size="14"></platform-icon></platform-button>`}
                                                <platform-button size="sm" title=${this.t('menu.modifiers')} @click=${() => this._openModifiers(p)}>
                                                    <platform-icon name="list-checks" size="14"></platform-icon>
                                                </platform-button>
                                                <platform-button size="sm" title=${this.t('menu.edit')} @click=${() => this._startEdit(p)}>
                                                    <platform-icon name="edit" size="14"></platform-icon>
                                                </platform-button>
                                                <platform-button size="sm" @click=${() => this._removeProduct(p)}>
                                                    <platform-icon name="trash" size="14"></platform-icon>
                                                </platform-button>
                                            </div>
                                        </td>
                                    </tr>
                                `)}
                            </tbody>
                        </table>
                    `}
            </div>
        `;
    }
}

customElements.define('shop-menu-page', ShopMenuPage);

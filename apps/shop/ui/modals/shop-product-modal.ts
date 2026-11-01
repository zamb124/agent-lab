/**
 * ShopProductModal — карточка товара: создание и редактирование.
 *
 * Фото (загрузить / AI-улучшить / AI-сгенерировать), имя, цена, порция,
 * описание с AI-автозаполнением, метки. Один экземпляр на create/edit.
 */

import { html, css, nothing } from 'lit';
import type { TemplateResult } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

interface ShopBadgeDef {
    key: string;
    label: string;
    icon: string;
    icon_path: string;
}

export interface ProductDraft {
    shop_product_id?: string;
    name: string;
    description: string;
    price_minor: number;
    portion: string;
    badges: string[];
    photo_file_id: string | null;
}

function _str(e: CustomEvent<{ value?: unknown }>): string {
    return typeof e.detail.value === 'string' ? e.detail.value : '';
}

export class ShopProductModal extends PlatformModal {
    static modalKind = 'shop.product';
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare categoryId: string | null;
    declare product: ProductDraft | null;
    declare badgeDefs: ShopBadgeDef[];
    declare onSaved: (() => void) | null;

    private _createOp: OpController;
    private _updateOp: OpController;
    private _aiDescribeOp: OpController;
    private _aiEnhanceOp: OpController;
    private _aiGenerateOp: OpController;
    private _uploadOp: OpController;

    private _name = '';
    private _price = '';
    private _portion = '';
    private _description = '';
    private _badges: string[] = [];
    private _photoFileId = '';
    private _photoPreview = '';
    private _saving = false;

    static override properties = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        categoryId: { attribute: false },
        product: { attribute: false },
        badgeDefs: { attribute: false },
        onSaved: { attribute: false },
        _name: { state: true },
        _price: { state: true },
        _portion: { state: true },
        _description: { state: true },
        _badges: { state: true },
        _photoFileId: { state: true },
        _photoPreview: { state: true },
        _saving: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
            .top { display: grid; grid-template-columns: 120px 1fr; gap: var(--space-4); align-items: start; }
            .photo-box {
                width: 120px; height: 120px; border-radius: var(--radius-lg);
                border: 1px dashed var(--glass-border-subtle);
                background: color-mix(in srgb, var(--text-primary) 4%, transparent);
                cursor: pointer; overflow: hidden; position: relative;
                display: flex; flex-direction: column; align-items: center; justify-content: center;
                gap: var(--space-1); color: var(--text-tertiary); font-size: var(--text-xs);
            }
            .photo-box:hover { border-color: var(--accent); color: var(--accent); }
            .photo-box img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
            .photo-actions { display: flex; flex-direction: column; gap: var(--space-2); margin-top: var(--space-2); }
            .fields { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
            .row2 { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
            .desc-row { display: flex; flex-direction: column; gap: var(--space-2); }
            .desc-ai { align-self: flex-end; }
            .badges { display: flex; flex-wrap: wrap; gap: var(--space-1); }
            .bchip {
                display: inline-flex; align-items: center; gap: var(--space-1);
                padding: var(--space-1) var(--space-2); border-radius: var(--radius-full);
                border: 1px solid var(--border-default); background: var(--surface-secondary);
                color: var(--text-secondary); font-size: var(--text-xs); font-weight: var(--font-medium);
                cursor: pointer; user-select: none;
            }
            .bchip.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
            .bchip svg { width: 13px; height: 13px; fill: currentColor; }
            .actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
            @media (max-width: 560px) {
                .top { grid-template-columns: 1fr; }
                .photo-box { width: 100%; height: 160px; }
            }
        `,
    ];

    constructor() {
        super();
        this._createOp = this.useOp('shop/product_create');
        this._updateOp = this.useOp('shop/product_update');
        this._aiDescribeOp = this.useOp('shop/ai_describe');
        this._aiEnhanceOp = this.useOp('shop/ai_enhance_photo');
        this._aiGenerateOp = this.useOp('shop/ai_generate_photo');
        this._uploadOp = this.useOp('platform/file_create');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.shopId !== 'string' || this.shopId.length === 0) {
            throw new Error('ShopProductModal: prop "shopId" required');
        }
        const p = this.product;
        if (p !== null && p !== undefined) {
            this._name = p.name;
            this._price = (p.price_minor / 100).toString();
            this._portion = p.portion;
            this._description = p.description;
            this._badges = [...p.badges];
            this._photoFileId = p.photo_file_id ?? '';
            this._photoPreview = p.photo_file_id !== null
                ? `/shop/api/v1/files/download/${p.photo_file_id}`
                : '';
        }
    }

    private get _editing(): boolean {
        return this.product !== null && this.product !== undefined && typeof this.product.shop_product_id === 'string';
    }

    private _iconSvg(path: string) {
        return unsafeHTML(`<svg viewBox="0 -960 960 960"><path d="${path}"/></svg>`);
    }

    private _toggleBadge(key: string) {
        this._badges = this._badges.includes(key)
            ? this._badges.filter((b) => b !== key)
            : [...this._badges, key];
    }

    private async _save() {
        const name = this._name.trim();
        const price = Math.round(parseFloat(this._price.replace(',', '.')) * 100);
        if (name === '' || !Number.isFinite(price) || price < 0 || this._saving) return;
        this._saving = true;
        try {
            if (this._editing && this.product !== null && this.product.shop_product_id !== undefined) {
                const p = this.product;
                const payload: Record<string, unknown> = {
                    shop_id: this.shopId,
                    shop_product_id: p.shop_product_id,
                };
                if (name !== p.name) payload.name = name;
                if (price !== p.price_minor) payload.price_minor = price;
                if (this._portion !== p.portion) payload.portion = this._portion;
                if (JSON.stringify(this._badges) !== JSON.stringify(p.badges)) payload.badges = this._badges;
                if (this._description !== p.description) payload.description = this._description;
                if (this._photoFileId !== (p.photo_file_id ?? '')) payload.photo_file_id = this._photoFileId === '' ? null : this._photoFileId;
                if (Object.keys(payload).length > 2) await this._updateOp.run(payload);
            } else {
                await this._createOp.run({
                    shop_id: this.shopId,
                    category_id: this.categoryId,
                    name,
                    description: this._description.trim(),
                    portion: this._portion.trim(),
                    badges: this._badges,
                    price_minor: price,
                    photo_file_id: this._photoFileId === '' ? null : this._photoFileId,
                });
            }
            this.onSaved?.();
            this.close();
        } finally {
            this._saving = false;
        }
    }

    private async _uploadPhoto(e: Event) {
        const input = e.target as HTMLInputElement;
        const file = input.files && input.files[0];
        if (!file) return;
        const params: { shopId: string; productId?: string } = { shopId: this.shopId };
        if (this._editing && this.product !== null && this.product.shop_product_id !== undefined) {
            params.productId = this.product.shop_product_id;
        }
        const result = await this._uploadOp.run({
            file,
            spec: buildShopProductFileCreateSpecJson(params),
        });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                this._photoFileId = fileId;
                this._photoPreview = `/shop/api/v1/files/download/${fileId}`;
            }
        }
        input.value = '';
    }

    private async _enhancePhoto() {
        if (this._photoFileId === '') return;
        const result = await this._aiEnhanceOp.run({ shop_id: this.shopId, file_id: this._photoFileId });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                this._photoFileId = fileId;
                this._photoPreview = `/shop/api/v1/files/download/${fileId}`;
            }
        }
    }

    private async _generatePhoto() {
        const name = this._name.trim();
        if (name === '') return;
        const result = await this._aiGenerateOp.run({ shop_id: this.shopId, name, description: this._description.trim() });
        if (result !== null && typeof result === 'object' && 'file_id' in (result as Record<string, unknown>)) {
            const fileId = (result as { file_id?: unknown }).file_id;
            if (typeof fileId === 'string') {
                this._photoFileId = fileId;
                this._photoPreview = `/shop/api/v1/files/download/${fileId}`;
            }
        }
    }

    private async _describeWithAi() {
        const name = this._name.trim();
        if (name === '') return;
        const result = await this._aiDescribeOp.run({ shop_id: this.shopId, name, category_name: null });
        if (result !== null && typeof result === 'object' && 'text' in (result as Record<string, unknown>)) {
            const text = (result as { text?: unknown }).text;
            if (typeof text === 'string') this._description = text;
        }
    }

    override renderHeader() {
        return this._editing ? this.t('menu.product_edit') : this.t('menu.product_new');
    }

    override renderBody(): TemplateResult {
        const badges = Array.isArray(this.badgeDefs) ? this.badgeDefs : [];
        return html`
            <div class="body">
                <div class="top">
                    <div>
                        <button class="photo-box" title=${this.t('menu.photo_pick')}
                            ?disabled=${this._uploadOp.busy}
                            @click=${() => this.renderRoot.querySelector<HTMLInputElement>('#photo-input')?.click()}>
                            ${this._photoPreview === ''
                                ? html`<platform-icon name="image" size="24"></platform-icon><span>${this.t('menu.photo_pick')}</span>`
                                : html`<img src=${this._photoPreview} alt="">`}
                        </button>
                        <div class="photo-actions">
                            <input id="photo-input" type="file" accept="image/*" style="display:none" @change=${(e: Event) => this._uploadPhoto(e)}>
                            ${this._photoFileId !== ''
                                ? html`<platform-button size="sm" ?busy=${this._aiEnhanceOp.busy} @click=${() => this._enhancePhoto()}>
                                      <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menu.ai_enhance')}
                                  </platform-button>`
                                : nothing}
                            <platform-button size="sm" ?busy=${this._aiGenerateOp.busy} ?disabled=${this._name.trim() === ''}
                                title=${this.t('menu.ai_generate_hint')} @click=${() => this._generatePhoto()}>
                                <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menu.ai_generate')}
                            </platform-button>
                        </div>
                    </div>
                    <div class="fields">
                        <platform-field type="string" mode="edit" label=${this.t('menu.field_name')} .value=${this._name}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._name = _str(e); }}></platform-field>
                        <div class="row2">
                            <platform-field type="number" mode="edit" label=${this.t('menu.field_price')} .value=${this._price}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._price = _str(e); }}></platform-field>
                            <platform-field type="string" mode="edit" label=${this.t('menu.field_portion')} .value=${this._portion}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._portion = _str(e); }}></platform-field>
                        </div>
                    </div>
                </div>
                <div class="desc-row">
                    <platform-field type="text" mode="edit" label=${this.t('menu.field_description')} .value=${this._description}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._description = _str(e); }}></platform-field>
                    <platform-button size="sm" class="desc-ai" ?busy=${this._aiDescribeOp.busy} ?disabled=${this._name.trim() === ''}
                        @click=${() => this._describeWithAi()}>
                        <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menu.ai_describe')}
                    </platform-button>
                </div>
                ${badges.length > 0
                    ? html`<div class="badges">${badges.map((b) => html`
                          <button type="button" class="bchip ${this._badges.includes(b.key) ? 'on' : ''}"
                              @click=${() => this._toggleBadge(b.key)}>${this._iconSvg(b.icon_path)} ${b.label}</button>`)}</div>`
                    : nothing}
                <div class="actions">
                    <platform-button @click=${() => this.close()}>${this.t('menu.cancel')}</platform-button>
                    <platform-button variant="primary" ?busy=${this._saving}
                        ?disabled=${this._name.trim() === '' || this._price.trim() === ''}
                        @click=${() => this._save()}>${this.t('menu.save')}</platform-button>
                </div>
            </div>`;
    }
}

customElements.define('shop-product-modal', ShopProductModal);
registerModalKind(ShopProductModal.modalKind, 'shop-product-modal');

/**
 * ShopProductModal — карточка блюда каталога: создание и редактирование.
 *
 * Фото (загрузить / AI-улучшить / AI-сгенерировать), имя, цена, выход
 * (`measure` + `measure_unit`), описание с AI-автозаполнением, метки.
 * Блюдо с `ai_unverified` предлагает подтвердить AI-поля, блюдо с
 * `similar_shop_product_id` — открыть сравнение `shop.product_merge`.
 */

import { html, css, nothing } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { ShopBadgeResponse, ShopMeasureUnit, ShopProductResponse } from '@platform/lib/events/wire/shop.gen.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { buildShopProductFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { shopBadgeSvg, shopFileUrl, shopMeasureUnitLabel, shopPriceMinor } from '../_helpers/shop-format.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

const MEASURE_UNITS: readonly ShopMeasureUnit[] = ['g', 'ml', 'pcs'];

function fieldText(e: CustomEvent<{ value?: unknown }>): string {
    const v = e.detail.value;
    return typeof v === 'string' ? v : typeof v === 'number' ? String(v) : '';
}

function isMeasureUnit(value: unknown): value is ShopMeasureUnit {
    return value === 'g' || value === 'ml' || value === 'pcs';
}

export class ShopProductModal extends PlatformModal {
    static modalKind = 'shop.product';
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare product: ShopProductResponse | null;
    declare badgeDefs: ShopBadgeResponse[];
    declare onSaved: ((product: ShopProductResponse) => void) | null;

    private _createOp: ControllerFor<'shop/product_create'>;
    private _updateOp: ControllerFor<'shop/product_update'>;
    private _verifyOp: ControllerFor<'shop/product_verify'>;
    private _aiDescribeOp: ControllerFor<'shop/ai_describe'>;
    private _aiEnhanceOp: ControllerFor<'shop/ai_enhance_photo'>;
    private _aiGenerateOp: ControllerFor<'shop/ai_generate_photo'>;
    private _uploadOp: ControllerFor<'platform/file_create'>;

    declare _name: string;
    declare _price: string;
    declare _measure: string;
    declare _measureUnit: ShopMeasureUnit;
    declare _description: string;
    declare _badges: string[];
    declare _photoFileId: string;

    static override properties = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        product: { attribute: false },
        badgeDefs: { attribute: false },
        onSaved: { attribute: false },
        _name: { state: true },
        _price: { state: true },
        _measure: { state: true },
        _measureUnit: { state: true },
        _description: { state: true },
        _badges: { state: true },
        _photoFileId: { state: true },
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
            .photo-actions { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: var(--space-2); }
            .fields { display: flex; flex-direction: column; gap: var(--space-3); min-width: 0; }
            .row3 { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-3); }
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
            .notice {
                display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
                padding: var(--space-2) var(--space-3); border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--warning) 10%, transparent);
                color: var(--text-secondary); font-size: var(--text-xs); line-height: 1.45;
            }
            .notice span { flex: 1; min-width: 0; }
            .actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
            @media (max-width: 560px) {
                .top { grid-template-columns: 1fr; }
                .photo-box { width: 100%; height: 160px; }
                .row3 { grid-template-columns: 1fr 1fr; }
            }
        `,
    ];

    constructor() {
        super();
        this.product = null;
        this.badgeDefs = [];
        this.onSaved = null;
        this._name = '';
        this._price = '';
        this._measure = '';
        this._measureUnit = 'g';
        this._description = '';
        this._badges = [];
        this._photoFileId = '';
        this._createOp = this.useOp('shop/product_create');
        this._updateOp = this.useOp('shop/product_update');
        this._verifyOp = this.useOp('shop/product_verify');
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
        if (!Array.isArray(this.badgeDefs)) {
            throw new Error('ShopProductModal: prop "badgeDefs" must be an array');
        }
        const p = this.product;
        if (p !== null) {
            this._name = p.name;
            this._price = (p.price_minor / 100).toString();
            this._measure = p.measure === null ? '' : String(p.measure);
            this._measureUnit = p.measure_unit;
            this._description = p.description;
            this._badges = [...p.badges];
            this._photoFileId = p.photo_file_id === null ? '' : p.photo_file_id;
        }
    }

    private get _saving(): boolean {
        return this._createOp.busy || this._updateOp.busy;
    }

    private _measureValue(): number | null {
        const text = this._measure.trim().replace(',', '.');
        if (text === '') return null;
        const value = Math.round(Number(text));
        return Number.isFinite(value) && value > 0 ? value : null;
    }

    private _toggleBadge(key: string) {
        this._badges = this._badges.includes(key)
            ? this._badges.filter((b) => b !== key)
            : [...this._badges, key];
    }

    private async _save() {
        const name = this._name.trim();
        const price = shopPriceMinor(this._price);
        if (name === '' || price === null || this._saving) return;
        const measure = this._measureValue();
        const photo = this._photoFileId === '' ? null : this._photoFileId;
        const p = this.product;
        const saved = p === null
            ? await this._createOp.run({
                shop_id: this.shopId,
                name,
                description: this._description.trim(),
                measure,
                measure_unit: this._measureUnit,
                badges: this._badges,
                price_minor: price,
                photo_file_id: photo,
            })
            : await this._updateOp.run({
                shop_id: this.shopId,
                shop_product_id: p.shop_product_id,
                name,
                description: this._description,
                measure,
                measure_unit: this._measureUnit,
                badges: this._badges,
                price_minor: price,
                photo_file_id: photo,
            });
        if (saved === null) return;
        if (this.onSaved !== null) this.onSaved(saved);
        this.close();
    }

    private async _verify() {
        const p = this.product;
        if (p === null) return;
        const verified = await this._verifyOp.run({ shop_id: this.shopId, shop_product_id: p.shop_product_id });
        if (verified !== null) this.product = verified;
    }

    private _openMerge() {
        const p = this.product;
        if (p === null) return;
        this.openModal('shop.product_merge', { shopId: this.shopId, product: p });
        this.close();
    }

    private async _uploadPhoto(e: Event) {
        const input = e.target;
        if (!(input instanceof HTMLInputElement) || input.files === null) return;
        const file = input.files[0];
        if (file === undefined) return;
        const p = this.product;
        const spec = p === null
            ? buildShopProductFileCreateSpecJson({ shopId: this.shopId })
            : buildShopProductFileCreateSpecJson({ shopId: this.shopId, productId: p.shop_product_id });
        const uploaded = await this._uploadOp.run({ file, spec });
        input.value = '';
        if (uploaded === null) return;
        const fileId = uploaded.file_id;
        if (typeof fileId !== 'string' || fileId === '') {
            throw new Error('ShopProductModal: platform/file_create must return result.file_id');
        }
        this._photoFileId = fileId;
    }

    private async _enhancePhoto() {
        if (this._photoFileId === '') return;
        const result = await this._aiEnhanceOp.run({ shop_id: this.shopId, file_id: this._photoFileId });
        if (result !== null) this._photoFileId = result.file_id;
    }

    private async _generatePhoto() {
        const name = this._name.trim();
        if (name === '') return;
        const result = await this._aiGenerateOp.run({ shop_id: this.shopId, name, description: this._description.trim() });
        if (result !== null) this._photoFileId = result.file_id;
    }

    private async _describeWithAi() {
        const name = this._name.trim();
        if (name === '') return;
        const result = await this._aiDescribeOp.run({ shop_id: this.shopId, name, category_name: null });
        if (result !== null) this._description = result.text;
    }

    override renderHeader() {
        return this.product === null ? this.t('product.title_new') : this.t('product.title_edit');
    }

    private _renderNotices(): TemplateResult | typeof nothing {
        const p = this.product;
        if (p === null) return nothing;
        return html`
            ${p.ai_unverified ? html`
                <div class="notice">
                    <platform-icon name="sparkle" size="14"></platform-icon>
                    <span>${this.t('product.ai_unverified_hint')}</span>
                    <platform-button size="sm" variant="secondary" ?loading=${this._verifyOp.busy}
                        @click=${() => this._verify()}
                    ><platform-icon name="badge-check" size="14"></platform-icon> ${this.t('product.verify')}</platform-button>
                </div>` : nothing}
            ${p.similar_shop_product_id !== null ? html`
                <div class="notice">
                    <platform-icon name="git-compare" size="14"></platform-icon>
                    <span>${this.t('product.similar_hint')}</span>
                    <platform-button size="sm" variant="secondary" @click=${() => this._openMerge()}
                    >${this.t('product.merge')}</platform-button>
                </div>` : nothing}
        `;
    }

    override renderBody(): TemplateResult {
        return html`
            <div class="body">
                ${this._renderNotices()}
                <div class="top">
                    <button class="photo-box" type="button" title=${this.t('product.photo_pick')}
                        ?disabled=${this._uploadOp.busy}
                        @click=${() => { const input = this.renderRoot.querySelector<HTMLInputElement>('#photo-input'); if (input !== null) input.click(); }}>
                        ${this._photoFileId === ''
                            ? html`<platform-icon name="image" size="24"></platform-icon><span>${this.t('product.photo_pick')}</span>`
                            : html`<img src=${shopFileUrl(this._photoFileId)} alt="">`}
                    </button>
                    <div class="fields">
                        <platform-field type="string" mode="edit" label=${this.t('product.field_name')} .value=${this._name}
                            @change=${(e: CustomEvent<{ value?: unknown }>) => { this._name = fieldText(e); }}></platform-field>
                        <div class="row3">
                            <platform-field type="number" mode="edit" label=${this.t('product.field_price')} .value=${this._price}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._price = fieldText(e); }}></platform-field>
                            <platform-field type="number" mode="edit" label=${this.t('product.field_measure')} .value=${this._measure}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { this._measure = fieldText(e); }}></platform-field>
                            <platform-field type="enum" mode="edit" label=${this.t('product.field_measure_unit')} .value=${this._measureUnit}
                                .config=${{ values: MEASURE_UNITS.map((unit) => ({ value: unit, label: shopMeasureUnitLabel(unit, (key) => this.t(key)) })) }}
                                @change=${(e: CustomEvent<{ value?: unknown }>) => { if (isMeasureUnit(e.detail.value)) this._measureUnit = e.detail.value; }}></platform-field>
                        </div>
                    </div>
                    <div class="photo-actions">
                        <input id="photo-input" type="file" accept="image/*" hidden @change=${(e: Event) => this._uploadPhoto(e)}>
                        ${this._photoFileId !== ''
                            ? html`<platform-button size="sm" variant="accent" ?loading=${this._aiEnhanceOp.busy} @click=${() => this._enhancePhoto()}>
                                  <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('product.ai_enhance')}
                              </platform-button>`
                            : nothing}
                        <platform-button size="sm" variant="accent" ?loading=${this._aiGenerateOp.busy} ?disabled=${this._name.trim() === ''}
                            title=${this.t('product.ai_generate_hint')} @click=${() => this._generatePhoto()}>
                            <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('product.ai_generate')}
                        </platform-button>
                    </div>
                </div>
                <div class="desc-row">
                    <platform-field type="text" mode="edit" label=${this.t('product.field_description')} .value=${this._description}
                        @change=${(e: CustomEvent<{ value?: unknown }>) => { this._description = fieldText(e); }}></platform-field>
                    <platform-button size="sm" variant="accent" class="desc-ai" ?loading=${this._aiDescribeOp.busy} ?disabled=${this._name.trim() === ''}
                        @click=${() => this._describeWithAi()}>
                        <platform-icon name="sparkle" size="14"></platform-icon> ${this.t('product.ai_describe')}
                    </platform-button>
                </div>
                ${this.badgeDefs.length > 0
                    ? html`<div class="badges">${this.badgeDefs.map((b) => html`
                          <button type="button" class="bchip ${this._badges.includes(b.key) ? 'on' : ''}"
                              @click=${() => this._toggleBadge(b.key)}>${shopBadgeSvg(b.icon_path)} ${b.label}</button>`)}</div>`
                    : nothing}
                <div class="actions">
                    <platform-button variant="secondary" @click=${() => this.close()}>${this.t('product.cancel')}</platform-button>
                    <platform-button variant="primary" ?loading=${this._saving}
                        ?disabled=${this._name.trim() === '' || shopPriceMinor(this._price) === null}
                        @click=${() => this._save()}>${this.t('product.save')}</platform-button>
                </div>
            </div>`;
    }
}

customElements.define('shop-product-modal', ShopProductModal);
registerModalKind(ShopProductModal.modalKind, 'shop-product-modal');

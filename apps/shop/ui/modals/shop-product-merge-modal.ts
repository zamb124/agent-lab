/**
 * ShopProductMergeModal — сравнение блюда с похожими в каталоге.
 *
 * Кандидаты — `shop/product_similar_list` (pg_trgm similarity названия),
 * по умолчанию выбран `similar_shop_product_id`. «Объединить» — `shop/product_merge`:
 * отмеченные поля переносятся с этого блюда в выбранное, позиции меню
 * переходят к выбранному, это блюдо удаляется. «Это разные блюда» —
 * `shop/product_dismiss_similar` снимает пометку.
 */

import { html, css, nothing } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { ShopProductMergePayload, ShopProductResponse } from '@platform/lib/events/wire/shop.gen.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { formatShopMeasure, formatShopPrice, shopFileUrl } from '../_helpers/shop-format.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';

type MergeField = NonNullable<ShopProductMergePayload['fields']>[number];

const MERGE_FIELDS: readonly MergeField[] = [
    'name', 'description', 'price_minor', 'measure', 'measure_unit',
    'ingredients', 'nutrition', 'allergens', 'badges', 'photo_file_id',
];

function fieldDiffers(field: MergeField, source: ShopProductResponse, target: ShopProductResponse): boolean {
    switch (field) {
        case 'name': return source.name !== target.name;
        case 'description': return source.description !== '' && source.description !== target.description;
        case 'price_minor': return source.price_minor !== target.price_minor;
        case 'measure': return source.measure !== null && source.measure !== target.measure;
        case 'measure_unit': return source.measure_unit !== target.measure_unit;
        case 'ingredients': return source.ingredients.length > 0 && source.ingredients.join('|') !== target.ingredients.join('|');
        case 'nutrition': return source.nutrition !== null && JSON.stringify(source.nutrition) !== JSON.stringify(target.nutrition);
        case 'allergens': return source.allergens.length > 0 && source.allergens.join('|') !== target.allergens.join('|');
        case 'badges': return source.badges.length > 0 && source.badges.join('|') !== target.badges.join('|');
        case 'photo_file_id': return source.photo_file_id !== null && source.photo_file_id !== target.photo_file_id;
    }
}

export class ShopProductMergeModal extends PlatformModal {
    static modalKind = 'shop.product_merge';
    static i18nNamespace = 'shop';

    declare shopId: string;
    declare product: ShopProductResponse;

    private _similarOp: ControllerFor<'shop/product_similar_list'>;
    private _mergeOp: ControllerFor<'shop/product_merge'>;
    private _dismissOp: ControllerFor<'shop/product_dismiss_similar'>;
    private _locale: SelectController<string>;

    declare _targetId: string;
    declare _fields: MergeField[];

    static override properties = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        product: { attribute: false },
        _targetId: { state: true },
        _fields: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            :host { --modal-width: min(720px, 100%); }
            .body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); line-height: 1.5; }
            .pair { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
            .label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; margin-bottom: var(--space-1); }
            .card {
                display: flex; gap: var(--space-3); align-items: center;
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-lg);
                background: var(--bg-surface); padding: var(--space-3); width: 100%;
                font: inherit; color: inherit; text-align: left;
            }
            button.card { cursor: pointer; }
            button.card:hover { border-color: color-mix(in srgb, var(--text-primary) 18%, transparent); }
            .card.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 8%, var(--bg-surface)); }
            .thumb { width: 48px; height: 48px; border-radius: var(--radius-md); object-fit: cover; flex-shrink: 0; }
            .thumb-empty {
                width: 48px; height: 48px; border-radius: var(--radius-md); flex-shrink: 0;
                background: color-mix(in srgb, var(--text-primary) 5%, transparent);
                display: flex; align-items: center; justify-content: center; color: var(--text-tertiary);
            }
            .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
            .name { font-weight: var(--font-semibold); color: var(--text-primary); font-size: var(--text-sm); }
            .meta { color: var(--text-tertiary); font-size: var(--text-xs); }
            .score { font-size: var(--text-xs); color: var(--accent); font-variant-numeric: tabular-nums; white-space: nowrap; }
            .candidates { display: flex; flex-direction: column; gap: var(--space-2); }
            .fields { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: var(--space-2); }
            .actions { display: flex; gap: var(--space-2); justify-content: space-between; flex-wrap: wrap; }
            .actions-right { display: flex; gap: var(--space-2); }
            @media (max-width: 560px) { .pair { grid-template-columns: 1fr; } }
        `,
    ];

    constructor() {
        super();
        this._targetId = '';
        this._fields = [];
        this._similarOp = this.useOp('shop/product_similar_list');
        this._mergeOp = this.useOp('shop/product_merge');
        this._dismissOp = this.useOp('shop/product_dismiss_similar');
        this._locale = this.select((state) => (state.i18n.locale === '' ? 'en' : state.i18n.locale));
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.shopId !== 'string' || this.shopId.length === 0) {
            throw new Error('ShopProductMergeModal: prop "shopId" required');
        }
        if (this.product === undefined || this.product === null) {
            throw new Error('ShopProductMergeModal: prop "product" required');
        }
        if (this.product.similar_shop_product_id !== null) {
            this._targetId = this.product.similar_shop_product_id;
        }
        void this._load();
    }

    private async _load() {
        const result = await this._similarOp.run({ shop_id: this.shopId, shop_product_id: this.product.shop_product_id });
        if (result === null) return;
        const first = result.items[0];
        if (this._targetId === '' && first !== undefined) {
            this._targetId = first.product.shop_product_id;
        }
        this._resetFields();
    }

    private _candidates(): Array<{ product: ShopProductResponse; score: number }> {
        const result = this._similarOp.lastResult;
        return result === null ? [] : result.items;
    }

    private _target(): ShopProductResponse | null {
        const match = this._candidates().find((c) => c.product.shop_product_id === this._targetId);
        return match === undefined ? null : match.product;
    }

    private _resetFields() {
        const target = this._target();
        this._fields = target === null ? [] : MERGE_FIELDS.filter((field) => fieldDiffers(field, this.product, target)
            && field !== 'name' && field !== 'price_minor');
    }

    private _selectTarget(id: string) {
        this._targetId = id;
        this._resetFields();
    }

    private _toggleField(field: MergeField, on: boolean) {
        this._fields = on
            ? [...new Set([...this._fields, field])]
            : this._fields.filter((f) => f !== field);
    }

    private async _merge() {
        const target = this._target();
        if (target === null) return;
        const merged = await this._mergeOp.run({
            shop_id: this.shopId,
            shop_product_id: this.product.shop_product_id,
            into_shop_product_id: target.shop_product_id,
            fields: this._fields,
        });
        if (merged !== null) this.close();
    }

    private async _dismiss() {
        const dismissed = await this._dismissOp.run({ shop_id: this.shopId, shop_product_id: this.product.shop_product_id });
        if (dismissed !== null) this.close();
    }

    private _fieldLabel(field: MergeField): string {
        switch (field) {
            case 'name': return this.t('product.field_name');
            case 'description': return this.t('product.field_description');
            case 'price_minor': return this.t('product.field_price');
            case 'measure': return this.t('product.field_measure');
            case 'measure_unit': return this.t('product.field_measure_unit');
            case 'ingredients': return this.t('product.field_ingredients');
            case 'nutrition': return this.t('product.nutrition_title');
            case 'allergens': return this.t('product.allergens_title');
            case 'badges': return this.t('product.badges_title');
            case 'photo_file_id': return this.t('product.photo');
        }
    }

    private _card(product: ShopProductResponse, score: number | null): TemplateResult {
        const measure = formatShopMeasure(product.measure, product.measure_unit, (key) => this.t(key));
        const price = formatShopPrice(product.price_minor, this._locale.value);
        const body = html`
            ${product.photo_file_id !== null
                ? html`<img class="thumb" src=${shopFileUrl(product.photo_file_id)} alt="" loading="lazy">`
                : html`<span class="thumb-empty"><platform-icon name="image" size="16"></platform-icon></span>`}
            <span class="info">
                <span class="name">${product.name}</span>
                <span class="meta">${price} ₽${measure === '' ? '' : ` · ${measure}`}</span>
            </span>
            ${score === null ? nothing : html`<span class="score">${Math.round(score * 100)}%</span>`}
        `;
        if (score === null) return html`<div class="card">${body}</div>`;
        return html`
            <button type="button" class="card ${product.shop_product_id === this._targetId ? 'on' : ''}"
                @click=${() => this._selectTarget(product.shop_product_id)}>${body}</button>`;
    }

    override renderHeader() {
        return this.t('product_merge.title');
    }

    override renderBody(): TemplateResult {
        const candidates = this._candidates();
        const target = this._target();
        const diffFields = target === null ? [] : MERGE_FIELDS.filter((field) => fieldDiffers(field, this.product, target));
        return html`
            <div class="body">
                <div class="hint">${this.t('product_merge.hint', { name: this.product.name })}</div>
                <div>
                    <div class="label">${this.t('product_merge.col_source')}</div>
                    ${this._card(this.product, null)}
                </div>
                <div>
                    <div class="label">${this.t('product_merge.target')}</div>
                    ${this._similarOp.busy && candidates.length === 0
                        ? html`<platform-empty-state loading></platform-empty-state>`
                        : candidates.length === 0
                        ? html`<div class="hint">${this.t('product_merge.empty')}</div>`
                        : html`<div class="candidates">${candidates.map((c) => this._card(c.product, c.score))}</div>`}
                </div>
                ${diffFields.length > 0 ? html`
                    <div>
                        <div class="label">${this.t('product_merge.fields_title')}</div>
                        <div class="fields">
                            ${diffFields.map((field) => html`
                                <platform-switch
                                    label=${this._fieldLabel(field)}
                                    ?checked=${this._fields.includes(field)}
                                    @change=${(e: CustomEvent<{ value?: unknown }>) => this._toggleField(field, e.detail.value === true)}
                                ></platform-switch>`)}
                        </div>
                    </div>` : nothing}
                <div class="actions">
                    ${this.product.similar_shop_product_id !== null
                        ? html`<platform-button variant="ghost" ?loading=${this._dismissOp.busy} @click=${() => this._dismiss()}
                            >${this.t('product_merge.dismiss')}</platform-button>`
                        : html`<span></span>`}
                    <div class="actions-right">
                        <platform-button variant="secondary" @click=${() => this.close()}>${this.t('product_merge.cancel')}</platform-button>
                        <platform-button variant="primary" ?loading=${this._mergeOp.busy} ?disabled=${target === null}
                            @click=${() => this._merge()}
                        ><platform-icon name="git-compare" size="14"></platform-icon> ${this.t('product_merge.merge')}</platform-button>
                    </div>
                </div>
            </div>`;
    }
}

customElements.define('shop-product-merge-modal', ShopProductMergeModal);
registerModalKind(ShopProductMergeModal.modalKind, 'shop-product-merge-modal');

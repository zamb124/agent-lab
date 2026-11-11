/**
 * Переоценка запаса товара: «добавь/убавь сумму» или «новая цена единицы».
 *
 * Пишет слой `revaluation` через `stock/valuation/revalue` — количество
 * не меняется, дельта суммы обязательна и ненулевая (проверяет backend).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type { FormController, OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import type { SegmentItem } from '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-segmented-control.js';

export class StockValuationRevalueModal extends PlatformFormModal {
    static modalKind = 'stock.valuation_revalue';
    static i18nNamespace = 'stock';

    static override properties: PropertyDeclarations = {
        productId: { type: String, attribute: 'product-id' },
    };
    declare productId: string;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .form-grid { display: grid; gap: var(--space-3); }
        `,
    ];

    private _form: FormController;
    private _revalueOp: OpController;
    private _products: ResourceController;

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this.productId = '';
        this._form = this.useForm('stock/valuation_revalue_form');
        this._revalueOp = this.useOp('stock/valuation_revalue');
        this._products = this.useResource('stock/products', { autoload: true });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._form.openForm({
            product_id: this.productId,
            mode: 'delta',
            value_delta: null,
            new_price: null,
            description: '',
        });
        this.useEvent(this._revalueOp.op.events.SUCCEEDED, () => {
            this.closeAfterSave();
        });
    }

    override disconnectedCallback(): void {
        this._form.close();
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        const draft = this._form.draft;
        const amount = draft.mode === 'price' ? draft.new_price : draft.value_delta;
        this.isDirty = typeof amount === 'number';
    }

    private _valid(): boolean {
        const draft = this._form.draft;
        if (typeof draft.product_id !== 'string' || draft.product_id === '') return false;
        const raw = draft.mode === 'price' ? draft.new_price : draft.value_delta;
        return typeof raw === 'number' && Number.isFinite(raw);
    }

    override async _performSave(): Promise<void> {
        if (!this._valid()) return;
        this._form.submit();
    }

    override renderHeader() {
        return this.t('valuation.modal_revalue_title');
    }

    override renderSaveHeaderButton() {
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !this._valid(),
            title: this.t('valuation.submit_apply'),
        });
    }

    private _productOptions() {
        const values: { value: string; label: string }[] = [];
        for (const item of this._products.items) {
            if (isPlainRecord(item) && typeof item.product_id === 'string') {
                const name = typeof item.name === 'string' ? item.name : item.product_id;
                const sku = typeof item.sku === 'string' && item.sku !== '' ? ` · ${item.sku}` : '';
                values.push({ value: item.product_id, label: `${name}${sku}` });
            }
        }
        return { values };
    }

    private _modeItems(): Array<Partial<SegmentItem>> {
        return [
            { value: 'delta', label: this.t('valuation.mode_delta') },
            { value: 'price', label: this.t('valuation.mode_price') },
        ];
    }

    override renderBody() {
        const draft = this._form.draft;
        const mode = typeof draft.mode === 'string' ? draft.mode : 'delta';
        return html`
            <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); this._performSave(); }}>
                <platform-field
                    type="enum"
                    mode="edit"
                    .label=${this.t('valuation.field_product')}
                    .value=${typeof draft.product_id === 'string' ? draft.product_id : ''}
                    .config=${this._productOptions()}
                    data-revalue-product
                    @change=${(e: CustomEvent) => this._form.setField('product_id', e.detail.value)}
                ></platform-field>
                <platform-segmented-control
                    full-width
                    density="compact"
                    .value=${mode}
                    .items=${this._modeItems()}
                    .ariaLabel=${this.t('valuation.field_mode')}
                    data-revalue-mode
                    @change=${(e: CustomEvent<{ value?: unknown }>) => {
                        const value = e.detail.value;
                        if (value === 'delta' || value === 'price') {
                            this._form.setField('mode', value);
                        }
                    }}
                ></platform-segmented-control>
                ${mode === 'delta'
                    ? html`
                        <platform-field
                            type="number"
                            mode="edit"
                            .label=${this.t('valuation.field_value_delta')}
                            .value=${draft.value_delta}
                            data-revalue-delta
                            @change=${(e: CustomEvent) => this._form.setField('value_delta', e.detail.value)}
                        ></platform-field>
                    `
                    : html`
                        <platform-field
                            type="number"
                            mode="edit"
                            .label=${this.t('valuation.field_new_price')}
                            .value=${draft.new_price}
                            data-revalue-price
                            @change=${(e: CustomEvent) => this._form.setField('new_price', e.detail.value)}
                        ></platform-field>
                    `}
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('valuation.field_description')}
                    .value=${draft.description}
                    @change=${(e: CustomEvent) => this._form.setField('description', e.detail.value)}
                ></platform-field>
            </form>
        `;
    }
}

customElements.define('stock-valuation-revalue-modal', StockValuationRevalueModal);
registerModalKind(StockValuationRevalueModal.modalKind, 'stock-valuation-revalue-modal');

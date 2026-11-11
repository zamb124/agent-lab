/**
 * Корректировка записи журнала: сторно через новый слой `correction`.
 *
 * Исходная запись не трогается — указываем дельты количества и суммы,
 * журнал остаётся честной историей.
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import type { FormController, OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { StockValueLayer } from '@platform/lib/events/wire/stock.gen.js';
import { formatQty, formatUnitCost } from '../_helpers/valuation.js';
import '@platform/lib/components/fields/platform-field.js';

export class StockValuationCorrectionModal extends PlatformFormModal {
    static modalKind = 'stock.valuation_correction';
    static i18nNamespace = 'stock';

    static override properties: PropertyDeclarations = {
        layer: { attribute: false },
        productName: { type: String, attribute: 'product-name' },
    };
    declare layer: StockValueLayer | null;
    declare productName: string;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .form-grid { display: grid; gap: var(--space-3); }
            .origin {
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
        `,
    ];

    private _form: FormController;
    private _correctionOp: OpController;
    private _locale: SelectController<string>;

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this.layer = null;
        this.productName = '';
        this._form = this.useForm('stock/valuation_correction_form');
        this._correctionOp = this.useOp('stock/valuation_correction');
        this._locale = this.select((s) => {
            const locale = s.i18n.locale;
            if (locale.length === 0) {
                throw new Error('stock-valuation-correction: locale required');
            }
            return locale;
        });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        const layer = this.layer;
        if (layer === null || typeof layer.layer_id !== 'string' || layer.layer_id === '') {
            throw new Error('stock-valuation-correction: layer required');
        }
        this._form.openForm({
            origin_layer_id: layer.layer_id,
            quantity_delta: 0,
            value_delta: null,
            description: '',
        });
        this.useEvent(this._correctionOp.op.events.SUCCEEDED, () => {
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
        this.isDirty = typeof draft.value_delta === 'number'
            || (typeof draft.quantity_delta === 'number' && draft.quantity_delta !== 0);
    }

    private _valid(): boolean {
        const draft = this._form.draft;
        if (typeof draft.value_delta !== 'number' || !Number.isFinite(draft.value_delta)) return false;
        return draft.quantity_delta === null || typeof draft.quantity_delta === 'number';
    }

    override async _performSave(): Promise<void> {
        if (!this._valid()) return;
        this._form.submit();
    }

    override renderHeader() {
        return this.t('valuation.modal_correction_title');
    }

    override renderSaveHeaderButton() {
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !this._valid(),
            title: this.t('valuation.submit_apply'),
        });
    }

    private _originSummary(): string {
        const layer = this.layer;
        if (layer === null) return '';
        const locale = this._locale.value;
        return this.t('valuation.origin_entry', {
            entry_no: layer.entry_no,
            qty: formatQty(layer.quantity, locale),
            cost: formatUnitCost(layer.unit_cost, locale),
        });
    }

    override renderBody() {
        const draft = this._form.draft;
        return html`
            <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); this._performSave(); }}>
                <div class="origin">
                    ${this._originSummary()}${this.productName !== '' ? ` · ${this.productName}` : ''}
                </div>
                <platform-field
                    type="number"
                    mode="edit"
                    .label=${this.t('valuation.field_qty_delta')}
                    .value=${draft.quantity_delta}
                    data-correction-qty
                    @change=${(e: CustomEvent) => this._form.setField('quantity_delta', e.detail.value)}
                ></platform-field>
                <platform-field
                    type="number"
                    mode="edit"
                    .label=${this.t('valuation.field_value_delta')}
                    .value=${draft.value_delta}
                    data-correction-value
                    @change=${(e: CustomEvent) => this._form.setField('value_delta', e.detail.value)}
                ></platform-field>
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

customElements.define('stock-valuation-correction-modal', StockValuationCorrectionModal);
registerModalKind(StockValuationCorrectionModal.modalKind, 'stock-valuation-correction-modal');

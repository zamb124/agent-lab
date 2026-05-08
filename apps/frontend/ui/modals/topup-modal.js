/**
 * Top-up modal — пополнение баланса компании.
 *
 * Сабмит вызывает `billingTopupOp` через useOp; effect редиректит на
 * payment_url, поэтому модалка просто закрывается после dispatch.
 */
import { html } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

export class FrontendTopupModal extends PlatformFormModal {
    static modalKind = 'frontend.billing_topup';

    static properties = {
        ...PlatformFormModal.properties,
        _amount: { state: true },
    };

    constructor() {
        super();
        this._amount = null;
        this.size = 'sm';
        this._topup = this.useOp('frontend/billing_topup');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('topup_modal.header');
    }

    validateForm() {
        const errors = {};
        const amount =
            typeof this._amount === 'number' && Number.isFinite(this._amount) ? this._amount : null;
        if (amount === null) {
            errors.amount = this.t('topup_modal.err_amount_required');
            return errors;
        }
        if (amount <= 0) {
            errors.amount = this.t('topup_modal.err_amount_invalid');
        } else if (amount < 100) {
            errors.amount = this.t('topup_modal.err_amount_min');
        }
        return errors;
    }

    async handleSubmit() {
        if (typeof this._amount !== 'number' || !Number.isFinite(this._amount)) {
            throw new Error('FrontendTopupModal.handleSubmit: amount is required');
        }
        this._topup.run({ amount: this._amount });
        this.closeAfterSave();
    }

    renderBody() {
        const amountNum = typeof this._amount === 'number' && Number.isFinite(this._amount) ? this._amount : null;
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="form-group">
                    <platform-field
                        type="number"
                        mode="edit"
                        label=${this.t('topup_modal.label_amount')}
                        .value=${amountNum}
                        @change=${(e) => {
                            if (!e.detail) {
                                throw new Error('topup modal: amount change expects detail');
                            }
                            const v = e.detail.value;
                            if (v !== null && typeof v !== 'number') {
                                throw new Error('topup modal: amount expects numeric detail.value or null');
                            }
                            this._amount = v;
                        }}
                    ></platform-field>
                    <small>${this.t('topup_modal.amount_hint')}</small>
                    ${this.renderFieldError('amount')}
                </div>
            </form>
        `;
    }

    renderFooter() {
        const canSubmit =
            typeof this._amount === 'number'
            && Number.isFinite(this._amount)
            && this._amount >= 100
            && !this.loading;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('topup_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${this.loading
                        ? this.t('topup_modal.submitting')
                        : this.t('topup_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-topup-modal', FrontendTopupModal);
registerModalKind(FrontendTopupModal.modalKind, 'frontend-topup-modal');

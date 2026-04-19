/**
 * Top-up modal — пополнение баланса компании.
 *
 * Сабмит вызывает `billingTopupOp` через useOp; effect редиректит на
 * payment_url, поэтому модалка просто закрывается после dispatch.
 */
import { html } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

export class FrontendTopupModal extends PlatformFormModal {
    static modalKind = 'frontend.billing_topup';

    static properties = {
        ...PlatformFormModal.properties,
        _amount: { state: true },
    };

    constructor() {
        super();
        this._amount = '';
        this.size = 'sm';
        this._topup = this.useOp('frontend/billing_topup');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('topup_modal.header');
    }

    validateForm() {
        const errors = {};
        const raw = this._amount;
        if (!raw) {
            errors.amount = this.t('topup_modal.err_amount_required');
            return errors;
        }
        const amount = Number(raw);
        if (Number.isNaN(amount) || amount <= 0) {
            errors.amount = this.t('topup_modal.err_amount_invalid');
        } else if (amount < 100) {
            errors.amount = this.t('topup_modal.err_amount_min');
        }
        return errors;
    }

    async handleSubmit() {
        this._topup.run({ amount: Number(this._amount) });
        this.closeAfterSave();
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="form-group">
                    <label class="form-label">${this.t('topup_modal.label_amount')}</label>
                    <input
                        type="number"
                        class="form-input"
                        name="amount"
                        .value=${this._amount}
                        @input=${(e) => { this._amount = e.target.value; }}
                        min="100"
                        autofocus
                    />
                    <small>${this.t('topup_modal.amount_hint')}</small>
                    ${this.renderFieldError('amount')}
                </div>
            </form>
        `;
    }

    renderFooter() {
        const canSubmit = Number(this._amount) >= 100 && !this.loading;
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

/**
 * Модалка начисления гранта на баланс выбранной компании (только из админки при компании system).
 */
import { html } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

export class FrontendBalanceGrantModal extends PlatformFormModal {
    static modalKind = 'frontend.balance_grant';

    static properties = {
        ...PlatformFormModal.properties,
        company_id: { type: String },
        _amount: { state: true },
        _note: { state: true },
    };

    constructor() {
        super();
        this.company_id = '';
        this._amount = '';
        this._note = '';
        this.size = 'sm';
        this._grant = this.useOp('frontend/admin_billing_balance_grant');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('platform_billing_page.balance_grant_modal_title');
    }

    validateForm() {
        const errors = {};
        if (!this.company_id) {
            errors.company_id = this.t('platform_billing_page.system_access_company_required');
        }
        const raw = typeof this._amount === 'string' ? this._amount.trim().replace(',', '.') : '';
        const n = Number(raw);
        if (raw === '' || Number.isNaN(n) || n < 0.01 || n > 10_000_000) {
            errors.amount = this.t('platform_billing_page.balance_grant_amount_invalid');
        }
        return errors;
    }

    async handleSubmit() {
        const raw = typeof this._amount === 'string' ? this._amount.trim().replace(',', '.') : '';
        const amount = Number(raw);
        const note = typeof this._note === 'string' ? this._note.trim() : '';
        this._grant.run({
            company_id: this.company_id,
            amount,
            note,
        });
        this.closeAfterSave();
    }

    renderBody() {
        return html`
            <p>${this.t('platform_billing_page.balance_grant_modal_subtitle', { company_id: this.company_id })}</p>
            <div class="form-group">
                <label>${this.t('platform_billing_page.balance_grant_label_amount')}</label>
                <input
                    type="text"
                    class="form-input"
                    inputmode="decimal"
                    .value=${this._amount}
                    @input=${(e) => { this._amount = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="form-group">
                <label>${this.t('platform_billing_page.balance_grant_label_note')}</label>
                <textarea
                    class="form-input"
                    rows="3"
                    .value=${this._note}
                    @input=${(e) => { this._note = e.target.value; this.isDirty = true; }}
                ></textarea>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('platform_billing_page.cancel')}
                </button>
                <button type="button" class="btn btn-primary" @click=${() => this._performSave()}>
                    ${this.t('platform_billing_page.balance_grant_submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-balance-grant-modal', FrontendBalanceGrantModal);
registerModalKind(FrontendBalanceGrantModal.modalKind, 'frontend-balance-grant-modal');

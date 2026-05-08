/**
 * Модалка начисления гранта на баланс выбранной компании (только из админки при компании system).
 */
import { html } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

export class FrontendBalanceGrantModal extends PlatformFormModal {
    static modalKind = 'frontend.balance_grant';
    static i18nNamespace = 'frontend';
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
            <platform-field
                type="string"
                mode="edit"
                .label=${this.t('platform_billing_page.balance_grant_label_amount')}
                .value=${this._amount}
                @change=${(e) => {
                    const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                    this._amount = v;
                    this.isDirty = true;
                }}
            ></platform-field>
            <platform-field
                type="text"
                mode="edit"
                .label=${this.t('platform_billing_page.balance_grant_label_note')}
                .value=${this._note}
                @change=${(e) => {
                    const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                    this._note = v;
                    this.isDirty = true;
                }}
            ></platform-field>
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

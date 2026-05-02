/**
 * Lead form modal — заявка с лендинга.
 *
 * Открывается через openModal(FrontendLeadFormModal). Submit вызывает
 * leadSubmitOp; HTTP и тосты живут в фабрике, модалка только закрывается.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function _digitsOnly(value) {
    return String(value).replace(/\D/g, '');
}

export class FrontendLeadFormModal extends PlatformFormModal {
    static i18nNamespace = 'landing';
    static modalKind = 'frontend.lead_form';

    static properties = {
        ...PlatformFormModal.properties,
        _name: { state: true },
        _email: { state: true },
        _phone: { state: true },
        _company: { state: true },
        _jobTitle: { state: true },
        _headcountRange: { state: true },
        _interestAgents: { state: true },
        _interestRag: { state: true },
        _interestCrm: { state: true },
        _interestSync: { state: true },
        _interestDocuments: { state: true },
        _comment: { state: true },
    };

    static styles = [
        PlatformFormModal.styles,
        css`
            .lead-fields { display: flex; flex-direction: column; gap: var(--space-3); }
            .lead-row { display: grid; grid-template-columns: 1fr; gap: var(--space-3); }
            @media (min-width: 600px) {
                .lead-row { grid-template-columns: 1fr 1fr; }
            }
            .products-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: var(--space-2);
            }
            @media (min-width: 600px) {
                .products-grid { grid-template-columns: 1fr 1fr; }
            }
            .product-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
            }
            select.form-input {
                width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this._name = '';
        this._email = '';
        this._phone = '';
        this._company = '';
        this._jobTitle = '';
        this._headcountRange = '';
        this._interestAgents = false;
        this._interestRag = false;
        this._interestCrm = false;
        this._interestSync = false;
        this._interestDocuments = false;
        this._comment = '';
        this.size = 'sm';
        this._submit = this.useOp('frontend/lead_submit');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('cta.modal_title');
    }

    validateForm() {
        const errors = {};
        if (!this._name.trim()) errors.name = this.t('cta.toast_required');

        const email = this._email.trim();
        if (email !== '' && !EMAIL_RE.test(email)) {
            errors.email = this.t('cta.toast_email_invalid');
        }

        const phoneDigits = _digitsOnly(this._phone);
        const hasEmail = email !== '';
        const hasPhone = phoneDigits.length >= 10;
        if (!hasEmail && !hasPhone) {
            errors.contact = this.t('cta.toast_contact_required');
        }

        if (this._headcountRange === '') {
            errors.headcount = this.t('cta.toast_required');
        }

        const anyProduct =
            this._interestAgents ||
            this._interestRag ||
            this._interestCrm ||
            this._interestSync ||
            this._interestDocuments;
        if (!anyProduct) {
            errors.products = this.t('cta.toast_products_required');
        }

        return errors;
    }

    async handleSubmit() {
        const interested_products = [];
        if (this._interestAgents) interested_products.push('agents');
        if (this._interestRag) interested_products.push('rag');
        if (this._interestCrm) interested_products.push('crm');
        if (this._interestSync) interested_products.push('sync');
        if (this._interestDocuments) interested_products.push('documents');

        await this._submit.run({
            name: this._name.trim(),
            email: this._email.trim() === '' ? null : this._email.trim(),
            phone: this._phone.trim() === '' ? null : this._phone.trim(),
            company: this._company.trim() === '' ? null : this._company.trim(),
            job_title: this._jobTitle.trim() === '' ? null : this._jobTitle.trim(),
            headcount_range: this._headcountRange,
            interested_products,
            comment: this._comment.trim() === '' ? null : this._comment.trim(),
        });
        this.closeAfterSave();
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="lead-fields">
                    <div class="lead-row">
                        <div class="form-group">
                            <input
                                class="form-input"
                                name="name"
                                autocomplete="name"
                                placeholder=${this.t('cta.placeholder_name')}
                                .value=${this._name}
                                @input=${(e) => { this._name = e.target.value; }}
                                autofocus
                                required
                            />
                            ${this.renderFieldError('name')}
                        </div>
                        <div class="form-group">
                            <input
                                class="form-input"
                                name="email"
                                type="email"
                                autocomplete="email"
                                placeholder=${this.t('cta.placeholder_email')}
                                .value=${this._email}
                                @input=${(e) => { this._email = e.target.value; }}
                            />
                            ${this.renderFieldError('email')}
                        </div>
                    </div>
                    <div class="lead-row">
                        <div class="form-group">
                            <input
                                class="form-input"
                                name="phone"
                                type="tel"
                                autocomplete="tel"
                                placeholder=${this.t('cta.placeholder_phone')}
                                .value=${this._phone}
                                @input=${(e) => { this._phone = e.target.value; }}
                            />
                        </div>
                        <div class="form-group">
                            <input
                                class="form-input"
                                name="company"
                                autocomplete="organization"
                                placeholder=${this.t('cta.placeholder_company')}
                                .value=${this._company}
                                @input=${(e) => { this._company = e.target.value; }}
                            />
                        </div>
                    </div>
                    <div class="lead-row">
                        <div class="form-group">
                            <input
                                class="form-input"
                                name="job_title"
                                autocomplete="organization-title"
                                placeholder=${this.t('cta.placeholder_job_title')}
                                .value=${this._jobTitle}
                                @input=${(e) => { this._jobTitle = e.target.value; }}
                            />
                        </div>
                        <div class="form-group">
                            <select
                                class="form-input"
                                name="headcount"
                                .value=${this._headcountRange}
                                @change=${(e) => { this._headcountRange = e.target.value; }}
                            >
                                <option value="" disabled>${this.t('cta.select_headcount_placeholder')}</option>
                                <option value="1_49">${this.t('cta.headcount_1_49')}</option>
                                <option value="50_199">${this.t('cta.headcount_50_199')}</option>
                                <option value="200_499">${this.t('cta.headcount_200_499')}</option>
                                <option value="500_plus">${this.t('cta.headcount_500_plus')}</option>
                            </select>
                            ${this.renderFieldError('headcount')}
                        </div>
                    </div>
                    <div class="form-group">
                        <div class="products-grid" role="group" aria-label=${this.t('cta.products_label')}>
                            <label class="product-row">
                                <input
                                    type="checkbox"
                                    .checked=${this._interestAgents}
                                    @change=${(e) => { this._interestAgents = e.target.checked; }}
                                />
                                <span>${this.t('cta.product_agents')}</span>
                            </label>
                            <label class="product-row">
                                <input
                                    type="checkbox"
                                    .checked=${this._interestRag}
                                    @change=${(e) => { this._interestRag = e.target.checked; }}
                                />
                                <span>${this.t('cta.product_rag')}</span>
                            </label>
                            <label class="product-row">
                                <input
                                    type="checkbox"
                                    .checked=${this._interestCrm}
                                    @change=${(e) => { this._interestCrm = e.target.checked; }}
                                />
                                <span>${this.t('cta.product_crm')}</span>
                            </label>
                            <label class="product-row">
                                <input
                                    type="checkbox"
                                    .checked=${this._interestSync}
                                    @change=${(e) => { this._interestSync = e.target.checked; }}
                                />
                                <span>${this.t('cta.product_sync')}</span>
                            </label>
                            <label class="product-row">
                                <input
                                    type="checkbox"
                                    .checked=${this._interestDocuments}
                                    @change=${(e) => { this._interestDocuments = e.target.checked; }}
                                />
                                <span>${this.t('cta.product_documents')}</span>
                            </label>
                        </div>
                        ${this.renderFieldError('products')}
                        ${this.renderFieldError('contact')}
                    </div>
                    <div class="form-group">
                        <input
                            class="form-input"
                            name="comment"
                            placeholder=${this.t('cta.placeholder_comment')}
                            .value=${this._comment}
                            @input=${(e) => { this._comment = e.target.value; }}
                        />
                    </div>
                </div>
            </form>
        `;
    }

    renderFooter() {
        const submitLabel = this.loading
            ? this.t('cta.submit_sending')
            : this.t('cta.submit_idle');
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('cta.button_cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${this.loading}
                    @click=${() => this._performSave()}
                >
                    <platform-icon name="send" size="18"></platform-icon>
                    <span>${submitLabel}</span>
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-lead-form-modal', FrontendLeadFormModal);
registerModalKind(FrontendLeadFormModal.modalKind, 'frontend-lead-form-modal');

/**
 * Модалка формы заявки — заявка с лендинга.
 *
 * Открывается через openModal(FrontendLeadFormModal). Отправка вызывает
 * leadSubmitOp; HTTP и тосты живут в фабрике, модалка только закрывается.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { isValidEmail, digitsOnly } from '@platform/lib/utils/validators.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';

export class FrontendLeadFormModal extends PlatformFormModal {
    static i18nNamespace = 'landing';
    static modalKind = 'frontend.lead_form';

    static properties = {
        ...PlatformFormModal.properties,
        _contactName: { state: true },
        _email: { state: true },
        _phone: { state: true },
        _organizationName: { state: true },
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
        `,
    ];

    constructor() {
        super();
        this._contactName = '';
        this._email = '';
        this._phone = '';
        this._organizationName = '';
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
        if (!this._contactName.trim()) errors.contact_name = this.t('cta.toast_required');

        const email = this._email.trim();
        if (email !== '' && !isValidEmail(email)) {
            errors.email = this.t('cta.toast_email_invalid');
        }

        const phoneDigits = digitsOnly(this._phone);
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
            contact_name: this._contactName.trim(),
            email: this._email.trim() === '' ? null : this._email.trim(),
            phone: this._phone.trim() === '' ? null : this._phone.trim(),
            organization_name: this._organizationName.trim() === '' ? null : this._organizationName.trim(),
            job_title: this._jobTitle.trim() === '' ? null : this._jobTitle.trim(),
            headcount_range: this._headcountRange,
            interested_products,
            comment: this._comment.trim() === '' ? null : this._comment.trim(),
        });
        this.closeAfterSave();
    }

    _headcountEnumConfig() {
        return {
            values: [
                { value: '', label: this.t('cta.select_headcount_placeholder') },
                { value: '1_49', label: this.t('cta.headcount_1_49') },
                { value: '50_199', label: this.t('cta.headcount_50_199') },
                { value: '200_499', label: this.t('cta.headcount_200_499') },
                { value: '500_plus', label: this.t('cta.headcount_500_plus') },
            ],
        };
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="lead-fields">
                    <div class="lead-row">
                        <platform-field
                            type="string"
                            mode="edit"
                            label=""
                            placeholder=${this.t('cta.placeholder_name')}
                            .value=${this._contactName}
                            @change=${(e) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('lead-form contact_name field expects detail.value string');
                                }
                                this._contactName = e.detail.value;
                            }}
                        ></platform-field>
                        ${this.renderFieldError('contact_name')}
                        <platform-field
                            type="string"
                            mode="edit"
                            input-type="email"
                            label=""
                            placeholder=${this.t('cta.placeholder_email')}
                            .value=${this._email}
                            @change=${(e) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('lead-form email field expects detail.value string');
                                }
                                this._email = e.detail.value;
                            }}
                        ></platform-field>
                        ${this.renderFieldError('email')}
                    </div>
                    <div class="lead-row">
                        <platform-field
                            type="string"
                            mode="edit"
                            input-type="tel"
                            label=""
                            placeholder=${this.t('cta.placeholder_phone')}
                            .value=${this._phone}
                            @change=${(e) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('lead-form phone field expects detail.value string');
                                }
                                this._phone = e.detail.value;
                            }}
                        ></platform-field>
                        <platform-field
                            type="string"
                            mode="edit"
                            label=""
                            placeholder=${this.t('cta.placeholder_company')}
                            .value=${this._organizationName}
                            @change=${(e) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('lead-form organization_name field expects detail.value string');
                                }
                                this._organizationName = e.detail.value;
                            }}
                        ></platform-field>
                    </div>
                    <div class="lead-row">
                        <platform-field
                            type="string"
                            mode="edit"
                            label=""
                            placeholder=${this.t('cta.placeholder_job_title')}
                            .value=${this._jobTitle}
                            @change=${(e) => {
                                if (!e.detail || typeof e.detail.value !== 'string') {
                                    throw new Error('lead-form job_title field expects detail.value string');
                                }
                                this._jobTitle = e.detail.value;
                            }}
                        ></platform-field>
                        <div>
                            <platform-field
                                type="enum"
                                mode="edit"
                                label=""
                                placeholder=""
                                .value=${this._headcountRange}
                                .config=${this._headcountEnumConfig()}
                                @change=${(e) => {
                                    if (!e.detail || typeof e.detail.value !== 'string') {
                                        throw new Error('lead-form headcount field expects detail.value string');
                                    }
                                    this._headcountRange = e.detail.value;
                                }}
                            ></platform-field>
                            ${this.renderFieldError('headcount')}
                        </div>
                    </div>
                    <div class="form-group">
                        <div class="products-grid" role="group" aria-label=${this.t('cta.products_label')}>
                            <div class="product-row">
                                <platform-switch
                                    size="sm"
                                    .checked=${this._interestAgents}
                                    @change=${(e) => {
                                        this._interestAgents = e.detail.value;
                                    }}
                                ></platform-switch>
                                <span>${this.t('cta.product_agents')}</span>
                            </div>
                            <div class="product-row">
                                <platform-switch
                                    size="sm"
                                    .checked=${this._interestRag}
                                    @change=${(e) => {
                                        this._interestRag = e.detail.value;
                                    }}
                                ></platform-switch>
                                <span>${this.t('cta.product_rag')}</span>
                            </div>
                            <div class="product-row">
                                <platform-switch
                                    size="sm"
                                    .checked=${this._interestCrm}
                                    @change=${(e) => {
                                        this._interestCrm = e.detail.value;
                                    }}
                                ></platform-switch>
                                <span>${this.t('cta.product_crm')}</span>
                            </div>
                            <div class="product-row">
                                <platform-switch
                                    size="sm"
                                    .checked=${this._interestSync}
                                    @change=${(e) => {
                                        this._interestSync = e.detail.value;
                                    }}
                                ></platform-switch>
                                <span>${this.t('cta.product_sync')}</span>
                            </div>
                            <div class="product-row">
                                <platform-switch
                                    size="sm"
                                    .checked=${this._interestDocuments}
                                    @change=${(e) => {
                                        this._interestDocuments = e.detail.value;
                                    }}
                                ></platform-switch>
                                <span>${this.t('cta.product_documents')}</span>
                            </div>
                        </div>
                        ${this.renderFieldError('products')}
                        ${this.renderFieldError('contact')}
                    </div>
                    <platform-field
                        type="text"
                        mode="edit"
                        label=""
                        placeholder=${this.t('cta.placeholder_comment')}
                        .value=${this._comment}
                        @change=${(e) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('lead-form comment field expects detail.value string');
                            }
                            this._comment = e.detail.value;
                        }}
                    ></platform-field>
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

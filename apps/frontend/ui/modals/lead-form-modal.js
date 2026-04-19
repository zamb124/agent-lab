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

export class FrontendLeadFormModal extends PlatformFormModal {
    static i18nNamespace = 'landing';
    static modalKind = 'frontend.lead_form';

    static properties = {
        ...PlatformFormModal.properties,
        _name: { state: true },
        _email: { state: true },
        _phone: { state: true },
        _company: { state: true },
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
        `,
    ];

    constructor() {
        super();
        this._name = '';
        this._email = '';
        this._phone = '';
        this._company = '';
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
        if (!this._email.trim()) errors.email = this.t('cta.toast_required');
        else if (!EMAIL_RE.test(this._email.trim())) errors.email = this.t('cta.toast_email_invalid');
        return errors;
    }

    async handleSubmit() {
        this._submit.run({
            name: this._name.trim(),
            email: this._email.trim(),
            phone: this._phone.trim(),
            company: this._company.trim(),
            comment: this._comment.trim(),
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
                                required
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
                    ${this.t('cta.modal_close_aria')}
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

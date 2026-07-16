/**
 * Модалка добавления домена в crawl profile.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { crawlDomainCreateOp } from '../events/resources/crawl-report.resource.js';
import '@platform/lib/components/fields/platform-field.js';

export class FrontendCrawlDomainAddModal extends PlatformFormModal {
    static modalKind = 'frontend.crawl_domain_add';
    static i18nNamespace = 'frontend';

    static properties = {
        ...PlatformFormModal.properties,
        crawl_profile_id: { type: String },
        _domain: { state: true },
        _runNow: { state: true },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .hint {
                margin: 0 0 var(--space-4);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.5;
            }
        `,
    ];

    constructor() {
        super();
        this.crawl_profile_id = '';
        this._domain = '';
        this._runNow = true;
        this.size = 'sm';
        this._create = this.useOp('frontend/crawl_domain_create');
        this.useEvent(crawlDomainCreateOp.events.SUCCEEDED, () => {
            this.closeAfterSave();
        });
        this.useEvent(crawlDomainCreateOp.events.FAILED, (event) => {
            const payload = event && event.payload;
            if (payload && payload.status === 409) {
                this.formErrors = {
                    domain: this.t('crawl_domain_add_modal.err_domain_conflict'),
                };
            }
        });
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('crawl_domain_add_modal.title');
        if (changed.has('crawl_profile_id')) {
            this._domain = '';
            this._runNow = true;
        }
    }

    validateForm() {
        const errors = {};
        const domain = this._domain.trim();
        if (!domain) {
            errors.domain = this.t('crawl_domain_add_modal.err_domain_required');
            return errors;
        }
        if (!domain.includes('.')) {
            errors.domain = this.t('crawl_domain_add_modal.err_domain_invalid');
        }
        return errors;
    }

    async handleSubmit() {
        const crawlProfileId = this.crawl_profile_id.trim();
        if (!crawlProfileId) {
            throw new Error('crawl_domain_add_modal: crawl_profile_id is required');
        }
        const domain = this._domain.trim();
        if (!domain) {
            return;
        }
        this._create.run({
            crawl_profile_id: crawlProfileId,
            domain,
            run_now: this._runNow,
        });
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <p class="hint">${this.t('crawl_domain_add_modal.hint')}</p>
                <div class="form-group">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('crawl_domain_add_modal.label_domain')}
                        placeholder=${this.t('crawl_domain_add_modal.placeholder_domain')}
                        .value=${this._domain}
                        @change=${(event) => {
                            if (!event.detail || typeof event.detail.value !== 'string') {
                                throw new Error('crawl-domain-add: domain expects detail.value string');
                            }
                            this._domain = event.detail.value;
                            this.isDirty = true;
                        }}
                    ></platform-field>
                    ${this.renderFieldError('domain')}
                </div>
                <div class="form-group">
                    <platform-field
                        type="boolean"
                        mode="edit"
                        label=${this.t('crawl_domain_add_modal.label_run_now')}
                        .value=${this._runNow}
                        @change=${(event) => {
                            this._runNow = Boolean(event.detail && event.detail.value);
                            this.isDirty = true;
                        }}
                    ></platform-field>
                </div>
            </form>
        `;
    }

    renderFooter() {
        const canSubmit = this._domain.trim().length > 0 && !this.loading && !this._create.state.busy;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('crawl_domain_add_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${this.loading || this._create.state.busy
                        ? this.t('crawl_domain_add_modal.saving')
                        : this.t('crawl_domain_add_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-crawl-domain-add-modal', FrontendCrawlDomainAddModal);
registerModalKind(FrontendCrawlDomainAddModal.modalKind, 'frontend-crawl-domain-add-modal');

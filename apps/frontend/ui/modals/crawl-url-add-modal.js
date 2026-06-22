/**
 * Модалка добавления конкретных страниц (URL) в домен (company system).
 *
 * Поля API (core/crawl/models.py::CrawlUrlAddRequest):
 *   urls: list[str] (required)
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

export class FrontendCrawlUrlAddModal extends PlatformFormModal {
    static modalKind = 'frontend.crawl_url_add';
    static i18nNamespace = 'frontend';

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .field-help {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: 4px;
            }
        `,
    ];

    static properties = {
        ...PlatformFormModal.properties,
        crawl_profile_id: { type: String },
        crawl_domain_id: { type: String },
        domain: { type: String },
        _urls: { state: true },
    };

    constructor() {
        super();
        this.crawl_profile_id = '';
        this.crawl_domain_id = '';
        this.domain = '';
        this._urls = '';
        this._addOp = this.useOp('frontend/crawl_url_add');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('crawl_report_page.url_add_title');
    }

    _urlsList() {
        return this._urls
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0);
    }

    validateForm() {
        const errors = {};
        if (this._urlsList().length === 0) errors.urls = this.t('crawl_report_page.err_urls_required');
        return errors;
    }

    async handleSubmit() {
        this._addOp.run({
            crawl_profile_id: this.crawl_profile_id,
            crawl_domain_id: this.crawl_domain_id,
            urls: this._urlsList(),
        });
        this.closeAfterSave();
    }

    renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="form-group">
                    <platform-field
                        type="string"
                        mode="view"
                        label=${this.t('crawl_report_page.field_domain')}
                        .value=${this.domain}
                    ></platform-field>
                </div>
                <div class="form-group">
                    <platform-field
                        type="text"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_urls')}
                        placeholder="https://example.com/page"
                        .value=${this._urls}
                        @change=${(e) => { this._urls = String(e.detail.value ?? ''); }}
                    ></platform-field>
                    ${this.renderFieldError('urls')}
                    <div class="field-help">${this.t('crawl_report_page.help_urls')}</div>
                </div>
            </form>
        `;
    }

    renderFooter() {
        const canSubmit = this._urlsList().length > 0 && !this.loading;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('crawl_report_page.cancel')}
                </button>
                <button type="button" class="btn btn-primary" ?disabled=${!canSubmit} @click=${() => this._performSave()}>
                    ${this.t('crawl_report_page.add')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-crawl-url-add-modal', FrontendCrawlUrlAddModal);
registerModalKind(FrontendCrawlUrlAddModal.modalKind, 'frontend-crawl-url-add-modal');

/**
 * Модалка редактирования crawl-домена (company system).
 *
 * Поля API (core/crawl/models.py::CrawlDomainPatchRequest):
 *   status:                   active | paused | blocked | error
 *   refresh_interval_seconds: int | null
 *   include_url_patterns:     list[str]
 *   exclude_url_patterns:     list[str]
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

const STATUS_VALUES = Object.freeze(['active', 'paused', 'blocked']);

export class FrontendCrawlDomainEditModal extends PlatformFormModal {
    static modalKind = 'frontend.crawl_domain_edit';
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
        status: { type: String },
        refresh_interval_seconds: { type: Number },
        include_url_patterns: { type: Array },
        exclude_url_patterns: { type: Array },
        _status: { state: true },
        _refreshInterval: { state: true },
        _includePatterns: { state: true },
        _excludePatterns: { state: true },
        _initialized: { state: true },
    };

    constructor() {
        super();
        this.crawl_profile_id = '';
        this.crawl_domain_id = '';
        this.domain = '';
        this.status = 'active';
        this.refresh_interval_seconds = null;
        this.include_url_patterns = [];
        this.exclude_url_patterns = [];
        this._status = 'active';
        this._refreshInterval = '';
        this._includePatterns = '';
        this._excludePatterns = '';
        this._initialized = false;
        this._patchOp = this.useOp('frontend/crawl_domain_patch');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('crawl_report_page.domain_edit_title');
        if (!this._initialized) {
            this._initialized = true;
            this._status = this.status || 'active';
            this._refreshInterval = typeof this.refresh_interval_seconds === 'number'
                ? String(this.refresh_interval_seconds)
                : '';
            this._includePatterns = (this.include_url_patterns || []).join('\n');
            this._excludePatterns = (this.exclude_url_patterns || []).join('\n');
        }
    }

    validateForm() {
        const errors = {};
        if (this._refreshInterval !== '' && Number(this._refreshInterval) < 60) {
            errors.refresh_interval_seconds = this.t('crawl_report_page.err_interval_min');
        }
        return errors;
    }

    _patternsList(raw) {
        return raw
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0);
    }

    async handleSubmit() {
        const payload = {
            crawl_domain_id: this.crawl_domain_id,
            crawl_profile_id: this.crawl_profile_id,
            status: this._status,
            include_url_patterns: this._patternsList(this._includePatterns),
            exclude_url_patterns: this._patternsList(this._excludePatterns),
        };
        if (this._refreshInterval !== '') {
            payload.refresh_interval_seconds = Number(this._refreshInterval);
        }
        this._patchOp.run(payload);
        this.closeAfterSave();
    }

    _statusOptions() {
        return STATUS_VALUES.map((status) => ({
            value: status,
            label: this.t(`crawl_report_page.status_${status}`),
        }));
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
                        type="enum"
                        label=${this.t('crawl_report_page.field_status')}
                        .value=${this._status}
                        .enumConfig=${{ values: this._statusOptions() }}
                        @value-changed=${(e) => { this._status = e.detail.value; this.isDirty = true; }}
                    ></platform-field>
                </div>
                <div class="form-group">
                    <platform-field
                        type="integer"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_refresh_interval')}
                        placeholder=${this.t('crawl_report_page.placeholder_inherit')}
                        .value=${this._refreshInterval === '' ? null : Number(this._refreshInterval)}
                        @change=${(e) => {
                            const value = e.detail ? e.detail.value : null;
                            this._refreshInterval = typeof value === 'number' ? String(value) : '';
                        }}
                    ></platform-field>
                    ${this.renderFieldError('refresh_interval_seconds')}
                    <div class="field-help">${this.t('crawl_report_page.help_refresh_interval_domain')}</div>
                </div>
                <div class="form-group">
                    <platform-field
                        type="text"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_include_patterns')}
                        .value=${this._includePatterns}
                        @change=${(e) => { this._includePatterns = String(e.detail.value ?? ''); }}
                    ></platform-field>
                    <div class="field-help">${this.t('crawl_report_page.help_include_patterns')}</div>
                </div>
                <div class="form-group">
                    <platform-field
                        type="text"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_exclude_patterns')}
                        .value=${this._excludePatterns}
                        @change=${(e) => { this._excludePatterns = String(e.detail.value ?? ''); }}
                    ></platform-field>
                    <div class="field-help">${this.t('crawl_report_page.help_exclude_patterns')}</div>
                </div>
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('crawl_report_page.cancel')}
                </button>
                <button type="button" class="btn btn-primary" ?disabled=${this.loading} @click=${() => this._performSave()}>
                    ${this.t('crawl_report_page.save')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-crawl-domain-edit-modal', FrontendCrawlDomainEditModal);
registerModalKind(FrontendCrawlDomainEditModal.modalKind, 'frontend-crawl-domain-edit-modal');

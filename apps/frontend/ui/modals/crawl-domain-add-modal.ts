/**
 * Модалка добавления домена в crawl-профиль (company system).
 *
 * Поля API (apps/search/models/contracts.py::CrawlDomainCreateRequest):
 *   domain:                   str (required)
 *   category:                 str
 *   refresh_interval_seconds: int | null
 *   seed_urls:                list[str]
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';

function fieldText(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}

export class FrontendCrawlDomainAddModal extends PlatformFormModal {
    static modalKind = 'frontend.crawl_domain_add';
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            .field-help {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                margin-top: 4px;
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        crawl_profile_id: { type: String },
        _domain: { state: true },
        _category: { state: true },
        _refreshInterval: { state: true },
        _seedUrls: { state: true },
    }
    declare crawl_profile_id: string;
    declare _domain: string;
    declare _category: string;
    declare _refreshInterval: string;
    declare _seedUrls: string;
;

    constructor() {
        super();
        this.crawl_profile_id = '';
        this._domain = '';
        this._category = 'manual';
        this._refreshInterval = '';
        this._seedUrls = '';
        this._createOp = this.useOp('search/crawl_domain_create');
    }
    private _createOp: OpController;


    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('crawl_report_page.domain_add_title');
    }

    override validateForm() {
        const errors: Record<string, unknown> = {};
        if (!this._domain.trim()) errors.domain = this.t('crawl_report_page.err_domain_required');
        if (this._refreshInterval !== '' && Number(this._refreshInterval) < 60) {
            errors.refresh_interval_seconds = this.t('crawl_report_page.err_interval_min');
        }
        return errors;
    }

    _seedUrlsList() {
        return this._seedUrls
            .split('\n')
            .map((line) => line.trim())
            .filter((line) => line.length > 0);
    }

    override async handleSubmit() {
        const payload: {
            crawl_profile_id: string;
            domain: string;
            category: string;
            refresh_interval_seconds?: number;
            seed_urls?: string[];
        } = {
            crawl_profile_id: this.crawl_profile_id,
            domain: this._domain.trim(),
            category: this._category.trim() || 'manual',
        };
        if (this._refreshInterval !== '') {
            payload.refresh_interval_seconds = Number(this._refreshInterval);
        }
        const seedUrls = this._seedUrlsList();
        if (seedUrls.length > 0) payload.seed_urls = seedUrls;
        this._createOp.run(payload);
        this.closeAfterSave();
    }

    override renderBody() {
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <div class="form-group">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_domain')}
                        placeholder="example.com"
                        .value=${this._domain}
                        .error=${this.fieldError('domain')}
                        @change=${(e: CustomEvent) => { this._domain = fieldText(e.detail.value); }}
                    ></platform-field>
                </div>
                <div class="form-group">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_category')}
                        .value=${this._category}
                        @change=${(e: CustomEvent) => { this._category = fieldText(e.detail.value); }}
                    ></platform-field>
                </div>
                <div class="form-group">
                    <platform-field
                        type="integer"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_refresh_interval')}
                        placeholder="21600"
                        .value=${this._refreshInterval === '' ? null : Number(this._refreshInterval)}
                        .error=${this.fieldError('refresh_interval_seconds')}
                        @change=${(e: CustomEvent) => {
                            const value = e.detail ? e.detail.value : null;
                            this._refreshInterval = typeof value === 'number' ? String(value) : '';
                        }}
                    ></platform-field>
                    <div class="field-help">${this.t('crawl_report_page.help_refresh_interval')}</div>
                </div>
                <div class="form-group">
                    <platform-field
                        type="text"
                        mode="edit"
                        label=${this.t('crawl_report_page.field_seed_urls')}
                        placeholder="https://example.com/page"
                        .value=${this._seedUrls}
                        @change=${(e: CustomEvent) => { this._seedUrls = fieldText(e.detail.value); }}
                    ></platform-field>
                    <div class="field-help">${this.t('crawl_report_page.help_seed_urls')}</div>
                </div>
            </form>
        `;
    }

    override renderFooter() {
        const canSubmit = this._domain.trim() && !this.loading;
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

customElements.define('frontend-crawl-domain-add-modal', FrontendCrawlDomainAddModal);
registerModalKind(FrontendCrawlDomainAddModal.modalKind, 'frontend-crawl-domain-add-modal');

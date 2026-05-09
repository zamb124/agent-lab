/**
 * company-modal — окно создания компании.
 *
 * Открытие: dispatch CoreEvents.UI_MODAL_OPEN { kind: 'platform.company_create' }.
 * Закрытие: this.close() / this.closeAfterSave() (dispatch CoreEvents.UI_MODAL_CLOSE).
 *
 * Логика:
 *   - проверка slug — dispatch COMPANIES_EVENTS.SLUG_CHECK_REQUESTED, ответ берётся
 *     селектором из state.companies.slugChecks[slug];
 *   - создание компании — dispatch COMPANIES_EVENTS.CREATE_REQUESTED, по CREATED
 *     модалка закрывается и происходит навигация по redirect_url из payload.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from './glass-form-modal.js';
import { registerModalKind } from '../utils/modal-registry.js';
import { COMPANIES_EVENTS } from '../events/reducers/companies.js';
import { formatCompanySubdomainLabel } from '../utils/tenant-url.js';

const TRANSLIT = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
};

function _slugify(text) {
    if (!text) return '';
    let slug = text.toLowerCase();
    for (const [cyr, lat] of Object.entries(TRANSLIT)) {
        slug = slug.replace(new RegExp(cyr, 'g'), lat);
    }
    slug = slug.replace(/[^a-z0-9-]/g, '-');
    slug = slug.replace(/-+/g, '-');
    slug = slug.replace(/^-+|-+$/g, '');
    return slug;
}

export class CompanyModal extends PlatformFormModal {
    static modalKind = 'platform.company_create';

    static i18nNamespace = 'platform';

    static properties = {
        ...PlatformFormModal.properties,
        companyName: { state: true },
        companySlug: { state: true },
        slugTouched: { state: true },
        slugChecking: { state: true },
        error: { state: true },
    };

    static styles = [
        PlatformFormModal.styles,
        css`
            .input-wrapper { position: relative; }
            .slug-status {
                position: absolute; right: var(--space-3); top: 50%;
                transform: translateY(-50%); font-size: var(--text-sm);
            }
            .slug-status.checking { opacity: 0.6; }
            .slug-status.available { color: #34C759; }
            .slug-status.unavailable { color: #FF3B30; }
            .slug-hint { font-size: var(--text-xs); opacity: 0.6; margin-top: 4px; }
            .slug-preview { font-size: var(--text-xs); color: var(--accent); margin-top: 4px; }
            .slug-error { font-size: var(--text-xs); color: #FF3B30; margin-top: 4px; }
            .error {
                margin-top: var(--space-3); padding: var(--space-3);
                background: rgba(255, 59, 48, 0.1);
                border: 1px solid rgba(255, 59, 48, 0.3);
                border-radius: var(--radius-sm);
                color: #FF3B30; font-size: var(--text-sm); text-align: center;
            }
        `,
    ];

    constructor() {
        super();
        this.companyName = '';
        this.companySlug = '';
        this.slugTouched = false;
        this.slugChecking = false;
        this.error = '';
        this._debounceTimer = null;
        this._slugChecksSel = this.select((s) => s.companies.slugChecks);
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(COMPANIES_EVENTS.SLUG_CHECKED, (e) => {
            const slug = e.payload && e.payload.slug;
            if (slug === this.companySlug) {
                this.slugChecking = false;
            }
        });
        this.useEvent(COMPANIES_EVENTS.SLUG_CHECK_FAILED, (e) => {
            const slug = e.payload && e.payload.slug;
            if (slug === this.companySlug) {
                this.slugChecking = false;
                this.error = (e.payload && e.payload.message)
                    || (this.t('company.slug_check_error') || 'company.slug_check_error');
            }
        });
        this.useEvent(COMPANIES_EVENTS.CREATED, (e) => {
            this.loading = false;
            this.closeAfterSave();
            const url = e.payload && e.payload.redirect_url;
            if (url) {
                window.location.href = url;
            } else {
                window.location.reload();
            }
        });
        this.useEvent(COMPANIES_EVENTS.CREATE_FAILED, (e) => {
            this.loading = false;
            this.error = (e.payload && e.payload.message)
                || (this.t('company.error_create') || 'company.error_create');
        });
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._debounceTimer) {
            clearTimeout(this._debounceTimer);
            this._debounceTimer = null;
        }
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('company.create_title') || 'company.create_title';
    }

    _slugCheck() {
        const slug = this.companySlug;
        if (!slug || slug.length < 3) return null;
        const checks = (this._slugChecksSel && this._slugChecksSel.value) || {};
        return checks[slug] || null;
    }

    _slugError() {
        if (!this.companySlug) return '';
        if (this.companySlug.length < 3) return this.t('company.slug_min') || 'company.slug_min';
        const r = this._slugCheck();
        if (r && r.available === false) return this.t('company.slug_taken') || 'company.slug_taken';
        return '';
    }

    _isAvailable() {
        const r = this._slugCheck();
        return r && r.available === true;
    }

    _onName(e) {
        this.companyName = e.target.value;
        this.isDirty = true;
        if (!this.slugTouched) {
            this.companySlug = _slugify(this.companyName);
            this._scheduleSlugCheck();
        }
    }

    _onSlug(e) {
        this.companySlug = e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '');
        this.slugTouched = true;
        this.isDirty = true;
        this._scheduleSlugCheck();
    }

    _scheduleSlugCheck() {
        if (this._debounceTimer) clearTimeout(this._debounceTimer);
        this._debounceTimer = setTimeout(() => {
            if (!this.companySlug || this.companySlug.length < 3) return;
            const checks = (this._slugChecksSel && this._slugChecksSel.value) || {};
            if (checks[this.companySlug]) return;
            this.slugChecking = true;
            this.dispatch(COMPANIES_EVENTS.SLUG_CHECK_REQUESTED, { slug: this.companySlug });
        }, 400);
    }

    validateForm() {
        const errs = {};
        if (!this.companyName.trim()) {
            errs.name = this.t('company.error_name_required') || 'company.error_name_required';
        }
        if (!this.companySlug || this.companySlug.length < 3) {
            errs.slug = this.t('company.error_slug_invalid') || 'company.error_slug_invalid';
        }
        if (!this._isAvailable()) {
            errs.slug = this.t('company.error_slug_taken') || 'company.error_slug_taken';
        }
        return errs;
    }

    async handleSubmit() {
        this.error = '';
        this.dispatch(COMPANIES_EVENTS.CREATE_REQUESTED, {
            name: this.companyName,
            slug: this.companySlug,
        });
    }

    renderBody() {
        const t = (key) => this.t(key) || key;
        const slugErr = this._slugError();
        const isAvail = this._isAvailable();
        return html`
            <p class="modal-subtitle">${t('company.create_subtitle')}</p>
            <form @submit=${this._onSubmit}>
                <div class="form-group">
                    <label class="form-label">${t('company.name_label')}</label>
                    <input
                        type="text"
                        class="form-input"
                        .value=${this.companyName}
                        @input=${this._onName}
                        placeholder=${t('company.name_placeholder')}
                        ?disabled=${this.loading}
                        required
                    />
                </div>
                <div class="form-group">
                    <label class="form-label">${t('company.slug_label')}</label>
                    <div class="input-wrapper">
                        <input
                            type="text"
                            class="form-input"
                            .value=${this.companySlug}
                            @input=${this._onSlug}
                            placeholder="moya-kompaniya"
                            pattern="[a-z0-9-]+"
                            minlength="3"
                            maxlength="63"
                            ?disabled=${this.loading}
                            required
                        />
                        ${this.slugChecking
                            ? html`<span class="slug-status checking">…</span>`
                            : isAvail
                                ? html`<span class="slug-status available">✓</span>`
                                : (slugErr
                                    ? html`<span class="slug-status unavailable">✗</span>`
                                    : '')}
                    </div>
                    ${slugErr
                        ? html`<div class="slug-error">${slugErr}</div>`
                        : (this.companySlug
                            ? html`<div class="slug-preview">${formatCompanySubdomainLabel(this.companySlug)}</div>`
                            : html`<div class="slug-hint">${t('company.slug_hint')}</div>`)}
                </div>
                ${this.error ? html`<div class="error">${this.error}</div>` : ''}
            </form>
        `;
    }

    renderFooter() {
        const t = (key) => this.t(key) || key;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${this.close}>
                    ${t('form_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    @click=${() => this._performSave()}
                    ?disabled=${this.loading || this.slugChecking || !this._isAvailable()}
                >
                    ${this.loading ? t('company.creating') : t('company.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('company-modal', CompanyModal);
registerModalKind(CompanyModal.modalKind, 'company-modal');

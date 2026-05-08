/**
 * Settings page — настройки компании в трёх вкладках:
 *
 *   - company:      имя, subdomain (read-only), monthly_budget, RAG embedding override,
 *                   metadata (JSON-textarea)
 *   - security:     OAuth providers (плейсхолдер)
 *   - integrations: список доступных интеграций (статичный, переходы по router)
 *
 * Сохранение собирает только изменённые поля → settingsUpdateOp.run(body);
 * успех → toast и перезагрузка settingsLoadOp.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { frontendIslandPageBodyStyles } from '../../styles/frontend-island-page-body.styles.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';

const PROVIDER_OPTIONS = Object.freeze(['openrouter', 'provider_litserve']);

const INTEGRATION_LIST = Object.freeze([
    { id: 'crm', route: '/crm' },
    { id: 'flows', route: '/flows' },
    { id: 'rag', route: '/rag' },
    { id: 'sync', route: '/sync' },
]);

export class FrontendSettingsPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host { display: block; }

            .tabs {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .tab {
                padding: var(--space-3) var(--space-4);
                background: transparent;
                color: var(--text-secondary);
                border: none;
                cursor: pointer;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                border-bottom: 2px solid transparent;
            }
            .tab[data-active="true"] {
                color: var(--text-primary);
                border-bottom-color: var(--accent);
            }

            section { margin-bottom: var(--space-6); }
            section h3 {
                color: var(--text-primary);
                font-size: var(--text-lg);
                margin: 0 0 var(--space-3) 0;
            }
            section .section-help {
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-3);
            }

            .form { display: flex; flex-direction: column; gap: var(--space-4); max-width: 720px; }
            .field-error { color: var(--error); font-size: var(--text-xs); }

            .toggle-row {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-3); background: var(--glass-solid-subtle);
                border-radius: var(--radius-md);
            }

            .info-grid {
                display: grid;
                grid-template-columns: 160px 1fr;
                gap: var(--space-2) var(--space-3);
                font-size: var(--text-sm);
                background: var(--glass-solid-subtle);
                padding: var(--space-3);
                border-radius: var(--radius-md);
            }
            .info-grid dt { color: var(--text-tertiary); }
            .info-grid dd { margin: 0; color: var(--text-primary); font-family: var(--font-mono); font-size: var(--text-xs); }

            .btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent); color: white; border: none;
                border-radius: var(--radius-md); cursor: pointer;
                font-size: var(--text-sm); font-weight: var(--font-medium);
                align-self: flex-start;
            }
            .btn:hover { filter: brightness(1.1); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .btn-ghost { background: transparent; color: var(--text-secondary); border: 1px solid var(--glass-border-subtle); }

            .integration-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                gap: var(--space-3);
            }
            .integration-card {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                display: flex; flex-direction: column; gap: var(--space-2);
            }
            .integration-card .integration-name { color: var(--text-primary); font-weight: var(--font-semibold); }
            .integration-card .integration-id { color: var(--text-tertiary); font-size: var(--text-xs); font-family: var(--font-mono); }

            .empty {
                padding: var(--space-6);
                text-align: center; color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-md);
            }
        `,
        frontendIslandPageBodyStyles,
    ];

    static properties = {
        _activeTab: { state: true },
        _name: { state: true },
        _monthlyBudget: { state: true },
        _ragEnabled: { state: true },
        _ragProvider: { state: true },
        _ragModel: { state: true },
        _metadataJson: { state: true },
        _metadataError: { state: true },
    };

    constructor() {
        super();
        this._load = this.useOp('frontend/settings_load');
        this._update = this.useOp('frontend/settings_update');
        this._loaded = false;
        this._draftSeeded = false;
        this._activeTab = 'company';
        this._name = '';
        this._monthlyBudget = 0;
        this._ragEnabled = false;
        this._ragProvider = '';
        this._ragModel = '';
        this._metadataJson = '{}';
        this._metadataError = '';
    }

    updated() {
        if (!this._loaded) {
            this._loaded = true;
            this._load.run();
        }
        const company = this._load.lastResult;
        if (!this._draftSeeded && company) {
            this._draftSeeded = true;
            this._seedDraft(company);
        }
    }

    _seedDraft(company) {
        this._name = company.name || '';
        this._monthlyBudget = Number(company.monthly_budget || 0);
        const rag = company.rag_embedding || {};
        this._ragEnabled = !!rag.enabled;
        this._ragProvider = rag.provider || rag.default_provider || '';
        this._ragModel = rag.model || rag.default_model || '';
        const metadata = company.metadata || {};
        this._metadataJson = JSON.stringify(metadata, null, 2);
    }

    _setTab(tab) {
        this._activeTab = tab;
    }

    _save() {
        let metadata = null;
        const trimmed = (this._metadataJson || '').trim();
        if (trimmed) {
            try {
                const parsed = JSON.parse(trimmed);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    metadata = parsed;
                    this._metadataError = '';
                } else {
                    this._metadataError = this.t('settings_page.metadata_invalid');
                    return;
                }
            } catch {
                this._metadataError = this.t('settings_page.metadata_invalid');
                return;
            }
        }
        const body = {
            name: this._name.trim(),
            monthly_budget: this._monthlyBudget,
            rag_embedding: {
                enabled: this._ragEnabled,
                provider: this._ragEnabled ? this._ragProvider : null,
                model: this._ragEnabled ? this._ragModel.trim() : null,
            },
        };
        if (metadata !== null) body.metadata = metadata;
        this._update.run(body);
    }

    _renderTabs() {
        const tabs = [
            { id: 'company', label: this.t('settings_page.tab_company') },
            { id: 'security', label: this.t('settings_page.tab_security') },
            { id: 'integrations', label: this.t('settings_page.tab_integrations') },
        ];
        return html`
            <div class="tabs">
                ${tabs.map((t) => html`
                    <button class="tab"
                        data-active=${this._activeTab === t.id ? 'true' : 'false'}
                        @click=${() => this._setTab(t.id)}
                    >${t.label}</button>
                `)}
            </div>
        `;
    }

    _ragProviderEnumConfig() {
        return {
            values: [
                { value: '', label: '\u2014' },
                ...PROVIDER_OPTIONS.map((p) => ({
                    value: p,
                    label: this.t(`settings_page.provider_${p}`),
                })),
            ],
        };
    }

    _renderCompanyTab(company) {
        const ragDefaultProvider = (company.rag_embedding && company.rag_embedding.default_provider) || '';
        const ragDefaultModel = (company.rag_embedding && company.rag_embedding.default_model) || '';
        const saving = this._update.busy;
        return html`
            <section>
                <h3>${this.t('settings_page.section_company')}</h3>
                <div class="info-grid">
                    <dt>${this.t('settings_page.company_id')}</dt><dd>${company.company_id || ''}</dd>
                    <dt>${this.t('settings_page.company_status')}</dt><dd>${company.status || ''}</dd>
                    <dt>${this.t('settings_page.company_owner')}</dt><dd>${company.owner_user_id ? html`<platform-user-chip user-id=${company.owner_user_id} size="sm"></platform-user-chip>` : ''}</dd>
                    <dt>${this.t('settings_page.tariff_plan')}</dt><dd>${company.tariff_plan || ''}</dd>
                    <dt>${this.t('settings_page.created_at')}</dt><dd>${company.created_at ? new Date(company.created_at).toLocaleString() : ''}</dd>
                </div>
            </section>

            <section>
                <h3>${this.t('settings_page.company_section')}</h3>
                <div class="form">
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('settings_page.label_company_name')}
                        .value=${this._name}
                        @change=${(e) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('settings: company name expects detail.value string');
                            }
                            this._name = e.detail.value;
                        }}
                    ></platform-field>
                    <platform-field
                        type="string"
                        mode="view"
                        label=${this.t('settings_page.label_subdomain')}
                        .value=${company.subdomain || ''}
                    ></platform-field>
                    <small>${this.t('settings_page.subdomain_help')}</small>
                    <platform-field
                        type="integer"
                        mode="edit"
                        label=${this.t('settings_page.label_monthly_budget')}
                        .value=${this._monthlyBudget}
                        @change=${(e) => {
                            if (!e.detail || e.detail.value === null || typeof e.detail.value !== 'number') {
                                throw new Error('settings: monthly budget expects integer detail.value');
                            }
                            this._monthlyBudget = e.detail.value;
                        }}
                    ></platform-field>
                    <small>${this.t('settings_page.budget_help')}</small>
                </div>
            </section>

            <section>
                <h3>${this.t('settings_page.section_rag')}</h3>
                <div class="section-help">${this.t('settings_page.rag_override_help')}</div>
                <div class="form">
                    <div class="toggle-row">
                        <input type="checkbox" id="rag-toggle"
                            .checked=${this._ragEnabled}
                            @change=${(e) => { this._ragEnabled = e.target.checked; }}
                        />
                        <label for="rag-toggle">${this.t('settings_page.rag_override_enable')}</label>
                    </div>
                    <platform-field
                        type="enum"
                        mode="edit"
                        label=${this.t('settings_page.rag_provider_label')}
                        ?disabled=${!this._ragEnabled}
                        .value=${this._ragProvider}
                        .config=${this._ragProviderEnumConfig()}
                        @change=${(e) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('settings: rag provider expects detail.value string');
                            }
                            this._ragProvider = e.detail.value;
                        }}
                    ></platform-field>
                    <small>${this.t('settings_page.rag_provider_default', { provider: ragDefaultProvider })}</small>
                    <platform-field
                        type="string"
                        mode="edit"
                        label=${this.t('settings_page.rag_model_label')}
                        ?disabled=${!this._ragEnabled}
                        .value=${this._ragModel}
                        @change=${(e) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('settings: rag model expects detail.value string');
                            }
                            this._ragModel = e.detail.value;
                        }}
                    ></platform-field>
                    <small>${this.t('settings_page.rag_model_default', { model: ragDefaultModel })}</small>
                </div>
            </section>

            <section>
                <h3>${this.t('settings_page.metadata_title')}</h3>
                <div class="section-help">${this.t('settings_page.metadata_help')}</div>
                <div class="form">
                    <platform-field
                        type="text"
                        mode="edit"
                        label=""
                        .value=${this._metadataJson}
                        @change=${(e) => {
                            if (!e.detail || typeof e.detail.value !== 'string') {
                                throw new Error('settings: metadata expects detail.value string');
                            }
                            this._metadataJson = e.detail.value;
                            this._metadataError = '';
                        }}
                    ></platform-field>
                    ${this._metadataError ? html`<div class="field-error">${this._metadataError}</div>` : ''}
                </div>
            </section>

            <button class="btn" ?disabled=${saving} @click=${this._save}>
                ${saving ? this.t('settings_page.saving') : this.t('settings_page.save')}
            </button>
        `;
    }

    _renderSecurityTab() {
        return html`
            <section>
                <h3>${this.t('settings_page.security_title')}</h3>
                <div class="section-help">${this.t('settings_page.security_info')}</div>
                <div class="empty">${this.t('settings_page.sessions_placeholder')}</div>
            </section>
            <section>
                <h3>${this.t('settings_page.oauth_title')}</h3>
                <div class="section-help">${this.t('settings_page.oauth_info')}</div>
                <div class="empty">—</div>
            </section>
        `;
    }

    _renderIntegrationsTab() {
        return html`
            <section>
                <h3>${this.t('settings_page.integrations_title')}</h3>
                <div class="section-help">${this.t('settings_page.integrations_info')}</div>
                <div class="integration-grid">
                    ${INTEGRATION_LIST.map((it) => html`
                        <div class="integration-card">
                            <div class="integration-name">${it.id}</div>
                            <div class="integration-id">${it.route}</div>
                            <button class="btn btn-ghost"
                                @click=${() => this.navigate(it.route)}
                            >${this.t('settings_page.connect')}</button>
                        </div>
                    `)}
                </div>
            </section>
        `;
    }

    render() {
        const company = this._load.lastResult;
        if (!company) {
            return html`
                <page-header title=${this.t('settings_page.title')}></page-header>
                <div class="page-body">
                <div class="empty"><glass-spinner></glass-spinner></div>
                </div>
            `;
        }
        return html`
            <page-header title=${this.t('settings_page.title')}></page-header>
            <div class="page-body">
            ${this._renderTabs()}
            ${this._activeTab === 'company' ? this._renderCompanyTab(company) : ''}
            ${this._activeTab === 'security' ? this._renderSecurityTab() : ''}
            ${this._activeTab === 'integrations' ? this._renderIntegrationsTab() : ''}
            </div>
        `;
    }
}

customElements.define('frontend-settings-page', FrontendSettingsPage);

/**
 * Settings Page - Настройки компании
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendStore } from '../../store/frontend.store.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/glass-spinner.js';

export class SettingsPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .tab-content {
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                padding: var(--space-8);
                backdrop-filter: blur(20px);
            }

            .form-group {
                margin-bottom: var(--space-6);
            }

            .form-label {
                display: block;
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }

            .form-input {
                width: 100%;
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-base);
                outline: none;
                transition: all var(--duration-fast);
                box-sizing: border-box;
            }

            .form-input:focus {
                background: var(--glass-solid-medium);
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-subtle);
            }

            .form-input:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }

            .form-help {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            .primary-button {
                padding: var(--space-3) var(--space-6);
                background: var(--accent);
                color: white;
                border: none;
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .primary-button:hover {
                transform: scale(1.05);
                box-shadow: 0 8px 24px rgba(153, 166, 249, 0.4);
            }

            .section-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-4) 0;
            }

            .page-loading {
                display: flex;
                align-items: center;
                justify-content: center;
                flex: 1;
                min-height: 200px;
            }
        `
    ];

    constructor() {
        super();
        this.state = this.use((s) => ({
            settings: s.entities.settings.company,
            loading: s.entities.settings.loading,
        }));
    }

    async connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        await this._loadSettings();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async _loadSettings() {
        const { settings } = this.state.value;
        if (settings) return;
        
        FrontendStore.setSettingsLoading(true);
        const companySettings = await this.services.get('settings').getCompanySettings();
        FrontendStore.setCompanySettings(companySettings);
    }

    render() {
        const td = (key, params) => this.i18n.t(key, params ?? {});
        const { loading } = this.state.value;
        
        if (loading) {
            return html`<div class="page-loading"><glass-spinner size="lg"></glass-spinner></div>`;
        }

        return html`
            <page-header title=${td('settings_page.title')}></page-header>
            ${this._renderCompanySettings()}
        `;
    }

    _renderCompanySettings() {
        const td = (key, params) => this.i18n.t(key, params ?? {});
        const { settings } = this.state.value;
        
        return html`
            <div class="tab-content">
                <h2 class="section-title">${td('settings_page.company_section')}</h2>
                
                <form @submit=${this._onSaveCompany}>
                    <div class="form-group">
                        <label class="form-label">${td('settings_page.label_company_name')}</label>
                        <input
                            type="text"
                            class="form-input"
                            value="${settings?.name ?? ''}"
                            id="company-name"
                            required
                        />
                    </div>

                    <div class="form-group">
                        <label class="form-label">${td('settings_page.label_subdomain')}</label>
                        <input
                            type="text"
                            class="form-input"
                            value="${settings?.subdomain ?? ''}"
                            disabled
                        />
                        <div class="form-help">
                            ${td('settings_page.subdomain_help')}
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">${td('settings_page.label_monthly_budget')}</label>
                        <input
                            type="number"
                            class="form-input"
                            value="${settings?.monthly_budget ?? 0}"
                            id="monthly-budget"
                            min="0"
                        />
                        <div class="form-help">
                            ${td('settings_page.budget_help')}
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">${td('settings_page.rag_override_title')}</label>
                        <input
                            type="checkbox"
                            id="rag-override-enabled"
                            ?checked=${settings?.rag_embedding?.enabled ?? false}
                        />
                        <div class="form-help">
                            ${td('settings_page.rag_override_help')}
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">${td('settings_page.rag_provider_label')}</label>
                        <select
                            class="form-input"
                            id="rag-provider"
                        >
                            <option value="provider_litserve" ?selected=${(settings?.rag_embedding?.provider ?? '') === 'provider_litserve'}>
                                ${td('settings_page.provider_humanitec')}
                            </option>
                            <option value="openrouter" ?selected=${(settings?.rag_embedding?.provider ?? '') === 'openrouter'}>
                                ${td('settings_page.provider_openrouter')}
                            </option>
                        </select>
                        <div class="form-help">
                            ${td('settings_page.rag_provider_default', { provider: settings?.rag_embedding?.default_provider ?? '' })}
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">${td('settings_page.rag_model_label')}</label>
                        <input
                            type="text"
                            class="form-input"
                            value="${settings?.rag_embedding?.model ?? ''}"
                            id="rag-model"
                        />
                        <div class="form-help">
                            ${td('settings_page.rag_model_default', { model: settings?.rag_embedding?.default_model ?? '' })}
                        </div>
                    </div>

                    <button type="submit" class="primary-button">
                        ${td('settings_page.save')}
                    </button>
                </form>
            </div>
        `;
    }

    async _onSaveCompany(e) {
        e.preventDefault();
        
        const name = this.shadowRoot.getElementById('company-name').value;
        const monthlyBudget = parseFloat(this.shadowRoot.getElementById('monthly-budget').value);
        const ragOverrideEnabled = this.shadowRoot.getElementById('rag-override-enabled').checked;
        const ragProvider = this.shadowRoot.getElementById('rag-provider').value;
        const ragModel = this.shadowRoot.getElementById('rag-model').value;
        
        await this.services.get('settings').updateCompanySettings({
            name,
            monthly_budget: monthlyBudget,
            rag_embedding: {
                enabled: ragOverrideEnabled,
                provider: ragProvider,
                model: ragModel,
            },
        });
        
        FrontendStore.setSettingsLoading(true);
        const companySettings = await this.services.get('settings').getCompanySettings();
        FrontendStore.setCompanySettings(companySettings);
        
        this.success(this.i18n.t('settings_page.toast_saved', {}));
    }
}

customElements.define('settings-page', SettingsPage);

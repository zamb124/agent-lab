/**
 * Settings Page - Настройки компании
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendStore } from '../../store/frontend.store.js';
import '@platform/lib/components/layout/page-header.js';

export class SettingsPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            .page-container {
                max-width: 1200px;
                margin: 0 auto;
            }

            .tabs {
                display: flex;
                gap: var(--space-2);
                margin-bottom: var(--space-8);
                border-bottom: 1px solid var(--glass-border-subtle);
                padding-bottom: var(--space-2);
            }

            .tab {
                padding: var(--space-3) var(--space-6);
                background: transparent;
                border: none;
                border-radius: var(--radius-md) var(--radius-md) 0 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .tab:hover {
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
            }

            .tab.active {
                color: var(--text-primary);
                background: var(--accent-subtle);
                border-bottom: 2px solid var(--accent);
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
                box-shadow: 0 8px 24px rgba(16, 185, 129, 0.4);
            }

            .providers-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-4);
                margin-bottom: var(--space-6);
            }

            .provider-card {
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-5);
                text-align: center;
                transition: all var(--duration-fast);
            }

            .provider-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }

            .provider-icon {
                font-size: var(--text-5xl);
                margin-bottom: var(--space-3);
            }

            .provider-name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-2) 0;
            }

            .provider-status {
                font-size: var(--text-xs);
                padding: var(--space-1) var(--space-3);
                background: var(--success-subtle);
                color: var(--success);
                border-radius: var(--radius-sm);
                display: inline-block;
            }

            .section-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-4) 0;
            }

            .info-box {
                background: var(--accent-subtle);
                border: 1px solid var(--accent);
                border-radius: var(--radius-lg);
                padding: var(--space-4);
                margin-bottom: var(--space-6);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            .loading-state {
                text-align: center;
                padding: var(--space-12);
                color: var(--text-secondary);
            }

            @media (max-width: 768px) {
                .tabs {
                    overflow-x: auto;
                    -webkit-overflow-scrolling: touch;
                }

                .tab {
                    white-space: nowrap;
                }

                .providers-grid {
                    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                }
            }
        `
    ];

    constructor() {
        super();
        this._activeTab = 'company';
        
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
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
        const { loading } = this.state.value;
        
        if (loading) {
            return html`
                <div class="loading-state">
                    ${td('settings_page.loading')}
                </div>
            `;
        }

        return html`
            <page-header title=${td('settings_page.title')}></page-header>

            <div class="tabs">
                <button 
                    class="tab ${this._activeTab === 'company' ? 'active' : ''}"
                    @click=${() => this._setTab('company')}
                >
                    ${td('settings_page.tab_company')}
                </button>
                <button 
                    class="tab ${this._activeTab === 'security' ? 'active' : ''}"
                    @click=${() => this._setTab('security')}
                >
                    ${td('settings_page.tab_security')}
                </button>
                <button 
                    class="tab ${this._activeTab === 'integrations' ? 'active' : ''}"
                    @click=${() => this._setTab('integrations')}
                >
                    ${td('settings_page.tab_integrations')}
                </button>
            </div>

            ${this._renderTabContent()}
        `;
    }

    _renderTabContent() {
        switch (this._activeTab) {
            case 'company':
                return this._renderCompanyTab();
            case 'security':
                return this._renderSecurityTab();
            case 'integrations':
                return this._renderIntegrationsTab();
            default:
                throw new Error(`Unknown tab: ${this._activeTab}`);
        }
    }

    _renderCompanyTab() {
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
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

                    <button type="submit" class="primary-button">
                        ${td('settings_page.save')}
                    </button>
                </form>
            </div>
        `;
    }

    _renderSecurityTab() {
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
        return html`
            <div class="tab-content">
                <h2 class="section-title">${td('settings_page.oauth_title')}</h2>
                
                <div class="info-box">
                    ${td('settings_page.oauth_info')}
                </div>

                <div class="providers-grid">
                    <div class="provider-card">
                        <div class="provider-icon">Y</div>
                        <h3 class="provider-name">Yandex</h3>
                        <span class="provider-status">${td('settings_page.provider_active')}</span>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">G</div>
                        <h3 class="provider-name">Google</h3>
                        <span class="provider-status">${td('settings_page.provider_active')}</span>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">H</div>
                        <h3 class="provider-name">GitHub</h3>
                        <span class="provider-status">${td('settings_page.provider_active')}</span>
                    </div>
                </div>

                <h2 class="section-title">${td('settings_page.sessions_title')}</h2>
                <div class="info-box">
                    ${td('settings_page.sessions_placeholder')}
                </div>
            </div>
        `;
    }

    _renderIntegrationsTab() {
        const td = (key, params) => this.i18n.t(key, params ?? {}, 'dashboard');
        return html`
            <div class="tab-content">
                <h2 class="section-title">${td('settings_page.integrations_title')}</h2>
                
                <div class="info-box">
                    ${td('settings_page.integrations_info')}
                </div>

                <div class="providers-grid">
                    <div class="provider-card">
                        <div class="provider-icon">T</div>
                        <h3 class="provider-name">Telegram</h3>
                        <button class="primary-button" style="margin-top: var(--space-3); width: 100%;">
                            ${td('settings_page.connect')}
                        </button>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">S</div>
                        <h3 class="provider-name">Slack</h3>
                        <button class="primary-button" style="margin-top: var(--space-3); width: 100%;">
                            ${td('settings_page.connect')}
                        </button>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">W</div>
                        <h3 class="provider-name">Webhooks</h3>
                        <button class="primary-button" style="margin-top: var(--space-3); width: 100%;">
                            ${td('settings_page.configure')}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    _setTab(tab) {
        this._activeTab = tab;
        this.requestUpdate();
    }

    async _onSaveCompany(e) {
        e.preventDefault();
        
        const name = this.shadowRoot.getElementById('company-name').value;
        const monthlyBudget = parseFloat(this.shadowRoot.getElementById('monthly-budget').value);
        
        await this.services.get('settings').updateCompanySettings({
            name,
            monthly_budget: monthlyBudget,
        });
        
        FrontendStore.setSettingsLoading(true);
        const companySettings = await this.services.get('settings').getCompanySettings();
        FrontendStore.setCompanySettings(companySettings);
        
        this.success(this.i18n.t('settings_page.toast_saved', {}, 'dashboard'));
    }
}

customElements.define('settings-page', SettingsPage);

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
        await this._loadSettings();
    }

    async _loadSettings() {
        const { settings } = this.state.value;
        if (settings) return;
        
        FrontendStore.setSettingsLoading(true);
        const companySettings = await this.services.get('settings').getCompanySettings();
        FrontendStore.setCompanySettings(companySettings);
    }

    render() {
        const { loading } = this.state.value;
        
        if (loading) {
            return html`
                <div class="loading-state">
                    Загрузка...
                </div>
            `;
        }

        return html`
            <page-header title="Настройки"></page-header>

            <div class="tabs">
                <button 
                    class="tab ${this._activeTab === 'company' ? 'active' : ''}"
                    @click=${() => this._setTab('company')}
                >
                    Компания
                </button>
                <button 
                    class="tab ${this._activeTab === 'security' ? 'active' : ''}"
                    @click=${() => this._setTab('security')}
                >
                    Безопасность
                </button>
                <button 
                    class="tab ${this._activeTab === 'integrations' ? 'active' : ''}"
                    @click=${() => this._setTab('integrations')}
                >
                    Интеграции
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
        const { settings } = this.state.value;
        
        return html`
            <div class="tab-content">
                <h2 class="section-title">Информация о компании</h2>
                
                <form @submit=${this._onSaveCompany}>
                    <div class="form-group">
                        <label class="form-label">Название компании</label>
                        <input
                            type="text"
                            class="form-input"
                            value="${settings?.name ?? ''}"
                            id="company-name"
                            required
                        />
                    </div>

                    <div class="form-group">
                        <label class="form-label">Subdomain</label>
                        <input
                            type="text"
                            class="form-input"
                            value="${settings?.subdomain ?? ''}"
                            disabled
                        />
                        <div class="form-help">
                            Поддомен нельзя изменить после создания
                        </div>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Месячный лимит расходов (Р)</label>
                        <input
                            type="number"
                            class="form-input"
                            value="${settings?.monthly_budget ?? 0}"
                            id="monthly-budget"
                            min="0"
                        />
                        <div class="form-help">
                            0 = без ограничений
                        </div>
                    </div>

                    <button type="submit" class="primary-button">
                        Сохранить изменения
                    </button>
                </form>
            </div>
        `;
    }

    _renderSecurityTab() {
        return html`
            <div class="tab-content">
                <h2 class="section-title">OAuth Провайдеры</h2>
                
                <div class="info-box">
                    Настройте методы авторизации для вашей команды
                </div>

                <div class="providers-grid">
                    <div class="provider-card">
                        <div class="provider-icon">Y</div>
                        <h3 class="provider-name">Yandex</h3>
                        <span class="provider-status">Активен</span>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">G</div>
                        <h3 class="provider-name">Google</h3>
                        <span class="provider-status">Активен</span>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">H</div>
                        <h3 class="provider-name">GitHub</h3>
                        <span class="provider-status">Активен</span>
                    </div>
                </div>

                <h2 class="section-title">Активные сессии</h2>
                <div class="info-box">
                    Список активных сессий будет доступен в следующей версии
                </div>
            </div>
        `;
    }

    _renderIntegrationsTab() {
        return html`
            <div class="tab-content">
                <h2 class="section-title">Доступные интеграции</h2>
                
                <div class="info-box">
                    Интеграции позволяют подключить внешние сервисы к вашей платформе
                </div>

                <div class="providers-grid">
                    <div class="provider-card">
                        <div class="provider-icon">T</div>
                        <h3 class="provider-name">Telegram</h3>
                        <button class="primary-button" style="margin-top: var(--space-3); width: 100%;">
                            Подключить
                        </button>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">S</div>
                        <h3 class="provider-name">Slack</h3>
                        <button class="primary-button" style="margin-top: var(--space-3); width: 100%;">
                            Подключить
                        </button>
                    </div>
                    
                    <div class="provider-card">
                        <div class="provider-icon">W</div>
                        <h3 class="provider-name">Webhooks</h3>
                        <button class="primary-button" style="margin-top: var(--space-3); width: 100%;">
                            Настроить
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
        
        this.success('Настройки сохранены');
    }
}

customElements.define('settings-page', SettingsPage);

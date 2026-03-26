import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendStore } from '../store/frontend.store.js';
import '@platform/lib/components/company-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';

export class DashboardPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .services-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: var(--space-6);
                margin-bottom: var(--space-8);
            }

            .service-card {
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-6);
                backdrop-filter: blur(20px);
                cursor: pointer;
                transition: all var(--duration-normal);
            }

            .service-card:hover {
                background: var(--glass-solid-strong);
                border-color: var(--border-default);
                transform: translateY(-4px);
                box-shadow: var(--shadow-lg);
            }

            .service-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: var(--space-4);
            }

            .service-icon {
                width: 48px;
                height: 48px;
            }

            .service-icon img {
                width: 100%;
                height: 100%;
            }

            .service-go-icon {
                width: 24px;
                height: 24px;
                color: var(--text-secondary);
                transition: transform var(--duration-normal), color var(--duration-normal);
            }

            .service-card:hover .service-go-icon {
                color: var(--accent);
                transform: translateX(4px);
            }

            .service-name {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-2) 0;
            }

            .service-description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0;
            }

            .quick-actions {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: var(--space-6);
                margin-bottom: var(--space-8);
            }

            .action-card {
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-6);
                backdrop-filter: blur(20px);
                cursor: pointer;
                transition: all var(--duration-normal);
                display: flex;
                align-items: center;
                gap: var(--space-4);
            }

            .action-card:hover {
                background: var(--accent-subtle);
                border-color: var(--accent);
                transform: scale(1.02);
            }

            .action-icon {
                display: flex;
                align-items: center;
                justify-content: center;
                min-width: 40px;
                width: 40px;
                height: 40px;
                flex-shrink: 0;
                color: var(--text-primary);
            }

            .action-icon platform-icon {
                color: var(--accent);
            }

            .action-card:hover .action-icon platform-icon {
                color: var(--accent-hover, var(--accent));
            }

            .action-content {
                flex: 1;
            }

            .action-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-1) 0;
            }

            .action-description {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0;
            }

            .stats-section {
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-8);
                backdrop-filter: blur(20px);
                margin-bottom: var(--space-8);
            }

            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: var(--space-8);
                margin-top: var(--space-6);
            }

            .stat-item {
                text-align: center;
            }

            .stat-value {
                font-size: var(--text-4xl);
                font-weight: var(--font-bold);
                color: var(--accent);
                margin: 0 0 var(--space-2) 0;
            }

            .stat-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin: 0;
            }

            .loading-state {
                text-align: center;
                padding: var(--space-12);
                color: var(--text-secondary);
            }

            .section-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-4) 0;
            }

            @media (max-width: 768px) {
                .services-grid,
                .quick-actions {
                    grid-template-columns: 1fr;
                }
            }
        `
    ];

    constructor() {
        super();
        this.state = this.use((s) => ({
            servicesStatus: s.entities.services.statuses,
            servicesLoading: s.entities.services.loading,
            subscription: s.entities.billing.subscription,
            billingLoading: s.entities.billing.loading,
            user: s.user.data,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadData();
    }

    async _loadData() {
        const { servicesStatus, subscription } = this.state.value;
        
        if (Object.keys(servicesStatus).length === 0) {
            await this._loadServicesStatus();
        }
        
        if (!subscription) {
            await this._loadBilling();
        }
        
        const user = this.auth.user;
        if (user && !user.active_company_id) {
            this._showCreateCompanyModal();
        }
    }

    async _loadServicesStatus() {
        FrontendStore.setServicesLoading(true);
        const statuses = await this.services.get('servicesStatus').getStatus();
        FrontendStore.setServicesStatus(statuses);
    }

    async _loadBilling() {
        FrontendStore.setBillingLoading(true);
        const billingService = this.services.get('billing');
        const [subscription, usage] = await Promise.all([
            billingService.getSubscription(),
            billingService.getUsageStats(),
        ]);
        FrontendStore.setBillingData(subscription, usage);
    }

    _showCreateCompanyModal() {
        const modal = document.querySelector('company-modal');
        if (modal) {
            modal.open = true;
        }
    }

    render() {
        const { servicesLoading, billingLoading } = this.state.value;
        
        if (servicesLoading && billingLoading) {
            return html`
                <div class="loading-state">
                    <p>Загрузка...</p>
                </div>
            `;
        }

        const user = this.auth.user;

        return html`
            <page-header 
                title="Добро пожаловать" 
                subtitle="${user?.name ?? 'Пользователь'}"
            ></page-header>
            
            ${this._renderServices()}
            ${this._renderQuickActions()}
            ${this._renderStats()}
            
            <company-modal></company-modal>
        `;
    }

    _renderServices() {
        const services = [
            {
                id: 'flows',
                name: 'Flows',
                logo: '/static/core/assets/service_logos/agents_logo.svg',
                description: 'Конструктор flow: графы, skills и интеграции',
                path: '/flows',
            },
            {
                id: 'crm',
                name: 'CRM',
                logo: '/static/core/assets/service_logos/crm_logo.svg',
                description: 'Управление контактами и Knowledge Graph',
                path: '/crm',
            },
            {
                id: 'rag',
                name: 'RAG',
                logo: '/static/core/assets/service_logos/rag_logo.svg',
                description: 'Управление документами и поиск',
                path: '/rag',
            },
            {
                id: 'sync',
                name: 'Sync',
                logo: '/static/core/assets/service_logos/sync_logo.svg',
                description: 'Инженерный чат с Git-интеграцией',
                path: '/sync',
            },
        ];

        return html`
            <div class="services-section">
                <h2 class="section-title">Сервисы</h2>
                <div class="services-grid">
                    ${services.map((service) => this._renderServiceCard(service))}
                </div>
            </div>
        `;
    }

    _renderServiceCard(service) {
        return html`
            <div class="service-card" @click=${() => window.open(service.path, '_blank')}>
                <div class="service-header">
                    <span class="service-icon">
                        <img src="${service.logo}" alt="${service.name}">
                    </span>
                    <svg class="service-go-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 18 15 12 9 6"></polyline>
                    </svg>
                </div>
                <h3 class="service-name">${service.name}</h3>
                <p class="service-description">${service.description}</p>
            </div>
        `;
    }

    _renderQuickActions() {
        const actions = [
            {
                iconName: 'share',
                title: 'Пригласить участника',
                description: 'Добавить нового члена команды',
                action: () => FrontendStore.setCurrentView('team'),
            },
            {
                iconName: 'key',
                title: 'Создать API ключ',
                description: 'Новый ключ для интеграций',
                action: () => FrontendStore.setCurrentView('api-keys'),
            },
            {
                iconName: 'chat',
                title: 'Добавить Embed виджет',
                description: 'Создать новый чат-виджет',
                action: () => FrontendStore.setCurrentView('embed-configs'),
            },
            {
                iconName: 'clipboard',
                title: 'Пополнить баланс',
                description: 'Управление биллингом',
                action: () => FrontendStore.setCurrentView('billing'),
            },
        ];

        return html`
            <div class="quick-actions-section">
                <h2 class="section-title">Быстрые действия</h2>
                <div class="quick-actions">
                    ${actions.map((action) => html`
                        <div class="action-card" @click=${action.action}>
                            <span class="action-icon">
                                <platform-icon name="${action.iconName}" size="28"></platform-icon>
                            </span>
                            <div class="action-content">
                                <h3 class="action-title">${action.title}</h3>
                                <p class="action-description">${action.description}</p>
                            </div>
                        </div>
                    `)}
                </div>
            </div>
        `;
    }

    _renderStats() {
        const { subscription, servicesStatus } = this.state.value;
        
        const balance = subscription?.balance ?? 0;
        const spent = subscription?.current_month_spent ?? 0;
        const plan = subscription?.plan ?? 'FREE';
        
        const statuses = Object.values(servicesStatus);
        const healthyCount = statuses.filter((s) => s.status === 'healthy').length;
        const totalCount = statuses.length;
        
        return html`
            <div class="stats-section">
                <h2 class="section-title">Статистика использования</h2>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value">${balance.toFixed(0)} Р</div>
                        <div class="stat-label">Баланс</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${spent.toFixed(0)} Р</div>
                        <div class="stat-label">Потрачено в месяце</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${plan.toUpperCase()}</div>
                        <div class="stat-label">Тарифный план</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value">${healthyCount}/${totalCount}</div>
                        <div class="stat-label">Сервисы онлайн</div>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('dashboard-page', DashboardPage);

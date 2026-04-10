import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';
import { FrontendStore } from '../store/frontend.store.js';
import { openUrlSameWindowOrTab } from '@platform/lib/utils/native-app-shell.js';
import '@platform/lib/components/company-modal.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class DashboardPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }

            .top-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-4);
                margin-bottom: var(--space-8);
            }

            .stats-strip {
                display: flex;
                align-items: center;
                gap: 0;
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                backdrop-filter: blur(20px);
                flex-shrink: 0;
            }

            .stat-cell {
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: var(--space-3) var(--space-5);
                border-right: 1px solid var(--border-subtle);
            }

            .stat-cell:last-child {
                border-right: none;
            }

            .stat-value {
                font-size: var(--text-base);
                font-weight: var(--font-bold);
                color: var(--accent);
                white-space: nowrap;
                line-height: 1.2;
            }

            .stat-label {
                font-size: 10px;
                color: var(--text-tertiary);
                margin-top: 2px;
                white-space: nowrap;
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

            .page-loading {
                display: flex;
                align-items: center;
                justify-content: center;
                flex: 1;
                min-height: 200px;
            }

            .section-title {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-4) 0;
            }

            @media (max-width: 768px) {
                .top-row {
                    flex-direction: column;
                    align-items: stretch;
                }

                .stats-strip {
                    justify-content: center;
                }

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
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this._loadData();
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async _loadData() {
        await Promise.all([
            this._loadServicesStatus(),
            this._loadBilling(),
        ]);
        
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
        const td = (key, params) => this.i18n.t(key, params ?? {});

        if (servicesLoading && billingLoading) {
            return html`
                <div class="page-loading">
                    <glass-spinner size="lg"></glass-spinner>
                </div>
            `;
        }

        const user = this.auth.user;

        return html`
            <div class="top-row">
                <page-header 
                    title=${td('console_home.welcome_title')}
                    subtitle="${user?.name ?? td('console_home.user_fallback')}"
                ></page-header>
                ${this._renderStatsStrip()}
            </div>
            
            ${this._renderServices()}
            ${this._renderQuickActions()}
            
            <company-modal></company-modal>
        `;
    }

    _renderStatsStrip() {
        const { subscription } = this.state.value;
        const td = (key, params) => this.i18n.t(key, params ?? {});

        const balance = subscription?.balance ?? 0;
        const spent = subscription?.current_month_spent ?? 0;
        const plan = subscription?.plan ?? 'FREE';
        const cur = td('console_home.currency_rub');

        return html`
            <div class="stats-strip">
                <div class="stat-cell">
                    <div class="stat-value">${balance.toFixed(2)} ${cur}</div>
                    <div class="stat-label">${td('console_home.stat_balance')}</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-value">${spent.toFixed(2)} ${cur}</div>
                    <div class="stat-label">${td('console_home.stat_spent_month')}</div>
                </div>
                <div class="stat-cell">
                    <div class="stat-value">${plan.toUpperCase()}</div>
                    <div class="stat-label">${td('console_home.stat_plan')}</div>
                </div>
            </div>
        `;
    }

    _renderServices() {
        const tp = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.PLATFORM);
        const td = (key, params) => this.i18n.t(key, params ?? {});
        const services = [
            {
                id: 'sync',
                name: tp('apps.sync.name'),
                logo: '/static/core/assets/service_logos/sync_logo.svg',
                description: tp('apps.sync.description'),
            },
            {
                id: 'crm',
                name: tp('apps.crm.name'),
                logo: '/static/core/assets/service_logos/crm_logo.svg',
                description: tp('apps.crm.description'),
            },
            {
                id: 'flows',
                name: tp('apps.flows.name'),
                logo: '/static/core/assets/service_logos/agents_logo.svg',
                description: tp('apps.flows.description'),
            },
            {
                id: 'rag',
                name: tp('apps.rag.name'),
                logo: '/static/core/assets/service_logos/rag_logo.svg',
                description: tp('apps.rag.description'),
            },
            {
                id: 'documents',
                name: tp('apps.documents.name'),
                logo: '/static/core/assets/service_logos/documents_logo.svg',
                description: tp('apps.documents.description'),
            },
        ];

        return html`
            <div class="services-section">
                <h2 class="section-title">${td('console_home.services_title')}</h2>
                <div class="services-grid">
                    ${services.map((service) => this._renderServiceCard(service))}
                </div>
            </div>
        `;
    }

    _renderServiceCard(service) {
        return html`
            <div class="service-card" @click=${() => openUrlSameWindowOrTab(this._buildServiceUrl(service.id))}>
                <div class="service-header">
                    <span class="service-icon">
                        <img src="${service.logo}" alt="${service.name}">
                    </span>
                    <platform-icon class="service-go-icon" name="chevron-right" size="20"></platform-icon>
                </div>
                <h3 class="service-name">${service.name}</h3>
                <p class="service-description">${service.description}</p>
            </div>
        `;
    }

    _buildServiceUrl(serviceId) {
        const servicePath = `/${serviceId}`;
        if (!this._isLocalHost(window.location.hostname)) {
            return servicePath;
        }

        const servicePortById = {
            flows: '8001',
            frontend: '8002',
            crm: '8003',
            rag: '8004',
            sync: '8005',
            documents: '8002',
        };

        const targetPort = servicePortById[serviceId];
        if (!targetPort) {
            throw new Error(this.i18n.t('console_home.err_unknown_service', { id: serviceId }));
        }

        if (window.location.port === targetPort) {
            return servicePath;
        }

        return `${window.location.protocol}//${window.location.hostname}:${targetPort}${servicePath}`;
    }

    _isLocalHost(hostname) {
        return (
            hostname === 'localhost' ||
            hostname === '127.0.0.1' ||
            hostname.endsWith('.lvh.me')
        );
    }

    _renderQuickActions() {
        const td = (key, params) => this.i18n.t(key, params ?? {});
        const actions = [
            {
                iconName: 'share',
                title: td('console_home.quick_invite_title'),
                description: td('console_home.quick_invite_desc'),
                action: () => FrontendStore.setCurrentView('team'),
            },
            {
                iconName: 'key',
                title: td('console_home.quick_api_title'),
                description: td('console_home.quick_api_desc'),
                action: () => FrontendStore.setCurrentView('api-keys'),
            },
            {
                iconName: 'chat',
                title: td('console_home.quick_embed_title'),
                description: td('console_home.quick_embed_desc'),
                action: () => FrontendStore.setCurrentView('embed-configs'),
            },
            {
                iconName: 'settings',
                title: td('console_home.quick_settings_title'),
                description: td('console_home.quick_settings_desc'),
                action: () => FrontendStore.setCurrentView('settings'),
            },
        ];

        return html`
            <div class="quick-actions-section">
                <h2 class="section-title">${td('console_home.quick_actions_title')}</h2>
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
}

customElements.define('dashboard-page', DashboardPage);

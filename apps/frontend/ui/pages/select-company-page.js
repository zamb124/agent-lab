import { html, css } from 'lit';
import { PlatformElement } from '/static/core/lib/platform-element/index.js';
import { Services } from '@platform/services/index.js';
import '/static/core/lib/components/company-modal.js';

/**
 * Страница выбора компании после авторизации
 * Показывается только на главном домене без субдомена
 */
export class SelectCompanyPage extends PlatformElement {
    static properties = {
        companies: { type: Array },
        loading: { type: Boolean },
        error: { type: String },
        showCreateModal: { type: Boolean }
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-height: 100vh;
                background: var(--landing-background, #0F0F0F);
                padding: 40px 20px;
            }

            .container {
                max-width: 800px;
                margin: 0 auto;
            }

            .header {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                margin-bottom: 48px;
            }

            .title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 48px;
                font-weight: 600;
                color: var(--landing-secondary);
                margin: 0 0 16px 0;
            }

            .subtitle {
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                color: var(--landing-secondary);
                opacity: 0.7;
            }

            .companies-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 24px;
                margin-bottom: 32px;
            }

            .company-card {
                background: var(--glass-bg);
                border: 1px solid var(--glass-border);
                border-radius: 16px;
                padding: 32px;
                cursor: pointer;
                transition: all 0.3s ease;
                backdrop-filter: blur(20px);
            }

            .company-card:hover {
                transform: translateY(-4px);
                border-color: var(--landing-primary);
                box-shadow: 0 8px 24px rgba(87, 104, 254, 0.2);
            }

            .company-name {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 24px;
                font-weight: 600;
                color: var(--landing-secondary);
                margin: 0 0 8px 0;
            }

            .company-subdomain {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-primary);
                margin: 0 0 12px 0;
            }

            .company-role {
                display: inline-block;
                padding: 4px 12px;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 12px;
                font-size: 12px;
                color: var(--landing-secondary);
                opacity: 0.7;
            }

            .create-button {
                width: 100%;
                padding: 20px;
                background: var(--landing-primary);
                color: var(--landing-secondary);
                border: none;
                border-radius: 16px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
            }

            .create-button:hover {
                background: #6877ff;
                transform: translateY(-2px);
            }

            .loading {
                text-align: center;
                padding: 60px 20px;
                color: var(--landing-secondary);
                font-size: 18px;
            }

            .error {
                padding: 16px;
                background: rgba(255, 59, 48, 0.1);
                border: 1px solid rgba(255, 59, 48, 0.3);
                border-radius: 12px;
                color: #FF3B30;
                text-align: center;
                margin-bottom: 24px;
            }

            .empty-state {
                text-align: center;
                padding: 60px 20px;
            }

            .empty-icon {
                font-size: 64px;
                margin-bottom: 16px;
            }

            .empty-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 24px;
                color: var(--landing-secondary);
                margin: 0 0 8px 0;
            }

            .empty-text {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary);
                opacity: 0.7;
                margin: 0 0 32px 0;
            }
        `
    ];

    constructor() {
        super();
        this.companies = [];
        this.loading = true;
        this.error = '';
        this.showCreateModal = false;
    }

    async connectedCallback() {
        super.connectedCallback();
        await this.loadCompanies();
    }

    async loadCompanies() {
        this.loading = true;
        this.error = '';

        try {
            this.companies = await Services.companies.getMyCompanies();

            if (this.companies.length === 1) {
                this.handleCompanySelect(this.companies[0]);
                return;
            }

            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('action') === 'create' && this.companies.length === 0) {
                this.showCreateModal = true;
            }
        } catch (error) {
            console.error('Error loading companies:', error);
            this.error = error.message;
        } finally {
            this.loading = false;
        }
    }

    handleCompanySelect(company) {
        const env = window.location.hostname === 'localhost' ? 'development' : 'production';
        const url = this._buildSubdomainUrl(company.subdomain, '/dashboard', env);
        window.location.href = url;
    }

    _buildSubdomainUrl(subdomain, path = '/', env = 'production') {
        if (env === 'development') {
            return `http://${subdomain}.localhost:8002${path}`;
        }
        return `https://${subdomain}.humanitec.ru${path}`;
    }

    handleCreateCompany() {
        this.showCreateModal = true;
    }

    handleCompanyCreated(e) {
        const { redirect_url } = e.detail;
        if (redirect_url) {
            window.location.href = redirect_url;
        } else {
            this.loadCompanies();
        }
    }

    render() {
        if (this.loading) {
            return html`
                <div class="container">
                    <div class="loading">Загрузка компаний...</div>
                </div>
            `;
        }

        return html`
            <div class="container">
                <div class="header">
                    <h1 class="title">Выберите компанию</h1>
                    <p class="subtitle">Выберите компанию для работы или создайте новую</p>
                </div>

                ${this.error ? html`
                    <div class="error">${this.error}</div>
                ` : ''}

                ${this.companies.length > 0 ? html`
                    <div class="companies-grid">
                        ${this.companies.map(company => html`
                            <div 
                                class="company-card" 
                                @click=${() => this.handleCompanySelect(company)}
                            >
                                <h3 class="company-name">${company.name}</h3>
                                <p class="company-subdomain">${company.subdomain}.humanitec.ru</p>
                                <span class="company-role">${this._getRoleLabel(company.role)}</span>
                            </div>
                        `)}
                    </div>
                ` : html`
                    <div class="empty-state">
                        <div class="empty-icon">🏢</div>
                        <h2 class="empty-title">У вас пока нет компаний</h2>
                        <p class="empty-text">Создайте свою первую компанию для начала работы</p>
                    </div>
                `}

                <button 
                    class="create-button" 
                    @click=${this.handleCreateCompany}
                >
                    + Создать новую компанию
                </button>

                <company-modal 
                    ?open=${this.showCreateModal}
                    @company-created=${this.handleCompanyCreated}
                    @click=${(e) => {
                        if (e.target.tagName === 'COMPANY-MODAL') {
                            this.showCreateModal = false;
                        }
                    }}
                ></company-modal>
            </div>
        `;
    }

    _getRoleLabel(role) {
        const labels = {
            'owner': 'Владелец',
            'admin': 'Администратор',
            'member': 'Участник'
        };
        return labels[role] || role;
    }
}

customElements.define('select-company-page', SelectCompanyPage);


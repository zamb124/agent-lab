/**
 * Select company page — после логина пользователь с несколькими компаниями
 * выбирает активную через core companies effect.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import { buildCompanySubdomainUrl } from '@platform/lib/utils/tenant-url.js';
import '@platform/lib/components/platform-icon.js';

export class SelectCompanyPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: 100vh;
                padding: var(--space-6);
                background: var(--bg-gradient);
            }
            .card {
                width: 100%;
                max-width: 960px;
                padding: var(--space-8) var(--space-7);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-2xl);
                box-shadow: 0 24px 64px rgba(0, 0, 0, 0.35);
            }
            :host-context([data-theme="light"]) .card {
                box-shadow: 0 16px 48px rgba(15, 23, 42, 0.12);
            }
            h1 {
                color: var(--text-primary);
                margin: 0 0 var(--space-6);
                text-align: center;
                font-size: var(--text-2xl, 1.5rem);
                font-weight: 600;
                letter-spacing: -0.02em;
            }
            .empty {
                color: var(--text-secondary);
                text-align: center;
                margin: 0;
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
                gap: var(--space-4);
                width: 100%;
            }
            @media (min-width: 600px) {
                .grid {
                    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                    gap: var(--space-5);
                }
            }
            .company-card {
                position: relative;
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                width: 100%;
                min-height: 0;
                aspect-ratio: 1 / 1;
                padding: var(--space-5) var(--space-4);
                margin: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-xl);
                background: var(--glass-bg-subtle);
                color: var(--text-primary);
                cursor: pointer;
                text-align: center;
                font: inherit;
                transition:
                    border-color 0.15s ease,
                    background 0.15s ease,
                    transform 0.12s ease;
            }
            .company-card:hover {
                background: var(--glass-solid-strong);
                border-color: var(--glass-border-medium);
                transform: translateY(-2px);
            }
            .company-card:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 3px;
            }
            .company-card.active {
                border-color: var(--accent);
                background: var(--glass-solid-strong);
                box-shadow: 0 0 0 1px var(--accent);
            }
            .company-card-icon-wrap {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 4.5rem;
                height: 4.5rem;
                border-radius: var(--radius-lg);
                background: var(--glass-tint-medium);
                color: var(--accent);
            }
            .company-card.active .company-card-icon-wrap {
                background: color-mix(in srgb, var(--accent) 18%, transparent);
            }
            .company-card-name {
                font-size: var(--text-base, 1rem);
                font-weight: 500;
                line-height: 1.35;
                word-break: break-word;
                max-width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this._companiesSel = this.select((s) => s.companies.list);
        this._authSel = this.select((s) => s.auth.user);
        this._loaded = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(CoreEvents.AUTH_COMPANY_SWITCHED, (event) => {
            const p = event.payload;
            if (!p || typeof p.company_id !== 'string' || p.company_id.length === 0) {
                throw new Error('AUTH_COMPANY_SWITCHED: company_id required in payload');
            }
            const list = this._companiesSel.value;
            const company = list.find((c) => c.company_id === p.company_id);
            if (!company) {
                throw new Error('select-company: company not found in list');
            }
            if (typeof company.subdomain !== 'string' || company.subdomain.length === 0) {
                this.toast('company.subdomain_missing', { type: 'error' });
                return;
            }
            const target = buildCompanySubdomainUrl(company.subdomain, '/dashboard');
            if (target === window.location.href) {
                return;
            }
            window.location.replace(target);
        });
    }

    updated() {
        if (!this._loaded) {
            this._loaded = true;
            this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null);
        }
    }

    _select(companyId) {
        this.switchCompany(companyId);
    }

    render() {
        const companies = this._companiesSel.value;
        const user = this._authSel.value;
        let currentId = '';
        if (user) {
            if (typeof user.company_id === 'string' && user.company_id.length > 0) {
                currentId = user.company_id;
            } else if (
                user.raw &&
                typeof user.raw.company_id === 'string' &&
                user.raw.company_id.length > 0
            ) {
                currentId = user.raw.company_id;
            }
        }
        return html`
            <div class="card">
                <h1>${this.t('select_company.title')}</h1>
                ${companies.length === 0
                    ? html`<p class="empty">${this.t('select_company.empty_text')}</p>`
                    : html`
                        <div class="grid" role="list">
                            ${companies.map(
                                (c) => html`
                                    <button
                                        type="button"
                                        class="company-card ${c.company_id === currentId ? 'active' : ''}"
                                        role="listitem"
                                        @click=${() => this._select(c.company_id)}
                                    >
                                        <span class="company-card-icon-wrap" aria-hidden="true">
                                            <platform-icon name="building-one" size="40"></platform-icon>
                                        </span>
                                        <span class="company-card-name">${c.name}</span>
                                    </button>
                                `,
                            )}
                        </div>
                    `}
            </div>
        `;
    }
}

customElements.define('select-company-page', SelectCompanyPage);

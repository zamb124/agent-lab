/**
 * Страница выбора компании — после логина пользователь с несколькими компаниями
 * выбирает активную через core companies effect.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import '@platform/lib/components/platform-icon.js';

function _userIsOwnerOfCompany(companyRecord) {
    if (!companyRecord || !Array.isArray(companyRecord.role)) {
        return false;
    }
    return companyRecord.role.includes('owner');
}

export class SelectCompanyPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host {
                box-sizing: border-box;
                display: flex;
                flex-direction: column;
                align-items: center;
                min-height: 100vh;
                padding: max(var(--space-10), var(--platform-safe-top)) var(--space-6) var(--space-8);
                background: var(--bg-gradient);
            }
            .page-title {
                flex: 0 0 auto;
                margin: 0 0 var(--space-6);
                width: 100%;
                max-width: 40rem;
                text-align: center;
                color: var(--text-primary);
                font-size: var(--text-2xl, 1.5rem);
                font-weight: 600;
                letter-spacing: -0.02em;
            }
            .empty {
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                text-align: center;
                margin: 0;
                max-width: 28rem;
                gap: var(--space-5);
            }
            .empty-text {
                margin: 0;
            }
            .empty-actions {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .grid-main {
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-6);
                width: 100%;
                min-height: 0;
            }
            .grid {
                display: flex;
                flex-wrap: wrap;
                justify-content: center;
                align-content: center;
                gap: var(--space-5);
            }
            .company-card {
                position: relative;
                box-sizing: border-box;
                display: flex;
                flex: 0 0 auto;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-4);
                width: 13rem;
                height: 13rem;
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
            @media (min-width: 480px) {
                .company-card {
                    width: 14.5rem;
                    height: 14.5rem;
                }
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
            .create-company-secondary {
                flex: 0 0 auto;
                display: flex;
                justify-content: center;
                width: 100%;
                max-width: 40rem;
            }
        `,
    ];

    constructor() {
        super();
        this._companiesSel = this.select((s) => s.companies.list);
        this._authSel = this.select((s) => s.auth.user);
        this._loaded = false;
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

    _createCompany() {
        this.openModal('platform.company_create', null);
    }

    _resolveCurrentCompanyId(user) {
        if (!user) return '';
        if (typeof user.company_id === 'string' && user.company_id.length > 0) {
            return user.company_id;
        }
        if (
            user.raw &&
            typeof user.raw.company_id === 'string' &&
            user.raw.company_id.length > 0
        ) {
            return user.raw.company_id;
        }
        return '';
    }

    render() {
        const companies = this._companiesSel.value;
        const user = this._authSel.value;
        const currentId = this._resolveCurrentCompanyId(user);
        const activeRecord = currentId ? companies.find((c) => c.company_id === currentId) : undefined;
        const canCreateAnother = companies.length > 0 && _userIsOwnerOfCompany(activeRecord);

        const cardsBlock = html`
                    <div class="grid-main">
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
                        ${canCreateAnother
                            ? html`
                                <div class="create-company-secondary">
                                    <button type="button" class="btn btn-secondary" @click=${this._createCompany}>
                                        ${this.t('select_company.create_action')}
                                    </button>
                                </div>
                            `
                            : ''}
                    </div>
                `;

        return html`
            <h1 class="page-title">${this.t('select_company.title')}</h1>
            ${companies.length === 0
                ? html`
                    <div class="empty">
                        <p class="empty-text">${this.t('select_company.empty_text')}</p>
                        <div class="empty-actions">
                            <button type="button" class="btn btn-primary" @click=${this._createCompany}>
                                ${this.t('select_company.create_action')}
                            </button>
                        </div>
                    </div>
                `
                : cardsBlock}
        `;
    }
}

customElements.define('select-company-page', SelectCompanyPage);

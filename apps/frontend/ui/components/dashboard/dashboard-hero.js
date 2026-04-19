/**
 * dashboard-hero — крупный приветственный блок страницы /dashboard.
 *
 * Читает текущего пользователя и активную компанию из auth/companies slice.
 * Рисует градиентный заголовок, лид-подзаголовок и чип активной компании.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class DashboardHero extends PlatformElement {
    static i18nNamespace = 'frontend';

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .hero {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .eyebrow {
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.18em;
                color: var(--text-tertiary);
            }
            h1 {
                margin: 0;
                font-size: clamp(var(--text-3xl), 4vw, var(--text-5xl));
                font-weight: var(--font-bold);
                line-height: 1.1;
                background: linear-gradient(135deg, var(--text-primary) 10%, var(--accent) 85%);
                -webkit-background-clip: text;
                background-clip: text;
                color: transparent;
            }
            .subtitle {
                font-size: var(--text-lg);
                color: var(--text-secondary);
                max-width: 640px;
            }
            .badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                margin-top: var(--space-2);
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-full);
                background: var(--glass-solid-soft);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                align-self: flex-start;
            }
            .badge .dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--success);
                box-shadow: 0 0 12px var(--success);
            }
        `,
    ];

    constructor() {
        super();
        this._auth = this.select((s) => ({
            user: s.auth.user,
            activeCompanyId: s.auth.activeCompanyId,
        }));
        this._companies = this.select((s) => s.companies.list);
    }

    _userName(user) {
        if (user && typeof user.name === 'string' && user.name.trim().length > 0) {
            return user.name.trim();
        }
        if (user && user.raw && typeof user.raw.name === 'string' && user.raw.name.trim().length > 0) {
            return user.raw.name.trim();
        }
        return this.t('console_home.user_fallback');
    }

    _activeCompanyName(activeCompanyId, list) {
        if (!activeCompanyId || !Array.isArray(list)) return null;
        const found = list.find((c) => c.company_id === activeCompanyId);
        return found ? found.name : null;
    }

    render() {
        const auth = this._auth.value;
        const companies = this._companies.value;
        const name = this._userName(auth.user);
        const companyName = this._activeCompanyName(auth.activeCompanyId, companies);
        return html`
            <div class="hero">
                <div class="eyebrow">${this.t('console_home.welcome_title')}</div>
                <h1>${name}</h1>
                <div class="subtitle">${this.t('console_home.welcome_subtitle')}</div>
                ${companyName === null ? '' : html`
                    <div class="badge">
                        <span class="dot"></span>
                        <span>${this.t('console_home.welcome_company_badge', { name: companyName })}</span>
                    </div>
                `}
            </div>
        `;
    }
}

customElements.define('dashboard-hero', DashboardHero);

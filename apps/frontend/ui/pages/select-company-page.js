/**
 * Select company page — после логина пользователь с несколькими компаниями
 * выбирает активную через core companies effect.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import '@platform/lib/components/platform-icon.js';

export class SelectCompanyPage extends PlatformPage {
    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex; align-items: center; justify-content: center;
                min-height: 100vh; padding: var(--space-6);
                background: var(--bg-gradient);
            }
            .card {
                max-width: 520px; width: 100%; padding: var(--space-8);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-2xl);
            }
            h1 { color: var(--text-primary); margin-bottom: var(--space-4); text-align: center; }
            .item {
                display: flex; align-items: center; gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                margin-bottom: var(--space-2);
                background: transparent; border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                cursor: pointer; color: var(--text-primary); width: 100%; text-align: left;
            }
            .item:hover { background: var(--glass-solid-strong); border-color: var(--accent); }
            .item.active { border-color: var(--accent); color: var(--accent); }
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
        this.useEvent(CoreEvents.AUTH_COMPANY_SWITCHED, () => {
            this.navigate('dashboard');
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
        const currentId = user && (user.company_id || (user.raw && user.raw.company_id));
        return html`
            <div class="card">
                <h1>${this.t('select_company.title')}</h1>
                ${companies.length === 0
                    ? html`<p>${this.t('select_company.empty_text')}</p>`
                    : companies.map((c) => html`
                        <button class="item ${c.company_id === currentId ? 'active' : ''}" @click=${() => this._select(c.company_id)}>
                            <platform-icon name="building-one" size="18"></platform-icon>
                            <span>${c.name}</span>
                        </button>
                    `)
                }
            </div>
        `;
    }
}

customElements.define('select-company-page', SelectCompanyPage);

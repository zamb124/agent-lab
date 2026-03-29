/**
 * Landing Page - Главная страница лендинга Humanitec
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/auth-modal.js';

export class LandingPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                background: var(--landing-bg, #0F0F0F);
                color: var(--landing-text, #FFFFFF);
            }
            
            .landing-container {
                width: 100%;
                overflow-x: hidden;
            }
            
            section {
                position: relative;
            }
        `
    ];

    static properties = {
        currentSection: { type: String }
    };

    constructor() {
        super();
        this.currentSection = 'hero';
    }

    connectedCallback() {
        super.connectedCallback();
        this._setupSmoothScroll();
        this.addEventListener('open-auth-modal', this._handleOpenAuthModal);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._removeSmoothScroll();
        this.removeEventListener('open-auth-modal', this._handleOpenAuthModal);
    }

    _setupSmoothScroll() {
        setTimeout(() => {
            const links = this.shadowRoot?.querySelectorAll('a[href^="#"]');
            links?.forEach(anchor => {
                anchor.addEventListener('click', this._handleSmoothScroll);
            });
        }, 100);
    }

    _removeSmoothScroll() {
        const links = this.shadowRoot?.querySelectorAll('a[href^="#"]');
        links?.forEach(anchor => {
            anchor.removeEventListener('click', this._handleSmoothScroll);
        });
    }

    _handleSmoothScroll = (e) => {
        e.preventDefault();
        const targetId = e.currentTarget.getAttribute('href').slice(1);
        const targetElement = this.shadowRoot?.getElementById(targetId);
        
        if (targetElement) {
            targetElement.scrollIntoView({ 
                behavior: 'smooth',
                block: 'start'
            });
        }
    };

    _handleOpenAuthModal = () => {
        console.log('🟢 Open auth modal event received');
        const authModal = this.shadowRoot?.querySelector('auth-modal');
        if (authModal) {
            console.log('✅ Auth modal found, opening...');
            authModal.open = true;
        } else {
            console.error('❌ Auth modal not found');
        }
    };

    render() {
        return html`
            <div class="landing-container">
                <landing-header></landing-header>
                
                <section id="hero">
                    <landing-hero></landing-hero>
                </section>
                
                <section id="about">
                    <landing-about></landing-about>
                </section>
                
                <section id="abilities">
                    <landing-abilities></landing-abilities>
                </section>
                
                <section id="advantages">
                    <landing-advantages></landing-advantages>
                </section>
                
                <section id="plans">
                    <landing-plans></landing-plans>
                </section>
                
                <section id="reviews">
                    <landing-reviews></landing-reviews>
                </section>
                
                <section id="faq">
                    <landing-faq></landing-faq>
                </section>
                
                <section id="cta">
                    <landing-cta></landing-cta>
                </section>
                
                <landing-footer></landing-footer>
            </div>
            
            <auth-modal></auth-modal>
        `;
    }
}

customElements.define('landing-page', LandingPage);

export class LegalPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-height: 100vh;
                background: var(--landing-bg, #0F0F0F);
                color: var(--landing-text, #FFFFFF);
                padding: 32px 16px 48px;
            }

            .container {
                max-width: 980px;
                margin: 0 auto;
                display: flex;
                flex-direction: column;
                gap: 24px;
            }

            .topbar {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 16px;
                flex-wrap: wrap;
            }

            .brand {
                color: var(--landing-secondary, #E8E8E8);
                text-decoration: none;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 24px;
                font-weight: 600;
            }

            .actions {
                display: flex;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;
            }

            .lang-btn {
                border: 1px solid rgba(255, 255, 255, 0.2);
                background: transparent;
                color: var(--landing-secondary, #E8E8E8);
                border-radius: 16px;
                padding: 6px 12px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                cursor: pointer;
            }

            .lang-btn.active {
                background: rgba(87, 104, 254, 0.2);
                border-color: rgba(87, 104, 254, 0.8);
            }

            .switch-doc {
                color: var(--landing-secondary, #E8E8E8);
                text-decoration: underline;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
            }

            .card {
                border: 1px solid rgba(255, 255, 255, 0.14);
                border-radius: 16px;
                background: rgba(255, 255, 255, 0.03);
                padding: 24px 18px;
                display: flex;
                flex-direction: column;
                gap: 22px;
            }

            h1 {
                margin: 0;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-weight: 600;
                font-size: 34px;
                line-height: 1.1;
            }

            .updated {
                margin: 0;
                color: rgba(232, 232, 232, 0.8);
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
            }

            section {
                display: flex;
                flex-direction: column;
                gap: 10px;
            }

            h2 {
                margin: 0;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 24px;
                font-weight: 600;
            }

            p {
                margin: 0;
                font-family: 'Fira Sans', sans-serif;
                line-height: 1.6;
                color: rgba(232, 232, 232, 0.9);
                white-space: pre-wrap;
            }

            ul {
                margin: 0;
                padding-left: 20px;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }

            li {
                font-family: 'Fira Sans', sans-serif;
                line-height: 1.6;
                color: rgba(232, 232, 232, 0.9);
            }

            .loading {
                font-family: 'Fira Sans', sans-serif;
                color: rgba(232, 232, 232, 0.85);
            }

            @media (min-width: 768px) {
                :host {
                    padding: 40px 28px 64px;
                }

                .card {
                    padding: 32px 28px;
                }
            }
        `,
    ];

    static properties = {
        docType: { type: String },
        locale: { type: String },
        translations: { type: Object },
        legal: { type: Object },
        loading: { type: Boolean },
    };

    constructor() {
        super();
        this.docType = 'policy';
        this.locale = 'en';
        this.translations = null;
        this.legal = null;
        this.loading = true;
    }

    connectedCallback() {
        super.connectedCallback();
        this._loadPageData();
    }

    updated(changedProperties) {
        if (changedProperties.has('docType')) {
            this._loadPageData();
        }
    }

    _resolveLocaleFromQuery() {
        const lang = new URLSearchParams(window.location.search).get('lang');
        return lang === 'ru' ? 'ru' : 'en';
    }

    _buildUrlWithLang(pathname, lang) {
        const params = new URLSearchParams(window.location.search);
        if (lang === 'ru') {
            params.set('lang', 'ru');
        } else {
            params.delete('lang');
        }
        const query = params.toString();
        return query ? `${pathname}?${query}` : pathname;
    }

    _interpolate(text) {
        if (typeof text !== 'string') {
            return text;
        }
        const legal = this.legal ?? {};
        return text.replace(/\{\{(\w+)\}\}/g, (_, key) => {
            const value = legal[key];
            if (value === undefined || value === null || value === '') {
                return `[${key}]`;
            }
            return String(value);
        });
    }

    async _loadPageData() {
        this.loading = true;
        this.locale = this._resolveLocaleFromQuery();

        const [i18nResponse, legalResponse] = await Promise.all([
            fetch(`/api/i18n/${this.locale}`),
            fetch('/api/public/legal'),
        ]);

        if (!i18nResponse.ok) {
            throw new Error(`Failed to load translations for locale ${this.locale}`);
        }
        if (!legalResponse.ok) {
            throw new Error('Failed to load legal config');
        }

        const i18n = await i18nResponse.json();
        const legal = await legalResponse.json();

        const namespace = this.docType === 'terms' ? 'terms' : 'privacy';
        const translations = i18n[namespace];
        if (!translations) {
            throw new Error(`Missing ${namespace} namespace for locale ${this.locale}`);
        }

        this.translations = translations;
        this.legal = legal;
        this.loading = false;
    }

    _renderSectionBody(value) {
        if (Array.isArray(value)) {
            return html`
                <ul>
                    ${value.map((item) => html`<li>${this._interpolate(item)}</li>`)}
                </ul>
            `;
        }
        if (typeof value === 'string') {
            return html`<p>${this._interpolate(value)}</p>`;
        }
        return null;
    }

    _sortedSections() {
        if (!this.translations) {
            return [];
        }
        return Object.entries(this.translations)
            .filter(([key]) => key.startsWith('section_'))
            .sort(([a], [b]) => {
                const numA = Number(a.replace('section_', ''));
                const numB = Number(b.replace('section_', ''));
                return numA - numB;
            });
    }

    render() {
        const isTerms = this.docType === 'terms';
        const oppositePath = isTerms ? '/policy' : '/terms';
        const oppositeLabel = isTerms ? 'Privacy Policy' : 'Terms of Service';
        const enUrl = this._buildUrlWithLang(window.location.pathname, 'en');
        const ruUrl = this._buildUrlWithLang(window.location.pathname, 'ru');
        const oppositeUrl = this._buildUrlWithLang(oppositePath, this.locale);

        return html`
            <div class="container">
                <div class="topbar">
                    <a class="brand" href="/">Humanitec</a>
                    <div class="actions">
                        <button
                            class="lang-btn ${this.locale === 'en' ? 'active' : ''}"
                            @click=${() => { window.location.href = enUrl; }}
                        >
                            EN
                        </button>
                        <button
                            class="lang-btn ${this.locale === 'ru' ? 'active' : ''}"
                            @click=${() => { window.location.href = ruUrl; }}
                        >
                            RU
                        </button>
                        <a class="switch-doc" href=${oppositeUrl}>${oppositeLabel}</a>
                    </div>
                </div>

                <div class="card">
                    ${this.loading || !this.translations
                        ? html`<p class="loading">Loading...</p>`
                        : html`
                            <h1>${this.translations.title}</h1>
                            <p class="updated">
                                ${this.translations.updated}: ${this._interpolate(this.translations.updated_at)}
                            </p>
                            ${this._sortedSections().map(([_, section]) => html`
                                <section>
                                    <h2>${section.title}</h2>
                                    ${Object.entries(section)
                                        .filter(([field]) => field !== 'title')
                                        .map(([_, value]) => this._renderSectionBody(value))}
                                </section>
                            `)}
                        `}
                </div>
            </div>
        `;
    }
}

customElements.define('legal-page', LegalPage);


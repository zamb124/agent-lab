/**
 * Подвал лендинга — подвал лендинга
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingFooter extends PlatformElement {
    static i18nNamespace = 'landing';

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 60px 20px;
                background: var(--landing-footer-bg, linear-gradient(180deg, #0F0F0F 0%, #0a0a0a 100%));
                border-top: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.1));
            }
            
            .footer-container {
                max-width: 1440px;
                margin: 0 auto;
            }
            
            .footer-content {
                display: flex;
                flex-direction: column;
                gap: 40px;
                margin-bottom: 40px;
            }
            
            .footer-left {
                flex: 1;
                min-width: 0;
            }
            
            .footer-email {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 28px;
                font-weight: 700;
                color: var(--landing-secondary);
                margin: 0 0 24px 0;
                text-decoration: none;
                display: inline-block;
                transition: color 0.3s;
            }
            
            .footer-email:hover {
                color: var(--accent);
            }
            
            .footer-logo {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(2rem, 12vw, 6.25rem);
                font-weight: 500;
                line-height: 1;
                color: var(--accent);
                margin: 0;
                text-transform: capitalize;
                white-space: nowrap;
            }

            .footer-requisites {
                margin-top: 28px;
                max-width: 520px;
            }

            .footer-requisites h3 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 18px;
                margin: 0 0 12px;
                color: var(--landing-secondary, #e8e8e8);
            }

            .footer-requisites p {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                line-height: 1.55;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.72));
                margin: 0 0 8px;
            }
            
            .footer-right {
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            
            .footer-link {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 18px;
                color: var(--landing-secondary);
                text-decoration: underline;
                transition: color 0.3s;
            }
            
            .footer-link:hover {
                color: var(--accent);
            }
            
            .footer-bottom {
                padding-top: 32px;
                border-top: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.1));
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            
            .footer-copy {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 16px;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.6));
                margin: 0;
            }
            
            .footer-legal {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            
            .footer-legal-link {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 14px;
                color: var(--landing-secondary);
                text-decoration: underline;
                transition: color 0.3s;
            }
            
            .footer-legal-link:hover {
                color: var(--accent);
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 80px 40px;
                }
                
                .footer-content {
                    flex-direction: row;
                    justify-content: space-between;
                    gap: 60px;
                    margin-bottom: 60px;
                }
                
                .footer-email {
                    font-size: 36px;
                }
                
                .footer-logo {
                    font-size: 150px;
                }
                
                .footer-link {
                    font-size: 20px;
                }
                
                .footer-bottom {
                    flex-direction: row;
                    justify-content: space-between;
                    align-items: center;
                }
                
                .footer-copy {
                    font-size: 18px;
                }
                
                .footer-legal {
                    flex-direction: row;
                    gap: 24px;
                }
                
                .footer-legal-link {
                    font-size: 16px;
                }
            }
            
            @media (min-width: 1440px) {
                :host {
                    padding: 100px 80px;
                }
                
                .footer-email {
                    font-size: 50px;
                }
                
                .footer-logo {
                    font-size: 276px;
                }
                
                .footer-link {
                    font-size: 30px;
                }
                
                .footer-copy {
                    font-size: 30px;
                }
                
                .footer-legal-link {
                    font-size: 30px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._bundle = this.useOp('frontend/public_site_bundle');
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    connectedCallback() {
        super.connectedCallback();
        void this._bundle.run(null);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
    }

    _legalUrl(pathname) {
        const lang = this._localeSel.value;
        if (lang === 'ru') {
            return `${pathname}?lang=ru`;
        }
        if (lang === 'en') {
            return `${pathname}?lang=en`;
        }
        throw new Error('landing-footer: i18n.locale must be ru or en');
    }

    _companyName(legal) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return legal.company_name_ru;
        if (locale === 'en') return legal.company_name_en;
        throw new Error('landing-footer: i18n.locale must be ru or en');
    }

    _legalAddress(legal) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return legal.legal_address_ru;
        if (locale === 'en') return legal.legal_address_en;
        throw new Error('landing-footer: i18n.locale must be ru or en');
    }

    render() {
        const bundleRes = this._bundle.lastResult;
        let legal = null;
        let telegramUrl = '';
        if (bundleRes && typeof bundleRes === 'object') {
            if (!bundleRes.legal || typeof bundleRes.legal !== 'object') {
                throw new Error('landing-footer: legal missing');
            }
            legal = bundleRes.legal;
            const marketing = bundleRes.marketing;
            if (!marketing || typeof marketing !== 'object') {
                throw new Error('landing-footer: marketing missing');
            }
            const rawUrl = marketing.telegram_community_url;
            if (typeof rawUrl === 'string' && rawUrl !== '') {
                telegramUrl = rawUrl;
            }
        }

        const t = (key, params) => this.t(key, params);
        const year = new Date().getFullYear();
        const supportMail = 'helpme@humanitec.ru';

        return html`
            <footer class="footer-container">
                <div class="footer-content">
                    <div class="footer-left">
                        <a href="mailto:${supportMail}" class="footer-email">
                            ${supportMail}
                        </a>
                        <h2 class="footer-logo">Humanitec</h2>
                        ${legal
                            ? html`
                                  <div class="footer-requisites">
                                      <h3>${t('footer.legal_heading')}</h3>
                                      <p>${this._companyName(legal)}</p>
                                      <p>${t('footer.inn_label')} ${legal.inn}</p>
                                      <p>${t('footer.ogrn_label')} ${legal.ogrn}</p>
                                      <p>${this._legalAddress(legal)}</p>
                                  </div>
                              `
                            : null}
                    </div>
                    
                    <div class="footer-right">
                        <a href="/documentation" class="footer-link">${t('footer.docs')}</a>
                        ${telegramUrl !== ''
                            ? html`<a href=${telegramUrl} class="footer-link" target="_blank" rel="noopener noreferrer"
                                  >${t('footer.telegram')}</a
                              >`
                            : null}
                    </div>
                </div>
                
                <div class="footer-bottom">
                    <p class="footer-copy">${t('footer.copyright', { year })}</p>
                    
                    <div class="footer-legal">
                        <a href=${this._legalUrl('/policy')} class="footer-legal-link">
                            ${t('footer.privacy')}
                        </a>
                        <a href=${this._legalUrl('/terms')} class="footer-legal-link">
                            ${t('footer.terms')}
                        </a>
                    </div>
                </div>
            </footer>
        `;
    }
}

customElements.define('landing-footer', LandingFooter);

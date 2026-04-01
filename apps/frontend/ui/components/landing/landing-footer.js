/**
 * Landing Footer - Подвал лендинга
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';

export class LandingFooter extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 60px 20px;
                background: linear-gradient(180deg, #0F0F0F 0%, #0a0a0a 100%);
                border-top: 1px solid rgba(255, 255, 255, 0.1);
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
                color: var(--landing-primary);
            }
            
            .footer-logo {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 100px;
                font-weight: 500;
                line-height: 1;
                color: var(--landing-primary);
                margin: 0;
                text-transform: capitalize;
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
                color: var(--landing-primary);
            }
            
            .footer-bottom {
                padding-top: 32px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            
            .footer-copy {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 16px;
                color: rgba(232, 232, 232, 0.6);
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
                color: var(--landing-primary);
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
        `
    ];

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    _legalUrl(pathname) {
        const params = new URLSearchParams(window.location.search);
        const lang = params.get('lang');
        if (lang === 'ru') {
            return `${pathname}?lang=ru`;
        }
        return pathname;
    }

    render() {
        const t = (key, params) => this.i18n.t(key, params ?? {}, I18nNs.LANDING);
        const year = new Date().getFullYear();
        return html`
            <footer class="footer-container">
                <div class="footer-content">
                    <div class="footer-left">
                        <a href="mailto:helpme@humanitec.ru" class="footer-email">
                            helpme@humanitec.ru
                        </a>
                        <h2 class="footer-logo">Humanitec</h2>
                    </div>
                    
                    <div class="footer-right">
                        <a href="#" class="footer-link">${t('footer.docs')}</a>
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


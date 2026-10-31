/**
 * Подвал лендинга — подвал лендинга
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { getPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { ControllerFor, OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export class LandingFooter extends PlatformElement {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 60px 20px;
                background: linear-gradient(180deg, var(--marketing-page-bg) 0%, var(--bg-primary) 100%);
                border-top: 1px solid var(--glass-border-medium);
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
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 28px;
                font-weight: 700;
                color: var(--text-secondary);
                margin: 0 0 24px 0;
                text-decoration: none;
                display: inline-block;
                transition: color 0.3s;
            }
            
            .footer-email:hover {
                color: var(--accent);
            }
            
            .footer-logo {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
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
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 18px;
                margin: 0 0 12px;
                color: var(--text-secondary);
            }

            .footer-requisites p {
                font-family: var(--font-sans);
                font-size: 14px;
                line-height: 1.55;
                color: var(--text-secondary);
                margin: 0 0 8px;
            }
            
            .footer-right {
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            
            .footer-link {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 18px;
                color: var(--text-secondary);
                text-decoration: underline;
                transition: color 0.3s;
            }
            
            .footer-link:hover {
                color: var(--accent);
            }
            
            .footer-bottom {
                padding-top: 32px;
                border-top: 1px solid var(--glass-border-medium);
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            
            .footer-copy {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 16px;
                color: var(--text-secondary);
                margin: 0;
            }
            
            .footer-legal {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }
            
            .footer-legal-link {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 14px;
                color: var(--text-secondary);
                text-decoration: underline;
                transition: color 0.3s;
            }

            button.footer-legal-link {
                display: inline;
                margin: 0;
                padding: 0;
                border: 0;
                background: transparent;
                cursor: pointer;
                text-align: left;
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
        this._cookieConsent = this.useSlice('frontend/cookie_consent');
        this._localeSel = this.select((s: Record<string, unknown>) => s.i18n.locale);
    }
    private _bundle: OpController;
    private _cookieConsent: ControllerFor<'frontend/cookie_consent'>;
    private _localeSel: SelectController<any>;


    override connectedCallback(): void {
        super.connectedCallback();
        void this._bundle.run(null);
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
    }

    _openCookieSettings() {
        this._cookieConsent.openSettings(null);
    }

    _legalUrl(pathname: string) {
        const lang = this._localeSel.value;
        if (lang === 'ru') {
            return `${pathname}?lang=ru`;
        }
        if (lang === 'en') {
            return `${pathname}?lang=en`;
        }
        throw new Error('landing-footer: i18n.locale must be ru or en');
    }

    _requireLegalString(legal: Record<string, unknown>, key: string) {
        const value = legal[key];
        if (typeof value !== 'string' || value === '') {
            throw new Error(`landing-footer: legal.${key} required`);
        }
        return value;
    }

    _companyName(legal: Record<string, unknown>) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return this._requireLegalString(legal, 'company_name_ru');
        if (locale === 'en') return this._requireLegalString(legal, 'company_name_en');
        throw new Error('landing-footer: i18n.locale must be ru or en');
    }

    _legalAddress(legal: Record<string, unknown>) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return this._requireLegalString(legal, 'legal_address_ru');
        if (locale === 'en') return this._requireLegalString(legal, 'legal_address_en');
        throw new Error('landing-footer: i18n.locale must be ru or en');
    }

    _bankName(legal: Record<string, unknown>) {
        const locale = this._localeSel.value;
        if (locale === 'ru') return this._requireLegalString(legal, 'bank_name_ru');
        if (locale === 'en') return this._requireLegalString(legal, 'bank_name_en');
        throw new Error('landing-footer: i18n.locale must be ru or en');
    }

    override render(): TemplateResult {
        const bundleRes = this._bundle.lastResult;
        let legal: Record<string, unknown> | null = null;
        let telegramUrl = '';
        if (isPlainRecord(bundleRes)) {
            const legalValue = bundleRes.legal;
            if (!isPlainRecord(legalValue)) {
                throw new Error('landing-footer: legal missing');
            }
            legal = legalValue;
            const marketing = bundleRes.marketing;
            if (!isPlainRecord(marketing)) {
                throw new Error('landing-footer: marketing missing');
            }
            const rawUrl = marketing.telegram_community_url;
            if (typeof rawUrl === 'string' && rawUrl !== '') {
                telegramUrl = rawUrl;
            }
        }

        const t = (key: string, params?: Record<string, string | number>) => this.t(key, params);
        const year = new Date().getFullYear();
        const brand = getPlatformBrandBootstrap();
        const supportMail = brand === undefined || brand === null || typeof brand.supportEmail !== 'string' ? '' : brand.supportEmail;
        const platformName = brand === undefined || brand === null || typeof brand.platformName !== 'string' ? '' : brand.platformName;

        return html`
            <footer class="footer-container">
                <div class="footer-content">
                    <div class="footer-left">
                        <a href="mailto:${supportMail}" class="footer-email">
                            ${supportMail}
                        </a>
                        <h2 class="footer-logo">${platformName}</h2>
                        ${legal
                            ? html`
                                  <div class="footer-requisites">
                                      <h3>${t('footer.legal_heading')}</h3>
                                      <p>${this._companyName(legal)}</p>
                                      <p>${t('footer.inn_label')} ${this._requireLegalString(legal, 'inn')}</p>
                                      <p>${t('footer.kpp_label')} ${this._requireLegalString(legal, 'kpp')}</p>
                                      <p>${t('footer.ogrn_label')} ${this._requireLegalString(legal, 'ogrn')}</p>
                                      <p>${this._legalAddress(legal)}</p>
                                      <p>${t('footer.bank_label')} ${this._bankName(legal)}</p>
                                      <p>${t('footer.bank_account_label')} ${this._requireLegalString(legal, 'bank_account')}</p>
                                      <p>${t('footer.bank_bik_label')} ${this._requireLegalString(legal, 'bank_bik')}</p>
                                      <p>${t('footer.bank_correspondent_account_label')} ${this._requireLegalString(legal, 'bank_correspondent_account')}</p>
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
                        <a href=${this._legalUrl('/cookies')} class="footer-legal-link">
                            ${t('footer.cookies')}
                        </a>
                        <button type="button" class="footer-legal-link" @click=${this._openCookieSettings}>
                            ${t('footer.cookie_settings')}
                        </button>
                    </div>
                </div>
            </footer>
        `;
    }
}

customElements.define('landing-footer', LandingFooter);

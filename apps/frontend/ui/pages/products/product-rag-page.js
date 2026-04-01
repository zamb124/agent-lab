/**
 * Product RAG Page - Страница продукта Knowledge Base
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/auth-modal.js';

export class ProductRagPage extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                background: var(--landing-bg, #0F0F0F);
                color: var(--landing-text, #FFFFFF);
                min-height: var(--app-vh, 100vh);
            }
            
            .page-container {
                width: 100%;
                overflow-x: hidden;
            }
            
            .hero {
                max-width: 1200px;
                margin: 0 auto;
                padding: 80px 20px 60px;
                text-align: center;
            }
            
            .hero-badge {
                display: inline-block;
                padding: 8px 20px;
                background: rgba(46, 204, 113, 0.15);
                border: 1px solid rgba(46, 204, 113, 0.3);
                border-radius: 100px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: #2ECC71;
                margin-bottom: 24px;
            }
            
            .hero-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 48px;
                font-weight: 600;
                line-height: 1.1;
                margin: 0 0 24px;
                background: linear-gradient(135deg, #FFFFFF 0%, #A0A0A0 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
            }
            
            .hero-icon {
                width: 80px;
                height: 80px;
                margin: 0 auto 24px;
            }
            
            .hero-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            
            .hero-description {
                font-family: 'Fira Sans', sans-serif;
                font-size: 20px;
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.7);
                max-width: 700px;
                margin: 0 auto 40px;
            }
            
            .cta-btn {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 16px 32px;
                background: #2ECC71;
                border: none;
                border-radius: 100px;
                color: #FFFFFF;
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s;
                text-decoration: none;
            }
            
            .cta-btn:hover {
                background: #27AE60;
                transform: translateY(-2px);
            }
            
            .features {
                max-width: 1200px;
                margin: 0 auto;
                padding: 60px 20px;
            }
            
            .features-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 24px;
            }
            
            .feature-card {
                background: rgba(30, 30, 30, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
                padding: 32px;
                transition: all 0.3s;
            }
            
            .feature-card:hover {
                border-color: rgba(46, 204, 113, 0.3);
                transform: translateY(-4px);
            }
            
            .feature-icon {
                font-size: 48px;
                margin-bottom: 20px;
            }
            
            .feature-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 24px;
                font-weight: 600;
                margin: 0 0 12px;
                color: #FFFFFF;
            }
            
            .feature-description {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.7);
                margin: 0;
            }
            
            .benefits {
                background: rgba(46, 204, 113, 0.05);
                border-top: 1px solid rgba(46, 204, 113, 0.1);
                border-bottom: 1px solid rgba(46, 204, 113, 0.1);
                padding: 80px 20px;
            }
            
            .benefits-container {
                max-width: 1200px;
                margin: 0 auto;
            }
            
            .benefits-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 36px;
                font-weight: 600;
                text-align: center;
                margin: 0 0 48px;
                color: #FFFFFF;
            }
            
            .benefits-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 32px;
            }
            
            .benefit-item {
                display: flex;
                align-items: flex-start;
                gap: 20px;
            }
            
            .benefit-icon {
                flex-shrink: 0;
                width: 56px;
                height: 56px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(46, 204, 113, 0.15);
                border-radius: 16px;
                font-size: 28px;
            }
            
            .benefit-content h3 {
                font-family: 'Fira Sans', sans-serif;
                font-size: 20px;
                font-weight: 600;
                margin: 0 0 8px;
                color: #FFFFFF;
            }
            
            .benefit-content p {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.7);
                margin: 0;
            }
            
            .use-cases {
                max-width: 1200px;
                margin: 0 auto;
                padding: 80px 20px;
            }
            
            .use-cases-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 36px;
                font-weight: 600;
                text-align: center;
                margin: 0 0 48px;
                color: #FFFFFF;
            }
            
            .use-cases-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 20px;
            }
            
            .use-case-item {
                display: flex;
                align-items: center;
                gap: 16px;
                padding: 20px 24px;
                background: rgba(30, 30, 30, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 12px;
            }
            
            .use-case-icon {
                font-size: 32px;
            }
            
            .use-case-text {
                font-family: 'Fira Sans', sans-serif;
                font-size: 17px;
                color: rgba(255, 255, 255, 0.85);
            }
            
            .cta-section {
                max-width: 800px;
                margin: 0 auto;
                padding: 80px 20px;
                text-align: center;
            }
            
            .cta-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 36px;
                font-weight: 600;
                margin: 0 0 16px;
                color: #FFFFFF;
            }
            
            .cta-subtitle {
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                color: rgba(255, 255, 255, 0.7);
                margin: 0 0 32px;
            }
            
            .back-link {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 12px 24px;
                color: rgba(255, 255, 255, 0.7);
                text-decoration: none;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                transition: color 0.3s;
                margin-top: 24px;
            }
            
            .back-link:hover {
                color: #2ECC71;
            }
            
            @media (min-width: 768px) {
                .hero {
                    padding: 120px 40px 80px;
                }
                
                .hero-title {
                    font-size: 64px;
                }
                
                .features-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .benefits-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .use-cases-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            
            @media (min-width: 1024px) {
                .hero-title {
                    font-size: 72px;
                }
                
                .features-grid {
                    grid-template-columns: repeat(4, 1fr);
                }
                
                .benefits-grid {
                    grid-template-columns: repeat(3, 1fr);
                }
            }
        `
    ];

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        this.addEventListener('open-auth-modal', this._handleOpenAuthModal);
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        this.removeEventListener('open-auth-modal', this._handleOpenAuthModal);
        super.disconnectedCallback();
    }

    _handleOpenAuthModal = () => {
        const authModal = this.shadowRoot?.querySelector('auth-modal');
        if (authModal) {
            authModal.open = true;
        }
    };

    render() {
        const t = (key) => this.i18n.t(key, {}, 'frontend_products');
        return html`
            <div class="page-container">
                <landing-header></landing-header>
                
                <section class="hero">
                    <div class="hero-icon">
                        <img src="/static/core/assets/service_logos/rag_logo.svg" alt="Knowledge Base" />
                    </div>
                    <span class="hero-badge">${t('rag.hero_badge')}</span>
                    <h1 class="hero-title">${t('rag.hero_title')}</h1>
                    <p class="hero-description">
                        ${t('rag.hero_description')}
                    </p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        ${t('rag.cta_try')}
                    </button>
                </section>
                
                <section class="features">
                    <div class="features-grid">
                        <div class="feature-card">
                            <div class="feature-icon">📄</div>
                            <h3 class="feature-title">${t('rag.f1_title')}</h3>
                            <p class="feature-description">
                                ${t('rag.f1_desc')}
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🔍</div>
                            <h3 class="feature-title">${t('rag.f2_title')}</h3>
                            <p class="feature-description">
                                ${t('rag.f2_desc')}
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🤖</div>
                            <h3 class="feature-title">${t('rag.f3_title')}</h3>
                            <p class="feature-description">
                                ${t('rag.f3_desc')}
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🔒</div>
                            <h3 class="feature-title">${t('rag.f4_title')}</h3>
                            <p class="feature-description">
                                ${t('rag.f4_desc')}
                            </p>
                        </div>
                    </div>
                </section>
                
                <section class="benefits">
                    <div class="benefits-container">
                        <h2 class="benefits-title">${t('rag.benefits_title')}</h2>
                        <div class="benefits-grid">
                            <div class="benefit-item">
                                <div class="benefit-icon">⚡</div>
                                <div class="benefit-content">
                                    <h3>${t('rag.b1_h')}</h3>
                                    <p>${t('rag.b1_p')}</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">🎓</div>
                                <div class="benefit-content">
                                    <h3>${t('rag.b2_h')}</h3>
                                    <p>${t('rag.b2_p')}</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">📞</div>
                                <div class="benefit-content">
                                    <h3>${t('rag.b3_h')}</h3>
                                    <p>${t('rag.b3_p')}</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">📖</div>
                                <div class="benefit-content">
                                    <h3>${t('rag.b4_h')}</h3>
                                    <p>${t('rag.b4_p')}</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">🔄</div>
                                <div class="benefit-content">
                                    <h3>${t('rag.b5_h')}</h3>
                                    <p>${t('rag.b5_p')}</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">💡</div>
                                <div class="benefit-content">
                                    <h3>${t('rag.b6_h')}</h3>
                                    <p>${t('rag.b6_p')}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
                
                <section class="use-cases">
                    <h2 class="use-cases-title">${t('rag.use_cases_title')}</h2>
                    <div class="use-cases-grid">
                        <div class="use-case-item">
                            <span class="use-case-icon">📋</span>
                            <span class="use-case-text">${t('rag.uc1')}</span>
                        </div>
                        <div class="use-case-item">
                            <span class="use-case-icon">❓</span>
                            <span class="use-case-text">${t('rag.uc2')}</span>
                        </div>
                        <div class="use-case-item">
                            <span class="use-case-icon">📦</span>
                            <span class="use-case-text">${t('rag.uc3')}</span>
                        </div>
                        <div class="use-case-item">
                            <span class="use-case-icon">📝</span>
                            <span class="use-case-text">${t('rag.uc4')}</span>
                        </div>
                        <div class="use-case-item">
                            <span class="use-case-icon">🎓</span>
                            <span class="use-case-text">${t('rag.uc5')}</span>
                        </div>
                        <div class="use-case-item">
                            <span class="use-case-icon">📊</span>
                            <span class="use-case-text">${t('rag.uc6')}</span>
                        </div>
                    </div>
                </section>
                
                <section class="cta-section">
                    <h2 class="cta-title">${t('rag.cta_title')}</h2>
                    <p class="cta-subtitle">${t('rag.cta_subtitle')}</p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        ${t('rag.cta_button')}
                    </button>
                    <a href="/" class="back-link">${t('rag.back_home')}</a>
                </section>
                
                <landing-footer></landing-footer>
            </div>
            
            <auth-modal></auth-modal>
        `;
    }
}

customElements.define('product-rag-page', ProductRagPage);

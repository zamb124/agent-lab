/**
 * Product Sync Page - Страница продукта Sync
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/auth-modal.js';

export class ProductSyncPage extends PlatformElement {
    static styles = [
        ...PlatformElement.styles,
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
                background: rgba(99, 102, 241, 0.15);
                border: 1px solid rgba(139, 92, 246, 0.35);
                border-radius: 100px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-primary, #6366f1);
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
                background: var(--landing-primary, #6366f1);
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
                filter: brightness(1.1);
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
                border-color: rgba(139, 92, 246, 0.35);
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
            
            .how-it-works {
                background: rgba(99, 102, 241, 0.06);
                border-top: 1px solid rgba(139, 92, 246, 0.15);
                border-bottom: 1px solid rgba(139, 92, 246, 0.15);
                padding: 80px 20px;
            }
            
            .how-it-works-container {
                max-width: 1200px;
                margin: 0 auto;
            }
            
            .how-it-works-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 36px;
                font-weight: 600;
                text-align: center;
                margin: 0 0 48px;
                color: #FFFFFF;
            }
            
            .steps-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 32px;
            }
            
            .step-item {
                display: flex;
                align-items: flex-start;
                gap: 24px;
            }
            
            .step-number {
                flex-shrink: 0;
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(99, 102, 241, 0.2);
                border: 2px solid var(--landing-primary, #6366f1);
                border-radius: 50%;
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 20px;
                font-weight: 600;
                color: var(--landing-primary, #6366f1);
            }
            
            .step-content h3 {
                font-family: 'Fira Sans', sans-serif;
                font-size: 20px;
                font-weight: 600;
                margin: 0 0 8px;
                color: #FFFFFF;
            }
            
            .step-content p {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.6;
                color: rgba(255, 255, 255, 0.7);
                margin: 0;
            }
            
            .benefits {
                max-width: 1200px;
                margin: 0 auto;
                padding: 80px 20px;
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
                background: rgba(139, 92, 246, 0.15);
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
                color: var(--landing-primary, #6366f1);
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
                
                .steps-grid {
                    grid-template-columns: repeat(2, 1fr);
                }
                
                .benefits-grid {
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
                
                .steps-grid {
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
                        <img src="/static/core/assets/service_logos/sync_logo.svg" alt="Sync" />
                    </div>
                    <span class="hero-badge">${t('sync.hero_badge')}</span>
                    <h1 class="hero-title">${t('sync.hero_title')}</h1>
                    <p class="hero-description">
                        ${t('sync.hero_description')}
                    </p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        ${t('sync.cta_try')}
                    </button>
                </section>
                
                <section class="features">
                    <div class="features-grid">
                        <div class="feature-card">
                            <div class="feature-icon">💬</div>
                            <h3 class="feature-title">${t('sync.f1_title')}</h3>
                            <p class="feature-description">
                                ${t('sync.f1_desc')}
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">📹</div>
                            <h3 class="feature-title">${t('sync.f2_title')}</h3>
                            <p class="feature-description">
                                ${t('sync.f2_desc')}
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🔗</div>
                            <h3 class="feature-title">${t('sync.f3_title')}</h3>
                            <p class="feature-description">
                                ${t('sync.f3_desc')}
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🔔</div>
                            <h3 class="feature-title">${t('sync.f4_title')}</h3>
                            <p class="feature-description">
                                ${t('sync.f4_desc')}
                            </p>
                        </div>
                    </div>
                </section>
                
                <section class="how-it-works">
                    <div class="how-it-works-container">
                        <h2 class="how-it-works-title">${t('sync.how_title')}</h2>
                        <div class="steps-grid">
                            <div class="step-item">
                                <div class="step-number">1</div>
                                <div class="step-content">
                                    <h3>${t('sync.s1_h')}</h3>
                                    <p>${t('sync.s1_p')}</p>
                                </div>
                            </div>
                            
                            <div class="step-item">
                                <div class="step-number">2</div>
                                <div class="step-content">
                                    <h3>${t('sync.s2_h')}</h3>
                                    <p>${t('sync.s2_p')}</p>
                                </div>
                            </div>
                            
                            <div class="step-item">
                                <div class="step-number">3</div>
                                <div class="step-content">
                                    <h3>${t('sync.s3_h')}</h3>
                                    <p>${t('sync.s3_p')}</p>
                                </div>
                            </div>
                            
                            <div class="step-item">
                                <div class="step-number">4</div>
                                <div class="step-content">
                                    <h3>${t('sync.s4_h')}</h3>
                                    <p>${t('sync.s4_p')}</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
                
                <section class="benefits">
                    <h2 class="benefits-title">${t('sync.benefits_title')}</h2>
                    <div class="benefits-grid">
                        <div class="benefit-item">
                            <div class="benefit-icon">⚡</div>
                            <div class="benefit-content">
                                <h3>${t('sync.b1_h')}</h3>
                                <p>${t('sync.b1_p')}</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">🛡️</div>
                            <div class="benefit-content">
                                <h3>${t('sync.b2_h')}</h3>
                                <p>${t('sync.b2_p')}</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">👀</div>
                            <div class="benefit-content">
                                <h3>${t('sync.b3_h')}</h3>
                                <p>${t('sync.b3_p')}</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">🧩</div>
                            <div class="benefit-content">
                                <h3>${t('sync.b4_h')}</h3>
                                <p>${t('sync.b4_p')}</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">👤</div>
                            <div class="benefit-content">
                                <h3>${t('sync.b5_h')}</h3>
                                <p>${t('sync.b5_p')}</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">📎</div>
                            <div class="benefit-content">
                                <h3>${t('sync.b6_h')}</h3>
                                <p>${t('sync.b6_p')}</p>
                            </div>
                        </div>
                    </div>
                </section>
                
                <section class="cta-section">
                    <h2 class="cta-title">${t('sync.cta_title')}</h2>
                    <p class="cta-subtitle">${t('sync.cta_subtitle')}</p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        ${t('sync.cta_button')}
                    </button>
                    <a href="/" class="back-link">${t('sync.back_home')}</a>
                </section>
                
                <landing-footer></landing-footer>
            </div>
            
            <auth-modal></auth-modal>
        `;
    }
}

customElements.define('product-sync-page', ProductSyncPage);

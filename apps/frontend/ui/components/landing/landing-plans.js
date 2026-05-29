/**
 * Тарифы лендинга — тарифы
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendLeadFormModal } from '../../modals/lead-form-modal.js';

export class LandingPlans extends PlatformElement {
    static i18nNamespace = 'landing';

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
            }
            
            .plans-container {
                max-width: 1440px;
                margin: 0 auto;
            }
            
            .plans-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 32px;
                font-weight: 500;
                color: var(--landing-secondary);
                margin: 0 0 60px 0;
                text-align: center;
            }
            
            .plans-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 40px;
            }
            
            .plan-card {
                background: var(--landing-panel-bg, rgba(255, 255, 255, 0.03));
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.1));
                border-radius: 24px;
                padding: 40px;
                backdrop-filter: blur(10px);
                transition: var(--motion-transition-interactive);
            }
            
            .plan-card:hover {
                transform: translateY(-5px);
                border-color: rgba(87, 104, 254, 0.5);
            }
            
            .plan-card.premium {
                background: radial-gradient(circle at top right, rgba(87, 104, 254, 0.2), var(--landing-panel-bg, rgba(255, 255, 255, 0.03)));
                border-color: var(--landing-primary);
                position: relative;
                overflow: hidden;
            }
            
            .plan-card.premium::before {
                content: '';
                position: absolute;
                top: -50%;
                right: -50%;
                width: 200%;
                height: 200%;
                background: radial-gradient(circle, rgba(87, 104, 254, 0.3), transparent 70%);
                filter: blur(80px);
                pointer-events: none;
            }
            
            .plan-badge {
                display: inline-block;
                padding: 6px 16px;
                background: rgba(87, 104, 254, 0.2);
                border: 1px solid var(--landing-primary);
                border-radius: 20px;
                font-size: 12px;
                color: var(--landing-primary);
                margin-bottom: 16px;
                font-weight: 500;
            }
            
            .plan-name {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 36px;
                font-weight: 500;
                color: var(--landing-secondary);
                margin: 0 0 16px 0;
            }

            .plan-price {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 22px;
                font-weight: 600;
                color: var(--landing-primary);
                margin: 0 0 16px 0;
            }
            
            .plan-card.premium .plan-name {
                color: var(--landing-primary);
            }
            
            .plan-description {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.6;
                color: var(--landing-text-soft, rgba(232, 232, 232, 0.8));
                margin: 0 0 32px 0;
            }
            
            .plan-features {
                list-style: none;
                padding: 0;
                margin: 0 0 32px 0;
            }
            
            .plan-features li {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-secondary);
                padding-left: 28px;
                position: relative;
                margin-bottom: 12px;
                line-height: 1.6;
            }
            
            .plan-features li::before {
                content: '✓';
                position: absolute;
                left: 0;
                color: var(--landing-primary);
                font-weight: bold;
                font-size: 18px;
            }
            
            .plan-target {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.6));
                margin: 0 0 24px 0;
                padding-top: 24px;
                border-top: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.1));
            }
            
            .plan-cta {
                width: 100%;
                padding: 16px 32px;
                border-radius: 40px;
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 18px;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                border: none;
            }
            
            .plan-cta.transparent {
                background: transparent;
                border: 1px solid var(--landing-secondary);
                color: var(--landing-on-primary, #FFFFFF);
            }
            
            .plan-cta.transparent:hover {
                background: rgba(87, 104, 254, 0.1);
                border-color: var(--landing-primary);
            }
            
            .plan-cta.primary {
                background: var(--landing-primary);
                color: var(--landing-secondary);
            }
            
            .plan-cta.primary:hover {
                background: #6877ff;
                transform: translateY(-2px);
                box-shadow: 0 10px 30px rgba(87, 104, 254, 0.4);
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 100px 40px;
                }
                
                .plans-title {
                    font-size: 48px;
                    margin-bottom: 80px;
                }
                
                .plans-grid {
                    grid-template-columns: repeat(3, 1fr);
                    gap: 40px;
                }
                
                .plan-card {
                    padding: 50px;
                }
                
                .plan-name {
                    font-size: 40px;
                }
                
                .plan-description {
                    font-size: 18px;
                }
                
                .plan-features li {
                    font-size: 16px;
                }
                
                .plan-target {
                    font-size: 15px;
                }
            }
            
            @media (min-width: 768px) and (max-width: 1199px) {
                .plans-grid {
                    grid-template-columns: 1fr;
                    gap: 48px;
                    max-width: 560px;
                    margin: 0 auto;
                }
            }

            @media (min-width: 1440px) {
                :host {
                    padding: 120px 80px;
                }
                
                .plans-title {
                    font-size: 60px;
                    margin-bottom: 100px;
                }
                
                .plans-grid {
                    gap: 56px;
                }
                
                .plan-card {
                    padding: 60px;
                }
                
                .plan-name {
                    font-size: 48px;
                }
                
                .plan-description {
                    font-size: 20px;
                }
                
                .plan-features li {
                    font-size: 18px;
                }
                
                .plan-target {
                    font-size: 16px;
                }
                
                .plan-cta {
                    font-size: 20px;
                }
            }
        `
    ];

    _handlePlanCta(planKind) {
        if (planKind === 'enterprise') {
            this.openModal(FrontendLeadFormModal);
            return;
        }
        if (planKind === 'business') {
            this.openModal('auth.login', { plan: 'business' });
            return;
        }
        if (planKind === 'self') {
            this.openModal('auth.login', { plan: 'constructor' });
            return;
        }
        throw new Error(`landing-plans: unknown planKind ${planKind}`);
    }

    connectedCallback() {
        super.connectedCallback();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
    }

    render() {
        const t = (key) => this.t(key);
        return html`
            <div class="plans-container">
                <h2 class="plans-title">${t('plans.title')}</h2>
                
                <div class="plans-grid">
                    <div class="plan-card">
                        <div class="plan-badge">${t('plans.self_badge')}</div>
                        <h3 class="plan-name">${t('plans.self_name')}</h3>
                        <p class="plan-price">${t('plans.self_price')}</p>
                        <p class="plan-description">
                            ${t('plans.self_description')}
                        </p>
                        <ul class="plan-features">
                            <li>${t('plans.self_li1')}</li>
                            <li>${t('plans.self_li2')}</li>
                            <li>${t('plans.self_li3')}</li>
                            <li>${t('plans.self_li4')}</li>
                        </ul>
                        <p class="plan-target">
                            ${t('plans.self_target')}
                        </p>
                        <button 
                            class=${classMap({ 'plan-cta': true, 'transparent': true })}
                            @click=${() => this._handlePlanCta('self')}
                        >
                            ${t('plans.self_cta')}
                        </button>
                    </div>
                    
                    <div class=${classMap({ 'plan-card': true, 'premium': true })}>
                        <div class="plan-badge">${t('plans.business_badge')}</div>
                        <h3 class="plan-name">${t('plans.business_name')}</h3>
                        <p class="plan-price">${t('plans.business_price')}</p>
                        <p class="plan-description">
                            ${t('plans.business_description')}
                        </p>
                        <ul class="plan-features">
                            <li>${t('plans.business_li1')}</li>
                            <li>${t('plans.business_li2')}</li>
                            <li>${t('plans.business_li3')}</li>
                            <li>${t('plans.business_li4')}</li>
                        </ul>
                        <p class="plan-target">
                            ${t('plans.business_target')}
                        </p>
                        <button 
                            class=${classMap({ 'plan-cta': true, 'primary': true })}
                            @click=${() => this._handlePlanCta('business')}
                        >
                            ${t('plans.business_cta')}
                        </button>
                    </div>

                    <div class="plan-card">
                        <div class="plan-badge">${t('plans.enterprise_badge')}</div>
                        <h3 class="plan-name">${t('plans.enterprise_name')}</h3>
                        <p class="plan-price">${t('plans.enterprise_price')}</p>
                        <p class="plan-description">
                            ${t('plans.enterprise_description')}
                        </p>
                        <ul class="plan-features">
                            <li>${t('plans.enterprise_li1')}</li>
                            <li>${t('plans.enterprise_li2')}</li>
                            <li>${t('plans.enterprise_li3')}</li>
                            <li>${t('plans.enterprise_li4')}</li>
                        </ul>
                        <p class="plan-target">
                            ${t('plans.enterprise_target')}
                        </p>
                        <button 
                            class=${classMap({ 'plan-cta': true, 'transparent': true })}
                            @click=${() => this._handlePlanCta('enterprise')}
                        >
                            ${t('plans.enterprise_cta')}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-plans', LandingPlans);

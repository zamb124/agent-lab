/**
 * Тарифы лендинга — тарифы
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FrontendLeadFormModal } from '../../modals/lead-form-modal.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

export class LandingPlans extends PlatformElement {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
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
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 32px;
                font-weight: 500;
                color: var(--text-secondary);
                margin: 0 0 60px 0;
                text-align: center;
            }
            
            .plans-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 40px;
            }
            
            .plan-card {
                background: var(--glass-bg-subtle);
                border: 1px solid var(--glass-border-medium);
                border-radius: 24px;
                padding: 40px;
                backdrop-filter: blur(10px);
                transition: var(--motion-transition-interactive);
            }
            
            .plan-card:hover {
                transform: translateY(-5px);
                border-color: color-mix(in srgb, var(--accent) 50%, transparent);
            }
            
            .plan-card.premium {
                background: radial-gradient(circle at top right, color-mix(in srgb, var(--accent) 20%, transparent), var(--glass-bg-subtle));
                border-color: var(--marketing-product-accent);
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
                background: radial-gradient(circle, color-mix(in srgb, var(--accent) 30%, transparent), transparent 70%);
                filter: blur(80px);
                pointer-events: none;
            }
            
            .plan-badge {
                display: inline-block;
                padding: 6px 16px;
                background: color-mix(in srgb, var(--accent) 20%, transparent);
                border: 1px solid var(--marketing-product-accent);
                border-radius: 20px;
                font-size: 12px;
                color: var(--marketing-product-accent);
                margin-bottom: 16px;
                font-weight: 500;
            }
            
            .plan-name {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 36px;
                font-weight: 500;
                color: var(--text-secondary);
                margin: 0 0 16px 0;
            }

            .plan-price {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 22px;
                font-weight: 600;
                color: var(--marketing-product-accent);
                margin: 0 0 16px 0;
            }
            
            .plan-card.premium .plan-name {
                color: var(--marketing-product-accent);
            }
            
            .plan-description {
                font-family: var(--font-sans);
                font-size: 16px;
                line-height: 1.6;
                color: var(--text-secondary);
                margin: 0 0 32px 0;
            }
            
            .plan-features {
                list-style: none;
                padding: 0;
                margin: 0 0 32px 0;
            }
            
            .plan-features li {
                font-family: var(--font-sans);
                font-size: 14px;
                color: var(--text-secondary);
                padding-left: 28px;
                position: relative;
                margin-bottom: 12px;
                line-height: 1.6;
            }
            
            .plan-features li::before {
                content: '✓';
                position: absolute;
                left: 0;
                color: var(--marketing-product-accent);
                font-weight: bold;
                font-size: 18px;
            }
            
            .plan-target {
                font-family: var(--font-sans);
                font-size: 14px;
                color: var(--text-secondary);
                margin: 0 0 24px 0;
                padding-top: 24px;
                border-top: 1px solid var(--glass-border-medium);
            }
            
            .plan-cta {
                width: 100%;
                padding: 16px 32px;
                border-radius: 40px;
                font-family: var(--font-sans);
                font-weight: 500;
                font-size: 18px;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                border: none;
            }
            
            .plan-cta.transparent {
                background: transparent;
                border: 1px solid var(--text-secondary);
                color: var(--text-on-accent);
            }
            
            .plan-cta.transparent:hover {
                background: color-mix(in srgb, var(--accent) 10%, transparent);
                border-color: var(--marketing-product-accent);
            }
            
            .plan-cta.primary {
                background: var(--marketing-product-accent);
                color: var(--text-secondary);
            }
            
            .plan-cta.primary:hover {
                background: var(--accent);
                transform: translateY(-2px);
                box-shadow: 0 10px 30px color-mix(in srgb, var(--accent) 40%, transparent);
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

    _handlePlanCta(planKind: string) {
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

    override connectedCallback(): void {
        super.connectedCallback();
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
    }

    override render(): TemplateResult {
        const t = (key: string) => this.t(key);
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

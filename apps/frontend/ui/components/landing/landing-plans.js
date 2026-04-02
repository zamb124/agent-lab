/**
 * Landing Plans - Тарифы
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';

export class LandingPlans extends PlatformElement {
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
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px;
                padding: 40px;
                backdrop-filter: blur(10px);
                transition: all 0.3s;
            }
            
            .plan-card:hover {
                transform: translateY(-5px);
                border-color: rgba(87, 104, 254, 0.5);
            }
            
            .plan-card.premium {
                background: radial-gradient(circle at top right, rgba(87, 104, 254, 0.2), rgba(255, 255, 255, 0.03));
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
            
            .plan-card.premium .plan-name {
                color: var(--landing-primary);
            }
            
            .plan-description {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.6;
                color: rgba(232, 232, 232, 0.8);
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
                color: rgba(232, 232, 232, 0.6);
                margin: 0 0 24px 0;
                padding-top: 24px;
                border-top: 1px solid rgba(255, 255, 255, 0.1);
            }
            
            .plan-cta {
                width: 100%;
                padding: 16px 32px;
                border-radius: 40px;
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 18px;
                cursor: pointer;
                transition: all 0.3s;
                border: none;
            }
            
            .plan-cta.transparent {
                background: transparent;
                border: 1px solid var(--landing-secondary);
                color: var(--landing-secondary);
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
                    grid-template-columns: repeat(2, 1fr);
                    gap: 60px;
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
            
            @media (min-width: 1440px) {
                :host {
                    padding: 120px 80px;
                }
                
                .plans-title {
                    font-size: 60px;
                    margin-bottom: 100px;
                }
                
                .plans-grid {
                    gap: 80px;
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

    _handleCTA(planType) {
        if (planType === 'constructor') {
            this.dispatchEvent(new CustomEvent('open-auth-modal', {
                bubbles: true,
                composed: true
            }));
            return;
        }
        this.dispatchEvent(new CustomEvent('plan-selected', {
            detail: { plan: planType },
            bubbles: true,
            composed: true
        }));
    }

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

    render() {
        const t = (key) => this.i18n.t(key, {}, I18nNs.LANDING);
        return html`
            <div class="plans-container">
                <h2 class="plans-title">${t('plans.title')}</h2>
                
                <div class="plans-grid">
                    <div class="plan-card">
                        <div class="plan-badge">${t('plans.self_badge')}</div>
                        <h3 class="plan-name">${t('plans.self_name')}</h3>
                        <p class="plan-description">
                            ${t('plans.self_description')}
                        </p>
                        <ul class="plan-features">
                            <li>${t('plans.self_li1')}</li>
                            <li>${t('plans.self_li2')}</li>
                            <li>${t('plans.self_li3')}</li>
                            <li>${t('plans.self_li4')}</li>
                            <li>${t('plans.self_li5')}</li>
                            <li>${t('plans.self_li6')}</li>
                        </ul>
                        <p class="plan-target">
                            ${t('plans.self_target')}
                        </p>
                        <button 
                            class=${classMap({ 'plan-cta': true, 'transparent': true })}
                            @click=${() => this._handleCTA('constructor')}
                        >
                            ${t('plans.self_cta')}
                        </button>
                    </div>
                    
                    <div class=${classMap({ 'plan-card': true, 'premium': true })}>
                        <div class="plan-badge">${t('plans.team_badge')}</div>
                        <h3 class="plan-name">${t('plans.team_name')}</h3>
                        <p class="plan-description">
                            ${t('plans.team_description')}
                        </p>
                        <ul class="plan-features">
                            <li>${t('plans.team_li1')}</li>
                            <li>${t('plans.team_li2')}</li>
                            <li>${t('plans.team_li3')}</li>
                            <li>${t('plans.team_li4')}</li>
                            <li>${t('plans.team_li5')}</li>
                        </ul>
                        <p class="plan-target">
                            ${t('plans.team_target')}
                        </p>
                        <button 
                            class=${classMap({ 'plan-cta': true, 'primary': true })}
                            @click=${() => this._handleCTA('expert')}
                        >
                            ${t('plans.team_cta')}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-plans', LandingPlans);


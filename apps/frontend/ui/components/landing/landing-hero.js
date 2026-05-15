/**
 * Landing Hero - Главная секция лендинга
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingHero extends PlatformElement {
    static i18nNamespace = 'landing';

    static properties = {
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                box-sizing: border-box;
                min-height: var(--app-vh, 100vh);
                position: relative;
                overflow: hidden;
                background: #0F0F0F;
            }
            
            .hero-container {
                max-width: 1440px;
                width: 100%;
                margin: 0 auto;
                padding: 0;
                box-sizing: border-box;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: calc(var(--app-vh, 100vh) - 71px);
                position: relative;
            }
            
            .hero-subtitle {
                display: none;
            }

            .hero-title {
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-family: 'Fira Sans Condensed', sans-serif;
                font-weight: 500;
                font-size: 280px;
                line-height: 320px;
                text-align: center;
                color: var(--landing-primary, #5768FE);
                margin: 0;
                text-transform: capitalize;
                z-index: 1;
                white-space: nowrap;
            }
            
            .hero-image-wrapper {
                position: relative;
                z-index: 10;
                width: 100%;
                max-width: 1200px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .hero-image {
                width: 100%;
                height: auto;
                object-fit: contain;
                filter: drop-shadow(0 0 60px rgba(87, 104, 254, 0.4));
            }
            
            .hero-text-left {
                position: absolute;
                bottom: 100px;
                left: 50px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 22px;
                line-height: 1.4;
                color: var(--landing-secondary, #E8E8E8);
                max-width: 280px;
                z-index: 3;
            }
            
            .hero-text-right {
                position: absolute;
                bottom: 100px;
                right: 50px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 22px;
                line-height: 1.4;
                color: var(--landing-secondary, #E8E8E8);
                max-width: 280px;
                text-align: right;
                z-index: 3;
            }
            
            .hero-cta {
                position: absolute;
                bottom: 140px;
                left: 50%;
                transform: translateX(-50%);
                padding: 12px 24px;
                background: var(--landing-primary, #5768FE);
                color: var(--landing-secondary, #E8E8E8);
                border: none;
                border-radius: 40px;
                font-family: 'Fira Sans', sans-serif;
                font-weight: 500;
                font-size: 20px;
                line-height: 24px;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
                white-space: nowrap;
                z-index: 11;
                box-shadow: none;
                text-align: center;
            }
            
            .hero-cta:hover {
                background: #6877ff;
                transform: translateX(-50%) translateY(-2px);
            }
            
            @media (max-width: 768px) {
                .hero-subtitle {
                    position: static;
                    transform: none;
                    margin: 16px auto 0;
                    pointer-events: auto;
                }

                .hero-title {
                    position: static;
                    transform: none;
                    font-size: min(80px, calc((100vw - 32px) / 5.2));
                    line-height: 1.05;
                    max-width: calc(100% - 16px);
                    box-sizing: border-box;
                }
            
                .hero-image-wrapper {
                    max-width: 350px;
                }
                
                .hero-text-left,
                .hero-text-right {
                    position: static;
                    max-width: 100%;
                    text-align: center;
                    margin: 20px;
                    font-size: 18px;
                }
            
                .hero-cta {
                    position: static;
                    transform: none;
                    margin: 20px auto;
                    display: block;
                    white-space: normal;
                    max-width: min(100%, calc(100vw - 32px));
                    box-sizing: border-box;
                    padding: 12px 16px;
                }
                
                .hero-cta:hover {
                    transform: translateY(-2px);
                }
                
                .hero-container {
                    flex-direction: column;
                    justify-content: center;
                    padding: 40px 20px;
                }

                .hero-title {
                    order: 1;
                }

                .hero-subtitle {
                    order: 2;
                }

                .hero-image-wrapper {
                    order: 3;
                }

                .hero-text-left {
                    order: 4;
                }

                .hero-cta {
                    order: 5;
                }

                .hero-text-right {
                    order: 6;
                }
            }
            
            @media (min-width: 769px) and (max-width: 1439px) {
                .hero-subtitle {
                    top: 62%;
                }

                .hero-title {
                    font-size: min(200px, calc((100vw - 64px) / 5.2));
                    line-height: 1.1;
                }
                
                .hero-image-wrapper {
                    max-width: 800px;
                }
                
                .hero-text-left {
                    left: 30px;
                    bottom: 80px;
                    font-size: 20px;
                    max-width: 240px;
                }
                
                .hero-text-right {
                    right: 30px;
                    bottom: 80px;
                    font-size: 20px;
                    max-width: 240px;
                }
                
                .hero-cta {
                    bottom: 120px;
                    font-size: 16px;
                    padding: 14px 32px;
                }
            }
            
            @media (min-width: 1440px) {
                .hero-subtitle {
                    top: 60%;
                    font-size: clamp(16px, 1.6vw, 22px);
                    max-width: 800px;
                }

                .hero-title {
                    font-size: clamp(200px, 15vw, 320px);
                    line-height: 1.1;
                }
                
                .hero-image-wrapper {
                    max-width: min(900px, 65vw);
                }
                
                .hero-text-left {
                    left: 48px;
                    bottom: 100px;
                    font-size: 22px;
                    max-width: 320px;
                }
                
                .hero-text-right {
                    right: 48px;
                    bottom: 100px;
                    font-size: 22px;
                    max-width: 320px;
                }
                
                .hero-cta {
                    bottom: 140px;
                    font-size: 18px;
                    padding: 14px 28px;
                }
            }
        `
    ];

    _handleCTA = () => {
        this.navigate('digital-workers');
    };

    render() {
        const t = (key) => this.t(key);
        return html`
            <div class="hero-container">
                <h1 class="hero-title">HUMANITEC</h1>
                <p class="hero-subtitle">${t('hero.subtitle')}</p>
                
                    <div class="hero-image-wrapper">
                        <img
                            src="/static/frontend/assets/images/main_img.png"
                            alt=${t('hero.image_alt')}
                            class="hero-image"
                        />
                    </div>
                    
                <p class="hero-text-left">
                    ${unsafeHTML(t('hero.trust_process'))}
                        </p>
                        
                        <button class="hero-cta" @click=${this._handleCTA}>
                            ${t('hero.start_button')}
                        </button>
                        
                <p class="hero-text-right">
                    ${unsafeHTML(t('hero.evolution'))}
                        </p>
            </div>
        `;
    }
}

customElements.define('landing-hero', LandingHero);


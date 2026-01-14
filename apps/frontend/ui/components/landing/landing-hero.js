/**
 * Landing Hero - Главная секция лендинга
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingHero extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-height: 100vh;
                position: relative;
                overflow: hidden;
                background: #0F0F0F;
            }
            
            .hero-container {
                max-width: 1440px;
                margin: 0 auto;
                padding: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                min-height: calc(100vh - 71px);
                position: relative;
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
                transition: all 0.3s ease;
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
                .hero-title {
                    font-size: 80px;
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
                }
                
                .hero-container {
                    flex-direction: column;
                    justify-content: center;
                    padding: 40px 20px;
                }
            }
            
            @media (min-width: 769px) and (max-width: 1439px) {
                .hero-title {
                    font-size: 200px;
                    line-height: 224px;
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

    _handleCTA() {
        const ctaSection = document.querySelector('landing-cta');
        if (ctaSection) {
            ctaSection.scrollIntoView({ behavior: 'smooth' });
        }
    }

    render() {
        return html`
            <div class="hero-container">
                <h1 class="hero-title">HUMANITEC</h1>
                
                    <div class="hero-image-wrapper">
                        <img 
                            src="/static/frontend/assets/images/main_img.png" 
                            alt="Humanitec Platform"
                            class="hero-image"
                        />
                    </div>
                    
                <p class="hero-text-left">
                    Доверьте процессы<br>AI-агентам
                        </p>
                        
                        <button class="hero-cta" @click=${this._handleCTA}>
                            Запустить цифровых сотрудников
                        </button>
                        
                <p class="hero-text-right">
                    Эволюция вашего<br>бизнеса уже здесь
                        </p>
            </div>
        `;
    }
}

customElements.define('landing-hero', LandingHero);


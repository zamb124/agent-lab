/**
 * Landing Advantages - Преимущества с плывущими badges
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingAdvantages extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 100px 20px;
                position: relative;
                overflow: hidden;
            }
            
            .blur-bg-primary {
                position: absolute;
                width: 800px;
                height: 800px;
                background: rgba(87, 104, 254, 0.6);
                filter: blur(150px);
                border-radius: 50%;
                top: 10%;
                left: -200px;
                pointer-events: none;
                z-index: 0;
            }
            
            .blur-bg-white {
                position: absolute;
                width: 1000px;
                height: 400px;
                background: rgba(255, 255, 255, 0.2);
                filter: blur(100px);
                top: 40%;
                right: -300px;
                pointer-events: none;
                z-index: 0;
            }
            
            .advantages-container {
                max-width: 1440px;
                margin: 0 auto;
                position: relative;
                z-index: 1;
            }
            
            .advantages-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 32px;
                font-weight: 500;
                line-height: 1.3;
                color: var(--landing-secondary);
                text-align: center;
                margin: 0 0 80px 0;
                max-width: 900px;
                margin-left: auto;
                margin-right: auto;
            }
            
            .advantages-grid {
                display: flex;
                flex-direction: column;
                gap: 40px;
                align-items: center;
            }
            
            .advantage-badge {
                padding: 20px 32px;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 30px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                color: var(--landing-secondary);
                backdrop-filter: blur(20px);
                text-align: center;
                animation: floatBadge 4s ease-in-out infinite;
                transition: all 0.3s;
                max-width: 320px;
            }
            
            .advantage-badge:nth-child(1) {
                animation-delay: 0s;
            }
            
            .advantage-badge:nth-child(2) {
                animation-delay: 0.8s;
                font-size: 18px;
                padding: 24px 40px;
            }
            
            .advantage-badge--featured {
                animation-delay: 1.6s;
                font-size: 20px;
                padding: 28px 48px;
                border-color: var(--landing-primary);
            }
            
            .advantage-badge:nth-child(4) {
                animation-delay: 2.4s;
            }
            
            .advantage-badge:nth-child(5) {
                animation-delay: 3.2s;
            }
            
            .advantage-badge:nth-child(6) {
                animation-delay: 4s;
                font-size: 18px;
                padding: 24px 40px;
            }
            
            .advantage-badge:hover {
                border-color: var(--landing-primary);
                transform: translateY(-5px) scale(1.05);
                animation-play-state: paused;
                box-shadow: 0 10px 40px rgba(87, 104, 254, 0.3);
            }
            
            .advantage-link {
                text-decoration: none;
                cursor: pointer;
            }
            
            .advantage-link:hover {
                background: rgba(87, 104, 254, 0.15);
            }
            
            @keyframes floatBadge {
                0%, 100% {
                    transform: translateY(0) rotate(0deg);
                }
                25% {
                    transform: translateY(-15px) rotate(1deg);
                }
                50% {
                    transform: translateY(-5px) rotate(-1deg);
                }
                75% {
                    transform: translateY(-20px) rotate(1deg);
                }
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 120px 40px;
                }
                
                .advantages-title {
                    font-size: 48px;
                    margin-bottom: 100px;
                }
                
                .advantages-grid {
                    display: grid;
                    grid-template-columns: repeat(2, 1fr);
                    gap: 60px;
                    align-items: start;
                }
                
                .advantage-badge {
                    font-size: 18px;
                    padding: 24px 36px;
                }
                
                .advantage-badge:nth-child(2) {
                    font-size: 20px;
                    padding: 28px 44px;
                    transform: translateY(40px);
                }
                
                .advantage-badge--featured {
                    font-size: 24px;
                    padding: 32px 52px;
                    grid-column: span 2;
                    justify-self: center;
                    max-width: 500px;
                }
                
                .advantage-badge:nth-child(6) {
                    font-size: 20px;
                    padding: 28px 44px;
                    transform: translateY(40px);
                }
            }
            
            @media (min-width: 1440px) {
                :host {
                    padding: 150px 80px;
                }
                
                .advantages-title {
                    font-size: 60px;
                    margin-bottom: 120px;
                }
                
                .advantages-grid {
                    grid-template-columns: repeat(3, 1fr);
                    gap: 80px;
                }
                
                .advantage-badge {
                    font-size: 20px;
                    padding: 28px 40px;
                }
                
                .advantage-badge:nth-child(2) {
                    font-size: 22px;
                    padding: 32px 48px;
                }
                
                .advantage-badge--featured {
                    font-size: 28px;
                    padding: 36px 56px;
                    max-width: 600px;
                }
                
                .advantage-badge:nth-child(6) {
                    font-size: 22px;
                    padding: 32px 48px;
                }
            }
        `
    ];

    render() {
        return html`
            <div class="blur-bg-primary"></div>
            <div class="blur-bg-white"></div>
            
            <div class="advantages-container">
                <h2 class="advantages-title">
                    Обеспечим впечатляющие результаты вашему бизнесу
                </h2>
                
                <div class="advantages-grid">
                    <a href="/products/agents" class="advantage-badge advantage-link">
                        AI Studio — конструктор агентов без кода
                    </a>
                    
                    <a href="/products/rag" class="advantage-badge advantage-link">
                        Knowledge Base — умный поиск по документам
                    </a>
                    
                    <a href="/products/crm" class="advantage-badge advantage-badge--featured advantage-link">
                        NetWorkle — граф связей вашего бизнеса
                    </a>
                    
                    <a href="/products/sync" class="advantage-badge advantage-link">
                        Sync — чат и видеозвонки для команды
                    </a>
                    
                    <div class="advantage-badge">
                        Запуск первого агента за 1 день
                    </div>
                    
                    <div class="advantage-badge">
                        On-premise или облако — вы выбираете
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-advantages', LandingAdvantages);


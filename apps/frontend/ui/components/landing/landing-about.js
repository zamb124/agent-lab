/**
 * Landing About - О нас и статистика
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingAbout extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
            }
            
            .about-container {
                max-width: 1440px;
                margin: 0 auto;
            }
            
            .about-header {
                text-align: center;
                margin-bottom: 60px;
            }
            
            .about-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 32px;
                font-weight: 500;
                line-height: 1.3;
                color: var(--landing-secondary);
                margin: 0 0 24px 0;
            }
            
            .about-description {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.6;
                color: rgba(232, 232, 232, 0.8);
                max-width: 800px;
                margin: 0 auto;
            }
            
            .stats-grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 20px;
                margin-bottom: 60px;
            }
            
            .stat-card {
                background: radial-gradient(circle at top left, rgba(87, 104, 254, 0.1), transparent);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                padding: 30px;
                backdrop-filter: blur(10px);
                transition: all 0.3s;
            }
            
            .stat-card:hover {
                border-color: var(--landing-primary);
                transform: translateY(-5px);
                box-shadow: 0 10px 40px rgba(87, 104, 254, 0.2);
            }
            
            .stat-value {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 48px;
                font-weight: 700;
                color: var(--landing-primary);
                margin: 0 0 8px 0;
            }
            
            .stat-label {
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                color: var(--landing-secondary);
                margin: 0;
            }
            
            .integrations {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            
            .integrations-title {
                font-family: 'Fira Sans', sans-serif;
                font-size: 20px;
                color: var(--landing-secondary);
                text-align: center;
                margin: 0 0 20px 0;
            }
            
            .integrations-cloud {
                display: flex;
                flex-wrap: wrap;
                justify-content: center;
                gap: 12px 16px;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px 0;
            }
            
            .integration-badge {
                padding: 12px 20px;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 24px;
                font-size: 14px;
                color: var(--landing-secondary);
                backdrop-filter: blur(10px);
                transition: all 0.3s;
                animation: float 4s ease-in-out infinite;
            }
            
            .integration-badge:nth-child(1) { animation-delay: 0s; transform: translateY(3px); }
            .integration-badge:nth-child(2) { animation-delay: 0.3s; transform: translateY(-5px); }
            .integration-badge:nth-child(3) { animation-delay: 0.6s; transform: translateY(2px); }
            .integration-badge:nth-child(4) { animation-delay: 0.9s; transform: translateY(-3px); }
            .integration-badge:nth-child(5) { animation-delay: 1.2s; transform: translateY(4px); }
            .integration-badge:nth-child(6) { animation-delay: 0.4s; transform: translateY(-2px); }
            .integration-badge:nth-child(7) { animation-delay: 0.7s; transform: translateY(5px); }
            .integration-badge:nth-child(8) { animation-delay: 1s; transform: translateY(-4px); }
            .integration-badge:nth-child(9) { animation-delay: 0.2s; transform: translateY(1px); }
            .integration-badge:nth-child(10) { animation-delay: 0.5s; transform: translateY(-6px); }
            .integration-badge:nth-child(11) { animation-delay: 0.8s; transform: translateY(3px); }
            .integration-badge:nth-child(12) { animation-delay: 1.1s; transform: translateY(-2px); }
            .integration-badge:nth-child(13) { animation-delay: 0.15s; transform: translateY(4px); }
            .integration-badge:nth-child(14) { animation-delay: 0.45s; transform: translateY(-5px); }
            .integration-badge:nth-child(15) { animation-delay: 0.75s; transform: translateY(2px); }
            
            .integration-badge:hover {
                border-color: var(--landing-primary);
                transform: translateY(-8px) scale(1.05);
                animation-play-state: paused;
                box-shadow: 0 8px 24px rgba(87, 104, 254, 0.3);
            }
            
            .integration-badge.product {
                text-decoration: none;
                cursor: pointer;
                border-color: var(--landing-primary);
                background: rgba(87, 104, 254, 0.15);
                font-weight: 500;
            }
            
            .integration-badge.product:hover {
                background: rgba(87, 104, 254, 0.3);
            }
            
            .integration-badge.highlight {
                background: rgba(87, 104, 254, 0.08);
                border-color: rgba(87, 104, 254, 0.4);
            }
            
            @keyframes float {
                0%, 100% {
                    transform: translateY(0);
                }
                50% {
                    transform: translateY(-10px);
                }
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 100px 40px;
                }
                
                .about-title {
                    font-size: 48px;
                }
                
                .about-description {
                    font-size: 18px;
                }
                
                .stats-grid {
                    grid-template-columns: repeat(2, 1fr);
                    gap: 30px;
                }
                
                .stat-card {
                    padding: 40px;
                }
                
                .stat-value {
                    font-size: 56px;
                }
                
                .stat-label {
                    font-size: 20px;
                }
                
                .integrations-title {
                    font-size: 24px;
                }
                
                .integration-badge {
                    padding: 12px 20px;
                    font-size: 16px;
                }
            }
            
            @media (min-width: 1440px) {
                :host {
                    padding: 120px 80px;
                }
                
                .about-title {
                    font-size: 60px;
                }
                
                .about-description {
                    font-size: 20px;
                }
                
                .stats-grid {
                    grid-template-columns: repeat(4, 1fr);
                    gap: 40px;
                }
                
                .stat-value {
                    font-size: 64px;
                }
                
                .stat-label {
                    font-size: 22px;
                }
                
                .integrations-title {
                    font-size: 28px;
                }
                
                .integration-badge {
                    padding: 14px 24px;
                    font-size: 18px;
                }
            }
        `
    ];

    render() {
        return html`
            <div class="about-container">
                <div class="about-header">
                    <h2 class="about-title">
                        Humanitec — ваша команда AI-сотрудников
                    </h2>
                    <p class="about-description">
                        Платформа с инструментами для автоматизации бизнеса: AI-агенты, умная база знаний 
                        и система управления контактами. Освобождаем время для роста.
                    </p>
                </div>
                
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">25+</div>
                        <p class="stat-label">встроенных<br>инструментов</p>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-value">500+</div>
                        <p class="stat-label">вариантов<br>AI-моделей</p>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-value">50 ₽</div>
                        <p class="stat-label">для старта<br>на платформе</p>
                    </div>
                    
                    <div class="stat-card">
                        <div class="stat-value">∞</div>
                        <p class="stat-label">возможности<br>автоматизации</p>
                    </div>
                </div>
                
                <div class="integrations">
                    <h3 class="integrations-title">Продукты и возможности</h3>
                    
                    <div class="integrations-cloud">
                        <a href="/products/agents" class="integration-badge product">AI Studio</a>
                        <span class="integration-badge">Telegram</span>
                        <span class="integration-badge highlight">Распознавание речи</span>
                        <a href="/products/rag" class="integration-badge product">Knowledge Base</a>
                        <span class="integration-badge">WhatsApp</span>
                        <span class="integration-badge">REST API</span>
                        <span class="integration-badge highlight">PDF & Word</span>
                        <a href="/products/crm" class="integration-badge product">NetWorkle</a>
                        <span class="integration-badge">Email</span>
                        <span class="integration-badge highlight">Граф связей</span>
                        <span class="integration-badge">amoCRM</span>
                        <span class="integration-badge">Webhooks</span>
                        <span class="integration-badge highlight">Семантический поиск</span>
                        <span class="integration-badge">Python SDK</span>
                        <span class="integration-badge highlight">500+ AI-моделей</span>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-about', LandingAbout);


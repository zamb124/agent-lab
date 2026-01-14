/**
 * Landing Reviews - Отзывы со слайдером
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingReviews extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
                background: linear-gradient(180deg, #0F0F0F 0%, #16213e 100%);
            }
            
            .reviews-container {
                max-width: 1200px;
                margin: 0 auto;
            }
            
            .reviews-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 32px;
                font-weight: 500;
                line-height: 1.3;
                color: var(--landing-secondary);
                text-align: center;
                margin: 0 0 60px 0;
            }
            
            .review-card {
                background: radial-gradient(circle at top left, rgba(87, 104, 254, 0.15), rgba(255, 255, 255, 0.03));
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px;
                padding: 40px;
                backdrop-filter: blur(20px);
                min-height: 300px;
                display: flex;
                flex-direction: column;
                animation: fadeIn 0.5s ease-in-out;
            }
            
            @keyframes fadeIn {
                from {
                    opacity: 0;
                    transform: translateX(20px);
                }
                to {
                    opacity: 1;
                    transform: translateX(0);
                }
            }
            
            .review-header {
                display: flex;
                align-items: center;
                gap: 16px;
                margin-bottom: 24px;
            }
            
            .review-avatar {
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: linear-gradient(135deg, var(--landing-primary), #8b9dff);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 24px;
                font-weight: bold;
                color: white;
                flex-shrink: 0;
            }
            
            .review-author {
                flex: 1;
            }
            
            .review-name {
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                font-weight: 600;
                color: var(--landing-secondary);
                margin: 0 0 4px 0;
            }
            
            .review-position {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: rgba(232, 232, 232, 0.6);
                margin: 0;
            }
            
            .review-text {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.7;
                color: rgba(232, 232, 232, 0.9);
                margin: 0;
                flex: 1;
            }
            
            .review-dots {
                display: flex;
                justify-content: center;
                gap: 12px;
                margin-top: 40px;
            }
            
            .dot {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.2);
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .dot.active {
                background: var(--landing-primary);
                transform: scale(1.2);
            }
            
            .dot:hover:not(.active) {
                background: rgba(255, 255, 255, 0.4);
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 100px 40px;
                }
                
                .reviews-title {
                    font-size: 48px;
                    margin-bottom: 80px;
                }
                
                .review-card {
                    padding: 60px;
                    min-height: 350px;
                }
                
                .review-avatar {
                    width: 80px;
                    height: 80px;
                    font-size: 32px;
                }
                
                .review-name {
                    font-size: 22px;
                }
                
                .review-position {
                    font-size: 16px;
                }
                
                .review-text {
                    font-size: 18px;
                }
            }
            
            @media (min-width: 1440px) {
                :host {
                    padding: 120px 80px;
                }
                
                .reviews-title {
                    font-size: 56px;
                    margin-bottom: 100px;
                }
                
                .review-card {
                    padding: 80px;
                    min-height: 400px;
                }
                
                .review-text {
                    font-size: 20px;
                }
            }
        `
    ];

    static properties = {
        currentReview: { type: Number },
        reviews: { type: Array }
    };

    constructor() {
        super();
        this.currentReview = 0;
        this.reviews = [
            {
                name: 'Алексей Иванов',
                position: 'CEO, TechStart',
                avatar: 'АИ',
                text: 'Humanitec помог нам автоматизировать обработку заявок от клиентов. Теперь наша команда может сосредоточиться на развитии продукта, а рутинные задачи выполняют AI-агенты. Окупилось за первый месяц!'
            },
            {
                name: 'Мария Петрова',
                position: 'Founder, E-commerce Store',
                avatar: 'МП',
                text: 'Внедрили AI-агента для работы с заказами и обращениями в мессенджерах. Качество обслуживания выросло, а время ответа сократилось с часов до минут. Клиенты довольны, продажи растут!'
            },
            {
                name: 'Дмитрий Соколов',
                position: 'CTO, FinTech Company',
                avatar: 'ДС',
                text: 'Сложные бизнес-процессы, которые раньше требовали команду разработчиков, теперь работают на базе Humanitec. Платформа гибкая, надежная, с отличной поддержкой. Рекомендую!'
            }
        ];
        this._intervalId = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._startAutoplay();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._stopAutoplay();
    }

    _startAutoplay() {
        this._intervalId = setInterval(() => {
            this._nextReview();
        }, 5000);
    }

    _stopAutoplay() {
        if (this._intervalId) {
            clearInterval(this._intervalId);
            this._intervalId = null;
        }
    }

    _nextReview() {
        this.currentReview = (this.currentReview + 1) % this.reviews.length;
    }

    _selectReview(index) {
        this.currentReview = index;
        this._stopAutoplay();
        this._startAutoplay();
    }

    render() {
        const review = this.reviews[this.currentReview];

        return html`
            <div class="reviews-container">
                <h2 class="reviews-title">
                    / Нам доверяют предприниматели и малый бизнес
                </h2>
                
                <div class="review-card">
                    <div class="review-header">
                        <div class="review-avatar">${review.avatar}</div>
                        <div class="review-author">
                            <h3 class="review-name">${review.name}</h3>
                            <p class="review-position">${review.position}</p>
                        </div>
                    </div>
                    <p class="review-text">${review.text}</p>
                </div>
                
                <div class="review-dots">
                    ${this.reviews.map((_, index) => html`
                        <div 
                            class=${classMap({ dot: true, active: index === this.currentReview })}
                            @click=${() => this._selectReview(index)}
                        ></div>
                    `)}
                </div>
            </div>
        `;
    }
}

customElements.define('landing-reviews', LandingReviews);


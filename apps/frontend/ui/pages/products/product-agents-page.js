/**
 * Product Agents Page - Страница продукта AI Studio
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/auth-modal.js';

export class ProductAgentsPage extends PlatformElement {
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
                background: rgba(87, 104, 254, 0.15);
                border: 1px solid rgba(87, 104, 254, 0.3);
                border-radius: 100px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-primary, #5768FE);
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
                background: var(--landing-primary, #5768FE);
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
                background: #6877ff;
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
                border-color: rgba(87, 104, 254, 0.3);
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
                background: rgba(87, 104, 254, 0.05);
                border-top: 1px solid rgba(87, 104, 254, 0.1);
                border-bottom: 1px solid rgba(87, 104, 254, 0.1);
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
                background: rgba(87, 104, 254, 0.15);
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
                color: var(--landing-primary, #5768FE);
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
        this.addEventListener('open-auth-modal', this._handleOpenAuthModal);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this.removeEventListener('open-auth-modal', this._handleOpenAuthModal);
    }

    _handleOpenAuthModal = () => {
        const authModal = this.shadowRoot?.querySelector('auth-modal');
        if (authModal) {
            authModal.open = true;
        }
    };

    render() {
        return html`
            <div class="page-container">
                <landing-header></landing-header>
                
                <section class="hero">
                    <div class="hero-icon">
                        <img src="/static/core/assets/service_logos/agents_logo.svg" alt="AI Studio" />
                    </div>
                    <span class="hero-badge">Конструктор AI-агентов</span>
                    <h1 class="hero-title">AI Studio</h1>
                    <p class="hero-description">
                        Создавайте умных помощников для вашего бизнеса без программирования. 
                        Визуальный конструктор позволяет собрать агента за несколько часов, 
                        а не месяцев разработки.
                    </p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        Попробовать бесплатно
                    </button>
                </section>
                
                <section class="features">
                    <div class="features-grid">
                        <div class="feature-card">
                            <div class="feature-icon">🎨</div>
                            <h3 class="feature-title">Визуальный редактор</h3>
                            <p class="feature-description">
                                Собирайте сценарии из готовых блоков. Не нужно писать код — 
                                просто соединяйте элементы на холсте.
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">💬</div>
                            <h3 class="feature-title">Telegram и WhatsApp</h3>
                            <p class="feature-description">
                                Запускайте агентов там, где ваши клиенты. Интеграция с мессенджерами 
                                за пару кликов.
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🔌</div>
                            <h3 class="feature-title">Готовые интеграции</h3>
                            <p class="feature-description">
                                CRM, базы знаний, внешние API — подключайте источники данных 
                                без технических сложностей.
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">📊</div>
                            <h3 class="feature-title">Аналитика диалогов</h3>
                            <p class="feature-description">
                                Отслеживайте эффективность агентов. Смотрите историю разговоров 
                                и улучшайте сценарии.
                            </p>
                        </div>
                    </div>
                </section>
                
                <section class="benefits">
                    <div class="benefits-container">
                        <h2 class="benefits-title">Почему предприниматели выбирают AI Studio</h2>
                        <div class="benefits-grid">
                            <div class="benefit-item">
                                <div class="benefit-icon">⏱️</div>
                                <div class="benefit-content">
                                    <h3>Запуск за часы</h3>
                                    <p>Первого агента можно запустить уже сегодня. Без найма разработчиков и месяцев ожидания.</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">💰</div>
                                <div class="benefit-content">
                                    <h3>Экономия на персонале</h3>
                                    <p>Один агент заменяет 2-3 менеджеров на типовых задачах: ответы на вопросы, сбор заявок, консультации.</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">🌙</div>
                                <div class="benefit-content">
                                    <h3>Работа 24/7</h3>
                                    <p>Агенты не спят, не болеют и не уходят в отпуск. Клиенты получают ответы в любое время.</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">📈</div>
                                <div class="benefit-content">
                                    <h3>Масштабирование</h3>
                                    <p>Обрабатывайте 10 или 10 000 обращений — стоимость агента не растет с объемом.</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">🎯</div>
                                <div class="benefit-content">
                                    <h3>Стабильное качество</h3>
                                    <p>Агент не устает и не ошибается. Каждый клиент получает одинаково хороший сервис.</p>
                                </div>
                            </div>
                            
                            <div class="benefit-item">
                                <div class="benefit-icon">🔧</div>
                                <div class="benefit-content">
                                    <h3>Полный контроль</h3>
                                    <p>Редактируйте сценарии в реальном времени. Изменения применяются мгновенно.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
                
                <section class="cta-section">
                    <h2 class="cta-title">Готовы автоматизировать общение с клиентами?</h2>
                    <p class="cta-subtitle">Создайте первого агента бесплатно и оцените результат</p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        Начать сейчас
                    </button>
                    <a href="/" class="back-link">← Вернуться на главную</a>
                </section>
                
                <landing-footer></landing-footer>
            </div>
            
            <auth-modal></auth-modal>
        `;
    }
}

customElements.define('product-agents-page', ProductAgentsPage);

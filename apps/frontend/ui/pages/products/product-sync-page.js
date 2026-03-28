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
                        <img src="/static/core/assets/service_logos/sync_logo.svg" alt="Sync" />
                    </div>
                    <span class="hero-badge">Чат и видеозвонки для команды</span>
                    <h1 class="hero-title">Sync</h1>
                    <p class="hero-description">
                        Каналы, личные переписки и треды в реальном времени. Видеозвонки с демонстрацией экрана,
                        контекст Git рядом с обсуждением и уведомления, если вы не в чате.
                    </p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        Открыть Sync
                    </button>
                </section>
                
                <section class="features">
                    <div class="features-grid">
                        <div class="feature-card">
                            <div class="feature-icon">💬</div>
                            <h3 class="feature-title">Каналы и треды</h3>
                            <p class="feature-description">
                                Командные каналы, личные сообщения и ветки обсуждений — история сохраняется,
                                новые сообщения приходят без перезагрузки страницы.
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">📹</div>
                            <h3 class="feature-title">Видеозвонки</h3>
                            <p class="feature-description">
                                Звонки из чата: камера, микрофон, демонстрация экрана. Гостевые ссылки для
                                подключения внешних участников.
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🔗</div>
                            <h3 class="feature-title">Git в контексте</h3>
                            <p class="feature-description">
                                Привязывайте обсуждения к репозиториям и веткам — команда видит, о чём
                                речь в коде.
                            </p>
                        </div>
                        
                        <div class="feature-card">
                            <div class="feature-icon">🔔</div>
                            <h3 class="feature-title">Уведомления</h3>
                            <p class="feature-description">
                                Если вас нет в открытом чате, платформа может напомнить о новом сообщении
                                или упоминании.
                            </p>
                        </div>
                    </div>
                </section>
                
                <section class="how-it-works">
                    <div class="how-it-works-container">
                        <h2 class="how-it-works-title">Как это работает</h2>
                        <div class="steps-grid">
                            <div class="step-item">
                                <div class="step-number">1</div>
                                <div class="step-content">
                                    <h3>Вход в компанию</h3>
                                    <p>После входа вы видите пространства и каналы своей компании — изоляция данных между организациями.</p>
                                </div>
                            </div>
                            
                            <div class="step-item">
                                <div class="step-number">2</div>
                                <div class="step-content">
                                    <h3>Выбор канала</h3>
                                    <p>Откройте общий канал или напишите коллеге в личку; внутри канала можно вести треды по темам.</p>
                                </div>
                            </div>
                            
                            <div class="step-item">
                                <div class="step-number">3</div>
                                <div class="step-content">
                                    <h3>Звонок при необходимости</h3>
                                    <p>Из чата запускается видеозвонок: участники комнаты подключаются, можно показать экран.</p>
                                </div>
                            </div>
                            
                            <div class="step-item">
                                <div class="step-number">4</div>
                                <div class="step-content">
                                    <h3>Ни одного пропущенного смысла</h3>
                                    <p>История переписки и вложения остаются в канале; при отсутствии в сети помогут уведомления.</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </section>
                
                <section class="benefits">
                    <h2 class="benefits-title">Зачем командам Sync</h2>
                    <div class="benefits-grid">
                        <div class="benefit-item">
                            <div class="benefit-icon">⚡</div>
                            <div class="benefit-content">
                                <h3>Один интерфейс</h3>
                                <p>Не нужно переключаться между мессенджером и таск-трекером для обсуждения кода и задач.</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">🛡️</div>
                            <div class="benefit-content">
                                <h3>Данные компании</h3>
                                <p>Переписка и файлы внутри контура вашей организации на платформе Humanitec.</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">👀</div>
                            <div class="benefit-content">
                                <h3>Онлайн и статус</h3>
                                <p>Видно, кто из коллег сейчас в сети, чтобы выбрать удобный момент для звонка.</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">🧩</div>
                            <div class="benefit-content">
                                <h3>Рядом с остальными сервисами</h3>
                                <p>Sync дополняет AI Studio, Knowledge Base и NetWorkle — единый вход с дашборда.</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">👤</div>
                            <div class="benefit-content">
                                <h3>Упоминания</h3>
                                <p>Отметьте коллегу в сообщении — он получит отдельное уведомление о важном контексте.</p>
                            </div>
                        </div>
                        
                        <div class="benefit-item">
                            <div class="benefit-icon">📎</div>
                            <div class="benefit-content">
                                <h3>Вложения</h3>
                                <p>Обмен файлами в сообщениях, чтобы договорённости и артефакты оставались в истории.</p>
                            </div>
                        </div>
                    </div>
                </section>
                
                <section class="cta-section">
                    <h2 class="cta-title">Подключите команду к Sync</h2>
                    <p class="cta-subtitle">Войдите под учётной записью компании — чат откроется с дашборда.</p>
                    <button class="cta-btn" @click=${this._handleOpenAuthModal}>
                        Войти и открыть
                    </button>
                    <a href="/" class="back-link">← Вернуться на главную</a>
                </section>
                
                <landing-footer></landing-footer>
            </div>
            
            <auth-modal></auth-modal>
        `;
    }
}

customElements.define('product-sync-page', ProductSyncPage);

/**
 * Landing Abilities - Возможности платформы
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingAbilities extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
                background: linear-gradient(180deg, #0F0F0F 0%, #1a1a2e 50%, #0F0F0F 100%);
            }
            
            .abilities-container {
                max-width: 1440px;
                margin: 0 auto;
            }
            
            .abilities-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 32px;
                font-weight: 500;
                color: var(--landing-secondary);
                margin: 0 0 60px 0;
                text-align: center;
            }
            
            .ability-item {
                display: flex;
                flex-direction: column;
                gap: 30px;
                margin-bottom: 80px;
            }
            
            .ability-item:last-child {
                margin-bottom: 0;
            }
            
            .ability-image {
                width: 100%;
                aspect-ratio: 4 / 3;
                background: radial-gradient(circle at center, rgba(87, 104, 254, 0.2), transparent);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 64px;
                order: -1;
            }
            
            .ability-content {
                flex: 1;
            }
            
            .ability-name {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 28px;
                font-weight: 500;
                color: var(--landing-primary);
                margin: 0 0 16px 0;
            }
            
            .ability-description {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.6;
                color: rgba(232, 232, 232, 0.8);
                margin: 0 0 20px 0;
            }
            
            .ability-features {
                list-style: none;
                padding: 0;
                margin: 0;
            }
            
            .ability-features li {
                font-family: 'Fira Sans', sans-serif;
                font-size: 14px;
                color: var(--landing-secondary);
                padding-left: 24px;
                position: relative;
                margin-bottom: 8px;
            }
            
            .ability-features li::before {
                content: '✓';
                position: absolute;
                left: 0;
                color: var(--landing-primary);
                font-weight: bold;
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 100px 40px;
                }
                
                .abilities-title {
                    font-size: 48px;
                    margin-bottom: 80px;
                }
                
                .ability-item {
                    flex-direction: row;
                    align-items: center;
                    gap: 60px;
                    margin-bottom: 100px;
                }
                
                .ability-item:nth-child(even) {
                    flex-direction: row-reverse;
                }
                
                .ability-image {
                    width: 45%;
                    order: 0;
                }
                
                .ability-name {
                    font-size: 36px;
                }
                
                .ability-description {
                    font-size: 18px;
                }
                
                .ability-features li {
                    font-size: 16px;
                }
            }
            
            @media (min-width: 1440px) {
                :host {
                    padding: 120px 80px;
                }
                
                .abilities-title {
                    font-size: 60px;
                    margin-bottom: 100px;
                }
                
                .ability-item {
                    gap: 80px;
                }
                
                .ability-name {
                    font-size: 44px;
                }
                
                .ability-description {
                    font-size: 20px;
                }
                
                .ability-features li {
                    font-size: 18px;
                }
            }
        `
    ];

    render() {
        return html`
            <div class="abilities-container">
                <h2 class="abilities-title">/ Возможности платформы</h2>
                
                <div class="ability-item">
                    <div class="ability-image">🚀</div>
                    <div class="ability-content">
                        <h3 class="ability-name">Запуск за часы, а не месяцы</h3>
                        <p class="ability-description">
                            Не тратьте время и деньги на разработку с нуля. Используйте готовые
                            сервисы: создавайте AI-агентов, общайтесь в Sync, управляйте контактами в NetWorkle,
                            храните документы в Knowledge Base. Всё уже настроено и работает.
                        </p>
                        <ul class="ability-features">
                            <li>Готовые решения для типовых задач</li>
                            <li>Запуск первого агента за 1 день</li>
                            <li>Не нужна команда разработчиков</li>
                        </ul>
                    </div>
                </div>
                
                <div class="ability-item">
                    <div class="ability-image">💰</div>
                    <div class="ability-content">
                        <h3 class="ability-name">Платите только за результат</h3>
                        <p class="ability-description">
                            Никаких скрытых платежей и абонентской платы. Начните с 50 рублей, 
                            платите только за то, что используете. Видите каждую копейку 
                            в детальной статистике расходов.
                        </p>
                        <ul class="ability-features">
                            <li>Старт от 50₽ без обязательств</li>
                            <li>Оплата только за использование</li>
                            <li>Полная прозрачность расходов</li>
                        </ul>
                    </div>
                </div>
                
                <div class="ability-item">
                    <div class="ability-image">📈</div>
                    <div class="ability-content">
                        <h3 class="ability-name">Масштаб без головной боли</h3>
                        <p class="ability-description">
                            Ваши агенты работают 24/7 без выходных, больничных и отпусков. 
                            Обрабатывают тысячи запросов одновременно. Обновляйте логику работы 
                            на лету, без остановки сервиса.
                        </p>
                        <ul class="ability-features">
                            <li>Работа 24/7 без перерывов</li>
                            <li>Обработка тысяч запросов в день</li>
                            <li>Обновления без простоя</li>
                        </ul>
                    </div>
                </div>
                
                <div class="ability-item">
                    <div class="ability-image">🔒</div>
                    <div class="ability-content">
                        <h3 class="ability-name">Ваши данные под контролем</h3>
                        <p class="ability-description">
                            Все данные хранятся в вашей базе, не передаются третьим лицам. 
                            Полная изоляция между компаниями. Интегрируйте с любыми 
                            вашими системами через API.
                        </p>
                        <ul class="ability-features">
                            <li>Данные только в вашей базе</li>
                            <li>Полная изоляция компаний</li>
                            <li>Интеграция с любыми системами</li>
                        </ul>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-abilities', LandingAbilities);


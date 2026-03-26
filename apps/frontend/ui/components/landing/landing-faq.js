/**
 * Landing FAQ - Вопросы и ответы с аккордеоном
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingFaq extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
            }
            
            .faq-container {
                max-width: 1000px;
                margin: 0 auto;
            }
            
            .faq-title {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 32px;
                font-weight: 500;
                color: var(--landing-secondary);
                margin: 0 0 60px 0;
                text-align: center;
            }
            
            .faq-list {
                display: flex;
                flex-direction: column;
                gap: 0;
            }
            
            .faq-item {
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                padding: 24px 0;
                cursor: pointer;
                transition: all 0.3s;
            }
            
            .faq-item:hover {
                background: rgba(87, 104, 254, 0.05);
            }
            
            .faq-question {
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 20px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 18px;
                font-weight: 500;
                color: var(--landing-secondary);
                margin: 0;
            }
            
            .faq-icon {
                flex-shrink: 0;
                width: 24px;
                height: 24px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: var(--landing-primary);
                transition: transform 0.3s;
                font-size: 20px;
            }
            
            .faq-item.open .faq-icon {
                transform: rotate(180deg);
            }
            
            .faq-answer {
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.3s ease-out, opacity 0.3s, padding 0.3s;
                opacity: 0;
                padding-top: 0;
            }
            
            .faq-item.open .faq-answer {
                max-height: 500px;
                opacity: 1;
                padding-top: 16px;
            }
            
            .faq-answer-text {
                font-family: 'Fira Sans', sans-serif;
                font-size: 16px;
                line-height: 1.7;
                color: rgba(232, 232, 232, 0.8);
                margin: 0;
            }
            
            @media (min-width: 768px) {
                :host {
                    padding: 100px 40px;
                }
                
                .faq-title {
                    font-size: 48px;
                    margin-bottom: 80px;
                }
                
                .faq-item {
                    padding: 32px 20px;
                }
                
                .faq-question {
                    font-size: 22px;
                }
                
                .faq-icon {
                    width: 28px;
                    height: 28px;
                    font-size: 24px;
                }
                
                .faq-answer-text {
                    font-size: 18px;
                }
            }
            
            @media (min-width: 1440px) {
                :host {
                    padding: 120px 80px;
                }
                
                .faq-title {
                    font-size: 60px;
                    margin-bottom: 100px;
                }
                
                .faq-item {
                    padding: 40px 30px;
                }
                
                .faq-question {
                    font-size: 24px;
                }
                
                .faq-answer-text {
                    font-size: 20px;
                }
            }
        `
    ];

    static properties = {
        faqItems: { type: Array }
    };

    constructor() {
        super();
        this.faqItems = [
            {
                id: 1,
                question: 'Что такое AI Studio и как создать своего агента?',
                answer: 'AI Studio — это визуальный конструктор AI-агентов без программирования. Вы выбираете задачу (поддержка клиентов, обработка заявок, консультации), настраиваете поведение агента через простой интерфейс, подключаете каналы (Telegram, WhatsApp, сайт) и запускаете. Агент сразу начинает работать 24/7, отвечая клиентам и выполняя задачи по вашим правилам.',
                open: true
            },
            {
                id: 2,
                question: 'Что такое Knowledge Base и зачем она нужна?',
                answer: 'Knowledge Base — это умная база знаний с семантическим поиском. Загрузите документы, инструкции, FAQ, прайсы — и система автоматически их проиндексирует. Ваши AI-агенты смогут находить точные ответы в этих документах и отвечать клиентам на основе актуальной информации. Больше не нужно вручную обучать агентов — достаточно обновить документ, и агент сразу знает новую информацию.',
                open: false
            },
            {
                id: 3,
                question: 'Какие документы можно загрузить в Knowledge Base?',
                answer: 'Поддерживаются все популярные форматы: PDF, Word, Excel, текстовые файлы, Markdown. Можно загружать инструкции для сотрудников, базы знаний, каталоги товаров, прайс-листы, регламенты, FAQ и любые другие документы. Система автоматически разбивает их на смысловые блоки и создает семантический индекс для быстрого поиска.',
                open: false
            },
            {
                id: 4,
                question: 'Что такое NetWorkle и чем он отличается от обычной CRM?',
                answer: 'NetWorkle — это умная записная книжка, которая превращает любые данные в связанную базу с поиском. В отличие от CRM, здесь нет жестких форм и полей. Вы создаете записи в свободной форме (контакты, встречи, заметки, сделки), а система сама находит связи между ними и строит граф отношений. Можно искать по смыслу: "с кем я встречался на прошлой неделе" или "контакты из сферы IT".',
                open: false
            },
            {
                id: 5,
                question: 'Как NetWorkle помогает в работе с клиентами?',
                answer: 'NetWorkle автоматически связывает все данные: контакт клиента, историю встреч, заметки, сделки, звонки. Вы видите полную картину отношений с каждым клиентом. Семантический поиск позволяет быстро находить нужную информацию: "что мы обсуждали с Иваном в декабре" или "клиенты, которые интересовались продуктом X". Никакой ручной работы по связыванию данных.',
                open: false
            },
            {
                id: 6,
                question: 'Можно ли использовать Knowledge Base и NetWorkle вместе с AI-агентами?',
                answer: 'Да, именно так они работают лучше всего. AI-агент может искать ответы в Knowledge Base (документы, инструкции) и использовать данные из NetWorkle (информация о клиентах, история общения). Например, агент поддержки находит ответ в базе знаний и сразу видит историю обращений клиента. Всё работает как единая система.',
                open: false
            },
            {
                id: 9,
                question: 'Что такое Sync и зачем он команде?',
                answer: 'Sync — это корпоративный чат Humanitec: каналы, личные сообщения, треды и видеозвонки с демонстрацией экрана. Рядом с обсуждением можно держать контекст Git. Данные изолированы по компании, уведомления помогают не пропустить важное, если вы не в чате.',
                open: false
            },
            {
                id: 10,
                question: 'Чем Sync отличается от обычного мессенджера?',
                answer: 'Sync встроен в платформу: один вход с дашборда, те же пользователи и компания, что в AI Studio, Knowledge Base и NetWorkle. Есть интеграция с репозиториями для инженерных команд, гостевые ссылки на звонки и политика доступа в рамках вашей организации — не смешанный личный и рабочий контур.',
                open: false
            },
            {
                id: 7,
                question: 'Насколько безопасно хранить данные на платформе?',
                answer: 'Безопасность — наш приоритет. Все данные шифруются при передаче и хранении. Доступна как облачная версия, так и установка на ваши сервера (on-premise) для полного контроля. Разграничение доступа позволяет настроить, кто какие данные видит. Регулярные бэкапы защищают от потери информации.',
                open: false
            },
            {
                id: 8,
                question: 'Нужны ли технические знания для работы с платформой?',
                answer: 'Нет. Все сервисы имеют простой визуальный интерфейс. Создание агента, загрузка документов в базу знаний, ведение записей в NetWorkle, переписка и звонки в Sync — всё делается через понятные экраны без программирования. Для сложных задач есть тариф с поддержкой, где наша команда поможет настроить всё под ваши процессы.',
                open: false
            }
        ];
    }

    _toggleFaq(id) {
        this.faqItems = this.faqItems.map(item => ({
            ...item,
            open: item.id === id ? !item.open : false
        }));
    }

    render() {
        return html`
            <div class="faq-container">
                <h2 class="faq-title">/ Вопросы & ответы</h2>
                
                <div class="faq-list">
                    ${this.faqItems.map(item => html`
                        <div 
                            class=${classMap({ 'faq-item': true, open: item.open })}
                            @click=${() => this._toggleFaq(item.id)}
                        >
                            <div class="faq-question">
                                <span>${item.question}</span>
                                <div class="faq-icon">▼</div>
                            </div>
                            <div class="faq-answer">
                                <p class="faq-answer-text">${item.answer}</p>
                            </div>
                        </div>
                    `)}
                </div>
            </div>
        `;
    }
}

customElements.define('landing-faq', LandingFaq);


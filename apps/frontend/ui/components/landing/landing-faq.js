/**
 * Landing FAQ - Вопросы и ответы с аккордеоном
 */
import { html, css } from 'lit';
import { classMap } from 'lit/directives/class-map.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const FAQ_SLOT_COUNT = 10;

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
        openIndex: { type: Number }
    };

    constructor() {
        super();
        this.openIndex = 0;
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

    _toggleFaq(index) {
        this.openIndex = this.openIndex === index ? -1 : index;
    }

    render() {
        const t = (key) => this.i18n.t(key, {}, 'landing');
        const slots = Array.from({ length: FAQ_SLOT_COUNT }, (_, i) => i + 1);
        return html`
            <div class="faq-container">
                <h2 class="faq-title">${t('faq.tag')}</h2>
                
                <div class="faq-list">
                    ${slots.map((slot) => {
                        const q = t(`faq.slot${slot}_q`);
                        const a = t(`faq.slot${slot}_a`);
                        const idx = slot - 1;
                        const open = this.openIndex === idx;
                        return html`
                        <div 
                            class=${classMap({ 'faq-item': true, open })}
                            @click=${() => this._toggleFaq(idx)}
                        >
                            <div class="faq-question">
                                <span>${q}</span>
                                <div class="faq-icon">▼</div>
                            </div>
                            <div class="faq-answer">
                                <p class="faq-answer-text">${a}</p>
                            </div>
                        </div>
                    `;
                    })}
                </div>
            </div>
        `;
    }
}

customElements.define('landing-faq', LandingFaq);

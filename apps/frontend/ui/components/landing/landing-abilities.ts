/**
 * Возможности лендинга — возможности платформы
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import {
    landFlowsEditorUrl,
    landRagSearchUrl,
    landCrmGraphUrl,
    landSyncChatUrl,
    landOfficeEditorUrl,
    landOfficeDocumentsUrl,
    landShopPizzaStorefrontUrl,
    landWorktrackerBoardUrl,
} from '../../_helpers/land-product-images.js';

export class LandingAbilities extends PlatformElement {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
                background: var(--bg-gradient);
            }
            
            .abilities-container {
                max-width: 1440px;
                margin: 0 auto;
            }
            
            .abilities-title {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 32px;
                font-weight: 500;
                color: var(--text-secondary);
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
                aspect-ratio: 16 / 9;
                background: var(--glass-bg-medium);
                border: 1px solid var(--glass-border-medium);
                border-radius: 20px;
                overflow: hidden;
                order: -1;
                box-shadow: var(--glass-shadow-strong);
            }

            .ability-image img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                object-position: top center;
                display: block;
            }

            .ability-images-stack {
                display: flex;
                flex-direction: column;
                gap: 20px;
                width: 100%;
                order: -1;
            }

            .ability-images-stack .ability-image {
                order: 0;
                width: 100%;
            }
            
            .ability-content {
                flex: 1;
            }
            
            .ability-name {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 28px;
                font-weight: 500;
                color: var(--marketing-product-accent);
                margin: 0 0 16px 0;
            }
            
            .ability-description {
                font-family: var(--font-sans);
                font-size: 16px;
                line-height: 1.6;
                color: var(--text-secondary);
                margin: 0 0 20px 0;
            }
            
            .ability-features {
                list-style: none;
                padding: 0;
                margin: 0;
            }
            
            .ability-features li {
                font-family: var(--font-sans);
                font-size: 14px;
                color: var(--text-secondary);
                padding-left: 24px;
                position: relative;
                margin-bottom: 8px;
            }
            
            .ability-features li::before {
                content: '✓';
                position: absolute;
                left: 0;
                color: var(--marketing-product-accent);
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

                .ability-images-stack {
                    width: 45%;
                    order: 0;
                    flex-shrink: 0;
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

            /* Pin-хореография: секция прилипает (200vh), лента слайдов едет
               горизонтально на --cosmic-section-t. Сдвиг ограничен min(0,·),
               чтобы короткая лента не уезжала вправо. */
            @media (prefers-reduced-motion: no-preference) {
                :host {
                    height: 100vh;
                    padding: 0;
                    overflow: clip;
                }

                .abilities-container {
                    max-width: none;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    gap: clamp(20px, 4vh, 48px);
                }

                .abilities-title {
                    margin: 0;
                    padding-top: clamp(64px, 10vh, 110px);
                }

                .abilities-track {
                    display: flex;
                    align-items: center;
                    gap: clamp(32px, 6vw, 96px);
                    padding: 0 clamp(20px, 10vw, 160px);
                    box-sizing: border-box;
                    /* translate % считается от ширины самого трека —
                       max-content даёт полную ширину ленты. */
                    width: max-content;
                    min-height: 0;
                    will-change: transform;
                    transform: translate3d(
                        min(0px, calc(var(--cosmic-section-t, 0) * (100vw - 100%))),
                        0,
                        0
                    );
                }

                .ability-item {
                    flex: 0 0 auto;
                    width: min(78vw, 960px);
                    margin: 0;
                }

                @media (min-width: 768px) {
                    .ability-item {
                        flex-direction: row;
                        align-items: center;
                    }
                }

                @media (max-width: 767px) {
                    .ability-item {
                        width: 84vw;
                    }
                    .abilities-title {
                        font-size: 26px;
                    }
                }
            }
        `
    ];

    constructor() {
        super();
        this._localeSel = this.select((s) => s.i18n.locale);
    }
    private _localeSel: SelectController<any>;


    override connectedCallback(): void {
        super.connectedCallback();
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
    }

    override render(): TemplateResult {
        const t = (key: string) => (this.t(key) || key);
        return html`
            <div class="abilities-container">
                <h2 class="abilities-title">${t('features.tag')}</h2>
                <div class="abilities-track">
                <div class="ability-item">
                    <div class="ability-image">
                        <img
                            src=${landFlowsEditorUrl}
                            alt=${t('features.ability_alt_flows')}
                            width="1200"
                            height="675"
                            loading="lazy"
                            decoding="async"
                        />
                    </div>
                    <div class="ability-content">
                        <h3 class="ability-name">${t('features.feature1_title')}</h3>
                        <p class="ability-description">
                            ${t('features.feature1_description')}
                        </p>
                        <ul class="ability-features">
                            <li>${t('features.feature1_li1')}</li>
                            <li>${t('features.feature1_li2')}</li>
                            <li>${t('features.feature1_li3')}</li>
                        </ul>
                    </div>
                </div>
                
                <div class="ability-item">
                    <div class="ability-image">
                        <img
                            src=${landRagSearchUrl}
                            alt=${t('features.ability_alt_kb')}
                            width="1200"
                            height="675"
                            loading="lazy"
                            decoding="async"
                        />
                    </div>
                    <div class="ability-content">
                        <h3 class="ability-name">${t('features.feature2_title')}</h3>
                        <p class="ability-description">
                            ${t('features.feature2_description')}
                        </p>
                        <ul class="ability-features">
                            <li>${t('features.feature2_li1')}</li>
                            <li>${t('features.feature2_li2')}</li>
                            <li>${t('features.feature2_li3')}</li>
                        </ul>
                    </div>
                </div>
                
                <div class="ability-item">
                    <div class="ability-image">
                        <img
                            src=${landCrmGraphUrl}
                            alt=${t('features.ability_alt_networkle')}
                            width="1200"
                            height="675"
                            loading="lazy"
                            decoding="async"
                        />
                    </div>
                    <div class="ability-content">
                        <h3 class="ability-name">${t('features.feature3_title')}</h3>
                        <p class="ability-description">
                            ${t('features.feature3_description')}
                        </p>
                        <ul class="ability-features">
                            <li>${t('features.feature3_li1')}</li>
                            <li>${t('features.feature3_li2')}</li>
                            <li>${t('features.feature3_li3')}</li>
                        </ul>
                    </div>
                </div>
                
                <div class="ability-item">
                    <div class="ability-image">
                        <img
                            src=${landSyncChatUrl}
                            alt=${t('features.ability_alt_sync')}
                            width="1200"
                            height="675"
                            loading="lazy"
                            decoding="async"
                        />
                    </div>
                    <div class="ability-content">
                        <h3 class="ability-name">${t('features.feature4_title')}</h3>
                        <p class="ability-description">
                            ${t('features.feature4_description')}
                        </p>
                        <ul class="ability-features">
                            <li>${t('features.feature4_li1')}</li>
                            <li>${t('features.feature4_li2')}</li>
                            <li>${t('features.feature4_li3')}</li>
                        </ul>
                    </div>
                </div>
                
                <div class="ability-item">
                    <div class="ability-images-stack">
                        <div class="ability-image">
                            <img
                                src=${landOfficeEditorUrl}
                                alt=${t('features.ability_alt_documents')}
                                width="1200"
                                height="673"
                                loading="lazy"
                                decoding="async"
                            />
                        </div>
                        <div class="ability-image">
                            <img
                                src=${landOfficeDocumentsUrl}
                                alt=${t('features.ability_alt_documents_2')}
                                width="1200"
                                height="673"
                                loading="lazy"
                                decoding="async"
                            />
                        </div>
                    </div>
                    <div class="ability-content">
                        <h3 class="ability-name">${t('features.feature5_title')}</h3>
                        <p class="ability-description">
                            ${t('features.feature5_description')}
                        </p>
                        <ul class="ability-features">
                            <li>${t('features.feature5_li1')}</li>
                            <li>${t('features.feature5_li2')}</li>
                            <li>${t('features.feature5_li3')}</li>
                        </ul>
                    </div>
                </div>

                <div class="ability-item">
                    <div class="ability-image">
                        <img
                            src=${landShopPizzaStorefrontUrl}
                            alt=${t('features.ability_alt_shop')}
                            width="1200"
                            height="675"
                            loading="lazy"
                            decoding="async"
                        />
                    </div>
                    <div class="ability-content">
                        <h3 class="ability-name">${t('features.feature6_title')}</h3>
                        <p class="ability-description">
                            ${t('features.feature6_description')}
                        </p>
                        <ul class="ability-features">
                            <li>${t('features.feature6_li1')}</li>
                            <li>${t('features.feature6_li2')}</li>
                            <li>${t('features.feature6_li3')}</li>
                        </ul>
                    </div>
                </div>

                <div class="ability-item">
                    <div class="ability-image">
                        <img
                            src=${landWorktrackerBoardUrl}
                            alt=${t('features.ability_alt_worktracker')}
                            width="1200"
                            height="675"
                            loading="lazy"
                            decoding="async"
                        />
                    </div>
                    <div class="ability-content">
                        <h3 class="ability-name">${t('features.feature7_title')}</h3>
                        <p class="ability-description">
                            ${t('features.feature7_description')}
                        </p>
                        <ul class="ability-features">
                            <li>${t('features.feature7_li1')}</li>
                            <li>${t('features.feature7_li2')}</li>
                            <li>${t('features.feature7_li3')}</li>
                        </ul>
                    </div>
                </div>
                </div>
            </div>
        `;
    }
}

customElements.define('landing-abilities', LandingAbilities);

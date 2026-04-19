/**
 * Landing Abilities - Возможности платформы
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import {
    landFlowsAbilityUrl,
    landRagAbilityUrl,
    landNetworkleAbilityUrl,
    landSyncAbilityUrl,
    landDocumentsHeroUrl,
    landDocumentsShot2Url,
} from '../../utils/land-product-images.js';

export class LandingAbilities extends PlatformElement {
    static i18nNamespace = 'landing';

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
                aspect-ratio: 16 / 9;
                background: rgba(20, 22, 34, 0.6);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                overflow: hidden;
                order: -1;
                box-shadow: 0 20px 56px rgba(0, 0, 0, 0.35);
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
        `
    ];

    connectedCallback() {
        super.connectedCallback();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
    }

    render() {
        const t = (key) => (this.t(key) || key);
        const locale = (this.bus.getState().i18n.locale || 'ru');
        const flowsSrc = landFlowsAbilityUrl(locale);
        return html`
            <div class="abilities-container">
                <h2 class="abilities-title">${t('features.tag')}</h2>
                
                <div class="ability-item">
                    <div class="ability-image">
                        <img
                            src=${flowsSrc}
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
                            src=${landRagAbilityUrl}
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
                            src=${landNetworkleAbilityUrl}
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
                            src=${landSyncAbilityUrl}
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
                                src=${landDocumentsHeroUrl}
                                alt=${t('features.ability_alt_documents')}
                                width="1200"
                                height="673"
                                loading="lazy"
                                decoding="async"
                            />
                        </div>
                        <div class="ability-image">
                            <img
                                src=${landDocumentsShot2Url}
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
            </div>
        `;
    }
}

customElements.define('landing-abilities', LandingAbilities);


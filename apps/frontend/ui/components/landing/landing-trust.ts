/**
 * Блок доверия: 152-ФЗ, развёртывание, оплата для юрлиц.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

export class LandingTrust extends PlatformElement {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 72px 20px 40px;
                background: var(--landing-bg, #0f0f0f);
            }
            .wrap {
                max-width: 1200px;
                margin: 0 auto;
            }
            h2 {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: clamp(28px, 4vw, 44px);
                font-weight: 500;
                color: var(--landing-secondary, #e8e8e8);
                text-align: center;
                margin: 0 0 48px;
            }
            .grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 24px;
            }
            @media (min-width: 900px) {
                .grid {
                    grid-template-columns: repeat(3, 1fr);
                }
            }
            article {
                padding: 28px 24px;
                border-radius: 20px;
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.12));
                background: var(--landing-panel-bg, rgba(255, 255, 255, 0.03));
                backdrop-filter: blur(12px);
            }
            h3 {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 20px;
                margin: 0 0 12px;
                color: var(--landing-primary, #5768fe);
            }
            p {
                margin: 0;
                font-family: var(--font-sans);
                font-size: 15px;
                line-height: 1.55;
                color: var(--landing-text-soft, rgba(232, 232, 232, 0.85));
            }
        `,
    ];

    override render(): TemplateResult {
        const t = (key: string) => this.t(key);
        return html`
            <section class="wrap" aria-labelledby="landing-trust-heading">
                <h2 id="landing-trust-heading">${t('trust.title')}</h2>
                <div class="grid">
                    <article>
                        <h3>${t('trust.card_pd152_title')}</h3>
                        <p>${t('trust.card_pd152_text')}</p>
                    </article>
                    <article>
                        <h3>${t('trust.card_deploy_title')}</h3>
                        <p>${t('trust.card_deploy_text')}</p>
                    </article>
                    <article>
                        <h3>${t('trust.card_billing_title')}</h3>
                        <p>${t('trust.card_billing_text')}</p>
                    </article>
                </div>
            </section>
        `;
    }
}

customElements.define('landing-trust', LandingTrust);

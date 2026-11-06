/**
 * Карточки бизнес-сценариев с метриками.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

export class LandingCases extends PlatformElement {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: 80px 20px;
            }
            .wrap {
                max-width: 1200px;
                margin: 0 auto;
            }
            h2 {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: clamp(26px, 3.5vw, 40px);
                margin: 0 0 12px;
                color: var(--text-secondary);
                text-align: center;
            }
            .sub {
                text-align: center;
                margin: 0 0 48px;
                font-size: 16px;
                color: var(--text-secondary);
            }
            .grid {
                display: grid;
                grid-template-columns: 1fr;
                gap: 20px;
            }
            @media (min-width: 768px) {
                .grid {
                    grid-template-columns: repeat(2, 1fr);
                }
            }
            article {
                padding: 24px;
                border-radius: 20px;
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-bg-subtle);
            }
            .metric {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 14px;
                font-weight: 600;
                color: var(--marketing-product-accent);
                margin-bottom: 10px;
            }
            h3 {
                font-family: var(--font-sans); letter-spacing: var(--tracking-tight);
                font-size: 20px;
                margin: 0 0 10px;
                color: var(--text-secondary);
            }
            p {
                margin: 0;
                font-size: 15px;
                line-height: 1.55;
                color: var(--text-secondary);
            }

            /* Pin-хореография: карточки едут горизонтально на
               --cosmic-section-t, пока секция прилипла (200vh). */
            @media (prefers-reduced-motion: no-preference) {
                :host {
                    height: 100vh;
                    padding: 0;
                    overflow: clip;
                }
                .wrap {
                    max-width: none;
                    height: 100%;
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    gap: clamp(24px, 4vh, 40px);
                }
                h2 {
                    margin: 0;
                    padding-top: clamp(64px, 10vh, 110px);
                }
                .sub {
                    margin: 0;
                }
                .grid {
                    display: flex;
                    align-items: stretch;
                    gap: clamp(16px, 2.5vw, 28px);
                    padding: 0 clamp(20px, 10vw, 160px);
                    box-sizing: border-box;
                    /* translate % считается от ширины трека —
                       max-content даёт полную ширину ленты. */
                    width: max-content;
                    will-change: transform;
                    transform: translate3d(
                        min(0px, calc(var(--cosmic-section-t, 0) * (100vw - 100%))),
                        0,
                        0
                    );
                }
                article {
                    flex: 0 0 min(400px, 78vw);
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    min-height: clamp(220px, 32vh, 300px);
                }
            }
        `,
    ];

    override render(): TemplateResult {
        const t = (key: string) => this.t(key);
        const blocks = [
            {
                title: 'cases.case1_title',
                metric: 'cases.case1_metric',
                text: 'cases.case1_text',
            },
            {
                title: 'cases.case2_title',
                metric: 'cases.case2_metric',
                text: 'cases.case2_text',
            },
            {
                title: 'cases.case3_title',
                metric: 'cases.case3_metric',
                text: 'cases.case3_text',
            },
            {
                title: 'cases.case4_title',
                metric: 'cases.case4_metric',
                text: 'cases.case4_text',
            },
        ];
        return html`
            <section class="wrap">
                <h2>${t('cases.title')}</h2>
                <p class="sub">${t('cases.subtitle')}</p>
                <div class="grid">
                    ${blocks.map((b) => html`
                            <article>
                                <div class="metric">${t(b.metric)}</div>
                                <h3>${t(b.title)}</h3>
                                <p>${t(b.text)}</p>
                            </article>
                        `,
                    )}
                </div>
            </section>
        `;
    }
}

customElements.define('landing-cases', LandingCases);

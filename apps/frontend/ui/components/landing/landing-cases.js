/**
 * Карточки бизнес-сценариев с метриками.
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class LandingCases extends PlatformElement {
    static i18nNamespace = 'landing';

    static styles = [
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
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(26px, 3.5vw, 40px);
                margin: 0 0 12px;
                color: var(--landing-secondary, #e8e8e8);
                text-align: center;
            }
            .sub {
                text-align: center;
                margin: 0 0 48px;
                font-size: 16px;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.72));
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
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.1));
                background: var(--landing-panel-bg, rgba(255, 255, 255, 0.04));
            }
            .metric {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 14px;
                font-weight: 600;
                color: var(--landing-primary, #5768fe);
                margin-bottom: 10px;
            }
            h3 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 20px;
                margin: 0 0 10px;
                color: var(--landing-secondary, #e8e8e8);
            }
            p {
                margin: 0;
                font-size: 15px;
                line-height: 1.55;
                color: var(--landing-text-soft, rgba(232, 232, 232, 0.82));
            }
        `,
    ];

    render() {
        const t = (key) => this.t(key);
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
                    ${blocks.map(
                        (b) => html`
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

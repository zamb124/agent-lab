/**
 * Публичная страница roadmap.
 */
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class RoadmapPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                min-height: var(--app-vh, 100vh);
                background: var(--landing-bg, #0f0f0f);
                color: var(--landing-text, #fff);
            }
            .wrap {
                max-width: 880px;
                margin: 0 auto;
                padding: 100px 20px 80px;
                box-sizing: border-box;
            }
            h1 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: clamp(32px, 5vw, 48px);
                margin: 0 0 12px;
                color: var(--landing-secondary, #e8e8e8);
            }
            .sub {
                margin: 0 0 36px;
                font-size: 17px;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.72));
            }
            section {
                margin-bottom: 32px;
                padding: 22px 24px;
                border-radius: 16px;
                border: 1px solid var(--landing-panel-border, rgba(255, 255, 255, 0.12));
                background: var(--landing-panel-bg, rgba(255, 255, 255, 0.03));
            }
            h2 {
                font-family: 'Fira Sans Condensed', sans-serif;
                font-size: 22px;
                margin: 0 0 14px;
                color: var(--landing-secondary, #e8e8e8);
            }
            ul {
                margin: 0;
                padding-left: 20px;
                font-family: 'Fira Sans', sans-serif;
                font-size: 15px;
                line-height: 1.55;
                color: var(--landing-text-soft, rgba(232, 232, 232, 0.82));
            }
            li {
                margin-bottom: 8px;
            }
            .note {
                margin-top: 24px;
                font-size: 14px;
                color: var(--landing-text-subtle, rgba(232, 232, 232, 0.62));
                line-height: 1.55;
            }
        `,
    ];

    connectedCallback() {
        super.connectedCallback();
        queueMicrotask(() => this._syncMeta());
    }

    _syncMeta() {
        if (typeof window === 'undefined') return;
        const origin = window.location.origin;
        applyPublicDocumentMeta({
            title: this.t('meta.roadmap_title'),
            description: this.t('meta.roadmap_description'),
            canonicalUrl: `${origin}/roadmap`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    render() {
        return html`
            <landing-header></landing-header>
            <div class="wrap">
                <h1>${this.t('roadmap_page.title')}</h1>
                <p class="sub">${this.t('roadmap_page.subtitle')}</p>
                <section>
                    <h2>${this.t('roadmap_page.q1_title')}</h2>
                    <ul>
                        <li>${this.t('roadmap_page.q1_li1')}</li>
                        <li>${this.t('roadmap_page.q1_li2')}</li>
                        <li>${this.t('roadmap_page.q1_li3')}</li>
                    </ul>
                </section>
                <section>
                    <h2>${this.t('roadmap_page.q2_title')}</h2>
                    <ul>
                        <li>${this.t('roadmap_page.q2_li1')}</li>
                        <li>${this.t('roadmap_page.q2_li2')}</li>
                        <li>${this.t('roadmap_page.q2_li3')}</li>
                    </ul>
                </section>
                <p class="note">${this.t('roadmap_page.note')}</p>
            </div>
            <landing-footer></landing-footer>
        `;
    }
}

customElements.define('roadmap-page', RoadmapPage);

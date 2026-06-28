/**
 * Публичная страница roadmap.
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { applyPublicDocumentMeta } from '../utils/public-document-meta.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';

export class RoadmapPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static styles = [PlatformPage.styles, ...marketingPublicContentPageStyles];

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
            <div class="marketing-page-container">
                <div class="marketing-content">
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title">${this.t('roadmap_page.title')}</h1>
                        <p class="marketing-content-lede">${this.t('roadmap_page.subtitle')}</p>
                    </header>
                    <div class="marketing-content-stack">
                        <section class="marketing-content-panel glass-medium">
                            <h2 class="marketing-content-card-title">${this.t('roadmap_page.q1_title')}</h2>
                            <ul class="marketing-prose">
                                <li>${this.t('roadmap_page.q1_li1')}</li>
                                <li>${this.t('roadmap_page.q1_li2')}</li>
                                <li>${this.t('roadmap_page.q1_li3')}</li>
                            </ul>
                        </section>
                        <section class="marketing-content-panel glass-medium">
                            <h2 class="marketing-content-card-title">${this.t('roadmap_page.q2_title')}</h2>
                            <ul class="marketing-prose">
                                <li>${this.t('roadmap_page.q2_li1')}</li>
                                <li>${this.t('roadmap_page.q2_li2')}</li>
                                <li>${this.t('roadmap_page.q2_li3')}</li>
                            </ul>
                        </section>
                    </div>
                    <p class="marketing-text-muted">${this.t('roadmap_page.note')}</p>
                </div>
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

customElements.define('roadmap-page', RoadmapPage);

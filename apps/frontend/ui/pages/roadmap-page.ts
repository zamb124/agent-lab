/**
 * Публичная страница roadmap.
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { applyPublicDocumentMeta } from '../_helpers/public-document-meta.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';
import '../components/cosmic/cosmic-scope.js';
import '../components/cosmic/scramble-text.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

export class RoadmapPage extends PlatformPage {
    static i18nNamespace = 'landing';

    static override styles: CSSResultGroup = [PlatformPage.styles, ...marketingPublicContentPageStyles];

    override connectedCallback(): void {
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

    override render(): TemplateResult {
        return html`
            <cosmic-scope class="marketing-page-container">
                <landing-header></landing-header>
                <section data-cosmic-chapter data-cosmic-hue="258" data-cosmic-label=${this.t('roadmap_page.title')}>
                <div class="marketing-content">
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title"><scramble-text .text=${this.t('roadmap_page.title')}></scramble-text></h1>
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
                </section>
                <landing-footer></landing-footer>
            </cosmic-scope>
        `;
    }
}

customElements.define('roadmap-page', RoadmapPage);

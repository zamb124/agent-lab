/**
 * Публичная страница «О компании».
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { marketingPublicContentPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import { applyPublicDocumentMeta } from '../_helpers/public-document-meta.js';
import { FrontendLeadFormModal } from '../modals/lead-form-modal.js';
import '@platform/lib/components/platform-button.js';
import '../components/landing/landing-header.js';
import '../components/landing/landing-footer.js';
import '../components/cosmic/cosmic-scope.js';
import '../components/cosmic/scramble-text.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

export class AboutPage extends PlatformPage {
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
            title: this.t('meta.about_title'),
            description: this.t('meta.about_description'),
            canonicalUrl: `${origin}/about`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    override render(): TemplateResult {
        return html`
            <cosmic-scope class="marketing-page-container">
                <landing-header></landing-header>
                <section data-cosmic-chapter data-cosmic-hue="222" data-cosmic-label=${this.t('about_page.title')}>
                <div class="marketing-content">
                    <header class="marketing-content-hero">
                        <h1 class="marketing-content-title"><scramble-text .text=${this.t('about_page.title')}></scramble-text></h1>
                        <p class="marketing-content-lede">${this.t('about_page.lead')}</p>
                    </header>
                    <div class="marketing-prose">
                        <h2>${this.t('about_page.mission_title')}</h2>
                        <p>${this.t('about_page.mission_text')}</p>
                        <h2>${this.t('about_page.trust_title')}</h2>
                        <p>${this.t('about_page.trust_text')}</p>
                        <h2>${this.t('about_page.cta_title')}</h2>
                    </div>
                    <div class="marketing-content-cta">
                        <platform-button variant="primary" @click=${() => this.openModal(FrontendLeadFormModal)}>
                            ${this.t('about_page.cta_button')}
                        </platform-button>
                    </div>
                </div>
                </section>
                <landing-footer></landing-footer>
            </cosmic-scope>
        `;
    }
}

customElements.define('about-page', AboutPage);

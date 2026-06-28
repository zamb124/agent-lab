/**
 * Базовая страница продуктового лендинга — core Design System.
 */
import { html } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { buildServiceEntryUrl } from '@platform/lib/utils/build-service-entry-url.js';
import { marketingProductPageStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import '@platform/lib/components/platform-button.js';
import '../landing/landing-header.js';
import '../landing/landing-footer.js';
import { applyPublicDocumentMeta } from '../../utils/public-document-meta.js';

/** @typedef {'hero' | 'gallery' | 'features' | 'steps' | 'benefits' | 'use-cases' | 'faq' | 'cta'} ProductLandingSection */

/**
 * @typedef {Object} ProductLandingHeroImage
 * @property {'static' | 'locale'} kind
 * @property {string | ((locale: 'ru' | 'en') => string)} value
 */

/**
 * @typedef {Object} ProductLandingGalleryImage
 * @property {string} src
 * @property {string} altKey
 */

export class ProductLandingPage extends PlatformPage {
    static i18nNamespace = 'frontend_products';

    /** @type {string} */
    static productKey = '';

    /** @type {ProductLandingSection[]} */
    static sections = [];

    /** @type {'flows' | 'crm' | 'rag' | 'sync' | 'documents' | 'frontend'} */
    static serviceEntry = 'flows';

    /** @type {'accent' | 'success' | 'accent-secondary'} */
    static productAccent = 'accent';

    /** @type {ProductLandingHeroImage} */
    static heroImage = { kind: 'static', value: '' };

    /** @type {ProductLandingGalleryImage[]} */
    static galleryImages = [];

    static styles = [PlatformPage.styles, ...marketingProductPageStyles];

    constructor() {
        super();
        this._authStatusSel = this.select((s) => s.auth.status);
        this._localeSel = this.select((s) => s.i18n.locale);
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.constructor.productAccent !== 'accent') {
            this.setAttribute('product-accent', this.constructor.productAccent);
        }
        queueMicrotask(() => this._syncProductDocumentMeta());
    }

    _translationKey(relativeKey) {
        return `${this.constructor.productKey}.${relativeKey}`;
    }

    _t(relativeKey) {
        return this.t(this._translationKey(relativeKey));
    }

    _resolveHeroImageSrc() {
        const heroImage = this.constructor.heroImage;
        const locale = this._localeSel.value;
        if (locale !== 'ru' && locale !== 'en') {
            throw new Error(`${this.tagName.toLowerCase()}: i18n.locale must be ru or en`);
        }
        if (heroImage.kind === 'locale') {
            if (typeof heroImage.value !== 'function') {
                throw new Error(`${this.tagName.toLowerCase()}: locale hero image requires resolver function`);
            }
            return heroImage.value(locale);
        }
        if (typeof heroImage.value !== 'string' || !heroImage.value) {
            throw new Error(`${this.tagName.toLowerCase()}: static hero image src is required`);
        }
        return heroImage.value;
    }

    _syncProductDocumentMeta() {
        if (typeof window === 'undefined') return;
        const productKey = this.constructor.productKey;
        if (!productKey) {
            throw new Error(`${this.tagName.toLowerCase()}: productKey is required`);
        }
        const origin = window.location.origin;
        applyPublicDocumentMeta({
            title: this._t('meta_title'),
            description: this._t('meta_description'),
            canonicalUrl: `${origin}/products/${productKey}`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    _handleProductCtaClick = () => {
        const serviceEntry = this.constructor.serviceEntry;
        if (this._authStatusSel.value === 'authenticated') {
            window.location.href = buildServiceEntryUrl(serviceEntry);
            return;
        }
        this.openModal('auth.login', { returnPath: buildServiceEntryUrl(serviceEntry) });
    };

    _renderHero() {
        const heroSrc = this._resolveHeroImageSrc();
        return html`
            <section class="marketing-hero">
                <span class="marketing-hero-badge">${this._t('hero_badge')}</span>
                <h1 class="marketing-hero-title">${this._t('hero_title')}</h1>
                <div class="marketing-hero-shot">
                    <img
                        src=${heroSrc}
                        alt=${this._t('hero_visual_alt')}
                        width="1200"
                        height="675"
                        loading="eager"
                        decoding="async"
                    />
                </div>
                <p class="marketing-hero-description">${this._t('hero_description')}</p>
                <div class="marketing-hero-cta">
                    <platform-button variant="primary" @click=${this._handleProductCtaClick}>
                        ${this._t('cta_try')}
                    </platform-button>
                </div>
            </section>
        `;
    }

    _renderGallery() {
        const galleryImages = this.constructor.galleryImages;
        if (galleryImages.length === 0) {
            return html``;
        }
        return html`
            <section class="marketing-gallery" aria-label=${this._t('gallery_section_label')}>
                <div class="marketing-gallery-grid">
                    ${galleryImages.map(
                        (galleryImage) => html`
                            <div class="marketing-hero-shot">
                                <img
                                    src=${galleryImage.src}
                                    alt=${this._t(galleryImage.altKey)}
                                    width="1200"
                                    height="673"
                                    loading="lazy"
                                    decoding="async"
                                />
                            </div>
                        `,
                    )}
                </div>
            </section>
        `;
    }

    _renderFeatures() {
        return html`
            <section class="marketing-features">
                <div class="marketing-features-grid">
                    ${[1, 2, 3, 4].map(
                        (index) => html`
                            <div class="marketing-feature-card glass-medium glass-interactive">
                                <h3 class="marketing-feature-title">${this._t(`f${index}_title`)}</h3>
                                <p class="marketing-feature-description">${this._t(`f${index}_desc`)}</p>
                            </div>
                        `,
                    )}
                </div>
            </section>
        `;
    }

    _renderSteps() {
        return html`
            <section class="marketing-steps">
                <div class="marketing-steps-container">
                    <h2 class="marketing-steps-title">${this._t('how_title')}</h2>
                    <div class="marketing-steps-grid">
                        ${[1, 2, 3, 4].map(
                            (index) => html`
                                <div class="marketing-step-item">
                                    <div class="marketing-step-number">${index}</div>
                                    <div class="marketing-step-content">
                                        <h3>${this._t(`s${index}_h`)}</h3>
                                        <p>${this._t(`s${index}_p`)}</p>
                                    </div>
                                </div>
                            `,
                        )}
                    </div>
                </div>
            </section>
        `;
    }

    _renderBenefits() {
        return html`
            <section class="marketing-benefits">
                <div class="marketing-benefits-container">
                    <h2 class="marketing-benefits-title">${this._t('benefits_title')}</h2>
                    <div class="marketing-benefits-grid">
                        ${[1, 2, 3, 4, 5, 6].map(
                            (index) => html`
                                <div class="marketing-benefit-item">
                                    <div class="marketing-benefit-marker" aria-hidden="true"></div>
                                    <div class="marketing-benefit-content">
                                        <h3>${this._t(`b${index}_h`)}</h3>
                                        <p>${this._t(`b${index}_p`)}</p>
                                    </div>
                                </div>
                            `,
                        )}
                    </div>
                </div>
            </section>
        `;
    }

    _renderUseCases() {
        return html`
            <section class="marketing-use-cases">
                <h2 class="marketing-use-cases-title">${this._t('use_cases_title')}</h2>
                <div class="marketing-use-cases-grid">
                    ${[1, 2, 3, 4, 5, 6].map(
                        (index) => html`
                            <div class="marketing-use-case-item">
                                <span class="marketing-use-case-num">${index}</span>
                                <span class="marketing-use-case-text">${this._t(`uc${index}`)}</span>
                            </div>
                        `,
                    )}
                </div>
            </section>
        `;
    }

    _renderFaq() {
        return html`
            <section class="marketing-faq">
                <h2 class="marketing-faq-title">${this._t('faq_title')}</h2>
                <div class="marketing-faq-list">
                    ${[1, 2, 3].map(
                        (index) => html`
                            <details class="marketing-faq-item">
                                <summary>${this._t(`faq${index}_q`)}</summary>
                                <p class="marketing-faq-answer">${this._t(`faq${index}_a`)}</p>
                            </details>
                        `,
                    )}
                </div>
            </section>
        `;
    }

    _renderCta() {
        return html`
            <section class="marketing-cta">
                <h2 class="marketing-cta-title">${this._t('cta_title')}</h2>
                <p class="marketing-cta-subtitle">${this._t('cta_subtitle')}</p>
                <platform-button variant="primary" @click=${this._handleProductCtaClick}>
                    ${this._t('cta_button')}
                </platform-button>
                <a href="/" class="marketing-back-link">${this._t('back_home')}</a>
            </section>
        `;
    }

    /** @param {ProductLandingSection} sectionKey */
    _renderSection(sectionKey) {
        switch (sectionKey) {
            case 'hero':
                return this._renderHero();
            case 'gallery':
                return this._renderGallery();
            case 'features':
                return this._renderFeatures();
            case 'steps':
                return this._renderSteps();
            case 'benefits':
                return this._renderBenefits();
            case 'use-cases':
                return this._renderUseCases();
            case 'faq':
                return this._renderFaq();
            case 'cta':
                return this._renderCta();
            default:
                throw new Error(`${this.tagName.toLowerCase()}: unknown section ${sectionKey}`);
        }
    }

    render() {
        const sections = this.constructor.sections;
        if (!sections.length) {
            throw new Error(`${this.tagName.toLowerCase()}: sections are required`);
        }
        return html`
            <landing-header></landing-header>
            <div class="marketing-page-container">
                ${sections.map((sectionKey) => this._renderSection(sectionKey))}
                <landing-footer></landing-footer>
            </div>
        `;
    }
}

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
import '../cosmic/cosmic-scope.js';
import '../cosmic/scramble-text.js';
import { applyPublicDocumentMeta } from '../../_helpers/public-document-meta.js';
import { getPlatformBrandBootstrap } from '@platform/lib/utils/platform-brand.js';
import type {CSSResultGroup, TemplateResult} from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { AuthStatus } from '@platform/lib/events/reducers/auth.js';

export type ProductLandingSection = 'hero' | 'gallery' | 'features' | 'steps' | 'benefits' | 'use-cases' | 'faq' | 'cta';

export interface ProductLandingHeroImage {
    kind: 'static' | 'locale';
    value: string | ((locale: 'ru' | 'en') => string);
}

export interface ProductLandingGalleryImage {
    src: string;
    altKey: string;
}

export type ProductLandingServiceEntry = 'flows' | 'crm' | 'rag' | 'sync' | 'documents' | 'frontend' | 'geo' | 'wiki' | 'shop';
export type ProductLandingAccent = 'accent' | 'success' | 'accent-secondary';

export class ProductLandingPage extends PlatformPage {
    static i18nNamespace = 'frontend_products';
    static productKey: string = '';
    static sections: ProductLandingSection[] = [];
    static serviceEntry: ProductLandingServiceEntry = 'flows';
    static productAccent: ProductLandingAccent = 'accent';
    static heroImage: ProductLandingHeroImage = { kind: 'static', value: '' };
    static galleryImages: ProductLandingGalleryImage[] = [];

    static override styles: CSSResultGroup = [PlatformPage.styles, ...marketingProductPageStyles];

    constructor() {
        super();
        this._authStatusSel = this.select((s) => s.auth.status);
        this._localeSel = this.select((s) => s.i18n.locale);
    }
    private _authStatusSel: SelectController<AuthStatus>;
    private _localeSel: SelectController<string>;


    override connectedCallback(): void {
        super.connectedCallback();
        const ctor = this.constructor as typeof ProductLandingPage;
        if (ctor.productAccent !== 'accent') {
            this.setAttribute('product-accent', ctor.productAccent);
        }
        queueMicrotask(() => this._syncProductDocumentMeta());
    }

    _translationKey(relativeKey: string) {
        const ctor = this.constructor as typeof ProductLandingPage;
        return `${ctor.productKey}.${relativeKey}`;
    }

    _t(relativeKey: string) {
        return this.t(this._translationKey(relativeKey));
    }

    _resolveHeroImageSrc() {
        const heroImage = (this.constructor as typeof ProductLandingPage).heroImage;
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
        const productKey = (this.constructor as typeof ProductLandingPage).productKey;
        if (!productKey) {
            throw new Error(`${this.tagName.toLowerCase()}: productKey is required`);
        }
        const origin = window.location.origin;
        const brand = getPlatformBrandBootstrap();
        const platformSuffix = brand ? ` | ${brand.platformName}` : '';
        applyPublicDocumentMeta({
            title: `${this._t('meta_title')}${platformSuffix}`,
            description: this._t('meta_description'),
            canonicalUrl: `${origin}/products/${productKey}`,
            ogImageUrl: `${origin}/static/frontend/assets/images/main_img.png`,
        });
    }

    _handleProductCtaClick = () => {
        const serviceEntry = (this.constructor as typeof ProductLandingPage).serviceEntry;
        if (this._authStatusSel.value === 'authenticated') {
            window.location.href = buildServiceEntryUrl(serviceEntry);
            return;
        }
        this.openModal('auth.login', { returnPath: buildServiceEntryUrl(serviceEntry) });
    };

    _renderHero() {
        const heroSrc = this._resolveHeroImageSrc();
        return html`
            <section class="marketing-hero" data-cosmic-chapter data-cosmic-hue="196" data-cosmic-label=${this._t('hero_badge')}>
                <span class="marketing-hero-badge">${this._t('hero_badge')}</span>
                <h1 class="marketing-hero-title"><scramble-text .text=${this._t('hero_title')}></scramble-text></h1>
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
        const galleryImages = (this.constructor as typeof ProductLandingPage).galleryImages;
        if (galleryImages.length === 0) {
            return html``;
        }
        return html`
            <section class="marketing-gallery" aria-label=${this._t('gallery_section_label')} data-cosmic-chapter data-cosmic-hue="216" data-cosmic-label=${this._t('gallery_section_label')}>
                <div class="marketing-gallery-grid">
                    ${galleryImages.map((galleryImage) => html`
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
            <section class="marketing-features" data-cosmic-chapter data-cosmic-hue="222" data-cosmic-label=${this._t('hero_badge')}>
                <div class="marketing-features-grid">
                    ${[1, 2, 3, 4].map((index) => html`
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
            <section class="marketing-steps" data-cosmic-chapter data-cosmic-hue="235" data-cosmic-label=${this._t('how_title')}>
                <div class="marketing-steps-container">
                    <h2 class="marketing-steps-title">${this._t('how_title')}</h2>
                    <div class="marketing-steps-grid">
                        ${[1, 2, 3, 4].map((index) => html`
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
            <section class="marketing-benefits" data-cosmic-chapter data-cosmic-hue="252" data-cosmic-label=${this._t('benefits_title')}>
                <div class="marketing-benefits-container">
                    <h2 class="marketing-benefits-title">${this._t('benefits_title')}</h2>
                    <div class="marketing-benefits-grid">
                        ${[1, 2, 3, 4, 5, 6].map((index) => html`
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
            <section class="marketing-use-cases" data-cosmic-chapter data-cosmic-hue="205" data-cosmic-label=${this._t('use_cases_title')}>
                <h2 class="marketing-use-cases-title">${this._t('use_cases_title')}</h2>
                <div class="marketing-use-cases-grid">
                    ${[1, 2, 3, 4, 5, 6].map((index) => html`
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
            <section class="marketing-faq" data-cosmic-chapter data-cosmic-hue="198" data-cosmic-label=${this._t('faq_title')}>
                <h2 class="marketing-faq-title">${this._t('faq_title')}</h2>
                <div class="marketing-faq-list">
                    ${[1, 2, 3].map((index) => html`
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
            <section class="marketing-cta" data-cosmic-chapter data-cosmic-hue="186" data-cosmic-label=${this._t('cta_title')}>
                <h2 class="marketing-cta-title">${this._t('cta_title')}</h2>
                <p class="marketing-cta-subtitle">${this._t('cta_subtitle')}</p>
                <platform-button variant="primary" @click=${this._handleProductCtaClick}>
                    ${this._t('cta_button')}
                </platform-button>
                <a href="/" class="marketing-back-link">${this._t('back_home')}</a>
            </section>
        `;
    }

    _renderSection(sectionKey: ProductLandingSection) {
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

    override render(): TemplateResult {
        const sections = (this.constructor as typeof ProductLandingPage).sections;
        if (!sections.length) {
            throw new Error(`${this.tagName.toLowerCase()}: sections are required`);
        }
        return html`
            <cosmic-scope class="marketing-page-container">
                <landing-header></landing-header>
                ${sections.map((sectionKey) => this._renderSection(sectionKey))}
                <landing-footer></landing-footer>
            </cosmic-scope>
        `;
    }
}

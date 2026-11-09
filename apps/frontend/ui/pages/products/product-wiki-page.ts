/**
 * Страница продукта Wiki — база знаний компании
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landWikiHomeShotUrl,
    landWikiPageShotUrl,
} from '../../_helpers/land-product-images.js';

export class ProductWikiPage extends ProductLandingPage {
    static override productKey: string = 'wiki';
    static override serviceEntry: ProductLandingServiceEntry = 'wiki';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'steps', 'benefits', 'use-cases', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landWikiHomeShotUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landWikiPageShotUrl, altKey: 'gallery_2_alt' },
    ];
}

customElements.define('product-wiki-page', ProductWikiPage);

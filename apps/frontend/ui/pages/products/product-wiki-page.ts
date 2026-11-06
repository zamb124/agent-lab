/**
 * Страница продукта Wiki — база знаний компании
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landWikiHomeUrl,
    landWikiPageUrl,
} from '../../_helpers/land-product-images.js';

export class ProductWikiPage extends ProductLandingPage {
    static override productKey: string = 'wiki';
    static override serviceEntry: ProductLandingServiceEntry = 'wiki';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'steps', 'benefits', 'use-cases', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landWikiHomeUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landWikiPageUrl, altKey: 'gallery_2_alt' },
    ];
}

customElements.define('product-wiki-page', ProductWikiPage);

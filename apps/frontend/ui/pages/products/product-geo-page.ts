/**
 * Страница продукта Geo — платформенный гео-движок
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landGeoMapUrl,
    landGeoMapLabUrl,
    landGeoSourcesUrl,
} from '../../_helpers/land-product-images.js';

export class ProductGeoPage extends ProductLandingPage {
    static override productKey: string = 'geo';
    static override serviceEntry: ProductLandingServiceEntry = 'geo';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'steps', 'benefits', 'use-cases', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landGeoMapUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landGeoMapLabUrl, altKey: 'gallery_2_alt' },
        { src: landGeoSourcesUrl, altKey: 'gallery_3_alt' },
    ];
}

customElements.define('product-geo-page', ProductGeoPage);

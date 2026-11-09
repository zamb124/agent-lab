/**
 * Страница продукта CRM — NetWorkle
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landCrmGraphUrl,
    landCrmNotesUrl,
    landCrmEntitiesUrl,
    landCrmTasksUrl,
} from '../../_helpers/land-product-images.js';

export class ProductCrmPage extends ProductLandingPage {
    static override productKey: string = 'crm';
    static override serviceEntry: ProductLandingServiceEntry = 'crm';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'steps', 'benefits', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landCrmGraphUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landCrmNotesUrl, altKey: 'gallery_2_alt' },
        { src: landCrmEntitiesUrl, altKey: 'gallery_3_alt' },
        { src: landCrmTasksUrl, altKey: 'gallery_4_alt' },
    ];
}

customElements.define('product-crm-page', ProductCrmPage);

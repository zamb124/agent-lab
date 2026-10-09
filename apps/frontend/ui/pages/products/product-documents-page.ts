/**
 * Страница продукта Documents — OnlyOffice
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landDocumentsHeroUrl,
    landDocumentsShot2Url,
    landDocumentsShot3Url,
} from '../../_helpers/land-product-images.js';

export class ProductDocumentsPage extends ProductLandingPage {
    static override productKey: string = 'documents';
    static override serviceEntry: ProductLandingServiceEntry = 'documents';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'steps', 'benefits', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landDocumentsHeroUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landDocumentsShot2Url, altKey: 'gallery_2_alt' },
        { src: landDocumentsShot3Url, altKey: 'gallery_3_alt' },
    ];
}

customElements.define('product-documents-page', ProductDocumentsPage);

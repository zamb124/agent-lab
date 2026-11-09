/**
 * Страница продукта Documents — OnlyOffice
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landOfficeEditorUrl,
    landOfficeDocumentsUrl,
} from '../../_helpers/land-product-images.js';

export class ProductDocumentsPage extends ProductLandingPage {
    static override productKey: string = 'documents';
    static override serviceEntry: ProductLandingServiceEntry = 'documents';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'steps', 'benefits', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landOfficeEditorUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landOfficeDocumentsUrl, altKey: 'gallery_2_alt' },
    ];
}

customElements.define('product-documents-page', ProductDocumentsPage);

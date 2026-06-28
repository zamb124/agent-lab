/**
 * Страница продукта Documents — OnlyOffice
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import {
    landDocumentsHeroUrl,
    landDocumentsShot2Url,
    landDocumentsShot3Url,
} from '../../utils/land-product-images.js';

export class ProductDocumentsPage extends ProductLandingPage {
    static productKey = 'documents';
    static serviceEntry = 'documents';
    static productAccent = 'accent';
    static sections = ['hero', 'gallery', 'features', 'steps', 'benefits', 'faq', 'cta'];
    static heroImage = { kind: 'static', value: landDocumentsHeroUrl };
    static galleryImages = [
        { src: landDocumentsShot2Url, altKey: 'gallery_2_alt' },
        { src: landDocumentsShot3Url, altKey: 'gallery_3_alt' },
    ];
}

customElements.define('product-documents-page', ProductDocumentsPage);

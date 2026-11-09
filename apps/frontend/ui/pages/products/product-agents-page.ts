/**
 * Страница продукта Agents — AI Studio
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landFlowsEditorUrl,
    landFlowsHomeUrl,
} from '../../_helpers/land-product-images.js';

export class ProductAgentsPage extends ProductLandingPage {
    static override productKey: string = 'agents';
    static override serviceEntry: ProductLandingServiceEntry = 'flows';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'benefits', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landFlowsEditorUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landFlowsHomeUrl, altKey: 'gallery_2_alt' },
    ];
}

customElements.define('product-agents-page', ProductAgentsPage);

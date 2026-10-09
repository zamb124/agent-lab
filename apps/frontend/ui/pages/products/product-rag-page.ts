/**
 * Страница продукта RAG — Knowledge Base
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import { landRagAbilityUrl } from '../../_helpers/land-product-images.js';

export class ProductRagPage extends ProductLandingPage {
    static override productKey: string = 'rag';
    static override serviceEntry: ProductLandingServiceEntry = 'rag';
    static override productAccent: ProductLandingAccent = 'success';
    static override sections: ProductLandingSection[] = ['hero', 'features', 'benefits', 'use-cases', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landRagAbilityUrl };
}

customElements.define('product-rag-page', ProductRagPage);

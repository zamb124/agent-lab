/**
 * Страница продукта Agents — AI Studio
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import { landFlowsAbilityUrl } from '../../_helpers/land-product-images.js';

export class ProductAgentsPage extends ProductLandingPage {
    static override productKey: string = 'agents';
    static override serviceEntry: ProductLandingServiceEntry = 'flows';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'features', 'benefits', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'locale', value: landFlowsAbilityUrl };
}

customElements.define('product-agents-page', ProductAgentsPage);

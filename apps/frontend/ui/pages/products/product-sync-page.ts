/**
 * Страница продукта Sync — инженерный чат
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import { landSyncAbilityUrl } from '../../_helpers/land-product-images.js';

export class ProductSyncPage extends ProductLandingPage {
    static override productKey: string = 'sync';
    static override serviceEntry: ProductLandingServiceEntry = 'sync';
    static override productAccent: ProductLandingAccent = 'accent-secondary';
    static override sections: ProductLandingSection[] = ['hero', 'features', 'steps', 'benefits', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landSyncAbilityUrl };
}

customElements.define('product-sync-page', ProductSyncPage);

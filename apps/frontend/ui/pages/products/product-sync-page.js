/**
 * Страница продукта Sync — инженерный чат
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import { landSyncAbilityUrl } from '../../utils/land-product-images.js';

export class ProductSyncPage extends ProductLandingPage {
    static productKey = 'sync';
    static serviceEntry = 'sync';
    static productAccent = 'accent-secondary';
    static sections = ['hero', 'features', 'steps', 'benefits', 'faq', 'cta'];
    static heroImage = { kind: 'static', value: landSyncAbilityUrl };
}

customElements.define('product-sync-page', ProductSyncPage);

/**
 * Страница продукта CRM — NetWorkle
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import { landNetworkleAbilityUrl } from '../../utils/land-product-images.js';

export class ProductCrmPage extends ProductLandingPage {
    static productKey = 'crm';
    static serviceEntry = 'crm';
    static productAccent = 'accent';
    static sections = ['hero', 'features', 'steps', 'benefits', 'faq', 'cta'];
    static heroImage = { kind: 'static', value: landNetworkleAbilityUrl };
}

customElements.define('product-crm-page', ProductCrmPage);

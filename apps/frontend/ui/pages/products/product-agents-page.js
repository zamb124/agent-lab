/**
 * Страница продукта Agents — AI Studio
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import { landFlowsAbilityUrl } from '../../utils/land-product-images.js';

export class ProductAgentsPage extends ProductLandingPage {
    static productKey = 'agents';
    static serviceEntry = 'flows';
    static productAccent = 'accent';
    static sections = ['hero', 'features', 'benefits', 'faq', 'cta'];
    static heroImage = { kind: 'locale', value: landFlowsAbilityUrl };
}

customElements.define('product-agents-page', ProductAgentsPage);

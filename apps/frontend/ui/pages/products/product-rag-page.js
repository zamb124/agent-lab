/**
 * Страница продукта RAG — Knowledge Base
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import { landRagAbilityUrl } from '../../utils/land-product-images.js';

export class ProductRagPage extends ProductLandingPage {
    static productKey = 'rag';
    static serviceEntry = 'rag';
    static productAccent = 'success';
    static sections = ['hero', 'features', 'benefits', 'use-cases', 'faq', 'cta'];
    static heroImage = { kind: 'static', value: landRagAbilityUrl };
}

customElements.define('product-rag-page', ProductRagPage);

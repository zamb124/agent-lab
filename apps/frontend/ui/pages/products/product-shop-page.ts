/**
 * Страница продукта Shop — витрина и онлайн-заказы
 */
import { ProductLandingPage } from '../../components/product-landing/product-landing-page.js';
import type { ProductLandingSection, ProductLandingHeroImage, ProductLandingGalleryImage, ProductLandingServiceEntry, ProductLandingAccent } from '../../components/product-landing/product-landing-page.js';
import {
    landShopStorefrontUrl,
    landShopCartUrl,
    landShopAdminMenuUrl,
    landShopBuilderUrl,
} from '../../_helpers/land-product-images.js';

export class ProductShopPage extends ProductLandingPage {
    static override productKey: string = 'shop';
    static override serviceEntry: ProductLandingServiceEntry = 'shop';
    static override productAccent: ProductLandingAccent = 'accent';
    static override sections: ProductLandingSection[] = ['hero', 'gallery', 'features', 'steps', 'benefits', 'use-cases', 'faq', 'cta'];
    static override heroImage: ProductLandingHeroImage = { kind: 'static', value: landShopStorefrontUrl };
    static override galleryImages: ProductLandingGalleryImage[] = [
        { src: landShopCartUrl, altKey: 'gallery_2_alt' },
        { src: landShopAdminMenuUrl, altKey: 'gallery_3_alt' },
        { src: landShopBuilderUrl, altKey: 'gallery_4_alt' },
    ];
}

customElements.define('product-shop-page', ProductShopPage);

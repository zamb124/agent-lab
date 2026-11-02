/**
 * ShopMenuPage — рейка категорий: ввод имени в cat-add включает кнопку
 * и _addCategory дергает shop/category_create с тем же payload.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import {
    shopShopsResource,
    shopUpdateOp,
    shopBadgeIconsListOp,
    shopCategoriesListOp,
    shopProductsListOp,
    shopCategoryCreateOp,
    shopCategoryRemoveOp,
    shopCategoriesReorderOp,
    shopProductUpdateOp,
    shopProductRemoveOp,
    shopProductsReorderOp,
    shopProductsImportOp,
    shopAiParseMenuOp,
    shopAiDescribeBatchOp,
    shopAiEnhancePhotoOp,
    shopAiGeneratePhotoOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import {
    shopCreateOp,
    shopPublishOp,
    shopAiAutofillOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '../../../../apps/shop/ui/pages/shop-menu-page.js';
import '../../../../apps/shop/ui/pages/shop-home-page.js';

const FACTORIES = [
    shopShopsResource,
    shopUpdateOp,
    shopBadgeIconsListOp,
    shopCategoriesListOp,
    shopProductsListOp,
    shopCategoryCreateOp,
    shopCategoryRemoveOp,
    shopCategoriesReorderOp,
    shopProductUpdateOp,
    shopProductRemoveOp,
    shopProductsReorderOp,
    shopProductsImportOp,
    shopAiParseMenuOp,
    shopAiDescribeBatchOp,
    shopAiEnhancePhotoOp,
    shopAiGeneratePhotoOp,
    shopCreateOp,
    shopPublishOp,
    shopAiAutofillOp,
    platformFileCreateOp,
];

function typeIntoField(host: HTMLElement, selector: string, text: string): void {
    const field = host.shadowRoot!.querySelector(selector) as HTMLElement & { shadowRoot: ShadowRoot };
    expect(field, `field ${selector}`).to.exist;
    const inner = field.shadowRoot.querySelector('platform-field-string') as HTMLElement & { shadowRoot: ShadowRoot };
    expect(inner, `${selector} platform-field-string`).to.exist;
    const input = inner.shadowRoot.querySelector('input') as HTMLInputElement;
    expect(input, `${selector} input`).to.exist;
    input.value = text;
    input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
}

describe('shop-menu-page: добавление категории', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('ввод имени включает кнопку "+" (disabled=false)', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        const addBtn = el.shadowRoot!.querySelector('.cat-add platform-button') as HTMLElement & { disabled: boolean };
        expect(addBtn, 'cat-add platform-button').to.exist;
        expect(addBtn.disabled).to.equal(true);
        typeIntoField(el, '.cat-add platform-field', 'Суши');
        await elementUpdated(el);
        expect((el as unknown as { _newCategory: string })._newCategory).to.equal('Суши');
        expect(addBtn.disabled).to.equal(false);
    });
});

const SHOP_ROW = {
    shop_id: 'shop_test',
    name: 'МОЙ МАГАЗ',
    slug: 'moy-magaz',
    status: 'published',
    badges: [],
};

const SHOP_ROUTES = [
    { key: 'shop_home', path: '', titleKey: 'routes.shop_home' },
    { key: 'shop_menu', path: ':shopId/menu', parent: 'shop_home', titleKey: 'routes.shop_menu' },
];

function seedShopAndRoute() {
    const bus = getPlatformBus();
    bus.dispatch(CoreEvents.ROUTER_ROUTE_CHANGED, { routeKey: 'shop_menu', params: { shopId: 'shop_test' } });
    bus.dispatch('shop/shops/list_loaded', { items: [SHOP_ROW], total: 1 });
}

describe('shop-menu-page: контекст магазина', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES, routes: SHOP_ROUTES });
    });

    it('shop-page-head показывает имя магазина, раздел и крошки', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        seedShopAndRoute();
        await elementUpdated(el);
        const head = el.shadowRoot!.querySelector('shop-page-head') as HTMLElement & { shadowRoot: ShadowRoot };
        expect(head, 'shop-page-head').to.exist;
        await elementUpdated(head);
        const h1 = head.shadowRoot.querySelector('h1');
        expect(h1?.textContent?.trim()).to.equal('МОЙ МАГАЗ');
        expect(head.shadowRoot.textContent).to.contain('moy-magaz');
        const breadcrumbs = head.shadowRoot.querySelector('platform-breadcrumbs') as HTMLElement & { shadowRoot: ShadowRoot };
        expect(breadcrumbs, 'platform-breadcrumbs').to.exist;
        await elementUpdated(breadcrumbs);
        const crumbsText = breadcrumbs.shadowRoot.textContent ?? '';
        expect(crumbsText).to.contain('МОЙ МАГАЗ');
        const storefront = head.shadowRoot.querySelector('a.storefront') as HTMLAnchorElement | null;
        expect(storefront, 'storefront link для published').to.exist;
        expect(storefront!.href).to.contain('/public/s/moy-magaz');
    });

    it('add_product — единственная primary-кнопка в шапке', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        const actions = Array.from(el.shadowRoot!.querySelectorAll('.head-actions platform-button')) as Array<HTMLElement & { variant: string }>;
        const primaries = actions.filter((b) => b.variant === 'primary');
        expect(primaries.length).to.equal(1);
        const variants = new Set(actions.map((b) => b.variant));
        expect(variants.has('secondary')).to.equal(true);
    });
});

describe('shop-menu-page: загрузка при монтировании', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('connectedCallback диспетчит categories/products/shops list_requested', async () => {
        const bus = getPlatformBus();
        const fired: string[] = [];
        bus.subscribeType(shopCategoriesListOp.events.REQUESTED, (event) => { fired.push(event.type); });
        bus.subscribeType(shopProductsListOp.events.REQUESTED, (event) => { fired.push(event.type); });
        bus.subscribeType(shopShopsResource.events.LIST_REQUESTED, (event) => { fired.push(event.type); });
        await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        expect(fired).to.include(shopCategoriesListOp.events.REQUESTED);
        expect(fired).to.include(shopProductsListOp.events.REQUESTED);
        expect(fired).to.include(shopShopsResource.events.LIST_REQUESTED);
    });

    it('смена shop-id перезагружает списки', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        let fired = 0;
        const bus = getPlatformBus();
        bus.subscribeType(shopCategoriesListOp.events.REQUESTED, () => { fired += 1; });
        el.setAttribute('shop-id', 'shop_other');
        await elementUpdated(el);
        expect(fired).to.equal(1);
    });
});

describe('shop-home-page: загрузка при монтировании', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('autoload диспетчит shops list_requested при connect', async () => {
        const bus = getPlatformBus();
        const fired: string[] = [];
        bus.subscribeType(shopShopsResource.events.LIST_REQUESTED, (event) => { fired.push(event.type); });
        await fixture<HTMLElement>(html`<shop-home-page></shop-home-page>`);
        expect(fired).to.include(shopShopsResource.events.LIST_REQUESTED);
    });
});

describe('shop-home-page: slug-поле', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('ручной ввод кириллицы транслитерируется в валидный slug', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-home-page></shop-home-page>
        `);
        getPlatformBus().dispatch('shop/shops/list_loaded', { items: [], total: 0 });
        await elementUpdated(el);
        const slugField = el.shadowRoot!.querySelector('platform-field[hint]') as HTMLElement;
        expect(slugField, 'slug platform-field с hint').to.exist;
        const inner = slugField.shadowRoot!.querySelector('platform-field-string') as HTMLElement;
        const input = inner.shadowRoot!.querySelector('input') as HTMLInputElement;
        input.value = 'выфвыфвфы';
        input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await elementUpdated(el);
        expect((el as unknown as { _newSlug: string })._newSlug).to.equal('vyfvyfvfy');
    });
});

/**
 * Страницы меню заведения: список меню (`shop-menus-page`) и редактор
 * одного меню (`shop-menu-page`) — загрузка при монтировании и
 * контекстная шапка магазина; `shop-home-page` — загрузка и slug-поле.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus } from '@platform/lib/events/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import {
    shopShopsResource,
    shopUpdateOp,
    shopBadgeIconsListOp,
    shopMenusListOp,
    shopMenuCreateOp,
    shopMenuUpdateOp,
    shopMenusReorderOp,
    shopMenuSetStatusOp,
    shopMenuRemoveOp,
    shopMenuSectionCreateOp,
    shopMenuSectionUpdateOp,
    shopMenuSectionRemoveOp,
    shopMenuSectionsReorderOp,
    shopMenuItemAddOp,
    shopMenuItemUpdateOp,
    shopMenuItemMoveOp,
    shopMenuItemRemoveOp,
    shopMenuItemsReorderOp,
    shopMenuImportsListOp,
    shopProductsListOp,
    shopProductCreateOp,
    shopProductUpdateOp,
    shopProductRemoveOp,
    shopAiEnhancePhotoOp,
    shopAiGeneratePhotoOp,
    shopCreateOp,
    shopPublishOp,
    shopAiAutofillOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import '../../../../apps/shop/ui/pages/shop-menus-page.js';
import '../../../../apps/shop/ui/pages/shop-menu-page.js';
import '../../../../apps/shop/ui/pages/shop-home-page.js';

const FACTORIES = [
    shopShopsResource,
    shopUpdateOp,
    shopBadgeIconsListOp,
    shopMenusListOp,
    shopMenuCreateOp,
    shopMenuUpdateOp,
    shopMenusReorderOp,
    shopMenuSetStatusOp,
    shopMenuRemoveOp,
    shopMenuSectionCreateOp,
    shopMenuSectionUpdateOp,
    shopMenuSectionRemoveOp,
    shopMenuSectionsReorderOp,
    shopMenuItemAddOp,
    shopMenuItemUpdateOp,
    shopMenuItemMoveOp,
    shopMenuItemRemoveOp,
    shopMenuItemsReorderOp,
    shopMenuImportsListOp,
    shopProductsListOp,
    shopProductCreateOp,
    shopProductUpdateOp,
    shopProductRemoveOp,
    shopAiEnhancePhotoOp,
    shopAiGeneratePhotoOp,
    shopCreateOp,
    shopPublishOp,
    shopAiAutofillOp,
    platformFileCreateOp,
];

const SHOP_ROW = {
    shop_id: 'shop_test',
    name: 'МОЙ МАГАЗ',
    slug: 'moy-magaz',
    status: 'published',
    badges: [],
};

const SHOP_ROUTES = [
    { key: 'shop_home', path: '', titleKey: 'routes.shop_home' },
    { key: 'shop_catalog', path: ':shopId/catalog', parent: 'shop_home', titleKey: 'routes.shop_catalog' },
    { key: 'shop_menus', path: ':shopId/menus', parent: 'shop_home', titleKey: 'routes.shop_menus' },
    { key: 'shop_menu', path: ':shopId/menus/:menuId', parent: 'shop_menus', titleKey: 'routes.shop_menu' },
];

type TestEl = HTMLElement & { shadowRoot: ShadowRoot };

function seedShopAndRoute(routeKey: string, params: Record<string, string>) {
    const bus = getPlatformBus();
    bus.dispatch(CoreEvents.ROUTER_ROUTE_CHANGED, { routeKey, params });
    bus.dispatch('shop/shops/list_loaded', { items: [SHOP_ROW], total: 1 });
}

async function headOf(el: TestEl): Promise<TestEl> {
    const head = el.shadowRoot.querySelector('shop-page-head') as TestEl | null;
    expect(head, 'shop-page-head').to.exist;
    await elementUpdated(head!);
    return head!;
}

describe('shop-menus-page: загрузка при монтировании', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('shop-id диспетчит menus_list и shops list_requested', async () => {
        const bus = getPlatformBus();
        const fired: string[] = [];
        bus.subscribeType(shopMenusListOp.events.REQUESTED, (event) => { fired.push(event.type); });
        bus.subscribeType(shopShopsResource.events.LIST_REQUESTED, (event) => { fired.push(event.type); });
        const el = await fixture<TestEl>(html`<shop-menus-page shop-id="shop_test"></shop-menus-page>`);
        await elementUpdated(el);
        expect(fired).to.include(shopMenusListOp.events.REQUESTED);
        expect(fired).to.include(shopShopsResource.events.LIST_REQUESTED);
    });

    it('смена shop-id перезагружает список меню', async () => {
        const el = await fixture<TestEl>(html`<shop-menus-page shop-id="shop_test"></shop-menus-page>`);
        await elementUpdated(el);
        let fired = 0;
        getPlatformBus().subscribeType(shopMenusListOp.events.REQUESTED, () => { fired += 1; });
        el.setAttribute('shop-id', 'shop_other');
        await elementUpdated(el);
        expect(fired).to.equal(1);
    });
});

describe('shop-menus-page: контекст магазина', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES, routes: SHOP_ROUTES });
    });

    it('shop-page-head показывает имя магазина, slug и ссылку на витрину', async () => {
        const el = await fixture<TestEl>(html`<shop-menus-page shop-id="shop_test"></shop-menus-page>`);
        seedShopAndRoute('shop_menus', { shopId: 'shop_test' });
        await elementUpdated(el);
        const head = await headOf(el);
        expect(head.shadowRoot.querySelector('h1')?.textContent?.trim()).to.equal('МОЙ МАГАЗ');
        expect(head.shadowRoot.textContent).to.contain('moy-magaz');
        const storefront = head.shadowRoot.querySelector('a.storefront') as HTMLAnchorElement | null;
        expect(storefront, 'storefront link для published').to.exist;
        expect(storefront!.href).to.contain('/public/s/moy-magaz');
    });

    it('«Создать меню» — единственная primary-кнопка в шапке', async () => {
        const el = await fixture<TestEl>(html`<shop-menus-page shop-id="shop_test"></shop-menus-page>`);
        await elementUpdated(el);
        const actions = Array.from(el.shadowRoot.querySelectorAll('.head-actions platform-button')) as Array<HTMLElement & { variant: string }>;
        expect(actions.filter((b) => b.variant === 'primary').length).to.equal(1);
        expect(new Set(actions.map((b) => b.variant))).to.deep.equal(new Set(['accent', 'secondary', 'primary']));
    });
});

describe('shop-menu-page: загрузка при монтировании', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('connectedCallback диспетчит menus_list, products_list и shops list_requested', async () => {
        const bus = getPlatformBus();
        const fired: string[] = [];
        bus.subscribeType(shopMenusListOp.events.REQUESTED, (event) => { fired.push(event.type); });
        bus.subscribeType(shopProductsListOp.events.REQUESTED, (event) => { fired.push(event.type); });
        bus.subscribeType(shopShopsResource.events.LIST_REQUESTED, (event) => { fired.push(event.type); });
        await fixture<TestEl>(html`
            <shop-menu-page shop-id="shop_test" menu-id="menu_test"></shop-menu-page>
        `);
        expect(fired).to.include(shopMenusListOp.events.REQUESTED);
        expect(fired).to.include(shopProductsListOp.events.REQUESTED);
        expect(fired).to.include(shopShopsResource.events.LIST_REQUESTED);
    });

    it('смена shop-id перезагружает меню и каталог', async () => {
        const el = await fixture<TestEl>(html`
            <shop-menu-page shop-id="shop_test" menu-id="menu_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        const fired: string[] = [];
        const bus = getPlatformBus();
        bus.subscribeType(shopMenusListOp.events.REQUESTED, (event) => { fired.push(event.type); });
        bus.subscribeType(shopProductsListOp.events.REQUESTED, (event) => { fired.push(event.type); });
        el.setAttribute('shop-id', 'shop_other');
        await elementUpdated(el);
        expect(fired.sort()).to.deep.equal([shopMenusListOp.events.REQUESTED, shopProductsListOp.events.REQUESTED].sort());
    });
});

describe('shop-menu-page: контекст магазина', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES, routes: SHOP_ROUTES });
    });

    it('shop-page-head показывает имя магазина и ссылку на витрину', async () => {
        const el = await fixture<TestEl>(html`
            <shop-menu-page shop-id="shop_test" menu-id="menu_test"></shop-menu-page>
        `);
        seedShopAndRoute('shop_menu', { shopId: 'shop_test', menuId: 'menu_test' });
        await elementUpdated(el);
        const head = await headOf(el);
        expect(head.shadowRoot.querySelector('h1')?.textContent?.trim()).to.equal('МОЙ МАГАЗ');
        expect(head.shadowRoot.textContent).to.contain('moy-magaz');
        const storefront = head.shadowRoot.querySelector('a.storefront') as HTMLAnchorElement | null;
        expect(storefront, 'storefront link для published').to.exist;
        expect(storefront!.href).to.contain('/public/s/moy-magaz');
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

/**
 * ShopMenuPage — рейка категорий (shop-category-tree): события дерева
 * превращаются в shop/* команды, выбор категории фильтрует товары
 * по всему поддереву.
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
    shopCategoryUpdateOp,
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
    shopDemosSeedOp,
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
    shopCategoryUpdateOp,
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
    shopDemosSeedOp,
    platformFileCreateOp,
];

const CATS = {
    result: {
        items: [
            { shop_category_id: 'cat_a', parent_id: null, name: 'Пицца', sort: 0, is_active: true },
            { shop_category_id: 'cat_a1', parent_id: 'cat_a', name: 'Классика', sort: 0, is_active: true },
            { shop_category_id: 'cat_b', parent_id: null, name: 'Роллы', sort: 1, is_active: true },
        ],
    },
};

const PRODUCTS = {
    result: {
        items: [
            { shop_product_id: 'p_root', category_id: 'cat_a', name: 'Маргарита', description: '', price_minor: 100, photo_file_id: null, is_available: true, portion: '', badges: [], sort: 0 },
            { shop_product_id: 'p_kid', category_id: 'cat_a1', name: 'Капричоза', description: '', price_minor: 200, photo_file_id: null, is_available: true, portion: '', badges: [], sort: 0 },
            { shop_product_id: 'p_b', category_id: 'cat_b', name: 'Филадельфия', description: '', price_minor: 300, photo_file_id: null, is_available: true, portion: '', badges: [], sort: 0 },
            { shop_product_id: 'p_none', category_id: null, name: 'Соевый соус', description: '', price_minor: 50, photo_file_id: null, is_available: true, portion: '', badges: [], sort: 0 },
        ],
    },
};

function seedCatalog() {
    const bus = getPlatformBus();
    bus.dispatch(shopCategoriesListOp.events.SUCCEEDED, CATS);
    bus.dispatch(shopProductsListOp.events.SUCCEEDED, PRODUCTS);
}

function categoryTree(page: HTMLElement): HTMLElement & { shadowRoot: ShadowRoot } {
    const tree = page.shadowRoot!.querySelector('shop-category-tree') as HTMLElement & { shadowRoot: ShadowRoot };
    expect(tree, 'shop-category-tree в рейке').to.exist;
    return tree;
}

function emitOnTree(tree: HTMLElement, name: string, detail: unknown): void {
    tree.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
}

describe('shop-menu-page: дерево категорий → команды', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    it('tree-change диспетчит categories/reorder_requested с items', async () => {
        const bus = getPlatformBus();
        const payloads: unknown[] = [];
        bus.subscribeType(shopCategoriesReorderOp.events.REQUESTED, (e) => { payloads.push(e.payload); });
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        seedCatalog();
        await elementUpdated(el);
        const tree = categoryTree(el);
        const items = [
            { category_id: 'cat_b', parent_id: null },
            { category_id: 'cat_a', parent_id: null },
            { category_id: 'cat_a1', parent_id: 'cat_a' },
        ];
        emitOnTree(tree, 'tree-change', { items });
        expect(payloads).to.deep.equal([{ shop_id: 'shop_test', items }]);
    });

    it('tree-create диспетчит categories/create_requested с parent_id', async () => {
        const bus = getPlatformBus();
        const payloads: unknown[] = [];
        bus.subscribeType(shopCategoryCreateOp.events.REQUESTED, (e) => { payloads.push(e.payload); });
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        emitOnTree(categoryTree(el), 'tree-create', { parentId: 'cat_a', name: 'Десерты' });
        expect(payloads).to.deep.equal([{ shop_id: 'shop_test', name: 'Десерты', parent_id: 'cat_a' }]);
    });

    it('tree-rename диспетчит categories/update_requested', async () => {
        const bus = getPlatformBus();
        const payloads: unknown[] = [];
        bus.subscribeType(shopCategoryUpdateOp.events.REQUESTED, (e) => { payloads.push(e.payload); });
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        emitOnTree(categoryTree(el), 'tree-rename', { id: 'cat_a', name: 'Пицца NEW' });
        expect(payloads).to.deep.equal([{ shop_id: 'shop_test', shop_category_id: 'cat_a', name: 'Пицца NEW' }]);
    });

    it('tree-remove диспетчит categories/remove_requested', async () => {
        const bus = getPlatformBus();
        const payloads: unknown[] = [];
        bus.subscribeType(shopCategoryRemoveOp.events.REQUESTED, (e) => { payloads.push(e.payload); });
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        emitOnTree(categoryTree(el), 'tree-remove', { id: 'cat_a' });
        expect(payloads).to.deep.equal([{ shop_id: 'shop_test', shop_category_id: 'cat_a' }]);
    });

    it('product-drop диспетчит product/update_requested с новой category_id', async () => {
        const bus = getPlatformBus();
        const payloads: unknown[] = [];
        bus.subscribeType(shopProductUpdateOp.events.REQUESTED, (e) => { payloads.push(e.payload); });
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        await elementUpdated(el);
        emitOnTree(categoryTree(el), 'product-drop', { productId: 'p_root', categoryId: 'cat_b' });
        expect(payloads).to.deep.equal([{ shop_id: 'shop_test', shop_product_id: 'p_root', category_id: 'cat_b' }]);
    });
});

describe('shop-menu-page: фильтрация товаров по поддереву', () => {
    beforeEach(() => {
        resetPlatformState();
        bootstrapTestBus({ factories: FACTORIES });
    });

    function productNames(el: HTMLElement): string[] {
        return Array.from(el.shadowRoot!.querySelectorAll('.list .card .pname'))
            .map((n) => n.textContent?.trim() ?? '');
    }

    it('выбор родителя показывает товары всего поддерева', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        seedCatalog();
        await elementUpdated(el);
        emitOnTree(categoryTree(el), 'tree-select', { id: 'cat_a' });
        await elementUpdated(el);
        expect(productNames(el)).to.have.members(['Маргарита', 'Капричоза']);
    });

    it('выбор листа показывает только его товары', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        seedCatalog();
        await elementUpdated(el);
        emitOnTree(categoryTree(el), 'tree-select', { id: 'cat_a1' });
        await elementUpdated(el);
        expect(productNames(el)).to.have.members(['Капричоза']);
    });

    it('выбор "все товары" показывает полный список включая без категории', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        seedCatalog();
        await elementUpdated(el);
        emitOnTree(categoryTree(el), 'tree-select', { id: null });
        await elementUpdated(el);
        expect(productNames(el)).to.have.members(['Маргарита', 'Капричоза', 'Филадельфия', 'Соевый соус']);
    });

    it('дерево получает счётчики по поддереву и expandedIds', async () => {
        const el = await fixture<HTMLElement>(html`
            <shop-menu-page shop-id="shop_test"></shop-menu-page>
        `);
        seedCatalog();
        await elementUpdated(el);
        const tree = categoryTree(el) as HTMLElement & { counts: Record<string, number>; categories: unknown[] };
        expect(tree.categories.length).to.equal(3);
        expect(tree.counts.cat_a).to.equal(2);
        expect(tree.counts.cat_b).to.equal(1);
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

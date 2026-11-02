/**
 * shop-page-head: контекстная шапка внутренних страниц конструктора —
 * имя магазина, раздел, крошки «Магазины / имя / раздел», статус,
 * ссылка на витрину; интеграция на orders/promos/home.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import {
    shopShopsResource,
    shopUpdateOp,
    shopCreateOp,
    shopPublishOp,
    shopSuspendOp,
    shopOrdersListOp,
    shopOrderSetStatusOp,
    shopPromosListOp,
    shopPromoCreateOp,
    shopPromoUpdateOp,
    shopPromoRemoveOp,
    shopProductsListOp,
    shopAiAutofillOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '../../../../apps/shop/ui/components/shop-page-head.js';
import '../../../../apps/shop/ui/pages/shop-orders-page.js';
import '../../../../apps/shop/ui/pages/shop-promos-page.js';
import '../../../../apps/shop/ui/pages/shop-home-page.js';

const FACTORIES = [
    shopShopsResource,
    shopUpdateOp,
    shopCreateOp,
    shopPublishOp,
    shopSuspendOp,
    shopOrdersListOp,
    shopOrderSetStatusOp,
    shopPromosListOp,
    shopPromoCreateOp,
    shopPromoUpdateOp,
    shopPromoRemoveOp,
    shopProductsListOp,
    shopAiAutofillOp,
];

const SHOP_ROUTES = [
    { key: 'shop_home', path: '', titleKey: 'routes.shop_home' },
    { key: 'shop_menu', path: ':shopId/menu', parent: 'shop_home', titleKey: 'routes.shop_menu' },
    { key: 'shop_builder', path: ':shopId/builder', parent: 'shop_home', titleKey: 'routes.shop_builder' },
    { key: 'shop_orders', path: ':shopId/orders', parent: 'shop_home', titleKey: 'routes.shop_orders' },
    { key: 'shop_promos', path: ':shopId/promos', parent: 'shop_home', titleKey: 'routes.shop_promos' },
    { key: 'shop_settings', path: ':shopId/settings', parent: 'shop_home', titleKey: 'routes.shop_settings' },
];

const PUBLISHED = { shop_id: 'shop_test', name: 'МОЙ МАГАЗ', slug: 'moy-magaz', status: 'published' };
const DRAFT = { shop_id: 'shop_test', name: 'МОЙ МАГАЗ', slug: 'moy-magaz', status: 'draft' };

type TestEl = HTMLElement & { shadowRoot: ShadowRoot } & Record<string, unknown>;

function shadow(el: TestEl): ShadowRoot {
    return el.shadowRoot;
}

/** Реальный сгенерированный ru-бандл: только namespace shop нужен тесту. */
async function seedI18n() {
    const response = await fetch('/core/i18n/generated/ru.json');
    if (!response.ok) throw new Error(`seedI18n: ${response.status}`);
    const bundle = (await response.json()) as { shop: Record<string, unknown> };
    const bus = getPlatformBus();
    const prev = bus.getState().i18n.translations.ru;
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale: 'ru', bundle: { ...prev, shop: bundle.shop } });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'ru' });
}

function seedRouter(routeKey: string) {
    const bus = getPlatformBus();
    bus.dispatch(CoreEvents.ROUTER_ROUTES_REGISTERED, { routes: SHOP_ROUTES });
    bus.dispatch(CoreEvents.ROUTER_ROUTE_CHANGED, { routeKey, params: { shopId: 'shop_test' } });
}

function seedShop(row: Record<string, unknown>) {
    getPlatformBus().dispatch('shop/shops/list_loaded', { items: [row], total: 1 });
}

function crumbLabels(el: TestEl): string[] {
    const crumbs = el.shadowRoot.querySelector('platform-breadcrumbs') as TestEl;
    return [...crumbs.shadowRoot.querySelectorAll('.breadcrumb-item')].map((n) => (n.textContent ?? '').trim());
}

describe('shop-page-head: компонент', () => {
    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('shop');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
    });

    it('показывает имя, раздел, статус и крошки «Магазины / имя / раздел»', async () => {
        seedRouter('shop_menu');
        const el = await fixture<TestEl>(html`
            <shop-page-head .shop=${PUBLISHED} shop-id="shop_test" section="Меню"></shop-page-head>
        `);
        await elementUpdated(el);
        expect(shadow(el).querySelector('h1')!.textContent).to.contain('МОЙ МАГАЗ');
        expect(shadow(el).querySelector('.section-label')!.textContent).to.contain('Меню');
        expect(shadow(el).querySelector('.status')!.textContent).to.contain('Опубликован');
        expect(crumbLabels(el)).to.deep.equal(['Магазины', 'МОЙ МАГАЗ', 'Меню']);
    });

    it('published: ссылка на витрину ведёт на /public/s/<slug>', async () => {
        seedRouter('shop_menu');
        const el = await fixture<TestEl>(html`
            <shop-page-head .shop=${PUBLISHED} shop-id="shop_test" section="Меню"></shop-page-head>
        `);
        await elementUpdated(el);
        const link = shadow(el).querySelector('a.storefront') as HTMLAnchorElement | null;
        expect(link).to.exist;
        expect(link!.href).to.contain('/shop/api/v1/public/s/moy-magaz');
        expect(link!.target).to.equal('_blank');
    });

    it('draft: ссылки на витрину нет, статус «Черновик»', async () => {
        seedRouter('shop_menu');
        const el = await fixture<TestEl>(html`
            <shop-page-head .shop=${DRAFT} shop-id="shop_test" section="Меню"></shop-page-head>
        `);
        await elementUpdated(el);
        expect(shadow(el).querySelector('a.storefront')).to.equal(null);
        expect(shadow(el).querySelector('.status')!.textContent).to.contain('Черновик');
    });

    it('без магазина: заголовок — раздел, крошки без trail-сегмента', async () => {
        seedRouter('shop_orders');
        const el = await fixture<TestEl>(html`
            <shop-page-head .shop=${null} shop-id="shop_test" section="Заказы"></shop-page-head>
        `);
        await elementUpdated(el);
        expect(shadow(el).querySelector('h1')!.textContent).to.contain('Заказы');
        expect(shadow(el).querySelector('.section-label')).to.equal(null);
        expect(crumbLabels(el)).to.deep.equal(['Магазины', 'Заказы']);
    });

    it('клик по крошке с именем ведёт в меню этого магазина', async () => {
        seedRouter('shop_orders');
        const el = await fixture<TestEl>(html`
            <shop-page-head .shop=${PUBLISHED} shop-id="shop_test" section="Заказы"></shop-page-head>
        `);
        await elementUpdated(el);
        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeAny((event: { type: string; payload: unknown }) => events.push(event));

        const crumbs = shadow(el).querySelector('platform-breadcrumbs') as TestEl;
        const buttons = crumbs.shadowRoot.querySelectorAll('button.breadcrumb-item');
        (buttons[1] as HTMLButtonElement).click();

        const navigate = events.find((e) => e.type === CoreEvents.ROUTER_NAVIGATE_REQUESTED);
        expect(navigate).to.exist;
        expect(navigate!.payload).to.deep.equal({ routeKey: 'shop_menu', params: { shopId: 'shop_test' } });
    });
});

describe('shop-page-head: интеграция на страницах', () => {
    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('shop');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
    });

    it('orders: шапка показывает имя текущего магазина из коллекции', async () => {
        seedRouter('shop_orders');
        const el = await fixture<TestEl>(html`<shop-orders-page shop-id="shop_test"></shop-orders-page>`);
        seedShop(PUBLISHED);
        await elementUpdated(el);
        const head = shadow(el).querySelector('shop-page-head') as TestEl;
        expect(head).to.exist;
        await elementUpdated(head);
        expect(head.shadowRoot.querySelector('h1')!.textContent).to.contain('МОЙ МАГАЗ');
        expect(crumbLabels(head)).to.deep.equal(['Магазины', 'МОЙ МАГАЗ', 'Заказы']);
    });

    it('promos: шапка показывает имя текущего магазина и раздел', async () => {
        seedRouter('shop_promos');
        const el = await fixture<TestEl>(html`<shop-promos-page shop-id="shop_test"></shop-promos-page>`);
        seedShop(PUBLISHED);
        await elementUpdated(el);
        const head = shadow(el).querySelector('shop-page-head') as TestEl;
        expect(head).to.exist;
        await elementUpdated(head);
        expect(head.shadowRoot.querySelector('h1')!.textContent).to.contain('МОЙ МАГАЗ');
        expect(crumbLabels(head)).to.deep.equal(['Магазины', 'МОЙ МАГАЗ', 'Акции']);
    });

    it('home: «Меню» — primary, разделы магазина — icon-only secondary', async () => {
        seedRouter('shop_home');
        const el = await fixture<TestEl>(html`<shop-home-page></shop-home-page>`);
        seedShop(DRAFT);
        await elementUpdated(el);
        const primary = shadow(el).querySelector('.actions platform-button.primary') as TestEl;
        expect(primary, 'primary-кнопка меню').to.exist;
        expect(primary.getAttribute('variant')).to.equal('primary');
        const navOps = [...shadow(el).querySelectorAll('.nav-ops platform-button')] as TestEl[];
        expect(navOps.length).to.equal(3);
        for (const btn of navOps) {
            expect(btn.getAttribute('variant')).to.equal('secondary');
            expect(btn.hasAttribute('icon-only')).to.equal(true);
        }
    });
});

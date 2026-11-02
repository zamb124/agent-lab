/**
 * shop-settings-page, раздел «Выдача заказов»: три способа выдачи
 * (самовывоз/доставка/в заведении), deep-link ?section=delivery,
 * редактор столов с QR-ссылками, dirty→save с onsite_enabled.
 */

import { fixture, html, expect, elementUpdated } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import {
    shopShopsResource,
    shopUpdateOp,
    shopPublishOp,
    shopSuspendOp,
    shopDomainAddOp,
    shopTelegramConnectOp,
    shopTelegramDisconnectOp,
    shopAiDescribeShopOp,
    shopTablesListOp,
    shopTableCreateOp,
    shopTableUpdateOp,
    shopTableRemoveOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '../../../../apps/shop/ui/pages/shop-settings-page.js';

const FACTORIES = [
    shopShopsResource,
    shopUpdateOp,
    shopPublishOp,
    shopSuspendOp,
    shopDomainAddOp,
    shopTelegramConnectOp,
    shopTelegramDisconnectOp,
    shopAiDescribeShopOp,
    shopTablesListOp,
    shopTableCreateOp,
    shopTableUpdateOp,
    shopTableRemoveOp,
];

const SHOP_ROUTES = [
    { key: 'shop_home', path: '', titleKey: 'routes.shop_home' },
    { key: 'shop_menu', path: ':shopId/menu', parent: 'shop_home', titleKey: 'routes.shop_menu' },
    { key: 'shop_builder', path: ':shopId/builder', parent: 'shop_home', titleKey: 'routes.shop_builder' },
    { key: 'shop_orders', path: ':shopId/orders', parent: 'shop_home', titleKey: 'routes.shop_orders' },
    { key: 'shop_promos', path: ':shopId/promos', parent: 'shop_home', titleKey: 'routes.shop_promos' },
    { key: 'shop_settings', path: ':shopId/settings', parent: 'shop_home', titleKey: 'routes.shop_settings' },
];

const SHOP = {
    shop_id: 'shop_test',
    name: 'Трактир',
    slug: 'traktir',
    status: 'draft',
    delivery_enabled: true,
    pickup_enabled: true,
    onsite_enabled: false,
    delivery_fee_minor: 0,
    min_order_minor: 0,
    working_hours: {},
    products_count: 0,
};

type TestEl = HTMLElement & { shadowRoot: ShadowRoot } & Record<string, unknown>;

function shadow(el: TestEl): ShadowRoot {
    return el.shadowRoot;
}

async function seedI18n() {
    const response = await fetch('/core/i18n/generated/ru.json');
    if (!response.ok) throw new Error(`seedI18n: ${response.status}`);
    const bundle = (await response.json()) as { shop: Record<string, unknown> };
    const bus = getPlatformBus();
    const prev = bus.getState().i18n.translations.ru;
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale: 'ru', bundle: { ...prev, shop: bundle.shop } });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'ru' });
}

function seedRouter(search = '') {
    const bus = getPlatformBus();
    bus.dispatch(CoreEvents.ROUTER_ROUTES_REGISTERED, { routes: SHOP_ROUTES });
    bus.dispatch(CoreEvents.ROUTER_ROUTE_CHANGED, {
        routeKey: 'shop_settings',
        params: { shopId: 'shop_test' },
        search,
    });
}

function seedShop(row: Record<string, unknown>) {
    getPlatformBus().dispatch('shop/shops/list_loaded', { items: [row], total: 1 });
}

function optionCards(el: TestEl): TestEl[] {
    return [...shadow(el).querySelectorAll('.option')] as TestEl[];
}

async function deliveryPage(shop: Record<string, unknown>): Promise<TestEl> {
    const el = await fixture<TestEl>(html`<shop-settings-page shop-id="shop_test"></shop-settings-page>`);
    seedShop(shop);
    await elementUpdated(el);
    return el;
}

describe('shop-settings-page: раздел «Выдача заказов»', () => {
    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('shop');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
        seedRouter('?section=delivery');
    });

    it('рендерит три карточки выдачи: самовывоз, доставка, в заведении', async () => {
        const el = await deliveryPage(SHOP);
        const cards = optionCards(el);
        expect(cards.length).to.equal(3);
        const titles = cards.map((c) => c.querySelector('.option-title')!.textContent!.trim());
        expect(titles).to.deep.equal(['Самовывоз', 'Доставка', 'В заведении']);
        expect(cards[0]!.classList.contains('on'), 'pickup on').to.equal(true);
        expect(cards[1]!.classList.contains('on'), 'delivery on').to.equal(true);
        expect(cards[2]!.classList.contains('on'), 'onsite off').to.equal(false);
    });

    it('включение «В заведении» → dirty-сейв → update_requested с onsite_enabled', async () => {
        const el = await deliveryPage(SHOP);
        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(shopUpdateOp.events.REQUESTED, (event) => events.push(event));

        const onsiteCard = optionCards(el)[2]!;
        const sw = onsiteCard.querySelector('platform-switch') as TestEl;
        sw.dispatchEvent(new CustomEvent('change', { detail: { value: true }, bubbles: true, composed: true }));
        await elementUpdated(el);

        const savebar = shadow(el).querySelector('.savebar');
        expect(savebar, 'savebar после изменения').to.exist;

        const saveBtn = [...savebar!.querySelectorAll('platform-button')]
            .find((b) => b.textContent!.includes('Сохранить')) as TestEl;
        saveBtn.click();
        const requested = events.find((e) => e.type === shopUpdateOp.events.REQUESTED);
        expect(requested).to.exist;
        expect((requested!.payload as Record<string, unknown>).onsite_enabled).to.equal(true);
    });

    it('onsite включён → редактор столов: list_requested + QR-ссылки на витрину', async () => {
        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(shopTablesListOp.events.REQUESTED, (event) => events.push(event));
        const el = await deliveryPage({ ...SHOP, onsite_enabled: true });

        const editor = shadow(el).querySelector('shop-tables-editor') as TestEl;
        expect(editor, 'редактор столов').to.exist;
        await elementUpdated(el);
        await elementUpdated(editor);

        const listed = events.find((e) => e.type === shopTablesListOp.events.REQUESTED);
        expect(listed, 'редактор запросил список столов').to.exist;
        expect((listed!.payload as Record<string, unknown>).shop_id).to.equal('shop_test');

        editor._tables = [
            { shop_table_id: 'shoptable_1', shop_id: 'shop_test', label: 'Стол 5' },
            { shop_table_id: 'shoptable_2', shop_id: 'shop_test', label: 'У окна' },
        ];
        await elementUpdated(editor);

        const rows = [...editor.shadowRoot.querySelectorAll('.table-row')] as TestEl[];
        expect(rows.length).to.equal(2);
        expect(rows[0]!.textContent).to.contain('Стол 5');
        const qrLink = rows[0]!.querySelector('a.icon-btn') as HTMLAnchorElement;
        expect(qrLink.href).to.contain(
            '/shop/api/v1/public/storefront/traktir/tables/shoptable_1/qr.svg'
        );
    });

    it('onsite выключен → редактора столов нет', async () => {
        const el = await deliveryPage(SHOP);
        expect(shadow(el).querySelector('shop-tables-editor')).to.equal(null);
    });

    it('чеклист «Способ выдачи» засчитывает onsite', async () => {
        seedRouter('');
        const el = await fixture<TestEl>(html`<shop-settings-page shop-id="shop_test"></shop-settings-page>`);
        seedShop({
            ...SHOP,
            delivery_enabled: false,
            pickup_enabled: false,
            onsite_enabled: true,
        });
        await elementUpdated(el);
        const orderItem = [...shadow(el).querySelectorAll('.check-item')]
            .find((n) => n.textContent!.includes('Способ выдачи заказов'));
        expect(orderItem).to.exist;
        expect(orderItem!.classList.contains('done'), 'пункт выдачи закрыт onsite').to.equal(true);
    });
});

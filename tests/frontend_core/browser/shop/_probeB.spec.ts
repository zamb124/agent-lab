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
import {
    geoAddressSuggestOp,
    geoAddressNearestOp,
    geoAddressesInZoneOp,
} from '@platform/lib/events/resources/geo-addresses.resource.js';
import {
    geoLayersOp,
    geoLayerFeaturesOp,
    geoMapSlice,
} from '@platform/lib/events/resources/geo-layers.resource.js';

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
    geoLayersOp,
    geoLayerFeaturesOp,
    geoMapSlice,
    geoAddressSuggestOp,
    geoAddressNearestOp,
    geoAddressesInZoneOp,
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

    it('доставка включена → platform-map; «Изменить» → platform.zone_editor → onApply → dirty → save с delivery_zone', async () => {
        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(shopUpdateOp.events.REQUESTED, (event) => events.push(event));
        const modalEvents: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_OPEN, (event) => modalEvents.push(event));
        const el = await deliveryPage(SHOP);

        const map = shadow(el).querySelector('platform-map') as TestEl | null;
        expect(map, 'карта зоны в секции доставки').to.exist;
        expect((map as Record<string, unknown>).config, 'config-driven виджет').to.exist;

        const editBtn = shadow(el).querySelector('.open-editor') as HTMLButtonElement;
        expect(editBtn, 'кнопка редактора зоны').to.exist;
        editBtn.click();
        const opened = modalEvents.find((e) => e.type === CoreEvents.UI_MODAL_OPEN);
        expect(opened, 'открытие platform.zone_editor').to.exist;
        const props = opened!.payload as { kind: string; props: Record<string, unknown> };
        expect(props.kind).to.equal('platform.zone_editor');
        expect(typeof props.props['onApply']).to.equal('function');

        const zone = {
            type: 'Polygon',
            coordinates: [[[37.5, 55.7], [37.7, 55.7], [37.7, 55.8], [37.5, 55.8], [37.5, 55.7]]],
        };
        (props.props['onApply'] as (z: unknown) => void)(zone);
        await elementUpdated(el);

        const savebar = shadow(el).querySelector('.savebar');
        expect(savebar, 'onApply → dirty-сейв').to.exist;
        const saveBtn = [...savebar!.querySelectorAll('platform-button')]
            .find((b) => b.textContent!.includes('Сохранить')) as TestEl;
        saveBtn.click();
        const requested = events.find((e) => e.type === shopUpdateOp.events.REQUESTED);
        expect(requested).to.exist;
        expect((requested!.payload as Record<string, unknown>).delivery_zone)
            .to.deep.equal(zone);
    });

    it('доставка выключена → platform-map не рендерится', async () => {
        const el = await deliveryPage({ ...SHOP, delivery_enabled: false });
        expect(shadow(el).querySelector('platform-map')).to.equal(null);
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

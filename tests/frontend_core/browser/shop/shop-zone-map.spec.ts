/**
 * shop-zone-map — редактор зоны доставки на Leaflet/OSM.
 *
 * Реальный браузер: Leaflet монтируется настоящий (динамический import
 * резолвится сборкой), полигон рисуется событиями карты как в проде —
 * клики → вершины → «Замкнуть» → GeoJSON Polygon в `zone-changed`.
 */

import { fixture, html, expect, elementUpdated, aTimeout } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import {
    shopShopsResource,
    shopGeocodeOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '../../../../apps/shop/ui/components/shop-zone-map.js';

const FACTORIES = [shopShopsResource, shopGeocodeOp];

const ZONE = {
    type: 'Polygon',
    coordinates: [
        [
            [37.5, 55.7],
            [37.7, 55.7],
            [37.7, 55.8],
            [37.5, 55.8],
            [37.5, 55.7],
        ],
    ],
};

type TestEl = HTMLElement & {
    shadowRoot: ShadowRoot;
    zone: Record<string, unknown> | null;
    address: string;
    shopId: string;
    _drawing: boolean;
    _draftPoints: Array<[number, number]>;
    _map: { fire: (type: string, ev: unknown) => void; _loaded: boolean };
};

async function seedI18n() {
    const response = await fetch('/core/i18n/generated/ru.json');
    if (!response.ok) throw new Error(`seedI18n: ${response.status}`);
    const bundle = (await response.json()) as { shop: Record<string, unknown> };
    const bus = getPlatformBus();
    const prev = bus.getState().i18n.translations.ru;
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale: 'ru', bundle: { ...prev, shop: bundle.shop } });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'ru' });
}

function btn(el: TestEl, text: string): HTMLButtonElement {
    const found = [...el.shadowRoot.querySelectorAll('platform-button')].find((b) =>
        b.textContent!.includes(text),
    ) as HTMLButtonElement | undefined;
    expect(found, `кнопка «${text}»`).to.exist;
    return found!;
}

async function mapReady(el: TestEl): Promise<void> {
    // Leaflet грузится динамическим импортом — ждём реальный init.
    for (let i = 0; i < 50 && !el._map?._loaded; i++) await aTimeout(20);
    expect(el._map, 'карта инициализирована').to.exist;
}

async function clickMap(el: TestEl, lat: number, lng: number): Promise<void> {
    el._map.fire('click', { latlng: { lat, lng } });
    await elementUpdated(el);
}

describe('shop-zone-map', () => {
    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('shop');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
    });

    it('пустая зона → «Нарисовать зону», без «Очистить»', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        await mapReady(el);
        expect(btn(el, 'Нарисовать зону')).to.exist;
        const clear = [...el.shadowRoot.querySelectorAll('platform-button')].find((b) =>
            b.textContent!.includes('Очистить'),
        );
        expect(clear).to.equal(undefined);
    });

    it('готовый полигон → overlay pane + «Перерисовать» + «Очистить»', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        el.zone = ZONE;
        await mapReady(el);
        await elementUpdated(el);
        const polygon = (el as unknown as { _polygon: { _latlngs: unknown[] } })._polygon;
        expect(polygon, 'полигон добавлен слоем на карту').to.exist;
        const ring = polygon._latlngs[0] as unknown[];
        expect(ring.length, 'кольцо полигона на карте').to.be.greaterThanOrEqual(4);
        expect(btn(el, 'Перерисовать зону')).to.exist;
        expect(btn(el, 'Очистить')).to.exist;
    });

    it('рисование: 3 клика → «Замкнуть» → zone-changed с замкнутым Polygon', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        await mapReady(el);
        const events: Array<Record<string, unknown>> = [];
        el.addEventListener('zone-changed', (e) =>
            events.push((e as CustomEvent).detail as Record<string, unknown>),
        );

        btn(el, 'Нарисовать зону').click();
        await elementUpdated(el);
        expect(el._drawing).to.equal(true);

        await clickMap(el, 55.7, 37.5);
        await clickMap(el, 55.7, 37.7);
        await clickMap(el, 55.8, 37.6);
        expect(el._draftPoints.length).to.equal(3);

        btn(el, 'Замкнуть зону').click();
        await elementUpdated(el);

        expect(events.length).to.equal(1);
        const zone = events[0]!['zone'] as {
            type: string;
            coordinates: number[][][];
        };
        expect(zone.type).to.equal('Polygon');
        const ring = zone.coordinates[0]!;
        expect(ring.length).to.equal(4); // замкнуто: первая точка повторена
        expect(ring[0]).to.deep.equal(ring[ring.length - 1]);
        expect(ring[0]).to.deep.equal([37.5, 55.7]); // GeoJSON [lng, lat]
        expect(el._drawing).to.equal(false);
    });

    it('«Отмена» в режиме рисования → без zone-changed, карта чистая', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        await mapReady(el);
        const events: unknown[] = [];
        el.addEventListener('zone-changed', (e) => events.push(e));

        btn(el, 'Нарисовать зону').click();
        await clickMap(el, 55.7, 37.5);
        btn(el, 'Отмена').click();
        await elementUpdated(el);
        expect(el._drawing).to.equal(false);
        expect(events.length).to.equal(0);
    });

    it('«Очистить» → zone-changed с пустым объектом', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        el.zone = ZONE;
        await mapReady(el);
        await elementUpdated(el);
        const events: Array<Record<string, unknown>> = [];
        el.addEventListener('zone-changed', (e) =>
            events.push((e as CustomEvent).detail as Record<string, unknown>),
        );

        btn(el, 'Очистить').click();
        await elementUpdated(el);
        expect(events.length).to.equal(1);
        expect(events[0]!['zone']).to.deep.equal({});
        expect(el.shadowRoot.querySelector('.leaflet-overlay-pane path')).to.equal(null);
    });

    it('«Найти магазин на карте» → shop/shop_geocode_requested с адресом', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        el.address = 'Москва, Тверская 1';
        el.shopId = 'shop_test';
        await mapReady(el);
        await elementUpdated(el);

        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(shopGeocodeOp.events.REQUESTED, (event) =>
            events.push(event),
        );
        btn(el, 'Найти магазин на карте').click();
        await aTimeout(50);

        const requested = events.find((e) => e.type === shopGeocodeOp.events.REQUESTED);
        expect(requested, 'geocode op запрошен').to.exist;
        const payload = requested!.payload as Record<string, unknown>;
        expect(payload['shop_id']).to.equal('shop_test');
        expect(payload['address']).to.equal('Москва, Тверская 1');
    });
});

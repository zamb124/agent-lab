/**
 * shop-zone-map — превью зоны доставки на MapLibre + открытие редактора.
 *
 * Реальный браузер: MapLibre монтируется настоящий (динамический import
 * резолвится сборкой), стиль базы — WTR-стаб по боевому URL
 * /geo/api/v1/tiles/style.json, полигон зоны — настоящий geojson-source
 * на карте. Клик «Изменить» — настоящий openModal('shop.zone_editor')
 * через UI_MODAL_OPEN; результат редактора приходит в onApply → zone-changed.
 */

import { fixture, html, expect, elementUpdated, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import {
    shopShopsResource,
    shopGeocodeOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '../../../../apps/shop/ui/components/shop-zone-map.js';
import '../../../../apps/shop/ui/modals/shop-zone-editor-modal.js';

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

type TestMap = {
    isStyleLoaded(): boolean;
    getSource(id: string): { _data?: { geojson?: { features?: unknown[] } } } | undefined;
    getLayer(id: string): unknown;
};

type TestEl = HTMLElement & {
    shadowRoot: ShadowRoot;
    zone: Record<string, unknown> | null;
    address: string;
    shopId: string;
    _map: TestMap | null;
};

async function seedI18n() {
    // Ждём settle штатного i18n-эффекта (bootstrap → /api/i18n/<locale>),
    // иначе его async-ответ перетирает locale/translations после сидирования.
    const bus = getPlatformBus();
    await waitUntil(
        () => {
            const i18n = bus.getState().i18n;
            if (i18n.loading) return false;
            const bundle = i18n.translations[i18n.locale];
            return Boolean(bundle && typeof bundle === 'object' && 'platform' in bundle);
        },
        'i18n bootstrap settled',
        { timeout: 15_000 },
    );
    const response = await fetch('/core/i18n/generated/ru.json');
    if (!response.ok) throw new Error(`seedI18n: ${response.status}`);
    const bundle = (await response.json()) as { shop: Record<string, unknown> };
    const prev = bus.getState().i18n.translations.ru;
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, { locale: 'ru', bundle: { ...prev, shop: bundle.shop } });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'ru' });
}

function openBtn(el: TestEl): HTMLButtonElement {
    const found = el.shadowRoot.querySelector<HTMLButtonElement>('.open-editor');
    expect(found, 'кнопка редактора на превью').to.exist;
    return found!;
}

async function mapReady(el: TestEl): Promise<void> {
    // MapLibre грузится динамическим импортом — ждём карту и стиль.
    for (let i = 0; i < 100 && !(el._map && el._map.isStyleLoaded()); i++) await aTimeout(30);
    expect(el._map, 'карта инициализирована').to.exist;
    expect(el._map!.isStyleLoaded(), 'стиль базы загружен').to.equal(true);
}

/** Число фич в geojson-source зоны на карте. */
function zoneFeatureCount(el: TestEl): number {
    const source = el._map!.getSource('zone');
    return source?._data?.geojson?.features?.length ?? 0;
}

describe('shop-zone-map', () => {
    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('shop');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
    });

    it('пустая зона → бейдж «зона не задана» + «Задать зону»', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        await mapReady(el);
        await elementUpdated(el);
        // maplibre-gl.css обязан жить в shadow root — head-стили сквозь boundary не идут.
        const link = el.shadowRoot.querySelector<HTMLLinkElement>('link[href*="maplibre-gl.css"]');
        expect(link, 'maplibre-gl.css в shadow root').to.exist;
        const canvas = el.shadowRoot.querySelector<HTMLElement>('canvas.maplibregl-canvas');
        expect(canvas, 'canvas карты смонтирован').to.exist;
        expect(el.shadowRoot.querySelector('.empty-badge'), 'бейдж пустой зоны').to.exist;
        expect(openBtn(el).textContent).to.include('Задать зону');
    });

    it('готовый полигон → geojson-слой на карте + «Изменить зону», без бейджа', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        el.zone = ZONE;
        await mapReady(el);
        await elementUpdated(el);
        expect(zoneFeatureCount(el), 'полигон в geojson-source карты').to.equal(1);
        expect(el._map!.getLayer('zone-fill'), 'fill-слой зоны').to.exist;
        expect(el._map!.getLayer('zone-line'), 'outline-слой зоны').to.exist;
        expect(el.shadowRoot.querySelector('.empty-badge')).to.equal(null);
        expect(openBtn(el).textContent).to.include('Изменить зону');
    });

    it('«Изменить зону» → UI_MODAL_OPEN с kind shop.zone_editor и props', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        el.zone = ZONE;
        el.address = 'Москва, Тверская 1';
        el.shopId = 'shop_test';
        await mapReady(el);
        await elementUpdated(el);

        const opened: Array<{ kind: string; props: Record<string, unknown> }> = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_OPEN, (event) =>
            opened.push(event.payload as { kind: string; props: Record<string, unknown> }),
        );
        openBtn(el).click();
        await aTimeout(30);

        expect(opened.length).to.equal(1);
        expect(opened[0]!.kind).to.equal('shop.zone_editor');
        const props = opened[0]!.props;
        expect(props['zone']).to.deep.equal(ZONE);
        expect(props['address']).to.equal('Москва, Тверская 1');
        expect(props['shop_id'] ?? props['shopId']).to.equal('shop_test');
        expect(typeof props['onApply']).to.equal('function');
    });

    it('onApply из модалки → zone-changed + полигон перерисован', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        await mapReady(el);
        const opened: Array<{ props: Record<string, unknown> }> = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_OPEN, (event) =>
            opened.push(event.payload as { props: Record<string, unknown> }),
        );
        openBtn(el).click();
        await aTimeout(30);
        const onApply = opened[0]!.props['onApply'] as (z: Record<string, unknown>) => void;
        expect(onApply, 'onApply передан в модалку').to.exist;

        const events: Array<Record<string, unknown>> = [];
        el.addEventListener('zone-changed', (e) =>
            events.push((e as CustomEvent).detail as Record<string, unknown>),
        );
        onApply(ZONE);
        await elementUpdated(el);

        expect(events.length).to.equal(1);
        expect(events[0]!['zone']).to.deep.equal(ZONE);
        expect(el.zone).to.deep.equal(ZONE);
        expect(zoneFeatureCount(el), 'полигон перерисован после onApply').to.equal(1);
    });

    it('onApply с {} → zone-changed с пустым объектом, полигон снят', async () => {
        const el = await fixture<TestEl>(html`<shop-zone-map></shop-zone-map>`);
        el.zone = ZONE;
        await mapReady(el);
        await elementUpdated(el);
        const opened: Array<{ props: Record<string, unknown> }> = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_OPEN, (event) =>
            opened.push(event.payload as { props: Record<string, unknown> }),
        );
        openBtn(el).click();
        await aTimeout(30);
        const onApply = opened[0]!.props['onApply'] as (z: Record<string, unknown>) => void;

        const events: Array<Record<string, unknown>> = [];
        el.addEventListener('zone-changed', (e) =>
            events.push((e as CustomEvent).detail as Record<string, unknown>),
        );
        onApply({});
        await elementUpdated(el);

        expect(events[0]!['zone']).to.deep.equal({});
        expect(zoneFeatureCount(el), 'geojson-source очищен').to.equal(0);
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
        const locate = [...el.shadowRoot.querySelectorAll('platform-button')].find((b) =>
            b.textContent!.includes('Найти магазин'),
        ) as HTMLElement | undefined;
        expect(locate, 'кнопка геолокации').to.exist;
        locate!.click();
        await aTimeout(50);

        const requested = events.find((e) => e.type === shopGeocodeOp.events.REQUESTED);
        expect(requested, 'geocode op запрошен').to.exist;
        const payload = requested!.payload as Record<string, unknown>;
        expect(payload['shop_id']).to.equal('shop_test');
        expect(payload['address']).to.equal('Москва, Тверская 1');
    });
});

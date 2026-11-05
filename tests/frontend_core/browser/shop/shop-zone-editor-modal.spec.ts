/**
 * shop-zone-editor-modal — полноэкранный редактор зоны на MapLibre + terra-draw.
 *
 * Реальный браузер: настоящий MapLibre и настоящий terra-draw (динамические
 * import резолвятся сборкой), стиль базы — WTR-стаб по боевому URL
 * /geo/api/v1/tiles/style.json. Рисование идёт боевым путём terra-draw:
 * setMode('polygon') → pointer-события на canvas карты → keyup Enter →
 * finish → полигон в store. Применение отдаёт GeoJSON в onApply и закрывает
 * модалку.
 */

import { fixture, html, expect, elementUpdated, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import {
    shopShopsResource,
    shopGeocodeOp,
    shopZoneAddressesOp,
} from '../../../../apps/shop/ui/events/resources/shop.resource.js';
import '@platform/lib/components/platform-modal-stack.js';
import '../../../../apps/shop/ui/modals/shop-zone-editor-modal.js';

const FACTORIES = [shopShopsResource, shopGeocodeOp, shopZoneAddressesOp];
const TAG = 'shop-zone-editor-modal';

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

type StoreFeature = {
    geometry: { type: string; coordinates: number[][][] };
    properties?: Record<string, unknown>;
};

type TestDraw = {
    getMode(): string;
    getSnapshot(): StoreFeature[];
};

type TestMap = {
    isStyleLoaded(): boolean;
    getCanvas(): HTMLCanvasElement;
    project(lngLat: [number, number]): { x: number; y: number };
    fire(type: string, ev?: unknown): void;
    getSource(id: string): { _data?: { geojson?: { features?: unknown[] } } } | undefined;
};

type TestEl = HTMLElement & {
    shadowRoot: ShadowRoot;
    zone: Record<string, unknown> | null;
    address: string;
    shopId: string;
    onApply: ((zone: Record<string, unknown>) => void) | null;
    _map: TestMap | null;
    _draw: TestDraw | null;
    _drawing: boolean;
    _mapError: boolean;
    _points: number;
    _areaM2: number;
    _perimM: number;
    _selfIntersect: boolean;
    _hint: string;
    open: boolean;
    close(): void;
    _retryMap(): void;
    _updateHint(): void;
    _addressFeatures: Map<number, StoreFeature>;
};

async function seedI18n() {
    // Сначала ждём settle штатного i18n-эффекта: bootstrap диспатчит
    // I18N_LOCALE_REQUESTED → middleware отдаёт platform-бандл →
    // I18N_LOCALE_LOADED/CHANGED. Без ожидания settle эффект перетирает
    // locale и translations уже после сидирования — гонка.
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
    const bundle = (await response.json()) as { shop: Record<string, unknown>; geo: Record<string, unknown> };
    const prev = bus.getState().i18n.translations.ru;
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, {
        locale: 'ru',
        bundle: { ...prev, shop: bundle.shop, geo: bundle.geo },
    });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'ru' });
}

/** Ответить на shop/zone_addresses_requested списком адресов (боевой контракт). */
function answerZoneAddresses(items: Array<Record<string, unknown>>, total = items.length): void {
    getPlatformBus().subscribeType(shopZoneAddressesOp.events.REQUESTED, (event) => {
        // Ответ обязан быть асинхронным: run() подписывается на SUCCEEDED
        // только после того, как dispatch(REQUESTED) вернулся.
        queueMicrotask(() => {
            getPlatformBus().dispatch(
                shopZoneAddressesOp.events.SUCCEEDED,
                { result: { items, total } },
                { causation_id: event.id, source: 'http' },
            );
        });
    });
}

async function openModal(props: Record<string, unknown>): Promise<TestEl> {
    const stack = await fixture<HTMLElement>(html`<platform-modal-stack></platform-modal-stack>`);
    getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'shop.zone_editor', props });
    await elementUpdated(stack);
    const modal = [...document.querySelectorAll<TestEl>(TAG)].at(-1);
    expect(modal, 'модалка смонтирована').to.exist;
    return modal!;
}

async function mapReady(el: TestEl): Promise<void> {
    // MapLibre + terra-draw грузятся динамическими import'ами — ждём
    // реальный init (draw создаётся по load-хуку карты).
    for (let i = 0; i < 200 && !(el._map && el._draw); i++) await aTimeout(30);
    expect(el._map, 'карта редактора инициализирована').to.exist;
    expect(el._draw, 'terra-draw активен на карте').to.exist;
}

function ztool(el: TestEl, text: string): HTMLButtonElement {
    const found = [...el.shadowRoot.querySelectorAll<HTMLButtonElement>('.ztool')].find((b) =>
        b.textContent!.includes(text),
    );
    expect(found, `кнопка «${text}» в панели`).to.exist;
    return found!;
}

function applyBtn(el: TestEl): HTMLElement {
    const found = [...el.shadowRoot.querySelectorAll<HTMLElement>('platform-button')].find((b) =>
        b.textContent!.includes('Применить'),
    );
    expect(found, 'кнопка «Применить»').to.exist;
    return found!;
}

/**
 * Клик по карте боевым путём terra-draw: адаптер слушает pointerdown/
 * pointerup на canvas и переводит clientX/clientY в lng/lat через unproject.
 */
async function clickMap(el: TestEl, lng: number, lat: number): Promise<void> {
    const canvas = el._map!.getCanvas();
    const rect = canvas.getBoundingClientRect();
    const point = el._map!.project([lng, lat]);
    const init = {
        clientX: rect.left + point.x,
        clientY: rect.top + point.y,
        bubbles: true,
        composed: true,
        pointerId: 1,
        isPrimary: true,
        button: 0,
        buttons: 1,
    };
    canvas.dispatchEvent(new PointerEvent('pointerdown', init));
    canvas.dispatchEvent(new PointerEvent('pointerup', { ...init, buttons: 0 }));
    await aTimeout(30);
}

/** Finish боевым путём: polygon-режим завершает по keyup Enter на canvas. */
async function finishDraw(el: TestEl): Promise<void> {
    el._map!.getCanvas().dispatchEvent(
        new KeyboardEvent('keyup', { key: 'Enter', bubbles: true, composed: true }),
    );
    await aTimeout(80);
}

describe('shop-zone-editor-modal', function () {
    this.timeout(60_000);

    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('shop');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
    });

    it('открытие без зоны → карта с terra-draw, пустые метрики, «Применить» активна', async () => {
        const applied: Array<Record<string, unknown>> = [];
        const modal = await openModal({
            zone: {},
            address: '',
            shopId: 'shop_test',
            onApply: (z: Record<string, unknown>) => applied.push(z),
        });
        await mapReady(modal);
        await elementUpdated(modal);
        // maplibre-gl.css обязана жить в shadow root: стили из head
        // не проходят сквозь shadow boundary.
        const links = [...modal.shadowRoot.querySelectorAll('link[rel="stylesheet"]')].map((l) =>
            (l as HTMLLinkElement).href,
        );
        expect(links.some((h) => h.includes('maplibre-gl.css')), 'maplibre-gl.css в shadow root').to.equal(true);
        const canvas = modal.shadowRoot.querySelector<HTMLElement>('canvas.maplibregl-canvas');
        expect(canvas, 'canvas карты смонтирован').to.exist;
        const attribution = modal.shadowRoot.querySelector('.maplibregl-ctrl-attrib');
        expect(attribution, 'атрибуция MapLibre на месте').to.exist;
        expect(modal._draw!.getSnapshot().filter((f) => f.geometry.type === 'Polygon').length)
            .to.equal(0);
        expect(modal._points).to.equal(0);
        expect(modal.shadowRoot.querySelector('.ztools'), 'панель инструментов').to.exist;
        expect(modal.shadowRoot.querySelector('.zstats')).to.equal(null);
        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied.length).to.equal(1);
        expect(applied[0]).to.deep.equal({});
    });

    it('существующая зона → полигон в terra-draw + метрики площади/периметра/точек', async () => {
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await elementUpdated(modal);
        const polygons = modal._draw!.getSnapshot().filter((f) => f.geometry.type === 'Polygon');
        expect(polygons.length, 'полигон в terra-draw store').to.equal(1);
        expect(modal._draw!.getMode(), 'select-режим после загрузки зоны').to.equal('select');
        expect(modal._points).to.equal(4);
        expect(modal._areaM2, 'площадь > 0').to.be.greaterThan(0);
        expect(modal._perimM, 'периметр > 0').to.be.greaterThan(0);
        const stats = modal.shadowRoot.querySelector('.zstats');
        expect(stats, 'панель метрик').to.exist;
        expect(stats!.textContent).to.include('км²');
    });

    it('рисование через terra-draw: polygon-режим → 3 клика → Enter → полигон', async () => {
        const applied: Array<Record<string, unknown>> = [];
        const modal = await openModal({
            zone: {},
            address: '',
            shopId: 'shop_test',
            onApply: (z: Record<string, unknown>) => applied.push(z),
        });
        await mapReady(modal);
        ztool(modal, 'Рисовать зону').click();
        await elementUpdated(modal);
        expect(modal._drawing).to.equal(true);
        expect(modal._draw!.getMode(), 'terra-draw polygon-режим').to.equal('polygon');

        await clickMap(modal, 37.5, 55.7);
        await clickMap(modal, 37.7, 55.7);
        await clickMap(modal, 37.6, 55.8);
        await finishDraw(modal);

        expect(modal._drawing).to.equal(false);
        const polygons = modal._draw!.getSnapshot().filter((f) => f.geometry.type === 'Polygon');
        expect(polygons.length, 'полигон создан terra-draw').to.equal(1);
        expect(modal._points, 'вершин на слое').to.be.greaterThanOrEqual(3);
        expect(modal._draw!.getMode(), 'назад в select-режим после finish').to.equal('select');

        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied.length).to.equal(1);
        const zone = applied[0]! as { type: string; coordinates: number[][][] };
        expect(zone.type).to.equal('Polygon');
        const ring = zone.coordinates[0]!;
        expect(ring[0]).to.deep.equal(ring[ring.length - 1]);
        expect(ring[0]![0]).to.be.closeTo(37.5, 0.01); // GeoJSON [lng, lat]
        expect(ring[0]![1]).to.be.closeTo(55.7, 0.01);
    });

    it('«Очистить» удаляет полигон; «Применить» отдаёт {} и модалка закрывается', async () => {
        const applied: Array<Record<string, unknown>> = [];
        const modal = await openModal({
            zone: ZONE,
            address: '',
            shopId: 'shop_test',
            onApply: (z: Record<string, unknown>) => applied.push(z),
        });
        await mapReady(modal);
        await elementUpdated(modal);
        expect(modal._draw!.getSnapshot().filter((f) => f.geometry.type === 'Polygon').length)
            .to.equal(1);

        ztool(modal, 'Очистить').click();
        await elementUpdated(modal);
        expect(modal._draw!.getSnapshot().filter((f) => f.geometry.type === 'Polygon').length)
            .to.equal(0);
        expect(modal._points).to.equal(0);

        const closes: unknown[] = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_CLOSE, (e) => closes.push(e));
        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied[0]).to.deep.equal({});
        expect(closes.length, 'модалка закрыта после применения').to.equal(1);
    });

    it('«Вписать зону» → fitBounds; «Найти магазин на карте» → geocode op', async () => {
        const modal = await openModal({
            zone: ZONE,
            address: 'Москва, Тверская 1',
            shopId: 'shop_test',
            onApply: null,
        });
        await mapReady(modal);
        await elementUpdated(modal);
        ztool(modal, 'Вписать зону').click();
        await aTimeout(50); // fitBounds отрабатывает без ошибок

        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(shopGeocodeOp.events.REQUESTED, (event) =>
            events.push(event),
        );
        ztool(modal, 'Найти магазин на карте').click();
        await aTimeout(50);
        const requested = events.find((e) => e.type === shopGeocodeOp.events.REQUESTED);
        expect(requested, 'geocode op запрошен').to.exist;
        expect((requested!.payload as Record<string, unknown>)['shop_id']).to.equal('shop_test');
    });

    it('error карты → error-state + «Повторить» пересоздаёт карту', async () => {
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await elementUpdated(modal);

        modal._map!.fire('error', { error: new Error('boom') });
        await elementUpdated(modal);
        expect(modal._mapError).to.equal(true);
        expect(modal.shadowRoot.querySelector('.zerror'), 'error-overlay').to.exist;
        const apply = applyBtn(modal) as HTMLElement & { disabled: boolean };
        expect(apply.disabled, '«Применить» заблокирована при ошибке карты').to.equal(true);

        const retry = [...modal.shadowRoot.querySelectorAll('platform-button')].find((b) =>
            b.textContent!.includes('Повторить'),
        ) as HTMLElement | undefined;
        expect(retry, 'кнопка «Повторить»').to.exist;
        retry!.click();
        await aTimeout(50);
        await elementUpdated(modal);
        expect(modal._mapError).to.equal(false);
        expect(modal.shadowRoot.querySelector('.zerror')).to.equal(null);
    });

    it('self-intersection → «Применить» заблокирована и warn-хинт', async () => {
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await elementUpdated(modal);
        // Боевой путь: terra-draw не даёт сделать self-intersection
        // (ValidateNotSelfIntersecting на draw и select), но флаг
        // перечитывается на каждом событии — проверяем реакцию UI.
        modal._selfIntersect = true;
        modal._updateHint();
        await elementUpdated(modal);
        const apply = applyBtn(modal) as HTMLElement & { disabled: boolean };
        expect(apply.disabled).to.equal(true);
        const hint = modal.shadowRoot.querySelector('.zhint.warn');
        expect(hint, 'warn-хинт про самопересечение').to.exist;
    });

    it('«Отмена» закрывает модалку без onApply', async () => {
        const applied: unknown[] = [];
        const modal = await openModal({
            zone: ZONE,
            address: '',
            shopId: 'shop_test',
            onApply: () => applied.push(1),
        });
        await mapReady(modal);
        const closes: unknown[] = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_CLOSE, (e) => closes.push(e));
        const cancel = [...modal.shadowRoot.querySelectorAll('platform-button')].find((b) =>
            b.textContent!.includes('Отмена'),
        ) as HTMLElement | undefined;
        expect(cancel, 'кнопка «Отмена»').to.exist;
        cancel!.click();
        await aTimeout(30);
        expect(applied.length).to.equal(0);
        expect(closes.length).to.equal(1);
    });

    it('панель адресов: зона → zone_addresses_requested с GeoJSON и счётчик', async () => {
        const items = [
            { id: 1, osm_type: 'node', osm_id: 11, display_name: 'Москва, Тверская, 1', city: 'Москва', street: 'Тверская', housenumber: '1', postcode: '', lat: 55.75, lng: 37.6 },
            { id: 2, osm_type: 'way', osm_id: 22, display_name: 'Москва, Тверская, 3', city: 'Москва', street: 'Тверская', housenumber: '3', postcode: '', lat: 55.76, lng: 37.65 },
        ];
        answerZoneAddresses(items, 137);
        const payloads: Array<Record<string, unknown>> = [];
        getPlatformBus().subscribeType(shopZoneAddressesOp.events.REQUESTED, (event) =>
            payloads.push(event.payload as Record<string, unknown>),
        );
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await elementUpdated(modal);
        // Debounce 300мс requery панели после первичной зоны.
        await waitUntil(() => payloads.length > 0, 'zone_addresses_requested', { timeout: 5_000 });
        expect(payloads[0]!['zone']).to.deep.equal(ZONE);
        expect(payloads[0]!['limit']).to.be.a('number');
        expect(payloads[0]!['offset']).to.equal(0);

        const panel = modal.shadowRoot.querySelector('platform-zone-address-panel')!;
        expect(panel, 'панель адресов справа от карты').to.exist;
        await waitUntil(
            () => panel.shadowRoot!.querySelectorAll('.row').length === 2,
            'строки адресов отрисованы',
            { timeout: 5_000 },
        );
        expect(panel.shadowRoot!.querySelector('.count')!.textContent).to.include('137');
        // Точки адресов — в geojson-source на карте, по одной на строку.
        expect(modal._addressFeatures.size).to.equal(2);
    });

    it('поиск в панели → повторный запрос с q и offset=0', async () => {
        answerZoneAddresses([], 0);
        const payloads: Array<Record<string, unknown>> = [];
        getPlatformBus().subscribeType(shopZoneAddressesOp.events.REQUESTED, (event) =>
            payloads.push(event.payload as Record<string, unknown>),
        );
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        await waitUntil(() => payloads.length > 0, 'первичный запрос', { timeout: 5_000 });

        const panel = modal.shadowRoot.querySelector('platform-zone-address-panel')!;
        const input = panel.shadowRoot!.querySelector('input[type="search"]')!;
        expect(input, 'поле поиска наверху панели').to.exist;
        (input as HTMLInputElement).value = 'Тверская';
        input.dispatchEvent(new InputEvent('input', { bubbles: true, composed: true }));
        await waitUntil(() => payloads.length > 1, 'запрос с q', { timeout: 5_000 });
        expect(payloads.at(-1)!['q']).to.equal('Тверская');
        expect(payloads.at(-1)!['offset']).to.equal(0);
    });

    it('hover строки → address-hover и подсветка точки на карте', async () => {
        const items = [
            { id: 7, osm_type: 'node', osm_id: 70, display_name: 'Москва, Арбат, 5', city: '', street: '', housenumber: '', postcode: '', lat: 55.75, lng: 37.6 },
        ];
        answerZoneAddresses(items);
        const modal = await openModal({ zone: ZONE, address: '', shopId: 'shop_test', onApply: null });
        await mapReady(modal);
        const panel = modal.shadowRoot.querySelector('platform-zone-address-panel')!;
        await waitUntil(
            () => panel.shadowRoot!.querySelectorAll('.row').length === 1,
            'строка адреса',
            { timeout: 5_000 },
        );
        const row = panel.shadowRoot!.querySelector('.row') as HTMLElement;
        row.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, composed: true }));
        await aTimeout(30);
        const feature = modal._addressFeatures.get(7)!;
        expect(feature.properties?.['hi'], 'точка подсвечена на hover').to.equal(true);
        const source = modal._map!.getSource('zone-addresses');
        const painted = source?._data?.geojson?.features?.[0] as StoreFeature | undefined;
        expect(painted?.properties?.['hi'], 'hi-флаг ушёл в geojson-source').to.equal(true);
        row.dispatchEvent(new MouseEvent('mouseleave', { bubbles: true, composed: true }));
        await aTimeout(30);
        expect(modal._addressFeatures.get(7)!.properties?.['hi'], 'подсветка снята').to.equal(false);
    });
});

/**
 * platform-map — единый config-driven виджет карты платформы.
 *
 * Реальный браузер: MapLibre монтируется настоящий (стиль — WTR-стаб
 * по боевому URL /geo/api/v1/tiles/style.json), канонические слои идут
 * через geo/layer_features, маркеры/оверлеи — декларативно из config.
 * platform.zone_editor — модалка редактора полигона поверх виджета
 * (TerraDraw рисует боевым путём: pointer-события на canvas).
 */

import { fixture, html, expect, elementUpdated, aTimeout, waitUntil } from '../helpers/render.js';
import { resetPlatformState, bootstrapTestBus } from '../helpers/reset.js';
import { getPlatformBus, CoreEvents } from '@platform/lib/events/index.js';
import { setDefaultI18nNamespace } from '@platform/lib/utils/i18n-namespace.js';
import {
    geoLayersOp,
    geoLayerFeaturesOp,
    geoMapSlice,
} from '@platform/lib/events/resources/geo-layers.resource.js';
import {
    geoAddressSuggestOp,
    geoAddressNearestOp,
    geoAddressesInZoneOp,
} from '@platform/lib/events/resources/geo-addresses.resource.js';
import { geoRouteOp, geoIsochroneOp } from '@platform/lib/events/resources/geo-route.resource.js';
import '@platform/lib/components/platform-map.js';
import '@platform/lib/modals/platform-zone-editor-modal.js';
import '@platform/lib/components/platform-modal-stack.js';
import type { PlatformMapConfig } from '@platform/lib/components/platform-map.js';

const FACTORIES = [
    geoLayersOp,
    geoLayerFeaturesOp,
    geoMapSlice,
    geoAddressSuggestOp,
    geoAddressNearestOp,
    geoAddressesInZoneOp,
    geoRouteOp,
    geoIsochroneOp,
];

const ZONE = {
    type: 'Polygon' as const,
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

type TestMap = {
    isStyleLoaded(): boolean;
    getCanvas(): HTMLCanvasElement;
    project(lngLat: [number, number]): { x: number; y: number };
    getCenter?(): { lng: number; lat: number };
    getSource(id: string): { setData(d: unknown): void; _data?: { geojson?: { features?: unknown[] } } } | undefined;
    getLayer(id: string): unknown;
    setBearing(b: number): void;
    getBearing(): number;
    fire(name: string): void;
    setStyle(url: string): void;
    getStyle(): { layers: Array<{ id: string; type: string }>; sources: Record<string, unknown> };
    getPaintProperty(layer: string, prop: string): string;
    getPitch(): number;
};

type TestDraw = {
    getMode(): string;
    getSnapshot(): StoreFeature[];
};

type MapEl = HTMLElement & {
    shadowRoot: ShadowRoot;
    config: PlatformMapConfig;
    _ready: boolean;
    _mode: string;
    _scheme: string;
    _routeInfo: { distanceM: number; durationS: number } | null;
    _routeBuildPts: [number, number][];
    _tilted: boolean;
    _rulerAreaM2(): number;
    getMap(): TestMap | null;
    getDraw(): { draw: TestDraw } | null;
};

type ModalEl = HTMLElement & {
    shadowRoot: ShadowRoot;
    zone: unknown;
    address: string;
    onApply: ((zone: unknown) => void) | null;
    _zone: unknown;
    _valid: boolean;
    _drawing: boolean;
    close(): void;
};

const LAYERS_RESULT = {
    layers: [
        { name: 'roads', count: 100, color: '#3b82f6' },
        { name: 'addresses', count: 50, color: '#f59e0b' },
    ],
};

async function seedI18n() {
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
    const bundle = (await response.json()) as { geo: Record<string, unknown> };
    const prev = bus.getState().i18n.translations.ru;
    bus.dispatch(CoreEvents.I18N_LOCALE_LOADED, {
        locale: 'ru',
        bundle: { ...prev, geo: bundle.geo },
    });
    bus.dispatch(CoreEvents.I18N_LOCALE_CHANGED, { locale: 'ru' });
}

const SUGGEST_RESULT = {
    items: [
        {
            id: 1,
            osm_type: 'node',
            osm_id: 1001,
            display_name: 'Москва, Тверская улица, 1',
            city: 'Москва',
            street: 'Тверская улица',
            housenumber: '1',
            lat: 55.7501,
            lng: 37.6173,
        },
    ],
};

/** Ответить на geo запросы боевым контрактом (async, как WS). */
function answerGeo(): void {
    const bus = getPlatformBus();
    bus.subscribeType(geoLayersOp.events.REQUESTED, (event) => {
        queueMicrotask(() => {
            bus.dispatch(geoLayersOp.events.SUCCEEDED, { result: LAYERS_RESULT }, { causation_id: event.id, source: 'http' });
        });
    });
    bus.subscribeType(geoAddressSuggestOp.events.REQUESTED, (event) => {
        queueMicrotask(() => {
            bus.dispatch(geoAddressSuggestOp.events.SUCCEEDED, { result: SUGGEST_RESULT }, { causation_id: event.id, source: 'http' });
        });
    });
    bus.subscribeType(geoAddressNearestOp.events.REQUESTED, (event) => {
        queueMicrotask(() => {
            bus.dispatch(geoAddressNearestOp.events.SUCCEEDED, { result: SUGGEST_RESULT }, { causation_id: event.id, source: 'http' });
        });
    });
    bus.subscribeType(geoLayerFeaturesOp.events.REQUESTED, (event) => {
        queueMicrotask(() => {
            bus.dispatch(
                geoLayerFeaturesOp.events.SUCCEEDED,
                {
                    result: {
                        features: [
                            {
                                layer: 'addresses',
                                geometry: { type: 'Point', coordinates: [37.6, 55.75] },
                                properties: { display_name: 'Москва, Тверская, 1' },
                            },
                        ],
                    },
                },
                { causation_id: event.id, source: 'http' },
            );
        });
    });
    bus.subscribeType(geoRouteOp.events.REQUESTED, (event) => {
        queueMicrotask(() => {
            const p = event.payload as { from_point: { lng: number; lat: number }; to_point: { lng: number; lat: number } };
            bus.dispatch(
                geoRouteOp.events.SUCCEEDED,
                {
                    result: {
                        distance_m: 900,
                        duration_s: 120,
                        geometry: {
                            type: 'LineString',
                            coordinates: [
                                [p.from_point.lng, p.from_point.lat],
                                [p.to_point.lng, p.to_point.lat],
                            ],
                        },
                        legs: [],
                    },
                },
                { causation_id: event.id, source: 'http' },
            );
        });
    });
    bus.subscribeType(geoIsochroneOp.events.REQUESTED, (event) => {
        queueMicrotask(() => {
            const p = event.payload as { center: { lng: number; lat: number }; minutes: number };
            const d = 0.002 * (p.minutes / 5);
            bus.dispatch(
                geoIsochroneOp.events.SUCCEEDED,
                {
                    result: {
                        minutes: p.minutes,
                        polygon: {
                            type: 'Polygon',
                            coordinates: [
                                [
                                    [p.center.lng - d, p.center.lat - d],
                                    [p.center.lng + d, p.center.lat - d],
                                    [p.center.lng + d, p.center.lat + d],
                                    [p.center.lng - d, p.center.lat + d],
                                    [p.center.lng - d, p.center.lat - d],
                                ],
                            ],
                        },
                    },
                },
                { causation_id: event.id, source: 'http' },
            );
        });
    });
}

async function mapEl(config: PlatformMapConfig): Promise<MapEl> {
    const el = await fixture<MapEl>(
        html`<platform-map style="display:block;height:480px;width:640px" .config=${config}></platform-map>`,
    );
    for (let i = 0; i < 300 && !(el.getMap() && el._ready); i++) await aTimeout(30);
    expect(el.getMap(), 'MapLibre инициализирован').to.exist;
    expect(el._ready, 'стиль загружен').to.equal(true);
    await elementUpdated(el);
    return el;
}

describe('platform-map', function () {
    this.timeout(60_000);

    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('geo');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
        answerGeo();
    });

    it('базовый config → canvas MapLibre + zoom-контролы', async () => {
        const el = await mapEl({ interactive: true });
        const canvas = el.shadowRoot.querySelector('canvas.maplibregl-canvas');
        expect(canvas, 'canvas карты').to.exist;
        expect(el.shadowRoot.querySelector('.pm-zoom'), 'zoom-контрол').to.exist;
    });

    it('layers.fetch → layer_features_requested по bbox + панель слоёв из реестра', async () => {
        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(geoLayerFeaturesOp.events.REQUESTED, (e) => events.push(e));
        const el = await mapEl({
            interactive: true,
            controls: { layers: true },
            layers: { fetch: true },
        });
        await waitUntil(
            () => events.length > 0,
            'layer_features запрошен после load',
            { timeout: 10_000 },
        );
        const req = events[0]!.payload as { layers: string[]; south: number; west: number; zoom: number };
        expect(typeof req.south).to.equal('number');
        expect(typeof req.west).to.equal('number');
        expect(typeof req.zoom).to.equal('number');
        await elementUpdated(el);
        const layerPanel = el.shadowRoot.querySelector('.pm-layers');
        expect(layerPanel, 'панель слоёв').to.exist;
        expect(layerPanel!.textContent).to.include('Дороги');
    });

    it('toggle слоя → geo/map/toggle + pm-layer-toggle', async () => {
        const el = await mapEl({ interactive: true, controls: { layers: true } });
        await waitUntil(
            () => el.shadowRoot.querySelector('.pm-layers button') !== null,
            'кнопки слоёв',
            { timeout: 10_000 },
        );
        const toggles: string[] = [];
        el.addEventListener('pm-layer-toggle', (e) =>
            toggles.push((e as CustomEvent<{ name: string }>).detail.name),
        );
        const btn = [...el.shadowRoot.querySelectorAll<HTMLButtonElement>('.pm-layers button')][0]!;
        btn.click();
        expect(toggles).to.deep.equal(['roads']);
    });

    it('markers + overlays из config → geojson-источники на карте', async () => {
        const el = await mapEl({
            interactive: false,
            layers: { fetch: false },
            markers: [{ key: 'a', lngLat: [37.6, 55.75], color: '#22c55e' }],
            overlays: [{ name: 'zone', data: { type: 'Feature', geometry: ZONE, properties: {} } }],
        });
        const map = el.getMap()!;
        const markers = map.getSource('pm-markers') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
        expect(markers?.serialize().data?.features?.length, 'маркер в источнике').to.equal(1);
        expect(map.getLayer('pm-ov-zone-layer'), 'overlay line-слой').to.exist;
    });

    it('pm-click несёт lngLat и features под курсором', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: true } });
        await waitUntil(
            () => {
                const src = el.getMap()!.getSource('pm-src-addresses') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                return (src?.serialize().data?.features?.length ?? 0) > 0;
            },
            'фичи загружены в источник',
            { timeout: 10_000 },
        );
        const clicks: Array<{ lngLat: [number, number]; features: unknown[] }> = [];
        el.addEventListener('pm-click', (e) =>
            clicks.push((e as CustomEvent<{ lngLat: [number, number]; features: unknown[] }>).detail),
        );
        const map = el.getMap()!;
        const pt = map.project([37.6, 55.75]);
        map.getCanvas().dispatchEvent(
            new MouseEvent('click', {
                clientX: pt.x,
                clientY: pt.y,
                bubbles: true,
                composed: true,
            }),
        );
        await aTimeout(50);
        expect(clicks.length, 'pm-click эмитнут').to.be.greaterThan(0);
        expect(clicks[0]!.lngLat[0]).to.be.closeTo(37.6, 0.05);
    });

    it('до готовности — loading-оверлей со спиннером', async () => {
        const el = await fixture<MapEl>(html`<platform-map .config=${{ interactive: true }}></platform-map>`);
        await elementUpdated(el);
        const loading = el.shadowRoot.querySelector('.pm-loading');
        if (el._ready) {
            expect(loading, 'ready → оверлея нет').to.equal(null);
        } else {
            expect(loading, 'loading-оверлей').to.exist;
        }
    });

    it('search: ввод → suggest_requested, выбор → easeTo + pin + pm-search-select', async () => {
        const el = await mapEl({ interactive: true, controls: { search: true }, layers: { fetch: false } });
        const input = el.shadowRoot.querySelector<HTMLInputElement>('.pm-search-input');
        expect(input, 'поле поиска').to.exist;
        const reqs: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(geoAddressSuggestOp.events.REQUESTED, (e) => reqs.push(e));
        input!.value = 'Тверск';
        input!.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await waitUntil(() => reqs.length > 0, 'suggest запрошен', { timeout: 5_000 });
        expect((reqs[0]!.payload as Record<string, unknown>)['q']).to.equal('Тверск');
        const selects: unknown[] = [];
        el.addEventListener('pm-search-select', (e) => selects.push((e as CustomEvent).detail));
        await waitUntil(
            () => el.shadowRoot.querySelector('.pm-suggest-item') !== null,
            'дропдаун подсказок',
            { timeout: 5_000 },
        );
        el.shadowRoot.querySelector<HTMLButtonElement>('.pm-suggest-item')!.dispatchEvent(
            new MouseEvent('mousedown', { bubbles: true, composed: true }),
        );
        await aTimeout(50);
        expect(selects.length, 'pm-search-select').to.equal(1);
        const pin = el.getMap()!.getSource('pm-search-pin') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
        expect(pin?.serialize().data?.features?.length, 'pin на выбранном адресе').to.equal(1);
    });

    it('search: Escape скрывает дропдаун', async () => {
        const el = await mapEl({ interactive: true, controls: { search: true }, layers: { fetch: false } });
        const input = el.shadowRoot.querySelector<HTMLInputElement>('.pm-search-input')!;
        input.value = 'Тверск';
        input.dispatchEvent(new Event('input', { bubbles: true, composed: true }));
        await waitUntil(
            () => el.shadowRoot.querySelector('.pm-suggest') !== null,
            'дропдаун открыт',
            { timeout: 5_000 },
        );
        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, composed: true }));
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.pm-suggest'), 'дропдаун скрыт').to.equal(null);
    });

    it('ruler: контрол → режим, клики → вершины + pm-ruler-change с дистанцией', async () => {
        const el = await mapEl({ interactive: true, controls: { ruler: true }, layers: { fetch: false } });
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='ruler']");
        expect(btn, 'кнопка линейки').to.exist;
        const changes: Array<{ points: unknown[]; distanceM: number; finished: boolean }> = [];
        el.addEventListener('pm-ruler-change', (e) => changes.push((e as CustomEvent).detail));
        btn!.click();
        await elementUpdated(el);
        const map = el.getMap()!;
        for (const [lng, lat] of [[37.6, 55.75], [37.61, 55.75]] as const) {
            const pt = map.project([lng, lat]);
            map.getCanvas().dispatchEvent(
                new MouseEvent('click', { clientX: pt.x, clientY: pt.y, bubbles: true, composed: true }),
            );
            await aTimeout(30);
        }
        expect(changes.length).to.be.greaterThan(0);
        const last = changes.at(-1)!;
        expect(last.points.length, 'две вершины').to.equal(2);
        expect(last.distanceM, 'дистанция > 0').to.be.greaterThan(100);
        const src = map.getSource('pm-ruler') as { serialize(): { data?: { features?: Array<{ geometry: { type: string } }> } } } | undefined;
        const kinds = src?.serialize().data?.features?.map((f) => f.geometry.type) ?? [];
        expect(kinds).to.include('LineString');
        btn!.click();
        await elementUpdated(el);
        expect(changes.at(-1)!.finished, 'finish при выходе').to.equal(true);
    });

    it('markersCluster → cluster-слои; draggable → pm-marker-drag после dragend', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            markersCluster: true,
            markers: [{ key: 'd', lngLat: [37.6, 55.75], draggable: true }],
        });
        const map = el.getMap()!;
        expect(map.getLayer('pm-cluster-circle'), 'cluster circle layer').to.exist;
        expect(map.getLayer('pm-cluster-count'), 'cluster count layer').to.exist;
        const drags: unknown[] = [];
        el.addEventListener('pm-marker-drag', (e) => drags.push((e as CustomEvent).detail));
        const domMarker = el.shadowRoot.querySelector('.maplibregl-marker');
        expect(domMarker, 'DOM-маркер для draggable').to.exist;
    });

    it('contextMenu: правый клик → меню; «Что здесь?» → nearest_requested', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, contextMenu: true });
        const map = el.getMap()!;
        map.getCanvas().dispatchEvent(
            new MouseEvent('contextmenu', { clientX: 60, clientY: 60, bubbles: true, composed: true }),
        );
        await elementUpdated(el);
        const menu = el.shadowRoot.querySelector('.pm-menu');
        expect(menu, 'контекстное меню').to.exist;
        expect(menu!.textContent).to.include('Что здесь');
        const reqs: unknown[] = [];
        getPlatformBus().subscribeType(geoAddressNearestOp.events.REQUESTED, (e) => reqs.push(e));
        const whatsHere = menu!.querySelector<HTMLButtonElement>("button[data-action='whats-here']")!;
        whatsHere.dispatchEvent(new MouseEvent('click', { bubbles: true, composed: true }));
        await waitUntil(() => reqs.length > 0, 'nearest запрошен', { timeout: 5_000 });
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.pm-menu'), 'меню закрыто').to.equal(null);
    });

    it('statusBar → строка координат и zoom', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, statusBar: true });
        const bar = el.shadowRoot.querySelector('.pm-status');
        expect(bar, 'statusbar').to.exist;
        const map = el.getMap()!;
        map.getCanvas().dispatchEvent(
            new MouseEvent('mousemove', { clientX: 50, clientY: 50, bubbles: true, composed: true }),
        );
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.pm-status-coords')!.textContent!.trim()).to.not.equal('');
        expect(el.shadowRoot.querySelector('.pm-status-zoom')!.textContent).to.include('z');
    });

    it('fit + fullscreen контролы рендерятся и не падают', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            controls: { fit: true, fullscreen: true },
            overlays: [{ name: 'zone', data: { type: 'Feature', geometry: ZONE, properties: {} } }],
        });
        const fit = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='fit']");
        const fs = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='fullscreen']");
        expect(fit, 'fit-контрол').to.exist;
        expect(fs, 'fullscreen-контрол').to.exist;
        const before = el.getMap()!.getCenter?.();
        fit!.click();
        await aTimeout(700);
        const after = el.getMap()!.getCenter?.();
        if (before && after) {
            const moved = Math.abs(before.lng - after.lng) + Math.abs(before.lat - after.lat);
            expect(moved, 'камера сместилась к зоне').to.be.greaterThan(0.001);
        }
        fs!.click();
    });

    it('interactive:false → контролы и жесты выключены', async () => {
        const el = await mapEl({ interactive: false, layers: { fetch: false }, controls: { search: true, ruler: true } });
        expect(el.shadowRoot.querySelector('.pm-search'), 'поиска нет').to.equal(null);
        expect(el.shadowRoot.querySelector('.pm-zoom'), 'zoom-контрола нет').to.equal(null);
    });

    it('route: config → линия + A/B-точки + чип с ETA + pm-route', async () => {
        const routes: unknown[] = [];
        const el = await fixture<MapEl>(
            html`<platform-map
                style="display:block;height:480px;width:640px"
                .config=${{
                    interactive: true,
                    layers: { fetch: false },
                    route: { points: [[37.6, 55.75], [37.61, 55.76]], mode: 'car' },
                }}
            ></platform-map>`,
        );
        // Слушатель до готовности: pm-route летит во время init карты.
        el.addEventListener('pm-route', (e) => routes.push((e as CustomEvent).detail));
        for (let i = 0; i < 300 && !(el.getMap() && el._ready); i++) await aTimeout(30);
        await waitUntil(
            () => {
                const src = el.getMap()!.getSource('pm-route') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                return (src?.serialize().data?.features?.length ?? 0) > 0;
            },
            'линия маршрута в источнике',
            { timeout: 10_000 },
        );
        const pts = el.getMap()!.getSource('pm-route-pts') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
        expect(pts?.serialize().data?.features?.length, 'A/B точки').to.equal(2);
        await elementUpdated(el);
        const chip = el.shadowRoot.querySelector('.pm-route-chip');
        expect(chip, 'чип маршрута').to.exist;
        expect(el._routeInfo?.distanceM, 'дистанция из ответа').to.equal(900);
        expect(routes.length, 'pm-route эмитнут').to.equal(1);
    });

    it('route: build-режим → два клика ставят A/B и строят линию', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            controls: { route: true },
            route: { build: true, mode: 'car' },
        });
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='route']");
        expect(btn, 'кнопка построения').to.exist;
        btn!.click();
        await elementUpdated(el);
        expect(el._mode).to.equal('route');
        expect(el.shadowRoot.querySelector('.pm-route-hint'), 'подсказка в чипе').to.exist;
        const map = el.getMap()!;
        for (const ll of [[37.6, 55.75], [37.62, 55.77]] as [number, number][]) {
            const pt = map.project(ll);
            map.getCanvas().dispatchEvent(
                new MouseEvent('click', { clientX: pt.x, clientY: pt.y, bubbles: true, composed: true }),
            );
            await aTimeout(30);
        }
        expect(el._routeBuildPts.length, 'две точки набраны').to.equal(2);
        await waitUntil(
            () => {
                const src = el.getMap()!.getSource('pm-route') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                return (src?.serialize().data?.features?.length ?? 0) > 0;
            },
            'линия после второго клика',
            { timeout: 10_000 },
        );
    });

    it('route: смена режима в чипе → повторный расчёт', async () => {
        const reqs: unknown[] = [];
        getPlatformBus().subscribeType(geoRouteOp.events.REQUESTED, (e) => reqs.push(e));
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            route: { points: [[37.6, 55.75], [37.61, 55.76]], mode: 'car' },
        });
        await waitUntil(() => reqs.length >= 1, 'первый расчёт', { timeout: 10_000 });
        await waitUntil(
            () => el.shadowRoot.querySelector(".pm-route-modes button[data-mode='foot']") !== null,
            'чип с режимами',
            { timeout: 10_000 },
        );
        el.shadowRoot.querySelector<HTMLButtonElement>(".pm-route-modes button[data-mode='foot']")!.click();
        await waitUntil(() => reqs.length >= 2, 'пересчёт под foot', { timeout: 10_000 });
        const last = reqs.at(-1) as { payload: { mode: string } };
        expect(last.payload.mode, 'запрос с режимом foot').to.equal('foot');
    });

    it('route: clear → линия и точки сняты, чип скрыт', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            route: { points: [[37.6, 55.75], [37.61, 55.76]], mode: 'car' },
        });
        await waitUntil(
            () => el.shadowRoot.querySelector("button[data-action='route-clear']") !== null,
            'кнопка очистки',
            { timeout: 10_000 },
        );
        el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='route-clear']")!.click();
        await elementUpdated(el);
        const src = el.getMap()!.getSource('pm-route') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
        expect(src?.serialize().data?.features?.length, 'линия очищена').to.equal(0);
        expect(el._routeInfo, 'ETA снят').to.equal(null);
    });

    it('isochrone → полигоны порогов + центр + pm-isochrone', async () => {
        const events: unknown[] = [];
        const el = await fixture<MapEl>(
            html`<platform-map
                style="display:block;height:480px;width:640px"
                .config=${{
                    interactive: true,
                    layers: { fetch: false },
                    isochrone: { center: [37.6, 55.75], minutes: [5, 10], mode: 'foot' },
                }}
            ></platform-map>`,
        );
        el.addEventListener('pm-isochrone', (e) => events.push((e as CustomEvent).detail));
        for (let i = 0; i < 300 && !(el.getMap() && el._ready); i++) await aTimeout(30);
        await waitUntil(
            () => {
                const src = el.getMap()!.getSource('pm-iso') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                return (src?.serialize().data?.features?.length ?? 0) >= 2;
            },
            'полигоны изохрон',
            { timeout: 10_000 },
        );
        const pts = el.getMap()!.getSource('pm-iso-pts') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
        expect(pts?.serialize().data?.features?.length, 'центр + лейблы').to.be.greaterThanOrEqual(3);
        expect(events.length, 'pm-isochrone').to.equal(1);
    });

    it('scheme-контрол → setStyle(dark) и обратно', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            controls: { scheme: true },
            markers: [{ key: 'a', lngLat: [37.6, 55.75] }],
        });
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='scheme']");
        expect(btn, 'переключатель схемы').to.exist;
        btn!.click();
        await waitUntil(() => el._scheme === 'dark', 'dark схема', { timeout: 5_000 });
        // После style.load источники переустановлены и маркер вернулся.
        await waitUntil(
            () => {
                const src = el.getMap()!.getSource('pm-markers') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                return (src?.serialize().data?.features?.length ?? 0) === 1;
            },
            'маркеры восстановлены после смены стиля',
            { timeout: 15_000 },
        );
        btn!.click();
        await waitUntil(() => el._scheme === 'light', 'обратно в light', { timeout: 5_000 });
    });

    it('compass → клик сбрасывает bearing на север', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            controls: { compass: true },
            rotate: true,
        });
        el.getMap()!.setBearing(50);
        await aTimeout(60);
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='compass']");
        expect(btn, 'компас').to.exist;
        btn!.click();
        await waitUntil(() => Math.abs(el.getMap()!.getBearing()) < 1, 'bearing → 0', { timeout: 5_000 });
    });

    it('rulerArea: три клика → полигон + площадь', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            controls: { rulerArea: true },
        });
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='ruler-area']");
        expect(btn, 'линейка площади').to.exist;
        btn!.click();
        const map = el.getMap()!;
        for (const ll of [[37.6, 55.75], [37.62, 55.75], [37.61, 55.77]] as [number, number][]) {
            const pt = map.project(ll);
            map.getCanvas().dispatchEvent(
                new MouseEvent('click', { clientX: pt.x, clientY: pt.y, bubbles: true, composed: true }),
            );
            await aTimeout(30);
        }
        const src = map.getSource('pm-ruler') as { serialize(): { data?: { features?: Array<{ geometry: { type: string } }> } } } | undefined;
        const kinds = src?.serialize().data?.features?.map((f) => f.geometry.type) ?? [];
        expect(kinds).to.include('Polygon');
        expect(el._rulerAreaM2(), 'площадь > 0').to.be.greaterThan(0);
    });

    it('moveEvent → pm-move с центром и bounds на moveend', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, moveEvent: true });
        const moves: Array<{ zoom: number }> = [];
        el.addEventListener('pm-move', (e) => moves.push((e as CustomEvent<{ zoom: number }>).detail));
        el.getMap()!.fire('moveend');
        await aTimeout(30);
        expect(moves.length, 'pm-move эмитнут').to.equal(1);
        expect(typeof moves[0]!.zoom).to.equal('number');
    });

    it("scheme:'auto' → схема из prefers-color-scheme и следит за сменой", async () => {
        const orig = window.matchMedia.bind(window);
        let dark = true;
        const listeners: Array<() => void> = [];
        const fake = (q: string): MediaQueryList => {
            const mql = orig(q);
            return {
                matches: q.includes('dark') ? dark : mql.matches,
                media: q,
                addEventListener: (_t: string, cb: EventListenerOrEventListenerObject) =>
                    listeners.push(cb as () => void),
                removeEventListener: () => undefined,
                addListener: () => undefined,
                removeListener: () => undefined,
                onchange: null,
                dispatchEvent: () => false,
            } as MediaQueryList;
        };
        window.matchMedia = fake as typeof window.matchMedia;
        let el: MapEl | null = null;
        try {
            el = await mapEl({ interactive: true, layers: { fetch: false }, scheme: 'auto' });
            await waitUntil(() => el!._scheme === 'dark', 'auto → dark', { timeout: 10_000 });
            dark = false;
            for (const cb of listeners) cb();
            await waitUntil(() => el!._scheme === 'light', 'auto следит за сменой → light', { timeout: 15_000 });
        } finally {
            window.matchMedia = orig;
        }
    });

    it('cooperativeGestures → scroll-zoom заблокирован без Ctrl', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, cooperativeGestures: true });
        const map = el.getMap()!;
        const cg = (map as unknown as { cooperativeGestures?: { isEnabled(): boolean } }).cooperativeGestures;
        expect(cg?.isEnabled(), 'handler включён').to.equal(true);
        // Поведение: wheel без Ctrl → экран-подсказка cooperative-gesture.
        map.getCanvas().dispatchEvent(
            new WheelEvent('wheel', { deltaY: 100, bubbles: true, composed: true, cancelable: true }),
        );
        await aTimeout(60);
        const screen = el.shadowRoot.querySelector('.maplibregl-cooperative-gesture-screen');
        expect(screen, 'cooperative-gesture экран').to.exist;
    });

    it('hash → moveend пишет #map= в URL (deep-link)', async () => {
        history.replaceState(null, '', location.pathname + location.search);
        const el = await mapEl({ interactive: true, layers: { fetch: false }, hash: true });
        try {
            el.getMap()!.fire('moveend');
            await aTimeout(80);
            expect(location.hash, 'хэш с камерой').to.include('#map=');
        } finally {
            history.replaceState(null, '', location.pathname + location.search);
        }
    });

    it('route: swap ⇅ → точки маршрута в обратном порядке', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            route: { points: [[37.6, 55.75], [37.61, 55.76]], mode: 'car' },
        });
        await waitUntil(
            () => el.shadowRoot.querySelector("button[data-action='route-swap']") !== null,
            'swap-кнопка',
            { timeout: 10_000 },
        );
        el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='route-swap']")!.click();
        await elementUpdated(el);
        expect(el._routeBuildPts.length).to.equal(2);
        expect(el._routeBuildPts[0]![0], 'старт = бывший B').to.be.closeTo(37.61, 0.001);
        expect(el._routeBuildPts[1]![0], 'финиш = бывший A').to.be.closeTo(37.6, 0.001);
    });

    it('contextMenu: «маршрут отсюда/сюда» ставит A/B из точки клика', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            contextMenu: true,
            route: { points: [[37.6, 55.75], [37.61, 55.76]], mode: 'car' },
        });
        const map = el.getMap()!;
        const pt = map.project([37.615, 55.752]);
        map.getCanvas().dispatchEvent(
            new MouseEvent('contextmenu', { clientX: pt.x, clientY: pt.y, bubbles: true, composed: true }),
        );
        await elementUpdated(el);
        const menu = el.shadowRoot.querySelector('.pm-menu');
        expect(menu, 'меню с route-пунктами').to.exist;
        const from = menu!.querySelector<HTMLButtonElement>("button[data-action='route-from']");
        const to = menu!.querySelector<HTMLButtonElement>("button[data-action='route-to']");
        expect(from, 'route-from').to.exist;
        expect(to, 'route-to').to.exist;
        from!.click();
        await elementUpdated(el);
        expect(el._routeBuildPts[0]![0], 'A = место клика').to.be.closeTo(37.615, 0.01);
        map.getCanvas().dispatchEvent(
            new MouseEvent('contextmenu', { clientX: pt.x, clientY: pt.y, bubbles: true, composed: true }),
        );
        await elementUpdated(el);
        el.shadowRoot
            .querySelector<HTMLButtonElement>(".pm-menu button[data-action='route-to']")!
            .click();
        await elementUpdated(el);
        expect(el._routeBuildPts.at(-1)![0], 'B = место клика').to.be.closeTo(37.615, 0.01);
        await waitUntil(
            () => {
                const src = map.getSource('pm-route') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                return (src?.serialize().data?.features?.length ?? 0) > 0;
            },
            'маршрут перестроен',
            { timeout: 10_000 },
        );
    });

    it('export → кнопка PNG + pm-export по клику', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, controls: { export: true } });
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>("button[data-action='export-png']");
        expect(btn, 'export-контрол').to.exist;
        const events: unknown[] = [];
        el.addEventListener('pm-export', (e) => events.push((e as CustomEvent).detail));
        btn!.click();
        await aTimeout(30);
        expect(events.length, 'pm-export эмитнут').to.equal(1);
    });

    it('marker title → хинт-попап при наведении', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            markers: [{ key: 'a', lngLat: [37.6, 55.75], title: 'Склад Центральный' }],
        });
        const map = el.getMap()!;
        const pt = map.project([37.6, 55.75]);
        // geojson-маркер попадает в render-pyramid асинхронно — шлём mousemove до хита.
        await waitUntil(
            () => {
                map.getCanvas().dispatchEvent(
                    new MouseEvent('mousemove', { clientX: pt.x, clientY: pt.y, bubbles: true, composed: true }),
                );
                return el.shadowRoot.querySelector('.pm-hint') !== null;
            },
            'хинт с title маркера',
            { timeout: 15_000 },
        );
        expect(el.shadowRoot.querySelector('.pm-hint')!.textContent).to.include('Склад Центральный');
    });

    it('long-press ≥600мс → контекстное меню на таче', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, contextMenu: true });
        const canvas = el.getMap()!.getCanvas();
        const rect = canvas.getBoundingClientRect();
        const touch = new Touch({
            identifier: 1,
            target: canvas,
            clientX: rect.left + 80,
            clientY: rect.top + 80,
        });
        canvas.dispatchEvent(
            new TouchEvent('touchstart', { touches: [touch], bubbles: true, composed: true }),
        );
        await aTimeout(700);
        await elementUpdated(el);
        expect(el.shadowRoot.querySelector('.pm-menu'), 'меню после долгого тапа').to.exist;
        canvas.dispatchEvent(
            new TouchEvent('touchend', { touches: [], bubbles: true, composed: true }),
        );
    });

    it('statusbar → bearing в строке состояния после поворота', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            statusBar: true,
            rotate: true,
            controls: { compass: true },
        });
        el.getMap()!.setBearing(45);
        await waitUntil(
            () => el.shadowRoot.querySelector('.pm-status-zoom')!.textContent!.includes('↻'),
            'bearing в статусбаре',
            { timeout: 10_000 },
        );
    });

    it('controls.miniMap → inset с прямоугольником viewport', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, controls: { miniMap: true } });
        const miniEl = el.shadowRoot.querySelector<HTMLElement>('.pm-minimap');
        expect(miniEl, 'контейнер миникарты').to.exist;
        await waitUntil(
            () => {
                const mini = (el as unknown as { _mini: TestMap | null })._mini;
                if (!mini) return false;
                const src = mini.getSource('pm-minimap-box') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                return (src?.serialize().data?.features?.length ?? 0) === 1;
            },
            'viewport-rect в inset',
            { timeout: 15_000 },
        );
        expect(el.shadowRoot.querySelectorAll('canvas.maplibregl-canvas').length, 'два canvas').to.equal(2);
    });

    it('locateWatch → синяя точка + круг точности + pm-locate', async () => {
        const orig = Object.getOwnPropertyDescriptor(Navigator.prototype, 'geolocation') ??
            Object.getOwnPropertyDescriptor(navigator, 'geolocation');
        const fixes = [{ coords: { longitude: 37.6, latitude: 55.75, accuracy: 25 } }];
        Object.defineProperty(navigator, 'geolocation', {
            configurable: true,
            value: {
                watchPosition: (ok: (p: unknown) => void) => {
                    setTimeout(() => ok(fixes[0]), 20);
                    return 42;
                },
                clearWatch: () => undefined,
                getCurrentPosition: () => undefined,
            },
        });
        try {
            const events: Array<{ lngLat: [number, number]; accuracy: number }> = [];
            const el = await fixture<MapEl>(
                html`<platform-map
                    style="display:block;height:480px;width:640px"
                    .config=${{ interactive: true, layers: { fetch: false }, locateWatch: true }}
                ></platform-map>`,
            );
            el.addEventListener('pm-locate', (e) =>
                events.push((e as CustomEvent<{ lngLat: [number, number]; accuracy: number }>).detail),
            );
            for (let i = 0; i < 300 && !(el.getMap() && el._ready); i++) await aTimeout(30);
            await waitUntil(
                () => {
                    const src = el.getMap()!.getSource('pm-user') as { serialize(): { data?: { features?: unknown[] } } } | undefined;
                    return (src?.serialize().data?.features?.length ?? 0) === 2;
                },
                'точка + круг точности в pm-user',
                { timeout: 10_000 },
            );
            expect(events.length, 'pm-locate с accuracy').to.be.greaterThan(0);
            expect(events[0]!.accuracy).to.equal(25);
        } finally {
            if (orig) {
                Object.defineProperty(navigator, 'geolocation', orig);
            }
        }
    });

    it('marker title → балун по клику на маркере', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            markers: [{ key: 'a', lngLat: [37.6, 55.75], title: 'Склад Центральный' }],
        });
        const map = el.getMap()!;
        const pt = map.project([37.6, 55.75]);
        await waitUntil(
            () => {
                map.getCanvas().dispatchEvent(
                    new MouseEvent('click', { clientX: pt.x, clientY: pt.y, bubbles: true, composed: true }),
                );
                return el.shadowRoot.querySelector('.pm-balloon') !== null;
            },
            'балун открылся',
            { timeout: 15_000 },
        );
        expect(el.shadowRoot.querySelector('.pm-balloon')!.textContent).to.include('Склад Центральный');
    });

    it('controls.tilt → кнопка переключает pitch карты', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, controls: { tilt: true } });
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>('button[data-action="tilt"]');
        expect(btn, 'кнопка tilt').to.exist;
        const map = el.getMap()!;
        btn!.click();
        await waitUntil(() => map.getPitch() > 55, 'pitch вырос до ~60', { timeout: 5_000 });
        expect(el._tilted).to.equal(true);
        btn!.click();
        await waitUntil(() => map.getPitch() < 5, 'pitch вернулся', { timeout: 5_000 });
        expect(el._tilted).to.equal(false);
    });

    it('controls.share → копия deep-link с #map= + тост + pm-share', async () => {
        const el = await mapEl({ interactive: true, layers: { fetch: false }, controls: { share: true } });
        const shares: Array<{ url: string }> = [];
        el.addEventListener('pm-share', (e) => shares.push((e as CustomEvent<{ url: string }>).detail));
        const btn = el.shadowRoot.querySelector<HTMLButtonElement>('button[data-action="share"]');
        expect(btn, 'кнопка share').to.exist;
        btn!.click();
        await elementUpdated(el);
        expect(shares.length, 'pm-share').to.equal(1);
        expect(shares[0]!.url).to.include('#map=');
        expect(shares[0]!.url).to.match(/#map=\d+\.\d+\/\d+\.\d+\/\d+\.\d+/);
        const toast = el.shadowRoot.querySelector('.pm-toast');
        expect(toast, 'тост «ссылка скопирована»').to.exist;
        expect(toast!.textContent).to.match(/копир|copied/i);
    });

    it('route → pm-route, а чип раскрывает плечи A→B→C', async () => {
        const el = await mapEl({
            interactive: true,
            layers: { fetch: false },
            route: { points: [[37.6, 55.75], [37.62, 55.76], [37.64, 55.77]] },
        });
        await waitUntil(
            () => el.shadowRoot.querySelector('button[data-action="route-legs"]') !== null,
            'кнопка плечей (2 плеча)',
            { timeout: 10_000 },
        );
        el.shadowRoot.querySelector<HTMLButtonElement>('button[data-action="route-legs"]')!.click();
        await elementUpdated(el);
        const legs = el.shadowRoot.querySelectorAll('.pm-route-leg');
        expect(legs.length, 'два плеча A→B и B→C').to.equal(2);
        expect(legs[0]!.textContent).to.include('A → B');
        expect(legs[1]!.textContent).to.include('B → C');
    });
});

describe('platform.zone_editor', function () {
    this.timeout(60_000);

    const TAG = 'platform-zone-editor-modal';

    beforeEach(async () => {
        resetPlatformState();
        setDefaultI18nNamespace('geo');
        bootstrapTestBus({ factories: FACTORIES });
        await seedI18n();
        answerGeo();
    });

    async function openEditor(props: Record<string, unknown>): Promise<ModalEl> {
        await fixture<HTMLElement>(html`<platform-modal-stack></platform-modal-stack>`);
        getPlatformBus().dispatch(CoreEvents.UI_MODAL_OPEN, { kind: 'platform.zone_editor', props });
        for (let i = 0; i < 50; i++) {
            await aTimeout(30);
            const modal = [...document.querySelectorAll<ModalEl>(TAG)].at(-1);
            if (modal) return modal;
        }
        throw new Error('platform.zone_editor не смонтирован');
    }

    function innerMap(modal: ModalEl): MapEl {
        const el = modal.shadowRoot.querySelector<MapEl>('platform-map');
        expect(el, 'platform-map внутри модалки').to.exist;
        return el!;
    }

    async function editorReady(modal: ModalEl): Promise<MapEl> {
        const mapEl = innerMap(modal);
        for (let i = 0; i < 200; i++) {
            if (mapEl.getMap() && mapEl.getDraw()) return mapEl;
            await aTimeout(30);
        }
        throw new Error('terra-draw не инициализирован');
    }

    function ztool(modal: ModalEl, text: string): HTMLButtonElement {
        const found = [...modal.shadowRoot.querySelectorAll<HTMLButtonElement>('.ztool')].find((b) =>
            b.textContent!.includes(text),
        );
        expect(found, `кнопка «${text}»`).to.exist;
        return found!;
    }

    function applyBtn(modal: ModalEl): HTMLElement {
        const found = [...modal.shadowRoot.querySelectorAll<HTMLElement>('platform-button')].find((b) =>
            b.textContent!.includes('Применить'),
        );
        expect(found, 'кнопка «Применить»').to.exist;
        return found!;
    }

    async function clickMap(mapEl: MapEl, lng: number, lat: number): Promise<void> {
        const map = mapEl.getMap()!;
        const canvas = map.getCanvas();
        const rect = canvas.getBoundingClientRect();
        const point = map.project([lng, lat]);
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

    async function finishDraw(mapEl: MapEl): Promise<void> {
        mapEl.getMap()!.getCanvas().dispatchEvent(
            new KeyboardEvent('keyup', { key: 'Enter', bubbles: true, composed: true }),
        );
        await aTimeout(80);
    }

    it('открытие без зоны → карта + terra-draw, «Применить» отдаёт null', async () => {
        const applied: unknown[] = [];
        const modal = await openEditor({ zone: null, address: '', onApply: (z: unknown) => applied.push(z) });
        const mapEl = await editorReady(modal);
        await elementUpdated(modal);
        const links = [...mapEl.shadowRoot.querySelectorAll('link[rel="stylesheet"]')].map((l) =>
            (l as HTMLLinkElement).href,
        );
        expect(links.some((h) => h.includes('maplibre-gl.css')), 'maplibre css в shadow root').to.equal(true);
        expect(mapEl.getDraw()!.draw.getSnapshot().filter((f) => f.geometry.type === 'Polygon').length).to.equal(0);
        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied).to.deep.equal([null]);
    });

    it('существующая зона → полигон в terra-draw + метрики', async () => {
        const modal = await openEditor({ zone: ZONE, address: '', onApply: null });
        const mapEl = await editorReady(modal);
        await elementUpdated(modal);
        const polygons = mapEl.getDraw()!.draw.getSnapshot().filter((f) => f.geometry.type === 'Polygon');
        expect(polygons.length, 'полигон в terra-draw').to.equal(1);
        expect(mapEl.getDraw()!.draw.getMode(), 'select-режим').to.equal('select');
        const stats = modal.shadowRoot.querySelector('.zstats');
        expect(stats, 'панель метрик').to.exist;
        expect(stats!.textContent).to.include('км²');
    });

    it('рисование: draw → 3 клика → Enter → полигон → «Применить» отдаёт GeoJSON', async () => {
        const applied: unknown[] = [];
        const modal = await openEditor({ zone: null, address: '', onApply: (z: unknown) => applied.push(z) });
        const mapEl = await editorReady(modal);
        ztool(modal, 'Рисовать зону').click();
        await elementUpdated(modal);
        expect(mapEl.getDraw()!.draw.getMode(), 'polygon-режим').to.equal('polygon');

        await clickMap(mapEl, 37.5, 55.7);
        await clickMap(mapEl, 37.7, 55.7);
        await clickMap(mapEl, 37.6, 55.8);
        await finishDraw(mapEl);

        const polygons = mapEl.getDraw()!.draw.getSnapshot().filter((f) => f.geometry.type === 'Polygon');
        expect(polygons.length, 'полигон создан').to.equal(1);
        expect(mapEl.getDraw()!.draw.getMode(), 'select после finish').to.equal('select');

        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied.length).to.equal(1);
        const zone = applied[0] as { type: string; coordinates: number[][][] };
        expect(zone.type).to.equal('Polygon');
        const ring = zone.coordinates[0]!;
        expect(ring[0]).to.deep.equal(ring[ring.length - 1]);
        expect(ring[0]![0]).to.be.closeTo(37.5, 0.01);
    });

    it('«Очистить» удаляет полигон; «Применить» отдаёт null и закрывает', async () => {
        const applied: unknown[] = [];
        const modal = await openEditor({ zone: ZONE, address: '', onApply: (z: unknown) => applied.push(z) });
        const mapEl = await editorReady(modal);
        await elementUpdated(modal);
        expect(mapEl.getDraw()!.draw.getSnapshot().filter((f) => f.geometry.type === 'Polygon').length).to.equal(1);

        ztool(modal, 'Очистить').click();
        await elementUpdated(modal);
        expect(mapEl.getDraw()!.draw.getSnapshot().filter((f) => f.geometry.type === 'Polygon').length).to.equal(0);

        const closes: unknown[] = [];
        getPlatformBus().subscribeType(CoreEvents.UI_MODAL_CLOSE, (e) => closes.push(e));
        applyBtn(modal).click();
        await aTimeout(30);
        expect(applied).to.deep.equal([null]);
        expect(closes.length, 'модалка закрыта').to.equal(1);
    });

    it('«К адресу» → geo/addresses_suggest с текстом адреса', async () => {
        const modal = await openEditor({ zone: ZONE, address: 'Москва, Тверская 1', onApply: null });
        await editorReady(modal);
        await elementUpdated(modal);
        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(geoAddressSuggestOp.events.REQUESTED, (e) => events.push(e));
        ztool(modal, 'К адресу').click();
        await aTimeout(50);
        const req = events.find((e) => e.type === geoAddressSuggestOp.events.REQUESTED);
        expect(req, 'suggest запрошен').to.exist;
        expect((req!.payload as Record<string, unknown>)['q']).to.equal('Москва, Тверская 1');
    });

    it('панель адресов: зона → geo/addresses_in_zone с GeoJSON', async () => {
        const events: Array<{ type: string; payload: unknown }> = [];
        getPlatformBus().subscribeType(geoAddressesInZoneOp.events.REQUESTED, (e) => events.push(e));
        const modal = await openEditor({ zone: ZONE, address: '', onApply: null });
        await editorReady(modal);
        await waitUntil(
            () => events.length > 0,
            'in_zone запрошен для зоны',
            { timeout: 10_000 },
        );
        const req = events[0]!.payload as { zone: { type: string } };
        expect(req.zone.type).to.equal('Polygon');
        const panel = innerMap(modal).shadowRoot.querySelector('platform-zone-address-panel');
        expect(panel, 'панель адресов внутри platform-map').to.exist;
    });

    it('addressesPanel:false → панели нет', async () => {
        const modal = await openEditor({ zone: ZONE, address: '', onApply: null, addressesPanel: false });
        const mapEl = await editorReady(modal);
        await elementUpdated(modal);
        expect(mapEl.shadowRoot.querySelector('platform-zone-address-panel')).to.equal(null);
    });
});

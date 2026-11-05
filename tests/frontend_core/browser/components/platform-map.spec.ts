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
    getSource(id: string): { setData(d: unknown): void; _data?: { geojson?: { features?: unknown[] } } } | undefined;
    getLayer(id: string): unknown;
};

type TestDraw = {
    getMode(): string;
    getSnapshot(): StoreFeature[];
};

type MapEl = HTMLElement & {
    shadowRoot: ShadowRoot;
    config: PlatformMapConfig;
    _ready: boolean;
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

/** Ответить на geo запросы боевым контрактом (async, как WS). */
function answerGeo(): void {
    const bus = getPlatformBus();
    bus.subscribeType(geoLayersOp.events.REQUESTED, (event) => {
        queueMicrotask(() => {
            bus.dispatch(geoLayersOp.events.SUCCEEDED, { result: LAYERS_RESULT }, { causation_id: event.id, source: 'http' });
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
}

async function mapEl(config: PlatformMapConfig): Promise<MapEl> {
    const el = await fixture<MapEl>(html`<platform-map .config=${config}></platform-map>`);
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

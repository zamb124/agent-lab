/**
 * <platform-map> — единый виджет карты платформы.
 *
 * Все сценарии (обзор слоёв geo, route lab, превью и редактор зон shop,
 * embed в wiki/tracker/flow-ui) идут через один сериализуемый `config` —
 * в духе options-объекта JS API Яндекс.Карт: что пришло в config, то
 * и работает, ничего больше. Секции:
 *
 *   center/zoom/interactive      — камера и жесты
 *   controls.zoom/layers/locate  — встроенные контролы
 *   layers.fetch/hidden          — канонические geo-слои по bbox
 *   featureCards.hover/click     — хинт и карточка фичи (Яндекс-стиль)
 *   markers[]                    — точечные маркеры (маршруты, locate)
 *   overlays[]                   — произвольные GeoJSON-слои (зоны, треки)
 *   draw                         — TerraDraw-редактирование полигона зоны
 *   addressesPanel               — боковая панель адресов в зоне
 *
 * События (bubbles+composed): pm-ready, pm-click, pm-marker-click,
 * pm-draw-change, pm-layer-toggle, pm-locate, pm-address-hover.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { SliceControllerOf, OpControllerOf } from '../base/use-resource.js';
import { maplibreCssLink, loadMapLibre } from '@platform/lib/map/maplibre.js';
import type { MapLibreModule } from '@platform/lib/map/maplibre.js';
import { createBasemap } from '@platform/lib/map/basemap.js';
import type { PlatformMap } from '@platform/lib/map/basemap.js';
import { createZoneDraw } from '@platform/lib/map/zone-draw.js';
import type { ZoneDraw } from '@platform/lib/map/zone-draw.js';
import { ringAreaM2, ringPerimeterM, fmtArea, fmtKm } from '@platform/lib/map/geo-math.js';
import { renderFeatureCard, featureTitle } from '@platform/lib/map/feature-card.js';
import './platform-zone-address-panel.js';
import '../events/resources/geo-layers.resource.js';
import '../events/resources/geo-addresses.resource.js';
import type { geoLayersOp, geoLayerFeaturesOp, geoMapSlice } from '../events/resources/geo-layers.resource.js';
import type { geoAddressNearestOp } from '../events/resources/geo-addresses.resource.js';
import type { GeoFeature, GeoLayerInfo } from '../events/wire/geo.gen.js';
import type {
    Feature,
    FeatureCollection,
    GeoJsonProperties,
    Geometry,
    LineString,
    MultiPolygon,
    Point,
    Polygon,
} from 'geojson';

export type LngLat = [number, number];

export interface PlatformMapMarker {
    key?: string;
    lngLat: LngLat;
    color?: string;
    title?: string;
    size?: number;
}

export interface PlatformMapOverlay {
    name: string;
    data: Feature | FeatureCollection;
    color?: string;
    opacity?: number;
    width?: number;
    fit?: boolean;
    fitPadding?: number;
}

export interface PlatformMapConfig {
    center?: LngLat;
    zoom?: number;
    minZoom?: number;
    interactive?: boolean;
    controls?: {
        zoom?: boolean;
        layers?: boolean;
        locate?: boolean;
    };
    layers?: {
        fetch?: boolean;
        hidden?: string[];
    };
    featureCards?: {
        hover?: boolean;
        click?: boolean;
    };
    markers?: PlatformMapMarker[];
    overlays?: PlatformMapOverlay[];
    draw?: {
        zone?: Polygon | MultiPolygon | null;
    } | false;
    addressesPanel?: {
        zone?: Polygon | MultiPolygon | null;
        title?: string;
    } | false;
    locateTo?: {
        lngLat: LngLat;
        zoom?: number;
    } | false;
}

type FeatureGeometry = Point | LineString | Polygon | MultiPolygon;
type GeoFeatureOf = Feature<FeatureGeometry, GeoJsonProperties>;
type DrawFeature = Feature<Polygon | MultiPolygon>;

const DEFAULT_CENTER: LngLat = [55.7512, 37.6184];
const DEFAULT_ZOOM = 10;
const REFRESH_DEBOUNCE_MS = 250;
const OVERLAY_COLOR = '#2563eb';
const MARKER_COLOR = '#f2542d';

const _EMPTY_FC: FeatureCollection = { type: 'FeatureCollection', features: [] };

function _zoneStats(zone: Polygon | MultiPolygon): { areaM2: number; perimeterM: number } {
    const rings =
        zone.type === 'Polygon' ? [zone.coordinates[0] ?? []] : zone.coordinates.map((p) => p[0] ?? []);
    let areaM2 = 0;
    let perimeterM = 0;
    for (const ring of rings) {
        const r = ring as LngLat[];
        areaM2 += ringAreaM2(r);
        perimeterM += ringPerimeterM(r);
    }
    return { areaM2, perimeterM };
}

export class PlatformMapEl extends PlatformElement {
    static i18nNamespace = 'geo';

    static override properties: PropertyDeclarations = {
        config: { type: Object, attribute: false },
        _ready: { state: true },
        _zoneStats: { state: true },
    };

    declare config: PlatformMapConfig;
    declare _ready: boolean;
    declare _zoneStats: { areaM2: number; perimeterM: number; valid: boolean } | null;

    private _el: HTMLDivElement | null = null;
    private _map: PlatformMap | null = null;
    private _maplibre: MapLibreModule | null = null;
    private _mapCtl: SliceControllerOf<typeof geoMapSlice> | null = null;
    private _featuresOp: OpControllerOf<typeof geoLayerFeaturesOp> | null = null;
    private _layersOp: OpControllerOf<typeof geoLayersOp> | null = null;
    private _nearestOp: OpControllerOf<typeof geoAddressNearestOp> | null = null;
    private _refreshTimer: number | null = null;
    private _hintPopup: { remove(): void; setLngLat(l: unknown): unknown } | null = null;
    private _cardPopup: { remove(): void } | null = null;
    private _zoneDraw: ZoneDraw | null = null;
    private _locateMarker: { remove(): void } | null = null;
    private _configLayersApplied = false;
    private _mapLayers = new Set<string>();

    constructor() {
        super();
        this.config = {};
        this._ready = false;
        this._zoneStats = null;
    }

    /** MapLibre-карта — для потребителей, которым нужен прямой API (fitBounds и т.п.). */
    getMap(): PlatformMap | null {
        return this._map;
    }

    /** TerraDraw-инстанс режима `draw` — контролы редактора зовут setMode/clear. */
    getDraw(): ZoneDraw | null {
        return this._zoneDraw;
    }

    private get _layersFetch(): boolean {
        return this.config.layers?.fetch !== false;
    }

    private get _hoverEnabled(): boolean {
        return this.config.featureCards?.hover !== false;
    }

    private get _clickCardEnabled(): boolean {
        return this.config.featureCards?.click !== false;
    }

    private get _layerNames(): string[] {
        return (this._layersOp?.lastResult?.layers ?? []).map((l: GeoLayerInfo) => l.name);
    }

    private _layerColor(name: string): string {
        return (
            (this._layersOp?.lastResult?.layers ?? []).find((l) => l.name === name)?.color ??
            '#475569'
        );
    }

    private _layerMinZoom(name: string): number {
        return (this._layersOp?.lastResult?.layers ?? []).find((l) => l.name === name)?.min_zoom ?? 0;
    }

    private get _interactive(): boolean {
        return this.config.interactive !== false;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (this._layersFetch) {
            this._mapCtl = this.useSlice('geo/map');
            this._featuresOp = this.useOp('geo/layer_features');
            this._layersOp = this.useOp('geo/layers');
            void this._layersOp.run({});
        }
        if (this.config.controls?.locate === true) {
            this._nearestOp = this.useOp('geo/addresses_nearest');
        }
    }

    override render() {
        const cls = `pm-wrap${this._interactive ? ' interactive' : ''}${this._ready ? ' ready' : ''}`;
        const panel = this.config.addressesPanel;
        return html`
            ${maplibreCssLink()}
            <div class=${cls}>
                <div
                    class="map-canvas"
                    @mousedown=${(e: MouseEvent) => e.stopPropagation()}
                    @touchstart=${(e: TouchEvent) => e.stopPropagation()}
                    @wheel=${(e: WheelEvent) => e.stopPropagation()}
                ></div>
                ${this._renderControls()}
                ${this.config.draw ? this._renderZoneStats() : nothing}
                ${panel ? this._renderAddressesPanel(panel) : nothing}
            </div>
        `;
    }

    private _renderControls() {
        const c = this.config.controls ?? {};
        const zoom = c.zoom !== false && this._ready && this._interactive;
        const layers = c.layers !== false && this._ready && this._layerNames.length > 0;
        const locate = c.locate === true && this._ready && this._interactive;
        if (!zoom && !layers && !locate) return nothing;
        const hidden = this._mapCtl?.value.hidden ?? {};
        return html`
            <div class="pm-controls">
                ${zoom
                    ? html`<div class="pm-ctrl pm-zoom">
                          <button type="button" @click=${() => this._map?.zoomIn()}>+</button>
                          <button type="button" @click=${() => this._map?.zoomOut()}>−</button>
                      </div>`
                    : nothing}
                ${locate
                    ? html`<button
                          type="button"
                          class="pm-ctrl pm-locate-btn"
                          title=${this.t('map.locate')}
                          @click=${this._onLocate}
                      >
                          ◎
                      </button>`
                    : nothing}
                ${layers
                    ? html`<div class="pm-ctrl pm-layers">
                          ${(this._layersOp!.lastResult!.layers ?? []).map(
                              (layer: GeoLayerInfo) => html`
                                  <button
                                      type="button"
                                      class=${hidden[layer.name] ? '' : 'active'}
                                      style="--swatch:${layer.color}"
                                      @click=${() => this._toggleLayer(layer.name)}
                                  >
                                      <span class="pm-dot"></span>${this.t(`layers.${layer.name}`)}
                                      <span class="pm-count">${(layer.features ?? 0).toLocaleString()}</span>
                                  </button>
                              `,
                          )}
                      </div>`
                    : nothing}
            </div>
        `;
    }

    private _renderZoneStats() {
        const s = this._zoneStats;
        if (!s) return nothing;
        return html`
            <div class="pm-stats">
                <span>${this.t('zone_editor.area')} <b>${fmtArea(s.areaM2)} ${this.t('zone_editor.km2')}</b></span>
                <span>${this.t('zone_editor.perimeter')} <b>${fmtKm(s.perimeterM)} ${this.t('zone_editor.km')}</b></span>
                ${!s.valid ? html`<span class="pm-stats-err">${this.t('zone_editor.self_intersection')}</span>` : nothing}
            </div>
        `;
    }

    private _renderAddressesPanel(panel: { zone?: Polygon | MultiPolygon | null; title?: string }) {
        return html`
            <div class="pm-panel">
                <platform-zone-address-panel
                    .zone=${panel.zone ?? null}
                    .title=${panel.title ?? this.t('map.addresses_title')}
                    .addressesOpName=${'geo/addresses_in_zone'}
                    @address-hover=${this._onAddressHover}
                ></platform-zone-address-panel>
            </div>
        `;
    }

    private _toggleLayer(name: string): void {
        this._mapCtl?.toggle({ name });
        this._applyVisibility();
        this.dispatchEvent(new CustomEvent('pm-layer-toggle', { detail: { name }, bubbles: true, composed: true }));
    }

    private _onAddressHover(e: Event): void {
        const detail = (e as CustomEvent<{ lat?: number; lng?: number }>).detail;
        this.dispatchEvent(new CustomEvent('pm-address-hover', { detail, bubbles: true, composed: true }));
        const map = this._map;
        if (!map || typeof detail?.lat !== 'number' || typeof detail.lng !== 'number') return;
        map.easeTo({ center: [detail.lng, detail.lat], duration: 400 });
    }

    override firstUpdated(): void {
        this._el = this.renderRoot.querySelector('.map-canvas');
        void this._initMap();
    }

    override updated(changed: PropertyValues): void {
        if (!changed.has('config') || !this._ready) return;
        // Контроллеры op/slice при изменении состояния зовут host.requestUpdate —
        // выносим side-effects в микротаск, чтобы не планировать update
        // внутри завершённого цикла (Lit dev-warning change-in-update).
        queueMicrotask(() => {
            if (!this._ready) return;
            this._syncOverlays();
            this._syncMarkers();
            if (this._interactive && this._layersFetch) {
                this._applyConfigHiddenLayers();
                this._refresh();
            }
            const lt = this.config.locateTo;
            if (lt && this._map) {
                this._map.easeTo({ center: lt.lngLat, zoom: lt.zoom ?? 15, duration: 600 });
            }
        });
    }

    private async _initMap(): Promise<void> {
        const el = this._el;
        if (!el || this._map) return;
        const maplibre = await loadMapLibre();
        // Пока ждали loadMapLibre/стиль, элемент мог быть detached —
        // disconnectedCallback уже обнулил _el/_map; не монтируем в мёртвый div.
        if (!this.isConnected || this._el !== el) return;
        this._maplibre = maplibre;
        const interactive = this._interactive;
        const map = await createBasemap(el, {
            center: this.config.center ?? DEFAULT_CENTER,
            zoom: this.config.zoom ?? DEFAULT_ZOOM,
            interactive,
        });
        if (this.config.minZoom !== undefined) map.setMinZoom(this.config.minZoom);
        map.touchZoomRotate?.enableRotation();
        this._map = map;
        if (!map.isStyleLoaded()) {
            // Источники и слои — только после load стиля; error отдаём
            // наружу и завершаем init, иначе addSource бросает.
            const ok = await new Promise<boolean>((resolve) => {
                map.once('load', () => resolve(true));
                map.once('error', () => resolve(false));
            });
            if (!ok || this._map !== map) {
                map.remove();
                if (this._map === map) this._map = null;
                if (!ok) {
                    this.dispatchEvent(new CustomEvent('pm-error', { detail: { stage: 'style' }, bubbles: true, composed: true }));
                }
                return;
            }
        }
        this._installSources(map);
        if (interactive) {
            this._installInteractions(maplibre, map);
        }
        this._syncOverlays();
        this._syncMarkers();
        this._ready = true;
        if (interactive && this._layersFetch) {
            this._applyConfigHiddenLayers();
            this._refresh();
            map.on('moveend', this._onMoveEnd);
        }
        if (this.config.draw) {
            await this._initDraw();
        }
        this.dispatchEvent(new CustomEvent('pm-ready', { detail: { map }, bubbles: true, composed: true }));
    }

    private _installSources(map: PlatformMap): void {
        map.addSource('pm-markers', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'pm-markers-circle',
            type: 'circle',
            source: 'pm-markers',
            paint: {
                'circle-radius': ['coalesce', ['get', 'size'], 9],
                'circle-color': ['coalesce', ['get', 'color'], MARKER_COLOR],
                'circle-stroke-width': 3,
                'circle-stroke-color': '#ffffff',
            },
        } as never);
    }

    /** Три style-layer на логический канонический слой: заливка, линии, точки. */
    private _ensureLayer(name: string): void {
        const map = this._map;
        if (!map || this._mapLayers.has(name)) return;
        this._mapLayers.add(name);
        const src = `pm-src-${name}`;
        const color = this._layerColor(name);
        const minzoom = this._layerMinZoom(name);
        map.addSource(src, { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: `pm-lyr-${name}-fill`,
            type: 'fill',
            source: src,
            minzoom,
            filter: ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]],
            paint: { 'fill-color': color, 'fill-opacity': 0.12 },
        } as never);
        map.addLayer({
            id: `pm-lyr-${name}-line`,
            type: 'line',
            source: src,
            minzoom,
            filter: [
                'in',
                ['geometry-type'],
                ['literal', ['LineString', 'MultiLineString', 'Polygon', 'MultiPolygon']],
            ],
            paint: { 'line-color': color, 'line-width': 2.5 },
        } as never);
        map.addLayer({
            id: `pm-lyr-${name}-point`,
            type: 'circle',
            source: src,
            minzoom,
            filter: ['in', ['geometry-type'], ['literal', ['Point', 'MultiPoint']]],
            paint: {
                'circle-radius': 6,
                'circle-color': color,
                'circle-opacity': 0.9,
                'circle-stroke-color': '#ffffff',
                'circle-stroke-width': 2,
            },
        } as never);
    }

    private _featureLayerIds(): string[] {
        const map = this._map;
        if (!map) return [];
        const ids: string[] = [];
        for (const name of this._mapLayers) {
            for (const kind of ['fill', 'line', 'point']) {
                const id = `pm-lyr-${name}-${kind}`;
                if (map.getLayer(id)) ids.push(id);
            }
        }
        return ids;
    }

    private _applyVisibility(): void {
        const map = this._map;
        if (!map) return;
        const hidden = this._mapCtl?.value.hidden ?? {};
        for (const name of this._mapLayers) {
            const visibility = hidden[name] === true ? 'none' : 'visible';
            for (const kind of ['fill', 'line', 'point']) {
                const id = `pm-lyr-${name}-${kind}`;
                if (map.getLayer(id)) {
                    map.setLayoutProperty(id, 'visibility', visibility);
                }
            }
        }
    }

    private _installInteractions(maplibre: MapLibreModule, map: PlatformMap): void {
        const { Popup } = maplibre;
        map.on('click', (e: { lngLat: { lng: number; lat: number }; point: { x: number; y: number } }) => {
            const feats = this._featuresAt(map, e.point);
            const detail = {
                lngLat: [e.lngLat.lng, e.lngLat.lat] as LngLat,
                features: feats.map((f) => ({ layer: f.layer, properties: f.properties })),
            };
            this.dispatchEvent(new CustomEvent('pm-click', { detail, bubbles: true, composed: true }));
            const markerHit = this._markerAt(map, e.point);
            if (markerHit) {
                this.dispatchEvent(
                    new CustomEvent('pm-marker-click', {
                        detail: { key: markerHit.key, lngLat: markerHit.lngLat },
                        bubbles: true,
                        composed: true,
                    }),
                );
            }
            if (this._clickCardEnabled && feats.length > 0) {
                this._showCard(maplibre, map, [e.lngLat.lng, e.lngLat.lat], feats);
            }
        });
        if (this._hoverEnabled) {
            map.on('mousemove', (e: { lngLat: { lng: number; lat: number }; point: { x: number; y: number } }) => {
                const feats = this._featuresAt(map, e.point);
                const markerHit = this._markerAt(map, e.point);
                map.getCanvas().style.cursor = feats.length > 0 || markerHit ? 'pointer' : '';
                if (feats.length > 0) {
                    const text = featureTitle({ layer: feats[0]!.layer, properties: feats[0]!.properties });
                    if (text !== '') {
                        if (!this._hintPopup) {
                            this._hintPopup = new Popup({ closeButton: false, closeOnClick: false, className: 'pm-hint' });
                        }
                        const popup = this._hintPopup as { setLngLat(l: unknown): { setText(t: string): { addTo(m: PlatformMap): void } } };
                        popup.setLngLat(e.lngLat).setText(text).addTo(map);
                        return;
                    }
                }
                this._hideHint();
            });
            map.getCanvas().addEventListener('mouseleave', () => this._hideHint());
        }
    }

    private _hideHint(): void {
        this._hintPopup?.remove();
        this._hintPopup = null;
    }

    private _featuresAt(map: PlatformMap, point: { x: number; y: number }): { layer: string; properties: Record<string, unknown> }[] {
        const layerIds = this._featureLayerIds();
        if (layerIds.length === 0) return [];
        type QueryFn = (p: [number, number], o?: { layers?: string[] }) => { properties?: Record<string, unknown> | null }[];
        const query = (map as unknown as { queryRenderedFeatures: QueryFn }).queryRenderedFeatures.bind(map);
        const hits = query([point.x, point.y], { layers: layerIds });
        return hits
            .slice(0, 8)
            .map((h) => ({
                layer: String(h.properties?.['layer'] ?? ''),
                properties: { ...(h.properties ?? {}) },
            }))
            .filter((h) => h.layer !== '');
    }

    private _markerAt(map: PlatformMap, point: { x: number; y: number }): { key: string; lngLat: LngLat } | null {
        if (!map.getLayer('pm-markers-circle')) return null;
        type QF = (p: [number, number], o?: { layers?: string[] }) => { properties?: Record<string, unknown> | null; geometry?: { coordinates?: unknown } }[];
        const query = (map as unknown as { queryRenderedFeatures: QF }).queryRenderedFeatures.bind(map);
        const hits = query([point.x, point.y], { layers: ['pm-markers-circle'] });
        const hit = hits[0];
        if (!hit) return null;
        const coords = hit.geometry?.coordinates as LngLat | undefined;
        return {
            key: String(hit.properties?.['key'] ?? ''),
            lngLat: coords ?? [0, 0],
        };
    }

    private _showCard(
        maplibre: MapLibreModule,
        map: PlatformMap,
        lngLat: LngLat,
        feats: { layer: string; properties: Record<string, unknown> }[],
    ): void {
        this._cardPopup?.remove();
        const t = (k: string) => this.t(k);
        const colorFor = (name: string): string | null => {
            const info = (this._layersOp?.lastResult?.layers ?? []).find((l) => l.name === name);
            return info ? info.color : null;
        };
        const coords = `${lngLat[1].toFixed(5)}, ${lngLat[0].toFixed(5)}`;
        const cards = feats
            .slice(0, 3)
            .map((f) => {
                const props = { ...f.properties, __coords: coords };
                return renderFeatureCard({ layer: f.layer, properties: props }, t, colorFor(f.layer));
            })
            .join('');
        this._cardPopup = new maplibre.Popup({ closeButton: true, className: 'pm-card-popup', maxWidth: '340px' })
            .setLngLat(lngLat)
            .setHTML(cards)
            .addTo(map) as unknown as { remove(): void };
    }

    private _applyConfigHiddenLayers(): void {
        if (this._configLayersApplied || !this._mapCtl) return;
        this._configLayersApplied = true;
        for (const name of this.config.layers?.hidden ?? []) {
            if (!this._mapCtl.value.hidden[name]) {
                this._mapCtl.toggle({ name });
            }
        }
        this._applyVisibility();
    }

    private _onMoveEnd = (): void => {
        if (this._refreshTimer !== null) window.clearTimeout(this._refreshTimer);
        this._refreshTimer = window.setTimeout(() => this._refresh(), REFRESH_DEBOUNCE_MS);
    };

    private _refresh(): void {
        const map = this._map;
        const op = this._featuresOp;
        if (!map || !op) return;
        const b = map.getBounds();
        void op
            .run({
                south: b.getSouth(),
                west: b.getWest(),
                north: b.getNorth(),
                east: b.getEast(),
                zoom: Math.round(map.getZoom()),
                layers: [],
            })
            .then((res) => {
                if (this._featuresOp !== op || !res) return;
                const perLayer = new Map<string, Feature[]>();
                for (const f of res.features ?? []) {
                    const feature: Feature = {
                        type: 'Feature',
                        geometry: f.geometry as unknown as Geometry,
                        properties: { layer: f.layer, ...f.properties },
                    };
                    const bucket = perLayer.get(f.layer);
                    if (bucket) bucket.push(feature);
                    else perLayer.set(f.layer, [feature]);
                }
                for (const name of this._mapLayers) {
                    if (!perLayer.has(name)) {
                        this._setSourceData(`pm-src-${name}`, _EMPTY_FC);
                    }
                }
                for (const [name, features] of perLayer) {
                    this._ensureLayer(name);
                    this._setSourceData(`pm-src-${name}`, { type: 'FeatureCollection', features });
                }
                this._applyVisibility();
            });
    }

    private _setSourceData(id: string, data: FeatureCollection): void {
        const source = this._map?.getSource(id) as { setData(d: FeatureCollection): void } | undefined;
        source?.setData(data);
    }

    private _syncOverlays(): void {
        const map = this._map;
        if (!map) return;
        const overlays = this.config.overlays ?? [];
        const wanted = new Set(overlays.map((o) => `pm-ov-${o.name}`));
        for (const id of this._overlayIds(map)) {
            if (!wanted.has(id)) {
                const layerId = `${id}-layer`;
                const fillId = `${id}-fill`;
                if (map.getLayer(layerId)) map.removeLayer(layerId);
                if (map.getLayer(fillId)) map.removeLayer(fillId);
                if (map.getSource(id)) map.removeSource(id);
            }
        }
        for (const ov of overlays) {
            const sid = `pm-ov-${ov.name}`;
            const color = ov.color ?? OVERLAY_COLOR;
            const data = ov.data;
            const src = map.getSource(sid) as { setData(d: Feature | FeatureCollection): void } | undefined;
            if (src) {
                src.setData(data);
            } else {
                map.addSource(sid, { type: 'geojson', data });
                map.addLayer({
                    id: `${sid}-fill`,
                    type: 'fill',
                    source: sid,
                    filter: ['==', ['geometry-type'], 'Polygon'],
                    paint: { 'fill-color': color, 'fill-opacity': ov.opacity ?? 0.15 },
                } as never);
                map.addLayer({
                    id: `${sid}-layer`,
                    type: 'line',
                    source: sid,
                    paint: { 'line-color': color, 'line-width': ov.width ?? 3 },
                } as never);
            }
            if (ov.fit) {
                this._fitOverlay(data, ov.fitPadding ?? 48);
            }
        }
    }

    private _overlayIds(map: PlatformMap): string[] {
        const style = (map as unknown as { getStyle(): { sources?: Record<string, unknown> } }).getStyle();
        return Object.keys(style?.sources ?? {}).filter((k) => k.startsWith('pm-ov-'));
    }

    private _fitOverlay(data: Feature | FeatureCollection, padding: number): void {
        const map = this._map;
        if (!map) return;
        const coords: LngLat[] = [];
        const collect = (g: Geometry | null | undefined): void => {
            if (!g) return;
            if (g.type === 'Polygon') {
                for (const ring of g.coordinates) for (const c of ring) coords.push(c as LngLat);
            } else if (g.type === 'MultiPolygon') {
                for (const poly of g.coordinates) for (const ring of poly) for (const c of ring) coords.push(c as LngLat);
            } else if (g.type === 'LineString') {
                for (const c of g.coordinates) coords.push(c as LngLat);
            } else if (g.type === 'Point') {
                coords.push(g.coordinates as LngLat);
            }
        };
        if (data.type === 'FeatureCollection') {
            for (const f of data.features) collect(f.geometry);
        } else {
            collect(data.geometry);
        }
        if (coords.length === 0) return;
        let w = coords[0]![0];
        let e = w;
        let s = coords[0]![1];
        let n = s;
        for (const [lng, lat] of coords) {
            w = Math.min(w, lng);
            e = Math.max(e, lng);
            s = Math.min(s, lat);
            n = Math.max(n, lat);
        }
        map.fitBounds(
            [
                [w, s],
                [e, n],
            ],
            { padding, duration: 500 },
        );
    }

    private _syncMarkers(): void {
        const map = this._map;
        if (!map) return;
        const src = map.getSource('pm-markers') as { setData(d: FeatureCollection): void } | undefined;
        if (!src) return;
        const features = (this.config.markers ?? []).map((m) => ({
            type: 'Feature' as const,
            geometry: { type: 'Point' as const, coordinates: m.lngLat },
            properties: { key: m.key ?? '', color: m.color ?? MARKER_COLOR, size: m.size ?? 9, title: m.title ?? '' },
        }));
        src.setData({ type: 'FeatureCollection', features });
    }

    private async _initDraw(): Promise<void> {
        const map = this._map;
        const drawCfg = this.config.draw;
        if (!map || !drawCfg) return;
        this._zoneDraw = await createZoneDraw(map);
        const { draw, validate } = this._zoneDraw;
        const emit = (): void => {
            const snap = draw.getSnapshot() as DrawFeature[];
            const poly = snap.find((f) => f.geometry.type === 'Polygon' || f.geometry.type === 'MultiPolygon');
            const zone = (poly?.geometry as Polygon | MultiPolygon | undefined) ?? null;
            const valid = poly ? validate(poly as Feature) : true;
            const stats = zone ? { ..._zoneStats(zone), valid } : null;
            this._zoneStats = stats;
            this.dispatchEvent(
                new CustomEvent('pm-draw-change', {
                    detail: {
                        zone,
                        valid,
                        areaM2: stats?.areaM2 ?? 0,
                        perimeterM: stats?.perimeterM ?? 0,
                    },
                    bubbles: true,
                    composed: true,
                }),
            );
        };
        draw.on('finish', () => {
            draw.setMode('select');
            emit();
        });
        draw.on('change', emit);
        const zone = drawCfg.zone ?? null;
        if (zone) {
            draw.addFeatures([
                {
                    type: 'Feature',
                    geometry: zone,
                    properties: { mode: 'polygon' },
                } as never,
            ]);
            emit();
        }
        draw.setMode('select');
    }

    private _onLocate = (): void => {
        const map = this._map;
        const maplibre = this._maplibre;
        if (!map || !maplibre) return;
        const onFix = (pos: { coords: { longitude: number; latitude: number } }): void => {
            const lngLat: LngLat = [pos.coords.longitude, pos.coords.latitude];
            map.easeTo({ center: lngLat, zoom: 16, duration: 700 });
            this._locateMarker?.remove();
            this._locateMarker = new maplibre.Marker({ color: '#155dfc' }).setLngLat(lngLat).addTo(map) as unknown as {
                remove(): void;
            };
            void this._nearestOp?.run({ lat: lngLat[1], lng: lngLat[0], limit: 3 }).then((res) => {
                this.dispatchEvent(
                    new CustomEvent('pm-locate', {
                        detail: { lngLat, addresses: res?.items ?? [] },
                        bubbles: true,
                        composed: true,
                    }),
                );
            });
        };
        navigator.geolocation.getCurrentPosition(onFix, () => {
            this.dispatchEvent(new CustomEvent('pm-locate', { detail: { error: 'denied' }, bubbles: true, composed: true }));
        });
    };

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (this._refreshTimer !== null) window.clearTimeout(this._refreshTimer);
        this._zoneDraw?.draw.stop();
        this._zoneDraw = null;
        this._map?.remove();
        this._map = null;
        this._el = null;
        this._hintPopup = null;
        this._cardPopup = null;
        this._locateMarker = null;
        this._configLayersApplied = false;
        this._mapLayers = new Set();
    }

    static override styles = css`
        :host {
            display: block;
        }
        .pm-wrap {
            position: relative;
            width: 100%;
            height: 100%;
            overflow: hidden;
            border-radius: inherit;
        }
        .map-canvas {
            position: absolute;
            inset: 0;
        }
        .pm-controls {
            position: absolute;
            top: 12px;
            right: 12px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            align-items: flex-end;
            z-index: 5;
        }
        .pm-ctrl {
            background: var(--color-surface, #fff);
            border: 1px solid var(--color-border, #e2e8f0);
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
            overflow: hidden;
        }
        .pm-zoom {
            display: flex;
            flex-direction: column;
        }
        .pm-zoom button {
            width: 36px;
            height: 34px;
            border: 0;
            background: transparent;
            font-size: 18px;
            cursor: pointer;
            color: var(--color-text, #0f172a);
        }
        .pm-zoom button + button {
            border-top: 1px solid var(--color-border, #e2e8f0);
        }
        .pm-locate-btn {
            width: 36px;
            height: 36px;
            font-size: 16px;
            cursor: pointer;
            color: var(--color-text, #0f172a);
        }
        .pm-layers {
            display: flex;
            flex-direction: column;
            padding: 4px;
        }
        .pm-layers button {
            display: flex;
            align-items: center;
            gap: 7px;
            padding: 6px 9px;
            border: 0;
            border-radius: 7px;
            background: transparent;
            font-size: 12px;
            cursor: pointer;
            color: var(--color-text-muted, #64748b);
            white-space: nowrap;
        }
        .pm-layers button.active {
            color: var(--color-text, #0f172a);
            background: var(--color-surface-muted, #f1f5f9);
        }
        .pm-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--swatch, #888);
            opacity: 0.35;
        }
        .pm-layers button.active .pm-dot {
            opacity: 1;
        }
        .pm-count {
            margin-left: auto;
            font-size: 10px;
            color: var(--color-text-muted, #94a3b8);
        }
        .pm-stats {
            position: absolute;
            left: 12px;
            bottom: 12px;
            display: flex;
            gap: 14px;
            padding: 8px 12px;
            background: var(--color-surface, #fff);
            border: 1px solid var(--color-border, #e2e8f0);
            border-radius: 10px;
            font-size: 12px;
            color: var(--color-text-muted, #64748b);
            z-index: 5;
        }
        .pm-stats b {
            color: var(--color-text, #0f172a);
        }
        .pm-stats-err {
            color: var(--color-danger, #dc2626);
        }
        .pm-panel {
            position: absolute;
            top: 12px;
            left: 12px;
            bottom: 12px;
            width: 300px;
            z-index: 6;
            display: flex;
        }
        .pm-panel platform-zone-address-panel {
            flex: 1;
            min-height: 0;
        }
        .pm-hint {
            font-size: 12px;
        }
        :host .pm-card-popup .maplibregl-popup-content,
        :host .pm-hint .maplibregl-popup-content {
            border-radius: 12px;
            box-shadow: 0 6px 24px rgba(15, 23, 42, 0.18);
            padding: 0;
        }
    `;
}

declare global {
    interface HTMLElementTagNameMap {
        'platform-map': PlatformMapEl;
    }
}

if (!customElements.get('platform-map')) {
    customElements.define('platform-map', PlatformMapEl);
}

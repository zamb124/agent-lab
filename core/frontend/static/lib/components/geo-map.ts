/**
 * GeoMap — векторная карта с каноническими слоями Geo.
 *
 * Базовая карта — MapLibre + style.json geo-сервиса (см. `map/basemap.ts`).
 * Источник данных — команды `geo/layers/*`: реестр (цвет, min_zoom,
 * счётчики) грузится один раз, фичи — GeoJSON по рамке на каждый
 * `moveend` (debounce). На каждый логический слой — geojson-source
 * `geo-src-<name>` и три style-layer (circle/line/fill); видимость —
 * slice `geo/map` (`hidden[name]`) через `layout.visibility`, без
 * повторного запроса.
 *
 * Свойства:
 *   center  — [lat, lng] начального центра (default — центр покрытия dev).
 *   zoom    — начальный зум.
 *   overlay — GeoJSON Feature/FeatureCollection поверх слоёв (маршрут,
 *             изохрона); null — снять.
 *
 * События:
 *   `geo-map-click` — detail {lat, lng} по клику на карте.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { SliceControllerOf } from '@platform/lib/base/use-resource.js';
import { maplibreCssLink } from '@platform/lib/map/maplibre.js';
import { createBasemap } from '@platform/lib/map/basemap.js';
import type { PlatformMap } from '@platform/lib/map/basemap.js';
import type { OpControllerOf } from '../base/use-resource.js';
import type { geoLayersOp, geoLayerFeaturesOp } from '../events/resources/geo-layers.resource.js';
import type { GeoFeature, GeoLayerInfo } from '../events/wire/geo.gen.js';
import { geoMapSlice } from '../events/resources/geo-layers.resource.js';
import '../events/resources/geo-layers.resource.js';

import type {
    Feature,
    FeatureCollection,
    GeoJSON,
    Geometry,
} from 'geojson';

export type GeoJsonOverlay = {
    type: string;
    geometry?: Record<string, unknown>;
    features?: GeoJsonOverlay[];
    properties?: Record<string, unknown>;
};

const DEFAULT_CENTER: [number, number] = [55.7512, 37.6184];
const DEFAULT_ZOOM = 10;
const REFRESH_DEBOUNCE_MS = 250;
const OVERLAY_COLOR = '#2563eb';

const _EMPTY_FC: FeatureCollection = { type: 'FeatureCollection', features: [] };

export class GeoMap extends PlatformElement {
    static i18nNamespace = 'geo';

    static override properties: PropertyDeclarations = {
        center: { type: Array, attribute: false },
        zoom: { type: Number },
        overlay: { type: Object, attribute: false },
        interactive: { type: Boolean },
        _loading: { state: true },
    };

    declare center: [number, number];
    declare zoom: number;
    declare overlay: GeoJsonOverlay | null;
    declare interactive: boolean;
    declare _loading: boolean;

    private _map: PlatformMap | null = null;
    private _markerFeatures: Feature[] = [];
    private _ro: ResizeObserver | null = null;
    private _debounce: number | null = null;
    private _layersCtl: OpControllerOf<typeof geoLayersOp>;
    private _featuresCtl: OpControllerOf<typeof geoLayerFeaturesOp>;
    private _mapCtl: SliceControllerOf<typeof geoMapSlice>;
    private _layersMeta = new Map<string, GeoLayerInfo>();
    private _mapLayers = new Set<string>();

    constructor() {
        super();
        this.center = DEFAULT_CENTER;
        this.zoom = DEFAULT_ZOOM;
        this.overlay = null;
        this.interactive = true;
        this._loading = false;
        this._layersCtl = this.useOp('geo/layers');
        this._featuresCtl = this.useOp('geo/layer_features');
        this._mapCtl = this.useSlice('geo/map');
    }

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; position: relative; }
            .mapwrap {
                position: relative;
                width: 100%;
                height: 100%;
                min-height: 320px;
                border-radius: var(--radius-m, 12px);
                overflow: hidden;
                border: 1px solid color-mix(in srgb, var(--text-primary) 12%, transparent);
                background: var(--bg-secondary, #f2f0ec);
            }
            .map { position: absolute; inset: 0; }
            .busy-badge {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                z-index: 600;
                padding: var(--space-1) var(--space-3);
                border-radius: var(--radius-full, 999px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 92%, transparent);
                backdrop-filter: blur(12px);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                pointer-events: none;
            }
            .layers-slot {
                position: absolute;
                top: var(--space-3);
                left: var(--space-3);
                z-index: 600;
            }
        `,
    ];

    override firstUpdated(): void {
        void this._init();
    }

    override disconnectedCallback(): void {
        this._ro?.disconnect();
        this._ro = null;
        if (this._debounce !== null) {
            clearTimeout(this._debounce);
            this._debounce = null;
        }
        this._map?.remove();
        this._map = null;
        this._mapLayers.clear();
        this._markerFeatures = [];
        super.disconnectedCallback();
    }

    protected override updated(changed: PropertyValues<this>): void {
        if (!this._map) return;
        this._applyVisibility();
        if (changed.has('overlay')) this._drawOverlay();
    }

    /** Публичный сброс маркеров-маршрута (клики лаборатории). */
    addMarker(lat: number, lng: number, color: string): void {
        this._markerFeatures.push({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [lng, lat] },
            properties: { color },
        });
        this._setSourceData('geo-markers', {
            type: 'FeatureCollection',
            features: this._markerFeatures,
        });
    }

    clearMarkers(): void {
        this._markerFeatures = [];
        this._setSourceData('geo-markers', _EMPTY_FC);
    }

    private _hidden(): Record<string, boolean> {
        return this._mapCtl.value.hidden;
    }

    private async _init(): Promise<void> {
        const el = this.renderRoot.querySelector<HTMLElement>('.map');
        if (!el || this._map) return;
        const map = (this._map = await createBasemap(el, {
            center: [this.center[1], this.center[0]],
            zoom: this.zoom,
            interactive: this.interactive,
        }));
        map.on('moveend', () => this._scheduleRefresh());
        map.on('click', (e) => {
            if (!this.interactive) return;
            this.dispatchEvent(
                new CustomEvent('geo-map-click', {
                    detail: { lat: e.lngLat.lat, lng: e.lngLat.lng },
                    bubbles: true,
                    composed: true,
                }),
            );
        });
        this._ro = new ResizeObserver(() => {
            if (!this._map || !el.offsetWidth || !el.offsetHeight) return;
            this._map.resize();
        });
        this._ro.observe(el);
        await this._mapLoaded(map);
        this._ensureAuxSources();
        await this._loadLayers();
        await this._refresh();
    }

    private _mapLoaded(map: PlatformMap): Promise<void> {
        return new Promise((resolve) => {
            if (map.isStyleLoaded()) resolve();
            else map.once('load', () => resolve());
        });
    }

    private async _loadLayers(): Promise<void> {
        const res = await this._layersCtl.run({});
        for (const layer of res?.layers ?? []) {
            this._layersMeta.set(layer.name, layer);
        }
    }

    private _scheduleRefresh(): void {
        if (this._debounce !== null) clearTimeout(this._debounce);
        this._debounce = window.setTimeout(() => {
            this._debounce = null;
            void this._refresh();
        }, REFRESH_DEBOUNCE_MS);
    }

    private _setSourceData(id: string, data: FeatureCollection): void {
        const source = this._map?.getSource(id) as
            | { setData(d: GeoJSON): void }
            | undefined;
        source?.setData(data);
    }

    /** Три style-layer на логический слой: точки, линии+контуры, заливка. */
    private _ensureLayer(name: string): void {
        const map = this._map;
        if (!map || this._mapLayers.has(name)) return;
        this._mapLayers.add(name);
        const src = `geo-src-${name}`;
        map.addSource(src, { type: 'geojson', data: _EMPTY_FC });
        const color = this._layersMeta.get(name)?.color ?? '#475569';
        const minzoom = this._layersMeta.get(name)?.min_zoom ?? 0;
        map.addLayer({
            id: `geo-lyr-${name}-fill`,
            type: 'fill',
            source: src,
            minzoom,
            filter: ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]],
            paint: { 'fill-color': color, 'fill-opacity': 0.12 },
        });
        map.addLayer({
            id: `geo-lyr-${name}-line`,
            type: 'line',
            source: src,
            minzoom,
            filter: [
                'in',
                ['geometry-type'],
                ['literal', ['LineString', 'MultiLineString', 'Polygon', 'MultiPolygon']],
            ],
            paint: { 'line-color': color, 'line-width': 2.5 },
        });
        map.addLayer({
            id: `geo-lyr-${name}-point`,
            type: 'circle',
            source: src,
            minzoom,
            filter: ['in', ['geometry-type'], ['literal', ['Point', 'MultiPoint']]],
            paint: {
                'circle-radius': 5,
                'circle-color': color,
                'circle-opacity': 0.85,
                'circle-stroke-color': color,
                'circle-stroke-width': 1.5,
            },
        });
    }

    private _applyVisibility(): void {
        const map = this._map;
        if (!map) return;
        const hidden = this._hidden();
        for (const name of this._mapLayers) {
            const visible = hidden[name] === true ? 'none' : 'visible';
            for (const kind of ['fill', 'line', 'point']) {
                map.setLayoutProperty(`geo-lyr-${name}-${kind}`, 'visibility', visible);
            }
        }
    }

    private async _refresh(): Promise<void> {
        const map = this._map;
        if (!map) return;
        const bounds = map.getBounds();
        this._loading = true;
        try {
            const res = await this._featuresCtl.run({
                south: bounds.getSouth(),
                west: bounds.getWest(),
                north: bounds.getNorth(),
                east: bounds.getEast(),
                zoom: Math.round(map.getZoom()),
                layers: [],
            });
            if (!this._map) return;
            const perLayer = new Map<string, Feature[]>();
            for (const feature of res?.features ?? []) {
                const geoFeature: Feature = {
                    type: 'Feature',
                    geometry: feature.geometry as unknown as Geometry,
                    properties: { layer: feature.layer },
                };
                const bucket = perLayer.get(feature.layer);
                if (bucket) bucket.push(geoFeature);
                else perLayer.set(feature.layer, [geoFeature]);
            }
            for (const name of this._mapLayers) {
                if (!perLayer.has(name)) {
                    this._setSourceData(`geo-src-${name}`, _EMPTY_FC);
                }
            }
            for (const [name, features] of perLayer) {
                this._ensureLayer(name);
                this._setSourceData(`geo-src-${name}`, {
                    type: 'FeatureCollection',
                    features,
                });
            }
            this._applyVisibility();
        } finally {
            this._loading = false;
        }
    }

    private _ensureAuxSources(): void {
        const map = this._map;
        if (!map) return;
        map.addSource('geo-overlay', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'geo-lyr-overlay-fill',
            type: 'fill',
            source: 'geo-overlay',
            filter: ['in', ['geometry-type'], ['literal', ['Polygon', 'MultiPolygon']]],
            paint: { 'fill-color': OVERLAY_COLOR, 'fill-opacity': 0.08 },
        });
        map.addLayer({
            id: 'geo-lyr-overlay-line',
            type: 'line',
            source: 'geo-overlay',
            filter: [
                'in',
                ['geometry-type'],
                ['literal', ['LineString', 'MultiLineString', 'Polygon', 'MultiPolygon']],
            ],
            paint: { 'line-color': OVERLAY_COLOR, 'line-width': 4 },
        });
        map.addSource('geo-markers', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'geo-lyr-markers',
            type: 'circle',
            source: 'geo-markers',
            paint: {
                'circle-radius': 7,
                'circle-color': ['coalesce', ['get', 'color'], '#2563eb'],
                'circle-opacity': 0.9,
                'circle-stroke-color': ['coalesce', ['get', 'color'], '#2563eb'],
                'circle-stroke-width': 2,
            },
        });
    }

    private _drawOverlay(): void {
        const map = this._map;
        if (!map) return;
        const data = (this.overlay ?? _EMPTY_FC) as FeatureCollection;
        this._setSourceData('geo-overlay', data);
        if (this.overlay === null) return;
        const coords: [number, number][] = [];
        const collect = (node: unknown): void => {
            if (!Array.isArray(node)) return;
            if (
                node.length === 2 &&
                typeof node[0] === 'number' &&
                typeof node[1] === 'number'
            ) {
                coords.push([node[0], node[1]]);
                return;
            }
            for (const child of node) collect(child);
        };
        const walk = (item: GeoJsonOverlay): void => {
            const geometry = item.geometry;
            if (geometry && 'coordinates' in geometry) collect(geometry.coordinates);
            for (const feature of item.features ?? []) walk(feature);
        };
        walk(this.overlay);
        if (!coords.length) return;
        const lngs = coords.map((c) => c[0]);
        const lats = coords.map((c) => c[1]);
        map.fitBounds(
            [
                [Math.min(...lngs), Math.min(...lats)],
                [Math.max(...lngs), Math.max(...lats)],
            ],
            { padding: 32, animate: false },
        );
    }

    protected override render(): TemplateResult {
        return html`
            ${maplibreCssLink()}
            <div class="mapwrap">
                <div class="map"></div>
                <div class="layers-slot"><slot name="panel"></slot></div>
                ${this._loading ? html`<div class="busy-badge">${this.t('map.loading')}</div>` : nothing}
            </div>
        `;
    }
}

if (!customElements.get('geo-map')) {
    customElements.define('geo-map', GeoMap);
}

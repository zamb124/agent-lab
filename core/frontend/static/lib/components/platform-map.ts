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
import { maplibreCssLink, loadMapLibre, basemapStyleUrl } from '@platform/lib/map/maplibre.js';
import type { BasemapScheme, MapLibreModule } from '@platform/lib/map/maplibre.js';
import { createBasemap } from '@platform/lib/map/basemap.js';
import type { PlatformMap } from '@platform/lib/map/basemap.js';
import { createZoneDraw } from '@platform/lib/map/zone-draw.js';
import type { ZoneDraw } from '@platform/lib/map/zone-draw.js';
import { ringAreaM2, ringPerimeterM, haversineM, fmtArea } from '@platform/lib/map/geo-math.js';
import { renderFeatureCard, featureTitle } from '@platform/lib/map/feature-card.js';
import './platform-zone-address-panel.js';
import '../events/resources/geo-layers.resource.js';
import '../events/resources/geo-addresses.resource.js';
import '../events/resources/geo-route.resource.js';
import type { geoLayersOp, geoLayerFeaturesOp, geoMapSlice } from '../events/resources/geo-layers.resource.js';
import type { geoAddressNearestOp, geoAddressSuggestOp } from '../events/resources/geo-addresses.resource.js';
import type { geoRouteOp, geoIsochroneOp } from '../events/resources/geo-route.resource.js';
import type { GeoAddressHit, GeoFeature, GeoLayerInfo } from '../events/wire/geo.gen.js';
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
    /** DOM-маркер с drag-жестом; по отпусканию — событие pm-marker-drag. */
    draggable?: boolean;
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

export type PlatformMapRouteMode = 'car' | 'foot' | 'bike' | 'scooter';

export interface PlatformMapConfig {
    center?: LngLat;
    zoom?: number;
    minZoom?: number;
    maxZoom?: number;
    interactive?: boolean;
    /** Безопасные поля камеры — панели хоста не перекрывают контент. */
    padding?: number;
    /** Схема базовой карты: light/dark; controls.scheme — кнопка-переключатель. */
    scheme?: 'light' | 'dark';
    /** Поворот/наклон камеры жестами (dragRotate/two-finger); нужен для compass. */
    rotate?: boolean;
    controls?: {
        zoom?: boolean;
        layers?: boolean;
        locate?: boolean;
        /** Поиск адреса по каноническому справочнику (geo/addresses_suggest). */
        search?: boolean;
        fullscreen?: boolean;
        /** Метрический масштаб в углу (нативный ScaleControl). */
        scale?: boolean;
        /** Линейка: клики ставят вершины, длина на сегментах и итог. */
        ruler?: boolean;
        /** Линейка площади: клики строят полигон, итог — площадь в м²/км². */
        rulerArea?: boolean;
        /** Кнопка «к содержимому»: fitBounds по оверлеям/маркерам/слоям. */
        fit?: boolean;
        /** Компас: показывает bearing, клик — север вверх. */
        compass?: boolean;
        /** Переключатель светлой/тёмной схемы базовой карты. */
        scheme?: boolean;
        /** Кнопка «маршрут»: режим построения кликами (требует route.build). */
        route?: boolean;
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
    /** Кластеризация точечных маркеров (кружки со счётчиком, zoom по клику). */
    markersCluster?: boolean;
    overlays?: PlatformMapOverlay[];
    /** Поиск по карте: параметры suggest-дропдауна и поведение выбора. */
    search?: {
        placeholder?: string;
        limit?: number;
        /** Zoom после выбора подсказки (default 16). */
        flyZoom?: number;
        /** Ставить pin на выбранном результате (default true). */
        pin?: boolean;
    } | false;
    /** Правый клик: меню «Что здесь?» (reverse geocode) + копирование координат. */
    contextMenu?: boolean;
    /** Нижняя строка состояния: координаты курсора и zoom. */
    statusBar?: boolean;
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
    /**
     * Маршрут A → via… → B по дорожному графу (geo/route на каждое плечо).
     * Линия + точки с буквами + ETA-чип «N км · M мин» с выбором режима.
     * `build: true` — точки расставляются кликами по карте (A, B, далее via).
     */
    route?: {
        points?: LngLat[];
        mode?: PlatformMapRouteMode;
        /** controls.route — кнопка входа в режим построения кликами. */
        build?: boolean;
        /** fitBounds по линии после расчёта (default true при build). */
        fit?: boolean;
        color?: string;
        /** Чип режима A↔B: смена mode пересчитывает маршрут (default true). */
        panel?: boolean;
    } | false;
    /**
     * Контуры достижимости за N минут от точки (geo/isochrone на каждый
     * порог; бóльшие рисуются под меньшими). Маркер центра + лейблы минут.
     */
    isochrone?: {
        center: LngLat;
        minutes: number[];
        mode?: PlatformMapRouteMode;
        colors?: string[];
    } | false;
    /** Событие pm-move на каждый moveend — синхронизация состояния для хостов. */
    moveEvent?: boolean;
}

type FeatureGeometry = Point | LineString | Polygon | MultiPolygon;
type GeoFeatureOf = Feature<FeatureGeometry, GeoJsonProperties>;
type DrawFeature = Feature<Polygon | MultiPolygon>;

const DEFAULT_CENTER: LngLat = [37.6184, 55.7512];
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
        _mode: { state: true },
        _error: { state: true },
        _searchQuery: { state: true },
        _suggestItems: { state: true },
        _suggestOpen: { state: true },
        _suggestBusy: { state: true },
        _cursorText: { state: true },
        _fullscreen: { state: true },
        _menu: { state: true },
        _searchPin: { state: true },
        _bearing: { state: true },
        _routeInfo: { state: true },
        _routeBusy: { state: true },
        _routeBuildPts: { state: true },
    };

    declare config: PlatformMapConfig;
    declare _ready: boolean;
    declare _zoneStats: { areaM2: number; perimeterM: number; valid: boolean } | null;
    declare _mode: 'select' | 'ruler' | 'area' | 'route';
    declare _error: 'style' | 'init' | null;
    declare _searchQuery: string;
    declare _suggestItems: GeoAddressHit[];
    declare _suggestOpen: boolean;
    declare _suggestBusy: boolean;
    declare _cursorText: string;
    declare _fullscreen: boolean;
    declare _menu: { x: number; y: number; lngLat: LngLat } | null;
    declare _searchPin: LngLat | null;
    declare _bearing: number;
    declare _routeInfo: { distanceM: number; durationS: number } | null;
    declare _routeBusy: boolean;
    declare _routeBuildPts: LngLat[];

    private _el: HTMLDivElement | null = null;
    private _map: PlatformMap | null = null;
    private _maplibre: MapLibreModule | null = null;
    private _mapCtl: SliceControllerOf<typeof geoMapSlice> | null = null;
    private _featuresOp: OpControllerOf<typeof geoLayerFeaturesOp> | null = null;
    private _layersOp: OpControllerOf<typeof geoLayersOp> | null = null;
    private _nearestOp: OpControllerOf<typeof geoAddressNearestOp> | null = null;
    private _suggestOp: OpControllerOf<typeof geoAddressSuggestOp> | null = null;
    private _routeOp: OpControllerOf<typeof geoRouteOp> | null = null;
    private _isoOp: OpControllerOf<typeof geoIsochroneOp> | null = null;
    private _routeSeq = 0;
    private _isoSeq = 0;
    private _scheme: BasemapScheme = 'light';
    private _refreshTimer: number | null = null;
    private _suggestTimer: number | null = null;
    private _hintPopup: { remove(): void; setLngLat(l: unknown): unknown } | null = null;
    private _cardPopup: { remove(): void } | null = null;
    private _zoneDraw: ZoneDraw | null = null;
    private _locateMarker: { remove(): void } | null = null;
    private _domMarkers: { remove(): void }[] = [];
    private _clusterHandlersBound = false;
    private _rulerPoints: LngLat[] = [];
    private _configLayersApplied = false;
    private _mapLayers = new Set<string>();

    constructor() {
        super();
        this.config = {};
        this._ready = false;
        this._zoneStats = null;
        this._mode = 'select';
        this._error = null;
        this._searchQuery = '';
        this._suggestItems = [];
        this._suggestOpen = false;
        this._suggestBusy = false;
        this._cursorText = '';
        this._fullscreen = false;
        this._menu = null;
        this._searchPin = null;
        this._bearing = 0;
        this._routeInfo = null;
        this._routeBusy = false;
        this._routeBuildPts = [];
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
        if (this.config.controls?.locate === true || this.config.contextMenu === true) {
            this._nearestOp = this.useOp('geo/addresses_nearest');
        }
        if (this.config.controls?.search === true && this.config.search !== false) {
            this._suggestOp = this.useOp('geo/addresses_suggest');
        }
        if (this.config.route) {
            this._routeOp = this.useOp('geo/route');
        }
        if (this.config.isochrone) {
            this._isoOp = this.useOp('geo/isochrone');
        }
    }

    override render() {
        const cls = `pm-wrap${this._interactive ? ' interactive' : ''}${this._ready ? ' ready' : ''}${this._mode === 'ruler' || this._mode === 'area' ? ' ruler' : ''}${this._mode === 'route' ? ' route-build' : ''}`;
        const panel = this.config.addressesPanel;
        return html`
            ${maplibreCssLink()}
            <div class=${cls} @click=${() => (this._menu = null)}>
                <div
                    class="map-canvas"
                    @mousedown=${(e: MouseEvent) => e.stopPropagation()}
                    @touchstart=${(e: TouchEvent) => e.stopPropagation()}
                    @wheel=${(e: WheelEvent) => e.stopPropagation()}
                    @contextmenu=${this._onContextMenu}
                ></div>
                ${this._renderSearch()}
                ${this._renderControls()}
                ${this._renderRouteChip()}
                ${this.config.draw ? this._renderZoneStats() : nothing}
                ${panel ? this._renderAddressesPanel(panel) : nothing}
                ${this.config.statusBar === true && this._ready ? this._renderStatusBar() : nothing}
                ${this._menu ? this._renderMenu() : nothing}
                ${!this._ready && this._error === null ? html`<div class="pm-overlay pm-loading"><span class="pm-spinner"></span>${this.t('map.loading')}</div>` : nothing}
                ${this._error !== null
                    ? html`<div class="pm-overlay pm-error">
                          <div class="pm-error-title">${this.t('map.error_title')}</div>
                          <button type="button" class="pm-retry" @click=${this._onRetry}>${this.t('map.retry')}</button>
                      </div>`
                    : nothing}
            </div>
        `;
    }

    private _renderSearch() {
        const enabled = this.config.controls?.search === true && this.config.search !== false && this._interactive;
        if (!enabled) return nothing;
        const cfg = typeof this.config.search === 'object' ? this.config.search : undefined;
        return html`
            <div class=${`pm-search${this.config.addressesPanel ? ' with-panel' : ''}`}>
                <input
                    class="pm-search-input"
                    type="text"
                    .value=${this._searchQuery}
                    placeholder=${cfg?.placeholder ?? this.t('map.search_placeholder')}
                    @input=${this._onSearchInput}
                    @focus=${() => (this._suggestOpen = this._suggestItems.length > 0)}
                    @keydown=${this._onSearchKeydown}
                />
                ${this._suggestBusy ? html`<span class="pm-search-busy"></span>` : nothing}
                ${this._suggestOpen && this._suggestItems.length > 0
                    ? html`<div class="pm-suggest">
                          ${this._suggestItems.map(
                              (hit, i) => html`
                                  <button
                                      type="button"
                                      class="pm-suggest-item"
                                      @mousedown=${(e: MouseEvent) => {
                                          e.preventDefault();
                                          this._pickSuggest(hit);
                                      }}
                                  >
                                      <span class="pm-suggest-name">${hit.display_name}</span>
                                      ${hit.city ? html`<span class="pm-suggest-sub">${hit.city}</span>` : nothing}
                                  </button>
                              `,
                          )}
                      </div>`
                    : nothing}
            </div>
        `;
    }

    private _renderControls() {
        const c = this.config.controls ?? {};
        const zoom = c.zoom !== false && this._ready && this._interactive;
        const layers = c.layers !== false && this._ready && this._layerNames.length > 0;
        const locate = c.locate === true && this._ready && this._interactive;
        const ruler = c.ruler === true && this._ready && this._interactive;
        const rulerArea = c.rulerArea === true && this._ready && this._interactive;
        const fit = c.fit === true && this._ready;
        const compass = c.compass === true && this._ready;
        const scheme = c.scheme === true && this._ready;
        const route = c.route === true && this._ready && this._interactive && this._routeCfg?.build === true;
        const fullscreen = c.fullscreen === true && this._ready;
        if (!zoom && !layers && !locate && !ruler && !rulerArea && !fit && !compass && !scheme && !route && !fullscreen) return nothing;
        const hidden = this._mapCtl?.value.hidden ?? {};
        return html`
            <div class="pm-controls">
                ${zoom
                    ? html`<div class="pm-ctrl pm-zoom">
                          <button type="button" title=${this.t('map.zoom_in')} @click=${() => this._map?.zoomIn()}>+</button>
                          <button type="button" title=${this.t('map.zoom_out')} @click=${() => this._map?.zoomOut()}>−</button>
                      </div>`
                    : nothing}
                ${locate
                    ? html`<button
                          type="button"
                          class="pm-ctrl pm-icon-btn"
                          data-action="locate"
                          title=${this.t('map.locate')}
                          @click=${this._onLocate}
                      >
                          ◎
                      </button>`
                    : nothing}
                ${ruler
                    ? html`<button
                          type="button"
                          class=${`pm-ctrl pm-icon-btn${this._mode === 'ruler' ? ' active' : ''}`}
                          data-action="ruler"
                          title=${this.t('map.ruler')}
                          @click=${() => this._toggleRuler('ruler')}
                      >
                          ⟋
                      </button>`
                    : nothing}
                ${rulerArea
                    ? html`<button
                          type="button"
                          class=${`pm-ctrl pm-icon-btn${this._mode === 'area' ? ' active' : ''}`}
                          data-action="ruler-area"
                          title=${this.t('map.ruler_area')}
                          @click=${() => this._toggleRuler('area')}
                      >
                          ⬠
                      </button>`
                    : nothing}
                ${fit
                    ? html`<button
                          type="button"
                          class="pm-ctrl pm-icon-btn"
                          data-action="fit"
                          title=${this.t('map.fit')}
                          @click=${this._fitContent}
                      >
                          ⤢
                      </button>`
                    : nothing}
                ${compass
                    ? html`<button
                          type="button"
                          class="pm-ctrl pm-icon-btn pm-compass"
                          data-action="compass"
                          title=${this.t('map.compass')}
                          @click=${this._resetNorth}
                      >
                          <span class="pm-compass-arrow" style="transform:rotate(${-this._bearing}deg)">▲</span>
                      </button>`
                    : nothing}
                ${scheme
                    ? html`<button
                          type="button"
                          class="pm-ctrl pm-icon-btn"
                          data-action="scheme"
                          title=${this.t(this._scheme === 'dark' ? 'map.scheme_light' : 'map.scheme_dark')}
                          @click=${this._toggleScheme}
                      >
                          ${this._scheme === 'dark' ? '☀' : '☾'}
                      </button>`
                    : nothing}
                ${route
                    ? html`<button
                          type="button"
                          class=${`pm-ctrl pm-icon-btn${this._mode === 'route' ? ' active' : ''}`}
                          data-action="route"
                          title=${this.t('map.route_build')}
                          @click=${this._toggleRouteBuild}
                      >
                          ⤳
                      </button>`
                    : nothing}
                ${fullscreen
                    ? html`<button
                          type="button"
                          class="pm-ctrl pm-icon-btn"
                          data-action="fullscreen"
                          title=${this.t('map.fullscreen')}
                          @click=${this._toggleFullscreen}
                      >
                          ${this._fullscreen ? '⤡' : '⛶'}
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

    private _renderStatusBar() {
        const zoom = this._map ? Math.round(this._map.getZoom() * 10) / 10 : 0;
        return html`<div class="pm-status"><span class="pm-status-coords">${this._cursorText}</span><span class="pm-status-zoom">z${zoom}</span></div>`;
    }

    private _renderMenu() {
        const m = this._menu!;
        return html`
            <div class="pm-menu" style="left:${m.x}px; top:${m.y}px" @click=${(e: Event) => e.stopPropagation()}>
                <button type="button" data-action="whats-here" @click=${() => this._menuWhatsHere(m.lngLat)}>${this.t('map.whats_here')}</button>
                <button type="button" data-action="copy-coords" @click=${() => this._menuCopyCoords(m.lngLat)}>${this.t('map.copy_coords')}</button>
            </div>
        `;
    }

    /** Чип маршрута: режимы car/foot/bike/scooter + «N км · M мин» + очистка. */
    private _renderRouteChip() {
        const cfg = this.config.route;
        if (!cfg || this._interactive === false) return nothing;
        const info = this._routeInfo;
        const pts = this._routePoints();
        const modes: PlatformMapRouteMode[] = ['car', 'foot', 'bike', 'scooter'];
        const modeIcons: Record<PlatformMapRouteMode, string> = { car: '🚗', foot: '🚶', bike: '🚲', scooter: '🛴' };
        const cur = cfg.mode ?? 'car';
        const showPanel = cfg.panel !== false;
        const building = this._mode === 'route';
        // Ничего не рисуем, пока нет ни линии, ни активного строительства.
        if (!info && !this._routeBusy && !building) return nothing;
        return html`
            <div class="pm-route-chip">
                ${showPanel
                    ? html`<span class="pm-route-modes">
                          ${modes.map(
                              (m) => html`<button
                                  type="button"
                                  class=${m === cur ? 'active' : ''}
                                  data-mode=${m}
                                  title=${this.t(`map.mode_${m}`)}
                                  @click=${() => this._setRouteMode(m)}
                              >
                                  ${modeIcons[m]}
                              </button>`,
                          )}
                      </span>`
                    : nothing}
                ${this._routeBusy
                    ? html`<span class="pm-route-busy"></span>`
                    : info
                      ? html`<span class="pm-route-text">${this._fmtDist(info.distanceM)} · ${this._fmtDuration(info.durationS)}</span>`
                      : building
                        ? html`<span class="pm-route-hint">${this.t(pts.length === 0 ? 'map.route_hint_a' : 'map.route_hint_b')}</span>`
                        : nothing}
                <button type="button" class="pm-route-clear" data-action="route-clear" title=${this.t('map.route_clear')} @click=${this.clearRoute}>×</button>
            </div>
        `;
    }

    private _fmtDuration(s: number): string {
        const m = Math.round(s / 60);
        if (m < 60) return `${m} ${this.t('map.min')}`;
        return `${Math.floor(m / 60)} ${this.t('map.hr')} ${m % 60} ${this.t('map.min')}`;
    }

    /** «111 м» / «1.2 км» — единицы по величине, не всегда км. */
    private _fmtDist(m: number): string {
        return m >= 1000
            ? `${(m / 1000).toFixed(1)} ${this.t('map.km')}`
            : `${Math.round(m)} ${this.t('map.m')}`;
    }

    /** «420 м²» / «0.85 км²» — то же для площади. */
    private _fmtAreaM2(m2: number): string {
        return m2 >= 1_000_000
            ? `${fmtArea(m2)} ${this.t('map.km2')}`
            : `${Math.round(m2)} ${this.t('map.m2')}`;
    }

    private _renderZoneStats() {
        const s = this._zoneStats;
        if (!s) return nothing;
        return html`
            <div class="pm-stats">
                <span>${this.t('zone_editor.area')} <b>${this._fmtAreaM2(s.areaM2)}</b></span>
                <span>${this.t('zone_editor.perimeter')} <b>${this._fmtDist(s.perimeterM)}</b></span>
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

    // ---- Search ----

    private _onSearchInput = (e: Event): void => {
        const q = (e.target as HTMLInputElement).value;
        this._searchQuery = q;
        if (this._suggestTimer !== null) window.clearTimeout(this._suggestTimer);
        if (q.trim().length < 2 || !this._suggestOp) {
            this._suggestItems = [];
            this._suggestOpen = false;
            this._suggestBusy = false;
            return;
        }
        this._suggestBusy = true;
        const op = this._suggestOp;
        this._suggestTimer = window.setTimeout(() => {
            const cfg = typeof this.config.search === 'object' ? this.config.search : undefined;
            const c = this._map?.getCenter();
            void op
                .run({
                    q: q.trim(),
                    limit: cfg?.limit ?? 7,
                    ...(c ? { lat: c.lat, lng: c.lng } : {}),
                })
                .then((res) => {
                if (this._suggestOp !== op) return;
                this._suggestBusy = false;
                this._suggestItems = res?.items ?? [];
                this._suggestOpen = this._suggestItems.length > 0;
            });
        }, 220);
    };

    private _onSearchKeydown = (e: KeyboardEvent): void => {
        if (e.key === 'Escape') {
            this._suggestOpen = false;
            (e.target as HTMLInputElement).blur();
        } else if (e.key === 'Enter' && this._suggestItems.length > 0) {
            e.preventDefault();
            this._pickSuggest(this._suggestItems[0]!);
        }
    };

    private _pickSuggest(hit: GeoAddressHit): void {
        const map = this._map;
        this._suggestOpen = false;
        this._searchQuery = hit.display_name;
        if (!map) return;
        const cfg = typeof this.config.search === 'object' ? this.config.search : undefined;
        const lngLat: LngLat = [hit.lng, hit.lat];
        map.easeTo({ center: lngLat, zoom: cfg?.flyZoom ?? 16, duration: 700 });
        if (cfg?.pin !== false) {
            this._searchPin = lngLat;
            this._syncSearchPin();
        }
        this.dispatchEvent(new CustomEvent('pm-search-select', { detail: { hit }, bubbles: true, composed: true }));
    }

    private _syncSearchPin(): void {
        const pin = this._searchPin;
        const fc: FeatureCollection = pin
            ? {
                  type: 'FeatureCollection',
                  features: [
                      { type: 'Feature', geometry: { type: 'Point', coordinates: pin }, properties: {} },
                  ],
              }
            : _EMPTY_FC;
        this._setSourceData('pm-search-pin', fc);
    }

    // ---- Ruler ----

    private _toggleRuler(mode: 'ruler' | 'area'): void {
        if (this._mode === mode) {
            this._exitRuler();
            return;
        }
        this._mode = mode;
        this._rulerPoints = [];
        this._hideHint();
        this._syncRuler();
    }

    private _exitRuler(): void {
        this._mode = 'select';
        this._emitRuler(true);
    }

    private _rulerAddPoint(lngLat: LngLat): void {
        this._rulerPoints = [...this._rulerPoints, lngLat];
        this._syncRuler();
        this._emitRuler(false);
    }

    private _rulerDistanceM(): number {
        let d = 0;
        for (let i = 1; i < this._rulerPoints.length; i++) {
            d += haversineM(this._rulerPoints[i - 1]!, this._rulerPoints[i]!);
        }
        return d;
    }

    private _rulerAreaM2(): number {
        return this._rulerPoints.length >= 3 ? ringAreaM2(this._rulerPoints) : 0;
    }

    private _syncRuler(): void {
        const pts = this._rulerPoints;
        const area = this._mode === 'area';
        const features: Feature[] = pts.map((p, i) => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: p },
            properties: {
                idx: i,
                label:
                    i === 0
                        ? ''
                        : area
                          ? ''
                          : this._fmtDist(haversineM(pts[i - 1]!, p)),
                total:
                    i === pts.length - 1 && pts.length > 1
                        ? area
                            ? pts.length >= 3
                                ? this._fmtAreaM2(this._rulerAreaM2())
                                : ''
                            : this._fmtDist(this._rulerDistanceM())
                        : '',
            },
        }));
        if (area) {
            if (pts.length >= 3) {
                features.push({
                    type: 'Feature',
                    geometry: { type: 'Polygon', coordinates: [[...pts, pts[0]!]] },
                    properties: { area: true },
                });
            }
            if (pts.length > 1) {
                features.push({
                    type: 'Feature',
                    geometry: { type: 'LineString', coordinates: [...pts, pts[0]!] },
                    properties: {},
                });
            }
        } else if (pts.length > 1) {
            features.push({
                type: 'Feature',
                geometry: { type: 'LineString', coordinates: pts },
                properties: {},
            });
        }
        this._setSourceData('pm-ruler', { type: 'FeatureCollection', features });
    }

    private _emitRuler(finished: boolean): void {
        this.dispatchEvent(
            new CustomEvent('pm-ruler-change', {
                detail: {
                    points: this._rulerPoints,
                    distanceM: this._rulerDistanceM(),
                    areaM2: this._rulerAreaM2(),
                    mode: this._mode,
                    finished,
                },
                bubbles: true,
                composed: true,
            }),
        );
    }

    /** Очистить линейку из хоста (или повторным кликом по контролу). */
    clearRuler(): void {
        this._rulerPoints = [];
        this._syncRuler();
    }

    // ---- Route / isochrone / scheme / compass ----

    private get _routeCfg(): Exclude<PlatformMapConfig['route'], false | undefined> | null {
        return this.config.route || null;
    }

    /** Очистка маршрута (линия, точки, чип); хост может звать напрямую. */
    clearRoute = (): void => {
        this._routeBuildPts = [];
        this._routeInfo = null;
        this._routeBusy = false;
        this._mode = 'select';
        this._setSourceData('pm-route', _EMPTY_FC);
        this._setSourceData('pm-route-pts', _EMPTY_FC);
        // config.route.points — базовый маршрут хоста; build-точки очищены →
        // refresh вернёт его на карту, а без точек просто прячет чип.
        this._refreshRoute();
    };

    /** Кнопка «маршрут»: вход/выход в режим построения кликами. */
    private _toggleRouteBuild = (): void => {
        if (this._mode === 'route') {
            this._mode = 'select';
            return;
        }
        this._mode = 'route';
        this._routeBuildPts = [];
        this._routeInfo = null;
        this._setSourceData('pm-route', _EMPTY_FC);
        this._setSourceData('pm-route-pts', _EMPTY_FC);
        this._hideHint();
    };

    private _setRouteMode(mode: PlatformMapRouteMode): void {
        const cfg = this._routeCfg;
        if (!cfg) return;
        this.config = { ...this.config, route: { ...cfg, mode } };
        this._refreshRoute();
    }

    /** Точки маршрута: build-состояние в режиме построения, иначе config. */
    private _routePoints(): LngLat[] {
        const cfg = this._routeCfg;
        if (!cfg) return [];
        return this._mode === 'route' ? this._routeBuildPts : (cfg.points ?? []);
    }

    /** Пересчёт маршрута: плечи параллельно, линия + точки + чип + fit. */
    private _refreshRoute(): void {
        const map = this._map;
        const op = this._routeOp;
        const cfg = this._routeCfg;
        if (!map || !cfg) return;
        const pts = this._routePoints();
        this._syncRoutePoints(pts);
        if (pts.length < 2 || !op) {
            this._routeInfo = null;
            this._routeBusy = false;
            this._setSourceData('pm-route', _EMPTY_FC);
            return;
        }
        const mode = cfg.mode ?? 'car';
        const seq = ++this._routeSeq;
        this._routeBusy = true;
        const legs = pts.slice(0, -1).map(
            (p, i): Promise<unknown> =>
                op.run({
                    from_point: { lng: p[0], lat: p[1] },
                    to_point: { lng: pts[i + 1]![0], lat: pts[i + 1]![1] },
                    mode,
                }),
        );
        void Promise.all(legs).then((results) => {
            if (seq !== this._routeSeq) return;
            this._routeBusy = false;
            const features: Feature[] = [];
            let distanceM = 0;
            let durationS = 0;
            for (const res of results) {
                const r = res as { distance_m?: number; duration_s?: number; geometry?: { type: string; coordinates: unknown } | null } | null;
                if (!r?.geometry) continue;
                distanceM += r.distance_m ?? 0;
                durationS += r.duration_s ?? 0;
                features.push({ type: 'Feature', geometry: r.geometry as Feature['geometry'], properties: {} });
            }
            this._setSourceData('pm-route', { type: 'FeatureCollection', features });
            if (features.length === 0) {
                this._routeInfo = null;
                return;
            }
            this._routeInfo = { distanceM, durationS };
            if (cfg.fit !== false) {
                this._fitFeatures(features);
            }
            this.dispatchEvent(
                new CustomEvent('pm-route', {
                    detail: { distanceM, durationS, mode, points: pts },
                    bubbles: true,
                    composed: true,
                }),
            );
        });
    }

    private _fitFeatures(features: Feature[]): void {
        const map = this._map;
        if (!map) return;
        let w = Infinity;
        let e = -Infinity;
        let s = Infinity;
        let n = -Infinity;
        const walk = (c: unknown): void => {
            if (!Array.isArray(c)) return;
            const [x, y] = c as [number, number];
            if (typeof x === 'number' && typeof y === 'number') {
                w = Math.min(w, x);
                e = Math.max(e, x);
                s = Math.min(s, y);
                n = Math.max(n, y);
                return;
            }
            for (const cc of c) walk(cc);
        };
        for (const f of features) walk((f.geometry as { coordinates?: unknown })?.coordinates);
        if (!Number.isFinite(w)) return;
        if (w === e && s === n) map.easeTo({ center: [w, s], duration: 500 });
        else map.fitBounds([[w, s], [e, n]], { padding: 80, duration: 600 });
    }

    /** A/B/via-точки маршрута с буквенными лейблами. */
    private _syncRoutePoints(pts: LngLat[]): void {
        const letters = 'ABCDEFGH';
        const features: Feature[] = pts.map((p, i) => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: p },
            properties: { label: letters[i] ?? `${i + 1}`, end: i === 0 || i === pts.length - 1 },
        }));
        this._setSourceData('pm-route-pts', { type: 'FeatureCollection', features });
    }

    /** Клик в build-режиме: добавить точку и пересчитать. */
    private _routeAddPoint(lngLat: LngLat): void {
        if (this._routeBuildPts.length >= 8) return;
        this._routeBuildPts = [...this._routeBuildPts, lngLat];
        this.dispatchEvent(new CustomEvent('pm-route-point', { detail: { lngLat, count: this._routeBuildPts.length }, bubbles: true, composed: true }));
        this._refreshRoute();
    }

    /** Контуры достижимости: N опов параллельно, бóльшие — под меньшими. */
    private _refreshIso(): void {
        const map = this._map;
        const op = this._isoOp;
        const cfg = this.config.isochrone;
        if (!map || !cfg || !op) return;
        const minutes = [...cfg.minutes].sort((a, b) => b - a);
        const mode = cfg.mode ?? 'car';
        const seq = ++this._isoSeq;
        void Promise.all(
            minutes.map((m) =>
                op.run({ center: { lng: cfg.center[0], lat: cfg.center[1] }, minutes: m, mode }),
            ),
        ).then((results) => {
            if (seq !== this._isoSeq) return;
            const colors = cfg.colors ?? ['#2563eb', '#7c3aed', '#db2777', '#ea580c'];
            const features: Feature[] = [];
            results.forEach((res, i) => {
                const r = res as { polygon?: { type: string; coordinates: unknown } | null } | null;
                if (!r?.polygon) return;
                features.push({
                    type: 'Feature',
                    geometry: r.polygon as Feature['geometry'],
                    properties: {
                        minutes: minutes[i],
                        color: colors[i % colors.length],
                        label: `${minutes[i]} ${this.t('map.min')}`,
                    },
                });
            });
            this._setSourceData('pm-iso', { type: 'FeatureCollection', features });
            const pts: Feature[] = [
                { type: 'Feature', geometry: { type: 'Point', coordinates: cfg.center }, properties: {} },
                ...features
                    .map((f) => {
                        const ring = ((f.geometry as { coordinates?: unknown })?.coordinates as LngLat[][] | undefined)?.[0];
                        const mid = ring?.[Math.floor((ring.length ?? 0) / 2)];
                        return mid
                            ? ({ type: 'Feature', geometry: { type: 'Point', coordinates: mid }, properties: f.properties } as Feature)
                            : null;
                    })
                    .filter((f): f is Feature => f !== null),
            ];
            this._setSourceData('pm-iso-pts', { type: 'FeatureCollection', features: pts });
            this.dispatchEvent(
                new CustomEvent('pm-isochrone', {
                    detail: { center: cfg.center, minutes, count: features.length },
                    bubbles: true,
                    composed: true,
                }),
            );
        });
    }

    private _resetNorth = (): void => {
        this._map?.easeTo({ bearing: 0, pitch: 0, duration: 400 });
    };

    /** Переключение светлой/тёмной схемы с переустановкой динамических слоёв. */
    private _toggleScheme = (): void => {
        const map = this._map;
        if (!map) return;
        this._scheme = this._scheme === 'dark' ? 'light' : 'dark';
        this._mapLayers.clear();
        map.once('style.load', () => {
            this._installSources(map);
            // TerraDraw-источники стираются setStyle — рестарт пересоздаёт их
            // и перерисовывает фичи из стора.
            if (this._zoneDraw) {
                this._zoneDraw.draw.stop();
                this._zoneDraw.draw.start();
            }
            this._syncOverlays();
            this._syncMarkers();
            this._syncSearchPin();
            this._syncRuler();
            this._syncRoutePoints(this._routePoints());
            this._refreshRoute();
            this._refreshIso();
            if (this._interactive && this._layersFetch) {
                this._applyConfigHiddenLayers();
                this._refresh();
            }
        });
        map.setStyle(basemapStyleUrl(this._scheme));
    };

    // ---- Fit / fullscreen / retry ----

    private _fitContent = (): void => {
        const map = this._map;
        if (!map) return;
        let w = Infinity;
        let e = -Infinity;
        let s = Infinity;
        let n = -Infinity;
        const extend = (c: unknown): void => {
            if (!Array.isArray(c)) return;
            const [x, y] = c as [number, number];
            if (typeof x === 'number' && typeof y === 'number') {
                w = Math.min(w, x);
                e = Math.max(e, x);
                s = Math.min(s, y);
                n = Math.max(n, y);
                return;
            }
            for (const cc of c) extend(cc);
        };
        const walk = (g: Geometry | null | undefined): void => {
            if (g) extend((g as { coordinates?: unknown }).coordinates);
        };
        for (const m of this.config.markers ?? []) extend(m.lngLat);
        for (const ov of this.config.overlays ?? []) {
            const d = ov.data;
            if (d.type === 'FeatureCollection') for (const f of d.features) walk(f.geometry);
            else walk(d.geometry);
        }
        const style = (map as unknown as { getStyle(): { sources?: Record<string, { data?: FeatureCollection }> } }).getStyle();
        for (const name of this._mapLayers) {
            const data = style?.sources?.[`pm-src-${name}`]?.data;
            if (data) for (const f of data.features ?? []) walk(f.geometry);
        }
        if (!Number.isFinite(w)) return;
        if (w === e && s === n) map.easeTo({ center: [w, s], zoom: 15, duration: 500 });
        else map.fitBounds([[w, s], [e, n]], { padding: 60, duration: 500 });
    };

    private _toggleFullscreen = (): void => {
        const wrap = this.renderRoot.querySelector('.pm-wrap');
        if (!(wrap instanceof HTMLElement)) return;
        if (document.fullscreenElement) {
            void document.exitFullscreen().catch(() => undefined);
        } else {
            void wrap.requestFullscreen?.().catch(() => undefined);
        }
    };

    private _onFullscreenChange = (): void => {
        this._fullscreen = document.fullscreenElement !== null;
        this._map?.resize();
    };

    private _onRetry = (): void => {
        this._error = null;
        void this._initMap();
    };

    // ---- Context menu ----

    private _onContextMenu = (e: MouseEvent): void => {
        const map = this._map;
        if (this.config.contextMenu !== true || !map) return;
        e.preventDefault();
        const el = e.currentTarget as HTMLElement;
        const rect = el.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const ll = (map as unknown as { unproject(p: [number, number]): { lng: number; lat: number } }).unproject([x, y]);
        this._menu = { x, y, lngLat: [ll.lng, ll.lat] };
    };

    private _menuWhatsHere(lngLat: LngLat): void {
        this._menu = null;
        const map = this._map;
        const maplibre = this._maplibre;
        if (!map || !maplibre || !this._nearestOp) return;
        void this._nearestOp.run({ lat: lngLat[1], lng: lngLat[0], limit: 1 }).then((res) => {
            const hit = res?.items?.[0];
            if (!hit) return;
            this._cardPopup?.remove();
            this._cardPopup = new maplibre.Popup({ closeButton: true, className: 'pm-card-popup', maxWidth: '340px' })
                .setLngLat(lngLat)
                .setHTML(
                    renderFeatureCard(
                        {
                            layer: 'addresses',
                            properties: {
                                display_name: hit.display_name,
                                city: hit.city,
                                street: hit.street,
                                housenumber: hit.housenumber,
                                __coords: `${lngLat[1].toFixed(5)}, ${lngLat[0].toFixed(5)}`,
                            },
                        },
                        (k) => this.t(k),
                        this._layerColor('addresses'),
                    ),
                )
                .addTo(map) as unknown as { remove(): void };
        });
    }

    private _menuCopyCoords(lngLat: LngLat): void {
        this._menu = null;
        const text = `${lngLat[1].toFixed(6)}, ${lngLat[0].toFixed(6)}`;
        void navigator.clipboard?.writeText(text).catch(() => undefined);
        this.dispatchEvent(new CustomEvent('pm-coords-copy', { detail: { lngLat, text }, bubbles: true, composed: true }));
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
            if (this._routeCfg) this._refreshRoute();
            if (this.config.isochrone) this._refreshIso();
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
        this._scheme = this.config.scheme ?? 'light';
        const interactive = this._interactive;
        const map = await createBasemap(el, {
            center: this.config.center ?? DEFAULT_CENTER,
            zoom: this.config.zoom ?? DEFAULT_ZOOM,
            interactive,
            scheme: this._scheme,
            rotate: this.config.rotate === true,
        });
        if (this.config.minZoom !== undefined) map.setMinZoom(this.config.minZoom);
        if (this.config.maxZoom !== undefined) map.setMaxZoom(this.config.maxZoom);
        if (this.config.padding !== undefined) {
            const p = this.config.padding;
            map.setPadding({ top: p, right: p, bottom: p, left: p });
        }
        map.touchZoomRotate?.enableRotation();
        this._map = map;
        if (this.config.controls?.scale === true) {
            map.addControl(new maplibre.ScaleControl({ maxWidth: 100, unit: 'metric' }), 'bottom-left');
        }
        if (!map.isStyleLoaded()) {
            // Источники и слои — только после load стиля; error отдаём
            // наружу и завершаем init, иначе addSource бросает.
            // 'error' отдельных тайлов/глифов НЕ фатален (404 за пределами
            // coverage) — ждём 'load'; без него таймаут или повторяющиеся
            // ошибки при незагруженном стиле → fail.
            const ok = await new Promise<boolean>((resolve) => {
                let settled = false;
                const done = (v: boolean): void => {
                    if (!settled) {
                        settled = true;
                        resolve(v);
                    }
                };
                map.once('load', () => done(true));
                map.on('error', () => {
                    // Шум тайла при грузящемся стиле: даём 'load' ещё 3с;
                    // мёртвый style.json — fail быстрее общего таймаута.
                    if (!settled) {
                        setTimeout(() => done(map.isStyleLoaded() === true), 3000);
                    }
                });
                setTimeout(() => done(map.isStyleLoaded() === true), 15_000);
            });
            if (!ok || this._map !== map) {
                map.remove();
                if (this._map === map) this._map = null;
                if (!ok) {
                    this._error = 'style';
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
        if (this._routeCfg) {
            this._refreshRoute();
        }
        if (this.config.isochrone) {
            this._refreshIso();
        }
        if (this.config.controls?.compass === true || this.config.rotate === true) {
            map.on('rotate', () => {
                this._bearing = map.getBearing();
            });
        }
        if (this.config.moveEvent === true) {
            map.on('moveend', () => {
                const c = map.getCenter();
                const b = map.getBounds();
                this.dispatchEvent(
                    new CustomEvent('pm-move', {
                        detail: {
                            center: [c.lng, c.lat] as LngLat,
                            zoom: map.getZoom(),
                            bearing: map.getBearing(),
                            bounds: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()],
                        },
                        bubbles: true,
                        composed: true,
                    }),
                );
            });
        }
        if (this.config.statusBar === true) {
            map.on('mousemove', (e: { lngLat: { lng: number; lat: number } }) => {
                this._cursorText = `${e.lngLat.lat.toFixed(5)}, ${e.lngLat.lng.toFixed(5)}`;
            });
            map.on('zoom', () => this.requestUpdate());
        }
        document.addEventListener('fullscreenchange', this._onFullscreenChange);
        this.dispatchEvent(new CustomEvent('pm-ready', { detail: { map }, bubbles: true, composed: true }));
    }

    private _installSources(map: PlatformMap): void {
        const cluster = this.config.markersCluster === true;
        map.addSource('pm-markers', {
            type: 'geojson',
            data: _EMPTY_FC,
            ...(cluster ? { cluster: true, clusterMaxZoom: 15, clusterRadius: 48 } : {}),
        } as never);
        if (cluster) {
            map.addLayer({
                id: 'pm-cluster-circle',
                type: 'circle',
                source: 'pm-markers',
                filter: ['has', 'point_count'],
                paint: {
                    'circle-color': '#2563eb',
                    'circle-radius': ['step', ['get', 'point_count'], 16, 10, 20, 50, 26],
                    'circle-stroke-width': 3,
                    'circle-stroke-color': '#ffffff',
                },
            } as never);
            map.addLayer({
                id: 'pm-cluster-count',
                type: 'symbol',
                source: 'pm-markers',
                filter: ['has', 'point_count'],
                layout: {
                    'text-field': ['get', 'point_count_abbreviated'],
                    'text-size': 12,
                },
                paint: { 'text-color': '#ffffff' },
            } as never);
        }
        map.addLayer({
            id: 'pm-markers-circle',
            type: 'circle',
            source: 'pm-markers',
            ...(cluster ? { filter: ['!', ['has', 'point_count']] } : {}),
            paint: {
                'circle-radius': ['coalesce', ['get', 'size'], 9],
                'circle-color': ['coalesce', ['get', 'color'], MARKER_COLOR],
                'circle-stroke-width': 3,
                'circle-stroke-color': '#ffffff',
            },
        } as never);
        map.addSource('pm-search-pin', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'pm-search-pin-circle',
            type: 'circle',
            source: 'pm-search-pin',
            paint: {
                'circle-radius': 10,
                'circle-color': '#155dfc',
                'circle-stroke-width': 4,
                'circle-stroke-color': '#ffffff',
            },
        } as never);
        map.addSource('pm-route', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'pm-route-casing',
            type: 'line',
            source: 'pm-route',
            paint: {
                'line-color': '#ffffff',
                'line-width': 8,
                'line-opacity': 0.85,
            },
            layout: { 'line-cap': 'round', 'line-join': 'round' },
        } as never);
        map.addLayer({
            id: 'pm-route-line',
            type: 'line',
            source: 'pm-route',
            paint: {
                'line-color': this._routeCfg?.color ?? '#155dfc',
                'line-width': 4.5,
            },
            layout: { 'line-cap': 'round', 'line-join': 'round' },
        } as never);
        map.addSource('pm-route-pts', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'pm-route-pt-circle',
            type: 'circle',
            source: 'pm-route-pts',
            paint: {
                'circle-radius': ['case', ['==', ['get', 'end'], true], 10, 7],
                'circle-color': ['case', ['==', ['get', 'idx'], 0], '#16a34a', '#155dfc'],
                'circle-stroke-width': 3,
                'circle-stroke-color': '#ffffff',
            },
        } as never);
        map.addLayer({
            id: 'pm-route-pt-label',
            type: 'symbol',
            source: 'pm-route-pts',
            layout: {
                'text-field': ['get', 'label'],
                'text-size': 11,
                'text-font': ['Noto Sans Regular'],
            },
            paint: { 'text-color': '#ffffff' },
        } as never);
        map.addSource('pm-iso', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'pm-iso-fill',
            type: 'fill',
            source: 'pm-iso',
            paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.16 },
        } as never);
        map.addLayer({
            id: 'pm-iso-line',
            type: 'line',
            source: 'pm-iso',
            paint: { 'line-color': ['get', 'color'], 'line-width': 2 },
        } as never);
        map.addSource('pm-iso-pts', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'pm-iso-label',
            type: 'symbol',
            source: 'pm-iso-pts',
            filter: ['has', 'minutes'],
            layout: {
                'text-field': ['get', 'label'],
                'text-size': 12,
                'text-font': ['Noto Sans Regular'],
            },
            paint: {
                'text-color': ['get', 'color'],
                'text-halo-color': '#ffffff',
                'text-halo-width': 2.5,
            },
        } as never);
        map.addLayer({
            id: 'pm-iso-center',
            type: 'circle',
            source: 'pm-iso-pts',
            filter: ['!', ['has', 'minutes']],
            paint: {
                'circle-radius': 7,
                'circle-color': '#0f172a',
                'circle-stroke-width': 3,
                'circle-stroke-color': '#ffffff',
            },
        } as never);
        map.addSource('pm-ruler', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'pm-ruler-fill',
            type: 'fill',
            source: 'pm-ruler',
            filter: ['==', ['geometry-type'], 'Polygon'],
            paint: { 'fill-color': '#7c3aed', 'fill-opacity': 0.14 },
        } as never);
        map.addLayer({
            id: 'pm-ruler-line',
            type: 'line',
            source: 'pm-ruler',
            filter: ['==', ['geometry-type'], 'LineString'],
            paint: { 'line-color': '#7c3aed', 'line-width': 3, 'line-dasharray': [2, 1.4] },
        } as never);
        map.addLayer({
            id: 'pm-ruler-vertex',
            type: 'circle',
            source: 'pm-ruler',
            filter: ['==', ['geometry-type'], 'Point'],
            paint: {
                'circle-radius': 6,
                'circle-color': '#ffffff',
                'circle-stroke-width': 3,
                'circle-stroke-color': '#7c3aed',
            },
        } as never);
        map.addLayer({
            id: 'pm-ruler-label',
            type: 'symbol',
            source: 'pm-ruler',
            filter: ['==', ['geometry-type'], 'Point'],
            layout: {
                'text-field': ['coalesce', ['get', 'total'], ['get', 'label']],
                'text-size': 12,
                'text-offset': [0, -1.4],
                'text-anchor': 'bottom',
                'text-font': ['Noto Sans Regular'],
            },
            paint: {
                'text-color': '#4c1d95',
                'text-halo-color': '#ffffff',
                'text-halo-width': 2,
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
            if (this._mode === 'ruler' || this._mode === 'area') {
                this._rulerAddPoint([e.lngLat.lng, e.lngLat.lat]);
                return;
            }
            if (this._mode === 'route') {
                this._routeAddPoint([e.lngLat.lng, e.lngLat.lat]);
                return;
            }
            if (this.config.markersCluster === true && this._clickCluster(map, e.point)) {
                return;
            }
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
                if (this._mode === 'ruler' || this._mode === 'area' || this._mode === 'route') {
                    map.getCanvas().style.cursor = 'crosshair';
                    this._hideHint();
                    return;
                }
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

    /** Клик по кластеру маркеров — expand zoom; true, если кластер был. */
    private _clickCluster(map: PlatformMap, point: { x: number; y: number }): boolean {
        if (!map.getLayer('pm-cluster-circle')) return false;
        type QF = (p: [number, number], o?: { layers?: string[] }) => { properties?: Record<string, unknown> | null; geometry?: { coordinates?: unknown } }[];
        const query = (map as unknown as { queryRenderedFeatures: QF }).queryRenderedFeatures.bind(map);
        const hits = query([point.x, point.y], { layers: ['pm-cluster-circle'] });
        const hit = hits[0];
        if (!hit) return false;
        const coords = hit.geometry?.coordinates as LngLat | undefined;
        const src = map.getSource('pm-markers') as unknown as {
            getClusterExpansionZoom?(id: number): Promise<number>;
        };
        const clusterId = Number(hit.properties?.['cluster_id'] ?? -1);
        if (src?.getClusterExpansionZoom && clusterId >= 0 && coords) {
            void src
                .getClusterExpansionZoom(clusterId)
                .then((zoom) => {
                    map.easeTo({ center: coords, zoom: zoom + 0.2, duration: 450 });
                })
                .catch(() => {
                    map.easeTo({ center: coords, zoom: map.getZoom() + 2, duration: 450 });
                });
        }
        return true;
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
        const maplibre = this._maplibre;
        if (!map) return;
        const src = map.getSource('pm-markers') as { setData(d: FeatureCollection): void } | undefined;
        const markers = this.config.markers ?? [];
        // Draggable-маркеры — DOM-элементы с родным drag-жестом MapLibre;
        // остальные рендерятся через geojson-слой (кластеризация работает на нём).
        for (const dm of this._domMarkers) dm.remove();
        this._domMarkers = [];
        const draggable = markers.filter((m) => m.draggable === true);
        if (maplibre) {
            for (const m of draggable) {
                const inst = new maplibre.Marker({ color: m.color ?? MARKER_COLOR, draggable: true })
                    .setLngLat(m.lngLat)
                    .addTo(map) as unknown as {
                    remove(): void;
                    on(evt: string, cb: () => void): void;
                    getLngLat(): { lng: number; lat: number };
                };
                inst.on('dragend', () => {
                    const ll = inst.getLngLat();
                    this.dispatchEvent(
                        new CustomEvent('pm-marker-drag', {
                            detail: { key: m.key ?? '', lngLat: [ll.lng, ll.lat] as LngLat },
                            bubbles: true,
                            composed: true,
                        }),
                    );
                });
                this._domMarkers.push(inst);
            }
        }
        const features = markers
            .filter((m) => m.draggable !== true)
            .map((m) => ({
                type: 'Feature' as const,
                geometry: { type: 'Point' as const, coordinates: m.lngLat },
                properties: { key: m.key ?? '', color: m.color ?? MARKER_COLOR, size: m.size ?? 9, title: m.title ?? '' },
            }));
        src?.setData({ type: 'FeatureCollection', features });
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
        if (this._suggestTimer !== null) window.clearTimeout(this._suggestTimer);
        document.removeEventListener('fullscreenchange', this._onFullscreenChange);
        this._zoneDraw?.draw.stop();
        this._zoneDraw = null;
        for (const dm of this._domMarkers) dm.remove();
        this._domMarkers = [];
        this._map?.remove();
        this._map = null;
        this._el = null;
        this._hintPopup = null;
        this._cardPopup = null;
        this._locateMarker = null;
        this._rulerPoints = [];
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
            background: color-mix(in srgb, var(--color-surface, #fff) 88%, transparent);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid var(--color-border, #e2e8f0);
            border-radius: 12px;
            box-shadow: 0 2px 12px rgba(15, 23, 42, 0.14);
            overflow: hidden;
        }
        .pm-zoom {
            display: flex;
            flex-direction: column;
        }
        .pm-zoom button {
            width: 38px;
            height: 36px;
            border: 0;
            background: transparent;
            font-size: 18px;
            cursor: pointer;
            color: var(--color-text, #0f172a);
            transition: background 0.15s ease;
        }
        .pm-zoom button:hover {
            background: var(--color-surface-muted, #f1f5f9);
        }
        .pm-zoom button + button {
            border-top: 1px solid var(--color-border, #e2e8f0);
        }
        .pm-icon-btn {
            width: 38px;
            height: 38px;
            font-size: 16px;
            cursor: pointer;
            color: var(--color-text, #0f172a);
            transition: background 0.15s ease, color 0.15s ease;
        }
        .pm-icon-btn:hover {
            background: var(--color-surface-muted, #f1f5f9);
        }
        .pm-icon-btn.active {
            background: var(--color-primary-soft, #dbeafe);
            color: var(--color-primary, #2563eb);
        }
        .pm-wrap.ruler .map-canvas {
            cursor: crosshair;
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
        .pm-search {
            position: absolute;
            top: 12px;
            left: 12px;
            width: min(320px, calc(100% - 140px));
            z-index: 6;
        }
        .pm-search.with-panel {
            left: 324px;
            width: min(320px, calc(100% - 464px));
        }
        .pm-search-input {
            width: 100%;
            box-sizing: border-box;
            padding: 10px 34px 10px 14px;
            border: 1px solid var(--color-border, #e2e8f0);
            border-radius: 12px;
            background: color-mix(in srgb, var(--color-surface, #fff) 92%, transparent);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 2px 12px rgba(15, 23, 42, 0.14);
            font-size: 13px;
            color: var(--color-text, #0f172a);
            outline: none;
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        .pm-search-input:focus {
            border-color: var(--color-primary, #2563eb);
            box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary, #2563eb) 18%, transparent), 0 2px 12px rgba(15, 23, 42, 0.14);
        }
        .pm-search-busy {
            position: absolute;
            right: 12px;
            top: 50%;
            width: 14px;
            height: 14px;
            margin-top: -7px;
            border: 2px solid var(--color-border, #e2e8f0);
            border-top-color: var(--color-primary, #2563eb);
            border-radius: 50%;
            animation: pm-spin 0.7s linear infinite;
        }
        .pm-suggest {
            margin-top: 6px;
            border: 1px solid var(--color-border, #e2e8f0);
            border-radius: 12px;
            background: color-mix(in srgb, var(--color-surface, #fff) 96%, transparent);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 8px 28px rgba(15, 23, 42, 0.18);
            overflow: hidden;
        }
        .pm-suggest-item {
            display: flex;
            flex-direction: column;
            gap: 2px;
            width: 100%;
            padding: 9px 14px;
            border: 0;
            background: transparent;
            text-align: left;
            cursor: pointer;
            font-size: 13px;
            color: var(--color-text, #0f172a);
            transition: background 0.12s ease;
        }
        .pm-suggest-item:hover,
        .pm-suggest-item:focus-visible {
            background: var(--color-surface-muted, #f1f5f9);
        }
        .pm-suggest-item + .pm-suggest-item {
            border-top: 1px solid color-mix(in srgb, var(--color-border, #e2e8f0) 60%, transparent);
        }
        .pm-suggest-name {
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .pm-suggest-sub {
            font-size: 11px;
            color: var(--color-text-muted, #64748b);
        }
        .pm-status {
            position: absolute;
            right: 12px;
            bottom: 12px;
            display: flex;
            gap: 10px;
            align-items: center;
            padding: 5px 10px;
            border-radius: 8px;
            background: color-mix(in srgb, var(--color-surface, #fff) 85%, transparent);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border: 1px solid var(--color-border, #e2e8f0);
            font-size: 11px;
            font-variant-numeric: tabular-nums;
            color: var(--color-text-muted, #64748b);
            z-index: 5;
        }
        .pm-status-zoom {
            color: var(--color-text, #0f172a);
            font-weight: 600;
        }
        .pm-menu {
            position: absolute;
            min-width: 180px;
            border-radius: 12px;
            border: 1px solid var(--color-border, #e2e8f0);
            background: color-mix(in srgb, var(--color-surface, #fff) 96%, transparent);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 8px 28px rgba(15, 23, 42, 0.2);
            overflow: hidden;
            z-index: 20;
        }
        .pm-menu button {
            display: block;
            width: 100%;
            padding: 9px 14px;
            border: 0;
            background: transparent;
            text-align: left;
            font-size: 13px;
            color: var(--color-text, #0f172a);
            cursor: pointer;
            transition: background 0.12s ease;
        }
        .pm-menu button:hover {
            background: var(--color-surface-muted, #f1f5f9);
        }
        .pm-menu button + button {
            border-top: 1px solid color-mix(in srgb, var(--color-border, #e2e8f0) 60%, transparent);
        }
        .pm-route-chip {
            position: absolute;
            left: 50%;
            bottom: 14px;
            transform: translateX(-50%);
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 7px 8px 7px 12px;
            border-radius: 14px;
            border: 1px solid var(--color-border, #e2e8f0);
            background: color-mix(in srgb, var(--color-surface, #fff) 90%, transparent);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            box-shadow: 0 4px 18px rgba(15, 23, 42, 0.16);
            font-size: 13px;
            color: var(--color-text, #0f172a);
            z-index: 15;
            white-space: nowrap;
        }
        .pm-route-modes {
            display: flex;
            border-radius: 9px;
            background: var(--color-surface-muted, #f1f5f9);
            overflow: hidden;
        }
        .pm-route-modes button {
            border: 0;
            background: transparent;
            padding: 4px 9px;
            font-size: 14px;
            cursor: pointer;
            opacity: 0.55;
            transition:
                background 0.12s ease,
                opacity 0.12s ease;
        }
        .pm-route-modes button:hover {
            opacity: 0.9;
        }
        .pm-route-modes button.active {
            background: var(--color-primary, #155dfc);
            opacity: 1;
        }
        .pm-route-text {
            font-weight: 600;
        }
        .pm-route-hint {
            color: var(--color-text-muted, #64748b);
        }
        .pm-route-busy {
            width: 16px;
            height: 16px;
            border: 2px solid var(--color-border, #e2e8f0);
            border-top-color: var(--color-primary, #155dfc);
            border-radius: 50%;
            animation: pm-spin 0.8s linear infinite;
        }
        .pm-route-clear {
            border: 0;
            background: transparent;
            font-size: 17px;
            line-height: 1;
            color: var(--color-text-muted, #64748b);
            cursor: pointer;
            padding: 3px 6px;
            border-radius: 7px;
        }
        .pm-route-clear:hover {
            background: var(--color-surface-muted, #f1f5f9);
            color: var(--color-text, #0f172a);
        }
        .pm-compass-arrow {
            display: inline-block;
            font-size: 13px;
            color: var(--color-danger, #dc2626);
            transition: transform 0.15s ease;
        }
        .pm-overlay {
            position: absolute;
            inset: 0;
            display: flex;
            flex-direction: column;
            gap: 12px;
            align-items: center;
            justify-content: center;
            background: color-mix(in srgb, var(--color-surface, #fff) 72%, transparent);
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
            font-size: 13px;
            color: var(--color-text-muted, #64748b);
            z-index: 8;
        }
        .pm-spinner {
            width: 22px;
            height: 22px;
            border: 3px solid var(--color-border, #e2e8f0);
            border-top-color: var(--color-primary, #2563eb);
            border-radius: 50%;
            animation: pm-spin 0.8s linear infinite;
        }
        .pm-error-title {
            font-size: 14px;
            font-weight: 600;
            color: var(--color-text, #0f172a);
        }
        .pm-retry {
            padding: 8px 18px;
            border: 0;
            border-radius: 10px;
            background: var(--color-primary, #2563eb);
            color: #fff;
            font-size: 13px;
            cursor: pointer;
        }
        @keyframes pm-spin {
            to {
                transform: rotate(360deg);
            }
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

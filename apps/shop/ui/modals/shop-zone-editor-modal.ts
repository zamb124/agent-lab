/**
 * ShopZoneEditorModal — полноэкранный редактор зоны доставки (MapLibre + terra-draw).
 *
 * Открывается из <shop-zone-map> (превью в настройках) через
 * openModal('shop.zone_editor', { zone, address, shopId, onApply }).
 * Полигон редактируется профессионально: вершины и midpoints тянутся,
 * зона целиком draggable, самопересечения запрещены
 * (ValidateNotSelfIntersecting на draw и select) и дополнительно
 * проверяются перед «Применить».
 *
 * Результат не сохраняется сам — onApply(zone) отдаёт GeoJSON Polygon в
 * родителя, сохранение идёт общим savebar настроек (shop/shop_update).
 * Пустой {} — «зоны нет, доставляем без ограничений».
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-zone-address-panel.js';
import type { GeoAddressItem } from '@platform/lib/components/platform-zone-address-panel.js';
import { loadMapLibre, maplibreCssLink } from '@platform/lib/map/maplibre.js';
import type { MapLibreModule } from '@platform/lib/map/maplibre.js';
import { createBasemap } from '@platform/lib/map/basemap.js';
import type { PlatformMap } from '@platform/lib/map/basemap.js';

import type { Feature, FeatureCollection, Position } from 'geojson';

type TerraDrawInstance = import('terra-draw').TerraDraw;
type MapLibreMarker = import('maplibre-gl').Marker;
type MapLibrePopup = import('maplibre-gl').Popup;
type LngLatRing = [number, number][];
type StoreFeature = Parameters<TerraDrawInstance['addFeatures']>[0][number];

const ACCENT = '#f2542d';
const ZONE_MAX_POINTS = 256;
const R_EARTH = 6_371_008.8;
const _EMPTY_FC: FeatureCollection = { type: 'FeatureCollection', features: [] };

function _ringAreaM2(ring: LngLatRing): number {
    // Сферическая площадь полигона (формула Льюилье/Чемберлена) — достаточна
    // для метрик директору; на зонах городского масштаба погрешность <0.5%.
    let sum = 0;
    for (let i = 0; i < ring.length; i++) {
        const [lng1, lat1] = ring[i]!;
        const [lng2, lat2] = ring[(i + 1) % ring.length]!;
        sum += (lng2 - lng1) * (Math.PI / 180) * (2 + Math.sin(lat1 * Math.PI / 180) + Math.sin(lat2 * Math.PI / 180));
    }
    return Math.abs(sum * R_EARTH * R_EARTH / 2);
}

function _haversineM(a: [number, number], b: [number, number]): number {
    const dLat = ((b[1] - a[1]) * Math.PI) / 180;
    const dLng = ((b[0] - a[0]) * Math.PI) / 180;
    const s =
        Math.sin(dLat / 2) ** 2 +
        Math.cos((a[1] * Math.PI) / 180) * Math.cos((b[1] * Math.PI) / 180) * Math.sin(dLng / 2) ** 2;
    return 2 * R_EARTH * Math.asin(Math.min(1, Math.sqrt(s)));
}

function _fmtKm(m: number): string {
    return m >= 1000 ? `${(m / 1000).toFixed(1)}` : `${Math.round(m)}`;
}

function _fmtArea(m2: number): string {
    return m2 >= 1_000_000 ? `${(m2 / 1_000_000).toFixed(2)}` : `${(m2 / 1_000_000).toFixed(3)}`;
}

export class ShopZoneEditorModal extends PlatformModal {
    static modalKind = 'shop.zone_editor';
    static i18nNamespace = 'shop';

    declare zone: Record<string, unknown> | null;
    declare address: string;
    declare shopId: string;
    declare onApply: ((zone: Record<string, unknown>) => void) | null;

    declare _drawing: boolean;
    declare _locating: boolean;
    declare _hint: string;
    declare _mapError: boolean;
    declare _areaM2: number;
    declare _perimM: number;
    declare _points: number;
    declare _selfIntersect: boolean;
    declare _zoneGeoJson: Record<string, unknown> | null;

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        zone: { attribute: false },
        address: { attribute: false },
        shopId: { attribute: false },
        onApply: { attribute: false },
        _drawing: { state: true },
        _locating: { state: true },
        _hint: { state: true },
        _mapError: { state: true },
        _areaM2: { state: true },
        _perimM: { state: true },
        _points: { state: true },
        _selfIntersect: { state: true },
        _zoneGeoJson: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .zwrap {
                position: relative;
                display: flex;
                height: 100%;
                min-height: 420px;
                border-radius: var(--radius-lg, 12px);
                overflow: hidden;
                border: 1px solid color-mix(in srgb, var(--text-primary) 12%, transparent);
                background: var(--bg-secondary, #f2f0ec);
            }
            .zbody { position: relative; flex: 1; min-width: 0; }
            .zmap { position: absolute; inset: 0; }
            .zmap.drawing { cursor: crosshair; }
            platform-zone-address-panel {
                flex: none;
                width: clamp(300px, 26vw, 380px);
                border-left: 1px solid color-mix(in srgb, var(--text-primary) 12%, transparent);
            }

            .ztools {
                position: absolute;
                top: var(--space-3);
                left: var(--space-3);
                z-index: 500;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-2);
                border-radius: var(--radius-lg, 12px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 92%, transparent);
                backdrop-filter: blur(14px);
                box-shadow: 0 8px 28px color-mix(in srgb, var(--text-primary) 16%, transparent);
            }
            .ztool {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-m, 10px);
                background: transparent;
                color: var(--text-primary);
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                white-space: nowrap;
                text-align: left;
            }
            .ztool:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
            .ztool.on { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent); }
            .ztool:disabled { opacity: 0.45; cursor: default; background: transparent; }
            .ztool.danger:hover { background: color-mix(in srgb, var(--danger, #d92d20) 10%, transparent); color: var(--danger, #d92d20); }

            .zstats {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                z-index: 500;
                display: flex;
                gap: var(--space-4);
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-full, 999px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 92%, transparent);
                backdrop-filter: blur(14px);
                box-shadow: 0 8px 28px color-mix(in srgb, var(--text-primary) 16%, transparent);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                white-space: nowrap;
            }
            .zstats b { color: var(--text-primary); font-weight: var(--font-semibold); }

            .zhint {
                position: absolute;
                left: 50%;
                bottom: var(--space-4);
                transform: translateX(-50%);
                z-index: 500;
                max-width: min(560px, calc(100% - 32px));
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-full, 999px);
                background: color-mix(in srgb, var(--bg-primary, #fff) 94%, transparent);
                backdrop-filter: blur(14px);
                box-shadow: 0 8px 28px color-mix(in srgb, var(--text-primary) 16%, transparent);
                font-size: var(--text-sm);
                color: var(--text-primary);
                text-align: center;
            }
            .zhint.warn { color: var(--danger, #d92d20); }

            .zerror {
                position: absolute;
                inset: 0;
                z-index: 600;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: var(--space-3);
                background: var(--bg-secondary, #f2f0ec);
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }

            @media (max-width: 720px) {
                .zstats { display: none; }
                .ztool span { display: none; }
                platform-zone-address-panel { display: none; }
            }
        `,
    ];

    private _maplibre: MapLibreModule | null = null;
    private _map: PlatformMap | null = null;
    private _draw: TerraDrawInstance | null = null;
    private _marker: MapLibreMarker | null = null;
    private _popup: MapLibrePopup | null = null;
    private _addressFeatures = new Map<number, Feature>();
    private _ro: ResizeObserver | null = null;
    private _geocodeOp: OpController;
    private _initStarted = false;
    private _zoneImported = false;

    constructor() {
        super();
        this.size = 'full';
        this.zone = null;
        this.address = '';
        this.shopId = '';
        this.onApply = null;
        this._drawing = false;
        this._locating = false;
        this._hint = '';
        this._mapError = false;
        this._areaM2 = 0;
        this._perimM = 0;
        this._points = 0;
        this._selfIntersect = false;
        this._zoneGeoJson = null;
        this._geocodeOp = this.useOp('shop/shop_geocode');
    }

    protected override updated(changed: Map<string, unknown>): void {
        super.updated(changed);
        if (this.open && !this._map) this._scheduleInit();
    }

    override disconnectedCallback(): void {
        // Портал модалки переносит элемент в document.body — disconnect при
        // переносе не должен убивать карту, только реальное снятие с DOM.
        queueMicrotask(() => {
            if (this.isConnected) return;
            this._teardownMap();
        });
        super.disconnectedCallback();
    }

    private _teardownMap(): void {
        this._ro?.disconnect();
        this._ro = null;
        this._draw?.stop();
        this._draw = null;
        this._popup?.remove();
        this._popup = null;
        this._marker?.remove();
        this._marker = null;
        this._map?.remove();
        this._map = null;
        this._addressFeatures.clear();
        this._initStarted = false;
        this._zoneImported = false;
    }

    private _scheduleInit(): void {
        if (this._initStarted) return;
        requestAnimationFrame(() => {
            if (this.open && !this._map) void this._initMap();
        });
    }

    private _mapEl(): HTMLElement | null {
        return this.renderRoot.querySelector<HTMLElement>('.zmap');
    }

    private async _initMap(): Promise<void> {
        const el = this._mapEl();
        if (!el || this._map || this._initStarted) return;
        // Контейнер должен иметь реальный размер — без него карта и
        // terra-draw отрисуются в неверном вьюпорте.
        if (!el.offsetWidth || !el.offsetHeight) {
            requestAnimationFrame(() => this._scheduleInit());
            return;
        }
        this._initStarted = true;
        const [maplibre, terraDraw, adapterMod] = await Promise.all([
            loadMapLibre(),
            import('terra-draw'),
            import('terra-draw-maplibre-gl-adapter'),
        ]);
        this._maplibre = maplibre;
        if (!this.isConnected || !this.open) {
            this._initStarted = false;
            return;
        }
        const map = (this._map = await createBasemap(el, {
            center: [37.6184, 55.7512],
            zoom: 11,
        }));
        map.on('error', () => {
            this._mapError = true;
        });
        this._ro = new ResizeObserver(() => {
            if (!this._map || !el.offsetWidth || !el.offsetHeight) return;
            this._map.resize();
        });
        this._ro.observe(el);
        map.once('load', () => {
            this._initDraw(terraDraw, adapterMod, map);
            this._initAddressLayers(map);
            this._renderZone();
            this._updateHint();
        });
    }

    private _initDraw(
        td: typeof import('terra-draw'),
        adapterMod: typeof import('terra-draw-maplibre-gl-adapter'),
        map: PlatformMap,
    ): void {
        this._validateFeature = td.ValidateNotSelfIntersecting;
        const draw = (this._draw = new td.TerraDraw({
            adapter: new adapterMod.TerraDrawMapLibreGLAdapter({ map }),
            modes: [
                new td.TerraDrawSelectMode({
                    flags: {
                        polygon: {
                            feature: {
                                draggable: true,
                                selfIntersectable: false,
                                validation: td.ValidateNotSelfIntersecting,
                                coordinates: {
                                    snappable: true,
                                    midpoints: { draggable: true },
                                    draggable: true,
                                    deletable: true,
                                },
                            },
                        },
                    },
                }),
                new td.TerraDrawPolygonMode({
                    editable: true,
                    validation: td.ValidateNotSelfIntersecting,
                    styles: {
                        fillColor: ACCENT,
                        fillOpacity: 0.12,
                        outlineColor: ACCENT,
                        outlineWidth: 2.5,
                        coordinatePointColor: ACCENT,
                        editedPointColor: '#155dfc',
                    },
                }),
            ],
        }));
        draw.start();
        draw.setMode('select');
        draw.on('change', () => this._syncMetrics());
        draw.on('finish', () => {
            draw.setMode('select');
            this._drawing = false;
            this._syncMetrics();
        });
    }

    private _initAddressLayers(map: PlatformMap): void {
        map.addSource('zone-addresses', { type: 'geojson', data: _EMPTY_FC });
        map.addLayer({
            id: 'zone-addresses-pts',
            type: 'circle',
            source: 'zone-addresses',
            paint: {
                'circle-radius': ['case', ['get', 'hi'], 8, 5],
                'circle-color': ['case', ['get', 'hi'], '#155dfc', ACCENT],
                'circle-opacity': 0.9,
                'circle-stroke-color': '#ffffff',
                'circle-stroke-width': ['case', ['get', 'hi'], 2, 1.5],
            },
        });
        map.on('mousemove', 'zone-addresses-pts', (e) => {
            const feature = e.features?.[0];
            const name = feature?.properties?.['name'] as string | undefined;
            const geometry = feature?.geometry as
                | { coordinates: [number, number] }
                | undefined;
            if (!name || !geometry || !this._maplibre || !this._map) return;
            const point = geometry.coordinates;
            if (!this._popup) {
                this._popup = new this._maplibre.Popup({
                    closeButton: false,
                    closeOnClick: false,
                    offset: 12,
                });
            }
            this._popup.setLngLat(point).setText(name).addTo(this._map);
        });
        map.on('mouseleave', 'zone-addresses-pts', () => {
            this._popup?.remove();
        });
    }

    private _retryMap(): void {
        this._mapError = false;
        if (!this._map) {
            this._initStarted = false;
            this._scheduleInit();
            return;
        }
        // Перезагрузка стиля: источники персоздаются в load-хуке заново —
        // стираем весь инстанс и строим карту с нуля.
        const el = this._mapEl();
        this._draw?.stop();
        this._draw = null;
        this._map.remove();
        this._map = null;
        this._initStarted = false;
        if (el) this._scheduleInit();
    }

    private _zoneRing(): LngLatRing | null {
        const draw = this._draw;
        if (!draw) return this._zoneRingFromProps();
        for (const feature of draw.getSnapshot()) {
            if (feature.geometry.type !== 'Polygon') continue;
            const ring = feature.geometry.coordinates[0] as LngLatRing | undefined;
            if (ring && ring.length >= 4) return ring;
        }
        // Пустой store — ещё не импортированная props-зона; после импорта
        // (или очистки пользователем) store — единственный источник правды.
        return this._zoneImported ? null : this._zoneRingFromProps();
    }

    private _zoneRingFromProps(): LngLatRing | null {
        const z = this.zone;
        if (!z || z['type'] !== 'Polygon') return null;
        const coords = z['coordinates'];
        if (!Array.isArray(coords) || !Array.isArray(coords[0]) || coords[0].length < 4) {
            return null;
        }
        const ring: LngLatRing = [];
        for (const pt of coords[0] as Array<unknown>) {
            if (Array.isArray(pt) && typeof pt[0] === 'number' && typeof pt[1] === 'number') {
                ring.push([pt[0], pt[1]]);
            } else {
                return null;
            }
        }
        return ring.length >= 4 ? ring : null;
    }

    private _zoneFeature(): StoreFeature | null {
        const ring = this._zoneRing();
        if (!ring) return null;
        return {
            type: 'Feature',
            geometry: {
                type: 'Polygon',
                coordinates: [ring.map((c) => [c[0]!, c[1]!])],
            },
            properties: { mode: 'polygon' },
        } as StoreFeature;
    }

    private _renderZone(): void {
        const draw = this._draw;
        const map = this._map;
        if (!draw || !map) return;
        const ring = this._zoneRing();
        if (!ring) {
            this._syncMetrics();
            return;
        }
        // Полигона в store ещё нет (зона пришла пропсом) — кладём через
        // addFeatures; mode:'polygon' в properties нужен select-флагам.
        if (!draw.getSnapshot().some((f) => f.geometry.type === 'Polygon')) {
            const feature = this._zoneFeature();
            if (feature) draw.addFeatures([feature]);
            this._zoneImported = true;
        }
        this._fitZone();
        this._syncMetrics();
    }

    private _syncMetrics(): void {
        const ring = this._zoneRing();
        if (!ring || !this._draw) {
            this._areaM2 = 0;
            this._perimM = 0;
            this._points = 0;
            this._selfIntersect = false;
            this._zoneGeoJson = null;
            this._updateHint();
            return;
        }
        this._points = Math.max(0, ring.length - 1);
        let perim = 0;
        for (let i = 0; i < ring.length - 1; i++) {
            perim += _haversineM(ring[i]!, ring[i + 1]!);
        }
        this._perimM = perim;
        this._areaM2 = _ringAreaM2(ring);
        const feature = this._zoneFeature();
        this._selfIntersect = feature ? !this._validate(feature) : false;
        this._zoneGeoJson = feature ? feature.geometry as unknown as Record<string, unknown> : null;
        this._updateHint();
    }

    /** pre-apply проверка: та же ValidateNotSelfIntersecting, что и в режимах. */
    private _validate(feature: StoreFeature): boolean {
        if (!this._validateFeature) return true;
        return this._validateFeature(feature).valid;
    }

    private _validateFeature:
        | ((f: StoreFeature) => { valid: boolean })
        | null = null;

    private _updateHint(): void {
        if (this._selfIntersect) {
            this._hint = this.t('settings.zone_hint_intersect');
            return;
        }
        if (this._drawing) {
            this._hint = this.t('settings.zone_hint_draw');
            return;
        }
        if (this._zoneRing()) {
            this._hint = this._points > ZONE_MAX_POINTS
                ? this.t('settings.zone_hint_toomany')
                : this.t('settings.zone_hint_edit');
            return;
        }
        this._hint = this.t('settings.zone_hint_empty');
    }

    private _startDraw(): void {
        const draw = this._draw;
        if (!draw) return;
        this._drawing = true;
        draw.setMode('polygon');
        this._updateHint();
    }

    private _stopDraw(): void {
        const draw = this._draw;
        if (!draw) return;
        draw.setMode('select');
        this._drawing = false;
        this._updateHint();
    }

    private _clearZone(): void {
        this._stopDraw();
        this._draw?.clear();
        this._syncMetrics();
    }

    private _fitZone(): void {
        const map = this._map;
        const ring = this._zoneRing();
        if (!map || !ring) return;
        const lngs = ring.map((c) => c[0]);
        const lats = ring.map((c) => c[1]);
        map.fitBounds(
            [
                [Math.min(...lngs), Math.min(...lats)],
                [Math.max(...lngs), Math.max(...lats)],
            ],
            { padding: 48, animate: false },
        );
    }

    private async _locate(): Promise<void> {
        const q = this.address.trim();
        if (!q || !this._map || !this._maplibre || !this.shopId) return;
        this._locating = true;
        try {
            const data = (await this._geocodeOp.run({
                shop_id: this.shopId,
                address: q,
            })) as { lat: number; lng: number } | null;
            if (data && this._map) {
                this._map.jumpTo({ center: [data.lng, data.lat], zoom: 14 });
                this._marker?.remove();
                this._marker = new this._maplibre.Marker()
                    .setLngLat([data.lng, data.lat])
                    .addTo(this._map);
            }
        } finally {
            this._locating = false;
        }
    }

    private _zoneFromDraw(): Record<string, unknown> {
        const feature = this._zoneFeature();
        if (!feature) return {};
        const ring = (feature.geometry as { coordinates: Position[][] })
            .coordinates[0]!;
        return ring.length < 4 ? {} : { type: 'Polygon', coordinates: [ring] };
    }

    /** Маркеры адресов из панели — точки справочника, попавшие в зону. */
    private _renderAddressMarkers(items: GeoAddressItem[]): void {
        this._addressFeatures.clear();
        const features = items.map((item) => {
            const feature = {
                type: 'Feature' as const,
                id: item.id,
                geometry: { type: 'Point' as const, coordinates: [item.lng, item.lat] },
                properties: { name: item.display_name, hi: false },
            };
            this._addressFeatures.set(item.id, feature);
            return feature;
        });
        const source = this._map?.getSource('zone-addresses') as
            | { setData(d: unknown): void }
            | undefined;
        source?.setData({ type: 'FeatureCollection', features });
    }

    private _onAddressesChanged(e: Event): void {
        const { items } = (e as CustomEvent<{ items: GeoAddressItem[] }>).detail;
        this._renderAddressMarkers(items);
    }

    /** Hover строки панели → подсветка точки на карте. */
    private _onAddressHover(e: Event): void {
        const { id, lat, lng } = (e as CustomEvent<{ id: number | null; lat: number | null; lng: number | null }>).detail;
        for (const [mid, feature] of this._addressFeatures) {
            if (feature.properties) feature.properties['hi'] = mid === id;
        }
        const source = this._map?.getSource('zone-addresses') as
            | { setData(d: unknown): void }
            | undefined;
        source?.setData({
            type: 'FeatureCollection',
            features: [...this._addressFeatures.values()],
        });
        if (id !== null && lat !== null && lng !== null && this._map) {
            const b = this._map.getBounds();
            if (lng < b.getWest() || lng > b.getEast() || lat < b.getSouth() || lat > b.getNorth()) {
                this._map.easeTo({ center: [lng, lat] });
            }
        }
    }

    private _canApply(): boolean {
        if (this._drawing || this._selfIntersect || this._mapError) return false;
        return this._points <= ZONE_MAX_POINTS;
    }

    private _apply(): void {
        if (!this._canApply()) return;
        const feature = this._zoneFeature();
        if (feature && !this._validate(feature)) {
            this._selfIntersect = true;
            this._updateHint();
            return;
        }
        this.onApply?.(this._zoneFromDraw());
        this.close();
    }

    override renderHeader() {
        return this.t('settings.zone_editor_title');
    }

    override renderBody(): TemplateResult {
        const km2 = _fmtArea(this._areaM2);
        const perim = _fmtKm(this._perimM);
        const perimUnit = this._perimM >= 1000 ? this.t('settings.zone_unit_km') : this.t('settings.zone_unit_m');
        const hasZone = this._zoneRing() !== null;
        return html`
            ${maplibreCssLink()}
            <div class="zwrap">
                <div class="zbody">
                <div class="zmap ${this._drawing ? 'drawing' : ''}"></div>
                <div class="ztools">
                    <button type="button" class="ztool ${this._drawing ? 'on' : ''}"
                        ?disabled=${this._mapError}
                        title=${this.t('settings.zone_draw')}
                        @click=${() => (this._drawing ? this._stopDraw() : this._startDraw())}>
                        <platform-icon name="edit" size="16"></platform-icon>
                        <span>${this._drawing ? this.t('settings.zone_draw_stop') : this.t('settings.zone_draw')}</span>
                    </button>
                    ${hasZone
                        ? html`
                            <button type="button" class="ztool" title=${this.t('settings.zone_fit')}
                                @click=${() => this._fitZone()}>
                                <platform-icon name="maximize" size="16"></platform-icon>
                                <span>${this.t('settings.zone_fit')}</span>
                            </button>
                            <button type="button" class="ztool danger" title=${this.t('settings.zone_clear')}
                                @click=${() => this._clearZone()}>
                                <platform-icon name="delete" size="16"></platform-icon>
                                <span>${this.t('settings.zone_clear')}</span>
                            </button>`
                        : nothing}
                    ${this.address.trim()
                        ? html`
                            <button type="button" class="ztool" title=${this.t('settings.zone_locate')}
                                ?disabled=${this._locating}
                                @click=${() => this._locate()}>
                                <platform-icon name="pin" size="16"></platform-icon>
                                <span>${this.t('settings.zone_locate')}</span>
                            </button>`
                        : nothing}
                </div>
                ${hasZone
                    ? html`
                        <div class="zstats">
                            <span>${this.t('settings.zone_area')}: <b>${km2} ${this.t('settings.zone_unit_km2')}</b></span>
                            <span>${this.t('settings.zone_perimeter')}: <b>${perim} ${perimUnit}</b></span>
                            <span>${this.t('settings.zone_points')}: <b>${this._points}</b></span>
                        </div>`
                    : nothing}
                ${this._hint
                    ? html`<div class="zhint ${this._selfIntersect || this._points > ZONE_MAX_POINTS ? 'warn' : ''}">${this._hint}</div>`
                    : nothing}
                ${this._mapError
                    ? html`
                        <div class="zerror">
                            <platform-icon name="warning" size="28"></platform-icon>
                            <div>${this.t('settings.zone_map_error')}</div>
                            <platform-button size="sm" variant="primary" @click=${() => this._retryMap()}>
                                ${this.t('settings.zone_retry')}
                            </platform-button>
                        </div>`
                    : nothing}
                </div>
                <platform-zone-address-panel
                    addresses-op-name="shop/zone_addresses"
                    .zone=${this._zoneGeoJson}
                    @addresses-changed=${this._onAddressesChanged}
                    @address-hover=${this._onAddressHover}
                ></platform-zone-address-panel>
            </div>
        `;
    }

    override renderFooter(): TemplateResult {
        return html`
            <platform-button variant="secondary" @click=${() => this.close()}>
                ${this.t('settings.zone_cancel')}
            </platform-button>
            <platform-button variant="primary" ?disabled=${!this._canApply()} @click=${() => this._apply()}>
                ${this.t('settings.zone_apply')}
            </platform-button>
        `;
    }
}

customElements.define('shop-zone-editor-modal', ShopZoneEditorModal);
registerModalKind(ShopZoneEditorModal.modalKind, 'shop-zone-editor-modal');

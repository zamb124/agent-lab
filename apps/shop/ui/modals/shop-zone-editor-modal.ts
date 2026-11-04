/**
 * ShopZoneEditorModal — полноэкранный редактор зоны доставки (Leaflet + Geoman).
 *
 * Открывается из <shop-zone-map> (превью в настройках) через
 * openModal('shop.zone_editor', { zone, address, shopId, onApply }).
 * Полигон редактируется профессионально: вершины и midpoints тянутся,
 * правая кнопка/двойной клик удаляет вершину, зона целиком draggable,
 * snapping к краю, самопересечения запрещены (allowSelfIntersection:false)
 * и дополнительно проверяются hasSelfIntersection() перед «Применить».
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
import { loadGeoman } from '../_helpers/leaflet.js';
import type { LeafletModule } from '../_helpers/leaflet.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

type LeafletMap = import('leaflet').Map;
type LeafletPolygon = import('leaflet').Polygon;
type LeafletMarker = import('leaflet').Marker;
type LeafletTileLayer = import('leaflet').TileLayer;
type LatLngTuple = [number, number];
type LeafletLatLng = import('leaflet').LatLng;

type PmPolygon = LeafletPolygon & {
    pm: {
        enable(options?: Record<string, unknown>): void;
        disable(): void;
        hasSelfIntersection(): boolean;
    };
};

const ACCENT = '#f2542d';
const ZONE_MAX_POINTS = 256;
const R_EARTH = 6_371_008.8;

function _ringAreaM2(ring: LatLngTuple[]): number {
    // Сферическая площадь полигона (формула Льюилье/Чемберлена) — достаточна
    // для метрик директору; на зонах городского масштаба погрешность <0.5%.
    let sum = 0;
    for (let i = 0; i < ring.length; i++) {
        const [lat1, lng1] = ring[i]!;
        const [lat2, lng2] = ring[(i + 1) % ring.length]!;
        sum += (lng2 - lng1) * (Math.PI / 180) * (2 + Math.sin(lat1 * Math.PI / 180) + Math.sin(lat2 * Math.PI / 180));
    }
    return Math.abs(sum * R_EARTH * R_EARTH / 2);
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
            .zmap { position: absolute; inset: 0; }
            .zmap.drawing { cursor: crosshair; }

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
            }
        `,
    ];

    private _L: LeafletModule | null = null;
    private _map: LeafletMap | null = null;
    private _tiles: LeafletTileLayer | null = null;
    private _polygon: PmPolygon | null = null;
    private _marker: LeafletMarker | null = null;
    private _ro: ResizeObserver | null = null;
    private _geocodeOp: OpController;
    private _localeSel: SelectController<string>;
    private _initStarted = false;

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
        this._geocodeOp = this.useOp('shop/shop_geocode');
        this._localeSel = this.select((s) => s.i18n.locale);
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
        this._map?.remove();
        this._map = null;
        this._tiles = null;
        this._polygon = null;
        this._marker = null;
        this._initStarted = false;
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
        // Контейнер должен иметь реальный размер — Leaflet кэширует его при
        // init и без размера рисует «уголки» тайлов.
        if (!el.offsetWidth || !el.offsetHeight) {
            requestAnimationFrame(() => this._scheduleInit());
            return;
        }
        this._initStarted = true;
        const L = (this._L = await loadGeoman());
        if (!this.isConnected || !this.open) {
            this._initStarted = false;
            return;
        }
        const map = (this._map = L.map(el, {
            center: [55.7512, 37.6184],
            zoom: 11,
            scrollWheelZoom: true,
        }));
        map.pm.setLang(this._localeSel.value === 'ru' ? 'ru' : 'en');
        this._addTiles();
        map.on('pm:create', (e: { layer: LeafletPolygon }) => {
            this._adoptPolygon(e.layer as PmPolygon);
            this._drawing = false;
            this._updateHint();
        });
        this._ro = new ResizeObserver(() => {
            if (!this._map || !el.offsetWidth || !el.offsetHeight) return;
            this._map.invalidateSize();
        });
        this._ro.observe(el);
        requestAnimationFrame(() => this._map?.invalidateSize());
        this._renderZone();
        this._updateHint();
    }

    private _addTiles(): void {
        if (!this._map || !this._L) return;
        const tiles = (this._tiles = this._L.tileLayer(
            'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            { attribution: '© OpenStreetMap', maxZoom: 19 },
        ));
        tiles.on('tileerror', () => {
            if (this._mapError) return;
            this._mapError = true;
        });
        tiles.addTo(this._map);
    }

    private _retryMap(): void {
        this._mapError = false;
        if (!this._map) {
            this._scheduleInit();
            return;
        }
        this._tiles?.remove();
        this._tiles = null;
        this._addTiles();
        this._map.invalidateSize();
    }

    private _ringLatLngs(): LatLngTuple[] | null {
        const z = this.zone;
        if (!z || z['type'] !== 'Polygon') return null;
        const coords = z['coordinates'];
        if (!Array.isArray(coords) || !Array.isArray(coords[0]) || coords[0].length < 4) {
            return null;
        }
        const ring: LatLngTuple[] = [];
        for (const pt of coords[0] as Array<unknown>) {
            if (Array.isArray(pt) && typeof pt[0] === 'number' && typeof pt[1] === 'number') {
                ring.push([pt[1], pt[0]]); // GeoJSON [lng,lat] → Leaflet [lat,lng]
            } else {
                return null;
            }
        }
        return ring.length >= 4 ? ring : null;
    }

    private _editOptions(): Record<string, unknown> {
        return {
            allowSelfIntersection: false,
            allowSelfIntersectionEdit: false,
            draggable: true,
            snappable: true,
            snapDistance: 20,
            removeVertexOn: 'contextmenu',
            limitMarkersToCount: ZONE_MAX_POINTS,
            markerEditable: true,
            preventMarkerRemoval: false,
            removeLayerBelowMinVertexCount: false,
        };
    }

    private _watchLayer(layer: PmPolygon): void {
        const sync = () => this._syncMetrics();
        layer.on('pm:edit', sync);
        layer.on('pm:update', sync);
        layer.on('pm:vertexadded', sync);
        layer.on('pm:vertexremoved', sync);
        layer.on('pm:markerdragend', sync);
        layer.on('pm:dragend', sync);
    }

    private _adoptPolygon(layer: PmPolygon): void {
        if (!this._map) return;
        this._polygon?.remove();
        this._polygon = layer;
        layer.setStyle({ color: ACCENT, weight: 2.5, fillOpacity: 0.12 });
        layer.pm.enable(this._editOptions());
        this._watchLayer(layer);
        this._syncMetrics();
    }

    private _renderZone(): void {
        if (!this._map || !this._L) return;
        const ring = this._ringLatLngs();
        if (this._polygon) {
            this._polygon.remove();
            this._polygon = null;
        }
        if (ring) {
            this._adoptPolygon(this._L.polygon(ring, {
                color: ACCENT,
                weight: 2.5,
                fillOpacity: 0.12,
            }).addTo(this._map) as PmPolygon);
            this._map.fitBounds(this._polygon!.getBounds(), { padding: [48, 48], animate: false });
        }
        this._syncMetrics();
    }

    private _syncMetrics(): void {
        const poly = this._polygon;
        if (!poly) {
            this._areaM2 = 0;
            this._perimM = 0;
            this._points = 0;
            this._selfIntersect = false;
            this._updateHint();
            return;
        }
        const ring = (poly.getLatLngs() as LeafletLatLng[][])[0] ?? [];
        this._points = ring.length;
        let perim = 0;
        for (let i = 0; i < ring.length; i++) {
            perim += ring[i]!.distanceTo(ring[(i + 1) % ring.length]!);
        }
        this._perimM = perim;
        this._areaM2 = _ringAreaM2(ring.map((p) => [p.lat, p.lng] as LatLngTuple));
        this._selfIntersect = poly.pm.hasSelfIntersection();
        this._updateHint();
    }

    private _updateHint(): void {
        if (this._selfIntersect) {
            this._hint = this.t('settings.zone_hint_intersect');
            return;
        }
        if (this._drawing) {
            this._hint = this.t('settings.zone_hint_draw');
            return;
        }
        if (this._polygon) {
            this._hint = this._points > ZONE_MAX_POINTS
                ? this.t('settings.zone_hint_toomany')
                : this.t('settings.zone_hint_edit');
            return;
        }
        this._hint = this.t('settings.zone_hint_empty');
    }

    private _startDraw(): void {
        if (!this._map) return;
        this._drawing = true;
        this._map.pm.enableDraw('Polygon', {
            allowSelfIntersection: false,
            finishOn: 'dblclick',
            snappable: true,
            snapDistance: 20,
            tooltips: true,
            continueDrawing: false,
            templineStyle: { color: ACCENT, weight: 2.5 },
            hintlineStyle: { color: ACCENT, weight: 2, dashArray: '6 6' },
            pathOptions: { color: ACCENT, weight: 2.5, fillOpacity: 0.12 },
        });
        this._updateHint();
    }

    private _stopDraw(): void {
        this._map?.pm.disableDraw();
        this._drawing = false;
        this._updateHint();
    }

    private _clearZone(): void {
        this._stopDraw();
        if (this._polygon) {
            this._polygon.remove();
            this._polygon = null;
        }
        this._syncMetrics();
        this._updateHint();
    }

    private _fitZone(): void {
        if (this._map && this._polygon) {
            this._map.fitBounds(this._polygon.getBounds(), { padding: [48, 48], animate: false });
        }
    }

    private async _locate(): Promise<void> {
        const q = this.address.trim();
        if (!q || !this._map || !this._L || !this.shopId) return;
        this._locating = true;
        try {
            const data = (await this._geocodeOp.run({
                shop_id: this.shopId,
                address: q,
            })) as { lat: number; lng: number } | null;
            if (data && this._map) {
                this._map.setView([data.lat, data.lng], 14, { animate: false });
                if (this._marker) this._marker.remove();
                this._marker = this._L.marker([data.lat, data.lng], { pmIgnore: true }).addTo(this._map);
            }
        } finally {
            this._locating = false;
        }
    }

    private _zoneFromPolygon(): Record<string, unknown> {
        const poly = this._polygon;
        if (!poly) return {};
        const ll = (poly.getLatLngs() as LeafletLatLng[][])[0] ?? [];
        if (ll.length < 3) return {};
        const ring = ll.map((p) => [p.lng, p.lat]);
        const first = ring[0]!;
        const last = ring[ring.length - 1]!;
        if (first[0] !== last[0] || first[1] !== last[1]) ring.push([first[0]!, first[1]!]);
        return { type: 'Polygon', coordinates: [ring] };
    }

    private _canApply(): boolean {
        if (this._drawing || this._selfIntersect || this._mapError) return false;
        return this._points <= ZONE_MAX_POINTS;
    }

    private _apply(): void {
        if (!this._canApply()) return;
        if (this._polygon && this._polygon.pm.hasSelfIntersection()) {
            this._selfIntersect = true;
            this._updateHint();
            return;
        }
        this.onApply?.(this._zoneFromPolygon());
        this.close();
    }

    override renderHeader() {
        return this.t('settings.zone_editor_title');
    }

    override renderBody(): TemplateResult {
        const km2 = _fmtArea(this._areaM2);
        const perim = _fmtKm(this._perimM);
        const perimUnit = this._perimM >= 1000 ? this.t('settings.zone_unit_km') : this.t('settings.zone_unit_m');
        return html`
            <div class="zwrap">
                <div class="zmap ${this._drawing ? 'drawing' : ''}"></div>
                <div class="ztools">
                    <button type="button" class="ztool ${this._drawing ? 'on' : ''}"
                        ?disabled=${this._mapError}
                        title=${this.t('settings.zone_draw')}
                        @click=${() => (this._drawing ? this._stopDraw() : this._startDraw())}>
                        <platform-icon name="edit" size="16"></platform-icon>
                        <span>${this._drawing ? this.t('settings.zone_draw_stop') : this.t('settings.zone_draw')}</span>
                    </button>
                    ${this._polygon
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
                ${this._polygon
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

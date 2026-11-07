/**
 * GeoRouteLabPage — маршрутная лаборатория.
 *
 * Три инструмента (сегментированный контрол):
 * - `route` — клики ставят A/B, `geo/route/calculate` рисует геометрию
 *   overlay'ем и показывает метрики;
 * - `matrix` — клики добавляют точки, `geo/route/matrix` показывает
 *   таблицу N×N длительностей;
 * - `order` — первая точка старт, остальные остановки,
 *   `geo/route/optimal_order` рисует оптимальный объезд и последовательность.
 * Режим движения — чипы car/foot/bike/scooter, пересчёт результата.
 */

import { html, css, nothing } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpControllerOf } from '@platform/lib/base/use-resource.js';
import type {
    geoRouteOp,
    geoMatrixOp,
    geoOrderOp,
} from '@platform/lib/events/resources/geo-route.resource.js';
import type {
    GeoRouteMatrixResponse,
    GeoRouteOrderResponse,
} from '@platform/lib/events/wire/geo.gen.js';
import '@platform/lib/components/platform-map.js';
import type { PlatformMapConfig, LngLat } from '@platform/lib/components/platform-map.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import type { Feature, FeatureCollection, LineString } from 'geojson';

const MODES = ['car', 'foot', 'bike', 'scooter'] as const;
const TOOLS = ['route', 'matrix', 'order'] as const;
type Mode = (typeof MODES)[number];
type Tool = (typeof TOOLS)[number];

const PIN_COLORS = ['#8b5cf6', '#06b6d4', '#f59e0b', '#ec4899', '#14b8a6'] as const;

export class GeoRouteLabPage extends PlatformPage {
    static i18nNamespace = 'geo';

    private _routeCtl: OpControllerOf<typeof geoRouteOp>;
    private _matrixCtl: OpControllerOf<typeof geoMatrixOp>;
    private _orderCtl: OpControllerOf<typeof geoOrderOp>;

    static override properties = {
        _mode: { state: true },
        _tool: { state: true },
        _from: { state: true },
        _to: { state: true },
        _result: { state: true },
        _routeGeometry: { state: true },
        _points: { state: true },
        _matrix: { state: true },
        _order: { state: true },
        _orderGeometry: { state: true },
    };

    declare _mode: Mode;
    declare _tool: Tool;
    declare _from: LngLat | null;
    declare _to: LngLat | null;
    declare _result: { distance_m: number; duration_s: number } | null;
    declare _routeGeometry: LineString | null;
    declare _points: LngLat[];
    declare _matrix: GeoRouteMatrixResponse | null;
    declare _order: GeoRouteOrderResponse | null;
    declare _orderGeometry: FeatureCollection | null;

    constructor() {
        super();
        this._routeCtl = this.useOp('geo/route');
        this._matrixCtl = this.useOp('geo/route_matrix');
        this._orderCtl = this.useOp('geo/route_order');
        this._mode = 'car';
        this._tool = 'route';
        this._from = null;
        this._to = null;
        this._result = null;
        this._routeGeometry = null;
        this._points = [];
        this._matrix = null;
        this._order = null;
        this._orderGeometry = null;
    }

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .breadcrumbs-wrap { flex-shrink: 0; margin-bottom: var(--space-3); }
            .map-wrap {
                position: relative;
                flex: 1;
                min-height: 0;
                display: flex;
            }
            platform-map { flex: 1; min-height: 0; }
            .map-modes {
                position: absolute;
                top: 12px;
                left: 12px;
                z-index: 6;
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: 4px;
                background: var(--glass-solid-medium, rgba(35, 35, 55, 0.85));
                border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                border-radius: var(--radius-full, 999px);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
            }
            .map-tools {
                position: absolute;
                top: 12px;
                left: 50%;
                transform: translateX(-50%);
                z-index: 6;
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: 4px;
                background: var(--glass-solid-medium, rgba(35, 35, 55, 0.85));
                border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                border-radius: var(--radius-full, 999px);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
            }
            .mode-btn {
                border: 1px solid transparent;
                background: transparent;
                color: var(--text-secondary);
                border-radius: var(--radius-full, 999px);
                padding: var(--space-1) var(--space-3);
                font: inherit;
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background 0.15s ease, color 0.15s ease;
            }
            .mode-btn:hover { color: var(--text-primary); }
            .mode-btn.active {
                color: var(--accent);
                background: var(--accent-subtle);
                border-color: color-mix(in srgb, var(--accent) 40%, transparent);
            }
            .map-hint {
                position: absolute;
                top: 56px;
                left: 12px;
                z-index: 6;
                padding: var(--space-1) var(--space-3);
                background: var(--glass-solid-medium, rgba(35, 35, 55, 0.85));
                border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                border-radius: var(--radius-md, 10px);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                font-size: var(--text-xs, 12px);
                color: var(--text-tertiary);
                pointer-events: none;
            }
            .map-metrics {
                position: absolute;
                bottom: 12px;
                left: 12px;
                z-index: 6;
                display: flex;
                gap: var(--space-4);
                padding: var(--space-2) var(--space-4);
                background: var(--glass-solid-medium, rgba(35, 35, 55, 0.85));
                border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                border-radius: var(--radius-md, 10px);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                pointer-events: none;
            }
            .map-metrics strong { color: var(--text-primary); font-weight: var(--font-semibold); }
            .map-actions {
                position: absolute;
                bottom: 12px;
                right: 12px;
                z-index: 6;
                display: flex;
                gap: var(--space-2);
            }
            .map-panel {
                position: absolute;
                top: 56px;
                right: 12px;
                z-index: 6;
                width: 320px;
                max-height: calc(100% - 140px);
                overflow: auto;
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-medium, rgba(35, 35, 55, 0.9));
                border: 1px solid var(--glass-border-subtle, rgba(255, 255, 255, 0.08));
                border-radius: var(--radius-md, 10px);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .map-panel table { width: 100%; border-collapse: collapse; font-size: var(--text-xs); }
            .map-panel th, .map-panel td { padding: 4px 6px; text-align: center; }
            .map-panel th { color: var(--text-tertiary); font-weight: var(--font-medium); }
            .map-panel td { color: var(--text-primary); border-top: 1px solid var(--glass-border-subtle); }
            .map-panel td.na { color: var(--text-tertiary); }
            .seq { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: var(--space-2); }
            .seq .pill {
                padding: 2px 8px;
                border-radius: var(--radius-full, 999px);
                background: var(--accent-subtle);
                color: var(--accent);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .panel-total { margin-top: var(--space-2); color: var(--text-tertiary); }
            .panel-total strong { color: var(--text-primary); }
        `,
    ];

    private get _mapConfig(): PlatformMapConfig {
        const markers: NonNullable<PlatformMapConfig['markers']> = [];
        if (this._from) markers.push({ key: 'from', lngLat: this._from, color: '#22c55e', title: 'A' });
        if (this._to) markers.push({ key: 'to', lngLat: this._to, color: '#ef4444', title: 'B' });
        this._points.forEach((pt, i) => {
            const isStart = this._tool === 'order' && i === 0;
            markers.push({
                key: `pt${i}`,
                lngLat: pt,
                color: isStart ? '#22c55e' : (PIN_COLORS[i % PIN_COLORS.length] ?? '#8b5cf6'),
                title: isStart ? 'S' : `${i + 1}`,
            });
        });
        const overlays: NonNullable<PlatformMapConfig['overlays']> = [];
        if (this._routeGeometry) {
            const feature: Feature<LineString> = {
                type: 'Feature',
                geometry: this._routeGeometry,
                properties: {},
            };
            overlays.push({ name: 'route', data: feature, color: '#155dfc', width: 5 });
        }
        if (this._orderGeometry) {
            overlays.push({ name: 'order', data: this._orderGeometry, color: '#8b5cf6', width: 5 });
        }
        return {
            interactive: true,
            controls: { zoom: true, layers: true, locate: true },
            layers: { fetch: true },
            featureCards: { hover: true, click: false },
            markers,
            overlays,
        };
    }

    private _clearResults(): void {
        this._result = null;
        this._routeGeometry = null;
        this._matrix = null;
        this._order = null;
        this._orderGeometry = null;
    }

    private async _calculate(): Promise<void> {
        if (!this._from || !this._to) return;
        const res = await this._routeCtl.run({
            from_point: { lat: this._from[1], lng: this._from[0] },
            to_point: { lat: this._to[1], lng: this._to[0] },
            mode: this._mode,
        });
        if (res === null) {
            this._result = null;
            this._routeGeometry = null;
            this.toast('route_lab.failed', { type: 'error' });
            return;
        }
        this._result = { distance_m: res.distance_m, duration_s: res.duration_s };
        this._routeGeometry = (res.geometry as LineString | null) ?? null;
    }

    private async _computeMatrix(): Promise<void> {
        if (this._points.length < 2) return;
        const points = this._points.map(([lng, lat]) => ({ lat, lng }));
        const res = await this._matrixCtl.run({
            sources: points,
            targets: points,
            mode: this._mode,
        });
        if (res === null) {
            this._matrix = null;
            this.toast('route_lab.failed', { type: 'error' });
            return;
        }
        this._matrix = res;
    }

    private async _computeOrder(): Promise<void> {
        if (this._points.length < 2) return;
        const [start, ...stops] = this._points;
        if (!start) return;
        const res = await this._orderCtl.run({
            start: { lat: start[1], lng: start[0] },
            points: stops.map(([lng, lat]) => ({ lat, lng })),
            mode: this._mode,
            legs: true,
        });
        if (res === null) {
            this._order = null;
            this._orderGeometry = null;
            this.toast('route_lab.failed', { type: 'error' });
            return;
        }
        this._order = res;
        const features: Feature[] = [];
        for (const leg of res.legs ?? []) {
            const geom = leg.geometry as Feature['geometry'] | null;
            if (geom) features.push({ type: 'Feature', geometry: geom, properties: {} });
        }
        this._orderGeometry = features.length
            ? { type: 'FeatureCollection', features }
            : null;
    }

    private async _recompute(): Promise<void> {
        if (this._tool === 'route') return this._calculate();
        if (this._tool === 'matrix' && this._matrix) return this._computeMatrix();
        if (this._tool === 'order' && this._order) return this._computeOrder();
    }

    private _onMapClick(e: CustomEvent<{ lngLat: LngLat }>): void {
        const lngLat = e.detail.lngLat;
        if (this._tool === 'route') {
            if (!this._from || (this._from && this._to)) {
                this._from = lngLat;
                this._to = null;
                this._clearResults();
                return;
            }
            this._to = lngLat;
            void this._calculate();
            return;
        }
        this._points = [...this._points, lngLat];
        if (this._tool === 'order') {
            this._order = null;
            this._orderGeometry = null;
        } else {
            this._matrix = null;
        }
    }

    private _setTool(tool: Tool): void {
        if (this._tool === tool) return;
        this._tool = tool;
        this._from = null;
        this._to = null;
        this._points = [];
        this._clearResults();
    }

    private _setMode(mode: Mode): void {
        this._mode = mode;
        void this._recompute();
    }

    private _resetPoints(): void {
        this._points = [];
        this._clearResults();
    }

    private _renderMatrixPanel(): TemplateResult | typeof nothing {
        const m = this._matrix;
        if (!m) return nothing;
        const n = this._points.length;
        const head = Array.from({ length: n }, (_, i) => html`<th>P${i + 1}</th>`);
        return html`
            <div class="map-panel" data-panel="matrix">
                <table>
                    <thead><tr><th></th>${head}</tr></thead>
                    <tbody>
                        ${m.durations_s.map((row, i) => html`
                            <tr>
                                <th>P${i + 1}</th>
                                ${row.map((cell) => html`
                                    <td class=${cell === null ? 'na' : ''}>
                                        ${cell === null ? '—' : Math.round(cell / 60)}
                                    </td>
                                `)}
                            </tr>
                        `)}
                    </tbody>
                </table>
                <div class="panel-total">${this.t('route_lab.matrix_minutes')}</div>
            </div>
        `;
    }

    private _renderOrderPanel(): TemplateResult | typeof nothing {
        const res = this._order;
        if (!res) return nothing;
        const labels = ['S', ...res.order.map((i) => `P${i + 2}`)];
        return html`
            <div class="map-panel" data-panel="order">
                <div class="seq">
                    ${labels.map((label, i) => html`
                        <span class="pill">${label}</span>${i < labels.length - 1 ? html`→` : ''}
                    `)}
                </div>
                <div class="panel-total">
                    ${this.t('route_lab.order_total')}
                    <strong>${(res.total_distance_m / 1000).toFixed(2)} ${this.t('route_lab.km')}</strong>
                    · <strong>${Math.round(res.total_duration_s / 60)} ${this.t('route_lab.min')}</strong>
                </div>
            </div>
        `;
    }

    override render() {
        const hintKey = this._tool === 'route'
            ? 'route_lab.click_hint'
            : this._tool === 'matrix'
                ? 'route_lab.matrix_hint'
                : 'route_lab.order_hint';
        const showHint = this._tool === 'route' ? !this._result : this._points.length < 2;
        const canCompute = this._points.length >= 2;
        const busy = this._matrixCtl.busy || this._orderCtl.busy;
        return html`
            <div class="breadcrumbs-wrap">
                <platform-breadcrumbs></platform-breadcrumbs>
            </div>
            <page-header
                dense
                title=${this.t('route_lab.header_title')}
            ></page-header>
            <div class="map-wrap">
                <platform-map
                    .config=${this._mapConfig}
                    @pm-click=${(e: CustomEvent<{ lngLat: LngLat }>) => this._onMapClick(e)}
                ></platform-map>
                <div class="map-tools">
                    ${TOOLS.map((tool) => html`
                        <button
                            class="mode-btn ${this._tool === tool ? 'active' : ''}"
                            data-tool=${tool}
                            @click=${() => this._setTool(tool)}
                        >${this.t(`route_lab.tool_${tool}`)}</button>
                    `)}
                </div>
                <div class="map-modes">
                    ${MODES.map((mode) => html`
                        <button
                            class="mode-btn ${this._mode === mode ? 'active' : ''}"
                            @click=${() => this._setMode(mode)}
                        >${this.t(`route_lab.mode_${mode}`)}</button>
                    `)}
                </div>
                ${showHint ? html`<div class="map-hint">${this.t(hintKey)}</div>` : nothing}
                ${this._result
                    ? html`
                        <div class="map-metrics">
                            <span>${this.t('route_lab.distance')} <strong>${(this._result.distance_m / 1000).toFixed(2)} ${this.t('route_lab.km')}</strong></span>
                            <span>${this.t('route_lab.duration')} <strong>${Math.round(this._result.duration_s / 60)} ${this.t('route_lab.min')}</strong></span>
                        </div>
                    `
                    : nothing}
                ${this._renderMatrixPanel()}
                ${this._renderOrderPanel()}
                ${this._tool !== 'route' && this._points.length > 0
                    ? html`
                        <div class="map-actions">
                            <platform-button size="sm" variant="ghost" @click=${this._resetPoints}>
                                ${this.t('route_lab.reset')}
                            </platform-button>
                            <platform-button
                                size="sm"
                                variant="secondary"
                                ?disabled=${!canCompute}
                                ?busy=${busy}
                                data-action="compute"
                                @click=${() => (this._tool === 'matrix' ? this._computeMatrix() : this._computeOrder())}
                            >
                                ${this.t('route_lab.compute')}
                            </platform-button>
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('geo-route-lab-page', GeoRouteLabPage);

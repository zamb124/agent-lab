/**
 * GeoMapLabPage — витрина возможностей `<platform-map>`.
 *
 * Демонстрирует и покрывает реальными сценариями все секции config:
 * канонические слои, поиск, линейку, контекстное меню, кластеризованные
 * и draggable-маркеры, GeoJSON-оверлей зоны, рисование TerraDraw,
 * панель адресов и встраивание неинтерактивного превью.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-map.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import type { LngLat, PlatformMapConfig, PlatformMapMarker } from '@platform/lib/components/platform-map.js';
import type { Polygon } from 'geojson';

const CENTER: LngLat = [37.6178, 55.7503];

const DEMO_ZONE: Polygon = {
    type: 'Polygon',
    coordinates: [
        [
            [37.616, 55.7498],
            [37.6205, 55.7498],
            [37.6205, 55.7512],
            [37.616, 55.7512],
            [37.616, 55.7498],
        ],
    ],
};

export class GeoMapLabPage extends PlatformPage {
    static i18nNamespace = 'geo';

    private _zone: Polygon | null = DEMO_ZONE;

    private get _mapConfig(): PlatformMapConfig {
        const markers: PlatformMapMarker[] = [
            { key: 'courier', lngLat: [37.6173, 55.7501] as LngLat, color: '#155dfc', title: 'Courier' },
            { key: 'depot', lngLat: [37.6195, 55.7509] as LngLat, color: '#22c55e', draggable: true, title: 'Depot' },
        ];
        // Кластер демо-точек вокруг центра — реальное кластерное поведение.
        for (let i = 0; i < 24; i++) {
            const dx = ((i % 6) - 2.5) * 0.003;
            const dy = ((i / 6) - 1.5) * 0.002;
            markers.push({ key: `poi-${i}`, lngLat: [37.6178 + dx, 55.7503 + dy] as LngLat });
        }
        return {
            center: CENTER,
            zoom: 12,
            interactive: true,
            rotate: true,
            hash: true,
            controls: {
                zoom: true,
                layers: true,
                locate: true,
                search: true,
                ruler: true,
                rulerArea: true,
                fit: true,
                compass: true,
                scheme: true,
                route: true,
                export: true,
                miniMap: true,
                fullscreen: true,
                scale: true,
            },
            layers: { fetch: true },
            featureCards: { hover: true, click: true },
            markers,
            markersCluster: true,
            overlays: [
                {
                    name: 'demo-zone',
                    data: { type: 'Feature', geometry: DEMO_ZONE, properties: { name: 'demo' } },
                    color: '#7c3aed',
                },
            ],
            search: { limit: 7 },
            contextMenu: true,
            locateWatch: true,
            statusBar: true,
            draw: { zone: this._zone },
            addressesPanel: { zone: this._zone },
            route: {
                points: [
                    [37.6173, 55.7501] as LngLat,
                    [37.6184, 55.7506] as LngLat,
                ],
                mode: 'car',
                build: true,
                fit: false,
            },
            isochrone: {
                center: [37.6181, 55.7504] as LngLat,
                minutes: [3, 7],
                mode: 'foot',
            },
            moveEvent: true,
        };
    }

    static override styles = [
        PlatformPage.styles,
        css`
            :host { display: flex; flex-direction: column; height: 100%; }
            .layout { flex: 1; min-height: 0; display: flex; gap: var(--space-4); }
            .map-col { flex: 1; min-width: 0; display: flex; }
            platform-map { flex: 1; min-height: 0; }
            .preview-col { width: 240px; flex-shrink: 0; display: flex; flex-direction: column; gap: var(--space-3); }
            .preview { height: 180px; border-radius: var(--radius-lg, 14px); overflow: hidden; }
            .preview platform-map { display: block; height: 100%; }
            .preview-title { font-size: var(--text-sm); color: var(--text-tertiary); }
        `,
    ];

    private _onDrawChange = (e: Event): void => {
        const zone = (e as CustomEvent<{ zone: Polygon | null }>).detail.zone;
        this._zone = zone;
        this.requestUpdate();
    };

    override render() {
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header
                title=${this.t('map_lab.header_title')}
                subtitle=${this.t('map_lab.header_subtitle')}
            ></page-header>
            <div class="layout">
                <div class="map-col">
                    <platform-map
                        class="main-map"
                        .config=${this._mapConfig}
                        @pm-draw-change=${this._onDrawChange}
                    ></platform-map>
                </div>
                <div class="preview-col">
                    <span class="preview-title">${this.t('map_lab.preview_title')}</span>
                    <div class="preview">
                        <platform-map
                            .config=${{
                                center: CENTER,
                                zoom: 14,
                                interactive: true,
                                cooperativeGestures: true,
                                scheme: 'auto',
                                layers: { fetch: false },
                                markers: [{ key: 'pin', lngLat: CENTER, title: 'HQ' }],
                            }}
                        ></platform-map>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('geo-map-lab-page', GeoMapLabPage);

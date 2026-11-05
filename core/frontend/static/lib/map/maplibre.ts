/**
 * Ленивая загрузка MapLibre GL JS и PMTiles-протокола.
 *
 * Vendor-ассеты лежат в core: `/static/core/lib/vendor/*` отдаётся любым
 * сервисом (mount `/static/core/lib` → embed-dist), поэтому компоненты карт
 * переиспользуются продуктами без копии ассетов в каждом ui/.
 *
 * `pmtiles://` URL векторных источников резолвит pmtiles.js Protocol —
 * регистрируется однократно до создания первой карты.
 */

import { html } from 'lit';
import type { TemplateResult } from 'lit';

export type MapLibreModule = typeof import('maplibre-gl');

export const MAPLIBRE_CSS = '/static/core/lib/vendor/maplibre/maplibre-gl.css';

/**
 * Web-worker MapLibre: бандлер не эмитит `maplibre-gl-worker.mjs` рядом с
 * чанком (esbuild не видит `new URL('./x', import.meta.url)` в node_modules),
 * поэтому воркер отдаём тем же vendor-маршрутом, что и CSS.
 */
export const MAPLIBRE_WORKER_URL = '/static/core/lib/vendor/maplibre/maplibre-gl-worker.mjs';

/** Style JSON векторной базовой карты, отдаётся geo-сервисом (анонимный). */
export const BASEMAP_STYLE_URL = '/geo/api/v1/tiles/style.json';

let _maplibrePromise: Promise<MapLibreModule> | null = null;
let _pmtilesProtocol = false;

/**
 * Стили карты должны жить ВНУТРИ shadow root компонента — stylesheet из
 * document.head сквозь shadow boundary не проходит. Вставлять в шаблон
 * рядом с .map-контейнером.
 */
export function maplibreCssLink(): TemplateResult {
    return html`<link rel="stylesheet" href=${MAPLIBRE_CSS} />`;
}

export function loadMapLibre(): Promise<MapLibreModule> {
    if (!_maplibrePromise) {
        _maplibrePromise = Promise.all([import('maplibre-gl'), import('pmtiles')]).then(
            ([mod, pmtiles]) => {
                const maplibre = ((mod as { default?: MapLibreModule }).default ??
                    mod) as MapLibreModule;
                maplibre.setWorkerUrl(MAPLIBRE_WORKER_URL);
                if (!_pmtilesProtocol) {
                    _pmtilesProtocol = true;
                    const protocol = new pmtiles.Protocol();
                    maplibre.addProtocol('pmtiles', protocol.tile);
                }
                return maplibre;
            },
        );
    }
    return _maplibrePromise;
}

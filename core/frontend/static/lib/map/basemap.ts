/**
 * Базовая векторная карта платформы: MapLibre + style JSON geo-сервиса.
 *
 * Единая точка создания карты — тема/источник стиля задаются здесь
 * (style.json живёт на geo и собирается из vendored Protomaps Light).
 */

import { BASEMAP_STYLE_URL, loadMapLibre } from './maplibre.js';
import type { MapLibreModule } from './maplibre.js';

export type PlatformMap = import('maplibre-gl').Map;

export interface BasemapOptions {
    center: [number, number];
    zoom: number;
    interactive?: boolean;
}

/** Создаёт MapLibre-карту в контейнере; `interactive=false` — без zoom/tilt. */
export async function createBasemap(
    el: HTMLElement,
    { center, zoom, interactive = true }: BasemapOptions,
): Promise<PlatformMap> {
    const maplibre: MapLibreModule = await loadMapLibre();
    const map = new maplibre.Map({
        container: el,
        style: BASEMAP_STYLE_URL,
        center,
        zoom,
        scrollZoom: interactive,
        boxZoom: interactive,
        dragPan: interactive,
        dragRotate: false,
        pitchWithRotate: false,
        keyboard: interactive,
        doubleClickZoom: interactive,
        touchZoomRotate: interactive,
        attributionControl: { compact: true },
    });
    return map;
}

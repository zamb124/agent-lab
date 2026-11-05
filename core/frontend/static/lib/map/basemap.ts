/**
 * Базовая векторная карта платформы: MapLibre + style JSON geo-сервиса.
 *
 * Единая точка создания карты — тема/источник стиля задаются здесь
 * (style.json живёт на geo и собирается из vendored Protomaps Light).
 */

import { basemapStyleUrl, loadMapLibre } from './maplibre.js';
import type { BasemapScheme, MapLibreModule } from './maplibre.js';

export type PlatformMap = import('maplibre-gl').Map;
export type { BasemapScheme } from './maplibre.js';

export interface BasemapOptions {
    center: [number, number];
    zoom: number;
    interactive?: boolean;
    /** Светлая/тёмная схема базовой карты (style.json?scheme=…). */
    scheme?: BasemapScheme;
    /** Правый drag/два пальца — поворот и наклон камеры (компас в контролах). */
    rotate?: boolean;
    /**
     * Embed-режим: колесо мыши/два пальца требуют Ctrl/⌘ — страница
     * скроллится свободно, карта не «захватывает» жесты (как Google embed).
     */
    cooperativeGestures?: boolean;
    /** Синхронизация камеры с URL-хэшем `map=z/lat/lng` — deep-link. */
    hash?: boolean;
    /** preserveDrawingBuffer — нужен для экспорта canvas в PNG. */
    preserveBuffer?: boolean;
}

/** Создаёт MapLibre-карту в контейнере; `interactive=false` — без zoom/tilt. */
export async function createBasemap(
    el: HTMLElement,
    {
        center,
        zoom,
        interactive = true,
        scheme = 'light',
        rotate = false,
        cooperativeGestures = false,
        hash = false,
        preserveBuffer = false,
    }: BasemapOptions,
): Promise<PlatformMap> {
    const maplibre: MapLibreModule = await loadMapLibre();
    const map = new maplibre.Map({
        container: el,
        style: basemapStyleUrl(scheme),
        center,
        zoom,
        scrollZoom: interactive,
        boxZoom: interactive,
        dragPan: interactive,
        dragRotate: interactive && rotate,
        pitchWithRotate: interactive && rotate,
        keyboard: interactive,
        doubleClickZoom: interactive,
        touchZoomRotate: interactive,
        cooperativeGestures,
        hash: hash ? 'map' : false,
        ...(preserveBuffer ? { canvasContextAttributes: { preserveDrawingBuffer: true } } : {}),
        attributionControl: { compact: true },
    });
    return map;
}

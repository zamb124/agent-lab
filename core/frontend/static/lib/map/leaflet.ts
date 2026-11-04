/**
 * Ленивая загрузка Leaflet и Leaflet-Geoman: JS-бандлы и CSS по требованию.
 *
 * Leaflet — UMD: в esbuild-бандле это namespace/default, в голом браузере —
 * глобал window.L (dist/leaflet-src.js выставляет его сам). Geoman — IIFE,
 * читает глобал window.L и вешает L.PM + initHook: `map.pm` появляется на
 * каждой карте, созданной ПОСЛЕ загрузки geoman. Поэтому порядок строгий:
 * loadLeaflet() → window.L → loadGeoman() → L.map().
 *
 * Vendor-ассеты лежат в core: `/static/core/lib/vendor/*` отдаётся любым
 * сервисом (mount `/static/core/lib` → embed-dist), поэтому компоненты карт
 * переиспользуются продуктами без копии ассетов в каждом ui/.
 */

export type LeafletModule = typeof import('leaflet');

export const LEAFLET_CSS = '/static/core/lib/vendor/leaflet/leaflet.css';
export const GEOMAN_CSS = '/static/core/lib/vendor/geoman/leaflet-geoman.css';

let _leafletPromise: Promise<LeafletModule> | null = null;
let _geomanPromise: Promise<LeafletModule> | null = null;

import { html } from 'lit';
import type { TemplateResult } from 'lit';

/**
 * Стили карты должны жить ВНУТРИ shadow root компонента — stylesheet из
 * document.head сквозь shadow boundary не проходит (без них тайлы Leaflet
 * плывут «пазлом» в DOM-порядке). Вставлять в шаблон рядом с .map-контейнером.
 */
export function leafletCssLinks({ geoman = false }: { geoman?: boolean } = {}): TemplateResult {
    return html`<link rel="stylesheet" href=${LEAFLET_CSS} />${geoman
        ? html`<link rel="stylesheet" href=${GEOMAN_CSS} />`
        : ''}`;
}

export function loadLeaflet(): Promise<LeafletModule> {
    if (!_leafletPromise) {
        _leafletPromise = import('leaflet').then((mod) => {
            const resolved = ((mod as { default?: LeafletModule }).default ?? mod) as LeafletModule;
            const L = typeof resolved.map === 'function'
                ? resolved
                : (window as unknown as { L: LeafletModule }).L;
            // Geoman — IIFE над глобалом: гарантируем window.L в обоих режимах
            // (бандл и голый браузер/WTR).
            (window as unknown as { L: LeafletModule }).L = L;
            return L;
        });
    }
    return _leafletPromise;
}

export function loadGeoman(): Promise<LeafletModule> {
    if (!_geomanPromise) {
        _geomanPromise = loadLeaflet().then((L) =>
            import('@geoman-io/leaflet-geoman-free').then(() => L),
        );
    }
    return _geomanPromise;
}

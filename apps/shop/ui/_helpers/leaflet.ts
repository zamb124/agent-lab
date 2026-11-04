/**
 * Ленивая загрузка Leaflet и Leaflet-Geoman: JS-бандлы и CSS по требованию.
 *
 * Leaflet — UMD: в esbuild-бандле это namespace/default, в голом браузере —
 * глобал window.L (dist/leaflet-src.js выставляет его сам). Geoman — IIFE,
 * читает глобал window.L и вешает L.PM + initHook: `map.pm` появляется на
 * каждой карте, созданной ПОСЛЕ загрузки geoman. Поэтому порядок строгий:
 * loadLeaflet() → window.L → loadGeoman() → L.map().
 */

export type LeafletModule = typeof import('leaflet');

let _leafletPromise: Promise<LeafletModule> | null = null;
let _geomanPromise: Promise<LeafletModule> | null = null;

function _ensureCss(id: string, href: string): void {
    if (document.getElementById(id)) return;
    const link = document.createElement('link');
    link.id = id;
    link.rel = 'stylesheet';
    link.href = href;
    document.head.appendChild(link);
}

export function loadLeaflet(): Promise<LeafletModule> {
    if (!_leafletPromise) {
        _ensureCss('leaflet-css', '/shop/ui/static/vendor/leaflet/leaflet.css');
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
        _ensureCss('geoman-css', '/shop/ui/static/vendor/geoman/leaflet-geoman.css');
        _geomanPromise = loadLeaflet().then((L) =>
            import('@geoman-io/leaflet-geoman-free').then(() => L),
        );
    }
    return _geomanPromise;
}

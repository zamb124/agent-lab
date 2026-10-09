/**
 * Иконка Flow UI: ``<img>`` из ``/static/core/assets/icons`` (embed без EventBus)
 * или stroke-SVG ``currentColor``. Фигуры — через ``svg`` tagged template,
 * иначе ``<rect>``/``<path>`` оказываются в HTML-namespace и не рисуются.
 */

import { html, svg } from '../../lit-shim.js';
import { platformStaticSrc } from '../shell/brand-logo.js';

const GLYPHS = Object.freeze(new Set([
    'alert-triangle', 'check', 'chevron-down', 'chevron-left', 'chevron-right', 'chevron-up', 'close', 'copy',
    'download', 'file-text', 'git-branch', 'globe', 'info', 'list', 'mic', 'mic-off', 'minimize', 'paperclip',
    'pause', 'play', 'plus', 'refresh', 'rotate-ccw', 'send', 'share', 'square', 'trash', 'volume-off', 'volume-up',
]));

function strokeGlyph(size: number, inner: unknown) {
    return html`<svg class="fu-glyph" width=${size} height=${size} viewBox="0 0 24 24" fill="none"
        stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"
        aria-hidden="true">${inner}</svg>`;
}

const STROKE_GLYPHS: Record<string, (size: number) => unknown> = Object.freeze({
    copy: (size: number) => strokeGlyph(size, svg`<rect width="14" height="14" x="8" y="8" rx="2" ry="2" fill="none"></rect><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" fill="none"></path>`),
    'git-branch': (size: number) => strokeGlyph(size, svg`<line x1="6" x2="6" y1="3" y2="15"></line><circle cx="18" cy="6" r="3" fill="none"></circle><circle cx="6" cy="18" r="3" fill="none"></circle><path d="M18 9a9 9 0 0 1-9 9" fill="none"></path>`),
    list: (size: number) => strokeGlyph(size, svg`<path d="M8 6h13" fill="none"></path><path d="M8 12h13" fill="none"></path><path d="M8 18h13" fill="none"></path><path d="M3 6h.01" fill="none"></path><path d="M3 12h.01" fill="none"></path><path d="M3 18h.01" fill="none"></path>`),
    check: (size: number) => strokeGlyph(size, svg`<path d="M20 6 9 17l-5-5" fill="none"></path>`),
});

export function flowUIGlyph(name: string, size = 16, platformUiOrigin = '') {
    if (!GLYPHS.has(name)) throw new Error(`flow-ui: unknown glyph ${JSON.stringify(name)}`);
    if (!Number.isFinite(size) || size <= 0) throw new Error(`flow-ui: invalid glyph size ${String(size)}`);
    const stroke = STROKE_GLYPHS[name];
    if (stroke) return stroke(size);
    const src = platformStaticSrc(platformUiOrigin, `/static/core/assets/icons/${name}.svg`);
    return html`<img class="fu-glyph" src=${src} width=${size} height=${size} alt="" aria-hidden="true">`;
}

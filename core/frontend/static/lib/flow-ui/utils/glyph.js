/**
 * Иконка Flow UI как ``<img>`` из ``/static/core/assets/icons`` — без ``platform-icon`` и EventBus,
 * чтобы работать в embed на чужом origin.
 */

import { html } from '../../lit-shim.js';
import { platformStaticSrc } from '../shell/brand-logo.js';

const GLYPHS = Object.freeze(new Set([
    'alert-triangle', 'check', 'chevron-down', 'chevron-left', 'chevron-right', 'chevron-up', 'close', 'copy',
    'download', 'file-text', 'globe', 'info', 'mic', 'mic-off', 'minimize', 'paperclip', 'pause', 'play', 'plus',
    'refresh', 'rotate-ccw', 'send', 'share', 'square', 'trash', 'volume-off', 'volume-up',
]));

export function flowUIGlyph(name, size = 16, platformUiOrigin = '') {
    if (!GLYPHS.has(name)) throw new Error(`flow-ui: unknown glyph ${JSON.stringify(name)}`);
    if (!Number.isFinite(size) || size <= 0) throw new Error(`flow-ui: invalid glyph size ${String(size)}`);
    const src = platformStaticSrc(platformUiOrigin, `/static/core/assets/icons/${name}.svg`);
    return html`<img class="fu-glyph" src=${src} width=${size} height=${size} alt="" aria-hidden="true">`;
}

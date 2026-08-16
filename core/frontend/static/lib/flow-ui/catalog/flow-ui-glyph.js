/**
 * Presentational glyph for Flow UI surfaces (including production iframe).
 * Must not use platform-icon / EventBus — iframe has no PlatformApp bootstrap.
 */
import { html } from '../../lit-shim.js';
import { platformStaticSrc } from '../shell/brand-logo.js';
import { resolveFlowUIGlyphFile } from './flow-ui-glyph-resolve.js';

export { resolveFlowUIGlyphFile, FLOW_UI_GLYPH_FILES } from './flow-ui-glyph-resolve.js';

/**
 * @param {string} name
 * @param {number} [size]
 * @param {string} [platformUiOrigin]
 */
export function flowUIGlyph(name, size = 16, platformUiOrigin = '') {
    const file = resolveFlowUIGlyphFile(name);
    if (!Number.isFinite(size) || size <= 0) {
        throw new Error(`flow-ui: invalid glyph size ${String(size)}`);
    }
    const src = platformStaticSrc(platformUiOrigin, `/static/core/assets/icons/${file}.svg`);
    return html`<img
        class="flow-ui-glyph"
        src=${src}
        width=${size}
        height=${size}
        alt=""
        aria-hidden="true"
    >`;
}

/**
 * Resolve Flow UI icon asset basename (no DOM / Lit).
 * Aliases map first; otherwise kebab-case under /static/core/assets/icons/.
 */

/** Chrome glyphs with alias → asset basename. */
export const FLOW_UI_GLYPH_FILES = Object.freeze({
    file: 'file-text',
    x: 'close',
    plus: 'plus',
    send: 'send',
    copy: 'copy',
    check: 'check',
    'rotate-ccw': 'rotate-ccw',
    'arrow-down': 'arrow-down',
    chart: 'chart',
});

const ICON_BASENAME_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

/**
 * @param {string} name
 * @returns {string}
 */
export function resolveFlowUIGlyphFile(name) {
    if (typeof name !== 'string' || name.trim() === '') {
        throw new Error('flow-ui: glyph name required');
    }
    const trimmed = name.trim();
    const aliased = FLOW_UI_GLYPH_FILES[trimmed];
    if (aliased) return aliased;
    if (!ICON_BASENAME_RE.test(trimmed)) {
        throw new Error(`flow-ui: invalid glyph name ${JSON.stringify(name)}`);
    }
    return trimmed;
}

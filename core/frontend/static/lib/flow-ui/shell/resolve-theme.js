/**
 * Resolve Flow UI theme from explicit override or platform html[data-theme].
 */

/**
 * @param {string | null | undefined} theme
 * @param {Document | null | undefined} [doc]
 * @returns {'light' | 'dark'}
 */
export function resolveFlowUITheme(theme, doc = typeof document !== 'undefined' ? document : null) {
    if (theme === 'light' || theme === 'dark') {
        return theme;
    }
    if (theme != null && theme !== '' && theme !== 'auto') {
        throw new Error(`flow-ui: unsupported theme ${JSON.stringify(theme)}`);
    }
    const fromDom = doc?.documentElement?.getAttribute('data-theme');
    if (fromDom === 'light' || fromDom === 'dark') {
        return fromDom;
    }
    return 'dark';
}

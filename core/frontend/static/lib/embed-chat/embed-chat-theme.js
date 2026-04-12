/**
 * @param {'light' | 'dark' | 'auto' | ''} theme
 * @returns {'light' | 'dark'}
 */
export function resolveEmbedChatTheme(theme) {
    const t = theme && String(theme).trim().toLowerCase();
    if (t === 'light' || t === 'dark') {
        return t;
    }
    return document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

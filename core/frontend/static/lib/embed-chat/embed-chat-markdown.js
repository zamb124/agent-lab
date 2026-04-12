/**
 * Ответы ассистента в embed-чате: GFM через globalThis.marked.
 * Хост (CRM, flows) подключает /static/core/assets/js/marked.min.js до виджета.
 */

export function escapeHtmlBeforeMarkdown(src) {
    if (src == null || src === '') {
        return '';
    }
    return String(src)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * @param {string} markdownText
 * @returns {string} HTML-фрагмент
 */
export function embedAssistantMarkdownToHtml(markdownText) {
    const escaped = escapeHtmlBeforeMarkdown(markdownText);
    if (!escaped) {
        return '';
    }
    const marked = globalThis.marked;
    if (marked && typeof marked.parse === 'function') {
        return marked.parse(escaped, { breaks: true, gfm: true });
    }
    return escaped.replace(/\n/g, '<br>');
}

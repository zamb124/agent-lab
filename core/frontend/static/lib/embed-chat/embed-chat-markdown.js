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

function applyInlineMarkdown(escapedText) {
    return escapedText
        .replace(
            /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
            '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
        )
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.+?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function fallbackMarkdownToHtml(escapedMarkdown) {
    const lines = escapedMarkdown.split('\n');
    const htmlParts = [];
    let paragraphLines = [];
    let listItems = [];

    const flushParagraph = () => {
        if (paragraphLines.length === 0) {
            return;
        }
        const text = paragraphLines.join('<br>');
        htmlParts.push(`<p>${applyInlineMarkdown(text)}</p>`);
        paragraphLines = [];
    };

    const flushList = () => {
        if (listItems.length === 0) {
            return;
        }
        htmlParts.push(`<ul>${listItems.map((item) => `<li>${applyInlineMarkdown(item)}</li>`).join('')}</ul>`);
        listItems = [];
    };

    for (const rawLine of lines) {
        const line = rawLine.trimEnd();
        const listMatch = line.match(/^\s*[-*]\s+(.+)$/);
        if (listMatch) {
            flushParagraph();
            listItems.push(listMatch[1]);
            continue;
        }
        if (line.trim() === '') {
            flushParagraph();
            flushList();
            continue;
        }
        flushList();
        paragraphLines.push(line);
    }

    flushParagraph();
    flushList();

    return htmlParts.join('');
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
    return fallbackMarkdownToHtml(escaped);
}

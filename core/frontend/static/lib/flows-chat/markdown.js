/**
 * Ответы ассистента flows-chat: полный GFM через `globalThis.marked` (скрипт `/static/core/assets/js/marked.min.js`).
 * Без `marked` — построчный fallback после `escapeHtmlAngleAndAmp` (экранированы только `&` и `<`): ATX-заголовки, hr, blockquote, ul/ol, GFM-таблицы, абзацы и базовый inline.
 * Во время A2A-стрима (`flowsChatMarkdownToHtml(..., { streaming: true })`) используется только этот
 * fallback без тяжёлого `marked.parse`; после завершения стрима вызывать с `streaming: false` для полного GFM.
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
 * Экранирование для построчного fallback: `&` и `<` (без `>`, чтобы работали blockquote `>`).
 *
 * @param {string|null|undefined} src
 * @returns {string}
 */
export function escapeHtmlAngleAndAmp(src) {
    if (src == null || src === '') {
        return '';
    }
    return String(src).replace(/&/g, '&amp;').replace(/</g, '&lt;');
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

function isMarkdownTableSeparatorLine(line) {
    const t = line.trim();
    if (!t.includes('|') || !/-/.test(t)) {
        return false;
    }
    let inner = t;
    if (inner.startsWith('|')) {
        inner = inner.slice(1);
    }
    if (inner.endsWith('|')) {
        inner = inner.slice(0, -1);
    }
    const cells = inner.split('|').map((c) => c.trim());
    if (cells.length === 0) {
        return false;
    }
    return cells.every((c) => /^:?-{3,}:?$/.test(c));
}

function splitGfmTableRow(line) {
    let t = line.trim();
    if (t.startsWith('|')) {
        t = t.slice(1);
    }
    if (t.endsWith('|')) {
        t = t.slice(0, -1);
    }
    return t.split('|').map((c) => c.trim());
}

function tableBlockToHtml(lines) {
    if (lines.length < 2) {
        return null;
    }
    if (!isMarkdownTableSeparatorLine(lines[1])) {
        return null;
    }
    const headerCells = splitGfmTableRow(lines[0]);
    if (headerCells.length === 0) {
        return null;
    }
    const bodyLines = lines.slice(2);
    const thead = `<thead><tr>${headerCells.map((c) => `<th>${applyInlineMarkdown(c)}</th>`).join('')}</tr></thead>`;
    const tbodyRows = bodyLines.map((bl) => {
        const cells = splitGfmTableRow(bl);
        if (cells.length === 0) {
            return '';
        }
        const padded = [...cells];
        while (padded.length < headerCells.length) {
            padded.push('');
        }
        return `<tr>${padded
            .slice(0, headerCells.length)
            .map((c) => `<td>${applyInlineMarkdown(c)}</td>`)
            .join('')}</tr>`;
    });
    const tbody = `<tbody>${tbodyRows.join('')}</tbody>`;
    return `<table>${thead}${tbody}</table>`;
}

/**
 * Построчный fallback без marked (GFM-подмножество).
 *
 * @param {string} escapedMarkdown — уже экранированный HTML
 * @returns {string} HTML-фрагмент
 */
export function fallbackMarkdownToHtml(escapedMarkdown) {
    const lines = escapedMarkdown.split('\n');
    const htmlParts = [];
    let paragraphLines = [];
    let unorderedItems = [];
    let orderedItems = [];
    let blockquoteLines = [];
    let tableAcc = [];

    const flushParagraph = () => {
        if (paragraphLines.length === 0) {
            return;
        }
        const text = paragraphLines.join('<br>');
        htmlParts.push(`<p>${applyInlineMarkdown(text)}</p>`);
        paragraphLines = [];
    };

    const flushUnordered = () => {
        if (unorderedItems.length === 0) {
            return;
        }
        htmlParts.push(
            `<ul>${unorderedItems.map((item) => `<li>${applyInlineMarkdown(item)}</li>`).join('')}</ul>`,
        );
        unorderedItems = [];
    };

    const flushOrdered = () => {
        if (orderedItems.length === 0) {
            return;
        }
        htmlParts.push(
            `<ol>${orderedItems.map((item) => `<li>${applyInlineMarkdown(item)}</li>`).join('')}</ol>`,
        );
        orderedItems = [];
    };

    const flushLists = () => {
        flushUnordered();
        flushOrdered();
    };

    const flushBlockquote = () => {
        if (blockquoteLines.length === 0) {
            return;
        }
        const inner = blockquoteLines.map((ln) => applyInlineMarkdown(ln)).join('<br>');
        htmlParts.push(`<blockquote>${inner}</blockquote>`);
        blockquoteLines = [];
    };

    const flushTable = () => {
        if (tableAcc.length === 0) {
            return;
        }
        const html = tableBlockToHtml(tableAcc);
        if (html) {
            htmlParts.push(html);
        } else {
            for (const lost of tableAcc) {
                paragraphLines.push(lost);
            }
            flushParagraph();
        }
        tableAcc = [];
    };

    const flushAllBlocks = () => {
        flushTable();
        flushBlockquote();
        flushLists();
        flushParagraph();
    };

    const rowLooksLikeGfmTable = (trimmed) => trimmed.length > 0 && trimmed.includes('|');

    for (let i = 0; i < lines.length; i++) {
        const rawLine = lines[i];
        const line = rawLine.trimEnd();
        const trimmed = line.trim();

        if (tableAcc.length > 0) {
            if (trimmed === '') {
                flushTable();
                continue;
            }
            if (rowLooksLikeGfmTable(trimmed) || isMarkdownTableSeparatorLine(trimmed)) {
                tableAcc.push(line);
                continue;
            }
            flushTable();
        }

        const hrMatch = trimmed.match(/^([-*_])(\1\1+)$/);
        if (trimmed.length > 0 && hrMatch) {
            flushAllBlocks();
            htmlParts.push('<hr>');
            continue;
        }

        const hdrMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
        if (hdrMatch) {
            flushAllBlocks();
            const level = hdrMatch[1].length;
            const title = applyInlineMarkdown(hdrMatch[2].trim());
            htmlParts.push(`<h${level}>${title}</h${level}>`);
            continue;
        }

        const bqMatch = line.match(/^\s*>\s?(.*)$/);
        if (bqMatch && trimmed.startsWith('>')) {
            flushLists();
            flushParagraph();
            flushTable();
            blockquoteLines.push(bqMatch[1]);
            continue;
        }
        flushBlockquote();

        const ulMatch = line.match(/^\s*[-*]\s+(.+)$/);
        if (ulMatch) {
            flushParagraph();
            flushOrdered();
            unorderedItems.push(ulMatch[1]);
            continue;
        }

        const olMatch = line.match(/^\s*\d+\.\s+(.+)$/);
        if (olMatch) {
            flushParagraph();
            flushUnordered();
            orderedItems.push(olMatch[1]);
            continue;
        }

        if (trimmed === '') {
            flushAllBlocks();
            continue;
        }

        const nextTrimmed = i + 1 < lines.length ? lines[i + 1].trim() : '';
        if (
            rowLooksLikeGfmTable(trimmed) &&
            isMarkdownTableSeparatorLine(nextTrimmed) &&
            paragraphLines.length === 0 &&
            unorderedItems.length === 0 &&
            orderedItems.length === 0 &&
            blockquoteLines.length === 0
        ) {
            flushBlockquote();
            tableAcc.push(line);
            i += 1;
            if (i < lines.length) {
                tableAcc.push(lines[i].trimEnd());
            }
            continue;
        }

        flushLists();
        paragraphLines.push(line);
    }

    flushAllBlocks();

    return htmlParts.join('');
}

/**
 * @param {string} markdownText
 * @param {{ streaming?: boolean }} [opts] — при `streaming: true` только лёгкий построчный fallback (быстрые чанки A2A); полный GFM через `marked` после завершения стрима.
 * @returns {string} HTML-фрагмент
 */
export function flowsChatMarkdownToHtml(markdownText, opts) {
    if (markdownText == null || markdownText === '') {
        return '';
    }
    const text = String(markdownText);
    const streaming = opts && opts.streaming === true;
    if (streaming) {
        return fallbackMarkdownToHtml(escapeHtmlAngleAndAmp(text));
    }
    const marked = globalThis.marked;
    if (marked && typeof marked.parse === 'function') {
        try {
            return marked.parse(escapeHtmlBeforeMarkdown(text), { breaks: true, gfm: true });
        } catch {
            return fallbackMarkdownToHtml(escapeHtmlAngleAndAmp(text));
        }
    }
    return fallbackMarkdownToHtml(escapeHtmlAngleAndAmp(text));
}

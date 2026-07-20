/**
 * Markdown ↔ HTML helpers for platform-markdown-editor.
 * sanitize — whitelist for WYSIWYG; htmlToMarkdown — subset roundtrip.
 */
export const MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;

const ALLOWED_TAGS = new Set([
    'P', 'BR', 'STRONG', 'B', 'EM', 'I', 'U', 'S', 'STRIKE',
    'UL', 'OL', 'LI', 'BLOCKQUOTE', 'A', 'DIV', 'SPAN', 'H1', 'H2', 'H3', 'H4',
]);

/**
 * @param {string} rawHtml
 * @returns {string}
 */
export function sanitizeMarkdownEditorHtml(rawHtml) {
    if (typeof rawHtml !== 'string' || rawHtml.length === 0) {
        return '';
    }
    const template = document.createElement('template');
    template.innerHTML = rawHtml;
    const walk = (node) => {
        const children = Array.from(node.childNodes);
        for (const child of children) {
            if (child.nodeType === Node.TEXT_NODE) {
                continue;
            }
            if (child.nodeType !== Node.ELEMENT_NODE) {
                child.remove();
                continue;
            }
            const el = /** @type {HTMLElement} */ (child);
            if (!ALLOWED_TAGS.has(el.tagName)) {
                const parent = el.parentNode;
                if (!parent) {
                    el.remove();
                    continue;
                }
                while (el.firstChild) {
                    parent.insertBefore(el.firstChild, el);
                }
                el.remove();
                continue;
            }
            if (el.tagName === 'A') {
                const href = el.getAttribute('href');
                for (const attr of Array.from(el.attributes)) {
                    el.removeAttribute(attr.name);
                }
                if (
                    typeof href === 'string'
                    && (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:'))
                ) {
                    el.setAttribute('href', href);
                }
            } else {
                for (const attr of Array.from(el.attributes)) {
                    el.removeAttribute(attr.name);
                }
            }
            walk(el);
        }
    };
    walk(template.content);
    return template.innerHTML;
}

/**
 * @param {Node} node
 * @returns {string}
 */
function _nodeToMarkdown(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent || '';
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
        return '';
    }
    const el = /** @type {HTMLElement} */ (node);
    const tag = el.tagName;
    const inner = Array.from(el.childNodes).map((child) => _nodeToMarkdown(child)).join('');
    if (tag === 'BR') {
        return '\n';
    }
    if (tag === 'STRONG' || tag === 'B') {
        return `**${inner}**`;
    }
    if (tag === 'EM' || tag === 'I') {
        return `*${inner}*`;
    }
    if (tag === 'S' || tag === 'STRIKE') {
        return `~~${inner}~~`;
    }
    if (tag === 'U') {
        return inner;
    }
    if (tag === 'A') {
        const href = el.getAttribute('href');
        if (typeof href === 'string' && href.length > 0) {
            return `[${inner}](${href})`;
        }
        return inner;
    }
    if (tag === 'H1') {
        return `# ${inner.trim()}\n\n`;
    }
    if (tag === 'H2') {
        return `## ${inner.trim()}\n\n`;
    }
    if (tag === 'H3') {
        return `### ${inner.trim()}\n\n`;
    }
    if (tag === 'H4') {
        return `#### ${inner.trim()}\n\n`;
    }
    if (tag === 'BLOCKQUOTE') {
        return inner
            .split('\n')
            .map((line) => `> ${line}`)
            .join('\n') + '\n\n';
    }
    if (tag === 'LI') {
        return `- ${inner.trim()}\n`;
    }
    if (tag === 'UL' || tag === 'OL') {
        return `${inner}\n`;
    }
    if (tag === 'P' || tag === 'DIV') {
        const trimmed = inner.trim();
        return trimmed.length > 0 ? `${trimmed}\n\n` : '';
    }
    if (tag === 'SPAN') {
        return inner;
    }
    return inner;
}

/**
 * @param {string} rawHtml
 * @returns {string}
 */
export function htmlToMarkdown(rawHtml) {
    const sanitized = sanitizeMarkdownEditorHtml(typeof rawHtml === 'string' ? rawHtml : '');
    if (sanitized.length === 0) {
        return '';
    }
    const template = document.createElement('template');
    template.innerHTML = sanitized;
    const md = Array.from(template.content.childNodes).map((node) => _nodeToMarkdown(node)).join('');
    return md.replace(/\n{3,}/g, '\n\n').trim();
}

/**
 * Plain text from HTML (for textValue).
 * @param {string} rawHtml
 * @returns {string}
 */
export function htmlToPlainText(rawHtml) {
    const sanitized = sanitizeMarkdownEditorHtml(typeof rawHtml === 'string' ? rawHtml : '');
    if (sanitized.length === 0) {
        return '';
    }
    const tmp = document.createElement('div');
    tmp.innerHTML = sanitized;
    return tmp.innerText || '';
}

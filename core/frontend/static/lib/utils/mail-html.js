/**
 * Безопасный рендер HTML-письма: CID, remote images, wrap+CSP.
 * Санитайзер (DOMPurify) — только в браузере.
 */
import DOMPurify from '../../assets/js/dompurify/purify.es.mjs';
import { escapeHtml } from './escape-html.js';

const CID_ATTR_RE = /(?:src|href|background)\s*=\s*['"]cid:([^'"]+)['"]/gi;
const CID_CSS_RE = /url\(\s*['"]?cid:([^'")\s]+)['"]?\s*\)/gi;
const CID_BARE_RE = /cid:([^'"\s)>]+)/gi;

const FORBID_TAGS = Object.freeze([
    'script',
    'iframe',
    'object',
    'embed',
    'form',
    'input',
    'button',
    'textarea',
    'select',
    'base',
    'link',
    'meta',
    'svg',
    'math',
    'video',
    'audio',
    'source',
    'track',
]);

const ADD_ATTR = Object.freeze([
    'style',
    'class',
    'id',
    'align',
    'valign',
    'bgcolor',
    'background',
    'width',
    'height',
    'border',
    'cellpadding',
    'cellspacing',
    'colspan',
    'rowspan',
    'role',
    'color',
    'face',
    'size',
    'noshade',
    'nowrap',
]);

const QUOTE_SELECTORS = Object.freeze([
    '.gmail_quote',
    'blockquote[type="cite"]',
    '#divRplyFwdMsg',
    '.yahoo_quoted',
]);

const MAIL_BODY_CSS = [
    'html,body{margin:0;padding:0;background:#ffffff;color:#222222;}',
    'img{max-width:100%;height:auto;}',
    'table{max-width:100%;}',
    'a{color:#1155cc;}',
    'details.mail-quote{margin:12px 0;border-left:2px solid #c5c5c5;padding-left:8px;color:#666666;}',
    'details.mail-quote>summary{cursor:pointer;color:#888888;font-size:13px;list-style:none;}',
].join('');

/**
 * @param {string} raw
 * @returns {string}
 */
export function normalizeContentId(raw) {
    if (typeof raw !== 'string' || !raw.trim()) {
        throw new Error('normalizeContentId: non-empty string required');
    }
    let value = raw.trim();
    if (value.toLowerCase().startsWith('cid:')) {
        value = value.slice(4);
    }
    if (value.startsWith('<') && value.endsWith('>')) {
        value = value.slice(1, -1).trim();
    }
    if (!value) {
        throw new Error('normalizeContentId: empty after normalize');
    }
    return value.toLowerCase();
}

/**
 * @param {string} html
 * @returns {Set<string>}
 */
export function findCidRefs(html) {
    if (typeof html !== 'string') {
        throw new Error('findCidRefs: html string required');
    }
    const ids = new Set();
    for (const re of [CID_ATTR_RE, CID_CSS_RE]) {
        re.lastIndex = 0;
        let match = re.exec(html);
        while (match) {
            ids.add(normalizeContentId(`cid:${match[1]}`));
            match = re.exec(html);
        }
    }
    return ids;
}

/**
 * @param {string} html
 * @returns {boolean}
 */
export function hasRemoteImages(html) {
    if (typeof html !== 'string') {
        throw new Error('hasRemoteImages: html string required');
    }
    if (/(?:src|background)\s*=\s*['"]https?:\/\//i.test(html)) {
        return true;
    }
    return /url\(\s*['"]?https?:\/\//i.test(html);
}

/**
 * @param {string} html
 * @param {Record<string, string>} cidMap
 * @returns {string}
 */
export function rewriteCidImages(html, cidMap) {
    if (typeof html !== 'string') {
        throw new Error('rewriteCidImages: html string required');
    }
    if (cidMap === null || typeof cidMap !== 'object' || Array.isArray(cidMap)) {
        throw new Error('rewriteCidImages: cidMap object required');
    }
    CID_BARE_RE.lastIndex = 0;
    return html.replace(CID_BARE_RE, (full, rawId) => {
        const id = normalizeContentId(`cid:${rawId}`);
        const dataUrl = Object.prototype.hasOwnProperty.call(cidMap, id)
            ? cidMap[id]
            : null;
        if (typeof dataUrl !== 'string' || !dataUrl.startsWith('data:')) {
            return full;
        }
        return dataUrl;
    });
}

/**
 * @param {unknown[]} attachments
 * @param {string} html
 * @returns {Record<string, string>}
 */
export function buildCidFileMap(attachments, html) {
    if (!Array.isArray(attachments)) {
        throw new Error('buildCidFileMap: attachments array required');
    }
    if (typeof html !== 'string') {
        throw new Error('buildCidFileMap: html string required');
    }
    const refs = findCidRefs(html);
    /** @type {Record<string, string>} */
    const out = {};
    if (refs.size === 0) {
        return out;
    }
    for (const att of attachments) {
        if (!att || typeof att !== 'object') {
            throw new Error('buildCidFileMap: attachment object required');
        }
        const record = /** @type {{ content_id?: unknown, file_id?: unknown }} */ (att);
        if (typeof record.content_id !== 'string' || !record.content_id.trim()) {
            continue;
        }
        const id = normalizeContentId(record.content_id);
        if (!refs.has(id)) {
            continue;
        }
        if (typeof record.file_id !== 'string' || !record.file_id.trim()) {
            continue;
        }
        out[id] = record.file_id;
    }
    return out;
}

/**
 * @param {unknown[]} attachments
 * @param {string} html
 * @returns {unknown[]}
 */
export function attachmentsWithoutInlineCid(attachments, html) {
    if (!Array.isArray(attachments)) {
        throw new Error('attachmentsWithoutInlineCid: attachments array required');
    }
    if (typeof html !== 'string') {
        throw new Error('attachmentsWithoutInlineCid: html string required');
    }
    const refs = findCidRefs(html);
    if (refs.size === 0) {
        return attachments;
    }
    return attachments.filter((att) => {
        if (!att || typeof att !== 'object') {
            throw new Error('attachmentsWithoutInlineCid: attachment object required');
        }
        const record = /** @type {{ content_id?: unknown }} */ (att);
        if (typeof record.content_id !== 'string' || !record.content_id.trim()) {
            return true;
        }
        return !refs.has(normalizeContentId(record.content_id));
    });
}

/**
 * @param {string} text
 * @returns {string}
 */
export function autolinkPlaintext(text) {
    if (typeof text !== 'string') {
        throw new Error('autolinkPlaintext: text string required');
    }
    const escaped = escapeHtml(text);
    return escaped.replace(
        /(https?:\/\/[^\s<&]+)/g,
        '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>',
    );
}

/**
 * @param {boolean} allowRemoteImages
 * @returns {string}
 */
export function mailDocumentCsp(allowRemoteImages) {
    if (typeof allowRemoteImages !== 'boolean') {
        throw new Error('mailDocumentCsp: allowRemoteImages boolean required');
    }
    const imgSrc = allowRemoteImages ? "img-src data: https: http:" : 'img-src data:';
    return [
        "default-src 'none'",
        "script-src 'none'",
        "style-src 'unsafe-inline'",
        imgSrc,
        "font-src 'none'",
        "media-src 'none'",
        "object-src 'none'",
        "frame-src 'none'",
        "base-uri 'none'",
        "form-action 'none'",
    ].join('; ');
}

/**
 * @returns {string}
 */
export function mailIframeSandbox() {
    const ua = typeof navigator === 'object' && navigator && typeof navigator.userAgent === 'string'
        ? navigator.userAgent
        : '';
    const isWebKit = /AppleWebKit/i.test(ua) && !/Chrome|Chromium|Edg\//i.test(ua);
    if (isWebKit) {
        return 'allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts';
    }
    return 'allow-popups allow-popups-to-escape-sandbox allow-same-origin';
}

/**
 * @param {Document} doc
 */
function wrapQuotedRegions(doc) {
    const seen = new Set();
    for (const selector of QUOTE_SELECTORS) {
        const nodes = [...doc.querySelectorAll(selector)];
        for (const node of nodes) {
            if (!(node instanceof HTMLElement)) {
                continue;
            }
            if (seen.has(node) || node.closest('details.mail-quote')) {
                continue;
            }
            const parent = node.parentNode;
            if (!parent) {
                continue;
            }
            const details = doc.createElement('details');
            details.className = 'mail-quote';
            const summary = doc.createElement('summary');
            summary.textContent = '\u2026';
            parent.insertBefore(details, node);
            details.appendChild(summary);
            details.appendChild(node);
            seen.add(node);
        }
    }
}

/**
 * @param {string} cleanHtml
 * @param {boolean} allowRemoteImages
 * @returns {string}
 */
export function wrapMailDocument(cleanHtml, allowRemoteImages) {
    if (typeof cleanHtml !== 'string') {
        throw new Error('wrapMailDocument: cleanHtml string required');
    }
    if (typeof allowRemoteImages !== 'boolean') {
        throw new Error('wrapMailDocument: allowRemoteImages boolean required');
    }
    if (typeof DOMParser !== 'function') {
        throw new Error('wrapMailDocument: DOMParser required');
    }
    const parser = new DOMParser();
    const doc = parser.parseFromString(cleanHtml, 'text/html');
    wrapQuotedRegions(doc);
    let head = doc.head;
    if (!head) {
        head = doc.createElement('head');
        doc.documentElement.insertBefore(head, doc.body);
    }
    for (const meta of [...head.querySelectorAll('meta')]) {
        meta.remove();
    }
    const charset = doc.createElement('meta');
    charset.setAttribute('charset', 'utf-8');
    const csp = doc.createElement('meta');
    csp.setAttribute('http-equiv', 'Content-Security-Policy');
    csp.setAttribute('content', mailDocumentCsp(allowRemoteImages));
    const style = doc.createElement('style');
    style.textContent = MAIL_BODY_CSS;
    head.insertBefore(style, head.firstChild);
    head.insertBefore(csp, head.firstChild);
    head.insertBefore(charset, head.firstChild);
    if (doc.body) {
        doc.body.style.background = '#ffffff';
        doc.body.style.color = '#222222';
    }
    return `<!doctype html>${doc.documentElement.outerHTML}`;
}

/**
 * @param {string} rawHtml
 * @param {{ allowRemoteImages: boolean, cidMap: Record<string, string> }} options
 * @returns {string}
 */
export function sanitizeMailHtml(rawHtml, options) {
    if (typeof rawHtml !== 'string') {
        throw new Error('sanitizeMailHtml: rawHtml string required');
    }
    if (!options || typeof options !== 'object') {
        throw new Error('sanitizeMailHtml: options required');
    }
    const allowRemoteImages = options.allowRemoteImages;
    if (typeof allowRemoteImages !== 'boolean') {
        throw new Error('sanitizeMailHtml: allowRemoteImages boolean required');
    }
    const cidMap = options.cidMap;
    if (cidMap === null || typeof cidMap !== 'object' || Array.isArray(cidMap)) {
        throw new Error('sanitizeMailHtml: cidMap object required');
    }
    if (typeof DOMPurify.sanitize !== 'function') {
        throw new Error('sanitizeMailHtml: DOMPurify.sanitize missing');
    }
    const rewritten = rewriteCidImages(rawHtml, cidMap);
    const afterSanitize = (node) => {
        if (!(node instanceof Element)) {
            return;
        }
        if (node.tagName === 'A') {
            const href = node.getAttribute('href');
            node.removeAttribute('href');
            if (
                typeof href === 'string'
                && (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('mailto:'))
            ) {
                node.setAttribute('href', href);
            }
            node.setAttribute('target', '_blank');
            node.setAttribute('rel', 'noopener noreferrer');
        }
        if (!allowRemoteImages) {
            const src = node.getAttribute('src');
            if (typeof src === 'string' && /^https?:\/\//i.test(src)) {
                node.removeAttribute('src');
            }
            const background = node.getAttribute('background');
            if (typeof background === 'string' && /^https?:\/\//i.test(background)) {
                node.removeAttribute('background');
            }
        }
    };
    DOMPurify.addHook('afterSanitizeAttributes', afterSanitize);
    let clean;
    try {
        clean = DOMPurify.sanitize(rewritten, {
            WHOLE_DOCUMENT: true,
            ADD_TAGS: ['style'],
            ADD_ATTR: [...ADD_ATTR],
            FORBID_TAGS: [...FORBID_TAGS],
            ALLOW_DATA_ATTR: false,
            ALLOW_UNKNOWN_PROTOCOLS: false,
        });
    } finally {
        DOMPurify.removeHook('afterSanitizeAttributes', afterSanitize);
    }
    if (typeof clean !== 'string') {
        throw new Error('sanitizeMailHtml: DOMPurify returned non-string');
    }
    return wrapMailDocument(clean, allowRemoteImages);
}

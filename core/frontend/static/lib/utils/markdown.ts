/**
 * Единственный markdown → HTML рендерер платформы (GFM, ``breaks``): ответы ассистента,
 * блок ``text`` Flow UI, заметки CRM, предпросмотр markdown-редактора, документация code node.
 *
 * Результат безопасен для ``unsafeHTML`` без отдельного sanitizer:
 * - сырой HTML в markdown экранируется и показывается как текст;
 * - ссылки и картинки — только ``http(s)``/``mailto``, ссылки открываются в новой вкладке.
 */

import { Marked } from '../../assets/js/marked/marked.esm.min.js';

import { escapeHtml } from './escape-html.js';

const SAFE_URL_PATTERN = /^(https?:\/\/|mailto:)/i;

interface MarkedToken { raw: string; type?: string }
interface MarkedInlineArgs { text: string; tokens?: MarkedToken[] }
interface MarkedLinkArgs { href: string; title?: string | null; tokens: MarkedToken[] }
interface MarkedImageArgs { href: string; title?: string | null; text: string }

const renderer = {
    html({ text }: MarkedInlineArgs): string {
        return escapeHtml(text);
    },
    link(this: { parser: { parseInline(t: MarkedToken[]): string } }, { href, title, tokens }: MarkedLinkArgs): string {
        const label = this.parser.parseInline(tokens);
        if (!SAFE_URL_PATTERN.test(href)) return label;
        const titleAttribute = title ? ` title="${escapeHtml(title)}"` : '';
        return `<a href="${escapeHtml(href)}"${titleAttribute} target="_blank" rel="noopener noreferrer">${label}</a>`;
    },
    image({ href, title, text }: MarkedImageArgs): string {
        if (!SAFE_URL_PATTERN.test(href)) return escapeHtml(text);
        const titleAttribute = title ? ` title="${escapeHtml(title)}"` : '';
        return `<img src="${escapeHtml(href)}" alt="${escapeHtml(text)}"${titleAttribute}>`;
    },
};

const marked = new Marked({ gfm: true, breaks: true, async: false, renderer });

/**
 * @param {string} markdown
 * @returns {string} HTML-фрагмент
 */
export function markdownToHtml(markdown: string): string {
    if (typeof markdown !== 'string') {
        throw new TypeError('markdownToHtml: markdown must be a string');
    }
    if (markdown === '') return '';
    return marked.parse(markdown) as string;
}

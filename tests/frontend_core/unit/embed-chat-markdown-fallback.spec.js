/**
 * Построчный fallback Markdown для embed-чата (без globalThis.marked).
 */

import { describe, it, expect } from 'vitest';
import {
    escapeHtmlAngleAndAmp,
    fallbackMarkdownToHtml,
    embedAssistantMarkdownToHtml,
} from '@platform/lib/embed-chat/embed-chat-markdown.js';

function fallbackFromRaw(md) {
    return fallbackMarkdownToHtml(escapeHtmlAngleAndAmp(md));
}

describe('embed-chat-markdown fallback', () => {
    it('ATX-заголовок и горизонтальная черта', () => {
        const html = fallbackFromRaw('## Резюме\n\n---\n\nтекст');
        expect(html).to.include('<h2>');
        expect(html).to.include('Резюме');
        expect(html).to.include('<hr>');
        expect(html).to.include('<p>');
        expect(html).to.not.include('##');
        expect(html).to.not.include('---');
    });

    it('GFM-таблица', () => {
        const md = '| A | B |\n| --- | --- |\n| 1 | 2 |';
        const html = fallbackFromRaw(md);
        expect(html).to.include('<table>');
        expect(html).to.include('<thead>');
        expect(html).to.include('<th>');
        expect(html).to.include('A');
        expect(html).to.include('<td>');
        expect(html).to.include('1');
        expect(html).to.not.include('| A |');
    });

    it('нумерованный и маркированный список', () => {
        const html = fallbackFromRaw('1. первый\n2. второй\n\n- маркер');
        expect(html).to.include('<ol>');
        expect(html).to.include('<ul>');
        expect(html).to.include('первый');
        expect(html).to.include('маркер');
    });

    it('blockquote', () => {
        const html = fallbackFromRaw('> цитируем');
        expect(html).to.include('<blockquote>');
        expect(html).to.include('цитируем');
        expect(html).to.not.include('&gt;');
    });

    it('embedAssistantMarkdownToHtml в режиме streaming не вызывает marked.parse', () => {
        const saved = globalThis.marked;
        let parseCalls = 0;
        globalThis.marked = {
            parse() {
                parseCalls += 1;
                return '<p>marked</p>';
            },
        };
        try {
            const html = embedAssistantMarkdownToHtml('## Часть\n\ntекст', { streaming: true });
            expect(parseCalls).toBe(0);
            expect(html).to.include('<h2>');
            expect(html).to.include('Часть');
            expect(html).to.not.include('marked');
        } finally {
            globalThis.marked = saved;
        }
    });
});

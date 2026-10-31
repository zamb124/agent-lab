/**
 * Единственный markdown → HTML рендерер платформы: GFM с ``breaks`` и результат,
 * безопасный для ``unsafeHTML`` без отдельного sanitizer.
 */

import { describe, expect, it } from 'vitest';

import { markdownToHtml } from '@platform/lib/utils/markdown.js';

describe('markdownToHtml: input contract', () => {
    it('accepts only strings and renders the empty string as nothing', () => {
        expect(markdownToHtml('')).toBe('');
        for (const value of [undefined, null, 5, {}, [], true]) {
            expect(() => markdownToHtml(value)).toThrow(TypeError);
        }
    });
});

describe('markdownToHtml: GFM', () => {
    it('renders headings, soft line breaks, emphasis, strikethrough and task lists', () => {
        expect(markdownToHtml('# H1\ntext')).toBe('<h1>H1</h1>\n<p>text</p>\n');
        expect(markdownToHtml('a\nb')).toBe('<p>a<br>b</p>\n');
        expect(markdownToHtml('**b** _i_ ~~s~~')).toBe('<p><strong>b</strong> <em>i</em> <del>s</del></p>\n');
        expect(markdownToHtml('- [ ] todo\n- [x] done')).toContain('<input checked="" disabled="" type="checkbox"> done');
    });

    it('renders tables and fenced code with escaped contents', () => {
        const table = markdownToHtml('| a | b |\n|---|---|\n| 1 | 2 |');
        expect(table).toContain('<table>');
        expect(table).toContain('<th>a</th>');
        expect(table).toContain('<td>2</td>');
        expect(markdownToHtml('```js\nlet a = 1 < 2;\n```')).toBe(
            '<pre><code class="language-js">let a = 1 &lt; 2;\n</code></pre>\n',
        );
        expect(markdownToHtml('`<i>`')).toBe('<p><code>&lt;i&gt;</code></p>\n');
    });
});

describe('markdownToHtml: safety', () => {
    it('escapes raw HTML blocks and inline tags instead of passing them through', () => {
        expect(markdownToHtml('<script>alert(1)</script>')).toBe('&lt;script&gt;alert(1)&lt;/script&gt;');
        expect(markdownToHtml('a <b>bold</b> c')).toBe('<p>a &lt;b&gt;bold&lt;/b&gt; c</p>\n');
        expect(markdownToHtml('<img src=x onerror=alert(1)>')).not.toContain('<img');
        expect(markdownToHtml('<a href="https://x">x</a>')).not.toContain('<a ');
    });

    it('keeps only http(s) and mailto links, opened in a new tab without opener', () => {
        expect(markdownToHtml('[t](https://e.com "Title")')).toBe(
            '<p><a href="https://e.com" title="Title" target="_blank" rel="noopener noreferrer">t</a></p>\n',
        );
        expect(markdownToHtml('[m](mailto:a@b.c)')).toContain('href="mailto:a@b.c"');
        expect(markdownToHtml('[up](HTTPS://UP.CASE)')).toContain('href="HTTPS://UP.CASE"');
        expect(markdownToHtml('<https://auto.link>')).toContain('href="https://auto.link"');
        expect(markdownToHtml('https://bare.link')).toContain('href="https://bare.link"');
        for (const unsafe of ['javascript:alert(1)', 'data:text/html,hi', '/relative', '#top', 'ftp://x', 'vbscript:x']) {
            expect(markdownToHtml(`[label](${unsafe})`), unsafe).toBe('<p>label</p>\n');
        }
        expect(markdownToHtml('[**bold**](javascript:x)')).toBe('<p><strong>bold</strong></p>\n');
    });

    it('drops images with unsafe sources and escapes alt/title attributes', () => {
        expect(markdownToHtml('![img](https://e.com/i.png "T")')).toBe(
            '<p><img src="https://e.com/i.png" alt="img" title="T"></p>\n',
        );
        expect(markdownToHtml('![img](javascript:x)')).toBe('<p>img</p>\n');
        expect(markdownToHtml('![img](data:image/png;base64,AAAA)')).toBe('<p>img</p>\n');
        expect(markdownToHtml('![a"b](https://e.com/i.png)')).toContain('alt="a&quot;b"');
        expect(markdownToHtml('[x](https://e.com/?a=1&b=2)')).toContain('href="https://e.com/?a=1&amp;b=2"');
    });
});

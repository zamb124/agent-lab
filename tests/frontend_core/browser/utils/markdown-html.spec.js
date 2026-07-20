/**
 * Strict coverage for markdown ↔ HTML helpers used by platform-markdown-editor.
 */

import { expect } from '../helpers/render.js';
import {
    sanitizeMarkdownEditorHtml,
    htmlToMarkdown,
    htmlToPlainText,
    MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES,
} from '@platform/lib/utils/markdown-html.js';

describe('markdown-html helpers', () => {
    describe('MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES', () => {
        it('is exactly 10 MiB', () => {
            expect(MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES).to.equal(10 * 1024 * 1024);
        });
    });

    describe('sanitizeMarkdownEditorHtml', () => {
        it('returns empty string for non-string and empty input', () => {
            expect(sanitizeMarkdownEditorHtml('')).to.equal('');
            expect(sanitizeMarkdownEditorHtml(/** @type {string} */ (null))).to.equal('');
            expect(sanitizeMarkdownEditorHtml(/** @type {string} */ (undefined))).to.equal('');
            expect(sanitizeMarkdownEditorHtml(/** @type {string} */ (42))).to.equal('');
        });

        it('keeps allowed tags and strips all attributes except safe A.href', () => {
            const out = sanitizeMarkdownEditorHtml(
                '<p class="x" onclick="alert(1)" style="color:red">Hi <strong id="a">bold</strong></p>',
            );
            expect(out).to.equal('<p>Hi <strong>bold</strong></p>');
        });

        it('unwraps disallowed tags and removes script/style content nodes as elements', () => {
            const out = sanitizeMarkdownEditorHtml(
                '<div>safe<script>evil()</script><b>bold</b><iframe src="x"></iframe></div>',
            );
            expect(out).to.not.include('<script');
            expect(out).to.not.include('<iframe');
            expect(out).to.include('safe');
            expect(out).to.include('<b>bold</b>');
        });

        it('allows only http(s) and mailto href on anchors', () => {
            expect(sanitizeMarkdownEditorHtml('<a href="https://ok.example">a</a>'))
                .to.equal('<a href="https://ok.example">a</a>');
            expect(sanitizeMarkdownEditorHtml('<a href="http://ok.example">a</a>'))
                .to.equal('<a href="http://ok.example">a</a>');
            expect(sanitizeMarkdownEditorHtml('<a href="mailto:a@b.c">a</a>'))
                .to.equal('<a href="mailto:a@b.c">a</a>');
            expect(sanitizeMarkdownEditorHtml('<a href="javascript:alert(1)">a</a>'))
                .to.equal('<a>a</a>');
            expect(sanitizeMarkdownEditorHtml('<a href="/relative">a</a>'))
                .to.equal('<a>a</a>');
            expect(sanitizeMarkdownEditorHtml('<a href="ftp://x">a</a>'))
                .to.equal('<a>a</a>');
        });

        it('preserves nested lists, headings, quote, br, em, strike, u, span', () => {
            const raw = [
                '<h1>H1</h1><h2>H2</h2><h3>H3</h3><h4>H4</h4>',
                '<ul><li>one</li></ul><ol><li>two</li></ol>',
                '<blockquote>q</blockquote><br><em>i</em><i>i2</i>',
                '<s>s</s><strike>st</strike><u>u</u><span>sp</span>',
            ].join('');
            const out = sanitizeMarkdownEditorHtml(raw);
            expect(out).to.include('<h1>H1</h1>');
            expect(out).to.include('<ul><li>one</li></ul>');
            expect(out).to.include('<blockquote>q</blockquote>');
            expect(out).to.include('<em>i</em>');
            expect(out).to.include('<s>s</s>');
            expect(out).to.include('<span>sp</span>');
        });
    });

    describe('htmlToMarkdown', () => {
        it('returns empty for empty / non-string', () => {
            expect(htmlToMarkdown('')).to.equal('');
            expect(htmlToMarkdown(/** @type {string} */ (null))).to.equal('');
            expect(htmlToMarkdown(/** @type {string} */ (1))).to.equal('');
        });

        it('maps bold/italic/strike/br/paragraph', () => {
            expect(htmlToMarkdown('<p><strong>a</strong> <em>b</em> <s>c</s></p><br>'))
                .to.match(/\*\*a\*\*/);
            expect(htmlToMarkdown('<p><strong>a</strong> <em>b</em> <s>c</s></p>'))
                .to.include('*b*');
            expect(htmlToMarkdown('<p><strong>a</strong> <em>b</em> <s>c</s></p>'))
                .to.include('~~c~~');
            expect(htmlToMarkdown('line<br>next')).to.equal('line\nnext');
        });

        it('maps headings, lists, blockquote, links', () => {
            expect(htmlToMarkdown('<h1>Title</h1>')).to.equal('# Title');
            expect(htmlToMarkdown('<h2>Title</h2>')).to.equal('## Title');
            expect(htmlToMarkdown('<h3>Title</h3>')).to.equal('### Title');
            expect(htmlToMarkdown('<h4>Title</h4>')).to.equal('#### Title');
            expect(htmlToMarkdown('<ul><li>one</li><li>two</li></ul>')).to.include('- one');
            expect(htmlToMarkdown('<ul><li>one</li><li>two</li></ul>')).to.include('- two');
            expect(htmlToMarkdown('<blockquote>quoted</blockquote>')).to.include('> quoted');
            expect(htmlToMarkdown('<a href="https://ex.com">label</a>'))
                .to.equal('[label](https://ex.com)');
            expect(htmlToMarkdown('<a>nolink</a>')).to.equal('nolink');
        });

        it('strips underline to plain text and collapses excess newlines', () => {
            expect(htmlToMarkdown('<u>under</u>')).to.equal('under');
            const md = htmlToMarkdown('<p>a</p><p></p><p></p><p>b</p>');
            expect(md).to.not.match(/\n{3,}/);
            expect(md).to.include('a');
            expect(md).to.include('b');
        });

        it('sanitizes before conversion (script gone, bold kept)', () => {
            const md = htmlToMarkdown('<p>ok<script>x</script><b>bold</b></p>');
            expect(md).to.include('ok');
            expect(md).to.include('**bold**');
            expect(md).to.not.include('script');
        });
    });

    describe('htmlToPlainText', () => {
        it('returns empty for empty / non-string', () => {
            expect(htmlToPlainText('')).to.equal('');
            expect(htmlToPlainText(/** @type {string} */ (false))).to.equal('');
        });

        it('strips tags and keeps visible text', () => {
            expect(htmlToPlainText('<p>Hello <strong>world</strong></p>')).to.equal('Hello world');
        });

        it('drops javascript href but keeps anchor text', () => {
            expect(htmlToPlainText('<a href="javascript:alert(1)">click</a>')).to.equal('click');
        });
    });
});

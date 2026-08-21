import { describe, it, expect } from 'vitest';
import {
    attachmentsWithoutInlineCid,
    autolinkPlaintext,
    buildCidFileMap,
    findCidRefs,
    hasRemoteImages,
    mailDocumentCsp,
    mailIframeSandbox,
    normalizeContentId,
    rewriteCidImages,
} from '../../../../core/frontend/static/lib/utils/mail-html.js';

describe('mail-html', () => {
    it('normalizeContentId strips cid: and angle brackets', () => {
        expect(normalizeContentId('<Logo@TBank>')).toBe('logo@tbank');
        expect(normalizeContentId('cid:logo@tbank')).toBe('logo@tbank');
    });

    it('findCidRefs collects cid from src and css url', () => {
        const html = '<img src="cid:logo@tbank"><div style="background:url(cid:bg@x)"></div>';
        expect([...findCidRefs(html)].sort()).toEqual(['bg@x', 'logo@tbank']);
    });

    it('hasRemoteImages detects http(s) img', () => {
        expect(hasRemoteImages('<img src="https://cdn.example/x.png">')).toBe(true);
        expect(hasRemoteImages('<img src="cid:logo@tbank">')).toBe(false);
    });

    it('rewriteCidImages replaces cid with data URL', () => {
        const out = rewriteCidImages('<img src="cid:logo@tbank">', {
            'logo@tbank': 'data:image/png;base64,aaa',
        });
        expect(out).toBe('<img src="data:image/png;base64,aaa">');
    });

    it('rewriteCidImages leaves unknown cid', () => {
        const html = '<img src="cid:missing@x">';
        expect(rewriteCidImages(html, {})).toBe(html);
    });

    it('buildCidFileMap maps referenced content_id to file_id', () => {
        const html = '<img src="cid:logo@tbank">';
        const map = buildCidFileMap(
            [
                { content_id: '<logo@tbank>', file_id: 'file-1', filename: 'logo.png' },
                { content_id: 'other@x', file_id: 'file-2', filename: 'doc.pdf' },
            ],
            html,
        );
        expect(map).toEqual({ 'logo@tbank': 'file-1' });
    });

    it('attachmentsWithoutInlineCid hides referenced cid parts', () => {
        const html = '<img src="cid:logo@tbank">';
        const visible = attachmentsWithoutInlineCid(
            [
                { content_id: 'logo@tbank', file_id: 'file-1', filename: 'logo.png' },
                { filename: 'invoice.pdf', file_id: 'file-2' },
            ],
            html,
        );
        expect(visible).toHaveLength(1);
        expect(visible[0].filename).toBe('invoice.pdf');
    });

    it('autolinkPlaintext escapes tags and links urls', () => {
        const out = autolinkPlaintext('see https://example.com and <script>');
        expect(out).toContain('&lt;script&gt;');
        expect(out).toContain('href="https://example.com"');
        expect(out).toContain('rel="noopener noreferrer"');
    });

    it('mailDocumentCsp blocks scripts and optional remote images', () => {
        const blocked = mailDocumentCsp(false);
        expect(blocked).toContain("script-src 'none'");
        expect(blocked).toContain('img-src data:');
        expect(blocked).not.toContain('https:');
        const allowed = mailDocumentCsp(true);
        expect(allowed).toContain('img-src data: https: http:');
    });

    it('mailIframeSandbox never allows scripts outside WebKit', () => {
        expect(mailIframeSandbox()).toContain('allow-same-origin');
        expect(mailIframeSandbox()).toContain('allow-popups');
    });
});

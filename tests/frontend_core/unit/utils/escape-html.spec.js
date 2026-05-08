import { describe, it, expect } from 'vitest';
import { escapeHtml } from '../../../../core/frontend/static/lib/utils/escape-html.js';

describe('escapeHtml', () => {
    it('null/undefined → empty string', () => {
        expect(escapeHtml(null)).toBe('');
        expect(escapeHtml(undefined)).toBe('');
    });

    it('escape всех 5 символов', () => {
        expect(escapeHtml('<script>alert("&")</script>')).toBe(
            '&lt;script&gt;alert(&quot;&amp;&quot;)&lt;/script&gt;',
        );
        expect(escapeHtml("it's")).toBe('it&#39;s');
    });

    it('обычный текст не меняется', () => {
        expect(escapeHtml('hello world')).toBe('hello world');
    });

    it('число и boolean приводятся к строке', () => {
        expect(escapeHtml(42)).toBe('42');
        expect(escapeHtml(true)).toBe('true');
    });
});

/**
 * Чистые функции sandbox блока ``html``: проекция state по ``fields`` и привязкам,
 * ``srcdoc`` с фиксированным CSP и токенами темы. Мост ``postMessage`` — в browser-спеке.
 */

import { describe, expect, it } from 'vitest';

import {
    FLOW_UI_HTML_CSP,
    FLOW_UI_HTML_MAX_HEIGHT,
    FLOW_UI_HTML_MIN_HEIGHT,
    FLOW_UI_HTML_THEME_TOKENS,
    buildHtmlSrcdoc,
    htmlBlockState,
    htmlBoundPaths,
} from '@platform/lib/flow-ui/runtime/html-sandbox.js';

describe('htmlBoundPaths', () => {
    it('reads attributes on start tags only, in document order, deduplicated', () => {
        const source = '<div data-show="order"><b data-bind="order.total"></b><i data-bind="order.total"></i></div>';
        expect(htmlBoundPaths(source)).toEqual(['order', 'order.total']);
        expect(htmlBoundPaths('')).toEqual([]);
        expect(htmlBoundPaths(12)).toEqual([]);
    });

    it('lists every invalid path in one error', () => {
        expect(() => htmlBoundPaths('<p data-bind="1a"></p><p data-show="b-c"></p>')).toThrow(
            'flow-ui: html block has invalid state path in data-bind="1a", data-show="b-c"',
        );
        expect(() => htmlBoundPaths('<p data-bind></p>')).toThrow(/data-bind=None/);
    });

    it('does not treat unterminated raw text as markup', () => {
        expect(htmlBoundPaths('<i data-bind="ok"></i><script>var x = "<b data-bind=\'nope\'>";')).toEqual(['ok']);
    });
});

describe('htmlBlockState', () => {
    const state = {
        customer: { name: 'Анна', email: 'a@b.c', address: { city: 'Тверь' } },
        items: [{ sku: 'a' }, { sku: 'b' }],
        total: 10,
        flag: false,
        secret: 'no',
    };

    it('projects only fields and bound paths, rebuilding nested objects', () => {
        const block = {
            fields: ['customer.name', 'total'],
            source: '<b data-bind="customer.address.city"></b><i data-show="flag"></i>',
        };
        expect(htmlBlockState(block, state)).toEqual({
            customer: { name: 'Анна', address: { city: 'Тверь' } },
            total: 10,
            flag: false,
        });
    });

    it('skips missing paths, copies whole lists and tolerates absent fields', () => {
        expect(htmlBlockState({ fields: ['missing', 'customer.phone'], source: '' }, state)).toEqual({});
        expect(htmlBlockState({ source: '<p data-bind="items"></p>' }, state)).toEqual({ items: state.items });
        expect(htmlBlockState({ fields: ['items.1.sku'], source: '' }, state)).toEqual({ items: { 1: { sku: 'b' } } });
        expect(htmlBlockState({ fields: ['items.1.sku', 'items.0.sku'], source: '' }, state)).toEqual({
            items: { 1: { sku: 'b' }, 0: { sku: 'a' } },
        });
        expect(htmlBlockState({ fields: null, source: '<p></p>' }, state)).toEqual({});
        expect(htmlBlockState({ fields: ['total'], source: '' }, null)).toEqual({});
    });

    it('a deeper path wins over a scalar written to the same prefix earlier', () => {
        const block = { fields: ['total', 'total.cents'], source: '' };
        expect(htmlBlockState(block, { total: 10 })).toEqual({ total: 10 });
        expect(htmlBlockState(block, { total: { cents: 5 } })).toEqual({ total: { cents: 5 } });
        expect(htmlBlockState({ fields: ['a', 'a.b'], source: '' }, { a: 'scalar' })).toEqual({ a: 'scalar' });
    });

    it('fails on invalid binding paths instead of rendering a partial projection', () => {
        expect(() => htmlBlockState({ fields: [], source: '<p data-bind="1x"></p>' }, state)).toThrow(/invalid state path/);
    });
});

describe('buildHtmlSrcdoc', () => {
    it('embeds the fixed CSP, the theme, the flowUi bootstrap and the author source in order', () => {
        const srcdoc = buildHtmlSrcdoc({ source: '<h1 data-bind="title"></h1>', tokens: { '--flow-ui-text': '#111' } });
        expect(srcdoc.startsWith('<!doctype html><html><head><meta charset="utf-8">')).toBe(true);
        expect(srcdoc).toContain(`<meta http-equiv="Content-Security-Policy" content="${FLOW_UI_HTML_CSP}">`);
        expect(srcdoc).toContain('<style id="flow-ui-theme">:root{--flow-ui-text:#111}</style>');
        expect(srcdoc).toContain('window.flowUi = Object.freeze({');
        expect(srcdoc.indexOf('</script></head><body><h1 data-bind="title"></h1></body></html>')).toBeGreaterThan(0);
        expect(srcdoc.endsWith('</body></html>')).toBe(true);
    });

    it('keeps only css custom property names and strips angle brackets from values', () => {
        const srcdoc = buildHtmlSrcdoc({
            source: '',
            tokens: { '--flow-ui-accent': 'red</style><script>1</script>', 'color': 'blue', '--bad name': 'x', '--Ok-9': 'y' },
        });
        expect(srcdoc).toContain(':root{--flow-ui-accent:red/stylescript1/script;--Ok-9:y}');
        expect(srcdoc.match(/<style id="flow-ui-theme">[^<]*<\/style>/)).not.toBeNull();
        expect(srcdoc).not.toContain('color:blue');
        expect(buildHtmlSrcdoc({ source: '' })).toContain('<style id="flow-ui-theme">:root{}</style>');
    });

    it('rejects a non-string source', () => {
        for (const source of [undefined, null, 1, {}]) {
            expect(() => buildHtmlSrcdoc({ source })).toThrow(/html block source must be a string/);
        }
    });
});

describe('sandbox constants', () => {
    it('pins height bounds and the theme token list', () => {
        expect(FLOW_UI_HTML_MIN_HEIGHT).toBe(24);
        expect(FLOW_UI_HTML_MAX_HEIGHT).toBe(4000);
        expect(Object.isFrozen(FLOW_UI_HTML_THEME_TOKENS)).toBe(true);
        expect(FLOW_UI_HTML_THEME_TOKENS.every((name) => name.startsWith('--flow-ui-'))).toBe(true);
        expect(new Set(FLOW_UI_HTML_THEME_TOKENS).size).toBe(FLOW_UI_HTML_THEME_TOKENS.length);
    });
});

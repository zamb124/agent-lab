/**
 * Грамматика текстовых шаблонов блоков: корнер-кейсы поверх паритетной фикстуры
 * ``tests/fixtures/flow_ui/templating.json`` (та закрывает совпадение с Python).
 */

import { describe, expect, it } from 'vitest';

import {
    blockText,
    blockUrl,
    designText,
    isVisible,
    renderTemplate,
    resolvedText,
    stringifyTemplateValue,
    templatePaths,
    unmatchedBraceMessage,
    valueAtPath,
} from '@platform/lib/flow-ui/runtime/templating.js';

describe('valueAtPath', () => {
    const state = {
        customer: { name: 'Анна', tags: ['vip', 'new'], address: null },
        items: [{ sku: 'a-1', qty: 2 }, { sku: 'b-2', qty: 0 }],
        count: 0,
        flag: false,
        empty: '',
    };

    it('walks objects and arrays by dotted path', () => {
        expect(valueAtPath(state, 'customer.name')).toBe('Анна');
        expect(valueAtPath(state, 'customer.tags.1')).toBe('new');
        expect(valueAtPath(state, 'items.0.sku')).toBe('a-1');
        expect(valueAtPath(state, 'items.1.qty')).toBe(0);
        expect(valueAtPath(state, 'count')).toBe(0);
        expect(valueAtPath(state, 'flag')).toBe(false);
        expect(valueAtPath(state, 'empty')).toBe('');
        expect(valueAtPath(state, 'customer.address')).toBeNull();
    });

    it('returns undefined for missing segments, scalar parents and non-numeric array indexes', () => {
        expect(valueAtPath(state, 'customer.phone')).toBeUndefined();
        expect(valueAtPath(state, 'customer.name.first')).toBeUndefined();
        expect(valueAtPath(state, 'customer.address.city')).toBeUndefined();
        expect(valueAtPath(state, 'items.first')).toBeUndefined();
        expect(valueAtPath(state, 'items.-1')).toBeUndefined();
        expect(valueAtPath(state, 'items.7')).toBeUndefined();
        expect(valueAtPath(state, 'count.value')).toBeUndefined();
    });

    it('ignores prototype properties and rejects empty or non-string paths', () => {
        expect(valueAtPath(state, 'constructor')).toBeUndefined();
        expect(valueAtPath(state, '__proto__')).toBeUndefined();
        expect(valueAtPath(state, 'customer.toString')).toBeUndefined();
        expect(valueAtPath(state, '')).toBeUndefined();
        expect(valueAtPath(state, 42)).toBeUndefined();
        expect(valueAtPath(null, 'customer')).toBeUndefined();
        expect(valueAtPath(undefined, 'customer')).toBeUndefined();
        expect(valueAtPath('text', 'length')).toBeUndefined();
    });
});

describe('stringifyTemplateValue', () => {
    it('renders scalars as text and structures as JSON', () => {
        expect(stringifyTemplateValue(undefined)).toBe('');
        expect(stringifyTemplateValue(null)).toBe('');
        expect(stringifyTemplateValue('x')).toBe('x');
        expect(stringifyTemplateValue(0)).toBe('0');
        expect(stringifyTemplateValue(1.5)).toBe('1.5');
        expect(stringifyTemplateValue(false)).toBe('false');
        expect(stringifyTemplateValue({ a: [1, 'b'] })).toBe('{"a":[1,"b"]}');
        expect(stringifyTemplateValue([])).toBe('[]');
    });
});

describe('templatePaths', () => {
    it('lists references in order without duplicates, including nested defaults', () => {
        expect(templatePaths('{b} {a} {?b|{c|{a}}} {d.e.f}')).toEqual(['b', 'a', 'c', 'd.e.f']);
    });

    it('treats escaped and bare braces as literal text', () => {
        expect(templatePaths('\\{not.a.path} {real}')).toEqual(['real']);
        expect(templatePaths('json: { "k": 1 } {real}')).toEqual(['real']);
        expect(templatePaths('{} {?} {|x}')).toEqual([]);
        expect(templatePaths('{ spaced }')).toEqual([]);
    });

    it('returns no paths for non-strings and stays lenient on unterminated expressions like the Python scanner', () => {
        expect(templatePaths(undefined)).toEqual([]);
        expect(templatePaths(null)).toEqual([]);
        expect(templatePaths(7)).toEqual([]);
        expect(templatePaths('{open')).toEqual(['open']);
        expect(templatePaths('{a|{b}')).toEqual(['a', 'b']);
        expect(templatePaths('{a|x')).toEqual(['a']);
    });

    it('still scans the path of a malformed expression', () => {
        expect(templatePaths('{a-b}')).toEqual(['a']);
        expect(templatePaths('{a b} {c}')).toEqual(['a', 'c']);
        expect(templatePaths('{items.0.sku}')).toEqual(['items.0.sku']);
    });
});

describe('unmatchedBraceMessage', () => {
    it('reports the first unmatched brace and ignores escaped ones', () => {
        expect(unmatchedBraceMessage('')).toBeNull();
        expect(unmatchedBraceMessage('{a} {b|{c}}')).toBeNull();
        expect(unmatchedBraceMessage('\\{ \\}')).toBeNull();
        expect(unmatchedBraceMessage('{a')).toMatch(/opening brace .*1 not closed/);
        expect(unmatchedBraceMessage('{a|{b}')).toMatch(/opening brace .*1 not closed/);
        expect(unmatchedBraceMessage('{{')).toMatch(/2 not closed/);
        expect(unmatchedBraceMessage('a } b')).toBe("unmatched closing brace '}' at position 2");
        expect(unmatchedBraceMessage('\\}}')).toBe("unmatched closing brace '}' at position 2");
        expect(unmatchedBraceMessage('text\\')).toBeNull();
    });
});

describe('renderTemplate', () => {
    it('reports rendered=false only for missing required references', () => {
        expect(renderTemplate('a {x} b', {})).toEqual({ text: 'a  b', rendered: false });
        expect(renderTemplate('a {?x} b', {})).toEqual({ text: 'a  b', rendered: true });
        expect(renderTemplate('a {x|def} b', {})).toEqual({ text: 'a def b', rendered: true });
        expect(renderTemplate('{x|{y}}', {})).toEqual({ text: '', rendered: false });
        expect(renderTemplate('{x|{?y}}', {})).toEqual({ text: '', rendered: true });
        expect(renderTemplate('{x|{y}}', { y: 'Y' })).toEqual({ text: 'Y', rendered: true });
    });

    it('treats null, undefined and empty string as absent but keeps 0 and false', () => {
        expect(renderTemplate('{a}', { a: null })).toEqual({ text: '', rendered: false });
        expect(renderTemplate('{a}', { a: '' })).toEqual({ text: '', rendered: false });
        expect(renderTemplate('{a}', { a: 0 })).toEqual({ text: '0', rendered: true });
        expect(renderTemplate('{a}', { a: false })).toEqual({ text: 'false', rendered: true });
        expect(renderTemplate('{a}', { a: [] })).toEqual({ text: '[]', rendered: true });
        expect(renderTemplate('{a}', { a: { b: 1 } })).toEqual({ text: '{"b":1}', rendered: true });
    });

    it('handles escapes, literal braces and defaults with braces or escapes inside', () => {
        expect(renderTemplate('\\{a\\} \\\\ tail\\', { a: 1 })).toEqual({ text: '{a} \\ tail\\', rendered: true });
        expect(renderTemplate('{a|x\\}y}', {})).toEqual({ text: 'x}y', rendered: true });
        expect(renderTemplate('{a|{b|{c|deep}}}', {})).toEqual({ text: 'deep', rendered: true });
        expect(renderTemplate('{a|}', {})).toEqual({ text: '', rendered: true });
        expect(renderTemplate('{ {a} }', { a: 'v' })).toEqual({ text: '{ v }', rendered: true });
    });

    it('accepts non-object state as empty and rejects non-string templates', () => {
        expect(renderTemplate('{a|d}', null)).toEqual({ text: 'd', rendered: true });
        expect(renderTemplate('{a|d}', 'state')).toEqual({ text: 'd', rendered: true });
        expect(renderTemplate('plain', undefined)).toEqual({ text: 'plain', rendered: true });
        expect(() => renderTemplate(null, {})).toThrow(/template must be a string/);
        expect(() => renderTemplate({}, {})).toThrow(/template must be a string/);
    });

    it('keeps malformed but balanced expressions as literal text', () => {
        expect(renderTemplate('{a-b}', { a: 'A' })).toEqual({ text: '{a-b}', rendered: true });
        expect(renderTemplate('{a b} {a}', { a: 'A' })).toEqual({ text: '{a b} A', rendered: true });
        expect(renderTemplate('{ spaced } {?x}', {})).toEqual({ text: '{ spaced } ', rendered: true });
        expect(renderTemplate('{} {?} {|x}', {})).toEqual({ text: '{} {?} {|x}', rendered: true });
    });

    it('throws on unbalanced braces before rendering anything', () => {
        expect(() => renderTemplate('{a', { a: 'A' })).toThrow(/unmatched opening brace/);
        expect(() => renderTemplate('a } b', {})).toThrow(/unmatched closing brace/);
        expect(() => renderTemplate('{a|{b}}}', {})).toThrow(/unmatched closing brace/);
        expect(() => resolvedText('Hi {name', { name: 'Ann' })).toThrow(/unmatched opening brace/);
    });
});

describe('resolvedText / designText / blockText', () => {
    it('resolvedText returns null when a required reference is missing', () => {
        expect(resolvedText('Hi {name}', { name: 'Ann' })).toBe('Hi Ann');
        expect(resolvedText('Hi {name}', {})).toBeNull();
        expect(resolvedText('Hi {?name}', {})).toBe('Hi ');
        expect(resolvedText('Hi {name|guest}', {})).toBe('Hi guest');
        expect(resolvedText('', {})).toBe('');
        expect(() => resolvedText(undefined, {})).toThrow(/template property must be a string/);
    });

    it('designText keeps unresolved references visible and substitutes known ones', () => {
        expect(designText('Hi {name}, total {total}', { name: 'Ann' })).toBe('Hi Ann, total {total}');
        expect(designText('{?note}', {})).toBe('{?note}');
        expect(designText('{total|0}', {})).toBe('0');
        expect(designText('{a|{b}}', {})).toBe('{b}');
        expect(designText('\\{lit\\}', null)).toBe('{lit}');
        expect(() => designText(3, {})).toThrow(/template property must be a string/);
    });

    it('designText never throws while the author is still typing a brace', () => {
        expect(designText('Hi {na', { name: 'Ann' })).toBe('Hi {na');
        expect(designText('Hi {name} }', { name: 'Ann' })).toBe('Hi {name} }');
        expect(designText('{a-b} {a}', { a: 'A' })).toBe('{a-b} A');
    });

    it('blockText switches between runtime and canvas rendering', () => {
        expect(blockText({ editing: false, state: {} }, 'Hi {name}')).toBeNull();
        expect(blockText({ editing: true, state: {} }, 'Hi {name}')).toBe('Hi {name}');
        expect(blockText({ editing: true, state: { name: 'A' } }, 'Hi {name}')).toBe('Hi A');
    });

    it('blockUrl resolves like runtime on the canvas too: an unresolved path is no URL, not text', () => {
        expect(blockUrl({ editing: true, state: {} }, '{file.url}')).toBeNull();
        expect(blockUrl({ editing: true, state: {} }, '{?contact.image_url}')).toBe('');
        expect(blockUrl({ editing: true, state: { file: { url: 'https://a/b.png' } } }, '{file.url}')).toBe('https://a/b.png');
        expect(blockUrl({ editing: false, state: {} }, 'https://a/{id}.png')).toBeNull();
        expect(blockUrl({ editing: false, state: { id: 7 } }, 'https://a/{id}.png')).toBe('https://a/7.png');
        expect(blockUrl({ editing: true, state: {} }, '')).toBe('');
        expect(() => blockUrl({ editing: true, state: {} }, '{open')).toThrow(/unmatched opening brace/);
    });
});

describe('isVisible', () => {
    const state = {
        list: [1],
        emptyList: [],
        zero: 0,
        one: 1,
        off: false,
        on: true,
        text: 'x',
        blank: '',
        obj: { a: 1 },
        nothing: null,
    };

    it('is visible without a rule and follows truthiness of the path value', () => {
        expect(isVisible(null, state)).toBe(true);
        expect(isVisible(undefined, state)).toBe(true);
        expect(isVisible({ path: 'list' }, state)).toBe(true);
        expect(isVisible({ path: 'emptyList' }, state)).toBe(false);
        expect(isVisible({ path: 'zero' }, state)).toBe(false);
        expect(isVisible({ path: 'one' }, state)).toBe(true);
        expect(isVisible({ path: 'off' }, state)).toBe(false);
        expect(isVisible({ path: 'on' }, state)).toBe(true);
        expect(isVisible({ path: 'text' }, state)).toBe(true);
        expect(isVisible({ path: 'blank' }, state)).toBe(false);
        expect(isVisible({ path: 'obj' }, state)).toBe(true);
        expect(isVisible({ path: 'nothing' }, state)).toBe(false);
        expect(isVisible({ path: 'missing.deep' }, state)).toBe(false);
    });

    it('compares equals structurally and treats equals=null as a truthiness rule', () => {
        expect(isVisible({ path: 'zero', equals: 0 }, state)).toBe(true);
        expect(isVisible({ path: 'off', equals: false }, state)).toBe(true);
        expect(isVisible({ path: 'blank', equals: '' }, state)).toBe(true);
        expect(isVisible({ path: 'obj', equals: { a: 1 } }, state)).toBe(true);
        expect(isVisible({ path: 'obj', equals: { a: 2 } }, state)).toBe(false);
        expect(isVisible({ path: 'list', equals: [1] }, state)).toBe(true);
        expect(isVisible({ path: 'one', equals: '1' }, state)).toBe(false);
        expect(isVisible({ path: 'missing', equals: 'x' }, state)).toBe(false);
        expect(isVisible({ path: 'on', equals: null }, state)).toBe(true);
        expect(isVisible({ path: 'off', equals: null }, state)).toBe(false);
    });

    it('rejects rules without a string path', () => {
        expect(() => isVisible({}, state)).toThrow(/visible_when requires path/);
        expect(() => isVisible({ path: 5 }, state)).toThrow(/visible_when requires path/);
        expect(() => isVisible('flag', state)).toThrow(/visible_when requires path/);
    });
});

/**
 * Чистая логика HTML-редактора: parse/merge test-state, пути полей, стабильный preview-block.
 */

import { describe, expect, it } from 'vitest';

import {
    HTML_EDITOR_SNIPPETS,
    HTML_EDITOR_VIEWPORTS,
    fieldControlKind,
    fieldEditorValue,
    mergeTestState,
    parseFieldEditorValue,
    parseTestState,
    previewBlock,
    setValueAtPath,
    valueAtSimplePath,
} from '@platform/lib/flow-ui/editor/html-editor-api.js';

describe('html-editor-api', () => {
    it('parses object test-state and rejects arrays and invalid JSON', () => {
        expect(parseTestState('{"title":"Hi"}')).toEqual({ ok: true, error: '', value: { title: 'Hi' } });
        expect(parseTestState('[]').ok).toBe(false);
        expect(parseTestState('null').ok).toBe(false);
        expect(parseTestState('{ not json').ok).toBe(false);
    });

    it('merges a snippet patch onto the last-good object without dropping keys', () => {
        expect(mergeTestState({ title: 'A', items: [1] }, { title: 'B', warning: 'x' })).toEqual({
            title: 'B',
            items: [1],
            warning: 'x',
        });
        expect(mergeTestState(null, { title: 'B' })).toEqual({ title: 'B' });
    });

    it('writes nested field paths and classifies controls', () => {
        const next = setValueAtPath({ title: 'A' }, 'order.total', 12);
        expect(next).toEqual({ title: 'A', order: { total: 12 } });
        expect(valueAtSimplePath(next, 'order.total')).toBe(12);
        expect(fieldControlKind(true)).toBe('boolean');
        expect(fieldControlKind(3)).toBe('number');
        expect(fieldControlKind([1])).toBe('json');
        expect(fieldEditorValue([1])).toBe('[\n  1\n]');
        expect(parseFieldEditorValue('number', '4')).toBe(4);
        expect(parseFieldEditorValue('json', '{"a":1}')).toEqual({ a: 1 });
    });

    it('reuses the preview block object when source is unchanged', () => {
        const block = { block_id: 'card', type: 'html', source: '<p></p>' };
        const once = previewBlock(block, '<p></p>', null);
        expect(once).not.toBe(block);
        expect(previewBlock(block, '<p></p>', once)).toBe(once);
        expect(previewBlock(block, '<b></b>', once).source).toBe('<b></b>');
        expect(HTML_EDITOR_VIEWPORTS).toEqual({ desktop: 1180, tablet: 820, mobile: 390 });
        expect(HTML_EDITOR_SNIPPETS.map((item) => item.id)).toEqual(['bind', 'show', 'list', 'send', 'value', 'card']);
    });
});

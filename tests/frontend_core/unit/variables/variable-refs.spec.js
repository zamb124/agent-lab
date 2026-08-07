import { describe, expect, it } from 'vitest';
import {
    buildExecutionStatePreview,
    collectStatePathsFromDataflow,
    findCatalogEntry,
    lookupPreviewValue,
    scanAtRefs,
    scanBraceRefs,
} from '../../../../core/frontend/static/lib/variables/variable-refs.js';

describe('variable-refs helpers', () => {
    it('scanAtRefs finds @var and @state paths', () => {
        const refs = scanAtRefs('Hi @state:content and @var:topic.extra');
        expect(refs).toEqual([
            {
                kind: 'state',
                path: 'content',
                from: 3,
                to: 17,
                raw: '@state:content',
            },
            {
                kind: 'var',
                path: 'topic.extra',
                from: 22,
                to: 38,
                raw: '@var:topic.extra',
            },
        ]);
    });

    it('scanBraceRefs finds required optional and for refs', () => {
        const refs = scanBraceRefs('{for item in items}{item.name}{endfor}{?opt|x}');
        expect(refs.some((r) => r.raw.startsWith('{for ') && r.path === 'items')).toBe(true);
        expect(refs.some((r) => r.path === 'item.name')).toBe(true);
        expect(refs.some((r) => r.path === 'endfor')).toBe(true);
        expect(refs.some((r) => r.path === 'opt')).toBe(true);
    });

    it('lookupPreviewValue resolves nested unwrap and catalog runtime_only', () => {
        expect(lookupPreviewValue('topic', {
            kind: 'var',
            values: { topic: { value: 'AI' } },
        })).toEqual({ status: 'resolved', value: 'AI' });

        expect(lookupPreviewValue('missing', {
            kind: 'brace',
            values: {},
            catalog: [{ name: 'missing', hasValue: false, source: 'system' }],
        })).toEqual({ status: 'runtime_only' });

        expect(lookupPreviewValue('unknown', {
            kind: 'var',
            values: {},
            catalog: [],
        })).toEqual({ status: 'undefined' });
    });

    it('lookupPreviewValue for @state uses statePreview or runtime_only', () => {
        expect(lookupPreviewValue('content', {
            kind: 'state',
            statePreview: { content: 'hello' },
        })).toEqual({ status: 'resolved', value: 'hello' });

        expect(lookupPreviewValue('content', {
            kind: 'state',
            statePreview: {},
        })).toEqual({ status: 'runtime_only' });
    });

    it('buildExecutionStatePreview keeps known top-level keys', () => {
        expect(buildExecutionStatePreview({
            content: 'x',
            response: 'y',
            breakpoint_hit: true,
            variables: { a: 1 },
        })).toEqual({
            content: 'x',
            response: 'y',
            variables: { a: 1 },
        });
    });

    it('collectStatePathsFromDataflow merges incoming_state paths', () => {
        const paths = collectStatePathsFromDataflow({
            incoming_state: [
                { path: 'content' },
                { path: 'variables.topic' },
                { path: 'context.foo' },
            ],
        });
        expect(paths).toContain('content');
        expect(paths).toContain('response');
        expect(paths).toContain('variables.topic');
        expect(paths).toContain('context.foo');
    });

    it('findCatalogEntry matches ui_values leaf and root family', () => {
        const catalog = [
            { name: 'company_name', source: 'system' },
            { name: 'ui_values.email', source: 'ui_value' },
            { name: 'ui_values.phone', source: 'ui_value' },
        ];
        expect(findCatalogEntry('ui_values.email', catalog)?.name).toBe('ui_values.email');
        expect(findCatalogEntry('ui_values', catalog)?.name).toMatch(/^ui_values\./);
        expect(findCatalogEntry('ui_values.phone', catalog)?.name).toBe('ui_values.phone');
        expect(findCatalogEntry('ui_values.missing', catalog)).toBeNull();
        expect(findCatalogEntry('company_name', catalog)?.name).toBe('company_name');
    });
});

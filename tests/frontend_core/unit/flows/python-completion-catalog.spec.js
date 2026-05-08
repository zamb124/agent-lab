import { describe, it, expect, afterEach } from 'vitest';
import {
    buildGlobalSymbolMap,
    buildPythonCompletions,
    fetchCompletionCatalog,
    isValidPythonIdentifier,
    normalizeCatalogResponse,
    parseImportCompletion,
    resetCompletionCatalogCacheForTests,
    scanPythonFragment,
} from '../../../../apps/flows/ui/_helpers/flows-python-completion-catalog.js';

afterEach(() => {
    resetCompletionCatalogCacheForTests();
});

function mockCatalog() {
    return normalizeCatalogResponse({
        modules: ['json', 're'],
        globals: [
            { name: 'ask_user', type: 'function', doc: 'interrupt' },
            { name: 'Встроенные tools', type: 'convention', doc: 'not an identifier' },
        ],
        builtins: ['len', 'str'],
        module_methods: {
            json: [
                { name: 'loads', type: 'function', doc: 'parse' },
                { name: 'dumps', type: 'function', doc: 'serialize' },
            ],
        },
        state_fields: [{ name: 'messages', type: 'list', description: 'dialog' }],
        platform_tools: [{ tool_id: 'calculator', display_name: 'Calc', description: 'math' }],
        runtime_namespace_extras: [{ name: 'extra_sym', type: 'function', doc: 'x' }],
    });
}

describe('isValidPythonIdentifier', () => {
    it('accepts ascii identifiers', () => {
        expect(isValidPythonIdentifier('ask_user')).toBe(true);
        expect(isValidPythonIdentifier('_x2')).toBe(true);
    });

    it('rejects spaced convention labels', () => {
        expect(isValidPythonIdentifier('Встроенные tools')).toBe(false);
        expect(isValidPythonIdentifier('')).toBe(false);
    });
});

describe('buildGlobalSymbolMap', () => {
    it('skips globals whose name is not a Python identifier', () => {
        const m = buildGlobalSymbolMap(mockCatalog());
        expect(m.has('ask_user')).toBe(true);
        expect(m.has('Встроенные tools')).toBe(false);
        expect(m.has('calculator')).toBe(true);
        expect(m.has('len')).toBe(true);
        expect(m.has('extra_sym')).toBe(true);
    });

    it('uses markdown info renderer when documentation text is non-empty', () => {
        const m = buildGlobalSymbolMap(mockCatalog());
        expect(typeof m.get('ask_user')?.info).toBe('function');
        expect(typeof m.get('calculator')?.info).toBe('function');
        expect(typeof m.get('extra_sym')?.info).toBe('function');
        expect(m.get('len')?.info).toBe('');
    });
});

describe('scanPythonFragment', () => {
    it('marks completesAfterDot after trailing dot', () => {
        const t = 'foo(state.';
        const r = scanPythonFragment(t, t.length);
        expect(r.chain).toBe('state');
        expect(r.partial).toBe('');
        expect(r.completesAfterDot).toBe(true);
    });

    it('splits chain and partial for attribute access', () => {
        const t = 'state.mes';
        const r = scanPythonFragment(t, t.length);
        expect(r.chain).toBe('state');
        expect(r.partial).toBe('mes');
        expect(r.completesAfterDot).toBe(false);
    });
});

describe('parseImportCompletion', () => {
    it('detects import module list tail', () => {
        const r = parseImportCompletion('import json, re');
        expect(r?.kind).toBe('import_modules');
        expect(r?.partial).toBe('re');
    });

    it('detects from-import names', () => {
        const r = parseImportCompletion('from json import loads');
        expect(r?.kind).toBe('from_import_names');
        expect(r?.module).toBe('json');
        expect(r?.partial).toBe('loads');
    });
});

describe('buildPythonCompletions', () => {
    const catalog = mockCatalog();

    it('completes state fields after state.', () => {
        const docText = 'x = state.mes';
        const r = buildPythonCompletions({
            docText,
            pos: docText.length,
            catalog,
            variableKeys: [],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.some((o) => o.label === 'messages')).toBe(true);
    });

    it('completes variable keys under state.variables.', () => {
        const docText = 'k = state.variables.api';
        const r = buildPythonCompletions({
            docText,
            pos: docText.length,
            catalog,
            variableKeys: ['api_key', 'api_base'],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.map((o) => o.label).sort()).toEqual(['api_base', 'api_key']);
    });

    it('completes json module members', () => {
        const docText = 'json.lo';
        const r = buildPythonCompletions({
            docText,
            pos: docText.length,
            catalog,
            variableKeys: [],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.some((o) => o.label === 'loads')).toBe(true);
    });

    it('returns null when nothing matches non-explicit empty fragment', () => {
        const docText = 'def f():\n    ';
        const r = buildPythonCompletions({
            docText,
            pos: docText.length,
            catalog,
            variableKeys: [],
            explicit: false,
        });
        expect(r).toBeNull();
    });
});

describe('fetchCompletionCatalog', () => {
    it('reuses cached catalog for same cache key', async () => {
        let calls = 0;
        const run = async () => {
            calls += 1;
            return mockCatalog();
        };
        const ctx = { perspective: 'node', include_runtime_namespace_extras: true };
        const a = await fetchCompletionCatalog(run, ctx);
        const b = await fetchCompletionCatalog(run, ctx);
        expect(calls).toBe(1);
        expect(a.modules.length).toBeGreaterThan(0);
        expect(b.modules).toEqual(a.modules);
    });

    it('drops cache entry when fetch rejects then retries', async () => {
        let calls = 0;
        const run = async () => {
            calls += 1;
            if (calls === 1) {
                throw new Error('network');
            }
            return mockCatalog();
        };
        const ctx = { perspective: 'editor', include_runtime_namespace_extras: false };
        await expect(fetchCompletionCatalog(run, ctx)).rejects.toThrow('network');
        const cat = await fetchCompletionCatalog(run, ctx);
        expect(calls).toBe(2);
        expect(cat.modules.length).toBeGreaterThan(0);
    });
});

import { describe, it, expect, afterEach } from 'vitest';
import { buildCodeQueryUrl } from '../../../../apps/flows/ui/events/resources/code.resource.js';
import {
    buildGlobalSymbolMap,
    buildCodeCompletions,
    buildPythonCompletions,
    fetchCompletionCatalog,
    getCompletionCatalogCacheKey,
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
        capability_namespaces: [
            { name: 'files', type: 'generated namespace', methods: ['create'], capability_names: ['files.create'] },
            { name: 'tools', type: 'generated namespace', methods: ['calculator'], capability_names: ['tools.calculator'] },
        ],
        capabilities: [
            {
                capability_name: 'files.create',
                namespace: 'files',
                method: 'create',
                label: 'files.create',
                title: 'Create file',
                description: 'Create platform file',
                signature: 'await files.create(content: string)',
                insert_text: 'await files.create(content="value")',
                documentation: '### `files.create`\n\nCreate platform file',
                tags: ['files'],
                input_fields: [{ path: 'content', type: 'string', required: true }],
                output_fields: [{ path: 'file_id', type: 'string', required: true }],
            },
        ],
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
        expect(m.has('files')).toBe(true);
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

    it('completes capability methods after namespace dot', () => {
        const docText = 'result = await files.cre';
        const r = buildPythonCompletions({
            docText,
            pos: docText.length,
            catalog,
            variableKeys: [],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.some((o) => o.label === 'create' && o.detail.includes('files.create'))).toBe(true);
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

describe('buildCodeCompletions', () => {
    const catalog = mockCatalog();

    it('uses generic symbols for javascript-like languages', () => {
        const docText = 'ask';
        const r = buildCodeCompletions({
            language: 'typescript',
            docText,
            pos: docText.length,
            catalog,
            variableKeys: [],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.some((o) => o.label === 'ask_user')).toBe(true);
        expect(r.options.some((o) => o.label === 'Встроенные tools')).toBe(false);
    });

    it('includes capability namespaces in generic symbols', () => {
        const docText = 'fi';
        const r = buildCodeCompletions({
            language: 'typescript',
            docText,
            pos: docText.length,
            catalog,
            variableKeys: [],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.some((o) => o.label === 'files')).toBe(true);
    });

    it('uses capability method names for selected generic language', () => {
        const docText = 'files.cre';
        const r = buildCodeCompletions({
            language: 'typescript',
            docText,
            pos: docText.length,
            catalog,
            variableKeys: [],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.some((o) => o.label === 'create' && o.detail.includes('files.create'))).toBe(true);
    });

    it('uses backend-provided Go/C# method casing', () => {
        const catalogWithGoMethod = normalizeCatalogResponse({
            capability_namespaces: [{ name: 'files', type: 'generated namespace' }],
            capabilities: [
                {
                    capability_name: 'files.create',
                    namespace: 'files',
                    method: 'Create',
                    label: 'files.Create',
                    title: 'Create file',
                    description: 'Create platform file',
                    signature: 'files.Create(map[string]any{...})',
                    insert_text: 'files.Create(map[string]any{})',
                    documentation: '### `files.Create`',
                    tags: ['files'],
                    input_fields: [],
                    output_fields: [],
                },
            ],
        });
        const docText = 'files.Cre';
        const r = buildCodeCompletions({
            language: 'go',
            docText,
            pos: docText.length,
            catalog: catalogWithGoMethod,
            variableKeys: [],
            explicit: false,
        });
        expect(r).not.toBeNull();
        expect(r.options.map((o) => o.label)).toEqual(['Create']);
    });
});

describe('fetchCompletionCatalog', () => {
    it('passes selected language through completion payload and cache key', async () => {
        const payloads = [];
        const run = async (payload) => {
            payloads.push(payload);
            return mockCatalog();
        };
        const goCtx = { language: 'go', perspective: 'node', include_runtime_namespace_extras: true };
        const tsCtx = { language: 'typescript', perspective: 'node', include_runtime_namespace_extras: true };

        await fetchCompletionCatalog(run, goCtx);
        await fetchCompletionCatalog(run, goCtx);
        await fetchCompletionCatalog(run, tsCtx);

        expect(payloads).toEqual([
            { language: 'go', perspective: 'node', include_runtime_namespace_extras: true },
            { language: 'typescript', perspective: 'node', include_runtime_namespace_extras: true },
        ]);
        expect(getCompletionCatalogCacheKey(goCtx)).toBe('go|node|1');
        expect(getCompletionCatalogCacheKey(tsCtx)).toBe('typescript|node|1');
    });

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

describe('code resource query URLs', () => {
    it('serializes selected language into completions request URL', () => {
        const url = buildCodeQueryUrl('/flows/api/v1/code/completions', {
            language: 'csharp',
            perspective: 'node',
            include_runtime_namespace_extras: true,
        });
        expect(url).toBe(
            '/flows/api/v1/code/completions?language=csharp&perspective=node&include_runtime_namespace_extras=true',
        );
    });
});

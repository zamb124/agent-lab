/**
 * Каталог автодополнения для flows-code-editor из ответа GET /flows/api/v1/code/completions.
 * Единый источник символов — JSON API (globals, runtime_namespace_extras, platform_tools, …).
 */

/**
 * @typedef {{
 *   label: string,
 *   type?: string,
 *   detail?: string,
 *   info?: string | ((completion: unknown) => HTMLElement | Text | DocumentFragment),
 * }} CMCompletionOption
 */

const PYTHON_IDENT_RE = /^[A-Za-z_]\w*$/;
const JS_IDENT_RE = /^[$A-Za-z_][$\w]*$/;
const SIMPLE_IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

const RUNTIME_GLOBALS = Object.freeze([
    {
        label: 'args',
        type: 'variable',
        detail: 'runtime input',
        info: 'Arguments passed into the code entrypoint.',
    },
    {
        label: 'state',
        type: 'variable',
        detail: 'execution state',
        info: 'Mutable flow execution state shared across nodes.',
    },
    {
        label: 'variables',
        type: 'namespace',
        detail: 'flow variables',
        info: 'Resolved flow variables from state.variables.',
    },
]);

const DEFAULT_STATE_FIELDS = Object.freeze([
    { name: 'content', type: 'string', description: 'Input message content.' },
    { name: 'response', type: 'string', description: 'Agent response text.' },
    { name: 'result', type: 'any', description: 'Last node or tool result.' },
    { name: 'validation', type: 'object', description: 'Node validation payload.' },
    { name: 'messages', type: 'array', description: 'Conversation message history.' },
    { name: 'variables', type: 'object', description: 'Resolved flow variables.' },
    { name: 'files', type: 'array', description: 'Attached files available to the flow.' },
    { name: 'triggers', type: 'object', description: 'Trigger runtime payloads by trigger id.' },
    { name: 'tool_results', type: 'object', description: 'Results produced by tools.' },
    { name: 'node_history', type: 'object', description: 'Runtime node call history.' },
    { name: 'current_nodes', type: 'array', description: 'Current graph nodes being executed.' },
    { name: 'branch_id', type: 'string', description: 'Current flow branch id.' },
    { name: 'session_id', type: 'string', description: 'Runtime session id.' },
    { name: 'flow_config_version', type: 'string', description: 'Flow config version snapshot.' },
]);

/**
 * @param {string} text
 */
function escapeHtmlForCompletion(text) {
    return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/**
 * Панель документации саджеста CM: Markdown через `globalThis.marked` (см. marked.min.js на странице flows).
 *
 * @param {string} md
 * @returns {string}
 */
function markdownToCompletionHtml(md) {
    const marked = globalThis.marked;
    if (marked && typeof marked.parse === 'function') {
        if (typeof marked.setOptions === 'function') {
            marked.setOptions({ gfm: true, breaks: true, mangle: false, headerIds: false });
        }
        return marked.parse(md);
    }
    return `<pre class="flows-cm-completion-md-fallback">${escapeHtmlForCompletion(md)}</pre>`;
}

/**
 * @param {string} md
 * @returns {(completion: unknown) => HTMLElement}
 */
function completionMarkdownInfo(md) {
    return () => {
        const root = document.createElement('div');
        root.className = 'flows-cm-completion-md';
        root.innerHTML = markdownToCompletionHtml(md);
        return root;
    };
}

const _catalogPromises = new Map();

/**
 * Сброс кэша промисов каталога (юнит-тесты).
 */
export function resetCompletionCatalogCacheForTests() {
    _catalogPromises.clear();
}

/**
 * @param {Record<string, unknown> | null | undefined} completionContext
 */
export function getCompletionCatalogCacheKey(completionContext) {
    const o = completionContext && typeof completionContext === 'object' ? completionContext : {};
    const language = typeof o.language === 'string' && o.language.length > 0 ? o.language : 'python';
    const perspective =
        typeof o.perspective === 'string' && o.perspective.length > 0 ? o.perspective : 'editor';
    const extras = o.include_runtime_namespace_extras === true ? '1' : '0';
    return `${language}|${perspective}|${extras}`;
}

/**
 * @param {(payload: Record<string, unknown>) => Promise<unknown>} runCompletionsOp
 * @param {Record<string, unknown> | null | undefined} completionContext
 */
export async function fetchCompletionCatalog(runCompletionsOp, completionContext) {
    const key = getCompletionCatalogCacheKey(completionContext);
    const existing = _catalogPromises.get(key);
    if (existing) {
        return existing;
    }
    const o = completionContext && typeof completionContext === 'object' ? completionContext : {};
    const payload = {
        language: typeof o.language === 'string' && o.language.length > 0 ? o.language : 'python',
        perspective:
            typeof o.perspective === 'string' && o.perspective.length > 0 ? o.perspective : 'editor',
        include_runtime_namespace_extras: o.include_runtime_namespace_extras === true,
    };
    const p = Promise.resolve(runCompletionsOp(payload))
        .then((raw) => normalizeCatalogResponse(raw))
        .catch((e) => {
            _catalogPromises.delete(key);
            throw e;
        });
    _catalogPromises.set(key, p);
    return p;
}

/**
 * @param {unknown} raw
 */
export function normalizeCatalogResponse(raw) {
    const r = raw && typeof raw === 'object' ? raw : {};
    return {
        modules: Array.isArray(r.modules) ? r.modules.filter((m) => typeof m === 'string') : [],
        globals: Array.isArray(r.globals) ? r.globals : [],
        builtins: Array.isArray(r.builtins) ? r.builtins.filter((b) => typeof b === 'string') : [],
        module_methods:
            r.module_methods && typeof r.module_methods === 'object' && !Array.isArray(r.module_methods)
                ? r.module_methods
                : {},
        state_fields: Array.isArray(r.state_fields) ? r.state_fields : [],
        platform_tools: Array.isArray(r.platform_tools) ? r.platform_tools : [],
        capability_namespaces: Array.isArray(r.capability_namespaces) ? r.capability_namespaces : [],
        capabilities: Array.isArray(r.capabilities) ? r.capabilities : [],
        runtime_namespace_extras: Array.isArray(r.runtime_namespace_extras)
            ? r.runtime_namespace_extras
            : [],
    };
}

/**
 * @param {unknown} name
 */
export function isValidPythonIdentifier(name) {
    return typeof name === 'string' && PYTHON_IDENT_RE.test(name);
}

/**
 * @param {unknown} language
 * @param {unknown} name
 */
function isValidLanguageIdentifier(language, name) {
    if (typeof name !== 'string') {
        return false;
    }
    if (language === 'javascript' || language === 'typescript') {
        return JS_IDENT_RE.test(name);
    }
    if (language === 'go' || language === 'csharp') {
        return SIMPLE_IDENT_RE.test(name);
    }
    return isValidPythonIdentifier(name);
}

/**
 * @param {string} t
 */
function mapDocTypeToCm(t) {
    if (t === 'function' || t === 'tool' || t === 'method') {
        return 'function';
    }
    if (t === 'class' || t === 'exception' || t === 'enum') {
        return 'class';
    }
    if (t === 'module') {
        return 'namespace';
    }
    if (t === 'constant' || t === 'literal') {
        return 'constant';
    }
    return 'variable';
}

/**
 * @param {string} language
 */
function runtimeGlobalOptions(language) {
    return RUNTIME_GLOBALS
        .filter((opt) => isValidLanguageIdentifier(language, opt.label))
        .map((opt) => ({ ...opt }));
}

/**
 * @param {unknown[]} stateFields
 */
function normalizedStateFieldRows(stateFields) {
    const rows = [];
    const seen = new Set();
    const push = (row) => {
        if (!row || typeof row !== 'object') {
            return;
        }
        const name = 'name' in row && typeof row.name === 'string' ? row.name : '';
        if (!isValidPythonIdentifier(name) || seen.has(name)) {
            return;
        }
        seen.add(name);
        const typ = 'type' in row && typeof row.type === 'string' ? row.type : '';
        const desc = 'description' in row && typeof row.description === 'string' ? row.description : '';
        rows.push({ name, type: typ, description: desc });
    };
    for (const row of DEFAULT_STATE_FIELDS) {
        push(row);
    }
    if (Array.isArray(stateFields)) {
        for (const row of stateFields) {
            push(row);
        }
    }
    return rows;
}

/**
 * @param {{ globals?: unknown[], runtime_namespace_extras?: unknown[], builtins?: string[], platform_tools?: unknown[] }} catalog
 * @returns {Map<string, CMCompletionOption>}
 */
export function buildGlobalSymbolMap(catalog, language = 'python') {
    /** @type {Map<string, CMCompletionOption>} */
    const map = new Map();

    for (const opt of runtimeGlobalOptions(language)) {
        map.set(opt.label, opt);
    }

    const pushGlobals = (arr) => {
        if (!Array.isArray(arr)) {
            return;
        }
        for (const g of arr) {
            const opts = globalEntryToGenericOptions(language, g);
            for (const opt of opts) {
                if (!map.has(opt.label)) {
                    map.set(opt.label, opt);
                }
            }
        }
    };

    pushGlobals(catalog.globals);
    pushGlobals(catalog.runtime_namespace_extras);

    if (Array.isArray(catalog.builtins)) {
        for (const name of catalog.builtins) {
            if (typeof name !== 'string' || !isValidPythonIdentifier(name)) {
                continue;
            }
            if (!map.has(name)) {
                map.set(name, {
                    label: name,
                    type: 'function',
                    detail: 'builtin',
                    info: '',
                });
            }
        }
    }

    if (Array.isArray(catalog.platform_tools)) {
        for (const t of catalog.platform_tools) {
            if (!t || typeof t !== 'object') {
                continue;
            }
            const tid = 'tool_id' in t && typeof t.tool_id === 'string' ? t.tool_id : '';
            if (!isValidPythonIdentifier(tid)) {
                continue;
            }
            if (!map.has(tid)) {
                const dn =
                    'display_name' in t && typeof t.display_name === 'string' ? t.display_name : '';
                const desc =
                    'description' in t && typeof t.description === 'string' ? t.description : '';
                const toolOpt = {
                    label: tid,
                    type: 'function',
                    detail: dn || 'platform tool',
                };
                if (desc.trim().length > 0) {
                    toolOpt.info = completionMarkdownInfo(desc);
                }
                map.set(tid, toolOpt);
            }
        }
    }

    for (const ns of catalog.capability_namespaces) {
        if (!ns || typeof ns !== 'object') {
            continue;
        }
        const name = 'name' in ns && typeof ns.name === 'string' ? ns.name : '';
        if (!isValidPythonIdentifier(name) || map.has(name)) {
            continue;
        }
        const type = 'type' in ns && typeof ns.type === 'string' ? ns.type : 'capability namespace';
        map.set(name, {
            label: name,
            type: 'namespace',
            detail: type,
            info: '',
        });
    }

    return map;
}

/**
 * @param {string} docText
 * @param {number} pos
 */
export function scanPythonFragment(docText, pos) {
    if (pos <= 0 || typeof docText !== 'string') {
        return { from: pos, fragment: '', chain: '', partial: '', completesAfterDot: false };
    }
    let i = pos - 1;
    while (i >= 0) {
        const ch = docText[i];
        if (/[A-Za-z0-9_.]/.test(ch)) {
            i--;
            continue;
        }
        break;
    }
    const from = i + 1;
    const fragment = docText.slice(from, pos);

    if (fragment.endsWith('.')) {
        const chain = fragment.slice(0, -1);
        return { from, fragment, chain, partial: '', completesAfterDot: true };
    }
    const lastDot = fragment.lastIndexOf('.');
    if (lastDot >= 0) {
        const chain = fragment.slice(0, lastDot);
        const partial = fragment.slice(lastDot + 1);
        return {
            from: pos - partial.length,
            fragment,
            chain,
            partial,
            completesAfterDot: false,
        };
    }
    return { from, fragment, chain: '', partial: fragment, completesAfterDot: false };
}

/**
 * @param {string} linePrefix
 */
export function parseImportCompletion(linePrefix) {
    const trimmed = linePrefix;

    const importLine = /^\s*import\s+(.+)$/.exec(trimmed);
    if (importLine && !/^\s*from\s/.test(trimmed)) {
        const tail = importLine[1];
        const segments = tail.split(',').map((s) => s.trim());
        const lastSeg = segments[segments.length - 1] || '';
        const partial = lastSeg.replace(/\s+/g, '');
        const replacementStart = trimmed.length - partial.length;
        return {
            kind: 'import_modules',
            partial,
            replacementStartFromLineStart: replacementStart,
        };
    }

    const fromImport = /^\s*from\s+([\w.]+)\s+import\s+(.*)$/.exec(trimmed);
    if (fromImport) {
        const mod = fromImport[1];
        const tail = fromImport[2];
        const segments = tail.split(',').map((s) => s.trim()).filter((s) => s.length > 0);
        const partial = segments.length ? segments[segments.length - 1] : '';
        const replacementStart = trimmed.length - partial.length;
        return {
            kind: 'from_import_names',
            module: mod,
            partial,
            replacementStartFromLineStart: replacementStart,
        };
    }

    const fromOnly = /^\s*from\s+([\w.]*)$/.exec(trimmed);
    if (fromOnly) {
        const partial = fromOnly[1];
        const replacementStart = trimmed.length - partial.length;
        return {
            kind: 'from_module',
            partial,
            replacementStartFromLineStart: replacementStart,
        };
    }

    return null;
}

/**
 * @param {string} partial
 * @param {string[]} modules
 * @returns {CMCompletionOption[]}
 */
function filterModuleNames(partial, modules) {
    const p = partial.toLowerCase();
    /** @type {CMCompletionOption[]} */
    const out = [];
    for (const m of modules) {
        if (typeof m !== 'string') {
            continue;
        }
        if (!p || m.toLowerCase().startsWith(p)) {
            out.push({ label: m, type: 'namespace', detail: 'module', info: '' });
        }
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
}

/**
 * @param {string} partial
 * @param {unknown[]} methods
 */
function filterModuleMethods(partial, methods) {
    const p = partial.toLowerCase();
    /** @type {CMCompletionOption[]} */
    const out = [];
    if (!Array.isArray(methods)) {
        return out;
    }
    for (const row of methods) {
        if (!row || typeof row !== 'object') {
            continue;
        }
        const name = 'name' in row && typeof row.name === 'string' ? row.name : '';
        if (!isValidPythonIdentifier(name)) {
            continue;
        }
        if (!p || name.toLowerCase().startsWith(p)) {
            const typ = 'type' in row && typeof row.type === 'string' ? row.type : 'function';
            const doc = 'doc' in row && typeof row.doc === 'string' ? row.doc : '';
            const rowOpt = {
                label: name,
                type: mapDocTypeToCm(typ),
                detail: typ,
            };
            if (doc.trim().length > 0) {
                rowOpt.info = completionMarkdownInfo(doc);
            }
            out.push(rowOpt);
        }
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
}

/**
 * @param {string} partial
 * @param {{ name?: string, type?: string, description?: string }[]} stateFields
 */
function filterStateFields(partial, stateFields) {
    const p = partial.toLowerCase();
    /** @type {CMCompletionOption[]} */
    const out = [];
    for (const f of normalizedStateFieldRows(stateFields)) {
        const name = f.name;
        if (!p || name.toLowerCase().startsWith(p)) {
            const typ = f.type;
            const desc = f.description;
            const fieldOpt = {
                label: name,
                type: 'property',
                detail: typ,
            };
            if (desc.trim().length > 0) {
                fieldOpt.info = completionMarkdownInfo(desc);
            }
            out.push(fieldOpt);
        }
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
}

/**
 * @param {string} language
 * @param {string} partial
 * @param {string} namespace
 * @param {ReturnType<normalizeCatalogResponse>} catalog
 */
function filterCapabilityMethods(language, partial, namespace, catalog) {
    const p = partial.toLowerCase();
    /** @type {CMCompletionOption[]} */
    const out = [];
    for (const c of catalog.capabilities) {
        if (!c || typeof c !== 'object') {
            continue;
        }
        const ns = 'namespace' in c && typeof c.namespace === 'string' ? c.namespace : '';
        if (ns !== namespace) {
            continue;
        }
        const method = 'method' in c && typeof c.method === 'string' ? c.method : '';
        if (!isValidLanguageIdentifier(language, method)) {
            continue;
        }
        if (p && !method.toLowerCase().startsWith(p)) {
            continue;
        }
        const signature = 'signature' in c && typeof c.signature === 'string' ? c.signature : '';
        const title = 'title' in c && typeof c.title === 'string' ? c.title : '';
        const doc = 'documentation' in c && typeof c.documentation === 'string' ? c.documentation : '';
        const opt = {
            label: method,
            type: 'function',
            detail: signature || title || 'capability',
        };
        if (doc.trim().length > 0) {
            opt.info = completionMarkdownInfo(doc);
        }
        out.push(opt);
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
}

/**
 * @param {string} partial
 * @param {Map<string, CMCompletionOption>} symbolMap
 */
function filterSymbolMap(partial, symbolMap) {
    const p = partial.toLowerCase();
    /** @type {CMCompletionOption[]} */
    const out = [];
    for (const opt of symbolMap.values()) {
        if (!p || opt.label.toLowerCase().startsWith(p)) {
            out.push({ ...opt });
        }
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
}

/**
 * @param {string} partial
 * @param {string[]} keys
 */
function filterVariableKeys(partial, keys) {
    const p = partial.toLowerCase();
    /** @type {CMCompletionOption[]} */
    const out = [];
    const seen = new Set();
    for (const k of keys) {
        if (typeof k !== 'string' || !isValidPythonIdentifier(k)) {
            continue;
        }
        if (seen.has(k)) {
            continue;
        }
        seen.add(k);
        if (!p || k.toLowerCase().startsWith(p)) {
            out.push({ label: k, type: 'property', detail: 'variables', info: '' });
        }
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
}

/**
 * @param {unknown} name
 * @returns {string[]}
 */
function splitGlobalNames(name) {
    if (typeof name !== 'string' || name.length === 0) {
        return [];
    }
    return name
        .split(/[\/,]+/)
        .map((part) => part.trim())
        .filter((part) => part.length > 0);
}

/**
 * @param {unknown} language
 * @param {unknown} g
 * @returns {CMCompletionOption[]}
 */
function globalEntryToGenericOptions(language, g) {
    if (!g || typeof g !== 'object') {
        return [];
    }
    const rawName = 'name' in g && typeof g.name === 'string' ? g.name : '';
    const typeRaw = 'type' in g && typeof g.type === 'string' ? g.type : 'variable';
    const doc = 'doc' in g && typeof g.doc === 'string' ? g.doc : '';
    const out = [];
    for (const name of splitGlobalNames(rawName)) {
        if (!isValidLanguageIdentifier(language, name)) {
            continue;
        }
        const opt = {
            label: name,
            type: mapDocTypeToCm(typeRaw),
            detail: typeRaw,
        };
        if (doc.trim().length > 0) {
            opt.info = completionMarkdownInfo(doc);
        }
        out.push(opt);
    }
    return out;
}

/**
 * @param {string} docText
 * @param {number} pos
 */
function scanGenericFragment(docText, pos) {
    if (pos <= 0 || typeof docText !== 'string') {
        return { from: pos, chain: '', partial: '', completesAfterDot: false };
    }
    let i = pos - 1;
    while (i >= 0) {
        const ch = docText[i];
        if (/[A-Za-z0-9_$.]/.test(ch)) {
            i--;
            continue;
        }
        break;
    }
    const from = i + 1;
    const fragment = docText.slice(from, pos);
    if (fragment.endsWith('.')) {
        return { from, chain: fragment.slice(0, -1), partial: '', completesAfterDot: true };
    }
    const lastDot = fragment.lastIndexOf('.');
    if (lastDot >= 0) {
        const partial = fragment.slice(lastDot + 1);
        return {
            from: pos - partial.length,
            chain: fragment.slice(0, lastDot),
            partial,
            completesAfterDot: false,
        };
    }
    return { from, chain: '', partial: fragment, completesAfterDot: false };
}

/**
 * @param {string} partial
 * @param {CMCompletionOption[]} options
 */
function filterCompletionOptions(partial, options) {
    const p = partial.toLowerCase();
    const seen = new Set();
    const out = [];
    for (const opt of options) {
        if (!opt || typeof opt.label !== 'string' || opt.label.length === 0) {
            continue;
        }
        if (seen.has(opt.label)) {
            continue;
        }
        seen.add(opt.label);
        if (!p || opt.label.toLowerCase().startsWith(p)) {
            out.push({ ...opt });
        }
    }
    out.sort((a, b) => a.label.localeCompare(b.label));
    return out;
}

/**
 * @param {{ language: string, catalog: ReturnType<normalizeCatalogResponse> }} args
 */
function buildGenericSymbolOptions(args) {
    const language = typeof args.language === 'string' ? args.language : 'javascript';
    const catalog = args.catalog && typeof args.catalog === 'object' ? args.catalog : normalizeCatalogResponse({});
    const out = runtimeGlobalOptions(language);
    for (const row of [...catalog.globals, ...catalog.runtime_namespace_extras]) {
        out.push(...globalEntryToGenericOptions(language, row));
    }
    for (const name of catalog.builtins) {
        if (isValidLanguageIdentifier(language, name)) {
            out.push({ label: name, type: 'function', detail: 'builtin', info: '' });
        }
    }
    if (Array.isArray(catalog.platform_tools)) {
        for (const t of catalog.platform_tools) {
            if (!t || typeof t !== 'object') {
                continue;
            }
            const tid = 'tool_id' in t && typeof t.tool_id === 'string' ? t.tool_id : '';
            if (!isValidLanguageIdentifier(language, tid)) {
                continue;
            }
            const displayName = 'display_name' in t && typeof t.display_name === 'string' ? t.display_name : '';
            const desc = 'description' in t && typeof t.description === 'string' ? t.description : '';
            const opt = {
                label: tid,
                type: 'function',
                detail: displayName.length > 0 ? displayName : 'platform tool',
            };
            if (desc.trim().length > 0) {
                opt.info = completionMarkdownInfo(desc);
            }
            out.push(opt);
        }
    }
    for (const ns of catalog.capability_namespaces) {
        if (!ns || typeof ns !== 'object') {
            continue;
        }
        const name = 'name' in ns && typeof ns.name === 'string' ? ns.name : '';
        if (!isValidLanguageIdentifier(language, name)) {
            continue;
        }
        const type = 'type' in ns && typeof ns.type === 'string' ? ns.type : 'capability namespace';
        out.push({ label: name, type: 'namespace', detail: type, info: '' });
    }
    return out;
}

/**
 * @param {{ docText: string, pos: number, catalog: ReturnType<normalizeCatalogResponse>, variableKeys?: string[], explicit?: boolean }} args
 * @returns {{ from: number, options: CMCompletionOption[] } | null}
 */
export function buildPythonCompletions(args) {
    const docText = typeof args.docText === 'string' ? args.docText : '';
    const pos = typeof args.pos === 'number' ? args.pos : 0;
    const catalog = args.catalog && typeof args.catalog === 'object' ? args.catalog : normalizeCatalogResponse({});
    const variableKeys = Array.isArray(args.variableKeys)
        ? args.variableKeys.filter((k) => typeof k === 'string')
        : [];
    const explicit = args.explicit === true;

    const lineStart = docText.lastIndexOf('\n', pos - 1) + 1;
    const linePrefix = docText.slice(lineStart, pos);

    const imp = parseImportCompletion(linePrefix);
    if (imp && imp.kind === 'import_modules') {
        const fromAbs = lineStart + imp.replacementStartFromLineStart;
        const opts = filterModuleNames(imp.partial, catalog.modules);
        return opts.length === 0 ? null : { from: fromAbs, options: opts };
    }
    if (imp && imp.kind === 'from_module') {
        const fromAbs = lineStart + imp.replacementStartFromLineStart;
        const opts = filterModuleNames(imp.partial, catalog.modules);
        return opts.length === 0 ? null : { from: fromAbs, options: opts };
    }
    if (imp && imp.kind === 'from_import_names' && typeof imp.module === 'string' && imp.module.length > 0) {
        const methods = catalog.module_methods[imp.module];
        const fromAbs = lineStart + imp.replacementStartFromLineStart;
        const opts = filterModuleMethods(imp.partial, Array.isArray(methods) ? methods : []);
        return opts.length === 0 ? null : { from: fromAbs, options: opts };
    }

    const { from, chain, partial, completesAfterDot } = scanPythonFragment(docText, pos);
    if (!explicit && partial === '' && !completesAfterDot) {
        return null;
    }

    const symbolMap = buildGlobalSymbolMap(catalog, 'python');

    if (!chain || chain === '') {
        const opts = filterSymbolMap(partial, symbolMap);
        return opts.length === 0 ? null : { from, options: opts };
    }

    if (chain === 'state') {
        const opts = filterStateFields(partial, catalog.state_fields);
        return opts.length === 0 ? null : { from, options: opts };
    }

    if (chain === 'state.variables' || chain === 'variables') {
        const opts = filterVariableKeys(partial, variableKeys);
        return opts.length === 0 ? null : { from, options: opts };
    }

    const capabilityMethods = filterCapabilityMethods('python', partial, chain, catalog);
    if (capabilityMethods.length > 0) {
        return { from, options: capabilityMethods };
    }

    const methods = catalog.module_methods[chain];
    if (Array.isArray(methods) && methods.length > 0) {
        const opts = filterModuleMethods(partial, methods);
        return opts.length === 0 ? null : { from, options: opts };
    }

    return null;
}

/**
 * @param {{ language?: string, docText: string, pos: number, catalog: ReturnType<normalizeCatalogResponse>, variableKeys?: string[], explicit?: boolean }} args
 * @returns {{ from: number, options: CMCompletionOption[] } | null}
 */
export function buildCodeCompletions(args) {
    const language = typeof args.language === 'string' && args.language.length > 0 ? args.language : 'python';
    if (language === 'python') {
        return buildPythonCompletions(args);
    }
    const docText = typeof args.docText === 'string' ? args.docText : '';
    const pos = typeof args.pos === 'number' ? args.pos : 0;
    const catalog = args.catalog && typeof args.catalog === 'object' ? args.catalog : normalizeCatalogResponse({});
    const explicit = args.explicit === true;
    const { from, chain, partial, completesAfterDot } = scanGenericFragment(docText, pos);
    if (!explicit && partial.length === 0 && !completesAfterDot) {
        return null;
    }
    if (chain) {
        if (chain === 'state') {
            const opts = filterStateFields(partial, catalog.state_fields);
            return opts.length === 0 ? null : { from, options: opts };
        }
        if (chain === 'state.variables' || chain === 'variables') {
            const variableKeys = Array.isArray(args.variableKeys)
                ? args.variableKeys.filter((k) => typeof k === 'string')
                : [];
            const opts = filterVariableKeys(partial, variableKeys);
            return opts.length === 0 ? null : { from, options: opts };
        }
        const opts = filterCapabilityMethods(language, partial, chain, catalog);
        return opts.length === 0 ? null : { from, options: opts };
    }
    const opts = filterCompletionOptions(partial, buildGenericSymbolOptions({ language, catalog }));
    return opts.length === 0 ? null : { from, options: opts };
}

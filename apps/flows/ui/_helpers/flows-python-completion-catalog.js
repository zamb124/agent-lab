/**
 * Каталог автодополнения Python для flows-code-editor из ответа GET /flows/api/v1/code/completions.
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
 * @param {unknown} g
 */
function globalEntryToOption(g) {
    if (!g || typeof g !== 'object') {
        return null;
    }
    const name = 'name' in g && typeof g.name === 'string' ? g.name : '';
    if (!isValidPythonIdentifier(name)) {
        return null;
    }
    const typeRaw = 'type' in g && typeof g.type === 'string' ? g.type : 'variable';
    const doc = 'doc' in g && typeof g.doc === 'string' ? g.doc : '';
    const opt = {
        label: name,
        type: mapDocTypeToCm(typeRaw),
        detail: typeRaw,
    };
    if (doc.trim().length > 0) {
        opt.info = completionMarkdownInfo(doc);
    }
    return opt;
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
 * @param {{ globals?: unknown[], runtime_namespace_extras?: unknown[], builtins?: string[], platform_tools?: unknown[] }} catalog
 * @returns {Map<string, CMCompletionOption>}
 */
export function buildGlobalSymbolMap(catalog) {
    /** @type {Map<string, CMCompletionOption>} */
    const map = new Map();

    const pushGlobals = (arr) => {
        if (!Array.isArray(arr)) {
            return;
        }
        for (const g of arr) {
            const opt = globalEntryToOption(g);
            if (opt && !map.has(opt.label)) {
                map.set(opt.label, opt);
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
    for (const f of stateFields) {
        if (!f || typeof f !== 'object') {
            continue;
        }
        const name = 'name' in f && typeof f.name === 'string' ? f.name : '';
        if (!isValidPythonIdentifier(name)) {
            continue;
        }
        if (!p || name.toLowerCase().startsWith(p)) {
            const typ = 'type' in f && typeof f.type === 'string' ? f.type : '';
            const desc =
                'description' in f && typeof f.description === 'string' ? f.description : '';
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

    const symbolMap = buildGlobalSymbolMap(catalog);

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

    const methods = catalog.module_methods[chain];
    if (Array.isArray(methods) && methods.length > 0) {
        const opts = filterModuleMethods(partial, methods);
        return opts.length === 0 ? null : { from, options: opts };
    }

    return null;
}

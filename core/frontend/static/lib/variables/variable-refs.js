/**
 * Pure helpers for @var: / @state: / {brace} refs in flow editors.
 * No DOM / HTTP — preview values come from parent props only.
 */

/** @typedef {'var' | 'state' | 'brace'} VariableRefKind */
/** @typedef {'resolved' | 'undefined' | 'runtime_only'} VariablePreviewStatus */

/**
 * @typedef {object} VariableCatalogEntry
 * @property {string} name
 * @property {string} [type]
 * @property {string} [source]
 * @property {boolean} [hasValue]
 * @property {'var' | 'state'} [kind]
 */

/**
 * @typedef {object} VariablePreviewLookup
 * @property {VariablePreviewStatus} status
 * @property {unknown} [value]
 */

/**
 * @typedef {object} ScannedRef
 * @property {VariableRefKind} kind
 * @property {string} path
 * @property {number} from
 * @property {number} to
 * @property {string} raw
 */

export const AT_VAR_PATTERN = /@var:([\w.]+)/g;
export const AT_STATE_PATTERN = /@state:([\w.]+)/g;

const STATE_PREVIEW_KEYS = Object.freeze([
    'content',
    'response',
    'context',
    'files',
    'variables',
    'nodes',
    'store',
]);

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
 */
function isPlainObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

/**
 * Unwrap flow variable nodes shaped as `{ value: ... }`.
 * @param {unknown} value
 * @returns {unknown}
 */
export function unwrapVariableNode(value) {
    if (isPlainObject(value) && Object.hasOwn(value, 'value')) {
        return value.value;
    }
    return value;
}

/**
 * @param {unknown} root
 * @param {string} path
 * @returns {{ found: boolean, value: unknown }}
 */
export function lookupPath(root, path) {
    if (typeof path !== 'string' || path.length === 0) {
        return { found: false, value: undefined };
    }
    if (!isPlainObject(root) && !Array.isArray(root)) {
        return { found: false, value: undefined };
    }

    const parts = path.split('.');
    let current = /** @type {unknown} */ (root);

    for (const part of parts) {
        if (current === null || current === undefined) {
            return { found: false, value: undefined };
        }
        if (typeof current !== 'object') {
            return { found: false, value: undefined };
        }

        const record = /** @type {Record<string, unknown>} */ (current);
        if (isPlainObject(record[part]) && Object.hasOwn(/** @type {Record<string, unknown>} */ (record[part]), 'value')) {
            current = /** @type {Record<string, unknown>} */ (record[part]).value;
            continue;
        }
        if (Object.hasOwn(record, part) || part in record) {
            current = record[part];
            continue;
        }
        return { found: false, value: undefined };
    }

    return { found: true, value: current };
}

/**
 * @param {string} path
 * @param {unknown} values
 * @returns {boolean}
 */
export function pathExistsInValues(path, values) {
    return lookupPath(values, path).found;
}

/**
 * @param {string} path
 * @param {unknown} catalog
 * @returns {VariableCatalogEntry | null}
 */
export function findCatalogEntry(path, catalog) {
    if (!Array.isArray(catalog) || typeof path !== 'string' || path.length === 0) {
        return null;
    }
    const root = path.split('.', 1)[0];
    for (const entry of catalog) {
        if (!entry || typeof entry !== 'object') continue;
        const name = /** @type {Record<string, unknown>} */ (entry).name;
        if (typeof name === 'string' && name === root) {
            return /** @type {VariableCatalogEntry} */ (entry);
        }
    }
    return null;
}

/**
 * @param {string} path
 * @param {{
 *   kind: VariableRefKind,
 *   values?: unknown,
 *   statePreview?: unknown,
 *   catalog?: unknown,
 * }} options
 * @returns {VariablePreviewLookup}
 */
export function lookupPreviewValue(path, options) {
    if (typeof path !== 'string' || path.length === 0) {
        throw new TypeError('lookupPreviewValue: path string required');
    }
    if (options === null || typeof options !== 'object') {
        throw new TypeError('lookupPreviewValue: options object required');
    }
    const { kind } = options;
    if (kind !== 'var' && kind !== 'state' && kind !== 'brace') {
        throw new TypeError(`lookupPreviewValue: unsupported kind ${String(kind)}`);
    }

    if (kind === 'state') {
        const hit = lookupPath(options.statePreview, path);
        if (hit.found) {
            return { status: 'resolved', value: hit.value };
        }
        return { status: 'runtime_only' };
    }

    const hit = lookupPath(options.values, path);
    if (hit.found) {
        return { status: 'resolved', value: hit.value };
    }

    const entry = findCatalogEntry(path, options.catalog);
    if (entry) {
        if (entry.hasValue === false) {
            return { status: 'runtime_only' };
        }
        return { status: 'runtime_only' };
    }

    return { status: 'undefined' };
}

/**
 * @param {string} text
 * @returns {ScannedRef[]}
 */
export function scanAtRefs(text) {
    if (typeof text !== 'string') {
        throw new TypeError('scanAtRefs: text string required');
    }
    /** @type {ScannedRef[]} */
    const refs = [];
    for (const match of text.matchAll(AT_VAR_PATTERN)) {
        const raw = match[0];
        const path = match[1];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'var', path, from, to: from + raw.length, raw });
    }
    for (const match of text.matchAll(AT_STATE_PATTERN)) {
        const raw = match[0];
        const path = match[1];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'state', path, from, to: from + raw.length, raw });
    }
    refs.sort((a, b) => a.from - b.from);
    return refs;
}

/**
 * Brace refs for LLM prompts: `{name}`, `{?name}`, `{name|default}`, `{for x in list}`, `{endfor}`.
 * @param {string} text
 * @returns {ScannedRef[]}
 */
export function scanBraceRefs(text) {
    if (typeof text !== 'string') {
        throw new TypeError('scanBraceRefs: text string required');
    }
    /** @type {ScannedRef[]} */
    const refs = [];

    const forRegex = /\{for\s+(\w+)\s+in\s+([\w.]+)\}/g;
    for (const match of text.matchAll(forRegex)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'brace', path: match[2], from, to: from + raw.length, raw });
    }

    const endforRegex = /\{endfor\}/g;
    for (const match of text.matchAll(endforRegex)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'brace', path: 'endfor', from, to: from + raw.length, raw });
    }

    const optionalWithDefault = /\{\?([\w.]+)\|([^}]+)\}/g;
    for (const match of text.matchAll(optionalWithDefault)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'brace', path: match[1], from, to: from + raw.length, raw });
    }

    const optional = /\{\?([\w.]+)\}/g;
    for (const match of text.matchAll(optional)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'brace', path: match[1], from, to: from + raw.length, raw });
    }

    const withDefault = /\{([\w.]+)\|([^}]+)\}/g;
    for (const match of text.matchAll(withDefault)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'brace', path: match[1], from, to: from + raw.length, raw });
    }

    const required = /\{([\w.]+)\}/g;
    for (const match of text.matchAll(required)) {
        const path = match[1];
        if (path === 'endfor' || path.startsWith('for ') || path.startsWith('?')) continue;
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'brace', path, from, to: from + raw.length, raw });
    }

    refs.sort((a, b) => a.from - b.from);
    return refs;
}

/**
 * Top-level ExecutionState fields used for `@state:` hover preview.
 * @param {unknown} executionState
 * @returns {Record<string, unknown>}
 */
export function buildExecutionStatePreview(executionState) {
    if (!isPlainObject(executionState)) {
        return {};
    }
    /** @type {Record<string, unknown>} */
    const preview = {};
    for (const key of STATE_PREVIEW_KEYS) {
        if (Object.hasOwn(executionState, key)) {
            preview[key] = executionState[key];
        }
    }
    return preview;
}

/**
 * @param {unknown} dataflowNode
 * @returns {string[]}
 */
export function collectStatePathsFromDataflow(dataflowNode) {
    /** @type {Set<string>} */
    const paths = new Set(['content', 'response']);
    if (!isPlainObject(dataflowNode)) {
        return [...paths];
    }
    const incoming = dataflowNode.incoming_state;
    if (!Array.isArray(incoming)) {
        return [...paths];
    }
    for (const descriptor of incoming) {
        if (!isPlainObject(descriptor)) continue;
        const path = descriptor.path;
        if (typeof path === 'string' && path.length > 0) {
            paths.add(path);
        }
    }
    return [...paths].sort((a, b) => a.localeCompare(b));
}

/**
 * Flatten object keys into dotted paths for autocomplete (one level of nesting max for objects).
 * @param {unknown} root
 * @param {string} [prefix]
 * @param {number} [depth]
 * @returns {string[]}
 */
export function flattenPreviewPaths(root, prefix = '', depth = 0) {
    if (!isPlainObject(root) || depth > 2) {
        return prefix ? [prefix] : [];
    }
    /** @type {string[]} */
    const paths = [];
    for (const [key, value] of Object.entries(root)) {
        const full = prefix ? `${prefix}.${key}` : key;
        paths.push(full);
        const unwrapped = unwrapVariableNode(value);
        if (isPlainObject(unwrapped) && !Array.isArray(unwrapped)) {
            paths.push(...flattenPreviewPaths(unwrapped, full, depth + 1));
        }
    }
    return paths;
}

/**
 * Pure helpers for @var: / @state: / {brace} refs in flow editors.
 * No DOM / HTTP — preview values come from parent props only.
 */

export type VariableRefKind = 'var' | 'state' | 'brace';
export type VariablePreviewStatus = 'resolved' | 'undefined' | 'runtime_only';

export interface VariableCatalogEntry {
    name: string;
    type?: string;
    source?: string;
    hasValue?: boolean;
    kind?: 'var' | 'state';
}

export interface VariablePreviewLookup {
    status: VariablePreviewStatus;
    value?: unknown;
}

export interface ScannedRef {
    kind: VariableRefKind;
    path: string;
    from: number;
    to: number;
    raw: string;
}

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

function isPlainObject(value: unknown): value is Record<string, unknown> {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function unwrapVariableNode(value: unknown): unknown {
    if (isPlainObject(value) && Object.hasOwn(value, 'value')) {
        return value.value;
    }
    return value;
}

export function lookupPath(root: unknown, path: string): { found: boolean; value: unknown } {
    if (typeof path !== 'string' || path.length === 0) {
        return { found: false, value: undefined };
    }
    if (!isPlainObject(root) && !Array.isArray(root)) {
        return { found: false, value: undefined };
    }

    const parts = path.split('.');
    let current: unknown = root;

    for (const part of parts) {
        if (current === null || current === undefined) {
            return { found: false, value: undefined };
        }
        if (typeof current !== 'object') {
            return { found: false, value: undefined };
        }

        if (Array.isArray(current)) {
            if (!(part in current)) {
                return { found: false, value: undefined };
            }
            const items: unknown[] = [];
            for (const item of current) items.push(item);
            const index = Number(part);
            if (!Number.isInteger(index) || String(index) !== part || index < 0) {
                current = part === 'length' ? current.length : undefined;
                continue;
            }
            const child = items[index];
            if (isPlainObject(child) && Object.hasOwn(child, 'value')) {
                current = child.value;
                continue;
            }
            current = child;
            continue;
        }
        if (!isPlainObject(current)) {
            return { found: false, value: undefined };
        }
        const child = current[part];
        if (isPlainObject(child) && Object.hasOwn(child, 'value')) {
            current = child.value;
            continue;
        }
        if (Object.hasOwn(current, part) || part in current) {
            current = child;
            continue;
        }
        return { found: false, value: undefined };
    }

    return { found: true, value: current };
}

export function pathExistsInValues(path: string, values: unknown): boolean {
    return lookupPath(values, path).found;
}

function catalogEntry(value: unknown): VariableCatalogEntry | null {
    if (!isPlainObject(value)) return null;
    const name = value.name;
    if (typeof name !== 'string' || name.length === 0) return null;
    const entry: VariableCatalogEntry = { name };
    if (typeof value.type === 'string') entry.type = value.type;
    if (typeof value.source === 'string') entry.source = value.source;
    if (typeof value.hasValue === 'boolean') entry.hasValue = value.hasValue;
    if (value.kind === 'var' || value.kind === 'state') entry.kind = value.kind;
    return entry;
}

export function findCatalogEntry(path: string, catalog: unknown): VariableCatalogEntry | null {
    if (!Array.isArray(catalog) || typeof path !== 'string' || path.length === 0) {
        return null;
    }
    const root = path.split('.', 1)[0];
    let rootMatch: VariableCatalogEntry | null = null;
    let childOfRootMatch: VariableCatalogEntry | null = null;
    for (const rawEntry of catalog) {
        const entry = catalogEntry(rawEntry);
        if (entry === null) continue;
        const name = entry.name;
        if (name === path) {
            return entry;
        }
        if (name === root) {
            rootMatch = entry;
            continue;
        }
        if (path === root && name.startsWith(`${root}.`)) {
            childOfRootMatch = entry;
        }
    }
    if (rootMatch) {
        return rootMatch;
    }
    if (path === root) {
        return childOfRootMatch;
    }
    return null;
}

export function lookupPreviewValue(path: string, options: {
    kind: VariableRefKind;
    values?: unknown;
    statePreview?: unknown;
    catalog?: unknown;
}): VariablePreviewLookup {
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

export function scanAtRefs(text: string): ScannedRef[] {
    if (typeof text !== 'string') {
        throw new TypeError('scanAtRefs: text string required');
    }
    const refs: ScannedRef[] = [];
    for (const match of text.matchAll(AT_VAR_PATTERN)) {
        const raw = match[0];
        const path = match[1];
        if (typeof path !== 'string') continue;
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'var', path, from, to: from + raw.length, raw });
    }
    for (const match of text.matchAll(AT_STATE_PATTERN)) {
        const raw = match[0];
        const path = match[1];
        if (typeof path !== 'string') continue;
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'state', path, from, to: from + raw.length, raw });
    }
    refs.sort((a, b) => a.from - b.from);
    return refs;
}

export function scanBraceRefs(text: string): ScannedRef[] {
    if (typeof text !== 'string') {
        throw new TypeError('scanBraceRefs: text string required');
    }
    const refs: ScannedRef[] = [];

    const forRegex = /\{for\s+(\w+)\s+in\s+([\w.]+)\}/g;
    for (const match of text.matchAll(forRegex)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        const path = match[2];
        if (typeof path !== 'string') continue;
        refs.push({ kind: 'brace', path, from, to: from + raw.length, raw });
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
        const path = match[1];
        if (typeof path !== 'string') continue;
        refs.push({ kind: 'brace', path, from, to: from + raw.length, raw });
    }

    const optional = /\{\?([\w.]+)\}/g;
    for (const match of text.matchAll(optional)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        const path = match[1];
        if (typeof path !== 'string') continue;
        refs.push({ kind: 'brace', path, from, to: from + raw.length, raw });
    }

    const withDefault = /\{([\w.]+)\|([^}]+)\}/g;
    for (const match of text.matchAll(withDefault)) {
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        const path = match[1];
        if (typeof path !== 'string') continue;
        refs.push({ kind: 'brace', path, from, to: from + raw.length, raw });
    }

    const required = /\{([\w.]+)\}/g;
    for (const match of text.matchAll(required)) {
        const path = match[1];
        if (typeof path !== 'string' || path === 'endfor' || path.startsWith('for ') || path.startsWith('?')) continue;
        const raw = match[0];
        const from = match.index;
        if (typeof from !== 'number') continue;
        refs.push({ kind: 'brace', path, from, to: from + raw.length, raw });
    }

    refs.sort((a, b) => a.from - b.from);
    return refs;
}

export function buildExecutionStatePreview(executionState: unknown): Record<string, unknown> {
    if (!isPlainObject(executionState)) {
        return {};
    }
    const preview: Record<string, unknown> = {};
    for (const key of STATE_PREVIEW_KEYS) {
        if (Object.hasOwn(executionState, key)) {
            preview[key] = executionState[key];
        }
    }
    return preview;
}

export function collectStatePathsFromDataflow(dataflowNode: unknown): string[] {
    const paths = new Set<string>(['content', 'response']);
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

export function flattenPreviewPaths(root: unknown, prefix = '', depth = 0): string[] {
    if (!isPlainObject(root) || depth > 2) {
        return prefix ? [prefix] : [];
    }
    const paths: string[] = [];
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

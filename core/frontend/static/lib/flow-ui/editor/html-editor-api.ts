/**
 * Чистая логика редактора блока ``html``: API шпаргалки, test-state, сниппеты, ширины кадра.
 * Тексты сниппетов — i18n ``interface_editor.html_snippet_*``; этот модуль знает только id и merge.
 */

export const HTML_EDITOR_VIEWPORTS = Object.freeze({ desktop: 1180, tablet: 820, mobile: 390 });
export const HTML_EDITOR_LIVE_MS = 300;

export const FLOW_UI_API = Object.freeze([
    { label: 'flowUi.state', detail: 'object', signature: 'flowUi.state', key: 'state' },
    { label: 'flowUi.onChange(', detail: '(state) => void', signature: 'flowUi.onChange((state) => { ... })', key: 'on_change' },
    { label: 'flowUi.send(', detail: '(action, payload?)', signature: "flowUi.send('action', { ... })", key: 'send' },
    { label: 'flowUi.setValue(', detail: '(value)', signature: 'flowUi.setValue(value)', key: 'set_value' },
    { label: 'flowUi.resize()', detail: '()', signature: 'flowUi.resize()', key: 'resize' },
    { label: 'flowUi.openUrl(', detail: '(url)', signature: "flowUi.openUrl('https://...')", key: 'open_url' },
    { label: 'data-bind=""', detail: 'attr', signature: 'data-bind="path"', key: 'data_bind' },
    { label: 'data-show=""', detail: 'attr', signature: 'data-show="path"', key: 'data_show' },
]);

export const HTML_EDITOR_SNIPPETS = Object.freeze([
    { id: 'bind' },
    { id: 'show' },
    { id: 'list' },
    { id: 'send' },
    { id: 'value' },
    { id: 'card', kitchen: true },
]);

export function parseTestState(text: string): { ok: boolean; error: string; value: Record<string, unknown> | null } {
    try {
        const value = JSON.parse(text) as unknown;
        if (value === null || typeof value !== 'object' || Array.isArray(value)) {
            return { ok: false, error: 'test state must be a JSON object', value: null };
        }
        return { ok: true, error: '', value: value as Record<string, unknown> };
    } catch (error) {
        return { ok: false, error: error instanceof Error ? error.message : String(error), value: null };
    }
}

export function mergeTestState(current: unknown, patch: unknown): Record<string, unknown> {
    const base = current && typeof current === 'object' && !Array.isArray(current) ? current as Record<string, unknown> : {};
    const extra = patch && typeof patch === 'object' && !Array.isArray(patch) ? patch as Record<string, unknown> : {};
    return { ...base, ...extra };
}

export function setValueAtPath(target: unknown, path: unknown, value: unknown): Record<string, unknown> {
    if (typeof path !== 'string' || path === '') throw new Error('html editor: path is required');
    const root = target && typeof target === 'object' && !Array.isArray(target) ? target as Record<string, unknown> : {};
    const segments = path.split('.');
    let cursor = root;
    for (const segment of segments.slice(0, -1)) {
        if (cursor[segment] === null || typeof cursor[segment] !== 'object') cursor[segment] = {};
        cursor = cursor[segment] as Record<string, unknown>;
    }
    cursor[segments[segments.length - 1] as string] = value;
    return root;
}

export function valueAtSimplePath(state: unknown, path: unknown): unknown {
    if (state === null || typeof state !== 'object') return undefined;
    return String(path).split('.').reduce((acc: unknown, key: string) => (acc && typeof acc === 'object' ? (acc as Record<string, unknown>)[key] : undefined), state);
}

export function fieldControlKind(value: unknown): 'boolean' | 'number' | 'json' | 'string' {
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    if (Array.isArray(value) || (value !== null && typeof value === 'object')) return 'json';
    return 'string';
}

export function fieldEditorValue(value: unknown): unknown {
    const kind = fieldControlKind(value);
    if (kind === 'json') return JSON.stringify(value, null, 2);
    if (value === null || value === undefined) return '';
    return value;
}

export function parseFieldEditorValue(kind: string, raw: unknown): unknown {
    if (kind === 'boolean') return raw === true;
    if (kind === 'number') {
        const next = typeof raw === 'number' ? raw : Number(raw);
        if (!Number.isFinite(next)) throw new Error('html editor: number field');
        return next;
    }
    if (kind === 'json') {
        const parsed = JSON.parse(typeof raw === 'string' ? raw : JSON.stringify(raw));
        return parsed;
    }
    return raw === null || raw === undefined ? '' : String(raw);
}

export function previewBlock<T extends { block_id?: unknown }>(block: T, source: unknown, cache: (T & { source?: unknown }) | null | undefined): T & { source?: unknown } {
    if (cache && cache.block_id === block.block_id && cache.source === source) return cache;
    return { ...block, source };
}

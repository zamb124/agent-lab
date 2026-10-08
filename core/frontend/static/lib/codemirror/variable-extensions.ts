/**
 * Shared CodeMirror 6 extensions for @var: / @state: / {brace} highlighting,
 * hover preview, and autocomplete. Consumers: platform-markdown-editor,
 * platform-variable-input.
 */

import {
    findCatalogEntry,
    flattenPreviewPaths,
    lookupPath,
    lookupPreviewValue,
    pathExistsInValues,
} from '../variables/variable-refs.js';

export type VariableSyntaxMode = 'at-ref' | 'brace' | 'both';

export interface VariableExtensionsOptions {
    syntax: VariableSyntaxMode;
    getValues: () => Record<string, unknown>;
    getStatePreview?: () => Record<string, unknown>;
    getCatalog: () => Array<{ name: string; type?: string; source?: string; hasValue?: boolean; kind?: string }>;
    getStatePaths?: () => string[];
    t: (key: string) => string;
}

/** Minimal structural surface of the vendored codemirror-bundle.js used by this module. */
export interface CmRange {
    from: number;
}

export interface CmDecoration {
    range(from: number, to: number): CmRange;
}

export interface CmViewLike {
    state: { doc: { toString(): string; length: number } };
}

export interface CmUpdateLike {
    docChanged: boolean;
    viewportChanged: boolean;
    view: CmViewLike;
}

export interface CmTooltip {
    pos: number;
    end: number;
    above: boolean;
    create(): { dom: HTMLElement };
}

export interface CmPluginInstance {
    decorations: unknown;
    update(update: CmUpdateLike): void;
}

export interface CmEditorViewLike extends CmViewLike {
    state: {
        doc: { toString(): string; length: number };
        readOnly: boolean;
        replaceSelection(text: string): unknown;
    };
    dispatch(spec: object): void;
    destroy(): void;
    requestMeasure(): void;
}

export interface CmCompartmentLike {
    of(extension: unknown): unknown;
    reconfigure(extension: unknown): unknown;
}

export interface CmTransactionLike {
    docChanged: boolean;
    newDoc: { lines: number; toString(): string };
    newSelection: unknown;
    startState: { doc: { length: number } };
    state: { doc: { toString(): string } };
    changes: {
        iterChanges(
            fn: (fromA: number, toA: number, fromB: number, toB: number, inserted: { toString(): string }) => void,
        ): void;
    };
}

export interface CmModule {
    Decoration: {
        mark(spec: { class: string }): CmDecoration;
        set(ranges: CmRange[], sort?: boolean): unknown;
    };
    ViewPlugin: {
        fromClass(
            cls: new (view: CmViewLike) => CmPluginInstance,
            spec?: { decorations: (v: CmPluginInstance) => unknown },
        ): unknown;
    };
    hoverTooltip(fn: (view: CmViewLike, pos: number) => CmTooltip | null): unknown;
    autocompletion(opts: { override: unknown[] }): unknown;
    EditorState: {
        create(config: { doc?: string; extensions?: unknown[] }): unknown;
        transactionFilter: { of(fn: (tr: CmTransactionLike) => unknown): unknown };
        readOnly: { of(value: boolean): unknown };
        tabSize: { of(value: number): unknown };
    };
    EditorView: {
        new (config: { state: unknown; parent: Element }): CmEditorViewLike;
        theme(spec: Record<string, unknown>, options?: { dark?: boolean }): unknown;
        updateListener: { of(fn: (update: { docChanged: boolean; state: { doc: { toString(): string } } }) => void): unknown };
        lineWrapping: unknown;
    };
    Compartment: new () => CmCompartmentLike;
    history(): unknown;
    keymap: { of(bindings: unknown[]): unknown };
    defaultKeymap: unknown[];
    historyKeymap: unknown[];
    lineNumbers(): unknown;
    json(): unknown;
    bracketMatching(): unknown;
    indentOnInput(): unknown;
    syntaxHighlighting(style: unknown, options?: { fallback?: boolean }): unknown;
    defaultHighlightStyle: unknown;
    oneDark?: unknown;
}

interface HighlighterContext {
    includeAtRef: boolean;
    includeBrace: boolean;
    getValues: () => Record<string, unknown>;
    getCatalog: () => unknown[];
}

interface TooltipContext {
    includeAtRef: boolean;
    includeBrace: boolean;
    getValues: () => Record<string, unknown>;
    getStatePreview: () => Record<string, unknown>;
    getCatalog: () => unknown[];
    t: (key: string) => string;
}

interface CompletionContext {
    includeAtRef: boolean;
    includeBrace: boolean;
    getValues: () => Record<string, unknown>;
    getStatePreview: () => Record<string, unknown>;
    getCatalog: () => Array<{ name: string; type?: string; source?: string; kind?: string }>;
    getStatePaths: () => string[];
}

interface CompletionMatch {
    text: string;
    from: number;
}

interface CompletionContextObj {
    matchBefore(regexp: RegExp): CompletionMatch | null;
}

interface CompletionOption {
    label: string;
    type: string;
    detail: string;
}

interface CompletionResult {
    from: number;
    options: CompletionOption[];
}

export function createVariableExtensions(cm: CmModule, options: VariableExtensionsOptions): unknown[] {
    if (cm === null || typeof cm !== 'object') {
        throw new TypeError('createVariableExtensions: cm module required');
    }
    if (options === null || typeof options !== 'object') {
        throw new TypeError('createVariableExtensions: options required');
    }
    const { syntax, getValues, getCatalog, t } = options;
    if (syntax !== 'at-ref' && syntax !== 'brace' && syntax !== 'both') {
        throw new TypeError(`createVariableExtensions: unsupported syntax ${String(syntax)}`);
    }
    if (typeof getValues !== 'function') {
        throw new TypeError('createVariableExtensions: getValues required');
    }
    if (typeof getCatalog !== 'function') {
        throw new TypeError('createVariableExtensions: getCatalog required');
    }
    if (typeof t !== 'function') {
        throw new TypeError('createVariableExtensions: t required');
    }

    const getStatePreview = typeof options.getStatePreview === 'function'
        ? options.getStatePreview
        : () => ({});
    const getStatePaths = typeof options.getStatePaths === 'function'
        ? options.getStatePaths
        : () => [];

    const includeAtRef = syntax === 'at-ref' || syntax === 'both';
    const includeBrace = syntax === 'brace' || syntax === 'both';

    const highlighter = _createHighlighter(cm, {
        includeAtRef,
        includeBrace,
        getValues,
        getCatalog,
    });
    const tooltip = _createTooltip(cm, {
        includeAtRef,
        includeBrace,
        getValues,
        getStatePreview,
        getCatalog,
        t,
    });
    const completionSource = _createCompletionSource({
        includeAtRef,
        includeBrace,
        getValues,
        getStatePreview,
        getCatalog,
        getStatePaths,
    });

    return [
        highlighter,
        tooltip,
        cm.autocompletion({ override: [completionSource] }),
    ];
}

export function refreshVariableDecorations(editorView: {
    state: { doc: { length: number } };
    dispatch: (spec: object) => void;
}): void {
    if (!editorView || typeof editorView.dispatch !== 'function') {
        throw new TypeError('refreshVariableDecorations: EditorView required');
    }
    const docLength = editorView.state.doc.length;
    editorView.dispatch({
        changes: { from: docLength, to: docLength, insert: ' ' },
    });
    editorView.dispatch({
        changes: { from: docLength, to: docLength + 1, insert: '' },
    });
}

function _createHighlighter(cm: CmModule, ctx: HighlighterContext) {
    const decoClasses = {
        required: cm.Decoration.mark({ class: 'cm-variable-required' }),
        optional: cm.Decoration.mark({ class: 'cm-variable-optional' }),
        default: cm.Decoration.mark({ class: 'cm-variable-default' }),
        interfaceField: cm.Decoration.mark({ class: 'cm-variable-interface' }),
        undefined: cm.Decoration.mark({ class: 'cm-variable-undefined' }),
        forKeyword: cm.Decoration.mark({ class: 'cm-for-keyword' }),
        loopVar: cm.Decoration.mark({ class: 'cm-loop-var' }),
        refVar: cm.Decoration.mark({ class: 'cm-ref-var' }),
        refState: cm.Decoration.mark({ class: 'cm-ref-state' }),
    };

    class VariableHighlighter implements CmPluginInstance {
        decorations: unknown;

        constructor(view: CmViewLike) {
            this.decorations = this.buildDecorations(view);
        }

        update(update: CmUpdateLike) {
            if (update.docChanged || update.viewportChanged) {
                this.decorations = this.buildDecorations(update.view);
            }
        }

        buildDecorations(view: CmViewLike) {
            const builder: CmRange[] = [];
            const doc = view.state.doc.toString();
            const values = ctx.getValues();
            const catalog = ctx.getCatalog();
            const loopVars: Set<string> = ctx.includeBrace ? _extractLoopVariables(doc) : new Set<string>();

            if (ctx.includeBrace) {
                const forRegex = /\{for\s+(\w+)\s+in\s+([\w.]+)\}/g;
                let match;
                while ((match = forRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.forKeyword.range(match.index, match.index + match[0].length));
                    const listVar = match[2];
                    if (typeof listVar !== 'string') continue;
                    if (!_variableKnown(listVar, values, catalog) && !loopVars.has(listVar)) {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }

                const endforRegex = /\{endfor\}/g;
                while ((match = endforRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.forKeyword.range(match.index, match.index + match[0].length));
                }
            }

            if (ctx.includeAtRef) {
                const refVarRegex = /@var:([\w.]+)/g;
                let match;
                while ((match = refVarRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    if (typeof varName !== 'string') continue;
                    builder.push(decoClasses.refVar.range(match.index, match.index + match[0].length));
                    if (!_variableKnown(varName, values, catalog)) {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }

                const refStateRegex = /@state:([\w.]+)/g;
                while ((match = refStateRegex.exec(doc)) !== null) {
                    const statePath = match[1];
                    if (typeof statePath !== 'string') continue;
                    const mark = _isInterfacePath(statePath, catalog) ? decoClasses.interfaceField : decoClasses.refState;
                    builder.push(mark.range(match.index, match.index + match[0].length));
                }
            }

            if (ctx.includeBrace) {
                const optionalWithDefaultRegex = /\{\?([\w.]+)\|([^}]+)\}/g;
                let match;
                while ((match = optionalWithDefaultRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    if (typeof varName !== 'string') continue;
                    const mark = _isInterfacePath(varName, catalog) ? decoClasses.interfaceField : decoClasses.optional;
                    builder.push(mark.range(match.index, match.index + match[0].length));
                }

                const optionalRegex = /\{\?([\w.]+)\}/g;
                while ((match = optionalRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    if (typeof varName !== 'string') continue;
                    const mark = _isInterfacePath(varName, catalog) ? decoClasses.interfaceField : decoClasses.optional;
                    builder.push(mark.range(match.index, match.index + match[0].length));
                }

                const defaultRegex = /\{([\w.]+)\|([^}]+)\}/g;
                while ((match = defaultRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    if (typeof varName !== 'string') continue;
                    const mark = _isInterfacePath(varName, catalog) ? decoClasses.interfaceField : decoClasses.default;
                    builder.push(mark.range(match.index, match.index + match[0].length));
                    if (
                        !_variableKnown(varName, values, catalog)
                        && !loopVars.has(varName)
                        && !_isLoopProperty(varName, loopVars)
                    ) {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }

                const requiredRegex = /\{([\w.]+)\}/g;
                while ((match = requiredRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    if (typeof varName !== 'string') continue;
                    if (varName === 'endfor' || varName.startsWith('for ') || varName.startsWith('?')) continue;

                    const isLoopVar = loopVars.has(varName) || _isLoopProperty(varName, loopVars);
                    if (isLoopVar) {
                        builder.push(decoClasses.loopVar.range(match.index, match.index + match[0].length));
                    } else if (_isInterfacePath(varName, catalog)) {
                        builder.push(decoClasses.interfaceField.range(match.index, match.index + match[0].length));
                    } else if (_variableKnown(varName, values, catalog)) {
                        builder.push(decoClasses.required.range(match.index, match.index + match[0].length));
                    } else {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }
            }

            builder.sort((a, b) => a.from - b.from);
            return cm.Decoration.set(builder, true);
        }
    }

    return cm.ViewPlugin.fromClass(VariableHighlighter, {
        decorations: (v) => v.decorations,
    });
}

function _createTooltip(cm: CmModule, ctx: TooltipContext) {
    return cm.hoverTooltip((view: CmViewLike, pos: number): CmTooltip | null => {
        const doc = view.state.doc.toString();
        const patterns: Array<{ regexp: RegExp; type: 'variable' | 'var_ref' | 'state_ref' }> = [];
        if (ctx.includeBrace) {
            patterns.push({ regexp: /\{\??[\w.]+(?:\|[^}]*)?\}/g, type: 'variable' });
        }
        if (ctx.includeAtRef) {
            patterns.push({ regexp: /@var:[\w.]+/g, type: 'var_ref' });
            patterns.push({ regexp: /@state:[\w.]+/g, type: 'state_ref' });
        }

        for (const { regexp, type } of patterns) {
            regexp.lastIndex = 0;
            let match;
            while ((match = regexp.exec(doc)) !== null) {
                const start = match.index;
                const end = start + match[0].length;
                if (pos < start || pos > end) continue;

                let varName = match[0];
                let kind: 'var' | 'state' | 'brace' = 'brace';
                if (type === 'variable') {
                    varName = varName.replace(/^\{\??/, '').replace(/(\|[^}]*)?\}$/, '');
                    kind = 'brace';
                } else if (type === 'var_ref') {
                    varName = varName.replace(/^@var:/, '');
                    kind = 'var';
                } else {
                    varName = varName.replace(/^@state:/, '');
                    kind = 'state';
                }

                return {
                    pos: start,
                    end,
                    above: true,
                    create() {
                        const dom = document.createElement('div');
                        dom.className = 'variable-tooltip';

                        const nameEl = document.createElement('div');
                        nameEl.className = 'variable-tooltip-name';
                        nameEl.textContent = varName;
                        dom.appendChild(nameEl);

                        const valueEl = document.createElement('div');
                        const preview = lookupPreviewValue(varName, {
                            kind,
                            values: ctx.getValues(),
                            statePreview: ctx.getStatePreview(),
                            catalog: ctx.getCatalog(),
                        });

                        if (preview.status === 'resolved') {
                            valueEl.className = 'variable-tooltip-value';
                            const value = preview.value;
                            if (typeof value === 'object' && value !== null) {
                                valueEl.textContent = JSON.stringify(value, null, 2);
                            } else {
                                valueEl.textContent = String(value);
                            }
                        } else if (preview.status === 'runtime_only') {
                            valueEl.className = 'variable-tooltip-undefined';
                            valueEl.textContent = ctx.t('runtime_value');
                        } else {
                            valueEl.className = 'variable-tooltip-undefined';
                            valueEl.textContent = ctx.t('undefined');
                        }
                        dom.appendChild(valueEl);

                        return { dom };
                    },
                };
            }
        }
        return null;
    });
}

function _createCompletionSource(ctx: CompletionContext) {
    return (context: CompletionContextObj): CompletionResult | null => {
        if (ctx.includeBrace) {
            const beforeCursor = context.matchBefore(/\{[\w.]*$/);
            if (beforeCursor) {
                const partial = beforeCursor.text.replace(/^\{/, '');
                const options = _buildVariableCompletions(partial, ctx.getValues(), ctx.getCatalog());
                if (options.length > 0) {
                    return { from: beforeCursor.from + 1, options };
                }
            }
        }

        if (ctx.includeAtRef) {
            const varRefMatch = context.matchBefore(/@var:[\w.]*$/);
            if (varRefMatch) {
                const partial = varRefMatch.text.replace(/^@var:/, '');
                const options = _buildVariableCompletions(partial, ctx.getValues(), ctx.getCatalog());
                if (options.length > 0) {
                    return { from: varRefMatch.from + 5, options };
                }
            }

            const stateRefMatch = context.matchBefore(/@state:[\w.]*$/);
            if (stateRefMatch) {
                const partial = stateRefMatch.text.replace(/^@state:/, '');
                const options = _buildStateCompletions(
                    partial,
                    ctx.getStatePreview(),
                    ctx.getStatePaths(),
                    ctx.getCatalog(),
                );
                if (options.length > 0) {
                    return { from: stateRefMatch.from + 7, options };
                }
            }
        }

        return null;
    };
}

function _buildVariableCompletions(
    partial: string,
    values: Record<string, unknown>,
    catalog: Array<{ name: string; type?: string; source?: string }>,
): CompletionOption[] {
    const options: CompletionOption[] = [];
    const seen = new Set<string>();
    const lowerPartial = partial.toLowerCase();

    const addVariable = (name: string, value: unknown, path = '') => {
        const fullPath = path ? `${path}.${name}` : name;

        if (fullPath.toLowerCase().startsWith(lowerPartial)) {
            let displayValue = value;
            if (
                displayValue !== null
                && typeof displayValue === 'object'
                && !Array.isArray(displayValue)
                && Object.hasOwn(displayValue, 'value')
            ) {
                displayValue = (displayValue as Record<string, unknown>).value;
            }

            let detail: string = typeof displayValue;
            if (typeof displayValue === 'string') {
                detail = displayValue.length > 30 ? `${displayValue.substring(0, 30)}...` : displayValue;
            } else if (typeof displayValue === 'object' && displayValue !== null) {
                detail = 'object';
            }

            options.push({ label: fullPath, type: 'variable', detail: String(detail) });
            seen.add(fullPath);
        }

        const actualValue = unwrapForNesting(value);
        if (actualValue !== null && typeof actualValue === 'object' && !Array.isArray(actualValue)) {
            for (const [key, val] of Object.entries(actualValue)) {
                addVariable(key, val, fullPath);
            }
        }
    };

    for (const [name, value] of Object.entries(values || {})) {
        addVariable(name, value);
    }

    for (const entry of Array.isArray(catalog) ? catalog : []) {
        if (!entry || typeof entry.name !== 'string' || seen.has(entry.name)) continue;
        if (!entry.name.toLowerCase().startsWith(lowerPartial)) continue;
        options.push({
            label: entry.name,
            type: 'variable',
            detail: `${entry.type || 'any'} · ${entry.source || 'runtime'}`,
        });
        seen.add(entry.name);
    }

    return options;
}

function _buildStateCompletions(
    partial: string,
    statePreview: Record<string, unknown>,
    statePaths: string[],
    catalog: Array<{ name: string; kind?: string; type?: string; source?: string }>,
): CompletionOption[] {
    const options: CompletionOption[] = [];
    const seen = new Set<string>();
    const lowerPartial = partial.toLowerCase();

    const candidates: string[] = [
        ...flattenPreviewPaths(statePreview),
        ...(Array.isArray(statePaths) ? statePaths : []),
    ];

    for (const entry of Array.isArray(catalog) ? catalog : []) {
        if (!entry || typeof entry.name !== 'string') continue;
        if (entry.kind === 'state') {
            candidates.push(entry.name);
        }
    }

    for (const path of candidates) {
        if (typeof path !== 'string' || path.length === 0) continue;
        if (seen.has(path)) continue;
        if (!path.toLowerCase().startsWith(lowerPartial)) continue;
        seen.add(path);
        const hit = lookupPath(statePreview, path);
        let detail = 'state';
        if (hit.found) {
            if (typeof hit.value === 'string') {
                detail = hit.value.length > 30 ? `${hit.value.substring(0, 30)}...` : hit.value;
            } else if (hit.value !== null && typeof hit.value === 'object') {
                detail = 'object';
            } else {
                detail = String(typeof hit.value);
            }
        }
        options.push({ label: path, type: 'variable', detail });
    }

    return options;
}

function unwrapForNesting(value: unknown): unknown {
    if (
        value !== null
        && typeof value === 'object'
        && !Array.isArray(value)
        && Object.hasOwn(value, 'value')
    ) {
        return (value as Record<string, unknown>).value;
    }
    return value;
}

function _isInterfacePath(path: string, catalog: unknown): boolean {
    const entry = findCatalogEntry(path, catalog);
    return entry !== null && entry.source === 'interface';
}

function _variableKnown(path: string, values: unknown, catalog: unknown): boolean {
    if (findCatalogEntry(path, catalog)) {
        return true;
    }
    return pathExistsInValues(path, values);
}

function _extractLoopVariables(doc: string): Set<string> {
    const loopVars = new Set<string>();
    const forRegex = /\{for\s+(\w+)\s+in\s+[\w.]+\}/g;
    let match;
    while ((match = forRegex.exec(doc)) !== null) {
        const loopVar = match[1];
        if (typeof loopVar === 'string') loopVars.add(loopVar);
    }
    return loopVars;
}

function _isLoopProperty(varName: string, loopVars: Set<string>): boolean {
    const parts = varName.split('.');
    const first = parts[0];
    return first !== undefined && loopVars.has(first);
}

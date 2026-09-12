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

/**
 * @typedef {'at-ref' | 'brace' | 'both'} VariableSyntaxMode
 */

/**
 * @typedef {object} VariableExtensionsOptions
 * @property {VariableSyntaxMode} syntax
 * @property {() => Record<string, unknown>} getValues
 * @property {() => Record<string, unknown>} [getStatePreview]
 * @property {() => Array<{ name: string, type?: string, source?: string, hasValue?: boolean, kind?: string }>} getCatalog
 * @property {() => string[]} [getStatePaths]
 * @property {(key: string) => string} t
 */

/**
 * @param {unknown} cm
 * @param {VariableExtensionsOptions} options
 * @returns {unknown[]}
 */
export function createVariableExtensions(cm, options) {
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

/**
 * Force ViewPlugin decoration rebuild after values/catalog change.
 * @param {{ state: { doc: { length: number } }, dispatch: (spec: object) => void }} editorView
 */
export function refreshVariableDecorations(editorView) {
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

/**
 * @param {object} cm
 * @param {{
 *   includeAtRef: boolean,
 *   includeBrace: boolean,
 *   getValues: () => Record<string, unknown>,
 *   getCatalog: () => unknown[],
 * }} ctx
 */
function _createHighlighter(cm, ctx) {
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

    return cm.ViewPlugin.fromClass(class {
        /**
         * @param {object} view
         */
        constructor(view) {
            this.decorations = this.buildDecorations(view);
        }

        /**
         * @param {object} update
         */
        update(update) {
            if (update.docChanged || update.viewportChanged) {
                this.decorations = this.buildDecorations(update.view);
            }
        }

        /**
         * @param {object} view
         */
        buildDecorations(view) {
            /** @type {unknown[]} */
            const builder = [];
            const doc = view.state.doc.toString();
            const values = ctx.getValues();
            const catalog = ctx.getCatalog();
            const loopVars = ctx.includeBrace ? _extractLoopVariables(doc) : new Set();

            if (ctx.includeBrace) {
                const forRegex = /\{for\s+(\w+)\s+in\s+([\w.]+)\}/g;
                let match;
                while ((match = forRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.forKeyword.range(match.index, match.index + match[0].length));
                    const listVar = match[2];
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
                    builder.push(decoClasses.refVar.range(match.index, match.index + match[0].length));
                    if (!_variableKnown(varName, values, catalog)) {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }

                const refStateRegex = /@state:([\w.]+)/g;
                while ((match = refStateRegex.exec(doc)) !== null) {
                    const statePath = match[1];
                    const mark = _isInterfacePath(statePath, catalog) ? decoClasses.interfaceField : decoClasses.refState;
                    builder.push(mark.range(match.index, match.index + match[0].length));
                }
            }

            if (ctx.includeBrace) {
                const optionalWithDefaultRegex = /\{\?([\w.]+)\|([^}]+)\}/g;
                let match;
                while ((match = optionalWithDefaultRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    const mark = _isInterfacePath(varName, catalog) ? decoClasses.interfaceField : decoClasses.optional;
                    builder.push(mark.range(match.index, match.index + match[0].length));
                }

                const optionalRegex = /\{\?([\w.]+)\}/g;
                while ((match = optionalRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    const mark = _isInterfacePath(varName, catalog) ? decoClasses.interfaceField : decoClasses.optional;
                    builder.push(mark.range(match.index, match.index + match[0].length));
                }

                const defaultRegex = /\{([\w.]+)\|([^}]+)\}/g;
                while ((match = defaultRegex.exec(doc)) !== null) {
                    const varName = match[1];
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

            builder.sort((a, b) => /** @type {{from: number}} */ (a).from - /** @type {{from: number}} */ (b).from);
            return cm.Decoration.set(builder, true);
        }
    }, {
        decorations: (v) => v.decorations,
    });
}

/**
 * @param {object} cm
 * @param {{
 *   includeAtRef: boolean,
 *   includeBrace: boolean,
 *   getValues: () => Record<string, unknown>,
 *   getStatePreview: () => Record<string, unknown>,
 *   getCatalog: () => unknown[],
 *   t: (key: string) => string,
 * }} ctx
 */
function _createTooltip(cm, ctx) {
    return cm.hoverTooltip((view, pos) => {
        const doc = view.state.doc.toString();
        /** @type {Array<{ regexp: RegExp, type: 'variable' | 'var_ref' | 'state_ref' }>} */
        const patterns = [];
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
                /** @type {'var' | 'state' | 'brace'} */
                let kind = 'brace';
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

/**
 * @param {{
 *   includeAtRef: boolean,
 *   includeBrace: boolean,
 *   getValues: () => Record<string, unknown>,
 *   getStatePreview: () => Record<string, unknown>,
 *   getCatalog: () => Array<{ name: string, type?: string, source?: string }>,
 *   getStatePaths: () => string[],
 * }} ctx
 */
function _createCompletionSource(ctx) {
    return (context) => {
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

/**
 * @param {string} partial
 * @param {Record<string, unknown>} values
 * @param {Array<{ name: string, type?: string, source?: string }>} catalog
 */
function _buildVariableCompletions(partial, values, catalog) {
    /** @type {Array<{ label: string, type: string, detail: string }>} */
    const options = [];
    const seen = new Set();
    const lowerPartial = partial.toLowerCase();

    /**
     * @param {string} name
     * @param {unknown} value
     * @param {string} [path]
     */
    const addVariable = (name, value, path = '') => {
        const fullPath = path ? `${path}.${name}` : name;

        if (fullPath.toLowerCase().startsWith(lowerPartial)) {
            let displayValue = value;
            if (
                displayValue !== null
                && typeof displayValue === 'object'
                && !Array.isArray(displayValue)
                && Object.hasOwn(/** @type {Record<string, unknown>} */ (displayValue), 'value')
            ) {
                displayValue = /** @type {Record<string, unknown>} */ (displayValue).value;
            }

            let detail = typeof displayValue;
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

/**
 * @param {string} partial
 * @param {Record<string, unknown>} statePreview
 * @param {string[]} statePaths
 * @param {Array<{ name: string, kind?: string, type?: string, source?: string }>} catalog
 */
function _buildStateCompletions(partial, statePreview, statePaths, catalog) {
    /** @type {Array<{ label: string, type: string, detail: string }>} */
    const options = [];
    const seen = new Set();
    const lowerPartial = partial.toLowerCase();

    /** @type {string[]} */
    const candidates = [
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

/**
 * @param {unknown} value
 * @returns {unknown}
 */
function unwrapForNesting(value) {
    if (
        value !== null
        && typeof value === 'object'
        && !Array.isArray(value)
        && Object.hasOwn(/** @type {Record<string, unknown>} */ (value), 'value')
    ) {
        return /** @type {Record<string, unknown>} */ (value).value;
    }
    return value;
}

/**
 * Поле интерфейса — обычный путь state, который каталог dataflow помечает `source: "interface"`.
 * @param {string} path
 * @param {unknown} catalog
 * @returns {boolean}
 */
function _isInterfacePath(path, catalog) {
    const entry = findCatalogEntry(path, catalog);
    return entry !== null && entry.source === 'interface';
}

/**
 * @param {string} path
 * @param {unknown} values
 * @param {unknown} catalog
 * @returns {boolean}
 */
function _variableKnown(path, values, catalog) {
    if (findCatalogEntry(path, catalog)) {
        return true;
    }
    return pathExistsInValues(path, values);
}

/**
 * @param {string} doc
 * @returns {Set<string>}
 */
function _extractLoopVariables(doc) {
    const loopVars = new Set();
    const forRegex = /\{for\s+(\w+)\s+in\s+[\w.]+\}/g;
    let match;
    while ((match = forRegex.exec(doc)) !== null) {
        loopVars.add(match[1]);
    }
    return loopVars;
}

/**
 * @param {string} varName
 * @param {Set<string>} loopVars
 * @returns {boolean}
 */
function _isLoopProperty(varName, loopVars) {
    const parts = varName.split('.');
    return loopVars.has(parts[0]);
}

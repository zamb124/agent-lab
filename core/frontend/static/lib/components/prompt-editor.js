/**
 * PromptEditor - редактор промптов с CodeMirror
 * Подсветка переменных, циклов, ссылок + tooltip со значениями
 * Режимы: split view, fullscreen
 */
import { html, css } from 'lit';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '../platform-element/index.js';

export class PromptEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .editor-wrapper {
                position: relative;
                border-radius: var(--radius-md);
                overflow: hidden;
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
            }
            
            .editor-wrapper:focus-within {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            
            .editor-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-medium);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .editor-label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .editor-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .editor-btn {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            
            .editor-btn:hover {
                color: var(--text-primary);
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            
            .editor-btn.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            
            /*
             * Растягиваем .cm-editor на всю минимальную высоту контейнера: иначе клики
             * ниже последней строки попадают в «пустоту» и курсор не ставится (только зона у текста).
             */
            #codemirror-container {
                box-sizing: border-box;
                min-height: var(--editor-min-height, 150px);
                display: flex;
                flex-direction: column;
            }
            
            #codemirror-container.hidden {
                display: none;
            }
            
            #codemirror-container .cm-editor {
                flex: 1 1 auto;
                align-self: stretch;
                min-height: var(--editor-min-height, 150px);
                font-size: 14px;
                line-height: 1.6;
            }
            
            #codemirror-container .cm-scroller {
                flex: 1 1 auto;
                min-height: 0;
                padding: var(--space-3);
            }
            
            #codemirror-container .cm-content {
                font-family: var(--font-sans);
            }
            
            .preview-container {
                min-height: var(--editor-min-height, 150px);
                padding: var(--space-4);
                font-size: var(--text-base);
                line-height: var(--leading-relaxed);
                color: var(--text-primary);
                overflow-y: auto;
            }
            
            .preview-container p {
                margin: 0 0 var(--space-3);
            }
            
            .preview-container p:last-child {
                margin-bottom: 0;
            }
            
            .preview-container code {
                font-family: var(--font-mono);
                font-size: 0.875em;
                padding: 2px 6px;
                background: var(--glass-tint-medium);
                border-radius: var(--radius-sm);
            }
            
            .preview-container pre {
                margin: var(--space-3) 0;
                padding: var(--space-3);
                background: var(--bg-primary);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                overflow-x: auto;
            }
            
            .preview-container pre code {
                padding: 0;
                background: none;
            }
            
            .hint {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                border-top: 1px solid var(--border-subtle);
            }
            
            /* Подсветка переменных */
            .cm-variable-required {
                color: #a78bfa;
                font-weight: 500;
            }
            
            .cm-variable-optional {
                color: #22d3ee;
                font-weight: 500;
            }
            
            .cm-variable-default {
                color: var(--accent);
            }
            
            .cm-for-keyword {
                color: #f59e0b;
                font-weight: 600;
            }
            
            .cm-ref-var {
                color: #f472b6;
                font-weight: 500;
            }
            
            .cm-ref-state {
                color: #fbbf24;
                font-weight: 500;
            }
            
            .cm-variable-undefined {
                color: #ef4444;
                text-decoration: wavy underline;
                text-underline-offset: 3px;
            }
            
            .cm-loop-var {
                color: #a78bfa;
                font-style: italic;
            }
            
            /* Tooltip стили */
            .cm-tooltip {
                background: var(--glass-solid-strong) !important;
                border: 1px solid var(--border-default) !important;
                border-radius: var(--radius-md) !important;
                box-shadow: var(--glass-shadow-medium) !important;
                padding: var(--space-2) var(--space-3) !important;
                font-family: var(--font-sans) !important;
                font-size: var(--text-sm) !important;
                color: var(--text-primary) !important;
                max-width: 300px !important;
            }
            
            .variable-tooltip {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
            }
            
            .variable-tooltip-name {
                font-weight: var(--font-semibold);
                color: var(--accent);
            }
            
            .variable-tooltip-value {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                word-break: break-all;
            }
            
            .variable-tooltip-undefined {
                color: var(--error);
                font-style: italic;
            }
            
            /* Light theme */
            :host-context([data-theme="light"]) .cm-variable-required {
                color: #7c3aed;
            }
            
            :host-context([data-theme="light"]) .cm-variable-optional {
                color: #0891b2;
            }
            
            :host-context([data-theme="light"]) .cm-variable-default {
                color: #7c8af4;
            }
            
            :host-context([data-theme="light"]) .cm-for-keyword {
                color: #d97706;
            }
            
            :host-context([data-theme="light"]) .cm-ref-var {
                color: #db2777;
            }
            
            :host-context([data-theme="light"]) .cm-ref-state {
                color: #ca8a04;
            }
            
            :host-context([data-theme="light"]) .cm-variable-undefined {
                color: #dc2626;
            }
            
            :host-context([data-theme="light"]) .cm-loop-var {
                color: #7c3aed;
            }
            
            /* Split mode */
            .split-container {
                display: flex;
                gap: 1px;
                background: var(--border-subtle);
            }
            
            .split-container .split-pane {
                flex: 1;
                min-width: 0;
                background: var(--glass-solid-subtle);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            
            .split-container .split-pane-label {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-tint-subtle);
                border-bottom: 1px solid var(--border-subtle);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                flex-shrink: 0;
            }
            
            .split-container #codemirror-container {
                border-radius: 0;
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }
            
            .split-container #codemirror-container .cm-editor,
            .split-container #codemirror-container .cm-scroller {
                height: 100%;
                min-height: unset;
            }
            
            .split-container .preview-container {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
            }
            
            /* Fullscreen mode */
            :host([fullscreen]) {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                z-index: 9999 !important;
                padding: var(--space-4);
                background: var(--bg-primary);
            }
            
            :host([fullscreen]) .editor-wrapper {
                height: 100%;
                display: flex;
                flex-direction: column;
            }
            
            :host([fullscreen]) #codemirror-container,
            :host([fullscreen]) .split-container {
                flex: 1;
                min-height: 0;
            }
            
            :host([fullscreen]) #codemirror-container .cm-editor,
            :host([fullscreen]) #codemirror-container .cm-scroller {
                height: 100%;
                min-height: unset;
            }
            
            :host([fullscreen]) .preview-container {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
            }
            
            /* Icon buttons */
            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                padding: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-tint-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            
            .icon-btn:hover {
                color: var(--text-primary);
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            
            .icon-btn.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            
            .icon-btn svg {
                width: 16px;
                height: 16px;
                fill: currentColor;
            }
        `
    ];

    static properties = {
        value: { type: String },
        variables: { type: Object },
        label: { type: String },
        placeholder: { type: String },
        readonly: { type: Boolean },
        showPreview: { type: Boolean, attribute: 'show-preview' },
        showHint: { type: Boolean, attribute: 'show-hint' },
        minHeight: { type: Number, attribute: 'min-height' },
        previewMode: { type: Boolean },
        splitMode: { type: Boolean },
        fullscreenMode: { type: Boolean },
        acceptFileDrop: { type: Boolean, attribute: 'accept-file-drop' },
    };

    constructor() {
        super();
        this.value = '';
        this.variables = {};
        this.label = 'Промпт';
        this.placeholder = 'Введите промпт...';
        this.readonly = false;
        this.showPreview = true;
        this.showHint = true;
        this.minHeight = 150;
        this.previewMode = false;
        this.splitMode = false;
        this.fullscreenMode = false;
        this.acceptFileDrop = false;
        this._editorView = null;
        this._iconCacheSelect = this.select((s) => s.icon);
        this._cmModules = null;
        this._readonlyCompartment = null;
        this._fileDropCleanup = null;
    }

    async firstUpdated() {
        this._loadIcons();
        await this._initCodeMirror();
        this._boundEscapeHandler = this._handleEscape.bind(this);
        document.addEventListener('keydown', this._boundEscapeHandler);
    }
    
    _handleEscape(e) {
        if (e.key === 'Escape' && this.fullscreenMode) {
            this._toggleFullscreen();
        }
    }
    
    _loadIcons() {
        const iconNames = ['fullscreen', 'minimize', 'list'];
        for (const name of iconNames) {
            this.dispatch('icon/ui_asset/load_requested', { name });
        }
    }

    _icon(name) {
        const cache = this._iconCacheSelect.value;
        if (!cache) return '';
        return cache.uiCache[name] || '';
    }

    updated(changedProperties) {
        if (changedProperties.has('value') && this._editorView) {
            const currentValue = this._editorView.state.doc.toString();
            if (this.value !== currentValue) {
                this._editorView.dispatch({
                    changes: { from: 0, to: currentValue.length, insert: this.value || '' }
                });
            }
        }
        
        if (changedProperties.has('readonly') && this._editorView && this._readonlyCompartment && this._cmModules) {
            this._editorView.dispatch({
                effects: this._readonlyCompartment.reconfigure(
                    this._cmModules.EditorState.readOnly.of(this.readonly)
                )
            });
        }
        
        if (changedProperties.has('variables') && this._editorView) {
            const doc = this._editorView.state.doc;
            this._editorView.dispatch({
                changes: { from: doc.length, to: doc.length, insert: ' ' }
            });
            this._editorView.dispatch({
                changes: { from: doc.length, to: doc.length + 1, insert: '' }
            });
        }
        
        if (changedProperties.has('splitMode') && this._cmModules) {
            this._recreateEditor();
        }

        if (changedProperties.has('acceptFileDrop') && this._editorView) {
            this._syncFileDropListeners();
        }
    }
    
    async _recreateEditor() {
        await this.updateComplete;
        
        const currentValue = this._editorView ? this._editorView.state.doc.toString() : this.value;
        
        if (this._editorView) {
            this._teardownFileDropListeners();
            this._editorView.destroy();
            this._editorView = null;
        }
        
        this.value = currentValue;
        this._createEditor();
    }

    async _initCodeMirror() {
        const cm = await import('/static/core/assets/codemirror/codemirror-bundle.js');
        
        this._cmModules = {
            EditorState: cm.EditorState,
            Compartment: cm.Compartment,
            EditorView: cm.EditorView,
            keymap: cm.keymap,
            history: cm.history,
            defaultKeymap: cm.defaultKeymap,
            historyKeymap: cm.historyKeymap,
            autocompletion: cm.autocompletion,
            oneDark: cm.oneDark,
            syntaxHighlighting: cm.syntaxHighlighting,
            defaultHighlightStyle: cm.defaultHighlightStyle,
            Decoration: cm.Decoration,
            ViewPlugin: cm.ViewPlugin,
            hoverTooltip: cm.hoverTooltip,
        };

        this._createEditor();
    }

    _createEditor() {
        const container = this.shadowRoot.querySelector('#codemirror-container');
        if (!container) return;

        const cm = this._cmModules;
        const isDarkTheme = document.documentElement.getAttribute('data-theme') !== 'light';
        
        this._readonlyCompartment = new cm.Compartment();
        
        const variableHighlighter = this._createVariableHighlighter(cm);
        const variableTooltip = this._createVariableTooltip(cm);
        const completionSource = this._createCompletionSource();

        const themeExtensions = isDarkTheme 
            ? [cm.oneDark]
            : [
                cm.syntaxHighlighting(cm.defaultHighlightStyle, { fallback: true }),
                cm.EditorView.theme({
                    "&": { backgroundColor: "transparent", color: "#383a42" },
                    ".cm-content": { caretColor: "#7c8af4" },
                    ".cm-cursor": { borderLeftColor: "#7c8af4" },
                }, { dark: false })
            ];

        const extensions = [
            cm.history(),
            this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
            cm.autocompletion({ override: [completionSource] }),
            cm.keymap.of([
                ...cm.defaultKeymap,
                ...cm.historyKeymap,
            ]),
            variableHighlighter,
            variableTooltip,
            ...themeExtensions,
            cm.EditorView.updateListener.of((update) => {
                if (update.docChanged) {
                    this.value = update.state.doc.toString();
                    this.emit('change', { value: this.value });
                }
            }),
            cm.EditorView.theme({
                "&.cm-focused": { outline: "none" },
                ".cm-line": { padding: "0 4px" },
            }),
        ];

        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: this.value || '',
                extensions
            }),
            parent: container
        });
        this._syncFileDropListeners();
    }

    _teardownFileDropListeners() {
        if (this._fileDropCleanup) {
            this._fileDropCleanup();
            this._fileDropCleanup = null;
        }
    }

    _syncFileDropListeners() {
        this._teardownFileDropListeners();
        if (!this.acceptFileDrop || !this._editorView) {
            return;
        }
        const dom = this._editorView.dom;
        const onDragOver = (e) => {
            e.preventDefault();
            e.stopPropagation();
            const types = e.dataTransfer.types ? Array.from(e.dataTransfer.types) : [];
            if (types.includes('text/plain')) {
                e.dataTransfer.dropEffect = 'copy';
            }
        };
        const onDrop = (e) => {
            e.preventDefault();
            e.stopPropagation();
            const text = e.dataTransfer.getData('text/plain');
            if (text) {
                this.insertTextAtCursor(text);
            }
        };
        dom.addEventListener('dragover', onDragOver);
        dom.addEventListener('drop', onDrop);
        this._fileDropCleanup = () => {
            dom.removeEventListener('dragover', onDragOver);
            dom.removeEventListener('drop', onDrop);
        };
    }

    _createVariableHighlighter(cm) {
        const self = this;
        
        const decoClasses = {
            required: cm.Decoration.mark({ class: "cm-variable-required" }),
            optional: cm.Decoration.mark({ class: "cm-variable-optional" }),
            default: cm.Decoration.mark({ class: "cm-variable-default" }),
            undefined: cm.Decoration.mark({ class: "cm-variable-undefined" }),
            forKeyword: cm.Decoration.mark({ class: "cm-for-keyword" }),
            loopVar: cm.Decoration.mark({ class: "cm-loop-var" }),
            refVar: cm.Decoration.mark({ class: "cm-ref-var" }),
            refState: cm.Decoration.mark({ class: "cm-ref-state" }),
        };

        return cm.ViewPlugin.fromClass(class {
            constructor(view) {
                this.decorations = this.buildDecorations(view);
            }

            update(update) {
                if (update.docChanged || update.viewportChanged) {
                    this.decorations = this.buildDecorations(update.view);
                }
            }

            buildDecorations(view) {
                const builder = [];
                const doc = view.state.doc.toString();
                const loopVars = this.extractLoopVariables(doc);
                
                const forRegex = /\{for\s+(\w+)\s+in\s+([\w.]+)\}/g;
                let match;
                while ((match = forRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.forKeyword.range(match.index, match.index + match[0].length));
                    
                    const listVar = match[2];
                    if (!self._variableExists(listVar) && !loopVars.has(listVar)) {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }
                
                const endforRegex = /\{endfor\}/g;
                while ((match = endforRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.forKeyword.range(match.index, match.index + match[0].length));
                }
                
                const refVarRegex = /@var:([\w.]+)/g;
                while ((match = refVarRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    builder.push(decoClasses.refVar.range(match.index, match.index + match[0].length));
                    if (!self._variableExists(varName)) {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }
                
                const refStateRegex = /@state:([\w.]+)/g;
                while ((match = refStateRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.refState.range(match.index, match.index + match[0].length));
                }
                
                const optionalWithDefaultRegex = /\{\?([\w.]+)\|([^}]+)\}/g;
                while ((match = optionalWithDefaultRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.optional.range(match.index, match.index + match[0].length));
                }
                
                const optionalRegex = /\{\?([\w.]+)\}/g;
                while ((match = optionalRegex.exec(doc)) !== null) {
                    builder.push(decoClasses.optional.range(match.index, match.index + match[0].length));
                }
                
                const defaultRegex = /\{([\w.]+)\|([^}]+)\}/g;
                while ((match = defaultRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    builder.push(decoClasses.default.range(match.index, match.index + match[0].length));
                    if (!self._variableExists(varName) && !loopVars.has(varName) && !this.isLoopProperty(varName, loopVars)) {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }
                
                const requiredRegex = /\{([\w.]+)\}/g;
                while ((match = requiredRegex.exec(doc)) !== null) {
                    const varName = match[1];
                    if (varName === 'endfor' || varName.startsWith('for ') || varName.startsWith('?')) continue;
                    
                    const isLoopVar = loopVars.has(varName) || this.isLoopProperty(varName, loopVars);
                    
                    if (isLoopVar) {
                        builder.push(decoClasses.loopVar.range(match.index, match.index + match[0].length));
                    } else if (self._variableExists(varName)) {
                        builder.push(decoClasses.required.range(match.index, match.index + match[0].length));
                    } else {
                        builder.push(decoClasses.undefined.range(match.index, match.index + match[0].length));
                    }
                }
                
                builder.sort((a, b) => a.from - b.from);
                return cm.Decoration.set(builder, true);
            }
            
            extractLoopVariables(doc) {
                const loopVars = new Set();
                const forRegex = /\{for\s+(\w+)\s+in\s+[\w.]+\}/g;
                let match;
                while ((match = forRegex.exec(doc)) !== null) {
                    loopVars.add(match[1]);
                }
                return loopVars;
            }
            
            isLoopProperty(varName, loopVars) {
                const parts = varName.split('.');
                return loopVars.has(parts[0]);
            }
        }, {
            decorations: v => v.decorations
        });
    }
    
    _variableExists(path) {
        if (!this.variables) return false;
        
        const parts = path.split('.');
        let value = this.variables;
        
        for (const part of parts) {
            if (value === null || value === undefined) return false;
            if (typeof value !== 'object') return false;
            
            if (typeof value[part] === 'object' && value[part] !== null && 'value' in value[part]) {
                value = value[part].value;
            } else if (part in value) {
                value = value[part];
            } else {
                return false;
            }
        }
        
        return true;
    }

    _createVariableTooltip(cm) {
        const self = this;
        
        return cm.hoverTooltip((view, pos) => {
            const doc = view.state.doc.toString();
            
            const patterns = [
                { regexp: /\{\??[\w.]+(?:\|[^}]*)?\}/g, type: 'variable' },
                { regexp: /@var:[\w.]+/g, type: 'var_ref' },
                { regexp: /@state:[\w.]+/g, type: 'state_ref' },
            ];
            
            for (const { regexp, type } of patterns) {
                regexp.lastIndex = 0;
                let match;
                while ((match = regexp.exec(doc)) !== null) {
                    const start = match.index;
                    const end = start + match[0].length;
                    
                    if (pos >= start && pos <= end) {
                        let varName = match[0];
                        
                        if (type === 'variable') {
                            varName = varName.replace(/^\{\??/, '').replace(/(\|[^}]*)?\}$/, '');
                        } else if (type === 'var_ref') {
                            varName = varName.replace(/^@var:/, '');
                        } else if (type === 'state_ref') {
                            varName = varName.replace(/^@state:/, '');
                        }
                        
                        return {
                            pos: start,
                            end: end,
                            above: true,
                            create() {
                                const dom = document.createElement('div');
                                dom.className = 'variable-tooltip';
                                
                                const nameEl = document.createElement('div');
                                nameEl.className = 'variable-tooltip-name';
                                nameEl.textContent = varName;
                                dom.appendChild(nameEl);
                                
                                const valueEl = document.createElement('div');
                                const value = self._getVariableValue(varName, type);
                                
                                if (value !== undefined) {
                                    valueEl.className = 'variable-tooltip-value';
                                    if (typeof value === 'object') {
                                        valueEl.textContent = JSON.stringify(value, null, 2);
                                    } else {
                                        valueEl.textContent = String(value);
                                    }
                                } else {
                                    valueEl.className = 'variable-tooltip-undefined';
                                    valueEl.textContent = 'не определена';
                                }
                                dom.appendChild(valueEl);
                                
                                return { dom };
                            }
                        };
                    }
                }
            }
            
            return null;
        });
    }

    _getVariableValue(path, type) {
        if (type === 'state_ref') {
            return undefined;
        }
        
        if (!this.variables) return undefined;
        
        const parts = path.split('.');
        let value = this.variables;
        
        for (const part of parts) {
            if (value === null || value === undefined) return undefined;
            if (typeof value !== 'object') return undefined;
            
            if (typeof value[part] === 'object' && value[part] !== null && 'value' in value[part]) {
                value = value[part].value;
            } else {
                value = value[part];
            }
        }
        
        return value;
    }

    _createCompletionSource() {
        const self = this;
        
        return (context) => {
            const beforeCursor = context.matchBefore(/\{[\w.]*$/);
            if (beforeCursor) {
                const partial = beforeCursor.text.replace(/^\{/, '');
                const options = self._buildVariableCompletions(partial);
                
                if (options.length > 0) {
                    return {
                        from: beforeCursor.from + 1,
                        options
                    };
                }
            }
            
            const varRefMatch = context.matchBefore(/@var:[\w.]*$/);
            if (varRefMatch) {
                const partial = varRefMatch.text.replace(/^@var:/, '');
                const options = self._buildVariableCompletions(partial, '@var:');
                
                if (options.length > 0) {
                    return {
                        from: varRefMatch.from + 5,
                        options
                    };
                }
            }
            
            return null;
        };
    }

    _buildVariableCompletions(partial, prefix = '') {
        if (!this.variables) return [];
        
        const options = [];
        const lowerPartial = partial.toLowerCase();
        
        const addVariable = (name, value, path = '') => {
            const fullPath = path ? `${path}.${name}` : name;
            
            if (fullPath.toLowerCase().startsWith(lowerPartial)) {
                let displayValue = value;
                if (typeof value === 'object' && value !== null && 'value' in value) {
                    displayValue = value.value;
                }
                
                let detail = typeof displayValue;
                if (typeof displayValue === 'string') {
                    detail = displayValue.length > 30 ? displayValue.substring(0, 30) + '...' : displayValue;
                } else if (typeof displayValue === 'object') {
                    detail = 'object';
                }
                
                options.push({
                    label: fullPath,
                    type: 'variable',
                    detail: detail,
                });
            }
            
            const actualValue = typeof value === 'object' && value !== null && 'value' in value ? value.value : value;
            if (typeof actualValue === 'object' && actualValue !== null && !Array.isArray(actualValue)) {
                for (const [key, val] of Object.entries(actualValue)) {
                    addVariable(key, val, fullPath);
                }
            }
        };
        
        for (const [name, value] of Object.entries(this.variables)) {
            addVariable(name, value);
        }
        
        return options;
    }

    _togglePreview() {
        if (this.splitMode) {
            this.splitMode = false;
        }
        this.previewMode = !this.previewMode;
    }
    
    _toggleSplit() {
        if (this.previewMode) {
            this.previewMode = false;
        }
        this.splitMode = !this.splitMode;
    }
    
    _toggleFullscreen() {
        this.fullscreenMode = !this.fullscreenMode;
        if (this.fullscreenMode) {
            this.setAttribute('fullscreen', '');
            document.body.style.overflow = 'hidden';
        } else {
            this.removeAttribute('fullscreen');
            document.body.style.overflow = '';
        }
    }

    _renderPreview() {
        if (!this.value) {
            return html`<div class="preview-container" style="color: var(--text-tertiary);">Пустой промпт</div>`;
        }
        
        let rendered = this._resolveTemplate(this.value);
        
        if (window.marked) {
            try {
                const htmlContent = window.marked.parse(rendered);
                return html`<div class="preview-container">${unsafeHTML(htmlContent)}</div>`;
            } catch (e) {
                console.warn('Marked parse error:', e);
            }
        }
        
        rendered = rendered.replace(/\n/g, '<br>');
        return html`<div class="preview-container">${unsafeHTML(rendered)}</div>`;
    }
    
    _resolveTemplate(template) {
        let result = template;
        
        result = this._resolveForLoops(result);
        
        result = result.replace(/\{\?([\w.]+)\|([^}]+)\}/g, (match, varName, defaultVal) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : '';
        });
        
        result = result.replace(/\{\?([\w.]+)\}/g, (match, varName) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : '';
        });
        
        result = result.replace(/\{([\w.]+)\|([^}]+)\}/g, (match, varName, defaultVal) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : defaultVal;
        });
        
        result = result.replace(/\{([\w.]+)\}/g, (match, varName) => {
            const value = this._getVariableValue(varName, 'variable');
            if (value !== undefined) {
                return this._formatValue(value);
            }
            return `⚠️${match}`;
        });
        
        result = result.replace(/@var:([\w.]+)/g, (match, varName) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : `⚠️${match}`;
        });
        
        result = result.replace(/@state:([\w.]+)/g, (match) => {
            return `📍${match}`;
        });
        
        return result;
    }
    
    _resolveForLoops(template) {
        const forPattern = /\{for\s+(\w+)\s+in\s+([\w.]+)\}([\s\S]*?)\{endfor\}/g;
        
        return template.replace(forPattern, (match, itemVar, listVar, body) => {
            const listValue = this._getVariableValue(listVar, 'variable');
            
            if (!Array.isArray(listValue)) {
                return `⚠️ ${listVar} не является массивом`;
            }
            
            const results = listValue.map(item => {
                let itemBody = body;
                
                itemBody = itemBody.replace(new RegExp(`\\{${itemVar}\\}`, 'g'), this._formatValue(item));
                
                itemBody = itemBody.replace(new RegExp(`\\{${itemVar}\\.(\\w+)\\}`, 'g'), (m, prop) => {
                    if (typeof item === 'object' && item !== null && prop in item) {
                        return this._formatValue(item[prop]);
                    }
                    return `⚠️{${itemVar}.${prop}}`;
                });
                
                return itemBody;
            });
            
            return results.join('');
        });
    }
    
    _formatValue(value) {
        if (value === null || value === undefined) return '';
        if (typeof value === 'object') return JSON.stringify(value);
        return String(value);
    }

    getValue() {
        if (this._editorView) {
            return this._editorView.state.doc.toString();
        }
        return this.value;
    }

    insertTextAtCursor(text) {
        if (!text || !this._editorView) {
            return;
        }
        const { from, to } = this._editorView.state.selection.main;
        this._editorView.dispatch({
            changes: { from, to, insert: text },
            selection: { anchor: from + text.length, head: from + text.length },
        });
        this.value = this._editorView.state.doc.toString();
        this.emit('change', { value: this.value });
    }

    setValue(text) {
        this.value = text;
        if (this._editorView) {
            this._editorView.dispatch({
                changes: { from: 0, to: this._editorView.state.doc.length, insert: text }
            });
        }
    }

    focus() {
        if (this._editorView) {
            this._editorView.focus();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._teardownFileDropListeners();
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
        if (this._boundEscapeHandler) {
            document.removeEventListener('keydown', this._boundEscapeHandler);
        }
        if (this.fullscreenMode) {
            document.body.style.overflow = '';
        }
    }

    render() {
        const style = `--editor-min-height: ${this.minHeight}px`;
        const splitMinHeight = Math.max(this.minHeight, 320);
        
        return html`
            <div class="editor-wrapper">
                <div class="editor-header">
                    <span class="editor-label">${this.label}</span>
                    <div class="editor-actions">
                        ${this.showPreview ? html`
                            <button 
                                type="button" 
                                class="editor-btn ${this.previewMode && !this.splitMode ? 'active' : ''}"
                                @click=${this._togglePreview}
                                title="Preview"
                            >
                                ${this.previewMode ? 'Редактор' : 'Preview'}
                            </button>
                            <button 
                                type="button" 
                                class="icon-btn ${this.splitMode ? 'active' : ''}"
                                @click=${this._toggleSplit}
                                title="Split view"
                            >
                                ${this._icon('list') ? unsafeHTML(this._icon('list')) : '⊞'}
                            </button>
                        ` : ''}
                        <button 
                            type="button" 
                            class="icon-btn ${this.fullscreenMode ? 'active' : ''}"
                            @click=${this._toggleFullscreen}
                            title="${this.fullscreenMode ? 'Выйти из полноэкранного режима' : 'Полноэкранный режим'}"
                        >
                            ${this.fullscreenMode 
                                ? (this._icon('minimize') ? unsafeHTML(this._icon('minimize')) : '⊠')
                                : (this._icon('fullscreen') ? unsafeHTML(this._icon('fullscreen')) : '⊡')
                            }
                        </button>
                    </div>
                </div>
                
                ${this.splitMode ? html`
                    <div class="split-container" style="min-height: ${splitMinHeight}px">
                        <div class="split-pane">
                            <div class="split-pane-label">Редактор</div>
                            <div id="codemirror-container"></div>
                        </div>
                        <div class="split-pane">
                            <div class="split-pane-label">Preview</div>
                            ${this._renderPreview()}
                        </div>
                    </div>
                ` : html`
                    <div id="codemirror-container" style=${style} class="${this.previewMode ? 'hidden' : ''}"></div>
                    ${this.previewMode ? this._renderPreview() : ''}
                `}
                
                ${this.showHint && !this.fullscreenMode ? html`
                    <div class="hint">
                        Переменные: <code>{variable}</code>, <code>{?optional}</code>, <code>{var|default}</code> | 
                        Циклы: <code>{for x in list}...{endfor}</code> | 
                        Ссылки: <code>@var:key</code>, <code>@state:path</code>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('prompt-editor', PromptEditor);

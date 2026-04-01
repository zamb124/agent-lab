/**
 * PythonCodeEditor - редактор Python кода с CodeMirror 6
 * Подсветка синтаксиса, autocomplete, темная/светлая тема
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AppEvents } from '@platform/lib/utils/types.js';

const DEFAULT_CODE = `async def run(state):
    """
    Process state.

    Args:
        state: Current execution state

    Returns:
        Updated state
    """
    return state
`;

export class PythonCodeEditor extends PlatformElement {
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
                border: 1px solid var(--border-subtle);
            }
            
            .editor-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-medium);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .editor-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
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
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .editor-btn:hover {
                color: var(--text-primary);
                border-color: var(--accent);
            }
            
            #codemirror-container {
                min-height: var(--editor-min-height, 200px);
            }
            
            #codemirror-container .cm-editor {
                min-height: var(--editor-min-height, 200px);
                font-size: 13px;
            }
            
            #codemirror-container .cm-scroller {
                min-height: var(--editor-min-height, 200px);
            }
            
            .editor-fallback {
                width: 100%;
                min-height: var(--editor-min-height, 200px);
                padding: var(--space-3);
                font-family: var(--font-mono, 'JetBrains Mono', monospace);
                font-size: 13px;
                line-height: 1.6;
                color: var(--text-primary);
                background: var(--bg-secondary);
                border: none;
                resize: vertical;
                outline: none;
                tab-size: 4;
                white-space: pre;
            }
            
            .editor-fallback:focus {
                outline: none;
            }
            
            .editor-fallback.readonly {
                background: var(--glass-tint-subtle);
                color: var(--text-secondary);
            }
            
            .validation-status {
                display: none;
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                border-top: 1px solid var(--border-subtle);
            }
            
            .validation-status.visible {
                display: block;
            }
            
            .validation-status.valid {
                color: var(--success);
                background: var(--success-bg);
            }
            
            .validation-status.error {
                color: var(--error);
                background: var(--error-bg);
            }
        `
    ];

    static properties = {
        value: { type: String },
        readonly: { type: Boolean },
        minHeight: { type: Number, attribute: 'min-height' },
        showHeader: { type: Boolean, attribute: 'show-header' },
        validationStatus: { type: String },
        validationMessage: { type: String },
    };

    constructor() {
        super();
        this.value = '';
        this.readonly = false;
        this.minHeight = 200;
        this.showHeader = true;
        this.validationStatus = '';
        this.validationMessage = '';
        this._defaultCode = DEFAULT_CODE;
        this._cmReady = false;
        this._editorView = null;
        this._cmModules = null;
        this._readonlyCompartment = null;
        this._completionData = null;
    }

    async firstUpdated() {
        await this._initCodeMirror();
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
    }

    async _initCodeMirror() {
         const cm = await import('/static/core/assets/codemirror/codemirror-bundle.js');
        
        this._cmModules = {
            EditorState: cm.EditorState,
            Compartment: cm.Compartment,
            EditorView: cm.EditorView,
            lineNumbers: cm.lineNumbers,
            highlightActiveLine: cm.highlightActiveLine,
            highlightActiveLineGutter: cm.highlightActiveLineGutter,
            keymap: cm.keymap,
            indentOnInput: cm.indentOnInput,
            bracketMatching: cm.bracketMatching,
            foldGutter: cm.foldGutter,
            syntaxHighlighting: cm.syntaxHighlighting,
            defaultHighlightStyle: cm.defaultHighlightStyle,
            autocompletion: cm.autocompletion,
            defaultKeymap: cm.defaultKeymap,
            historyKeymap: cm.historyKeymap,
            history: cm.history,
            indentMore: cm.indentMore,
            indentLess: cm.indentLess,
            python: cm.python,
            oneDark: cm.oneDark,
        };

        await this._loadCompletionData();
        this._createEditor();
        this._cmReady = true;
    }

    async _loadCompletionData() {
        if (this.a2a) {
            this._completionData = await this.a2a.get('/api/v1/code/completions');
        }
    }

    _createEditor() {
        const container = this.shadowRoot.querySelector('#codemirror-container');
        if (!container) return;

        const cm = this._cmModules;
        const isDarkTheme = document.documentElement.getAttribute('data-theme') !== 'light';
        
        this._readonlyCompartment = new cm.Compartment();
        
        const completions = this._buildCompletions();
        const customCompletionSource = this._createCompletionSource(completions);

        const themeExtensions = isDarkTheme 
            ? [cm.oneDark]
            : [
                cm.syntaxHighlighting(cm.defaultHighlightStyle, { fallback: true }),
                cm.EditorView.theme({
                    "&": { backgroundColor: "#fafafa", color: "#383a42" },
                    ".cm-content": { caretColor: "#526fff" },
                    ".cm-cursor": { borderLeftColor: "#526fff" },
                    ".cm-gutters": { backgroundColor: "#f0f0f0", color: "#9d9d9f", borderRight: "1px solid #e5e5e5" },
                    ".cm-activeLineGutter": { backgroundColor: "#e8e8e8" },
                    ".cm-activeLine": { backgroundColor: "#f0f4ff" },
                }, { dark: false })
            ];

        const extensions = [
            cm.history(),
            cm.lineNumbers(),
            cm.highlightActiveLine(),
            cm.highlightActiveLineGutter(),
            cm.indentOnInput(),
            cm.bracketMatching(),
            cm.foldGutter(),
            cm.EditorState.tabSize.of(4),
            cm.python(),
            ...themeExtensions,
            this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
            cm.autocompletion({ override: [customCompletionSource] }),
            cm.keymap.of([
                ...cm.defaultKeymap,
                ...cm.historyKeymap,
                { key: 'Tab', run: cm.indentMore },
                { key: 'Shift-Tab', run: cm.indentLess }
            ]),
            cm.EditorView.domEventHandlers({
                copy: (_event, view) => {
                    if (this.readonly) return false;
                    if (view.state.selection.main.empty) return false;
                    requestAnimationFrame(() => this._notifyCopied());
                    return false;
                },
            }),
            cm.EditorView.updateListener.of((update) => {
                if (update.docChanged) {
                    this.value = update.state.doc.toString();
                    this.emit('change', { value: this.value });
                }
            })
        ];

        const initialCode = this.value || this._defaultCode;

        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: initialCode,
                extensions
            }),
            parent: container
        });
    }

    _buildCompletions() {
        const completions = [];
        const data = this._completionData;

        if (data?.modules) {
            for (const mod of data.modules) {
                completions.push({ label: mod, type: 'namespace', detail: 'module' });
            }
        }

        if (data?.globals) {
            for (const g of data.globals) {
                completions.push({
                    label: g.name,
                    type: g.type === 'function' ? 'function' : 'variable',
                    detail: g.type,
                    info: g.doc
                });
            }
        }

        if (data?.builtins) {
            for (const b of data.builtins) {
                completions.push({ label: b, type: 'function', detail: 'builtin' });
            }
        }

        return completions;
    }

    _createCompletionSource(completions) {
        const stateFields = this._completionData?.state_fields || [];
        const moduleMethodsMap = this._completionData?.module_methods || {};

        return (context) => {
            // Автодополнение для state["..."]
            const stateKeyMatch = context.matchBefore(/state\s*\[\s*["'](\w*)$/);
            if (stateKeyMatch) {
                const partial = stateKeyMatch.text.match(/["'](\w*)$/)?.[1] || '';
                const stateOptions = stateFields
                    .filter(f => f.name.toLowerCase().startsWith(partial.toLowerCase()))
                    .map(f => ({ label: f.name, type: 'property', detail: f.type, info: f.description }));
                
                if (stateOptions.length > 0) {
                    const quotePos = stateKeyMatch.from + stateKeyMatch.text.lastIndexOf('"') + 1;
                    const altQuotePos = stateKeyMatch.from + stateKeyMatch.text.lastIndexOf("'") + 1;
                    return { from: Math.max(quotePos, altQuotePos), options: stateOptions };
                }
            }

            // Автодополнение методов модуля
            const beforeDot = context.matchBefore(/(\w+)\./);
            if (beforeDot) {
                const moduleName = beforeDot.text.slice(0, -1);
                const methods = moduleMethodsMap[moduleName];
                if (methods?.length > 0) {
                    const word = context.matchBefore(/\w*$/);
                    const methodOptions = methods.map(m => ({
                        label: m.name,
                        type: m.type === 'class' ? 'class' : (m.type === 'property' ? 'property' : 'function'),
                        detail: `${moduleName}.${m.name}`,
                        info: m.doc
                    }));
                    
                    const filtered = word?.text 
                        ? methodOptions.filter(o => o.label.toLowerCase().startsWith(word.text.toLowerCase()))
                        : methodOptions;
                    
                    if (filtered.length > 0) {
                        return { from: word ? word.from : context.pos, options: filtered };
                    }
                }
            }

            // Общие дополнения
            const word = context.matchBefore(/\w+/);
            if (!word || (word.from === word.to && !context.explicit)) return null;

            const options = completions.filter(c => c.label.toLowerCase().startsWith(word.text.toLowerCase()));
            if (options.length === 0) return null;

            return { from: word.from, options };
        };
    }

    getValue() {
        if (this._editorView) {
            return this._editorView.state.doc.toString();
        }
        return this.value;
    }

    setValue(code) {
        this.value = code;
        if (this._editorView) {
            this._editorView.dispatch({
                changes: { from: 0, to: this._editorView.state.doc.length, insert: code }
            });
        }
    }

    setReadonly(readonly) {
        this.readonly = readonly;
        if (this._editorView && this._readonlyCompartment && this._cmModules) {
            this._editorView.dispatch({
                effects: this._readonlyCompartment.reconfigure(
                    this._cmModules.EditorState.readOnly.of(readonly)
                )
            });
        }
    }

    reset() {
        this.setValue(this._defaultCode);
    }

    getDefaultCode() {
        return this._defaultCode;
    }

    showValidation(status, message) {
        this.validationStatus = status;
        this.validationMessage = message;
    }

    hideValidation() {
        this.validationStatus = '';
        this.validationMessage = '';
    }

    _notifyCopied() {
        const message = this.i18n.t('code_editor.copied');
        try {
            this.success(message);
        } catch {
            window.dispatchEvent(
                new CustomEvent(AppEvents.TOAST_SHOW, {
                    detail: {
                        id: `toast-copy-${Date.now()}`,
                        type: 'success',
                        message,
                        duration: 3000,
                    },
                })
            );
        }
    }

    async _copyCode() {
        try {
            await navigator.clipboard.writeText(this.getValue());
            this._notifyCopied();
        } catch {
            this.error(this.i18n.t('code_editor.copy_failed'));
        }
    }

    _onFallbackInput(e) {
        this.value = e.target.value;
        this.emit('change', { value: this.value });
    }

    _onFallbackKeyDown(e) {
        if (e.key === 'Tab') {
            e.preventDefault();
            const textarea = e.target;
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            
            this.value = this.value.substring(0, start) + '    ' + this.value.substring(end);
            
            requestAnimationFrame(() => {
                textarea.selectionStart = textarea.selectionEnd = start + 4;
            });
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
    }

    render() {
        const style = `--editor-min-height: ${this.minHeight}px`;
        
        return html`
            <div class="editor-wrapper">
                ${this.showHeader ? html`
                    <div class="editor-header">
                        <span class="editor-title">Python</span>
                    </div>
                ` : ''}
                
                <div id="codemirror-container" style=${style}></div>
                
                ${this.validationStatus ? html`
                    <div class="validation-status visible ${this.validationStatus}">
                        ${this.validationMessage}
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('python-code-editor', PythonCodeEditor);

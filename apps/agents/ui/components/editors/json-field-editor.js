/**
 * JsonFieldEditor - JSON редактор с CodeMirror и валидацией
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class JsonFieldEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            
            .editor-container {
                position: relative;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            
            .editor-container.invalid {
                border-color: var(--error);
            }
            
            #codemirror-container {
                min-height: var(--editor-min-height, 100px);
            }
            
            #codemirror-container .cm-editor {
                min-height: var(--editor-min-height, 100px);
                font-size: 12px;
            }
            
            #codemirror-container .cm-scroller {
                min-height: var(--editor-min-height, 100px);
            }
            
            .editor-fallback {
                width: 100%;
                min-height: var(--editor-min-height, 100px);
                padding: var(--space-3);
                font-family: var(--font-mono, 'JetBrains Mono', monospace);
                font-size: var(--text-xs);
                line-height: 1.5;
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: none;
                resize: vertical;
                outline: none;
            }
            
            .error-message {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                color: var(--error);
                background: var(--error-bg);
                border-top: 1px solid var(--error);
            }
            
            .hint {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-tint-subtle);
                border-top: 1px solid var(--border-subtle);
            }
        `
    ];

    static properties = {
        value: { type: String },
        placeholder: { type: String },
        minHeight: { type: Number, attribute: 'min-height' },
        readonly: { type: Boolean },
        hint: { type: String },
    };

    constructor() {
        super();
        this.value = '';
        this.placeholder = '{}';
        this.minHeight = 100;
        this.readonly = false;
        this.hint = '';
        this._error = '';
        this._cmReady = false;
        this._editorView = null;
        this._cmModules = null;
        this._readonlyCompartment = null;
    }

    async firstUpdated() {
        await this._initCodeMirror();
    }

    async _initCodeMirror() {
        const cm = await import('/static/core/assets/codemirror/codemirror-bundle.js');
        
        this._cmModules = {
            EditorState: cm.EditorState,
            Compartment: cm.Compartment,
            EditorView: cm.EditorView,
            lineNumbers: cm.lineNumbers,
            highlightActiveLine: cm.highlightActiveLine,
            keymap: cm.keymap,
            bracketMatching: cm.bracketMatching,
            syntaxHighlighting: cm.syntaxHighlighting,
            defaultHighlightStyle: cm.defaultHighlightStyle,
            defaultKeymap: cm.defaultKeymap,
            historyKeymap: cm.historyKeymap,
            history: cm.history,
            json: cm.json,
            oneDark: cm.oneDark,
        };

        this._createEditor();
        this._cmReady = true;
    }

    _createEditor() {
        const container = this.shadowRoot.querySelector('#codemirror-container');
        if (!container) return;

        const cm = this._cmModules;
        const isDarkTheme = document.documentElement.getAttribute('data-theme') !== 'light';
        
        this._readonlyCompartment = new cm.Compartment();

        const themeExtensions = isDarkTheme 
            ? [cm.oneDark]
            : [
                cm.syntaxHighlighting(cm.defaultHighlightStyle, { fallback: true }),
                cm.EditorView.theme({
                    "&": { backgroundColor: "#fafafa", color: "#383a42" },
                    ".cm-content": { caretColor: "#526fff" },
                    ".cm-gutters": { backgroundColor: "#f0f0f0", color: "#9d9d9f", borderRight: "1px solid #e5e5e5" },
                }, { dark: false })
            ];

        const extensions = [
            cm.history(),
            cm.lineNumbers(),
            cm.highlightActiveLine(),
            cm.bracketMatching(),
            cm.EditorState.tabSize.of(2),
            cm.json(),
            ...themeExtensions,
            this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
            cm.keymap.of([...cm.defaultKeymap, ...cm.historyKeymap]),
            cm.EditorView.updateListener.of((update) => {
                if (update.docChanged) {
                    this.value = update.state.doc.toString();
                    this._validate();
                    this.emit('change', { value: this.value, valid: this.isValid() });
                }
            })
        ];

        const initialValue = this.value || '';

        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: initialValue,
                extensions
            }),
            parent: container
        });
    }

    getValue() {
        if (this._editorView) {
            return this._editorView.state.doc.toString();
        }
        return this.value;
    }

    setValue(value) {
        if (typeof value === 'object') {
            this.value = JSON.stringify(value, null, 2);
        } else {
            this.value = value;
        }
        
        if (this._editorView) {
            this._editorView.dispatch({
                changes: { from: 0, to: this._editorView.state.doc.length, insert: this.value }
            });
        }
        
        this._validate();
    }

    getParsedValue() {
        const val = this.getValue();
        if (!val || !val.trim()) return {};
        return JSON.parse(val);
    }

    isValid() {
        return !this._error;
    }

    getError() {
        return this._error;
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

    _validate() {
        const val = this.getValue();
        if (!val || !val.trim()) {
            this._error = '';
            return true;
        }
        try {
            JSON.parse(val);
            this._error = '';
            return true;
        } catch (e) {
            this._error = e.message;
            return false;
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
        const style = this.minHeight ? `--editor-min-height: ${this.minHeight}px` : '';
        
        return html`
            <div class="editor-container ${this._error ? 'invalid' : ''}">
                <div id="codemirror-container" style=${style}></div>
                ${this._error ? html`<div class="error-message">${this._error}</div>` : ''}
                ${this.hint && !this._error ? html`<div class="hint">${this.hint}</div>` : ''}
            </div>
        `;
    }
}

customElements.define('json-field-editor', JsonFieldEditor);

/**
 * flows-code-editor — обёртка над vendored CodeMirror.
 *
 * Lazy-импортирует `/static/core/assets/codemirror/codemirror-bundle.js` при
 * первом mount. Поддерживает языки `python` / `json` / `text`. Тема
 * переключается по `select(s => s.theme.mode)`.
 *
 * Property API:
 *   - value: string
 *   - language: 'python' | 'json' | 'text'
 *   - readonly: boolean
 *   - placeholder: string (опц.)
 *   - completionContext: object (опц.) — передаётся в payload `flows/code_completions`.
 *
 * События (emit, slot-композиция):
 *   - 'change' { value }
 *   - 'save' { value }    — Cmd/Ctrl+S
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const CODEMIRROR_URL = '/static/core/assets/codemirror/codemirror-bundle.js';

let _cmPromise = null;
function loadCodeMirror() {
    if (!_cmPromise) {
        _cmPromise = import(CODEMIRROR_URL);
    }
    return _cmPromise;
}

export class FlowsCodeEditor extends PlatformElement {
    static properties = {
        value: { type: String },
        language: { type: String },
        readonly: { type: Boolean },
        placeholder: { type: String },
        completionContext: { type: Object, attribute: false },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                min-height: 120px;
                border-radius: var(--radius-md);
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                font-family: var(--font-mono, monospace);
            }
            #cm-host { height: 100%; min-height: 120px; }
            .cm-editor {
                height: 100%;
                min-height: 120px;
                font-size: var(--text-sm);
                background: transparent;
            }
            .cm-editor.cm-focused { outline: none; }
            .cm-content { padding: var(--space-2) var(--space-3); }
            .cm-scroller { overflow: auto; }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.language = 'text';
        this.readonly = false;
        this.placeholder = '';
        this.completionContext = null;
        this._editorView = null;
        this._cm = null;
        this._readonlyCompartment = null;
        this._languageCompartment = null;
        this._themeCompartment = null;
        this._completionsOp = this.useOp('flows/code_completions');
        this._themeSel = this.select((s) => s.theme?.mode || 'dark');
    }

    connectedCallback() {
        super.connectedCallback();
        void this._init();
    }

    disconnectedCallback() {
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._editorView || !this._cm) return;
        if (changed.has('value')) {
            const current = this._editorView.state.doc.toString();
            if (current !== this.value) {
                this._editorView.dispatch({
                    changes: { from: 0, to: current.length, insert: this.value || '' },
                });
            }
        }
        if (changed.has('readonly') && this._readonlyCompartment) {
            this._editorView.dispatch({
                effects: this._readonlyCompartment.reconfigure(this._cm.EditorState.readOnly.of(this.readonly)),
            });
        }
        if (changed.has('language') && this._languageCompartment) {
            this._editorView.dispatch({
                effects: this._languageCompartment.reconfigure(this._buildLanguageExtension()),
            });
        }
    }

    async _init() {
        const cm = await loadCodeMirror();
        this._cm = cm;
        this._readonlyCompartment = new cm.Compartment();
        this._languageCompartment = new cm.Compartment();
        this._themeCompartment = new cm.Compartment();
        const host = this.shadowRoot.querySelector('#cm-host');
        if (!host) return;
        const extensions = [
            cm.history(),
            cm.lineNumbers(),
            this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
            this._languageCompartment.of(this._buildLanguageExtension()),
            this._themeCompartment.of(this._buildThemeExtension()),
            cm.autocompletion({ override: [(ctx) => this._completionSource(ctx)] }),
            cm.keymap.of([
                ...cm.defaultKeymap,
                ...cm.historyKeymap,
                {
                    key: 'Mod-s',
                    run: () => {
                        this.emit('save', { value: this._editorView.state.doc.toString() });
                        return true;
                    },
                },
            ]),
            cm.EditorView.updateListener.of((update) => {
                if (update.docChanged) {
                    const next = update.state.doc.toString();
                    if (next !== this.value) {
                        this.value = next;
                        this.emit('change', { value: next });
                    }
                }
            }),
            cm.EditorView.theme({
                '&.cm-focused': { outline: 'none' },
                '.cm-line': { padding: '0 4px' },
            }),
        ];
        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: this.value || '',
                extensions,
            }),
            parent: host,
        });
        this._unsubscribeTheme = () => {};
        this._themeWatcher = () => {
            if (!this._editorView || !this._cm || !this._themeCompartment) return;
            this._editorView.dispatch({
                effects: this._themeCompartment.reconfigure(this._buildThemeExtension()),
            });
        };
        this._themeSel.subscribe?.(this._themeWatcher);
    }

    _buildLanguageExtension() {
        if (!this._cm) return [];
        const lang = this.language || 'text';
        if (lang === 'python' && this._cm.python) return this._cm.python();
        if (lang === 'json' && this._cm.json) return this._cm.json();
        return [];
    }

    _buildThemeExtension() {
        if (!this._cm) return [];
        const isDark = (this._themeSel.value || 'dark') === 'dark';
        if (isDark) return this._cm.oneDark || [];
        return this._cm.syntaxHighlighting(this._cm.defaultHighlightStyle, { fallback: true });
    }

    async _completionSource(ctx) {
        if (this.language !== 'python') return null;
        const word = ctx.matchBefore(/\w*/);
        if (!word || (word.from === word.to && !ctx.explicit)) return null;
        const code = ctx.state.doc.toString();
        const cursor = ctx.pos;
        const result = await this._completionsOp.run({
            code,
            cursor,
            ...(this.completionContext || {}),
        });
        const items = Array.isArray(result?.items) ? result.items : Array.isArray(result) ? result : [];
        if (items.length === 0) return null;
        return {
            from: word.from,
            options: items.map((it) => ({
                label: typeof it === 'string' ? it : it.label || it.text || '',
                type: typeof it === 'object' && it.type ? it.type : 'variable',
                detail: typeof it === 'object' ? it.detail || '' : '',
                info: typeof it === 'object' ? it.info || '' : '',
            })),
        };
    }

    render() {
        return html`<div id="cm-host"></div>`;
    }
}

customElements.define('flows-code-editor', FlowsCodeEditor);

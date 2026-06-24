/**
 * platform-code-editor — CodeMirror viewer/editor для text/code в платформенных UI.
 */
import { html, css } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

const CODEMIRROR_URL = '/static/core/assets/codemirror/codemirror-bundle.js';

let _cmPromise = null;
function loadCodeMirror() {
    if (!_cmPromise) {
        _cmPromise = import(CODEMIRROR_URL);
    }
    return _cmPromise;
}

export class PlatformCodeEditor extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: String },
        language: { type: String },
        readonly: { type: Boolean, reflect: true },
        showToolbar: { type: Boolean, attribute: 'show-toolbar' },
        fillParent: { type: Boolean, reflect: true, attribute: 'fill-parent' },
        lineWrapping: { type: Boolean, reflect: true, attribute: 'line-wrapping' },
        minHeight: { type: Number, attribute: 'min-height' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
                background: var(--glass-solid-subtle);
            }
            :host([fill-parent]) {
                display: flex;
                flex-direction: column;
                flex: 1;
                min-height: 0;
                height: 100%;
                border-radius: 0;
                border: 0;
                background: transparent;
            }
            :host([fill-parent]) .editor-root {
                flex: 1;
                min-height: 0;
            }
            .editor-root {
                display: flex;
                flex-direction: column;
                min-height: var(--code-editor-min-height, 220px);
            }
            .editor-toolbar {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
            }
            .editor-title {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            #cm-wrap {
                flex: 1 1 auto;
                min-height: 0;
                overflow: hidden;
            }
            #cm-host {
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }
            .cm-editor {
                height: 100%;
                min-height: var(--code-editor-min-height, 220px);
                background: transparent;
                font-size: var(--text-sm);
            }
            .cm-editor.cm-focused {
                outline: none;
            }
            .cm-content {
                padding: var(--space-2) var(--space-3);
            }
            .cm-scroller {
                overflow: auto;
            }
            .cm-line {
                overflow-wrap: anywhere;
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.language = 'text';
        this.readonly = true;
        this.showToolbar = false;
        this.fillParent = false;
        this.lineWrapping = true;
        this.minHeight = 220;
        this._cm = null;
        this._editorView = null;
        this._readonlyCompartment = null;
        this._languageCompartment = null;
        this._themeCompartment = null;
        this._wrappingCompartment = null;
        this._initInFlight = null;
        this._themeSel = this.select((s) => (s.theme && s.theme.mode ? s.theme.mode : 'dark'));
        this._lastTheme = undefined;
        this._themeObserver = null;
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof MutationObserver !== 'undefined') {
            this._themeObserver = new MutationObserver(() => this._syncEditorTheme());
            this._themeObserver.observe(document.documentElement, {
                attributes: true,
                attributeFilter: ['data-theme', 'data-platform-theme-lock'],
            });
        }
        this.updateComplete.then(() => {
            if (this.isConnected) {
                void this._ensureEditorMounted();
            }
        });
    }

    disconnectedCallback() {
        if (this._themeObserver) {
            this._themeObserver.disconnect();
            this._themeObserver = null;
        }
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
        this._initInFlight = null;
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('minHeight')) {
            const value = Number.isFinite(this.minHeight) ? this.minHeight : 220;
            this.style.setProperty('--code-editor-min-height', `${value}px`);
        }
        if (!this._editorView || !this._cm) {
            return;
        }
        if (changed.has('value')) {
            const current = this._editorView.state.doc.toString();
            if (current !== this.value) {
                this._editorView.dispatch({
                    changes: { from: 0, to: current.length, insert: this.value },
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
        if (changed.has('lineWrapping') && this._wrappingCompartment) {
            this._editorView.dispatch({
                effects: this._wrappingCompartment.reconfigure(this._buildWrappingExtension()),
            });
        }
        this._syncEditorTheme();
    }

    async _ensureEditorMounted() {
        if (this._editorView) return;
        if (this._initInFlight) return this._initInFlight;
        const host = this.renderRoot.querySelector('#cm-host');
        if (!host) return;
        this._initInFlight = this._init(host).finally(() => {
            this._initInFlight = null;
        });
        return this._initInFlight;
    }

    _buildLanguageExtension() {
        if (!this._cm) return [];
        const lang = typeof this.language === 'string' && this.language.length > 0 ? this.language : 'text';
        if (lang === 'python' && this._cm.python) {
            return this._cm.python();
        }
        if ((lang === 'javascript' || lang === 'typescript') && this._cm.javascript) {
            return this._cm.javascript({ typescript: lang === 'typescript' });
        }
        if (lang === 'go' && this._cm.go) {
            return this._cm.go();
        }
        if (lang === 'csharp' && this._cm.csharp) {
            return this._cm.csharp();
        }
        if (lang === 'json' && this._cm.json) {
            return this._cm.json();
        }
        return [];
    }

    _buildWrappingExtension() {
        if (!this._cm) return [];
        if (this.lineWrapping || this.language === 'json') {
            return this._cm.EditorView.lineWrapping;
        }
        return [];
    }

    async _init(host) {
        const cm = await loadCodeMirror();
        if (!this.isConnected || this._editorView) return;
        this._cm = cm;
        this._readonlyCompartment = new cm.Compartment();
        this._languageCompartment = new cm.Compartment();
        this._themeCompartment = new cm.Compartment();
        this._wrappingCompartment = new cm.Compartment();
        this._lastTheme = this._themeSignature();
        const keymap = [
            {
                key: 'Tab',
                run: (view) => {
                    if (view.state.readOnly) return false;
                    view.dispatch(view.state.replaceSelection('    '));
                    return true;
                },
            },
            ...cm.defaultKeymap,
            ...cm.historyKeymap,
            {
                key: 'Mod-s',
                run: () => {
                    this.emit('save', { value: this._editorView.state.doc.toString() });
                    return true;
                },
            },
        ];
        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: this.value,
                extensions: [
                    cm.history(),
                    cm.lineNumbers(),
                    cm.bracketMatching(),
                    cm.indentOnInput(),
                    cm.EditorState.tabSize.of(4),
                    this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
                    this._languageCompartment.of(this._buildLanguageExtension()),
                    this._wrappingCompartment.of(this._buildWrappingExtension()),
                    this._themeCompartment.of(this._buildThemeExtension()),
                    cm.keymap.of(keymap),
                    cm.EditorView.updateListener.of((update) => {
                        if (!update.docChanged) return;
                        const next = update.state.doc.toString();
                        if (next !== this.value) {
                            this.value = next;
                            this.emit('change', { value: next });
                        }
                    }),
                ],
            }),
            parent: host,
        });
    }

    _buildThemeExtension() {
        if (!this._cm) return [];
        const isLight = this._resolvedThemeMode() === 'light';
        const platformTheme = this._cm.EditorView.theme({
            '&': {
                color: isLight ? '#1f2937' : 'var(--text-primary)',
                backgroundColor: 'var(--bg-primary)',
            },
            '.cm-editor': {
                backgroundColor: 'var(--bg-primary)',
            },
            '.cm-content': {
                color: isLight ? '#1f2937' : 'var(--text-primary)',
                caretColor: 'var(--accent)',
            },
            '.cm-line': {
                color: isLight ? '#1f2937' : 'var(--text-primary)',
            },
            '.cm-gutters': {
                color: 'var(--text-tertiary)',
                backgroundColor: 'var(--glass-solid-medium)',
                borderRight: '1px solid var(--glass-border-subtle)',
            },
            '.cm-activeLine': {
                backgroundColor: 'color-mix(in srgb, var(--accent) 8%, transparent)',
            },
            '.cm-activeLineGutter': {
                color: 'var(--text-primary)',
                backgroundColor: 'color-mix(in srgb, var(--accent) 10%, transparent)',
            },
            '.cm-selectionBackground, &.cm-focused .cm-selectionBackground': {
                backgroundColor: 'color-mix(in srgb, var(--accent) 28%, transparent)',
            },
            '.cm-cursor': {
                borderLeftColor: 'var(--accent)',
            },
        }, { dark: !isLight });

        if (isLight) {
            return [
                this._cm.syntaxHighlighting(this._cm.defaultHighlightStyle, { fallback: true }),
                platformTheme,
            ];
        }
        if (this._cm.oneDark) {
            return [this._cm.oneDark, platformTheme];
        }
        return [
            this._cm.syntaxHighlighting(this._cm.defaultHighlightStyle, { fallback: true }),
            platformTheme,
        ];
    }

    _resolvedThemeMode() {
        const domTheme = document.documentElement.getAttribute('data-theme');
        if (domTheme === 'light' || domTheme === 'dark') {
            return domTheme;
        }
        const selected = this._themeSel.value;
        return selected === 'light' ? 'light' : 'dark';
    }

    _themeSignature() {
        return this._resolvedThemeMode();
    }

    _syncEditorTheme() {
        if (!this._editorView || !this._cm || !this._themeCompartment) {
            return;
        }
        const nextTheme = this._themeSignature();
        if (this._lastTheme === nextTheme) {
            return;
        }
        this._lastTheme = nextTheme;
        this._editorView.dispatch({
            effects: this._themeCompartment.reconfigure(this._buildThemeExtension()),
        });
    }

    render() {
        return html`
            <div class="editor-root">
                ${this.showToolbar ? html`
                    <div class="editor-toolbar">
                        <div class="editor-title">${this.language}</div>
                    </div>
                ` : null}
                <div id="cm-wrap"><div id="cm-host"></div></div>
            </div>
        `;
    }
}

customElements.define('platform-code-editor', PlatformCodeEditor);

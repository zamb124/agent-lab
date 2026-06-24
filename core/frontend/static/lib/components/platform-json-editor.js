/**
 * platform-json-editor — компактный CodeMirror viewer/editor для JSON в платформенных UI.
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

export class PlatformJsonEditor extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: String },
        readonly: { type: Boolean, reflect: true },
        showToolbar: { type: Boolean, attribute: 'show-toolbar' },
        fillParent: { type: Boolean, reflect: true, attribute: 'fill-parent' },
        fullscreen: { type: Boolean, reflect: true },
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
            :host([fullscreen]) {
                position: fixed;
                inset: var(--space-3);
                z-index: 10000;
                display: flex;
                flex-direction: column;
                background: var(--bg-primary);
                box-shadow: var(--shadow-xl);
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
            :host([fullscreen]) .editor-root {
                flex: 1 1 auto;
                min-height: 0;
            }
            .editor-root {
                display: flex;
                flex-direction: column;
                min-height: var(--json-editor-min-height, 220px);
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
            .toolbar-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            .icon-btn {
                width: 30px;
                height: 30px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
            }
            .icon-btn:hover,
            .icon-btn:focus-visible {
                color: var(--text-primary);
                border-color: var(--accent);
                outline: none;
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
                min-height: var(--json-editor-min-height, 220px);
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
        this.readonly = true;
        this.showToolbar = true;
        this.fillParent = false;
        this.fullscreen = false;
        this.minHeight = 220;
        this._cm = null;
        this._editorView = null;
        this._readonlyCompartment = null;
        this._themeCompartment = null;
        this._initInFlight = null;
        this._themeSel = this.select((s) => (s.theme && s.theme.mode ? s.theme.mode : 'dark'));
        this._lastTheme = undefined;
        this._themeObserver = null;
        this._onWindowKeydown = (e) => {
            if (e.key === 'Escape' && this.fullscreen) {
                this.fullscreen = false;
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('keydown', this._onWindowKeydown, true);
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
        window.removeEventListener('keydown', this._onWindowKeydown, true);
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
            this.style.setProperty('--json-editor-min-height', `${value}px`);
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

    async _init(host) {
        const cm = await loadCodeMirror();
        if (!this.isConnected || this._editorView) return;
        this._cm = cm;
        this._readonlyCompartment = new cm.Compartment();
        this._themeCompartment = new cm.Compartment();
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
                    cm.json(),
                    cm.bracketMatching(),
                    cm.indentOnInput(),
                    cm.EditorView.lineWrapping,
                    cm.EditorState.tabSize.of(4),
                    this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
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
            '.cm-matchingBracket, .cm-nonmatchingBracket': {
                backgroundColor: 'color-mix(in srgb, var(--accent) 14%, transparent)',
                outline: '1px solid var(--accent)',
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

    _toggleFullscreen() {
        this.fullscreen = !this.fullscreen;
        queueMicrotask(() => {
            if (this._editorView) this._editorView.requestMeasure();
        });
    }

    render() {
        return html`
            <div class="editor-root">
                ${this.showToolbar ? html`
                    <div class="editor-toolbar">
                        <div class="editor-title">JSON</div>
                        <div class="toolbar-actions">
                            <button
                                class="icon-btn"
                                type="button"
                                title=${this.fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                                aria-label=${this.fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                                @click=${() => this._toggleFullscreen()}
                            >
                                <platform-icon name=${this.fullscreen ? 'minimize' : 'fullscreen'} size="16"></platform-icon>
                            </button>
                        </div>
                    </div>
                ` : null}
                <div id="cm-wrap"><div id="cm-host"></div></div>
            </div>
        `;
    }
}

customElements.define('platform-json-editor', PlatformJsonEditor);

/**
 * flows-code-editor — обёртка над vendored CodeMirror.
 *
 * Lazy-импортирует `/static/core/assets/codemirror/codemirror-bundle.js` при
 * первом mount. Поддерживает языки раннеров, `json` и `text`. Тема
 * переключается по `select(s => s.theme.mode)`.
 *
 * Property API:
 *   - value: string
 *   - language: 'python' | 'javascript' | 'typescript' | 'go' | 'csharp' | 'json' | 'text'
 *   - readonly: boolean
 *   - placeholder: string (опц.)
 *   - showToolbar: boolean (шапка: полноэкран, подсказка про сохранение)
 *   - headerOnly: boolean — только шапка (слот + Save/Fullscreen), без CodeMirror (для соседнего контента под шапкой)
 *   - lineWrapping: boolean — принудительно переносить длинные строки; для JSON включено автоматически.
 *   - slot `toolbar-start` — светлый DOM слева в шапке (вкладки «Код»/«Схема» и т.п.).
 *   - completionContext: object (опц.) — query для `flows/code_completions` (`language`, `perspective`, `include_runtime_namespace_extras`).
 *   - completionVariableKeys: string[] (опц.) — ключи `variables` / `state.variables` для автодополнения.
 *
 * События (emit, slot-композиция):
 *   - 'change' { value }
 *   - 'save' { value }    — Cmd/Ctrl+S
 * Tab в фокусе редактора вставляет четыре пробела (без ухода фокуса в форму).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import {
    buildCodeCompletions,
    fetchCompletionCatalog,
} from '../../_helpers/flows-python-completion-catalog.js';
import { editorBodyPortalZIndex } from '@platform/lib/utils/modal-z-stack.js';

const CODEMIRROR_URL = '/static/core/assets/codemirror/codemirror-bundle.js';

const FLOWS_CM_TOOLTIP_MOUNT_ID = 'flows-cm-tooltip-mount';

/**
 * Единый контейнер на document.body для CM tooltips(): z-index инлайном (editorBodyPortalZIndex).
 * Внешний вид тултипов — селекторы `#flows-cm-tooltip-mount` в tokens.css (после инжекта baseTheme CM).
 *
 * @returns {HTMLElement}
 */
function ensureFlowsCmTooltipMount() {
    let el = document.getElementById(FLOWS_CM_TOOLTIP_MOUNT_ID);
    if (!el) {
        el = document.createElement('div');
        el.id = FLOWS_CM_TOOLTIP_MOUNT_ID;
        document.body.appendChild(el);
    }
    el.style.position = 'relative';
    el.style.pointerEvents = 'none';
    el.style.zIndex = String(editorBodyPortalZIndex());
    return el;
}

let _cmPromise = null;
function loadCodeMirror() {
    if (!_cmPromise) {
        _cmPromise = import(CODEMIRROR_URL);
    }
    return _cmPromise;
}

export class FlowsCodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        value: { type: String },
        language: { type: String },
        readonly: { type: Boolean },
        placeholder: { type: String },
        showToolbar: { type: Boolean, attribute: 'show-toolbar' },
        headerOnly: { type: Boolean, reflect: true, attribute: 'header-only' },
        fillParent: { type: Boolean, reflect: true, attribute: 'fill-parent' },
        fullscreen: { type: Boolean, reflect: true, attribute: 'fullscreen' },
        lineWrapping: { type: Boolean, reflect: true, attribute: 'line-wrapping' },
        completionContext: { type: Object, attribute: false },
        completionVariableKeys: { type: Array, attribute: false },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                min-width: 0;
                min-height: 120px;
                box-sizing: border-box;
                border-radius: var(--radius-md);
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                font-family: var(--font-mono, monospace);
            }
            :host([header-only]) {
                min-height: 0;
            }
            :host([header-only]) .editor-root {
                min-height: 0;
            }
            :host([fullscreen]) {
                position: fixed;
                z-index: 10000;
                top: 0;
                right: 0;
                bottom: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                min-height: 100vh;
                margin: 0;
                box-sizing: border-box;
                padding: var(--space-3);
                overflow: hidden;
                background: var(--bg-primary, var(--glass-solid-elevated));
            }
            :host([fullscreen]) .editor-root {
                height: 100%;
                display: flex;
                flex-direction: column;
                min-height: 0;
            }
            :host([fullscreen]) #cm-wrap {
                flex: 1;
                min-height: 0;
            }
            :host([fullscreen]) #cm-host,
            :host([fullscreen]) .cm-editor,
            :host([fullscreen]) .cm-scroller {
                min-height: 0;
                height: 100%;
            }
            :host([fill-parent]) {
                min-height: 0;
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                max-height: 100%;
            }
            :host([fill-parent]) .editor-root {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
                max-height: 100%;
            }
            :host([fill-parent]) #cm-wrap {
                flex: 1 1 auto;
                min-height: 0;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            :host([fill-parent]) #cm-host {
                flex: 1 1 auto;
                min-height: 0;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            :host([fill-parent]) .cm-editor {
                min-height: 0;
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                height: 100%;
                max-height: 100%;
            }
            :host([fill-parent]) .cm-scroller {
                flex: 1 1 auto;
                min-height: 0;
                overflow: auto;
            }
            .editor-header {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-medium);
                border-bottom: 1px solid var(--border-subtle);
                overflow-x: auto;
                scrollbar-width: thin;
            }
            .editor-header-leading {
                flex: 1 1 auto;
                min-width: 0;
                display: flex;
                align-items: center;
            }
            .editor-header-trailing {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-2);
                flex: 0 0 auto;
            }
            .header-actions {
                display: flex;
                flex-wrap: nowrap;
                align-items: center;
                gap: var(--space-1);
            }
            .hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .editor-icon-button {
                width: 32px;
                height: 32px;
                padding: 0;
                margin: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-full, 999px);
                cursor: pointer;
                flex: 0 0 auto;
                transition:
                    color var(--duration-fast, 0.2s) ease,
                    background var(--duration-fast, 0.2s) ease,
                    border-color var(--duration-fast, 0.2s) ease;
            }
            .editor-icon-button:hover,
            .editor-icon-button:focus-visible {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                outline: none;
            }
            .editor-root {
                display: flex;
                flex-direction: column;
                min-height: 120px;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
            }
            #cm-wrap {
                flex: 1 1 auto;
                min-height: 120px;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }
            #cm-host {
                height: 100%;
                min-height: 120px;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                overflow: hidden;
            }
            .cm-editor {
                height: 100%;
                min-height: 120px;
                min-width: 0;
                max-width: 100%;
                width: 100%;
                box-sizing: border-box;
                font-size: var(--text-sm);
                background: transparent;
            }
            .cm-editor.cm-focused {
                outline: none;
            }
            .cm-content {
                padding: var(--space-2) var(--space-3);
                min-width: 0;
                overflow-wrap: anywhere;
            }
            .cm-scroller {
                min-width: 0;
                max-width: 100%;
                width: 100%;
                box-sizing: border-box;
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
        this.readonly = false;
        this.placeholder = '';
        this.showToolbar = true;
        this.headerOnly = false;
        this.fillParent = false;
        this.fullscreen = false;
        this.lineWrapping = false;
        this.completionContext = null;
        this.completionVariableKeys = [];
        this._editorView = null;
        this._cm = null;
        this._readonlyCompartment = null;
        this._languageCompartment = null;
        this._themeCompartment = null;
        this._wrappingCompartment = null;
        this._completionsOp = this.useOp('flows/code_completions');
        this._themeSel = this.select((s) => (isPlainObject(s.theme) && s.theme.mode === 'light' ? 'light' : 'dark'));
        this._lastTheme = undefined;
        this._initInFlight = null;
        this._onWindowKeydown = (e) => {
            if (e.key === 'Escape' && this.fullscreen) {
                this.fullscreen = false;
            }
        };
    }

    connectedCallback() {
        super.connectedCallback();
        window.addEventListener('keydown', this._onWindowKeydown, true);
        this.updateComplete.then(() => {
            if (!this.isConnected || this.headerOnly) {
                return;
            }
            void this._ensureEditorMounted();
        });
    }

    disconnectedCallback() {
        window.removeEventListener('keydown', this._onWindowKeydown, true);
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
        this._initInFlight = null;
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('headerOnly')) {
            if (this.headerOnly) {
                if (this._editorView) {
                    this._editorView.destroy();
                    this._editorView = null;
                }
                this._initInFlight = null;
            } else if (!this._editorView && this.isConnected) {
                void this._ensureEditorMounted();
            }
        }
        if (this._editorView && (changed.has('fillParent') || changed.has('fullscreen'))) {
            queueMicrotask(() => {
                if (this._editorView) {
                    this._editorView.requestMeasure();
                }
            });
        }
        if (this._editorView && this._cm && this._themeCompartment) {
            const next = this._themeSel.value;
            if (this._lastTheme !== next) {
                this._lastTheme = next;
                this._editorView.dispatch({
                    effects: this._themeCompartment.reconfigure(this._buildThemeExtension()),
                });
            }
        }
        if (!this._editorView || !this._cm) {
            return;
        }
        if (changed.has('value')) {
            const current = this._editorView.state.doc.toString();
            if (current !== this.value) {
                this._editorView.dispatch({
                    changes: { from: 0, to: current.length, insert: asString(this.value) },
                });
            }
            if (this.fillParent) {
                queueMicrotask(() => {
                    if (this._editorView) {
                        this._editorView.requestMeasure();
                    }
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
        if ((changed.has('language') || changed.has('lineWrapping')) && this._wrappingCompartment) {
            this._editorView.dispatch({
                effects: this._wrappingCompartment.reconfigure(this._buildWrappingExtension()),
            });
        }
    }

    _toggleFullscreen() {
        this.fullscreen = !this.fullscreen;
    }

    async _ensureEditorMounted() {
        if (this.headerOnly) {
            return;
        }
        if (this._editorView) {
            return;
        }
        if (this._initInFlight) {
            return this._initInFlight;
        }
        const host = this.renderRoot.querySelector('#cm-host');
        if (!host) {
            queueMicrotask(() => {
                if (this.isConnected && !this._editorView) {
                    void this._ensureEditorMounted();
                }
            });
            return;
        }
        this._initInFlight = this._init(host).finally(() => {
            this._initInFlight = null;
        });
        return this._initInFlight;
    }

    async _init(host) {
        const cm = await loadCodeMirror();
        if (!this.isConnected || this._editorView || this.headerOnly) {
            return;
        }
        this._cm = cm;
        this._readonlyCompartment = new cm.Compartment();
        this._languageCompartment = new cm.Compartment();
        this._themeCompartment = new cm.Compartment();
        this._wrappingCompartment = new cm.Compartment();
        this._lastTheme = this._themeSel.value;
        const fourSpaces = '    ';
        const keymapForTab = [
            {
                key: 'Tab',
                run: (view) => {
                    if (view.state.readOnly) {
                        return false;
                    }
                    view.dispatch(view.state.replaceSelection(fourSpaces));
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
        const extensions = [
            cm.history(),
            cm.lineNumbers(),
            cm.tooltips({ parent: ensureFlowsCmTooltipMount(), position: 'absolute' }),
            this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
            this._languageCompartment.of(this._buildLanguageExtension()),
            this._themeCompartment.of(this._buildThemeExtension()),
            this._wrappingCompartment.of(this._buildWrappingExtension()),
            cm.EditorState.tabSize.of(4),
            cm.autocompletion({ override: [(ctx) => this._completionSource(ctx)] }),
            cm.keymap.of(keymapForTab),
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
                doc: asString(this.value),
                extensions,
            }),
            parent: host,
        });
        const docText = asString(this.value);
        if (this._editorView.state.doc.toString() !== docText) {
            this._editorView.dispatch({
                changes: { from: 0, to: this._editorView.state.doc.length, insert: docText },
            });
        }
        if (this.fillParent) {
            queueMicrotask(() => {
                if (this._editorView) {
                    this._editorView.requestMeasure();
                }
            });
        }
    }

    _buildLanguageExtension() {
        if (!this._cm) {
            return [];
        }
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

    _buildThemeExtension() {
        if (!this._cm) {
            return [];
        }
        const isDark = this._themeSel.value !== 'light';
        if (isDark) {
            return this._cm.oneDark ? this._cm.oneDark : [];
        }
        return this._cm.syntaxHighlighting(this._cm.defaultHighlightStyle, { fallback: true });
    }

    _buildWrappingExtension() {
        if (!this._cm) {
            return [];
        }
        const lang = typeof this.language === 'string' ? this.language : '';
        if (this.lineWrapping || lang === 'json') {
            return this._cm.EditorView.lineWrapping;
        }
        return [];
    }

    async _completionSource(ctx) {
        const language = typeof this.language === 'string' && this.language.length > 0 ? this.language : 'text';
        if (language === 'json' || language === 'text') {
            return null;
        }
        let catalog;
        try {
            catalog = await fetchCompletionCatalog(
                (payload) => this._completionsOp.run(payload),
                this.completionContext,
            );
        } catch {
            return null;
        }
        const variableKeys = Array.isArray(this.completionVariableKeys)
            ? this.completionVariableKeys.filter((k) => typeof k === 'string')
            : [];
        const built = buildCodeCompletions({
            language,
            docText: ctx.state.doc.toString(),
            pos: ctx.pos,
            catalog,
            variableKeys,
            explicit: ctx.explicit === true,
        });
        if (!built || built.options.length === 0) {
            return null;
        }
        return built;
    }

    _onSaveFromToolbar() {
        if (this._editorView) {
            this.emit('save', { value: this._editorView.state.doc.toString() });
        } else {
            this.emit('save', { value: asString(this.value) });
        }
    }

    render() {
        const fsLabel = this.fullscreen
            ? this.t('code_editor.exit_fullscreen')
            : this.t('code_editor.fullscreen');
        return html`
            <div class="editor-root">
                ${this.showToolbar
                    ? html`
                        <div class="editor-header">
                            <div class="editor-header-leading">
                                <slot name="toolbar-start"></slot>
                            </div>
                            <div class="editor-header-trailing">
                                <div class="header-actions">
                                    <button
                                        type="button"
                                        class="editor-icon-button"
                                        title=${this.t('editor_header.save')}
                                        aria-label=${this.t('editor_header.save')}
                                        @click=${this._onSaveFromToolbar}
                                    >
                                        <platform-icon name="save" size="16"></platform-icon>
                                    </button>
                                    <button
                                        type="button"
                                        class="editor-icon-button"
                                        title=${fsLabel}
                                        aria-label=${fsLabel}
                                        @click=${this._toggleFullscreen}
                                    >
                                        <platform-icon name=${this.fullscreen ? 'minimize' : 'fullscreen'} size="16"></platform-icon>
                                    </button>
                                </div>
                            </div>
                        </div>
                    `
                    : ''}
                ${this.headerOnly
                    ? ''
                    : html`
                <div id="cm-wrap">
                    <div id="cm-host"></div>
                </div>
                `}
            </div>
        `;
    }
}

customElements.define('flows-code-editor', FlowsCodeEditor);

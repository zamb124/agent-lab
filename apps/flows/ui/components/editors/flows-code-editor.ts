/**
 * flows-code-editor — обёртка над vendored CodeMirror.
 *
 * Lazy-импортирует `@platform/lib/codemirror/codemirror-lazy.js` при
 * первом mount. Поддерживает языки раннеров, `json` и `text`. Тема
 * переключается по `select(s => s.theme.mode)`.
 *
 * Свойства (API):
 *   - value: string
 *   - language: 'python' | 'javascript' | 'typescript' | 'go' | 'csharp' | 'json' | 'text'
 *   - readonly: boolean
 *   - placeholder: string (опц.)
 *   - showToolbar: boolean (шапка: полноэкран, подсказка про сохранение)
 *   - headerOnly: boolean — только шапка (слот + Save/Fullscreen), без CodeMirror (для соседнего контента под шапкой)
 *   - lineWrapping: boolean — принудительно переносить длинные строки; для JSON включено автоматически.
 *   - slot `toolbar-start` — светлый DOM слева в шапке (вкладки «Код»/«Схема» и т.п.).
 *   - completionContext: object (опц.) — `{ parameters_schema }` для typed `args` stub LSP.
 *   - completionVariableKeys: string[] (опц.) — ключи `variables` / `state.variables` в stub LSP.
 *
 * События (emit, slot-композиция):
 *   - 'change' { value }
 *   - 'save' { value }    — Cmd/Ctrl+S
 * Tab в фокусе редактора вставляет четыре пробела (без ухода фокуса в форму).
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { editorBodyPortalZIndex } from '@platform/lib/utils/modal-z-stack.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const LSP_LANGUAGES = new Set(['python', 'javascript', 'typescript', 'go', 'csharp']);

interface CodeMirrorDoc {
    toString(): string;
    length: number;
}

interface CodeMirrorEditorStateView {
    doc: CodeMirrorDoc;
    readOnly: boolean;
    replaceSelection(text: string): unknown;
}

interface CodeMirrorEditorView {
    state: CodeMirrorEditorStateView;
    dispatch(spec: unknown): void;
    destroy(): void;
    requestMeasure(): void;
}

interface CodeMirrorUpdate {
    docChanged: boolean;
    state: { doc: CodeMirrorDoc };
}

interface CodeMirrorCompartment {
    of(extension: unknown): unknown;
    reconfigure(extension: unknown): unknown;
}

interface CodeMirrorFacet<T> {
    of(value: T): unknown;
}

interface CodeMirrorEditorStateApi {
    readOnly: CodeMirrorFacet<boolean>;
    tabSize: CodeMirrorFacet<number>;
    create(config: { doc: string; extensions: unknown[] }): unknown;
}

interface CodeMirrorEditorViewApi {
    new (config: { state: unknown; parent: HTMLElement }): CodeMirrorEditorView;
    updateListener: { of(handler: (update: CodeMirrorUpdate) => void): unknown };
    theme(spec: Record<string, unknown>): unknown;
    lineWrapping: unknown;
}

interface CodeMirrorKeymapApi {
    of(bindings: readonly unknown[]): unknown;
}

interface LspClient {
    disconnect(): void;
    connect(transport: LspTransport): void;
    plugin(documentUri: string, languageId: string): unknown;
}

interface LspTransport {
    send(message: string): void;
    subscribe(handler: (data: unknown) => void): void;
    unsubscribe(handler: (data: unknown) => void): void;
}

interface CodeMirrorModule {
    Compartment: new () => CodeMirrorCompartment;
    EditorState: CodeMirrorEditorStateApi;
    EditorView: CodeMirrorEditorViewApi;
    history(): unknown;
    lineNumbers(): unknown;
    tooltips(options: { parent: HTMLElement; position: 'absolute' }): unknown;
    keymap: CodeMirrorKeymapApi;
    defaultKeymap: readonly unknown[];
    historyKeymap: readonly unknown[];
    python?(): unknown;
    javascript?(options: { typescript: boolean }): unknown;
    go?(): unknown;
    csharp?(): unknown;
    json?(): unknown;
    oneDark?: unknown;
    syntaxHighlighting(style: unknown, options: { fallback: boolean }): unknown;
    defaultHighlightStyle: unknown;
    LSPClient?: new (options: { rootUri: string; timeout: number; extensions: unknown }) => LspClient;
    languageServerExtensions?(): unknown;
}

interface LspSession {
    wsPath: string;
    documentUri: string;
    rootUri: string;
    languageId: string;
}

function isCodeMirrorModule(value: unknown): value is CodeMirrorModule {
    if (!isPlainObject(value)) {
        return false;
    }
    if (typeof value.Compartment !== 'function' || typeof value.EditorView !== 'function' || typeof value.EditorState !== 'function') {
        return false;
    }
    if (typeof value.history !== 'function' || typeof value.lineNumbers !== 'function' || typeof value.tooltips !== 'function') {
        return false;
    }
    if (typeof value.syntaxHighlighting !== 'function' || !isPlainObject(value.keymap) || typeof value.keymap.of !== 'function') {
        return false;
    }
    return Array.isArray(value.defaultKeymap) && Array.isArray(value.historyKeymap);
}

function lspSession(value: Record<string, unknown>): LspSession {
    const wsPath = value.ws_path;
    const documentUri = value.document_uri;
    const rootUri = value.root_uri;
    const languageId = value.language_id;
    if (typeof wsPath !== 'string' || !wsPath.startsWith('/')) {
        throw new Error('code lsp ws_path required');
    }
    if (typeof documentUri !== 'string' || documentUri.length === 0) {
        throw new Error('code lsp document_uri required');
    }
    if (typeof rootUri !== 'string' || rootUri.length === 0) {
        throw new Error('code lsp root_uri required');
    }
    if (typeof languageId !== 'string' || languageId.length === 0) {
        throw new Error('code lsp language_id required');
    }
    return { wsPath, documentUri, rootUri, languageId };
}

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

let _cmPromise: Promise<CodeMirrorModule> | null = null;
function loadCodeMirror(): Promise<CodeMirrorModule> {
    if (_cmPromise === null) {
        _cmPromise = import('@platform/lib/codemirror/codemirror-lazy.js').then(
            (mod) => {
                if (!isCodeMirrorModule(mod)) {
                    throw new Error('flows-code-editor: codemirror bundle required');
                }
                return mod;
            },
            (err) => {
                _cmPromise = null;
                throw err;
            },
        );
    }
    return _cmPromise;
}

export class FlowsCodeEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
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
    }
    declare value: string;
    declare language: string;
    declare readonly: boolean;
    declare placeholder: string;
    declare showToolbar: boolean;
    declare headerOnly: boolean;
    declare fillParent: boolean;
    declare fullscreen: boolean;
    declare lineWrapping: boolean;
    declare completionContext: Record<string, unknown> | null;
    declare completionVariableKeys: string[];
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        glassStyles,
        css`
            :host {
                display: block;
                width: 100%;
                max-width: 100%;
                min-width: 0;
                min-height: 120px;
                box-sizing: border-box;
                font-family: var(--font-mono);
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
                background: var(--bg-primary);
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
            .editor-root {
                display: flex;
                flex-direction: column;
                min-height: 120px;
                min-width: 0;
                max-width: 100%;
                box-sizing: border-box;
                border-radius: var(--radius-md);
                overflow: hidden;
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
    private _lspSessionOp: OpController;
    private _themeSel: SelectController<'dark' | 'light'>;
    private _editorView: CodeMirrorEditorView | null;
    private _cm: CodeMirrorModule | null;
    private _readonlyCompartment: CodeMirrorCompartment | null;
    private _languageCompartment: CodeMirrorCompartment | null;
    private _themeCompartment: CodeMirrorCompartment | null;
    private _wrappingCompartment: CodeMirrorCompartment | null;
    private _lspCompartment: CodeMirrorCompartment | null;
    private _lspClient: LspClient | null;
    private _lspSocket: WebSocket | null;
    private _lspGeneration: number;
    private _lspRestartTimer: number;
    /** Fingerprint language + schema + variable_keys активной LSP-сессии; рестарт только при смене содержимого. */
    private _lspSessionFingerprint: string;
    private _lastTheme: 'dark' | 'light' | undefined;
    private _initInFlight: Promise<void> | null;
    private _onWindowKeydown: (event: KeyboardEvent) => void;

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
        this._lspCompartment = null;
        this._lspSessionOp = this.useOp('flows/code_lsp_session');
        this._lspClient = null;
        this._lspSocket = null;
        this._lspGeneration = 0;
        this._lspRestartTimer = 0;
        this._lspSessionFingerprint = '';
        this._themeSel = this.select((state) => state.theme.mode);
        this._lastTheme = undefined;
        this._initInFlight = null;
        this._onWindowKeydown = (e: KeyboardEvent) => {
            if (e.key === 'Escape' && this.fullscreen) {
                this.fullscreen = false;
            }
        };
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useDomEvent(window, 'keydown', this._onWindowKeydown, true);
        this.updateComplete.then(() => {
            if (!this.isConnected || this.headerOnly) {
                return;
            }
            void this._ensureEditorMounted();
        });
    }

    override disconnectedCallback(): void {
        this._stopLsp();
        if (this._lspRestartTimer) {
            window.clearTimeout(this._lspRestartTimer);
            this._lspRestartTimer = 0;
        }
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
        this._initInFlight = null;
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('headerOnly')) {
            if (this.headerOnly) {
                this._stopLsp();
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
        if (
            changed.has('language')
            || changed.has('completionContext')
            || changed.has('completionVariableKeys')
        ) {
            this._maybeScheduleLspRestart();
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
        void this._initInFlight.then(
            () => {
                if (this.isConnected && !this.headerOnly && !this._editorView) {
                    queueMicrotask(() => {
                        if (this.isConnected && !this._editorView) {
                            void this._ensureEditorMounted();
                        }
                    });
                }
            },
            () => {
                if (!this.isConnected || this.headerOnly || this._editorView) {
                    return;
                }
                window.setTimeout(() => {
                    if (this.isConnected && !this._editorView) {
                        void this._ensureEditorMounted();
                    }
                }, 200);
            },
        );
        return this._initInFlight;
    }

    async _init(host: Element) {
        if (!(host instanceof HTMLElement)) {
            throw new Error('flows-code-editor: host element required');
        }
        const cm = await loadCodeMirror();
        if (!this.isConnected || this._editorView || this.headerOnly) {
            return;
        }
        this._cm = cm;
        this._readonlyCompartment = new cm.Compartment();
        this._languageCompartment = new cm.Compartment();
        this._themeCompartment = new cm.Compartment();
        this._wrappingCompartment = new cm.Compartment();
        this._lspCompartment = new cm.Compartment();
        this._lastTheme = this._themeSel.value;
        const fourSpaces = '    ';
        const keymapForTab = [
            {
                key: 'Tab',
                run: (view: CodeMirrorEditorView) => {
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
                    const editorView = this._editorView;
                    if (editorView === null) {
                        throw new Error('flows-code-editor: editor view required');
                    }
                    this.emit('save', { value: editorView.state.doc.toString() });
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
            this._lspCompartment.of([]),
            cm.EditorState.tabSize.of(4),
            cm.keymap.of(keymapForTab),
            cm.EditorView.updateListener.of((update: CodeMirrorUpdate) => {
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
        this._scheduleLspRestart();
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

    _lspFingerprintFromProps(): string {
        const language = typeof this.language === 'string' && this.language.length > 0 ? this.language : 'text';
        const ctx = isPlainObject(this.completionContext) ? this.completionContext : {};
        const parametersSchema = isPlainObject(ctx.parameters_schema)
            ? ctx.parameters_schema
            : { type: 'object', properties: {} };
        const variableKeys = Array.isArray(this.completionVariableKeys)
            ? this.completionVariableKeys.filter((key) => typeof key === 'string' && key.length > 0)
            : [];
        return JSON.stringify({
            language,
            parameters_schema: parametersSchema,
            variable_keys: variableKeys,
        });
    }

    _maybeScheduleLspRestart() {
        if (this._lspFingerprintFromProps() === this._lspSessionFingerprint) {
            return;
        }
        this._scheduleLspRestart();
    }

    _scheduleLspRestart() {
        if (this._lspRestartTimer) {
            window.clearTimeout(this._lspRestartTimer);
        }
        this._lspRestartTimer = window.setTimeout(() => {
            this._lspRestartTimer = 0;
            void this._restartLsp();
        }, 250);
    }

    _stopLsp() {
        this._lspGeneration += 1;
        this._lspSessionFingerprint = '';
        if (this._lspClient && typeof this._lspClient.disconnect === 'function') {
            this._lspClient.disconnect();
        }
        this._lspClient = null;
        if (this._lspSocket) {
            this._lspSocket.close();
            this._lspSocket = null;
        }
        if (this._editorView && this._lspCompartment && this._cm) {
            this._editorView.dispatch({
                effects: this._lspCompartment.reconfigure([]),
            });
        }
    }

    async _restartLsp() {
        if (!this._editorView || !this._cm || !this._lspCompartment) {
            return;
        }
        const language = typeof this.language === 'string' && this.language.length > 0 ? this.language : 'text';
        const fingerprint = this._lspFingerprintFromProps();
        if (fingerprint === this._lspSessionFingerprint && this._lspClient !== null) {
            return;
        }
        this._stopLsp();
        if (!LSP_LANGUAGES.has(language)) {
            return;
        }
        const generation = this._lspGeneration;
        const ctx = isPlainObject(this.completionContext) ? this.completionContext : {};
        const parametersSchema = isPlainObject(ctx.parameters_schema)
            ? ctx.parameters_schema
            : { type: 'object', properties: {} };
        const variableKeys = Array.isArray(this.completionVariableKeys)
            ? this.completionVariableKeys.filter((key) => typeof key === 'string' && key.length > 0)
            : [];
        let session;
        try {
            session = await this._lspSessionOp.run({
                language,
                source: this._editorView.state.doc.toString(),
                parameters_schema: parametersSchema,
                variable_keys: variableKeys,
            });
        } catch (err) {
            if (generation !== this._lspGeneration) {
                return;
            }
            this.toast('code_editor.lsp_failed', { type: 'error' });
            if (err instanceof Error) {
                return;
            }
            throw err;
        }
        if (generation !== this._lspGeneration || !this.isConnected || !this._editorView) {
            return;
        }
        if (!isPlainObject(session)) {
            throw new Error('code lsp session must be an object');
        }
        const lsp = lspSession(session);
        const LspClientCtor = this._cm.LSPClient;
        const languageServerExtensions = this._cm.languageServerExtensions;
        if (typeof LspClientCtor !== 'function' || typeof languageServerExtensions !== 'function') {
            throw new Error('codemirror lsp-client is required');
        }
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const socket = new WebSocket(`${protocol}//${window.location.host}${lsp.wsPath}`);
        await new Promise((resolve, reject) => {
            socket.addEventListener('open', () => resolve(undefined), { once: true });
            socket.addEventListener('error', () => reject(new Error('code lsp websocket failed')), { once: true });
        });
        if (generation !== this._lspGeneration) {
            socket.close();
            return;
        }
        const listeners = new Map<(data: unknown) => void, (event: Event) => void>();
        const transport: LspTransport = {
            send(message: string) {
                socket.send(message);
            },
            subscribe(handler: (data: unknown) => void) {
                const listener = (event: Event) => {
                    if (!(event instanceof MessageEvent)) {
                        throw new Error('lsp transport message required');
                    }
                    handler(event.data);
                };
                listeners.set(handler, listener);
                socket.addEventListener('message', listener);
            },
            unsubscribe(handler: (data: unknown) => void) {
                const listener = listeners.get(handler);
                if (listener === undefined) {
                    throw new Error('lsp transport handler is not subscribed');
                }
                socket.removeEventListener('message', listener);
                listeners.delete(handler);
            },
        };
        const client = new LspClientCtor({
            rootUri: lsp.rootUri,
            timeout: 20000,
            extensions: languageServerExtensions(),
        });
        client.connect(transport);
        this._lspClient = client;
        this._lspSocket = socket;
        this._lspSessionFingerprint = fingerprint;
        this._editorView.dispatch({
            effects: this._lspCompartment.reconfigure(
                client.plugin(lsp.documentUri, lsp.languageId),
            ),
        });
    }

    _onSaveFromToolbar() {
        if (this._editorView) {
            this.emit('save', { value: this._editorView.state.doc.toString() });
        } else {
            this.emit('save', { value: asString(this.value) });
        }
    }

    override render(): TemplateResult {
        const fsLabel = this.fullscreen
            ? this.t('code_editor.exit_fullscreen')
            : this.t('code_editor.fullscreen');
        return html`
            <div class="editor-root glass-subtle">
                ${this.showToolbar
                    ? html`
                        <div class="editor-header">
                            <div class="editor-header-leading">
                                <slot name="toolbar-start"></slot>
                            </div>
                            <div class="editor-header-trailing">
                                <div class="header-actions">
                                    <platform-button
                                        variant="ghost"
                                        icon-only
                                        density="compact"
                                        title=${this.t('editor_header.save')}
                                        aria-label=${this.t('editor_header.save')}
                                        @click=${this._onSaveFromToolbar}
                                    >
                                        <platform-icon name="save" size="16"></platform-icon>
                                    </platform-button>
                                    <platform-button
                                        variant="ghost"
                                        icon-only
                                        density="compact"
                                        title=${fsLabel}
                                        aria-label=${fsLabel}
                                        @click=${this._toggleFullscreen}
                                    >
                                        <platform-icon name=${this.fullscreen ? 'minimize' : 'fullscreen'} size="16"></platform-icon>
                                    </platform-button>
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

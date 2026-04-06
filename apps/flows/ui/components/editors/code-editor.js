/**
 * CodeEditor - универсальный редактор кода с CodeMirror 6
 * Поддержка Python/JavaScript, документация, шаблоны
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import '@platform/lib/components/platform-icon.js';
import {
    FLOWS_NODE_FILE_MIME,
    buildPythonReadFileSnippet,
    prefixCodeLines,
} from '../../utils/file-signature.js';

const DEFAULT_PYTHON = `def execute(args, state):
    """
    Process state.

    Args:
        args: Invocation arguments
        state: Current execution state

    Returns:
        Execution result dict
    """
    return {"result": "ok"}
`;

const DEFAULT_JAVASCRIPT = `async function execute(args, state) {
    /**
     * Process state.
     *
     * @param {Object} args - Invocation arguments
     * @param {Object} state - Current execution state
     * @returns {Object} Execution result
     */
    return { result: "ok" };
}
`;

export class CodeEditor extends PlatformElement {
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
                gap: var(--space-2);
            }

            .editor-header-start {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                flex: 1;
            }

            .code-schema-pane-toggle {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
            }
            
            .editor-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }

            .schema-body-slot-wrap {
                min-height: var(--editor-min-height, 200px);
                max-height: min(70vh, 780px);
                overflow-x: hidden;
                overflow-y: auto;
                display: block;
                min-width: 0;
                overscroll-behavior: contain;
            }

            .schema-body-slot-wrap > slot::slotted(*) {
                display: block;
                min-height: 0;
                max-width: 100%;
            }
            
            .editor-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            .editor-actions-overflow {
                position: relative;
                flex-shrink: 0;
            }

            .editor-overflow-menu-btn {
                padding: var(--space-1) var(--space-2);
            }

            .editor-overflow-dropdown {
                position: absolute;
                top: 100%;
                right: 0;
                margin-top: var(--space-1);
                min-width: 220px;
                max-width: min(92vw, 320px);
                max-height: min(72vh, 480px);
                overflow-x: hidden;
                overflow-y: auto;
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-strong);
                z-index: 120;
                padding: var(--space-1) 0;
            }

            .editor-overflow-dropdown .templates-dropdown {
                position: static;
                margin-top: 0;
                max-height: min(50vh, 360px);
                box-shadow: none;
                border: none;
                border-radius: 0;
            }

            .editor-overflow-section-label {
                padding: var(--space-1) var(--space-3) var(--space-1);
                font-size: 10px;
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.06em;
            }

            .editor-overflow-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                text-align: left;
                cursor: pointer;
                border-radius: var(--radius-sm);
            }

            .editor-overflow-item:hover {
                background: var(--glass-tint-medium);
            }

            .editor-overflow-item.active-lang {
                color: var(--accent);
                font-weight: var(--font-medium);
            }

            slot[name='schema-header-actions']::slotted(button) {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                font-family: inherit;
            }

            slot[name='schema-header-actions']::slotted(button):hover {
                color: var(--text-primary);
                border-color: var(--accent);
                background: var(--glass-tint-medium);
            }
            
            .lang-toggle {
                display: flex;
                align-items: center;
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-full);
                padding: 2px;
                gap: 0;
            }
            
            .lang-toggle-option {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
                background: transparent;
                border: none;
                border-radius: var(--radius-full);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                white-space: nowrap;
            }
            
            .lang-toggle-option platform-icon {
                opacity: 0.7;
                --icon-color: currentColor;
            }
            
            .lang-toggle-option.active platform-icon {
                opacity: 1;
                --icon-color: #1a1a1a;
            }
            
            .lang-toggle-option:hover:not(.active) {
                color: var(--text-secondary);
            }
            
            .lang-toggle-option.active {
                color: #1a1a1a;
                background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
            }
            
            .editor-btn {
                display: flex;
                align-items: center;
                gap: var(--space-1);
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
                background: var(--glass-tint-medium);
            }
            
            .editor-btn.active {
                color: var(--accent);
                border-color: var(--accent);
            }
            
            .templates-container {
                position: relative;
            }
            
            .templates-dropdown {
                position: absolute;
                top: 100%;
                right: 0;
                margin-top: var(--space-1);
                min-width: 280px;
                max-height: 400px;
                overflow-y: auto;
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-default);
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-strong);
                z-index: 100;
            }
            
            .templates-category {
                padding: var(--space-1) var(--space-3);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                background: var(--glass-tint-subtle);
                border-bottom: 1px solid var(--border-subtle);
            }
            
            .template-item {
                display: flex;
                flex-direction: column;
                gap: 2px;
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                border-bottom: 1px solid var(--border-subtle);
                transition: background var(--duration-fast) var(--easing-default);
            }
            
            .template-item:hover {
                background: var(--glass-tint-medium);
            }
            
            .template-item:last-child {
                border-bottom: none;
            }
            
            .template-name {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
            
            .template-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
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
            
            :host(.fullscreen.fullscreen-embedded) {
                position: absolute;
                inset: 0;
                z-index: 30;
                box-sizing: border-box;
                margin: 0;
                background: var(--glass-solid-strong);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                min-height: 0;
                isolation: isolate;
            }

            :host(.fullscreen:not(.fullscreen-embedded)) {
                position: fixed;
                inset: 0;
                z-index: var(--platform-modal-layer-z, 30050);
                box-sizing: border-box;
                margin: 0;
                background: var(--bg-base);
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                min-height: 0;
            }

            :host(.fullscreen) .editor-wrapper {
                flex: 1 1 0%;
                min-height: 0;
                display: flex;
                flex-direction: column;
                background: var(--glass-solid-strong);
            }

            :host(.fullscreen) .editor-header {
                flex-shrink: 0;
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--border-default);
            }

            :host(.fullscreen) .validation-status.visible {
                flex-shrink: 0;
            }
            
            :host(.fullscreen) #codemirror-container {
                flex: 1 1 0%;
                min-height: 0;
                overflow: hidden;
                position: relative;
            }
            
            :host(.fullscreen) #codemirror-container .cm-editor {
                height: 100% !important;
                max-height: 100%;
                min-height: 0 !important;
                overflow: hidden !important;
                display: flex !important;
                flex-direction: column !important;
            }
            
            :host(.fullscreen) #codemirror-container .cm-scroller {
                flex: 1 1 0% !important;
                min-height: 0 !important;
                overflow: auto !important;
            }

            :host(.fullscreen) .schema-body-slot-wrap {
                flex: 1 1 0%;
                min-height: 0;
                max-height: none;
                overflow: auto;
            }
        `
    ];

    static properties = {
        value: { type: String },
        language: { type: String },
        nodeType: { type: String, attribute: 'node-type' },
        readonly: { type: Boolean },
        minHeight: { type: Number, attribute: 'min-height' },
        showHeader: { type: Boolean, attribute: 'show-header' },
        showDocs: { type: Boolean, attribute: 'show-docs' },
        showTemplates: { type: Boolean, attribute: 'show-templates' },
        showLanguageSwitch: { type: Boolean, attribute: 'show-language-switch' },
        acceptNodeFileDrop: { type: Boolean, attribute: 'accept-node-file-drop' },
        /** Режим code-node: переключатель Код/Схема в одной шапке с кнопками редактора */
        codeSchemaMode: { type: Boolean, attribute: 'code-schema-mode' },
        /** Активная вкладка при codeSchemaMode: code | schema (задаёт родитель) */
        activeSchemaPane: { type: String, attribute: 'active-schema-pane' },
        /** Родитель в широком режиме (полноэкран модалки, развёрнутая панель) — кнопки шапки в строку, без ⋮ */
        parentLayoutWide: { type: Boolean, attribute: 'parent-layout-wide' },
        validationStatus: { type: String },
        validationMessage: { type: String },
        _templatesOpen: { type: Boolean, state: true },
        _templates: { type: Array, state: true },
        _fullscreen: { type: Boolean, state: true },
        _actionsMenuOpen: { type: Boolean, state: true },
        _overflowTemplatesView: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this.value = '';
        this.language = 'python';
        this.nodeType = 'code';
        this.readonly = false;
        this.minHeight = 200;
        this.showHeader = true;
        this.showDocs = true;
        this.showTemplates = true;
        this.showLanguageSwitch = true;
        this.acceptNodeFileDrop = false;
        this.codeSchemaMode = false;
        this.activeSchemaPane = 'code';
        this.parentLayoutWide = false;
        this.validationStatus = '';
        this.validationMessage = '';
        this._templatesOpen = false;
        this._templates = [];
        this._fullscreen = false;
        this._actionsMenuOpen = false;
        this._overflowTemplatesView = false;
        /** @type {ParentNode | null} */
        this._fsPortalParent = null;
        /** @type {ChildNode | null} */
        this._fsPortalNext = null;
        /** @type {HTMLElement[]} */
        this._editorFullscreenHosts = [];
        /** @type {HTMLElement | null} */
        this._fullscreenEmbedRoot = null;
        this._fsPortalReparent = false;
        this._boundClickOutside = (e) => this._handleClickOutside(e);
        this._boundKeydownFs = (e) => this._handleKeydown(e);
        this._cmReady = false;
        this._editorView = null;
        this._cmModules = null;
        this._readonlyCompartment = null;
        this._languageCompartment = null;
        this._completionData = null;
        /** @type {null | (() => void)} */
        this._nodeFileDropCleanup = null;
    }

    get _defaultCode() {
        return this.language === 'javascript' ? DEFAULT_JAVASCRIPT : DEFAULT_PYTHON;
    }

    async firstUpdated() {
        await this._initCodeMirror();
        document.addEventListener('click', this._boundClickOutside);
        document.addEventListener('keydown', this._boundKeydownFs);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._fsPortalReparent) {
            return;
        }
        document.removeEventListener('click', this._boundClickOutside);
        document.removeEventListener('keydown', this._boundKeydownFs);
        if (this._fullscreen) {
            this._fullscreen = false;
            this.classList.remove('fullscreen', 'fullscreen-embedded');
            this.style.removeProperty('--platform-modal-layer-z');
            if (this._fullscreenEmbedRoot) {
                this._fullscreenEmbedRoot = null;
            } else {
                document.body.style.overflow = '';
            }
            this._clearEditorFullscreenMask();
            this._fsPortalParent = null;
            this._fsPortalNext = null;
        }
        if (this._editorView) {
            this._teardownNodeFileDropListeners();
            this._editorView.destroy();
            this._editorView = null;
        }
    }

    _handleKeydown(e) {
        if (e.key === 'Escape') {
            if (this._actionsMenuOpen) {
                if (this._overflowTemplatesView) {
                    this._overflowTemplatesView = false;
                } else {
                    this._actionsMenuOpen = false;
                }
                return;
            }
            if (this._fullscreen) {
                this._toggleFullscreen();
            }
        }
    }

    _handleClickOutside(e) {
        const path = e.composedPath();
        if (this._templatesOpen && !path.includes(this)) {
            this._templatesOpen = false;
        }
        if (this._actionsMenuOpen) {
            const overflowRoot = this.shadowRoot?.querySelector('.editor-actions-overflow');
            if (overflowRoot && !path.includes(overflowRoot)) {
                this._actionsMenuOpen = false;
                this._overflowTemplatesView = false;
            }
        }
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
        
        if (changedProperties.has('language') && this._editorView && this._languageCompartment && this._cmModules) {
            this._switchLanguage();
        }

        if (
            (changedProperties.has('acceptNodeFileDrop') || changedProperties.has('language')) &&
            this._editorView
        ) {
            this._syncNodeFileDropListeners();
        }

        if (changedProperties.has('activeSchemaPane') && this.codeSchemaMode) {
            void this._afterActiveSchemaPaneChange();
        }
    }

    async _afterActiveSchemaPaneChange() {
        await this.updateComplete;
        await new Promise((r) => requestAnimationFrame(r));
        await new Promise((r) => requestAnimationFrame(r));
        const pane = this._effectiveSchemaPane();
        if (pane === 'code' && this._editorView) {
            this._editorView.requestMeasure();
        }
        if (pane === 'schema') {
            const slotHost = this.querySelector('[slot="schema-body"]');
            const jsonEd = slotHost?.querySelector?.('json-field-editor');
            if (jsonEd && typeof jsonEd.refreshLayout === 'function') {
                jsonEd.refreshLayout();
            }
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
            javascript: cm.javascript,
            oneDark: cm.oneDark,
        };

        await this._loadCompletionData();
        this._createEditor();
        this._cmReady = true;
    }

    async _loadCompletionData() {
        if (!this.a2a) return;
        
        // Бэкенд поддерживает только python, для других языков используем python completions
        const lang = this.language === 'python' ? 'python' : 'python';
        const params = new URLSearchParams({
            language: lang,
            perspective: 'editor',
        });
        
        try {
            this._completionData = await this.a2a.get(`/api/v1/code/completions?${params}`);
        } catch (e) {
            console.warn('Failed to load code completions:', e);
            this._completionData = null;
        }
    }

    async _loadTemplates() {
        if (!this.a2a) return;
        
        // Бэкенд может не поддерживать все языки
        const lang = this.language === 'python' ? 'python' : 'python';
        const params = new URLSearchParams({
            language: lang,
        });
        if (this.nodeType) {
            params.set('node_type', this.nodeType);
        }
        
        try {
            const response = await this.a2a.get(`/api/v1/code/templates?${params}`);
            this._templates = response?.templates || [];
        } catch (e) {
            console.warn('Failed to load templates:', e);
            this._templates = [];
        }
    }

    _getLanguageExtension() {
        const cm = this._cmModules;
        if (this.language === 'javascript' && cm.javascript) {
            return cm.javascript();
        }
        // Python как fallback для всех языков
        return cm.python();
    }

    _createEditor() {
        const container = this.shadowRoot.querySelector('#codemirror-container');
        if (!container) return;

        const cm = this._cmModules;
        const isDarkTheme = document.documentElement.getAttribute('data-theme') !== 'light';
        
        this._readonlyCompartment = new cm.Compartment();
        this._languageCompartment = new cm.Compartment();
        
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
            this._languageCompartment.of(this._getLanguageExtension()),
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
                    this.emit('change', { value: this.value, language: this.language });
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
        this._syncNodeFileDropListeners();
    }

    _teardownNodeFileDropListeners() {
        if (this._nodeFileDropCleanup) {
            this._nodeFileDropCleanup();
            this._nodeFileDropCleanup = null;
        }
    }

    /**
     * Отступ для вставляемого блока: по текущей строке или по контексту (пустая строка после `:`).
     * @param {number} pos
     * @returns {string}
     */
    _baseIndentAtDocPos(pos) {
        const doc = this._editorView.state.doc;
        const line = doc.lineAt(pos);
        const lead = /^[\t ]*/.exec(line.text);
        if (line.text.trim() !== '') {
            return lead ? lead[0] : '';
        }
        for (let n = line.number - 1; n >= 1; n--) {
            const prevText = doc.line(n).text;
            if (prevText.trim() === '') {
                continue;
            }
            const prevLead = /^[\t ]*/.exec(prevText);
            const base = prevLead ? prevLead[0] : '';
            const trimmedEnd = prevText.trimEnd();
            if (/:\s*(#.*)?$/.test(trimmedEnd)) {
                if (base.includes('\t')) {
                    return `${base}\t`;
                }
                return `${base}    `;
            }
            return base;
        }
        return lead ? lead[0] : '';
    }

    _syncNodeFileDropListeners() {
        this._teardownNodeFileDropListeners();
        if (!this.acceptNodeFileDrop || !this._editorView || this.readonly) {
            return;
        }
        const dom = this._editorView.dom;
        const typesIncludeNodeFile = (e) => {
            const types = e.dataTransfer?.types ? Array.from(e.dataTransfer.types) : [];
            return types.includes(FLOWS_NODE_FILE_MIME);
        };
        const onDragOverCapture = (e) => {
            if (!typesIncludeNodeFile(e)) {
                return;
            }
            e.preventDefault();
            e.stopImmediatePropagation();
            e.dataTransfer.dropEffect = 'copy';
        };
        const onDropCapture = (e) => {
            if (!typesIncludeNodeFile(e)) {
                return;
            }
            const raw = e.dataTransfer.getData(FLOWS_NODE_FILE_MIME);
            if (!raw) {
                return;
            }
            e.preventDefault();
            e.stopImmediatePropagation();
            let parsed;
            try {
                parsed = JSON.parse(raw);
            } catch {
                return;
            }
            if (typeof parsed !== 'object' || parsed === null || typeof parsed.name !== 'string') {
                return;
            }
            if (this.language !== 'python') {
                this.warning(this.i18n.t('code_editor.node_file_drop_python_only'));
                return;
            }
            let insertPos = this._editorView.posAtCoords({ x: e.clientX, y: e.clientY });
            if (insertPos == null) {
                insertPos = this._editorView.state.selection.main.head;
            }
            const baseIndent = this._baseIndentAtDocPos(insertPos);
            const snippet = prefixCodeLines(buildPythonReadFileSnippet(parsed), baseIndent);
            this._editorView.dispatch({
                changes: { from: insertPos, to: insertPos, insert: snippet },
                selection: { anchor: insertPos + snippet.length, head: insertPos + snippet.length },
            });
        };
        dom.addEventListener('dragover', onDragOverCapture, true);
        dom.addEventListener('drop', onDropCapture, true);
        this._nodeFileDropCleanup = () => {
            dom.removeEventListener('dragover', onDragOverCapture, true);
            dom.removeEventListener('drop', onDropCapture, true);
        };
    }

    _switchLanguage() {
        if (!this._editorView || !this._languageCompartment || !this._cmModules) return;
        
        this._editorView.dispatch({
            effects: this._languageCompartment.reconfigure(this._getLanguageExtension())
        });
        
        this._loadCompletionData();
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

    insertCode(code) {
        if (this._editorView) {
            const pos = this._editorView.state.selection.main.head;
            this._editorView.dispatch({
                changes: { from: pos, insert: code }
            });
        }
    }

    insertTextAtSelection(text) {
        if (!this._editorView || !text) {
            return;
        }
        const { from, to } = this._editorView.state.selection.main;
        this._editorView.dispatch({
            changes: { from, to, insert: text },
            selection: { anchor: from + text.length, head: from + text.length },
        });
    }

    replaceCode(code) {
        this.setValue(code);
    }

    _isDefaultCode(code) {
        if (!code) return true;
        const trimmed = code.trim();
        return trimmed === '' || 
               trimmed === DEFAULT_PYTHON.trim() || 
               trimmed === DEFAULT_JAVASCRIPT.trim();
    }

    _switchToLanguage(newLang) {
        if (newLang === this.language) return;
        
        const oldLang = this.language;
        const currentCode = this.getValue();
        
        // Сохраняем код для текущего языка
        if (!this._isDefaultCode(currentCode)) {
            this._savedCode = this._savedCode || {};
            this._savedCode[oldLang] = currentCode;
        }
        
        this.language = newLang;
        
        // Проверяем, есть ли сохранённый код для нового языка
        if (this._savedCode?.[newLang]) {
            this.setValue(this._savedCode[newLang]);
        } else if (this._isDefaultCode(currentCode)) {
            // Вставляем дефолтный код для нового языка
            const defaultCode = newLang === 'javascript' ? DEFAULT_JAVASCRIPT : DEFAULT_PYTHON;
            this.setValue(defaultCode);
        }
        // Иначе оставляем текущий код как есть
        
        this.emit('language-change', { language: newLang });
    }

    async _toggleTemplates(e) {
        e.stopPropagation();
        if (!this._templatesOpen) {
            await this._loadTemplates();
        }
        this._templatesOpen = !this._templatesOpen;
    }

    _selectTemplate(template) {
        this.replaceCode(template.code);
        this._templatesOpen = false;
        this._actionsMenuOpen = false;
        this._overflowTemplatesView = false;
        this.emit('template-selected', { template });
    }

    _closeActionsMenu() {
        this._actionsMenuOpen = false;
        this._overflowTemplatesView = false;
    }

    _toggleActionsMenu(e) {
        e.stopPropagation();
        const next = !this._actionsMenuOpen;
        this._actionsMenuOpen = next;
        if (!next) {
            this._overflowTemplatesView = false;
        }
    }

    _overflowTemplatesBack(e) {
        e.stopPropagation();
        this._overflowTemplatesView = false;
    }

    async _openOverflowTemplatesPanel(e) {
        e.stopPropagation();
        await this._loadTemplates();
        this._overflowTemplatesView = true;
    }

    async _onOverflowCopy(e) {
        e.stopPropagation();
        await this._copyCode();
        this._closeActionsMenu();
    }

    _onOverflowDocs(e) {
        e.stopPropagation();
        this._openDocs();
        this._closeActionsMenu();
    }

    _onOverflowFullscreen(e) {
        e.stopPropagation();
        this._toggleFullscreen();
        this._closeActionsMenu();
    }

    _onOverflowSwitchLanguage(e, lang) {
        e.stopPropagation();
        this._switchToLanguage(lang);
        this._closeActionsMenu();
    }

    _openDocs() {
        this.emit('open-docs', { 
            language: this.language, 
            nodeType: this.nodeType,
            perspective: 'editor'
        });
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
        const text = this.getValue();
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
            }
            this._notifyCopied();
        } catch (e) {
            console.warn('Copy failed:', e);
            this.error(this.i18n.t('code_editor.copy_failed'));
        }
    }

    _clearEditorFullscreenMask() {
        for (const host of this._editorFullscreenHosts) {
            host.removeAttribute('data-editor-fullscreen');
        }
        this._editorFullscreenHosts = [];
    }

    _applyEditorFullscreenMask() {
        this._editorFullscreenHosts = [];
        let el = this;
        for (let i = 0; i < 64; i++) {
            const root = el.getRootNode();
            if (!(root instanceof ShadowRoot) || !(root.host instanceof HTMLElement)) {
                break;
            }
            const host = root.host;
            host.setAttribute('data-editor-fullscreen', '');
            this._editorFullscreenHosts.push(host);
            el = host;
        }
    }

    _scheduleEditorMeasure() {
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                if (this._editorView) {
                    this._editorView.requestMeasure();
                }
            });
        });
    }

    _getFullscreenEmbedRoot() {
        let el = this.parentElement;
        for (let depth = 0; depth < 64 && el; depth++) {
            if (el.nodeType === Node.ELEMENT_NODE && el.classList) {
                if (
                    el.classList.contains('floating-panel-body')
                    || el.classList.contains('modal-content')
                    || el.classList.contains('modal-content-wrapper')
                ) {
                    return el;
                }
            }
            const parent = el.parentElement;
            if (parent) {
                el = parent;
                continue;
            }
            const root = el.getRootNode();
            if (root instanceof ShadowRoot && root.host) {
                el = root.host;
                continue;
            }
            break;
        }
        return null;
    }

    _toggleFullscreen() {
        this._fullscreen = !this._fullscreen;
        if (this._fullscreen) {
            this._applyEditorFullscreenMask();
            this.classList.add('fullscreen');
            const embedRoot = this._getFullscreenEmbedRoot();
            if (embedRoot) {
                this.classList.add('fullscreen-embedded');
                this._fullscreenEmbedRoot = embedRoot;
            } else {
                this._fullscreenEmbedRoot = null;
                this._fsPortalParent = this.parentNode;
                this._fsPortalNext = this.nextSibling;
                this.style.setProperty(
                    '--platform-modal-layer-z',
                    String(nextModalLayerZIndex()),
                );
                this._fsPortalReparent = true;
                try {
                    document.body.appendChild(this);
                } finally {
                    this._fsPortalReparent = false;
                }
                document.body.style.overflow = 'hidden';
            }
        } else {
            this.classList.remove('fullscreen', 'fullscreen-embedded');
            this._clearEditorFullscreenMask();
            if (this._fullscreenEmbedRoot) {
                this._fullscreenEmbedRoot = null;
            } else {
                this.style.removeProperty('--platform-modal-layer-z');
                document.body.style.overflow = '';
                const parent = this._fsPortalParent;
                const next = this._fsPortalNext;
                this._fsPortalParent = null;
                this._fsPortalNext = null;
                this._fsPortalReparent = true;
                try {
                    if (parent) {
                        if (next && next.parentNode === parent) {
                            parent.insertBefore(this, next);
                        } else {
                            parent.appendChild(this);
                        }
                    }
                } finally {
                    this._fsPortalReparent = false;
                }
            }
        }
        this._scheduleEditorMeasure();
    }

    showValidation(status, message) {
        this.validationStatus = status;
        this.validationMessage = message;
    }

    hideValidation() {
        this.validationStatus = '';
        this.validationMessage = '';
    }

    _effectiveSchemaPane() {
        if (!this.codeSchemaMode) {
            return 'code';
        }
        return this.activeSchemaPane === 'schema' ? 'schema' : 'code';
    }

    _emitCodeSchemaPane(pane) {
        if (!this.codeSchemaMode) {
            return;
        }
        const next = pane === 'schema' ? 'schema' : 'code';
        if (this._effectiveSchemaPane() === next) {
            return;
        }
        this.emit('code-schema-pane-change', { pane: next });
    }

    _useCompactCodeHeaderActions() {
        return (
            this.codeSchemaMode &&
            !this._fullscreen &&
            !this.parentLayoutWide
        );
    }

    _renderEditorActionsForCodePane() {
        if (this._useCompactCodeHeaderActions()) {
            return this._renderEditorActionsCompact();
        }
        return this._renderEditorActionsExpanded();
    }

    _renderEditorActionsExpanded() {
        return html`
            ${this.showLanguageSwitch
                ? html`
                      <div class="lang-toggle">
                          <button
                              type="button"
                              class="lang-toggle-option ${this.language === 'python' ? 'active' : ''}"
                              @click=${() => this._switchToLanguage('python')}
                          >
                              <platform-icon name="python" size="12" filled></platform-icon>
                              Python
                          </button>
                          <button
                              type="button"
                              class="lang-toggle-option ${this.language === 'javascript' ? 'active' : ''}"
                              @click=${() => this._switchToLanguage('javascript')}
                          >
                              <platform-icon name="javascript" size="12" filled></platform-icon>
                              JS
                          </button>
                      </div>
                  `
                : ''}
            ${this.showTemplates
                ? html`
                      <div class="templates-container">
                          <button
                              class="editor-btn ${this._templatesOpen ? 'active' : ''}"
                              @click=${this._toggleTemplates}
                          >
                              <platform-icon file-icon name="text" size="12"></platform-icon>
                              ${this.i18n.t('code_editor.templates')}
                          </button>
                          ${this._renderTemplatesDropdown()}
                      </div>
                  `
                : ''}
            ${this.showDocs
                ? html`
                      <button class="editor-btn" @click=${this._openDocs}>
                          <platform-icon name="book-open" size="12"></platform-icon>
                          ${this.i18n.t('code_editor.docs')}
                      </button>
                  `
                : ''}
            <button class="editor-btn" @click=${this._copyCode}>
                <platform-icon name="copy" size="12"></platform-icon>
            </button>
            <button
                class="editor-btn"
                @click=${this._toggleFullscreen}
                title="${this._fullscreen
                    ? this.i18n.t('code_editor.fullscreen_min')
                    : this.i18n.t('code_editor.fullscreen_max')}"
            >
                <platform-icon name="${this._fullscreen ? 'minimize' : 'maximize'}" size="12"></platform-icon>
            </button>
        `;
    }

    _renderEditorActionsCompact() {
        return html`
            <div class="editor-actions-overflow">
                <button
                    type="button"
                    class="editor-btn editor-overflow-menu-btn"
                    @click=${this._toggleActionsMenu}
                    title=${this.i18n.t('code_editor.more_actions')}
                    aria-expanded=${this._actionsMenuOpen ? 'true' : 'false'}
                    aria-haspopup="true"
                >
                    <platform-icon name="more-vert" size="18"></platform-icon>
                </button>
                ${this._actionsMenuOpen ? this._renderOverflowMenuDropdown() : ''}
            </div>
        `;
    }

    _renderOverflowMenuDropdown() {
        if (this._overflowTemplatesView) {
            return html`
                <div class="editor-overflow-dropdown" role="menu">
                    <button type="button" class="editor-overflow-item" @click=${this._overflowTemplatesBack}>
                        <platform-icon name="chevron-left" size="14"></platform-icon>
                        ${this.i18n.t('code_editor.back')}
                    </button>
                    ${this._renderTemplatesDropdown()}
                </div>
            `;
        }
        return html`
            <div class="editor-overflow-dropdown" role="menu">
                ${this.showLanguageSwitch
                    ? html`
                          <div class="editor-overflow-section-label">${this.i18n.t('code_editor.language')}</div>
                          <button
                              type="button"
                              class="editor-overflow-item ${this.language === 'python' ? 'active-lang' : ''}"
                              @click=${(ev) => this._onOverflowSwitchLanguage(ev, 'python')}
                          >
                              <platform-icon name="python" size="14" filled></platform-icon>
                              Python
                          </button>
                          <button
                              type="button"
                              class="editor-overflow-item ${this.language === 'javascript' ? 'active-lang' : ''}"
                              @click=${(ev) => this._onOverflowSwitchLanguage(ev, 'javascript')}
                          >
                              <platform-icon name="javascript" size="14"></platform-icon>
                              JS
                          </button>
                      `
                    : ''}
                ${this.showTemplates
                    ? html`
                          <button type="button" class="editor-overflow-item" @click=${this._openOverflowTemplatesPanel}>
                              <platform-icon file-icon name="text" size="14"></platform-icon>
                              ${this.i18n.t('code_editor.templates')}
                          </button>
                      `
                    : ''}
                ${this.showDocs
                    ? html`
                          <button type="button" class="editor-overflow-item" @click=${this._onOverflowDocs}>
                              <platform-icon name="book-open" size="14"></platform-icon>
                              ${this.i18n.t('code_editor.docs')}
                          </button>
                      `
                    : ''}
                <button type="button" class="editor-overflow-item" @click=${this._onOverflowCopy}>
                    <platform-icon name="copy" size="14"></platform-icon>
                    ${this.i18n.t('code_modal.copy_title')}
                </button>
                <button
                    type="button"
                    class="editor-overflow-item"
                    @click=${this._onOverflowFullscreen}
                    title="${this._fullscreen
                        ? this.i18n.t('code_editor.fullscreen_min')
                        : this.i18n.t('code_editor.fullscreen_max')}"
                >
                    <platform-icon name="${this._fullscreen ? 'minimize' : 'maximize'}" size="14"></platform-icon>
                    ${this._fullscreen
                        ? this.i18n.t('code_editor.fullscreen_min')
                        : this.i18n.t('code_editor.fullscreen_max')}
                </button>
            </div>
        `;
    }

    _renderTemplatesDropdown() {
        if (!this._templatesOpen) return '';
        
        const grouped = {};
        for (const t of this._templates) {
            if (!grouped[t.category]) {
                grouped[t.category] = [];
            }
            grouped[t.category].push(t);
        }
        
        return html`
            <div class="templates-dropdown">
                ${Object.entries(grouped).map(([category, templates]) => html`
                    <div class="templates-category">${category}</div>
                    ${templates.map(t => html`
                        <div class="template-item" @click=${() => this._selectTemplate(t)}>
                            <span class="template-name">${t.name}</span>
                            <span class="template-desc">${t.description}</span>
                        </div>
                    `)}
                `)}
                ${this._templates.length === 0 ? html`
                    <div class="template-item">
                        <span class="template-desc">${this.i18n.t('code_editor.no_templates')}</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    render() {
        const style = `--editor-min-height: ${this.minHeight}px`;
        const pane = this._effectiveSchemaPane();
        const showCodeBody = !this.codeSchemaMode || pane === 'code';
        const showSchemaBody = this.codeSchemaMode && pane === 'schema';

        return html`
            <div class="editor-wrapper">
                ${this.showHeader ? html`
                    <div class="editor-header">
                        <div class="editor-header-start">
                            ${this.codeSchemaMode
                                ? html`
                                      <div class="code-schema-pane-toggle" role="tablist">
                                          <button
                                              type="button"
                                              class="editor-btn ${pane === 'code' ? 'active' : ''}"
                                              @click=${() => this._emitCodeSchemaPane('code')}
                                          >
                                              <platform-icon name="code" size="14"></platform-icon>
                                              ${this.i18n.t('code_node_editor.pane_code')}
                                          </button>
                                          <button
                                              type="button"
                                              class="editor-btn ${pane === 'schema' ? 'active' : ''}"
                                              @click=${() => this._emitCodeSchemaPane('schema')}
                                          >
                                              <platform-icon name="schema" size="14"></platform-icon>
                                              ${this.i18n.t('code_node_editor.pane_schema')}
                                          </button>
                                      </div>
                                  `
                                : html`
                                      <span class="editor-title">${this.i18n.t('code_editor.title_code')}</span>
                                  `}
                        </div>
                        <div class="editor-actions">
                            ${showCodeBody ? this._renderEditorActionsForCodePane() : ''}
                            ${showSchemaBody
                                ? html`<slot name="schema-header-actions"></slot>`
                                : ''}
                        </div>
                    </div>
                ` : ''}
                
                <div
                    id="codemirror-container"
                    style=${showCodeBody ? style : `${style};display:none`}
                ></div>
                ${this.codeSchemaMode
                    ? html`
                          <div
                              class="schema-body-slot-wrap"
                              style=${showSchemaBody ? style : `${style};display:none`}
                          >
                              <slot name="schema-body"></slot>
                          </div>
                      `
                    : ''}
                
                ${this.validationStatus ? html`
                    <div class="validation-status visible ${this.validationStatus}">
                        ${this.validationMessage}
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('code-editor', CodeEditor);

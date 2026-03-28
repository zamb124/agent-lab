/**
 * JsonFieldEditor - JSON редактор с CodeMirror и валидацией
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { nextModalLayerZIndex } from '@platform/lib/utils/modal-z-stack.js';

export class JsonFieldEditor extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }

            :host([bounded]:not(.fullscreen)) {
                flex: 0 1 auto;
                align-self: stretch;
                width: 100%;
                max-width: 100%;
                min-height: 0;
            }

            :host([bounded]:not(.fullscreen)) .editor-shell {
                max-height: min(42vh, 380px);
                min-height: 0;
                overflow: hidden;
            }

            :host([bounded]:not(.fullscreen)) .editor-container {
                flex: 1 1 0%;
                min-height: 0;
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }

            :host([bounded]:not(.fullscreen)) #codemirror-container {
                flex: 1 1 0%;
                min-height: 0 !important;
                overflow: hidden;
                position: relative;
            }

            :host([bounded]:not(.fullscreen)) #codemirror-container .cm-editor {
                height: 100% !important;
                min-height: 0 !important;
                max-height: 100%;
                overflow: hidden !important;
                display: flex !important;
                flex-direction: column !important;
            }

            :host([bounded]:not(.fullscreen)) #codemirror-container .cm-scroller {
                flex: 1 1 0% !important;
                min-height: 0 !important;
                overflow: auto !important;
            }

            .editor-shell {
                position: relative;
                display: flex;
                flex-direction: column;
                gap: 0;
            }

            .editor-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-medium);
                border: 1px solid var(--border-subtle);
                border-bottom: none;
                border-radius: var(--radius-md) var(--radius-md) 0 0;
            }

            .editor-header-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                min-height: 1em;
            }

            .editor-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
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

            .json-fs-fab {
                position: absolute;
                top: var(--space-2);
                right: var(--space-2);
                z-index: 3;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                padding: 0;
                color: var(--text-secondary);
                background: var(--glass-solid-strong);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
                transition: all var(--duration-fast) var(--easing-default);
            }

            .json-fs-fab:hover {
                color: var(--accent);
                border-color: var(--accent);
            }

            .editor-header[hidden] {
                display: none !important;
            }

            .json-fs-fab[hidden] {
                display: none !important;
            }

            .editor-container {
                position: relative;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }

            .editor-shell:has(.editor-header:not([hidden])) .editor-container {
                border-top-left-radius: 0;
                border-top-right-radius: 0;
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

            :host(.fullscreen) .editor-shell {
                flex: 1 1 0%;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }

            :host(.fullscreen) .editor-container {
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

            :host(.fullscreen) .editor-container .error-message,
            :host(.fullscreen) .editor-container .hint {
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
        `
    ];

    static properties = {
        value: { type: String },
        placeholder: { type: String },
        minHeight: { type: Number, attribute: 'min-height' },
        readonly: { type: Boolean },
        hint: { type: String },
        showToolbar: { type: Boolean, attribute: 'show-toolbar' },
        toolbarTitle: { type: String, attribute: 'toolbar-title' },
        bounded: { type: Boolean, reflect: true },
        _fullscreen: { type: Boolean, state: true },
    };

    constructor() {
        super();
        this.value = '';
        this.placeholder = '{}';
        this.minHeight = 100;
        this.readonly = false;
        this.hint = '';
        this.showToolbar = false;
        this.toolbarTitle = '';
        this.bounded = false;
        this._error = '';
        this._cmReady = false;
        this._editorView = null;
        this._cmModules = null;
        this._readonlyCompartment = null;
        this._fullscreen = false;
        /** @type {ParentNode | null} */
        this._fsPortalParent = null;
        /** @type {ChildNode | null} */
        this._fsPortalNext = null;
        /** @type {HTMLElement[]} */
        this._editorFullscreenHosts = [];
        /** @type {HTMLElement | null} */
        this._fullscreenEmbedRoot = null;
        this._fsPortalReparent = false;
        this._boundKeydown = (e) => {
            if (e.key === 'Escape' && this._fullscreen) {
                this._toggleFullscreen();
            }
        };
    }

    async firstUpdated() {
        document.addEventListener('keydown', this._boundKeydown);
        await this._initCodeMirror();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._fsPortalReparent) {
            return;
        }
        document.removeEventListener('keydown', this._boundKeydown);
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
            this._editorView.destroy();
            this._editorView = null;
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
                    '&': { backgroundColor: '#fafafa', color: '#383a42' },
                    '.cm-content': { caretColor: '#526fff' },
                    '.cm-gutters': {
                        backgroundColor: '#f0f0f0',
                        color: '#9d9d9f',
                        borderRight: '1px solid #e5e5e5',
                    },
                }, { dark: false }),
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
            }),
        ];

        const initialValue = this.value || '';

        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: initialValue,
                extensions,
            }),
            parent: container,
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
                changes: { from: 0, to: this._editorView.state.doc.length, insert: this.value },
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
                    this._cmModules.EditorState.readOnly.of(readonly),
                ),
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

    _notifyCopied() {
        this.success('Скопировано');
    }

    async _copyValue() {
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
            this.error('Не удалось скопировать');
        }
    }

    updated(changedProperties) {
        if (changedProperties.has('value') && this._editorView) {
            const currentValue = this._editorView.state.doc.toString();
            if (this.value !== currentValue) {
                this._editorView.dispatch({
                    changes: { from: 0, to: currentValue.length, insert: this.value || '' },
                });
            }
        }

        if (changedProperties.has('readonly') && this._editorView && this._readonlyCompartment && this._cmModules) {
            this._editorView.dispatch({
                effects: this._readonlyCompartment.reconfigure(
                    this._cmModules.EditorState.readOnly.of(this.readonly),
                ),
            });
        }
    }

    _renderHeaderActions() {
        return html`
            <div class="editor-actions">
                <button
                    type="button"
                    class="editor-btn"
                    @click=${this._copyValue}
                    title="Копировать"
                >
                    <platform-icon name="copy" size="12"></platform-icon>
                </button>
                <button
                    type="button"
                    class="editor-btn ${this._fullscreen ? 'active' : ''}"
                    @click=${this._toggleFullscreen}
                    title="${this._fullscreen ? 'Выйти из полноэкранного режима (Esc)' : 'На весь экран'}"
                >
                    <platform-icon
                        name="${this._fullscreen ? 'minimize' : 'maximize'}"
                        size="12"
                    ></platform-icon>
                </button>
            </div>
        `;
    }

    render() {
        const style = this.minHeight ? `--editor-min-height: ${this.minHeight}px` : '';
        const showHeaderRow = this.showToolbar || this._fullscreen;
        const showFab = !showHeaderRow;

        return html`
            <div class="editor-shell">
                <div class="editor-header" ?hidden=${!showHeaderRow}>
                    <span class="editor-header-title">${this.toolbarTitle}</span>
                    ${this._renderHeaderActions()}
                </div>
                <div class="editor-container ${this._error ? 'invalid' : ''}">
                    <button
                        type="button"
                        class="json-fs-fab"
                        title="На весь экран"
                        ?hidden=${!showFab}
                        @click=${this._toggleFullscreen}
                    >
                        <platform-icon name="maximize" size="14"></platform-icon>
                    </button>
                    <div id="codemirror-container" style=${style}></div>
                    ${this._error ? html`<div class="error-message">${this._error}</div>` : ''}
                    ${this.hint && !this._error ? html`<div class="hint">${this.hint}</div>` : ''}
                </div>
            </div>
        `;
    }
}

customElements.define('json-field-editor', JsonFieldEditor);

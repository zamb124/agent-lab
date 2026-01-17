/**
 * CodeEditor - универсальный редактор кода с CodeMirror 6
 * Поддержка Python/JavaScript, документация, шаблоны
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const DEFAULT_PYTHON = `def execute(args, state):
    """
    Обработка state.
    
    Args:
        args: Аргументы вызова
        state: Текущее состояние
    
    Returns:
        Результат выполнения
    """
    return {"result": "ok"}
`;

const DEFAULT_JAVASCRIPT = `async function execute(args, state) {
    /**
     * Обработка state.
     * 
     * @param {Object} args - Аргументы вызова
     * @param {Object} state - Текущее состояние
     * @returns {Object} Результат выполнения
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
            }
            
            .editor-title {
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
            }
            
            .editor-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
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
            
            /* Fullscreen mode */
            :host(.fullscreen) {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                z-index: 9999;
                background: var(--bg-base);
                padding: var(--space-4);
            }
            
            :host(.fullscreen) .editor-wrapper {
                height: 100%;
                display: flex;
                flex-direction: column;
            }
            
            :host(.fullscreen) #codemirror-container {
                flex: 1;
                min-height: unset !important;
            }
            
            :host(.fullscreen) #codemirror-container .cm-editor {
                height: 100%;
                min-height: unset !important;
            }
            
            :host(.fullscreen) #codemirror-container .cm-scroller {
                min-height: unset !important;
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
        validationStatus: { type: String },
        validationMessage: { type: String },
        _templatesOpen: { type: Boolean, state: true },
        _templates: { type: Array, state: true },
        _fullscreen: { type: Boolean, state: true },
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
        this.validationStatus = '';
        this.validationMessage = '';
        this._templatesOpen = false;
        this._templates = [];
        this._fullscreen = false;
        this._cmReady = false;
        this._editorView = null;
        this._cmModules = null;
        this._readonlyCompartment = null;
        this._languageCompartment = null;
        this._completionData = null;
    }

    get _defaultCode() {
        return this.language === 'javascript' ? DEFAULT_JAVASCRIPT : DEFAULT_PYTHON;
    }

    async firstUpdated() {
        await this._initCodeMirror();
        document.addEventListener('click', this._handleClickOutside.bind(this));
        document.addEventListener('keydown', this._handleKeydown.bind(this));
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._handleClickOutside.bind(this));
        document.removeEventListener('keydown', this._handleKeydown.bind(this));
        if (this._fullscreen) {
            document.body.style.overflow = '';
        }
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
    }

    _handleKeydown(e) {
        if (e.key === 'Escape' && this._fullscreen) {
            this._toggleFullscreen();
        }
    }

    _handleClickOutside(e) {
        if (this._templatesOpen && !e.composedPath().includes(this)) {
            this._templatesOpen = false;
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
        this.emit('template-selected', { template });
    }

    _openDocs() {
        this.emit('open-docs', { 
            language: this.language, 
            nodeType: this.nodeType,
            perspective: 'editor'
        });
    }

    async _copyCode() {
        const text = this.getValue();
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                // Fallback для HTTP
                const textarea = document.createElement('textarea');
                textarea.value = text;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
            }
            this.success('Код скопирован');
        } catch (e) {
            console.warn('Copy failed:', e);
            this.error('Не удалось скопировать');
        }
    }

    _toggleFullscreen() {
        this._fullscreen = !this._fullscreen;
        if (this._fullscreen) {
            this.classList.add('fullscreen');
            document.body.style.overflow = 'hidden';
        } else {
            this.classList.remove('fullscreen');
            document.body.style.overflow = '';
        }
    }

    showValidation(status, message) {
        this.validationStatus = status;
        this.validationMessage = message;
    }

    hideValidation() {
        this.validationStatus = '';
        this.validationMessage = '';
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
                        <span class="template-desc">Нет шаблонов</span>
                    </div>
                ` : ''}
            </div>
        `;
    }

    render() {
        const style = `--editor-min-height: ${this.minHeight}px`;
        
        return html`
            <div class="editor-wrapper">
                ${this.showHeader ? html`
                    <div class="editor-header">
                        <span class="editor-title">Код</span>
                        <div class="editor-actions">
                            ${this.showLanguageSwitch ? html`
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
                            ` : ''}
                            
                            ${this.showTemplates ? html`
                                <div class="templates-container">
                                    <button 
                                        class="editor-btn ${this._templatesOpen ? 'active' : ''}"
                                        @click=${this._toggleTemplates}
                                    >
                                        <platform-icon name="file" size="12"></platform-icon>
                                        Шаблоны
                                    </button>
                                    ${this._renderTemplatesDropdown()}
                                </div>
                            ` : ''}
                            
                            ${this.showDocs ? html`
                                <button class="editor-btn" @click=${this._openDocs}>
                                    <platform-icon name="book-open" size="12"></platform-icon>
                                    Docs
                                </button>
                            ` : ''}
                            
                            <button class="editor-btn" @click=${this._copyCode}>
                                <platform-icon name="copy" size="12"></platform-icon>
                            </button>
                            
                            <button class="editor-btn" @click=${this._toggleFullscreen} title="${this._fullscreen ? 'Свернуть' : 'На весь экран'}">
                                <platform-icon name="${this._fullscreen ? 'minimize' : 'maximize'}" size="12"></platform-icon>
                            </button>
                        </div>
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

customElements.define('code-editor', CodeEditor);

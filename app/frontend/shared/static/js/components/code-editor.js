/**
 * Универсальный CodeEditor компонент на базе Ace Editor
 * Используется в Builder, админке тулов, везде где нужен Python редактор
 */

class CodeEditor {
    constructor(options = {}) {
        this.container = typeof options.container === 'string' 
            ? document.querySelector(options.container)
            : options.container;
        
        if (!this.container) {
            throw new Error('Container для CodeEditor не найден');
        }
        
        const currentTheme = this.detectSystemTheme();
        const aceTheme = currentTheme === 'dark' ? 'monokai' : 'github';
        
        this.options = {
            mode: options.mode || 'python',
            theme: options.theme || aceTheme,
            value: options.value || '',
            readOnly: options.readOnly || false,
            flowId: options.flowId || null,
            placeholder: options.placeholder || 'Введите код...',
            height: options.height || '400px',
            minHeight: options.minHeight || '200px',
            maxHeight: options.maxHeight || '800px',
            showLineNumbers: options.showLineNumbers !== false,
            showGutter: options.showGutter !== false,
            highlightActiveLine: options.highlightActiveLine !== false,
            autocompletion: options.autocompletion !== false,
            ...options
        };
        
        this.onChange = options.onChange || null;
        this.onSave = options.onSave || null;
        
        this.editor = null;
        this.storeVars = {};
        this.flowVars = {};
        this.availableLibs = {};
        this.currentSystemTheme = currentTheme;
        
        this.init();
    }
    
    detectSystemTheme() {
        const builderContainer = document.querySelector('.builder-container');
        if (builderContainer) {
            return 'dark';
        }
        
        const htmlTheme = document.documentElement.getAttribute('data-theme');
        if (htmlTheme) {
            return htmlTheme;
        }
        
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return 'dark';
        }
        
        return 'dark';
    }
    
    init() {
        this.createEditorWrapper();
        this.createEditor();
        this.setupEventListeners();
        this.watchThemeChanges();
        
        if (this.options.flowId) {
            this.loadFlowContext(this.options.flowId);
        }
    }
    
    watchThemeChanges() {
        const builderContainer = document.querySelector('.builder-container');
        if (builderContainer) {
            return;
        }
        
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === 'data-theme') {
                    const newTheme = this.detectSystemTheme();
                    if (newTheme !== this.currentSystemTheme) {
                        this.currentSystemTheme = newTheme;
                        this.updateEditorTheme(newTheme);
                    }
                }
            });
        });
        
        observer.observe(document.documentElement, {
            attributes: true,
            attributeFilter: ['data-theme']
        });
        
        this.themeObserver = observer;
    }
    
    updateEditorTheme(theme) {
        if (!this.editor) return;
        
        const aceTheme = theme === 'dark' ? 'monokai' : 'github';
        this.editor.setTheme(`ace/theme/${aceTheme}`);
        
        this.container.setAttribute('data-theme', theme);
        
        console.log(`🎨 CodeEditor тема обновлена: ${aceTheme}`);
    }
    
    createEditorWrapper() {
        this.container.innerHTML = '';
        this.container.classList.add('code-editor-wrapper');
        this.container.setAttribute('data-theme', this.currentSystemTheme);
        
        this.toolbar = document.createElement('div');
        this.toolbar.className = 'code-editor-toolbar';
        this.toolbar.innerHTML = `
            <div class="toolbar-left">
                <span class="toolbar-label">
                    <i class="bi bi-code-square"></i>
                    Python Editor
                </span>
            </div>
            <div class="toolbar-right">
                <button class="toolbar-btn" id="formatCodeBtn-${this.getUniqueId()}" title="Форматировать код (Ctrl+Shift+F)">
                    <i class="bi bi-brush"></i>
                </button>
                <button class="toolbar-btn" id="validateCodeBtn-${this.getUniqueId()}" title="Проверить синтаксис">
                    <i class="bi bi-check-circle"></i>
                </button>
                <button class="toolbar-btn" id="showStoreVarsBtn-${this.getUniqueId()}" title="Доступные переменные store">
                    <i class="bi bi-database"></i>
                </button>
                <button class="toolbar-btn" id="fullscreenBtn-${this.getUniqueId()}" title="Полноэкранный режим (F11)">
                    <i class="bi bi-arrows-fullscreen"></i>
                </button>
            </div>
        `;
        
        this.editorContainer = document.createElement('div');
        this.editorContainer.className = 'code-editor-container';
        this.editorContainer.style.height = this.options.height;
        this.editorContainer.style.minHeight = this.options.minHeight;
        this.editorContainer.style.maxHeight = this.options.maxHeight;
        
        this.statusBar = document.createElement('div');
        this.statusBar.className = 'code-editor-status';
        this.statusBar.innerHTML = `
            <span class="status-item" id="lineColStatus-${this.getUniqueId()}">Строка 1, Столбец 1</span>
            <span class="status-item" id="langStatus-${this.getUniqueId()}">Python</span>
            <span class="status-item" id="validationStatus-${this.getUniqueId()}"></span>
        `;
        
        this.container.appendChild(this.toolbar);
        this.container.appendChild(this.editorContainer);
        this.container.appendChild(this.statusBar);
        
        this.uniqueId = this.getUniqueId();
    }
    
    getUniqueId() {
        if (!this._uniqueId) {
            this._uniqueId = Math.random().toString(36).substr(2, 9);
        }
        return this._uniqueId;
    }
    
    createEditor() {
        if (typeof ace === 'undefined') {
            console.error('Ace Editor не загружен!');
            this.editorContainer.innerHTML = '<div class="code-editor-loading"><i class="bi bi-exclamation-triangle"></i> Редактор не загружен</div>';
            return;
        }
        
        this.editor = ace.edit(this.editorContainer);
        
        this.editor.setTheme(`ace/theme/${this.options.theme}`);
        this.editor.session.setMode(`ace/mode/${this.options.mode}`);
        this.editor.setValue(this.options.value, -1);
        
        this.editor.setOptions({
            enableBasicAutocompletion: this.options.autocompletion,
            enableLiveAutocompletion: this.options.autocompletion,
            enableSnippets: true,
            fontSize: 14,
            showPrintMargin: false,
            showLineNumbers: this.options.showLineNumbers,
            showGutter: this.options.showGutter,
            highlightActiveLine: this.options.highlightActiveLine,
            tabSize: 4,
            useSoftTabs: true,
            wrap: true,
            readOnly: this.options.readOnly
        });
        
        if (this.options.autocompletion) {
            this.setupAutocompletion();
        }
        
        this.editor.on('change', () => {
            if (this.onChange) {
                this.onChange(this.getValue());
            }
        });
        
        this.editor.selection.on('changeCursor', () => {
            this.updateCursorPosition();
        });
        
        this.editor.commands.addCommand({
            name: 'save',
            bindKey: {win: 'Ctrl-S', mac: 'Command-S'},
            exec: () => {
                if (this.onSave) {
                    this.onSave(this.getValue());
                }
            }
        });
        
        this.updateCursorPosition();
    }
    
    setupAutocompletion() {
        const platformCompleter = {
            getCompletions: (editor, session, pos, prefix, callback) => {
                const completions = this.getCompletions();
                callback(null, completions);
            }
        };
        
        if (this.editor.completers) {
            this.editor.completers.push(platformCompleter);
        }
    }
    
    getCompletions() {
        const completions = [];
        
        const standardLibs = [
            { caption: 'httpx', value: 'httpx', meta: 'library', docHTML: 'Асинхронный HTTP клиент' },
            { caption: 'asyncio', value: 'asyncio', meta: 'library', docHTML: 'Асинхронное программирование' },
            { caption: 'typing', value: 'typing', meta: 'library', docHTML: 'Типизация Python' },
            { caption: 'json', value: 'json', meta: 'library', docHTML: 'Работа с JSON' },
            { caption: 'datetime', value: 'datetime', meta: 'library', docHTML: 'Работа с датами' },
            { caption: 're', value: 're', meta: 'library', docHTML: 'Регулярные выражения' },
            { caption: 'uuid', value: 'uuid', meta: 'library', docHTML: 'Генерация UUID' },
            { caption: 'pathlib', value: 'pathlib', meta: 'library', docHTML: 'Работа с путями' }
        ];
        
        const platformImports = [
            { caption: '@tool', value: 'from app.core.tool_decorator import tool\n\n@tool', meta: 'snippet', docHTML: 'Декоратор для создания тула' },
            { caption: 'get_context', value: 'get_context()', meta: 'function', docHTML: 'Получить текущий контекст' },
            { caption: 'get_state', value: 'get_state()', meta: 'function', docHTML: 'Получить state агента' },
            { caption: 'send_progress', value: 'send_progress()', meta: 'function', docHTML: 'Отправить прогресс' },
            { caption: 'GraphInterrupt', value: 'GraphInterrupt', meta: 'class', docHTML: 'Запрос данных у пользователя' }
        ];
        
        completions.push(...standardLibs, ...platformImports);
        
        Object.keys(this.storeVars).forEach(key => {
            completions.push({
                caption: `store.${key}`,
                value: `state["store"]["${key}"]`,
                meta: 'store',
                docHTML: `Store переменная: ${this.storeVars[key]}`
            });
        });
        
        Object.keys(this.flowVars).forEach(key => {
            completions.push({
                caption: `flow.${key}`,
                value: `{${key}}`,
                meta: 'flow',
                docHTML: `Flow переменная: ${this.flowVars[key]}`
            });
        });
        
        return completions;
    }
    
    setupEventListeners() {
        const formatBtn = this.toolbar.querySelector(`#formatCodeBtn-${this.uniqueId}`);
        if (formatBtn) {
            formatBtn.addEventListener('click', () => this.formatCode());
        }
        
        const validateBtn = this.toolbar.querySelector(`#validateCodeBtn-${this.uniqueId}`);
        if (validateBtn) {
            validateBtn.addEventListener('click', () => this.validateCode());
        }
        
        const storeVarsBtn = this.toolbar.querySelector(`#showStoreVarsBtn-${this.uniqueId}`);
        if (storeVarsBtn) {
            storeVarsBtn.addEventListener('click', () => this.showStoreVariables());
        }
        
        const fullscreenBtn = this.toolbar.querySelector(`#fullscreenBtn-${this.uniqueId}`);
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
        }
    }
    
    async loadFlowContext(flowId) {
        try {
            const response = await fetch(`/frontend/api/flows/${flowId}/variables`);
            if (!response.ok) {
                console.warn('Не удалось загрузить контекст flow');
                return;
            }
            
            const data = await response.json();
            this.storeVars = data.store || {};
            this.flowVars = data.variables || {};
            this.availableLibs = data.available_tools || [];
            
            console.log('✅ Контекст flow загружен:', {
                storeVars: Object.keys(this.storeVars).length,
                flowVars: Object.keys(this.flowVars).length
            });
        } catch (error) {
            console.error('Ошибка загрузки контекста flow:', error);
        }
    }
    
    async validateCode() {
        const code = this.getValue();
        const statusEl = this.statusBar.querySelector(`#validationStatus-${this.uniqueId}`);
        
        if (!code.trim()) {
            this.setStatus('Код пуст', 'warning');
            return;
        }
        
        statusEl.innerHTML = '<i class="bi bi-hourglass-split"></i> Проверка...';
        statusEl.className = 'status-item status-validating';
        
        try {
            const response = await fetch('/frontend/api/code/validate-python', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ code })
            });
            
            const result = await response.json();
            
            if (result.valid) {
                this.setStatus('✓ Код валиден', 'success');
            } else {
                const errorMsg = result.errors[0]?.message || 'Ошибка синтаксиса';
                this.setStatus(`✗ ${errorMsg}`, 'error');
            }
        } catch (error) {
            this.setStatus('Ошибка проверки', 'error');
            console.error('Ошибка валидации:', error);
        }
    }
    
    formatCode() {
        console.log('🎨 Форматирование кода...');
        this.setStatus('Форматирование в разработке', 'info');
    }
    
    showStoreVariables() {
        const hasVars = Object.keys(this.storeVars).length > 0 || Object.keys(this.flowVars).length > 0;
        
        if (!hasVars) {
            if (window.showNotification) {
                window.showNotification('Нет доступных переменных', 'info');
            }
            return;
        }
        
        let content = '<div class="store-vars-popup">';
        
        if (Object.keys(this.storeVars).length > 0) {
            content += '<h4>📦 Store переменные:</h4><ul>';
            for (const [key, value] of Object.entries(this.storeVars)) {
                content += `<li><code>state["store"]["${key}"]</code> = ${JSON.stringify(value)}</li>`;
            }
            content += '</ul>';
        }
        
        if (Object.keys(this.flowVars).length > 0) {
            content += '<h4>🔧 Flow переменные:</h4><ul>';
            for (const [key, value] of Object.entries(this.flowVars)) {
                content += `<li><code>{${key}}</code> = ${JSON.stringify(value)}</li>`;
            }
            content += '</ul>';
        }
        
        content += '</div>';
        
        if (window.showNotification) {
            window.showNotification(content, 'info', 10000);
        }
    }
    
    toggleFullscreen() {
        this.container.classList.toggle('code-editor-fullscreen');
        const icon = this.toolbar.querySelector(`#fullscreenBtn-${this.uniqueId} i`);
        if (this.container.classList.contains('code-editor-fullscreen')) {
            icon.className = 'bi bi-fullscreen-exit';
        } else {
            icon.className = 'bi bi-arrows-fullscreen';
        }
    }
    
    updateCursorPosition() {
        if (!this.editor) return;
        
        const pos = this.editor.getCursorPosition();
        const lineNum = pos.row + 1;
        const col = pos.column + 1;
        
        const statusEl = this.statusBar.querySelector(`#lineColStatus-${this.uniqueId}`);
        if (statusEl) {
            statusEl.textContent = `Строка ${lineNum}, Столбец ${col}`;
        }
    }
    
    setStatus(message, type = 'info') {
        const statusEl = this.statusBar.querySelector(`#validationStatus-${this.uniqueId}`);
        if (!statusEl) return;
        
        const icons = {
            success: 'bi-check-circle-fill',
            error: 'bi-x-circle-fill',
            warning: 'bi-exclamation-triangle-fill',
            info: 'bi-info-circle-fill'
        };
        
        statusEl.innerHTML = `<i class="bi ${icons[type] || icons.info}"></i> ${message}`;
        statusEl.className = `status-item status-${type}`;
        
        setTimeout(() => {
            statusEl.innerHTML = '';
            statusEl.className = 'status-item';
        }, 5000);
    }
    
    getValue() {
        return this.editor ? this.editor.getValue() : '';
    }
    
    setValue(code) {
        if (this.editor) {
            this.editor.setValue(code, -1);
        }
    }
    
    focus() {
        if (this.editor) {
            this.editor.focus();
        }
    }
    
    destroy() {
        if (this.themeObserver) {
            this.themeObserver.disconnect();
        }
        if (this.editor) {
            this.editor.destroy();
        }
        this.container.innerHTML = '';
    }
}

window.CodeEditor = CodeEditor;

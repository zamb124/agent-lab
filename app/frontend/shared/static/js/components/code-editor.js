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
        this.libraryDocumentation = null;
        this.currentSystemTheme = currentTheme;
        
        this.init();
    }
    
    detectSystemTheme() {
        const htmlTheme = document.documentElement.getAttribute('data-theme');
        if (htmlTheme) {
            console.log('🎨 Тема из data-theme:', htmlTheme);
            return htmlTheme;
        }
        
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            console.log('🎨 Тема из system preference: dark');
            return 'dark';
        }
        
        console.log('🎨 Тема по умолчанию: light');
        return 'light';
    }
    
    init() {
        console.log('🔧 CodeEditor.init(), flowId:', this.options.flowId);
        this.createEditorWrapper();
        this.createEditor();
        this.setupEventListeners();
        this.watchThemeChanges();
        
        if (this.options.flowId) {
            console.log('📡 Загружаем контекст flow:', this.options.flowId);
            this.loadFlowContext(this.options.flowId);
        } else {
            console.warn('⚠️ flowId не передан, контекст не загружается');
        }
    }
    
    watchThemeChanges() {
        const observer = new MutationObserver((mutations) => {
            mutations.forEach((mutation) => {
                if (mutation.attributeName === 'data-theme') {
                    const newTheme = this.detectSystemTheme();
                    if (newTheme !== this.currentSystemTheme) {
                        console.log(`🎨 Тема изменилась: ${this.currentSystemTheme} → ${newTheme}`);
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
        this.uniqueId = Math.random().toString(36).substr(2, 9);
        
        console.log('🔧 createEditorWrapper, uniqueId:', this.uniqueId);
        
        this.container.innerHTML = '';
        this.container.classList.add('code-editor-wrapper');
        this.container.setAttribute('data-theme', this.currentSystemTheme);
        
        this.toolbar = document.createElement('div');
        this.toolbar.className = 'code-editor-toolbar';
        this.toolbar.innerHTML = `
            <div class="toolbar-left">
                <span class="toolbar-label">
                    <i class="ti ti-code-square"></i>
                    Python Editor
                </span>
            </div>
            <div class="toolbar-right">
                <button class="toolbar-btn" id="formatCodeBtn-${this.uniqueId}" title="Форматировать код (Ctrl+Shift+F)">
                    <i class="ti ti-brush"></i>
                </button>
                <button class="toolbar-btn" id="validateCodeBtn-${this.uniqueId}" title="Проверить синтаксис">
                    <i class="ti ti-check"></i>
                </button>
                <button class="toolbar-btn" id="showStoreVarsBtn-${this.uniqueId}" title="Доступные переменные store">
                    <i class="ti ti-database"></i>
                </button>
                <button class="toolbar-btn" id="infoBtn-${this.uniqueId}" title="Документация по API">
                    <i class="ti ti-info-circle"></i>
                </button>
                <button class="toolbar-btn" id="fullscreenBtn-${this.uniqueId}" title="Полноэкранный режим (F11)">
                    <i class="ti ti-maximize"></i>
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
            <span class="status-item" id="lineColStatus-${this.uniqueId}">Строка 1, Столбец 1</span>
            <span class="status-item" id="langStatus-${this.uniqueId}">Python</span>
            <span class="status-item" id="validationStatus-${this.uniqueId}"></span>
        `;
        
        this.container.appendChild(this.toolbar);
        this.container.appendChild(this.editorContainer);
        this.container.appendChild(this.statusBar);
    }
    
    createEditor() {
        if (typeof ace === 'undefined') {
            console.error('Ace Editor не загружен!');
            this.editorContainer.innerHTML = '<div class="code-editor-loading"><i class="ti ti-exclamation-triangle"></i> Редактор не загружен</div>';
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

        // Загружаем документацию по библиотекам
        this.loadLibraryDocumentation();
    }
    
    getCompletions() {
        const completions = [];

        // Добавляем доступные библиотеки из документации
        if (this.libraryDocumentation) {
            this.libraryDocumentation.forEach(lib => {
                // Основной элемент
                completions.push({
                    caption: lib.name,
                    value: lib.name,
                    meta: lib.type,
                    docHTML: lib.description || `${lib.type} ${lib.name}`
                });

                // Добавляем методы/подэлементы
                if (lib.methods) {
                    lib.methods.forEach(method => {
                        completions.push({
                            caption: `${lib.name}.${method.name}`,
                            value: `${lib.name}.${method.name}`,
                            meta: method.type,
                            docHTML: method.description || `${method.type} ${method.name}`
                        });
                    });
                }
            });
        }

        // Store переменные
        Object.keys(this.storeVars).forEach(key => {
            completions.push({
                caption: `store.${key}`,
                value: `state["store"]["${key}"]`,
                meta: 'store',
                docHTML: `Store переменная: ${this.storeVars[key]}`
            });
        });

        // Flow переменные
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
        console.log('🔧 setupEventListeners, uniqueId:', this.uniqueId);
        
        const formatBtn = this.toolbar.querySelector(`#formatCodeBtn-${this.uniqueId}`);
        console.log('   formatBtn:', !!formatBtn);
        if (formatBtn) {
            formatBtn.addEventListener('click', () => this.formatCode());
        }
        
        const validateBtn = this.toolbar.querySelector(`#validateCodeBtn-${this.uniqueId}`);
        console.log('   validateBtn:', !!validateBtn);
        if (validateBtn) {
            validateBtn.addEventListener('click', () => this.validateCode());
        }
        
        const storeVarsBtn = this.toolbar.querySelector(`#showStoreVarsBtn-${this.uniqueId}`);
        console.log('   storeVarsBtn:', !!storeVarsBtn);
        if (storeVarsBtn) {
            storeVarsBtn.addEventListener('click', () => {
                console.log('🗄️ Кнопка Store Variables нажата!');
                this.showStoreVariables();
            });
        } else {
            console.error('❌ Кнопка showStoreVarsBtn не найдена!');
        }

        const infoBtn = this.toolbar.querySelector(`#infoBtn-${this.uniqueId}`);
        console.log('   infoBtn:', !!infoBtn);
        if (infoBtn) {
            infoBtn.addEventListener('click', () => {
                console.log('📚 Кнопка Info нажата!');
                this.showApiDocumentation();
            });
        } else {
            console.error('❌ Кнопка infoBtn не найдена!');
        }

        const fullscreenBtn = this.toolbar.querySelector(`#fullscreenBtn-${this.uniqueId}`);
        console.log('   fullscreenBtn:', !!fullscreenBtn);
        if (fullscreenBtn) {
            fullscreenBtn.addEventListener('click', () => this.toggleFullscreen());
        }
    }
    
    async loadFlowContext(flowId) {
        console.log('📡 loadFlowContext вызван для flowId:', flowId);

        try {
            const url = `/frontend/api/flows/${flowId}/variables`;
            console.log('📡 Запрос к API:', url);

            const response = await fetch(url);
            console.log('📡 Ответ от API:', response.status, response.statusText);

            if (!response.ok) {
                console.warn('❌ Не удалось загрузить контекст flow, статус:', response.status);
                return;
            }

            const data = await response.json();
            console.log('📡 Данные от API:', data);

            this.storeVars = data.store || {};
            this.flowVars = data.variables || {};
            this.availableLibs = data.available_tools || [];

            console.log('✅ Контекст flow загружен:', {
                storeVars: Object.keys(this.storeVars).length,
                flowVars: Object.keys(this.flowVars).length,
                availableTools: this.availableLibs.length
            });
            console.log('   Store vars:', this.storeVars);
            console.log('   Flow vars:', this.flowVars);
        } catch (error) {
            console.error('❌ Ошибка загрузки контекста flow:', error);
        }
    }

    async loadLibraryDocumentation() {
        console.log('📚 Загружаем документацию по библиотекам...');

        try {
            const response = await fetch('/frontend/api/code/documentation');
            if (!response.ok) {
                console.warn('❌ Не удалось загрузить документацию:', response.status);
                return;
            }

            const data = await response.json();
            this.libraryDocumentation = data.libraries || [];

            console.log('✅ Документация загружена:', this.libraryDocumentation.length, 'элементов');
        } catch (error) {
            console.error('❌ Ошибка загрузки документации:', error);
            // Fallback - пустая документация
            this.libraryDocumentation = [];
        }
    }
    
    async validateCode() {
        const code = this.getValue();
        const statusEl = this.statusBar.querySelector(`#validationStatus-${this.uniqueId}`);
        
        if (!code.trim()) {
            this.setStatus('Код пуст', 'warning');
            return;
        }
        
        statusEl.innerHTML = '<i class="ti ti-hourglass-split"></i> Проверка...';
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
        console.log('🗄️ showStoreVariables вызван');
        console.log('   this.storeVars:', this.storeVars);
        console.log('   this.flowVars:', this.flowVars);
        console.log('   this.options.flowId:', this.options.flowId);
        
        const hasVars = Object.keys(this.storeVars).length > 0 || Object.keys(this.flowVars).length > 0;
        
        console.log('   hasVars:', hasVars);
        
        if (!hasVars) {
            this.showVariablesModal('Нет доступных переменных', `
                <p style="text-align: center; color: var(--code-editor-text-secondary); padding: 20px;">
                    ${this.options.flowId ? 'Переменные и store этого flow пусты.<br>Добавьте переменные в конфигурацию flow.' : 'Flow ID не передан в редактор.<br>Редактор должен быть открыт в контексте flow.'}
                </p>
            `);
            return;
        }
        
        let content = '';
        
        if (Object.keys(this.storeVars).length > 0) {
            content += '<div class="vars-section"><h4>📦 Store переменные</h4><div class="vars-list">';
            for (const [key, value] of Object.entries(this.storeVars)) {
                const valueStr = JSON.stringify(value, null, 2);
                const copyText = `state["store"]["${key}"]`;
                content += `
                    <div class="var-item">
                        <div class="var-key">state["store"]["${key}"]</div>
                        <div class="var-value">${this.escapeHtml(valueStr)}</div>
                        <button class="var-copy-btn" data-copy-text='${copyText}' title="Копировать">
                            <i class="ti ti-clipboard"></i>
                        </button>
                    </div>
                `;
            }
            content += '</div></div>';
        }
        
        if (Object.keys(this.flowVars).length > 0) {
            content += '<div class="vars-section"><h4>🔧 Flow переменные</h4><div class="vars-list">';
            for (const [key, value] of Object.entries(this.flowVars)) {
                const valueStr = JSON.stringify(value, null, 2);
                const copyText = `{${key}}`;
                content += `
                    <div class="var-item">
                        <div class="var-key">{${key}}</div>
                        <div class="var-value">${this.escapeHtml(valueStr)}</div>
                        <button class="var-copy-btn" data-copy-text='${copyText}' title="Копировать">
                            <i class="ti ti-clipboard"></i>
                        </button>
                    </div>
                `;
            }
            content += '</div></div>';
        }
        
        this.showVariablesModal('Доступные переменные', content);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    formatDocstring(text) {
        if (!text) return '';

        // Очищаем от лишних пробелов в начале и конце
        text = text.trim();

        // Заменяем \n на <br> для переносов строк
        text = text.replace(/\n/g, '<br>');

        // Обрабатываем многострочные докстринги с отступами
        text = text.replace(/<br>\s+/g, (match) => {
            const spaces = match.length - 4; // 4 символа <br>
            return '<br>' + '&nbsp;'.repeat(Math.max(0, spaces));
        });

        // Подсвечиваем Args: и Returns: секции
        text = text.replace(/(Args:|Returns:|Examples?:)/gi, '<strong>$1</strong>');

        return text;
    }

    showApiDocumentation() {
        console.log('📚 showApiDocumentation вызван');

        if (!this.libraryDocumentation || this.libraryDocumentation.length === 0) {
            this.showVariablesModal('Документация по API', `
                <p style="text-align: center; color: var(--code-editor-text-secondary); padding: 20px;">
                    Документация загружается...<br>
                    Если загрузка не удалась, попробуйте перезагрузить страницу.
                </p>
            `);
            return;
        }

        let content = '<div class="api-documentation">';

        // Группируем по типам
        const grouped = {
            function: [],
            module: [],
            class: [],
            variable: []
        };

        this.libraryDocumentation.forEach(lib => {
            if (grouped[lib.type]) {
                grouped[lib.type].push(lib);
            }
        });

        // Функции платформы
        if (grouped.function.length > 0) {
            content += '<div class="doc-section"><h4>🔧 Функции платформы</h4>';
            grouped.function.forEach(func => {
                content += `
                    <div class="api-item">
                        <div class="api-name">${func.name}</div>
                        <div class="api-signature">${func.signature || ''}</div>
                        <div class="api-description">${this.formatDocstring(func.description) || 'Нет описания'}</div>
                    </div>
                `;
            });
            content += '</div>';
        }

        // Модули
        if (grouped.module.length > 0) {
            content += '<div class="doc-section"><h4>📦 Модули</h4>';
            grouped.module.forEach(mod => {
                content += `
                    <div class="api-item">
                        <div class="api-name">${mod.name}</div>
                        <div class="api-description">${this.formatDocstring(mod.description) || 'Нет описания'}</div>
                    </div>
                `;

                if (mod.methods && mod.methods.length > 0) {
                    content += '<div class="api-methods">';
                    mod.methods.forEach(method => {
                        content += `
                            <div class="api-method">
                                <span class="method-name">${method.name}</span>
                                <span class="method-signature">${method.signature || ''}</span>
                                <div class="method-description">${this.formatDocstring(method.description) || ''}</div>
                            </div>
                        `;
                    });
                    content += '</div>';
                }
            });
            content += '</div>';
        }

        // Классы
        if (grouped.class.length > 0) {
            content += '<div class="doc-section"><h4>🏗️ Классы</h4>';
            grouped.class.forEach(cls => {
                content += `
                    <div class="api-item">
                        <div class="api-name">${cls.name}</div>
                        <div class="api-description">${this.formatDocstring(cls.description) || 'Нет описания'}</div>
                    </div>
                `;

                if (cls.methods && cls.methods.length > 0) {
                    content += '<div class="api-methods">';
                    cls.methods.forEach(method => {
                        content += `
                            <div class="api-method">
                                <span class="method-name">${method.name}</span>
                                <span class="method-signature">${method.signature || ''}</span>
                                <div class="method-description">${this.formatDocstring(method.description) || ''}</div>
                            </div>
                        `;
                    });
                    content += '</div>';
                }
            });
            content += '</div>';
        }

        // Переменные
        if (grouped.variable.length > 0) {
            content += '<div class="doc-section"><h4>📊 Переменные</h4>';
            grouped.variable.forEach(v => {
                content += `
                    <div class="api-item">
                        <div class="api-name">${v.name}</div>
                        <div class="api-description">${this.formatDocstring(v.description) || 'Нет описания'}</div>
                    </div>
                `;
            });
            content += '</div>';
        }

        content += '</div>';

        this.showVariablesModal('Документация по API', content);
    }

    showVariablesModal(title, content) {
        const existingModal = document.querySelector('.code-editor-variables-modal');
        if (existingModal) {
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.className = 'code-editor-variables-modal';
        modal.innerHTML = `
            <div class="variables-modal-overlay"></div>
            <div class="variables-modal-content">
                <div class="variables-modal-header">
                    <h3>${title}</h3>
                    <button class="variables-modal-close">
                        <i class="ti ti-x"></i>
                    </button>
                </div>
                <div class="variables-modal-body">
                    ${content}
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        setTimeout(() => modal.classList.add('show'), 10);

        const closeBtn = modal.querySelector('.variables-modal-close');
        const overlay = modal.querySelector('.variables-modal-overlay');

        const closeModal = () => {
            modal.classList.remove('show');
            setTimeout(() => modal.remove(), 300);
        };

        closeBtn.addEventListener('click', closeModal);
        overlay.addEventListener('click', closeModal);

        // Обработчики для кнопок копирования
        const copyBtns = modal.querySelectorAll('.var-copy-btn');
        copyBtns.forEach(btn => {
            btn.addEventListener('click', async () => {
                const textToCopy = btn.dataset.copyText;
                if (textToCopy) {
                    try {
                        await navigator.clipboard.writeText(textToCopy);
                        console.log('✅ Скопировано:', textToCopy);

                        // Визуальная обратная связь
                        const icon = btn.querySelector('i');
                        if (icon) {
                            icon.className = 'ti ti-check';
                            setTimeout(() => {
                                icon.className = 'ti ti-clipboard';
                            }, 1000);
                        }
                    } catch (error) {
                        console.error('❌ Ошибка копирования:', error);
                    }
                }
            });
        });

        document.addEventListener('keydown', function escHandler(e) {
            if (e.key === 'Escape') {
                closeModal();
                document.removeEventListener('keydown', escHandler);
            }
        });
    }
    
    toggleFullscreen() {
        const isFullscreen = this.container.classList.contains('code-editor-fullscreen');
        
        if (!isFullscreen) {
            // Входим в fullscreen
            this.originalParent = this.container.parentNode;
            this.originalNextSibling = this.container.nextSibling;
            
            // Перемещаем в body
            document.body.appendChild(this.container);
            this.container.classList.add('code-editor-fullscreen');
            
            const icon = this.toolbar.querySelector(`#fullscreenBtn-${this.uniqueId} i`);
            if (icon) icon.className = 'ti ti-minimize';
            
            // Блокируем скролл body
            document.body.style.overflow = 'hidden';
            
            console.log('✅ Fullscreen режим включен');
        } else {
            // Выходим из fullscreen
            this.container.classList.remove('code-editor-fullscreen');
            
            // Возвращаем на место
            if (this.originalParent) {
                if (this.originalNextSibling) {
                    this.originalParent.insertBefore(this.container, this.originalNextSibling);
                } else {
                    this.originalParent.appendChild(this.container);
                }
            }
            
            const icon = this.toolbar.querySelector(`#fullscreenBtn-${this.uniqueId} i`);
            if (icon) icon.className = 'ti ti-maximize';
            
            // Разблокируем скролл body
            document.body.style.overflow = '';
            
            console.log('✅ Fullscreen режим выключен');
        }
        
        // Обновляем размер редактора
        if (this.editor) {
            this.editor.resize();
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
            success: 'ti-check-circle-fill',
            error: 'ti-x-circle-fill',
            warning: 'ti-exclamation-triangle-fill',
            info: 'ti-info-circle-fill'
        };
        
        statusEl.innerHTML = `<i class="ti ti-${icons[type] || icons.info}"></i> ${message}`;
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

/**
 * Prompt Editor - vanilla JS редактор без зависимостей
 * Поддержка переменных {variable} с автокомплитом
 */

/**
 * Класс для работы с редактором промптов
 */
class PromptEditor {
    constructor(containerElement, options = {}) {
        this.container = containerElement;
        this.options = {
            initialValue: options.initialValue || '',
            placeholder: options.placeholder || 'Введите промпт...',
            flowId: options.flowId || null,
            onVariableInsert: options.onVariableInsert || null,
            onChange: options.onChange || null,
            onVariablesChange: options.onVariablesChange || null,
            ...options
        };
        
        // Переменные (загружаются с сервера)
        this.systemVariables = [];
        this.companyVariables = [];
        this.userVariables = [];
        this.flowVariables = [];
        this.localVariables = [];
        
        this.editor = null;
        
        this.init();
    }
    
    /**
     * Инициализация редактора
     */
    async init() {
        // Загружаем переменные с сервера
        if (this.options.flowId) {
            await this.loadVariables();
        }
        
        // Создаем структуру
        this.container.innerHTML = `
            <div class="prompt-editor-wrapper">
                <div class="prompt-editor-toolbar">
                    <div class="toolbar-section">
                        <button class="toolbar-btn" data-action="h1" title="Заголовок 1">
                            <i class="bi bi-type-h1"></i>
                        </button>
                        <button class="toolbar-btn" data-action="h2" title="Заголовок 2">
                            <i class="bi bi-type-h2"></i>
                        </button>
                        <button class="toolbar-btn" data-action="h3" title="Заголовок 3">
                            <i class="bi bi-type-h3"></i>
                        </button>
                    </div>
                    <div class="toolbar-section toolbar-divider">
                        <button class="toolbar-btn" data-action="bold" title="Жирный текст">
                            <i class="bi bi-type-bold"></i>
                        </button>
                        <button class="toolbar-btn" data-action="italic" title="Курсив">
                            <i class="bi bi-type-italic"></i>
                        </button>
                        <button class="toolbar-btn" data-action="code" title="Код">
                            <i class="bi bi-code"></i>
                        </button>
                    </div>
                    <div class="toolbar-section toolbar-divider">
                        <button class="toolbar-btn" data-action="list" title="Маркированный список">
                            <i class="bi bi-list-ul"></i>
                        </button>
                        <button class="toolbar-btn" data-action="ordered-list" title="Нумерованный список">
                            <i class="bi bi-list-ol"></i>
                        </button>
                    </div>
                    <div class="toolbar-section">
                        <button class="toolbar-btn" data-action="preview" title="Предпросмотр">
                            <i class="bi bi-eye"></i> Preview
                        </button>
                    </div>
                </div>
                
                <div class="prompt-editor-container">
                    <div class="prompt-editor">
                        <div class="editor-mode" style="display: block;"></div>
                        <div class="preview-mode" style="display: none;"></div>
                    </div>
                    <div class="prompt-variables-panel">
                        <div class="variables-panel-header">
                            <h5><i class="bi bi-list-ul"></i> Переменные</h5>
                            <button class="btn-toggle-panel" title="Свернуть">
                                <i class="bi bi-chevron-right"></i>
                            </button>
                        </div>
                        <div class="variables-panel-content">
                            <div class="variables-search">
                                <input type="text" 
                                       class="form-control form-control-sm" 
                                       placeholder="Поиск переменных...">
                            </div>
                            
                            <div class="variables-categories">
                                <!-- Системные -->
                                <div class="variable-category">
                                    <div class="category-header">
                                        <i class="bi bi-gear"></i> Системные
                                    </div>
                                    <div class="category-items" data-category="system"></div>
                                </div>
                                
                                <!-- Компания -->
                                <div class="variable-category">
                                    <div class="category-header">
                                        <i class="bi bi-building"></i> Компания
                                    </div>
                                    <div class="category-items" data-category="company"></div>
                                </div>
                                
                                <!-- Пользователь -->
                                <div class="variable-category">
                                    <div class="category-header">
                                        <i class="bi bi-person"></i> Пользователь
                                    </div>
                                    <div class="category-items" data-category="user"></div>
                                </div>
                                
                                <!-- Flow -->
                                <div class="variable-category">
                                    <div class="category-header">
                                        <i class="bi bi-diagram-3"></i> Flow
                                        <button class="btn-add-variable" data-type="flow" title="Добавить">
                                            <i class="bi bi-plus-circle"></i>
                                        </button>
                                    </div>
                                    <div class="category-items" data-category="flow"></div>
                                </div>
                                
                                <!-- Локальные -->
                                <div class="variable-category">
                                    <div class="category-header">
                                        <i class="bi bi-box"></i> Локальные
                                        <button class="btn-add-variable" data-type="local" title="Добавить">
                                            <i class="bi bi-plus-circle"></i>
                                        </button>
                                    </div>
                                    <div class="category-items" data-category="local"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Создаем редактор
        const editorElement = this.container.querySelector('.editor-mode');
        this.createEditor(editorElement);
        
        // Получаем preview элемент
        this.previewElement = this.container.querySelector('.preview-mode');
        
        // Рендерим переменные
        this.renderVariables();
        
        // Привязываем обработчики
        this.attachHandlers();
    }
    
    /**
     * Загрузка переменных с сервера
     */
    async loadVariables() {
        if (!this.options.flowId) {
            console.warn('PromptEditor: flowId не указан, переменные не загружены');
            return;
        }
        
        try {
            const response = await fetch(`/frontend/api/variables/flow/${this.options.flowId}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            
            console.log('🔍 DEBUG: API вернул данные:', data);
            console.log('🔍 DEBUG: data.flow =', data.flow);
            
            this.systemVariables = data.system || [];
            this.companyVariables = data.company || [];
            this.userVariables = data.user || [];
            this.flowVariables = data.flow || [];
            this.localVariables = data.local || [];
            
            // Дополнительно загружаем все переменные компании из variables API
            try {
                const varsResponse = await fetch('/api/v1/admin/variables');
                if (varsResponse.ok) {
                    const varsData = await varsResponse.json();
                    // Добавляем пользовательские переменные компании
                    for (const [key, varInfo] of Object.entries(varsData)) {
                        if (!this.companyVariables.find(v => v.name === key)) {
                            this.companyVariables.push({
                                name: key,
                                description: varInfo.secret ? 'Секрет компании' : 'Переменная компании',
                                category: 'company',
                                value: varInfo.secret ? '***' : varInfo.value,
                                editable: true
                            });
                        }
                    }
                }
            } catch (err) {
                console.warn('Не удалось загрузить переменные компании:', err);
            }
            
            console.log('✅ Переменные загружены:', {
                system: this.systemVariables.length,
                company: this.companyVariables.length,
                user: this.userVariables.length,
                flow: this.flowVariables.length,
                local: this.localVariables.length
            });
            console.log('🔍 DEBUG: flowVariables:', this.flowVariables);
            
        } catch (error) {
            console.error('Ошибка загрузки переменных:', error);
        }
    }
    
    /**
     * Создание простого textarea редактора с подсветкой переменных
     */
    createEditor(element) {
        // Создаем контейнер с подсветкой
        const editorContainer = document.createElement('div');
        editorContainer.className = 'prompt-editor-inner';
        
        // Backdrop для подсветки
        const backdrop = document.createElement('div');
        backdrop.className = 'prompt-backdrop';
        
        const highlights = document.createElement('div');
        highlights.className = 'prompt-highlights';
        backdrop.appendChild(highlights);
        
        // Textarea
        const textarea = document.createElement('textarea');
        textarea.className = 'prompt-textarea';
        textarea.placeholder = this.options.placeholder;
        textarea.value = this.options.initialValue;
        
        // Drag and drop - вставка в место клика
        textarea.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
            
            // Обновляем позицию курсора при перемещении мыши
            const pos = this.getTextareaPositionFromPoint(textarea, e.clientX, e.clientY);
            if (pos !== null) {
                textarea.setSelectionRange(pos, pos);
            }
        });
        
        textarea.addEventListener('drop', (e) => {
            e.preventDefault();
            const variableName = e.dataTransfer.getData('text/plain');
            if (variableName) {
                // Вставляем в текущую позицию курсора
                const cursorPos = textarea.selectionStart;
                const textBefore = textarea.value.substring(0, cursorPos);
                const textAfter = textarea.value.substring(cursorPos);
                
                textarea.value = textBefore + `{${variableName}}` + textAfter;
                const newPos = cursorPos + variableName.length + 2;
                textarea.setSelectionRange(newPos, newPos);
                textarea.focus();
                
                this.highlightVariables();
                
                if (this.options.onChange) {
                    this.options.onChange(this.getValue());
                }
            }
        });
        
        // Обработчик изменений
        textarea.addEventListener('input', () => {
            this.highlightVariables();
            
            if (this.options.onChange) {
                this.options.onChange(this.getValue());
            }
        });
        
        // Синхронизация прокрутки
        textarea.addEventListener('scroll', () => {
            backdrop.scrollTop = textarea.scrollTop;
            backdrop.scrollLeft = textarea.scrollLeft;
        });
        
        // Автокомплит при вводе {
        textarea.addEventListener('keydown', (e) => {
            if (e.key === '{') {
                setTimeout(() => this.showAutocomplete(textarea), 50);
            } else if (e.key === 'Escape') {
                this.hideAutocomplete();
            }
        });
        
        // Клик вне автокомплита
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.autocomplete-dropdown')) {
                this.hideAutocomplete();
            }
        });
        
        editorContainer.appendChild(backdrop);
        editorContainer.appendChild(textarea);
        element.appendChild(editorContainer);
        
        this.editor = textarea;
        this.highlights = highlights;
        
        // Первичная подсветка
        this.highlightVariables();
    }
    
    /**
     * Показать автокомплит переменных
     */
    showAutocomplete(textarea) {
        // Получаем позицию курсора
        const cursorPos = textarea.selectionStart;
        const textBeforeCursor = textarea.value.substring(0, cursorPos);
        
        // Проверяем есть ли незакрытая {
        const lastBrace = textBeforeCursor.lastIndexOf('{');
        if (lastBrace === -1 || textBeforeCursor.substring(lastBrace).includes('}')) {
            return;
        }
        
        // Получаем текст после {
        const searchText = textBeforeCursor.substring(lastBrace + 1).toLowerCase();
        
        // Фильтруем переменные
        const allVariables = [
            ...this.systemVariables,
            ...this.companyVariables,
            ...this.userVariables,
            ...this.flowVariables,
            ...this.localVariables
        ];
        
        const filtered = allVariables.filter(v => 
            v.name.toLowerCase().includes(searchText) ||
            (v.description && v.description.toLowerCase().includes(searchText))
        );
        
        if (filtered.length === 0) return;
        
        // Создаем dropdown
        this.hideAutocomplete();
        
        const dropdown = document.createElement('div');
        dropdown.className = 'autocomplete-dropdown';
        dropdown.innerHTML = filtered.slice(0, 10).map(v => `
            <div class="autocomplete-item" data-variable="${v.name}">
                <div class="autocomplete-name">{${v.name}}</div>
                <div class="autocomplete-desc">${v.description || ''}</div>
                ${v.value !== undefined && v.value !== null ? `<div class="autocomplete-value">Текущее: ${v.value}</div>` : ''}
            </div>
        `).join('');
        
        // Вычисляем позицию курсора относительно textarea
        const coords = this.getCaretCoordinates(textarea, cursorPos);
        const textareaRect = textarea.getBoundingClientRect();
        
        dropdown.style.position = 'fixed';
        dropdown.style.left = `${textareaRect.left + coords.left}px`;
        dropdown.style.top = `${textareaRect.top + coords.top + coords.height + 2}px`;
        dropdown.style.minWidth = '300px';
        dropdown.style.maxWidth = '400px';
        
        // Обработчик клика
        dropdown.addEventListener('click', (e) => {
            const item = e.target.closest('.autocomplete-item');
            if (item) {
                const varName = item.dataset.variable;
                this.completeVariable(textarea, lastBrace, varName);
                this.hideAutocomplete();
            }
        });
        
        document.body.appendChild(dropdown);
        this.autocompleteDropdown = dropdown;
    }
    
    /**
     * Вычисление координат каретки в textarea
     * Использует скрытый div для измерения позиции
     */
    getCaretCoordinates(element, position) {
        const div = document.createElement('div');
        const style = window.getComputedStyle(element);
        
        // Копируем стили textarea
        ['fontFamily', 'fontSize', 'fontWeight', 'lineHeight', 
         'letterSpacing', 'padding', 'border', 'whiteSpace',
         'wordWrap', 'wordBreak'].forEach(prop => {
            div.style[prop] = style[prop];
        });
        
        div.style.position = 'absolute';
        div.style.visibility = 'hidden';
        div.style.whiteSpace = 'pre-wrap';
        div.style.wordWrap = 'break-word';
        div.style.width = element.clientWidth + 'px';
        
        // Копируем текст до курсора
        const textBeforeCaret = element.value.substring(0, position);
        div.textContent = textBeforeCaret;
        
        // Создаем span для измерения позиции курсора
        const span = document.createElement('span');
        span.textContent = '|';
        div.appendChild(span);
        
        document.body.appendChild(div);
        
        const spanRect = span.getBoundingClientRect();
        const divRect = div.getBoundingClientRect();
        
        const coordinates = {
            left: spanRect.left - divRect.left + element.scrollLeft,
            top: spanRect.top - divRect.top + element.scrollTop,
            height: spanRect.height
        };
        
        document.body.removeChild(div);
        
        return coordinates;
    }
    
    /**
     * Скрыть автокомплит
     */
    hideAutocomplete() {
        if (this.autocompleteDropdown) {
            this.autocompleteDropdown.remove();
            this.autocompleteDropdown = null;
        }
    }
    
    /**
     * Завершить ввод переменной
     */
    completeVariable(textarea, bracePos, varName) {
        const cursorPos = textarea.selectionStart;
        const text = textarea.value;
        
        // Заменяем текст от { до курсора на {varName}
        const newText = text.substring(0, bracePos) + `{${varName}}` + text.substring(cursorPos);
        textarea.value = newText;
        
        // Ставим курсор после }
        const newCursorPos = bracePos + varName.length + 2;
        textarea.setSelectionRange(newCursorPos, newCursorPos);
        textarea.focus();
        
        if (this.options.onChange) {
            this.options.onChange(this.getValue());
        }
    }
    
    /**
     * Получить позицию в тексте по координатам клика (упрощенный метод)
     */
    getTextareaPositionFromPoint(textarea, x, y) {
        const rect = textarea.getBoundingClientRect();
        const style = window.getComputedStyle(textarea);
        
        // Координаты относительно textarea с учетом padding
        const paddingLeft = parseFloat(style.paddingLeft);
        const paddingTop = parseFloat(style.paddingTop);
        const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.6;
        
        const relX = x - rect.left - paddingLeft + textarea.scrollLeft;
        const relY = y - rect.top - paddingTop + textarea.scrollTop;
        
        // Определяем строку
        const lineIndex = Math.floor(relY / lineHeight);
        const lines = textarea.value.split('\n');
        
        if (lineIndex < 0) return 0;
        if (lineIndex >= lines.length) return textarea.value.length;
        
        // Позиция начала строки
        let lineStart = 0;
        for (let i = 0; i < lineIndex; i++) {
            lineStart += lines[i].length + 1; // +1 для \n
        }
        
        // Приблизительно вычисляем позицию в строке
        const charWidth = parseFloat(style.fontSize) * 0.6; // Примерная ширина символа
        const charIndex = Math.round(relX / charWidth);
        const lineLength = lines[lineIndex].length;
        
        const posInLine = Math.max(0, Math.min(charIndex, lineLength));
        return lineStart + posInLine;
    }
    
    /**
     * Подсветка переменных в тексте
     */
    highlightVariables() {
        if (!this.highlights || !this.editor) return;
        
        const text = this.editor.value;
        
        // Получаем значения переменных
        const allVariables = [
            ...this.systemVariables,
            ...this.companyVariables,
            ...this.userVariables,
            ...this.flowVariables,
            ...this.localVariables
        ];
        
        // Создаем map для быстрого поиска
        const varMap = {};
        allVariables.forEach(v => {
            varMap[v.name] = v;
        });
        
        // Экранируем HTML и подсвечиваем переменные
        const highlighted = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '\n')
            .replace(/\{(\w+)\}/g, (match, varName) => {
                const variable = varMap[varName];
                let title = varName;
                
                if (variable) {
                    title = variable.description ? `${variable.name} - ${variable.description}` : variable.name;
                    if (variable.value !== undefined && variable.value !== null) {
                        title += `\nТекущее значение: ${variable.value}`;
                    }
                }
                
                return `<span class="variable-highlight" title="${title}">{${varName}}</span>`;
            });
        
        this.highlights.innerHTML = highlighted;
    }
    
    /**
     * Рендеринг списка переменных
     */
    renderVariables() {
        this.renderVariableCategory('system', this.systemVariables);
        this.renderVariableCategory('company', this.companyVariables);
        this.renderVariableCategory('user', this.userVariables);
        this.renderVariableCategory('flow', this.flowVariables);
        this.renderVariableCategory('local', this.localVariables);
    }
    
    /**
     * Рендеринг категории переменных
     */
    renderVariableCategory(category, variables) {
        const container = this.container.querySelector(`.category-items[data-category="${category}"]`);
        if (!container) return;
        
        if (variables.length === 0) {
            container.innerHTML = '<div class="no-variables">Нет переменных</div>';
            return;
        }
        
        container.innerHTML = variables.map(v => `
            <div class="variable-item" 
                 data-variable="${v.name}"
                 draggable="true">
                <div class="variable-info">
                    <div class="variable-name">{${v.name}}</div>
                    <div class="variable-description">${v.description || ''}</div>
                    ${v.value !== undefined && v.value !== null ? `<div class="variable-value">Текущее: ${v.value}</div>` : ''}
                </div>
                <button class="btn-insert-variable" 
                        data-variable="${v.name}" 
                        title="Вставить">
                    <i class="bi bi-plus-lg"></i>
                </button>
            </div>
        `).join('');
        
        // Добавляем обработчики drag для новых элементов
        container.querySelectorAll('.variable-item').forEach(item => {
            item.addEventListener('dragstart', (e) => {
                const varName = item.dataset.variable;
                e.dataTransfer.setData('text/plain', varName);
                e.dataTransfer.effectAllowed = 'copy';
                item.classList.add('dragging');
            });
            
            item.addEventListener('dragend', (e) => {
                item.classList.remove('dragging');
            });
        });
    }
    
    /**
     * Привязка обработчиков событий
     */
    attachHandlers() {
        // Toolbar кнопки
        this.container.querySelectorAll('.toolbar-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.currentTarget.dataset.action;
                this.handleToolbarAction(action);
            });
        });
        
        // Вставка переменных
        this.container.addEventListener('click', (e) => {
            const insertBtn = e.target.closest('.btn-insert-variable');
            if (insertBtn) {
                const variable = insertBtn.dataset.variable;
                this.insertVariable(variable);
            }
        });
        
        // Добавление новой переменной
        this.container.querySelectorAll('.btn-add-variable').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const type = e.currentTarget.dataset.type;
                this.showAddVariableDialog(type);
            });
        });
        
        // Переключение панели
        const toggleBtn = this.container.querySelector('.btn-toggle-panel');
        const panel = this.container.querySelector('.prompt-variables-panel');
        if (toggleBtn && panel) {
            toggleBtn.addEventListener('click', () => {
                const isCollapsed = panel.classList.contains('collapsed');
                panel.classList.toggle('collapsed');
                
                const icon = toggleBtn.querySelector('i');
                if (icon) {
                    if (isCollapsed) {
                        icon.className = 'bi bi-chevron-right';
                        toggleBtn.title = 'Свернуть';
                    } else {
                        icon.className = 'bi bi-chevron-left';
                        toggleBtn.title = 'Развернуть';
                    }
                }
            });
        }
        
        // Поиск переменных
        const searchInput = this.container.querySelector('.variables-search input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterVariables(e.target.value);
            });
        }
    }
    
    /**
     * Обработка действий тулбара
     */
    handleToolbarAction(action) {
        switch (action) {
            case 'h1':
                this.insertHeading(1);
                break;
            case 'h2':
                this.insertHeading(2);
                break;
            case 'h3':
                this.insertHeading(3);
                break;
            case 'bold':
                this.wrapSelection('**', '**');
                break;
            case 'italic':
                this.wrapSelection('*', '*');
                break;
            case 'code':
                this.wrapSelection('`', '`');
                break;
            case 'list':
                this.insertListItem();
                break;
            case 'ordered-list':
                this.insertOrderedListItem();
                break;
            case 'preview':
                this.togglePreview();
                break;
        }
    }
    
    /**
     * Вставить заголовок
     */
    insertHeading(level) {
        const textarea = this.editor;
        if (!textarea) return;
        
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const text = textarea.value;
        
        const lineStart = text.lastIndexOf('\n', start - 1) + 1;
        const prefix = '#'.repeat(level) + ' ';
        
        const newText = text.substring(0, lineStart) + prefix + text.substring(lineStart);
        textarea.value = newText;
        
        textarea.setSelectionRange(start + prefix.length, end + prefix.length);
        textarea.focus();
        
        this.highlightVariables();
        if (this.options.onChange) {
            this.options.onChange(this.getValue());
        }
    }
    
    /**
     * Вставить элемент маркированного списка
     */
    insertListItem() {
        const textarea = this.editor;
        if (!textarea) return;
        
        const start = textarea.selectionStart;
        const text = textarea.value;
        
        const lineStart = text.lastIndexOf('\n', start - 1) + 1;
        const prefix = '- ';
        
        const newText = text.substring(0, lineStart) + prefix + text.substring(lineStart);
        textarea.value = newText;
        
        textarea.setSelectionRange(start + prefix.length, start + prefix.length);
        textarea.focus();
        
        this.highlightVariables();
        if (this.options.onChange) {
            this.options.onChange(this.getValue());
        }
    }
    
    /**
     * Вставить элемент нумерованного списка
     */
    insertOrderedListItem() {
        const textarea = this.editor;
        if (!textarea) return;
        
        const start = textarea.selectionStart;
        const text = textarea.value;
        
        const lineStart = text.lastIndexOf('\n', start - 1) + 1;
        const prefix = '1. ';
        
        const newText = text.substring(0, lineStart) + prefix + text.substring(lineStart);
        textarea.value = newText;
        
        textarea.setSelectionRange(start + prefix.length, start + prefix.length);
        textarea.focus();
        
        this.highlightVariables();
        if (this.options.onChange) {
            this.options.onChange(this.getValue());
        }
    }
    
    /**
     * Обернуть выделенный текст
     */
    wrapSelection(before, after) {
        const textarea = this.editor;
        if (!textarea) return;
        
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        const selectedText = textarea.value.substring(start, end);
        
        const newText = textarea.value.substring(0, start) + before + selectedText + after + textarea.value.substring(end);
        textarea.value = newText;
        
        textarea.setSelectionRange(start + before.length, start + before.length + selectedText.length);
        textarea.focus();
        
        if (this.options.onChange) {
            this.options.onChange(this.getValue());
        }
    }
    
    /**
     * Вставить переменную
     */
    insertVariable(variableName) {
        const textarea = this.editor;
        if (!textarea) return;
        
        const start = textarea.selectionStart;
        const end = textarea.selectionEnd;
        
        const varText = `{${variableName}}`;
        const newText = textarea.value.substring(0, start) + varText + textarea.value.substring(end);
        textarea.value = newText;
        
        textarea.setSelectionRange(start + varText.length, start + varText.length);
        textarea.focus();
        
        if (this.options.onChange) {
            this.options.onChange(this.getValue());
        }
        
        if (this.options.onVariableInsert) {
            this.options.onVariableInsert(variableName);
        }
    }
    
    /**
     * Переключить preview режим
     */
    togglePreview() {
        const editorMode = this.container.querySelector('.editor-mode');
        const previewMode = this.container.querySelector('.preview-mode');
        const btn = this.container.querySelector('[data-action="preview"]');
        
        const isPreview = editorMode.style.display === 'none';
        
        if (isPreview) {
            // Возврат к редактированию
            editorMode.style.display = 'block';
            previewMode.style.display = 'none';
            if (btn) {
                btn.querySelector('i').className = 'bi bi-eye';
                btn.querySelector('.btn-text')?.remove();
                const text = document.createTextNode(' Preview');
                btn.appendChild(text);
            }
        } else {
            // Показать preview
            editorMode.style.display = 'none';
            previewMode.style.display = 'block';
            this.updatePreview();
            if (btn) {
                btn.querySelector('i').className = 'bi bi-pencil';
                btn.childNodes.forEach(node => {
                    if (node.nodeType === 3) node.remove();
                });
                const text = document.createTextNode(' Редактор');
                btn.appendChild(text);
            }
        }
    }
    
    /**
     * Обновить preview
     */
    updatePreview() {
        if (!this.previewElement) return;
        
        let text = this.getValue();
        
        // Подставляем значения переменных
        const allVariables = [
            ...this.systemVariables,
            ...this.companyVariables,
            ...this.userVariables,
            ...this.flowVariables,
            ...this.localVariables
        ];
        
        allVariables.forEach(v => {
            if (v.value !== undefined && v.value !== null) {
                const regex = new RegExp(`\\{${v.name}\\}`, 'g');
                const tooltipText = v.description ? `${v.name} - ${v.description}` : v.name;
                text = text.replace(regex, `<span class="variable-value-inline" title="${tooltipText}">${v.value}</span>`);
            }
        });
        
        // Простой markdown рендеринг
        text = this.renderMarkdown(text);
        
        this.previewElement.innerHTML = text;
    }
    
    /**
     * Простой markdown рендеринг
     */
    renderMarkdown(text) {
        return text
            // Заголовки
            .replace(/^### (.+)$/gm, '<h3>$1</h3>')
            .replace(/^## (.+)$/gm, '<h2>$1</h2>')
            .replace(/^# (.+)$/gm, '<h1>$1</h1>')
            // Жирный
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Курсив
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // Код
            .replace(/`(.+?)`/g, '<code>$1</code>')
            // Списки
            .replace(/^- (.+)$/gm, '<li>$1</li>')
            .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
            .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
            // Переносы строк
            .replace(/\n\n/g, '</p><p>')
            .replace(/^(.+)$/gm, '<p>$1</p>')
            .replace(/<p><\/p>/g, '');
    }
    
    /**
     * Показать диалог добавления переменной
     */
    showAddVariableDialog(type) {
        const modal = document.createElement('div');
        modal.className = 'prompt-variable-modal';
        
        // Для flow переменных - выбор из company variables
        let valueInput = '';
        if (type === 'flow') {
            const companyVarsOptions = this.companyVariables.map(v => 
                `<option value="@var:${v.name}">@var:${v.name} (${v.value || 'пусто'})</option>`
            ).join('');
            
            valueInput = `
                <div class="form-group">
                    <label>Тип значения</label>
                    <div class="mb-2">
                        <div class="form-check">
                            <input class="form-check-input" type="radio" name="value-type" id="value-type-var" value="var" checked onchange="toggleValueInput()">
                            <label class="form-check-label" for="value-type-var">
                                Ссылка на переменную компании
                            </label>
                        </div>
                        <div class="form-check">
                            <input class="form-check-input" type="radio" name="value-type" id="value-type-hardcoded" value="hardcoded" onchange="toggleValueInput()">
                            <label class="form-check-label" for="value-type-hardcoded">
                                Хардкод значение
                            </label>
                        </div>
                    </div>
                </div>
                <div class="form-group" id="var-select-group">
                    <label>Выберите переменную</label>
                    <select class="form-control" id="variable-value-select">
                        <option value="">-- Выберите переменную --</option>
                        ${companyVarsOptions}
                    </select>
                </div>
                <div class="form-group" id="hardcoded-input-group" style="display: none;">
                    <label>Значение</label>
                    <input type="text" class="form-control" placeholder="Хардкод значение" id="variable-value-hardcoded">
                </div>
            `;
        } else {
            valueInput = `
                <div class="form-group">
                    <label>Значение по умолчанию</label>
                    <input type="text" 
                           class="form-control" 
                           placeholder="Значение" 
                           id="variable-value">
                </div>
            `;
        }
        
        modal.innerHTML = `
            <div class="modal-overlay" onclick="this.parentElement.remove()"></div>
            <div class="modal-content">
                <div class="modal-header">
                    <h5>Добавить ${type === 'flow' ? 'Flow' : 'локальную'} переменную</h5>
                    <button class="btn-close" onclick="this.closest('.prompt-variable-modal').remove()">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Название переменной</label>
                        <input type="text" 
                               class="form-control" 
                               placeholder="my_variable" 
                               pattern="[a-z_][a-z0-9_]*"
                               id="variable-name">
                        <small class="form-text">Только латинские буквы, цифры и подчеркивание</small>
                    </div>
                    ${valueInput}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="this.closest('.prompt-variable-modal').remove()">
                        Отмена
                    </button>
                    <button class="btn btn-primary" onclick="window.currentEditor.addVariable('${type}')">
                        Добавить
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        window.currentEditor = this;
        
        // Функция переключения между select и input для flow переменных
        window.toggleValueInput = function() {
            const varGroup = document.getElementById('var-select-group');
            const hardcodedGroup = document.getElementById('hardcoded-input-group');
            const varRadio = document.getElementById('value-type-var');
            
            if (varGroup && hardcodedGroup) {
                if (varRadio.checked) {
                    varGroup.style.display = 'block';
                    hardcodedGroup.style.display = 'none';
                } else {
                    varGroup.style.display = 'none';
                    hardcodedGroup.style.display = 'block';
                }
            }
        };
        
        // Фокус на поле ввода
        setTimeout(() => modal.querySelector('#variable-name').focus(), 100);
    }
    
    /**
     * Добавить новую переменную
     */
    addVariable(type) {
        const modal = document.querySelector('.prompt-variable-modal');
        const name = modal.querySelector('#variable-name').value.trim();
        
        let value = '';
        if (type === 'flow') {
            // Для flow переменных проверяем тип
            const varRadio = modal.querySelector('#value-type-var');
            if (varRadio && varRadio.checked) {
                // Ссылка на company variable
                const select = modal.querySelector('#variable-value-select');
                value = select ? select.value : '';
            } else {
                // Хардкод значение
                const input = modal.querySelector('#variable-value-hardcoded');
                value = input ? input.value.trim() : '';
            }
        } else {
            // Для локальных переменных - обычный input
            const valueInput = modal.querySelector('#variable-value');
            value = valueInput ? valueInput.value.trim() : '';
        }
        
        if (!name) {
            alert('Введите название переменной');
            return;
        }
        
        if (!/^[a-z_][a-z0-9_]*$/.test(name)) {
            alert('Название должно содержать только латинские буквы, цифры и подчеркивание');
            return;
        }
        
        if (!value) {
            alert('Выберите или введите значение');
            return;
        }
        
        const variable = {
            name,
            description: '',
            value,
            category: type
        };
        
        if (type === 'flow') {
            this.flowVariables.push(variable);
        } else {
            this.localVariables.push(variable);
        }
        
        this.renderVariables();
        modal.remove();
        
        // Триггерим событие изменения переменных
        if (this.options.onVariablesChange) {
            this.options.onVariablesChange(type, this.getVariables(type));
        }
    }
    
    /**
     * Фильтрация переменных
     */
    filterVariables(query) {
        const items = this.container.querySelectorAll('.variable-item');
        const lowerQuery = query.toLowerCase();
        
        items.forEach(item => {
            const name = item.dataset.variable.toLowerCase();
            const description = item.querySelector('.variable-description')?.textContent.toLowerCase() || '';
            
            if (name.includes(lowerQuery) || description.includes(lowerQuery)) {
                item.style.display = '';
            } else {
                item.style.display = 'none';
            }
        });
    }
    
    
    /**
     * Получить значение редактора
     */
    getValue() {
        return this.editor ? this.editor.value : '';
    }
    
    /**
     * Установить значение редактора
     */
    setValue(value) {
        if (this.editor) {
            this.editor.value = value;
        }
    }
    
    /**
     * Получить переменные
     */
    getVariables(type) {
        if (type === 'flow') {
            return this.flowVariables;
        } else if (type === 'local') {
            return this.localVariables;
        }
        return [];
    }
    
    /**
     * Установить переменные
     */
    setVariables(type, variables) {
        if (type === 'flow') {
            this.flowVariables = variables;
        } else if (type === 'local') {
            this.localVariables = variables;
        }
        this.renderVariables();
    }
    
    /**
     * Уничтожить редактор
     */
    destroy() {
        if (this.autocompleteDropdown) {
            this.autocompleteDropdown.remove();
        }
        if (this.editor) {
            this.editor.remove();
        }
    }
}

// Экспорт
window.PromptEditor = PromptEditor;

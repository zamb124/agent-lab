/**
 * PropertiesPanel - управление панелью свойств ноды
 * Загружает формы через HTMX при клике на ноду
 */

export default class PropertiesPanel {
    constructor(builder) {
        this.builder = builder;
        this.panel = document.getElementById('propertiesPanel');
        
        console.log('🔧 PropertiesPanel init:', {
            panel: !!this.panel
        });
        
        this.currentNode = null;
        this.codeEditor = null;
    }
    
    init() {
        this.setupEventListeners();
    }
    
    initCodeEditor(containerId, defaultCode, onSaveCallback) {
        console.log('🔧 initCodeEditor вызван');
        console.log('   containerId:', containerId);
        console.log('   this.builder.flowId:', this.builder.flowId);
        
        if (typeof CodeEditor === 'undefined') {
            console.error('CodeEditor не загружен! Проверьте что code-editor.js подключен.');
            return null;
        }
        
        if (typeof ace === 'undefined') {
            console.error('Ace Editor не загружен! Проверьте что ace.js подключен из CDN.');
            return null;
        }
        
        return new CodeEditor({
            container: containerId,
            value: defaultCode,
            flowId: this.builder.flowId,
            height: '400px',
            onSave: onSaveCallback
        });
    }
    
    setupEventListeners() {
        const closeBtn = document.getElementById('closePanelBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }
    }
    
    async show(node) {
        this.currentNode = node;
        
        if (this.panel) {
            this.panel.classList.remove('hidden');
            this.panel.style.display = 'block';
        }
        
        await this.loadNodeForm(node);
    }
    
    hide() {
        if (this.codeEditor) {
            this.codeEditor.destroy();
            this.codeEditor = null;
        }
        
        this.panel.classList.add('hidden');
        this.panel.style.display = 'none';
        this.currentNode = null;
        
        this.panel.innerHTML = `
            <button class="properties-close-btn" id="closePanelBtn">
                <i class="bi bi-x-circle-fill"></i>
            </button>
            <div class="properties-empty">
                <i class="bi bi-cursor"></i>
                <p>Select a node to edit properties</p>
            </div>
        `;
        
        const closeBtn = this.panel.querySelector('#closePanelBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }
    }
    
    loadMessageNodeEditor(node) {
        const nodeName = node.data.params?.name || node.id;
        
        this.panel.innerHTML = `
            <button class="properties-close-btn" id="closePanelBtn">
                <i class="bi bi-x-circle-fill"></i>
            </button>
            <div class="card">
                <div class="card-header" style="background: #06b6d4; color: white;">
                    <i class="bi bi-chat-dots"></i> ${nodeName}
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3">Отправка фиксированного сообщения пользователю</p>
                    
                    <div class="form-group mb-3">
                        <label>Текст сообщения</label>
                        <textarea 
                            class="form-control" 
                            rows="4" 
                            id="message-text"
                            placeholder="Введите текст сообщения..."
                        >${node.data.params?.message || ''}</textarea>
                        <small class="form-text">Это сообщение будет добавлено в историю диалога</small>
                    </div>
                    
                    <div class="form-group mb-3">
                        <label>Описание ноды</label>
                        <input 
                            type="text" 
                            class="form-control" 
                            id="node-description"
                            value="${node.data.params?.description || ''}"
                            placeholder="Опишите назначение ноды">
                    </div>
                    
                    <button class="btn btn-primary" onclick="window.builderInstance.propertiesPanel.saveMessageNode('${node.id}')">
                        <i class="bi bi-floppy"></i> Сохранить
                    </button>
                </div>
            </div>
        `;
        
        const closeBtn = this.panel.querySelector('#closePanelBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }
    }
    
    loadRouterNodeEditor(node) {
        console.log('🔧 Loading Router Node editor, data:', node.data);
        
        const nodeName = node.data.params?.name || node.id;
        
        this.panel.innerHTML = `
            <button class="properties-close-btn" id="closePanelBtn">
                <i class="bi bi-x-circle-fill"></i>
            </button>
            <div class="card">
                <div class="card-header" style="background: #ef4444; color: white;">
                    <i class="bi bi-lightning"></i> ${nodeName}
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3">Функция-роутер для условных переходов. Возвращает ID следующей ноды на основе state.</p>
                    
                    <div class="form-group mb-3">
                        <label>Путь к функции</label>
                        <input 
                            type="text" 
                            class="form-control font-monospace" 
                            id="router-function"
                            value="${node.data.params?.function_path || node.data.function_path || ''}"
                            placeholder="app.agents.my.router_function">
                        <small class="form-text">Или используйте inline код ниже</small>
                    </div>
                    
                    <div class="form-group mb-3">
                        <label>Inline код роутера</label>
                        <div id="router-inline-code-editor"></div>
                        <small class="form-text mt-2 d-block">Функция должна возвращать ID следующей ноды (строку)</small>
                    </div>
                    
                    <div class="form-group mb-3">
                        <label>Описание</label>
                        <input 
                            type="text" 
                            class="form-control" 
                            id="node-description"
                            value="${node.data.params?.description || ''}"
                            placeholder="Опишите логику роутинга">
                    </div>
                    
                    <button class="btn btn-primary" onclick="window.builderInstance.propertiesPanel.saveRouterNode('${node.id}')">
                        <i class="bi bi-floppy"></i> Сохранить
                    </button>
                </div>
            </div>
        `;
        
        const closeBtn = this.panel.querySelector('#closePanelBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }
        
        const defaultCode = node.data.params?.inline_code || node.data.inline_code || `def router_condition(state: dict) -> str:
    """Router function that returns next node ID
    
    Args:
        state: Graph state with keys: messages, store, etc.
        
    Returns:
        ID of next node (string) or 'END'
    """
    if state.get('done'):
        return 'next_node_id'
    return 'END'
`;
        
        setTimeout(() => {
            if (this.codeEditor) {
                this.codeEditor.destroy();
                this.codeEditor = null;
            }
            
            this.codeEditor = this.initCodeEditor(
                '#router-inline-code-editor',
                defaultCode,
                () => this.saveRouterNode(node.id)
            );
        }, 100);
    }
    
    loadFunctionNodeEditor(node) {
        console.log('🔧 Loading Function Node editor, data:', node.data);
        
        const nodeName = node.data.params?.name || node.id;
        
        this.panel.innerHTML = `
            <button class="properties-close-btn" id="closePanelBtn">
                <i class="bi bi-x-circle-fill"></i>
            </button>
            <div class="card">
                <div class="card-header" style="background: #f59e0b; color: white;">
                    <i class="bi bi-code-square"></i> ${nodeName}
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3">Выполнение произвольного Python кода. Функция получает state и возвращает обновлённый state.</p>
                    
                    <div class="form-group mb-3">
                        <label>Путь к функции</label>
                        <input 
                            type="text" 
                            class="form-control font-monospace" 
                            id="function-path"
                            value="${node.data.params?.function_path || node.data.function_path || ''}"
                            placeholder="app.agents.my.my_function">
                        <small class="form-text">Или используйте inline код ниже</small>
                    </div>
                    
                    <div class="form-group mb-3">
                        <label>Inline код</label>
                        <div id="function-inline-code-editor"></div>
                        <small class="form-text mt-2 d-block">Функция для выполнения в графе</small>
                    </div>
                    
                    <div class="form-group mb-3">
                        <label>Описание</label>
                        <input 
                            type="text" 
                            class="form-control" 
                            id="node-description"
                            value="${node.data.params?.description || ''}"
                            placeholder="Опишите что делает функция">
                    </div>
                    
                    <button class="btn btn-primary" onclick="window.builderInstance.propertiesPanel.saveFunctionNode('${node.id}')">
                        <i class="bi bi-floppy"></i> Сохранить
                    </button>
                </div>
            </div>
        `;
        
        const closeBtn = this.panel.querySelector('#closePanelBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }
        
        const defaultCode = node.data.params?.inline_code || node.data.inline_code || `async def node_function(state: dict) -> dict:
    """Node function in StateGraph
    
    Args:
        state: Graph state with keys: messages, store, etc.
        
    Returns:
        Updated state dict
    """
    messages = state.get("messages", [])
    store = state.get("store", {})
    
    # Your logic here
    
    return state
`;
        
        setTimeout(() => {
            if (this.codeEditor) {
                this.codeEditor.destroy();
                this.codeEditor = null;
            }
            
            this.codeEditor = this.initCodeEditor(
                '#function-inline-code-editor',
                defaultCode,
                () => this.saveFunctionNode(node.id)
            );
        }, 100);
    }
    
    saveMessageNode(nodeId) {
        const node = this.builder.canvas.nodes.get(nodeId);
        if (!node) return;
        
        const message = document.getElementById('message-text').value;
        const description = document.getElementById('node-description').value;
        
        node.data.params = node.data.params || {};
        node.data.params.message = message;
        node.data.params.description = description;
        node.data.params.name = node.data.params.name || node.id;
        
        // Обновляем визуал ноды на канвасе
        const nodeElement = node.element;
        const nameElement = nodeElement.querySelector('.palette-name');
        if (nameElement) {
            nameElement.textContent = description || message.substring(0, 30) || 'Message';
        }
        
        this.builder.showNotification('Message Node сохранён', 'success');
    }
    
    saveRouterNode(nodeId) {
        const node = this.builder.canvas.nodes.get(nodeId);
        if (!node) return;
        
        const functionPath = document.getElementById('router-function').value;
        const inlineCode = this.codeEditor ? this.codeEditor.getValue() : '';
        const description = document.getElementById('node-description').value;
        
        node.data.function_path = functionPath || null;
        node.data.inline_code = inlineCode || null;
        node.data.code_mode = inlineCode ? 'inline_code' : 'code_reference';
        node.data.params = node.data.params || {};
        node.data.params.description = description;
        node.data.params.name = node.data.params.name || node.id;
        
        this.builder.showNotification('Router Node сохранён', 'success');
    }
    
    saveFunctionNode(nodeId) {
        const node = this.builder.canvas.nodes.get(nodeId);
        if (!node) return;
        
        const functionPath = document.getElementById('function-path').value;
        const inlineCode = this.codeEditor ? this.codeEditor.getValue() : '';
        const description = document.getElementById('node-description').value;
        
        node.data.function_path = functionPath || null;
        node.data.inline_code = inlineCode || null;
        node.data.code_mode = inlineCode ? 'inline_code' : 'code_reference';
        node.data.params = node.data.params || {};
        node.data.params.description = description;
        node.data.params.name = node.data.params.name || node.id;
        
        this.builder.showNotification('Function Node сохранён', 'success');
    }
    
    async loadNodeForm(node) {
        try {
            this.panel.innerHTML = `
                <button class="properties-close-btn" id="closePanelBtn">
                    <i class="bi bi-x-circle-fill"></i>
                </button>
                <div class="properties-loading">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-2">Loading form...</p>
                </div>
            `;
            
            let closeBtn = this.panel.querySelector('#closePanelBtn');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.hide());
            }
            
            const nodeType = node.data.type;
            let url;
            
            // Inline редакторы для базовых нод
            if (nodeType === 'message_node') {
                this.loadMessageNodeEditor(node);
                return;
            } else if (nodeType === 'router_node') {
                this.loadRouterNodeEditor(node);
                return;
            } else if (nodeType === 'function_node') {
                this.loadFunctionNodeEditor(node);
                return;
            }
            
            // HTMX формы для сложных нод
            if (nodeType === 'flow_node') {
                const flowId = node.data.params?.flow_id || 'new';
                url = `/frontend/models/flow/${encodeURIComponent(flowId)}?view=form`;
            } else if (nodeType === 'agent_node') {
                const agentId = node.data.params?.agent_id || 'new';
                url = `/frontend/models/agent/${encodeURIComponent(agentId)}?view=form`;
            } else if (nodeType === 'tool_node') {
                const toolId = node.data.params?.tool_id || 'new';
                console.log('🔧 Загружаем Tool:', toolId);
                url = `/frontend/models/tool/${encodeURIComponent(toolId)}?view=form`;
                console.log('📡 URL для Tool:', url);
            } else {
                this.panel.innerHTML = `
                    <button class="properties-close-btn" id="closePanelBtn">
                        <i class="bi bi-x-circle-fill"></i>
                    </button>
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle"></i>
                        <p>Properties for ${nodeType} will be available soon.</p>
                    </div>
                `;
                
                const closeBtn = this.panel.querySelector('#closePanelBtn');
                if (closeBtn) {
                    closeBtn.addEventListener('click', () => this.hide());
                }
                return;
            }
            
            console.log('📡 Загружаем форму:', url);
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const html = await response.text();
            
            this.panel.innerHTML = `
                <button class="properties-close-btn" id="closePanelBtn">
                    <i class="bi bi-x-circle-fill"></i>
                </button>
                ${html}
            `;
            
            closeBtn = this.panel.querySelector('#closePanelBtn');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.hide());
            }
            
            if (typeof htmx !== 'undefined') {
                htmx.process(this.panel);
            }
            
            // Инициализируем Ace Editor через HTMXManager
            if (window.app && window.app.htmxManager) {
                console.log('🔧 Вызываем HTMXManager.initAceEditors()');
                window.app.htmxManager.initAceEditors(this.panel);
            } else {
                console.warn('⚠️ HTMXManager не найден, пробуем локальную инициализацию');
                this.initAceEditors();
            }
            
            this.setupAutoSave(node);
            
            console.log('✅ Форма загружена в properties panel');
            
        } catch (error) {
            console.error('❌ Ошибка загрузки формы:', error);
            this.panel.innerHTML = `
                <button class="properties-close-btn" id="closePanelBtn">
                    <i class="bi bi-x-circle-fill"></i>
                </button>
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i>
                    <p>Error loading form: ${error.message}</p>
                </div>
            `;
            
            const closeBtn = this.panel.querySelector('#closePanelBtn');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.hide());
            }
        }
    }
    
    setupAutoSave(node) {
        const form = this.panel.querySelector('form');
        if (!form) return;
        
        const inputs = form.querySelectorAll('input, textarea, select');
        
        inputs.forEach(input => {
            input.addEventListener('change', async (e) => {
                console.log('💾 Автосохранение поля:', input.name);
                
                const nodeType = node.data.type;
                let modelId;
                
                if (nodeType === 'flow_node') {
                    modelId = node.data.params?.flow_id;
                } else if (nodeType === 'agent_node') {
                    modelId = node.data.params?.agent_id;
                } else if (nodeType === 'tool_node') {
                    modelId = node.data.params?.tool_id;
                }
                
                if (!modelId) return;
                
                if (node.data.params) {
                    node.data.params[input.name] = input.value;
                }
                
                this.builder.canvas.updateNodeFromData(node);
            });
        });
    }
    
    initAceEditors() {
        // Находим все контейнеры для code-editor
        const codeContainers = this.panel.querySelectorAll('.code-editor-container');
        
        if (codeContainers.length === 0) {
            return;
        }
        
        console.log(`📝 Найдено ${codeContainers.length} code editor контейнеров`);
        
        codeContainers.forEach(container => {
            const fieldName = container.dataset.fieldName;
            const containerId = container.id;
            
            if (!fieldName || !containerId) {
                console.warn('⚠️ Container без fieldName или id');
                return;
            }
            
            // Проверяем что Ace загружен
            if (typeof ace === 'undefined') {
                console.error('❌ Ace Editor не загружен!');
                return;
            }
            
            console.log(`✅ Инициализируем Ace Editor для ${fieldName}`);
            
            try {
                const editor = ace.edit(containerId);
                editor.setTheme('ace/theme/monokai');
                editor.session.setMode('ace/mode/python');
                
                // Получаем начальное значение из textarea
                const textarea = document.getElementById(fieldName);
                if (textarea) {
                    editor.setValue(textarea.value || '', -1);
                }
                
                editor.setOptions({
                    fontSize: '14px',
                    showPrintMargin: false,
                    enableBasicAutocompletion: true,
                    enableLiveAutocompletion: true,
                    enableSnippets: true
                });
                
                // Синхронизация с textarea
                editor.session.on('change', () => {
                    if (textarea) {
                        textarea.value = editor.getValue();
                        const event = new Event('change', { bubbles: true });
                        textarea.dispatchEvent(event);
                    }
                });
                
                console.log(`✅ Ace Editor инициализирован для ${fieldName}`);
                
            } catch (error) {
                console.error(`❌ Ошибка инициализации Ace для ${fieldName}:`, error);
            }
        });
    }
}

// Экспортируем класс


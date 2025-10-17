/**
 * PropertiesPanel - управление панелью свойств ноды
 * Загружает формы через HTMX при клике на ноду
 */

class PropertiesPanel {
    constructor(builder) {
        this.builder = builder;
        this.panel = document.getElementById('propertiesPanel');
        this.body = document.getElementById('propertiesBody');
        this.footer = document.getElementById('propertiesFooter');
        this.title = document.getElementById('propertiesTitle');
        
        console.log('🔧 PropertiesPanel init:', {
            panel: !!this.panel,
            body: !!this.body,
            footer: !!this.footer,
            title: !!this.title
        });
        
        this.currentNode = null;
        this.codeEditor = null;
    }
    
    init() {
        this.setupEventListeners();
    }
    
    initCodeEditor(containerId, defaultCode, onSaveCallback) {
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
        
        const deleteBtn = document.getElementById('deleteNodeBtn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => this.deleteCurrentNode());
        }
        
        const duplicateBtn = document.getElementById('duplicateNodeBtn');
        if (duplicateBtn) {
            duplicateBtn.addEventListener('click', () => this.duplicateCurrentNode());
        }
    }
    
    async show(node) {
        this.currentNode = node;
        
        if (this.panel) {
            this.panel.style.display = 'flex';
        }
        
        if (this.footer) {
            this.footer.style.display = 'flex';
        }
        
        // Обновляем заголовок и показываем его только для inline редакторов
        const nodeType = node.data.type;
        const isInlineEditor = ['message_node', 'router_node', 'function_node'].includes(nodeType);
        
        if (this.title) {
            this.title.style.display = isInlineEditor ? 'flex' : 'none';
            if (isInlineEditor) {
                this.updateTitle(node);
            }
        }
        
        await this.loadNodeForm(node);
    }
    
    hide() {
        if (this.codeEditor) {
            this.codeEditor.destroy();
            this.codeEditor = null;
        }
        
        this.panel.style.display = 'none';
        this.currentNode = null;
        
        this.body.innerHTML = `
            <div class="properties-empty">
                <i class="bi bi-cursor"></i>
                <p>Select a node to edit properties</p>
            </div>
        `;
    }
    
    updateTitle(node) {
        if (!this.title) {
            console.warn('⚠️ Title element не найден в properties panel');
            return;
        }
        
        const nodeType = node.data.type;
        const nodeName = node.data.params?.name || node.id;
        
        const iconMap = {
            'flow_node': 'bi-diagram-3',
            'agent_node': 'bi-robot',
            'tool_node': 'bi-tools',
            'function_node': 'bi-code-square',
            'message_node': 'bi-chat-dots',
            'router_node': 'bi-lightning'
        };
        
        const colorMap = {
            'flow_node': '#3b82f6',
            'agent_node': '#8b5cf6',
            'tool_node': '#10b981',
            'function_node': '#f59e0b',
            'message_node': '#06b6d4',
            'router_node': '#ef4444'
        };
        
        const icon = iconMap[nodeType] || 'bi-square';
        const color = colorMap[nodeType] || '#666';
        
        this.title.innerHTML = `
            <span class="properties-icon">
                <i class="bi ${icon}" style="color: ${color};"></i>
            </span>
            <span class="properties-name">${nodeName}</span>
        `;
    }
    
    loadMessageNodeEditor(node) {
        this.body.innerHTML = `
            <div class="properties-form">
                <p class="text-muted mb-3">Отправка фиксированного сообщения пользователю</p>
                
                <div class="form-group">
                    <label>Текст сообщения</label>
                    <textarea 
                        class="form-control" 
                        rows="4" 
                        id="message-text"
                        placeholder="Введите текст сообщения..."
                    >${node.data.params?.message || ''}</textarea>
                    <small class="form-text">Это сообщение будет добавлено в историю диалога</small>
                </div>
                
                <div class="form-group">
                    <label>Описание ноды</label>
                    <input 
                        type="text" 
                        class="form-control" 
                        id="node-description"
                        value="${node.data.params?.description || ''}"
                        placeholder="Опишите назначение ноды">
                </div>
                
                <button class="btn btn-primary mt-3" onclick="window.builderInstance.propertiesPanel.saveMessageNode('${node.id}')">
                    <i class="bi bi-floppy"></i> Сохранить
                </button>
            </div>
        `;
    }
    
    loadRouterNodeEditor(node) {
        console.log('🔧 Loading Router Node editor, data:', node.data);
        
        this.body.innerHTML = `
            <div class="properties-form">
                <p class="text-muted mb-3">Функция-роутер для условных переходов. Возвращает ID следующей ноды на основе state.</p>
                
                <div class="form-group">
                    <label>Путь к функции</label>
                    <input 
                        type="text" 
                        class="form-control font-monospace" 
                        id="router-function"
                        value="${node.data.params?.function_path || node.data.function_path || ''}"
                        placeholder="app.agents.my.router_function">
                    <small class="form-text">Или используйте inline код ниже</small>
                </div>
                
                <div class="form-group">
                    <label>Inline код роутера</label>
                    <div id="router-inline-code-editor"></div>
                    <small class="form-text mt-2 d-block">Функция должна возвращать ID следующей ноды (строку)</small>
                </div>
                
                <div class="form-group">
                    <label>Описание</label>
                    <input 
                        type="text" 
                        class="form-control" 
                        id="node-description"
                        value="${node.data.params?.description || ''}"
                        placeholder="Опишите логику роутинга">
                </div>
                
                <button class="btn btn-primary mt-3" onclick="window.builderInstance.propertiesPanel.saveRouterNode('${node.id}')">
                    <i class="bi bi-floppy"></i> Сохранить
                </button>
            </div>
        `;
        
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
        
        this.body.innerHTML = `
            <div class="properties-form">
                <p class="text-muted mb-3">Выполнение произвольного Python кода. Функция получает state и возвращает обновлённый state.</p>
                
                <div class="form-group">
                    <label>Путь к функции</label>
                    <input 
                        type="text" 
                        class="form-control font-monospace" 
                        id="function-path"
                        value="${node.data.params?.function_path || node.data.function_path || ''}"
                        placeholder="app.agents.my.my_function">
                    <small class="form-text">Или используйте inline код ниже</small>
                </div>
                
                <div class="form-group">
                    <label>Inline код</label>
                    <div id="function-inline-code-editor"></div>
                    <small class="form-text mt-2 d-block">Функция для выполнения в графе</small>
                </div>
                
                <div class="form-group">
                    <label>Описание</label>
                    <input 
                        type="text" 
                        class="form-control" 
                        id="node-description"
                        value="${node.data.params?.description || ''}"
                        placeholder="Опишите что делает функция">
                </div>
                
                <button class="btn btn-primary mt-3" onclick="window.builderInstance.propertiesPanel.saveFunctionNode('${node.id}')">
                    <i class="bi bi-floppy"></i> Сохранить
                </button>
            </div>
        `;
        
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
            this.body.innerHTML = `
                <div class="properties-loading">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                    <p class="mt-2">Loading form...</p>
                </div>
            `;
            
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
                url = `/frontend/models/tool/${encodeURIComponent(toolId)}?view=form`;
            } else {
                this.body.innerHTML = `
                    <div class="alert alert-info">
                        <i class="bi bi-info-circle"></i>
                        <p>Properties for ${nodeType} will be available soon.</p>
                    </div>
                `;
                return;
            }
            
            console.log('📡 Загружаем форму:', url);
            
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const html = await response.text();
            this.body.innerHTML = html;
            
            if (typeof htmx !== 'undefined') {
                htmx.process(this.body);
            }
            
            this.setupAutoSave(node);
            
            console.log('✅ Форма загружена в properties panel');
            
        } catch (error) {
            console.error('❌ Ошибка загрузки формы:', error);
            this.body.innerHTML = `
                <div class="alert alert-danger">
                    <i class="bi bi-exclamation-triangle"></i>
                    <p>Error loading form: ${error.message}</p>
                </div>
            `;
        }
    }
    
    setupAutoSave(node) {
        const form = this.body.querySelector('form');
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
    
    deleteCurrentNode() {
        if (!this.currentNode) return;
        
        if (confirm('Are you sure you want to delete this node?')) {
            this.builder.canvas.removeNode(this.currentNode.id, true);
            this.hide();
        }
    }
    
    duplicateCurrentNode() {
        if (!this.currentNode) return;
        
        const duplicatedNode = this.builder.canvas.duplicateNode(this.currentNode);
        this.show(duplicatedNode);
    }
}

// Экспортируем класс
window.PropertiesPanel = PropertiesPanel;


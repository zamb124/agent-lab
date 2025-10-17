/**
 * PropertiesPanel - управление панелью свойств ноды
 * Загружает формы через HTMX при клике на ноду
 */

class PropertiesPanel {
    constructor(builder) {
        this.builder = builder;
        this.panel = document.getElementById('propertiesPanel');
        this.body = document.getElementById('propertiesBody');
        
        this.currentNode = null;
    }
    
    init() {
        // Обработчик для фиксированного крестика
        const closeBtn = document.getElementById('propertiesCloseBtn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }
    }
    
    async show(node) {
        this.currentNode = node;
        
        this.panel.style.display = 'block';
        
        await this.loadNodeForm(node);
    }
    
    hide() {
        this.panel.style.display = 'none';
        this.currentNode = null;
        
        this.body.innerHTML = `
            <div class="properties-empty">
                <i class="bi bi-cursor"></i>
                <p>Select a node to edit properties</p>
            </div>
        `;
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
    
}

// Экспортируем класс
window.PropertiesPanel = PropertiesPanel;


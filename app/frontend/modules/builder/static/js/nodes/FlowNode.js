import { BaseNode } from '../core/BaseNode.js';

/**
 * Нода для flow (точка входа)
 */
export class FlowNode extends BaseNode {
    constructor(data, canvas) {
        super(data, canvas);
        this.flowData = null;
    }
    
    /**
     * Создание DOM элемента
     */
    async createDOMElement() {
        const element = document.createElement('div');
        element.className = 'canvas-node flow-node';
        
        const flowId = this.data.params?.flow_id;
        // Загружаем данные только если их еще нет
        if (flowId && !this.flowData) {
            this.flowData = await this.fetchFlowData(flowId);
        }
        
        element.innerHTML = this.renderTemplate();
        
        return element;
    }
    
    /**
     * Создание портов
     */
    async createPorts() {
        // Flow имеет только выходной порт (это entry point)
        this.createPort('output', 'output');
        this.mountPorts();
    }
    
    /**
     * Загрузка данных flow из API
     */
    async fetchFlowData(flowId) {
        try {
            const encodedFlowId = encodeURIComponent(flowId);
            const response = await fetch(`/frontend/api/flows/${encodedFlowId}`);
            
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.warn('Ошибка загрузки данных flow:', error);
        }
        
        return null;
    }
    
    /**
     * Рендеринг шаблона
     */
    renderTemplate() {
        const name = this.flowData?.name || this.data.params?.name || 'Flow';
        const description = this.flowData?.description || this.data.params?.description || 'Entry point';
        
        const displayName = name.length > 30 ? name.substring(0, 27) + '...' : name;
        const displayDesc = description.length > 25 ? description.substring(0, 22) + '...' : description;
        
        return `
            <div class="node-simple-content">
                <div class="node-simple-icon flow">
                    <i class="ti ti-hierarchy"></i>
                </div>
                <div class="node-simple-info">
                    <div class="node-simple-title">${this.escapeHtml(displayName)}</div>
                    <div class="node-simple-desc">${this.escapeHtml(displayDesc)}</div>
                </div>
            </div>
        `;
    }
    
    /**
     * Рекурсивное разворачивание flow
     * Flow имеет только один дочерний элемент - entry_point_agent
     */
    async expand(layoutManager) {
        console.log('📂 FlowNode.expand() для', this.data.params?.flow_id);
        
        if (!this.flowData || !this.flowData.entry_point_agent) {
            console.warn('⚠️ Нет entry_point_agent');
            return [];
        }
        
        const agentId = this.flowData.entry_point_agent;
        console.log('🎯 Создаем entry_point агента:', agentId);
        
        // Вычисляем позицию для агента
        const position = layoutManager.getNextPosition(this);
        
        const agentNodeData = {
            id: `agent_${Date.now()}`,
            type: 'agent_node',
            params: { agent_id: agentId },
            ui: {
                x: position.x,
                y: position.y,
                width: 200,
                height: 100
            }
        };
        
        // Создаем агента БЕЗ автоматического разворачивания
        const agentNode = await this.canvas.addNode(agentNodeData, { autoExpand: false });
        
        // Соединяем flow → agent
        this.canvas.connectionManager.createEdge(this.id, agentNode.id);
        
        // Явно разворачиваем агента
        const children = await agentNode.expand(layoutManager);
        
        return [agentNode, ...children];
    }
    
    /**
     * Сохранение flow с рекурсивным сохранением детей
     */
    async save() {
        let flowId = this.data.params?.flow_id;
        const isNewFlow = !flowId;
        
        console.log('💾 FlowNode.save():', isNewFlow ? 'создание нового' : flowId);
        
        try {
            // Если нового Flow - сначала создаем его в БД
            if (isNewFlow) {
                const createResponse = await fetch('/frontend/api/flows/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: this.data.params?.name || `Новый Flow ${new Date().toLocaleString('ru')}`,
                        description: this.data.params?.description || 'Создан через Builder'
                    })
                });
                
                if (!createResponse.ok) {
                    throw new Error(`HTTP ${createResponse.status}`);
                }
                
                const newFlow = await createResponse.json();
                flowId = newFlow.flow_id;
                
                this.data.params.flow_id = flowId;
                this.flowData = newFlow;
                
                // Обновляем текст ноды с новыми данными
                this.updateNodeContent();
                
                console.log('✅ Flow создан в БД:', flowId);
            }
            
            // Получаем все ноды и связи на canvas
            const graphData = this.canvas.getGraphData();
            
            // Canvas data с позициями
            const canvasData = {
                zoom: this.canvas.zoom,
                panX: this.canvas.panX,
                panY: this.canvas.panY,
                nodes: {}
            };
            
            this.canvas.nodes.forEach((node, nodeId) => {
                canvasData.nodes[nodeId] = {
                    x: node.x,
                    y: node.y,
                    width: node.width,
                    height: node.height
                };
            });
            
            // Сначала сохраняем всех агентов рекурсивно
            const agentNodes = Array.from(this.canvas.nodes.values()).filter(n => n.type === 'agent_node');
            for (const agentNode of agentNodes) {
                await agentNode.save();
            }
            
            // Затем обновляем сам flow
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    graph_definition: graphData,
                    canvas_data: canvasData
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            console.log('✅ Flow сохранен:', flowId);
            return { success: true, flowId };
            
        } catch (error) {
            console.error('❌ Ошибка сохранения flow:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Обновление контента ноды (без перерисовки портов)
     */
    updateNodeContent() {
        if (!this.element) return;
        
        const name = this.flowData?.name || this.data.params?.name || 'Flow';
        const description = this.flowData?.description || this.data.params?.description || 'Entry point';
        
        const displayName = name.length > 30 ? name.substring(0, 27) + '...' : name;
        const displayDesc = description.length > 25 ? description.substring(0, 22) + '...' : description;
        
        const titleEl = this.element.querySelector('.node-simple-title');
        const descEl = this.element.querySelector('.node-simple-desc');
        
        if (titleEl) titleEl.textContent = displayName;
        if (descEl) descEl.textContent = displayDesc;
    }
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}


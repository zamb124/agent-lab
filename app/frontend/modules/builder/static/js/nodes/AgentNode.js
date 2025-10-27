import { BaseNode } from '../core/BaseNode.js';

/**
 * Нода для агентов
 */
export class AgentNode extends BaseNode {
    constructor(data, canvas) {
        super(data, canvas);
        this.agentData = null;
    }
    
    /**
     * Создание DOM элемента
     */
    async createDOMElement() {
        const element = document.createElement('div');
        element.className = 'canvas-node agent-node';
        
        const agentId = this.data.params?.agent_id;
        // Загружаем данные только если их еще нет и agent_id существует в БД
        if (agentId && !this.agentData && !agentId.startsWith('new_')) {
            this.agentData = await this.fetchAgentData(agentId);
        }
        
        element.innerHTML = this.renderTemplate();
        
        return element;
    }
    
    /**
     * Создание портов
     */
    async createPorts() {
        const agentType = this.agentData?.type || this.data.params?.type;
        
        // Входной порт есть всегда
        this.createPort('input', 'input');
        
        // Выходной порт для подключения дочерних нод
        // И для ReAct (тулы/субагенты), и для StateGraph (строим граф)
        this.createPort('output', 'output');
        
        this.mountPorts();
    }
    
    /**
     * Загрузка данных агента из API
     */
    async fetchAgentData(agentId) {
        try {
            const encodedAgentId = encodeURIComponent(agentId);
            const response = await fetch(`/frontend/api/agents/${encodedAgentId}`);
            
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.warn('Ошибка загрузки данных агента:', error);
        }
        
        return null;
    }
    
    /**
     * Рендеринг шаблона
     */
    renderTemplate() {
        const name = this.agentData?.name || this.data.params?.name || 'Agent';
        const description = this.agentData?.description || this.data.params?.description || '';
        const agentType = this.agentData?.type || this.data.params?.type || 'unknown';
        
        const displayName = name.length > 30 ? name.substring(0, 27) + '...' : name;
        const displayDesc = description.length > 25 ? description.substring(0, 22) + '...' : description;
        
        return `
            <div class="node-simple-content">
                <div class="node-simple-icon agent">
                    <i class="bi bi-robot"></i>
                </div>
                <div class="node-simple-info">
                    <div class="node-simple-title">${this.escapeHtml(displayName)}</div>
                    ${displayDesc ? `<div class="node-simple-desc">${this.escapeHtml(displayDesc)}</div>` : ''}
                    <div class="node-simple-meta">
                        <span class="agent-type-badge">${agentType}</span>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * Рекурсивное разворачивание агента
     */
    async expand(layoutManager) {
        console.log('📂 AgentNode.expand() для', this.data.params?.agent_id);
        
        if (!this.agentData) {
            console.warn('⚠️ Нет данных агента для разворачивания');
            return [];
        }
        
        const agentType = this.agentData.type;
        
        if (agentType === 'react') {
            return await this.expandReactAgent(layoutManager);
        } else if (agentType === 'stategraph') {
            return await this.expandStateGraphAgent(layoutManager);
        }
        
        return [];
    }
    
    /**
     * Разворачивание ReAct агента - создаем тулы и субагенты
     */
    async expandReactAgent(layoutManager) {
        const tools = this.agentData.tools || [];
        
        if (tools.length === 0) {
            console.log('📋 У ReAct агента нет тулов');
            return [];
        }
        
        console.log(`🔧 Создаем ${tools.length} элементов для ReAct агента`);
        
        const createdNodes = [];
        
        for (const toolRef of tools) {
            const position = layoutManager.getNextPosition(this);
            
            // Определяем тип элемента
            let nodeType, params, elementId;
            
            if (toolRef.agent_id) {
                // Прямая ссылка на агента через agent_id
                nodeType = 'agent_node';
                elementId = toolRef.agent_id;
                params = {
                    agent_id: elementId,
                    name: toolRef.name || elementId
                };
            } else if (toolRef.tool_id) {
                // Проверяем префикс tool_id - может быть ссылка на агента
                if (toolRef.tool_id.startsWith('agent:')) {
                    // Это агент с префиксом "agent:"
                    nodeType = 'agent_node';
                    elementId = toolRef.tool_id.replace('agent:', '');
                    params = {
                        agent_id: elementId,
                        name: toolRef.name || elementId
                    };
                } else {
                    // Обычный тул
                    nodeType = 'tool_node';
                    elementId = toolRef.tool_id;
                    params = {
                        tool_id: elementId,
                        name: toolRef.name || elementId
                    };
                }
            } else {
                console.warn('⚠️ Неизвестный тип ссылки:', toolRef);
                continue;
            }
            
            const nodeData = {
                id: `${nodeType}_${Date.now()}_${Math.random()}`,
                type: nodeType,
                params,
                ui: {
                    x: position.x,
                    y: position.y,
                    width: 200,
                    height: 100
                }
            };
            
            // Создаем ноду
            // Для tool_node - без разворачивания
            // Для agent_node (субагент) - С разворачиванием его тулов
            const autoExpand = nodeType === 'agent_node';
            const childNode = await this.canvas.addNode(nodeData, { 
                autoExpand,
                layoutManager // Передаем тот же layoutManager для правильных позиций
            });
            createdNodes.push(childNode);
            
            // Соединяем agent → child
            this.canvas.connectionManager.createEdge(this.id, childNode.id);
            
            // Если это субагент и он развернулся - добавляем его детей в результат
            if (nodeType === 'agent_node') {
                const subChildren = childNode.getChildNodes();
                createdNodes.push(...subChildren);
            }
        }
        
        return createdNodes;
    }
    
    /**
     * Разворачивание StateGraph агента - разворачиваем граф
     */
    async expandStateGraphAgent(layoutManager) {
        const graphDef = this.agentData.graph_definition;
        
        if (!graphDef || !graphDef.nodes) {
            console.log('📋 У StateGraph агента нет graph_definition');
            return [];
        }
        
        console.log(`📊 Разворачиваем StateGraph: ${graphDef.nodes.length} нод`);
        
        const createdNodes = [];
        const nodeIdMap = new Map();
        
        // Создаем все ноды
        for (const nodeData of graphDef.nodes) {
            const position = layoutManager.getNextPosition(this);
            
            const childNodeData = {
                ...nodeData,
                id: nodeData.id || `${nodeData.type}_${Date.now()}`,
                ui: {
                    x: position.x,
                    y: position.y,
                    width: 200,
                    height: 100
                }
            };
            
            // Создаем ноду БЕЗ автоматического разворачивания
            const childNode = await this.canvas.addNode(childNodeData, { autoExpand: false });
            createdNodes.push(childNode);
            nodeIdMap.set(nodeData.id, childNode.id);
        }
        
        // Создаем связи между нодами
        if (graphDef.edges && Array.isArray(graphDef.edges)) {
            for (const edgeData of graphDef.edges) {
                const sourceId = nodeIdMap.get(edgeData.source) || edgeData.source;
                const targetId = nodeIdMap.get(edgeData.target) || edgeData.target;
                
                this.canvas.connectionManager.createEdge(sourceId, targetId);
            }
        }
        
        // Соединяем текущего агента с первой нодой графа
        if (createdNodes.length > 0) {
            this.canvas.connectionManager.createEdge(this.id, createdNodes[0].id);
        }
        
        return createdNodes;
    }
    
    /**
     * Сохранение агента с рекурсивным сохранением детей
     */
    async save() {
        let agentId = this.data.params?.agent_id;
        const isNewAgent = !agentId || agentId.startsWith('new_');
        
        console.log('💾 AgentNode.save():', isNewAgent ? 'создание нового' : agentId);
        
        try {
            let agentData;
            
            // Если новый агент - создаем в БД
            if (isNewAgent) {
                const agentType = this.data.params?.type || 'react';
                console.log('🆕 Создание агента в БД:', {
                    'agentType': agentType,
                    'data.params': this.data.params
                });
                
                const createResponse = await fetch('/frontend/api/agents/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: this.data.params?.name || `Новый ${agentType} агент`,
                        description: this.data.params?.description || 'Создан через Builder',
                        agent_type: agentType,  // API ожидает agent_type, не type
                        tools: [],
                        prompt: 'Ты helpful ассистент'
                    })
                });
                
                if (!createResponse.ok) {
                    throw new Error(`HTTP ${createResponse.status}`);
                }
                
                agentData = await createResponse.json();
                agentId = agentData.agent_id;
                
                this.data.params.agent_id = agentId;
                this.agentData = agentData;
                
                // Обновляем текст ноды с новыми данными
                this.updateNodeContent();
                
                console.log('✅ Агент создан в БД:', agentId);
            } else {
                // Загружаем существующего агента
                const response = await fetch(`/frontend/api/agents/${encodeURIComponent(agentId)}`);
                if (!response.ok) {
                    console.warn('⚠️ Не удалось загрузить агента:', agentId);
                    return { success: false, error: 'Agent not found' };
                }
                
                agentData = await response.json();
            }
            
            const childNodes = this.getChildNodes();
            
            // Для ReAct: обновляем tools из дочерних tool_node и agent_node
            if (agentData.type === 'react') {
                const toolRefs = [];
                
                childNodes.forEach(child => {
                    if (child.type === 'tool_node' && child.data.params?.tool_id) {
                        // Обычный тул
                        toolRefs.push({
                            tool_id: child.data.params.tool_id,
                            name: child.data.params.name
                        });
                    } else if (child.type === 'agent_node' && child.data.params?.agent_id) {
                        // Субагент - сохраняем с префиксом "agent:"
                        toolRefs.push({
                            tool_id: `agent:${child.data.params.agent_id}`,
                            name: child.data.params.name
                        });
                    }
                });
                
                agentData.tools = toolRefs;
                
                console.log(`   📋 Сохранено ${toolRefs.length} элементов (тулы + субагенты)`);
            }
            
            // Для StateGraph: собираем graph_definition из дочерних нод
            if (agentData.type === 'stategraph') {
                const childNodeIds = new Set(childNodes.map(n => n.id));
                
                const nodes = childNodes.map(child => ({
                    id: child.id,
                    type: child.type,
                    params: child.data.params || {}
                }));
                
                // Собираем связи между дочерними нодами
                const edges = [];
                this.canvas.connectionManager.getAllEdges().forEach(edge => {
                    if (childNodeIds.has(edge.source) && childNodeIds.has(edge.target)) {
                        edges.push({
                            id: edge.id,
                            source: edge.source,
                            target: edge.target
                        });
                    }
                });
                
                agentData.graph_definition = { nodes, edges };
                
                console.log(`   📊 Сохранено ${nodes.length} нод, ${edges.length} связей`);
                
                // Рекурсивно сохраняем вложенных агентов
                const nestedAgents = childNodes.filter(n => n.type === 'agent_node');
                for (const nestedAgent of nestedAgents) {
                    await nestedAgent.save();
                }
            }
            
            // Сохраняем агента
            const saveResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(agentId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(agentData)
            });
            
            if (!saveResponse.ok) {
                throw new Error(`HTTP ${saveResponse.status}`);
            }
            
            console.log('✅ Агент сохранен:', agentId);
            return { success: true };
            
        } catch (error) {
            console.error('❌ Ошибка сохранения агента:', error);
            return { success: false, error: error.message };
        }
    }
    
    /**
     * Обновление контента ноды (без перерисовки портов)
     */
    updateNodeContent() {
        if (!this.element) return;
        
        const name = this.agentData?.name || this.data.params?.name || 'Agent';
        const description = this.agentData?.description || this.data.params?.description || '';
        const agentType = this.agentData?.type || this.data.params?.type || 'unknown';
        
        console.log('🔄 updateNodeContent():', {
            'agentType': agentType,
            'agentData.type': this.agentData?.type,
            'params.type': this.data.params?.type,
            'name': name
        });
        
        const displayName = name.length > 30 ? name.substring(0, 27) + '...' : name;
        const displayDesc = description.length > 25 ? description.substring(0, 22) + '...' : description;
        
        const titleEl = this.element.querySelector('.node-simple-title');
        const descEl = this.element.querySelector('.node-simple-desc');
        const metaEl = this.element.querySelector('.node-simple-meta');
        
        if (titleEl) titleEl.textContent = displayName;
        if (descEl) descEl.textContent = displayDesc;
        if (metaEl) {
            metaEl.innerHTML = `<span class="agent-type-badge">${agentType}</span>`;
            console.log('✅ Бейдж типа обновлен:', agentType);
        } else {
            console.warn('⚠️ Не найден .node-simple-meta элемент');
        }
    }
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}


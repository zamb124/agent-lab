/**
 * Tools Manager
 */

export class ToolsManager {
    constructor(authToken) {
        this.authToken = authToken;
    }
    
    async loadTools() {
        const toolsSelector = document.getElementById('bot-tools-selector');
        if (!toolsSelector) {
            return;
        }
        
        try {
            const [publicToolsResponse, publicAgentsResponse] = await Promise.all([
                fetch('/frontend/api/tools/?public_only=true'),
                fetch('/frontend/api/agents/?public_only=true')
            ]);
            
            if (!publicToolsResponse.ok) {
                throw new Error('Не удалось загрузить список тулов');
            }
            
            const publicTools = await publicToolsResponse.json();
            const publicAgents = publicAgentsResponse.ok ? await publicAgentsResponse.json() : [];
            
            const flowIdElement = document.querySelector('[data-flow-id]');
            const flowId = flowIdElement?.dataset?.flowId;
            let agentTools = [];
            let selectedToolIds = [];
            
            if (flowId && flowId !== 'new') {
                const entryPointElement = document.querySelector('[data-entry-point]');
                const entryPoint = entryPointElement?.dataset?.entryPoint;
                
                if (entryPoint) {
                    try {
                        const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`);
                        if (agentResponse.ok) {
                            const agentData = await agentResponse.json();
                            agentTools = agentData.tools || [];
                            selectedToolIds = agentTools.map(t => t.tool_id);
                        }
                    } catch (error) {
                        console.error('Не удалось загрузить текущие тулы агента:', error);
                    }
                }
            }
            
            const toolsMap = new Map();
            
            publicTools.forEach(tool => {
                toolsMap.set(tool.id, {
                    ...tool,
                    type: 'tool'
                });
            });
            
            publicAgents.forEach(agent => {
                const agentId = `agent:${agent.agent_id}`;
                toolsMap.set(agentId, {
                    id: agentId,
                    name: agent.name,
                    title: agent.title || agent.name,
                    description: agent.description || 'Агент как инструмент',
                    cost: 0,
                    is_public: true,
                    type: 'agent'
                });
            });
            
            for (const agentTool of agentTools) {
                if (!toolsMap.has(agentTool.tool_id)) {
                    try {
                        const toolResponse = await fetch(`/frontend/api/tools/${encodeURIComponent(agentTool.tool_id)}`);
                        if (toolResponse.ok) {
                            const toolData = await toolResponse.json();
                            toolsMap.set(agentTool.tool_id, {
                                id: toolData.id,
                                name: toolData.name,
                                title: toolData.title || toolData.name,
                                description: toolData.description || 'Уже добавленная функция',
                                cost: toolData.cost || 0,
                                is_public: false
                            });
                        } else {
                            toolsMap.set(agentTool.tool_id, {
                                id: agentTool.tool_id,
                                name: agentTool.tool_id.split('.').pop(),
                                title: agentTool.title || agentTool.tool_id.split('.').pop(),
                                description: agentTool.description || 'Уже добавленная функция',
                                cost: agentTool.cost || 0,
                                is_public: false
                            });
                        }
                    } catch (error) {
                        console.warn(`Не удалось загрузить информацию о туле ${agentTool.tool_id}:`, error);
                        toolsMap.set(agentTool.tool_id, {
                            id: agentTool.tool_id,
                            name: agentTool.tool_id.split('.').pop(),
                            title: agentTool.title || agentTool.tool_id.split('.').pop(),
                            description: agentTool.description || 'Уже добавленная функция',
                            cost: agentTool.cost || 0,
                            is_public: false
                        });
                    }
                }
            }
            
            if (toolsMap.size === 0) {
                toolsSelector.innerHTML = '<div class="tools-empty"><i class="bi bi-info-circle"></i> Нет доступных функций</div>';
                return;
            }
            
            const toolsList = document.createElement('div');
            toolsList.className = 'tools-list';
            
            Array.from(toolsMap.values()).forEach(tool => {
                const toolItem = document.createElement('div');
                toolItem.className = 'tool-item';
                
                const isChecked = selectedToolIds.includes(tool.id);
                const isNonPublic = !tool.is_public;
                const isAgent = tool.type === 'agent';
                const badge = isAgent 
                    ? '<span class="tool-type-badge agent">Агент</span>' 
                    : '<span class="tool-type-badge function">Функция</span>';
                const lockIcon = isNonPublic ? ' 🔒' : '';
                
                toolItem.innerHTML = `
                    <input type="checkbox" 
                           id="tool-${tool.id.replace(/\./g, '-').replace(/:/g, '-')}" 
                           data-tool-id="${tool.id}"
                           ${isChecked ? 'checked' : ''}>
                    <div class="tool-item-content">
                        <label class="tool-item-name" for="tool-${tool.id.replace(/\./g, '-').replace(/:/g, '-')}">
                            ${badge}
                            <span>${tool.title || tool.name}${lockIcon}</span>
                        </label>
                        ${tool.description ? `<div class="tool-item-description">${tool.description}</div>` : ''}
                        ${tool.cost > 0 ? `<div class="tool-item-cost">Стоимость: ${tool.cost} ₽</div>` : ''}
                    </div>
                `;
                
                toolsList.appendChild(toolItem);
            });
            
            toolsSelector.innerHTML = '';
            toolsSelector.appendChild(toolsList);
            
        } catch (error) {
            console.error('Ошибка загрузки тулов:', error);
            toolsSelector.innerHTML = '<div class="tools-empty"><i class="bi bi-exclamation-triangle"></i> Ошибка загрузки функций</div>';
        }
    }
}


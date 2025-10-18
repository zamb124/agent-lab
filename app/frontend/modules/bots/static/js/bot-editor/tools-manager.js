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
            toolsList.className = 'abilities-selector-grid';
            
            Array.from(toolsMap.values()).forEach(tool => {
                const toolItem = document.createElement('div');
                toolItem.className = 'ability-selector-card';
                
                const isChecked = selectedToolIds.includes(tool.id);
                const isNonPublic = !tool.is_public;
                const isAgent = tool.type === 'agent';
                const lockIcon = isNonPublic ? '<i class="bi bi-lock-fill"></i>' : '';
                
                const iconClass = isAgent ? 'agent-icon' : 'tool-icon';
                const iconName = isAgent ? 'bi-robot' : 'bi-tools';
                const badgeClass = isAgent ? 'agent-badge' : '';
                const badge = isAgent ? `<div class="ability-badge ${badgeClass}">${tool.type || 'agent'}</div>` : '';
                const costBadge = tool.cost > 0 ? `<div class="ability-badge cost-badge">${tool.cost} ₽</div>` : '';
                
                toolItem.innerHTML = `
                    <input type="checkbox" 
                           class="ability-selector-checkbox"
                           id="tool-${tool.id.replace(/\./g, '-').replace(/:/g, '-')}" 
                           data-tool-id="${tool.id}"
                           ${isChecked ? 'checked' : ''}>
                    <label for="tool-${tool.id.replace(/\./g, '-').replace(/:/g, '-')}" class="ability-selector-label">
                        <div class="ability-card-header">
                            <div class="ability-icon ${iconClass}">
                                <i class="bi ${iconName}"></i>
                            </div>
                            <div class="ability-header-right">
                                <div class="ability-selector-check">
                                    <i class="bi bi-check-circle-fill"></i>
                                </div>
                                <div class="ability-badges">
                                    ${badge}
                                    ${costBadge}
                                </div>
                            </div>
                        </div>
                        
                        <div class="ability-card-body">
                            <h4 class="ability-name">
                                ${tool.title || tool.name}
                                ${lockIcon}
                            </h4>
                            ${tool.description ? `<p class="ability-description" title="${tool.description}">${tool.description}</p>` : ''}
                        </div>
                    </label>
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


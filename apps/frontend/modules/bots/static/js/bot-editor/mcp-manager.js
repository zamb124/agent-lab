/**
 * MCP Manager - управление MCP инструментами в боте
 */

export class MCPManager {
    constructor(authToken) {
        this.authToken = authToken;
    }
    
    async loadMCPTools() {
        const mcpSelector = document.getElementById('bot-mcp-selector');
        if (!mcpSelector) {
            return;
        }
        
        try {
            const serversResponse = await fetch('/frontend/api/mcp/servers', {
                headers: {
                    'Authorization': `Bearer ${this.authToken}`
                }
            });
            
            if (!serversResponse.ok) {
                throw new Error('Не удалось загрузить список MCP серверов');
            }
            
            const servers = await serversResponse.json();
            
            if (!servers || servers.length === 0) {
                mcpSelector.innerHTML = `
                    <div class="mcp-empty">
                        <i class="ti ti-info-circle"></i> 
                        <p>MCP серверы не настроены.</p>
                        <p><a href="/frontend/mcp/" class="btn btn-primary btn-sm">Настроить MCP</a></p>
                    </div>
                `;
                return;
            }

            const flowIdElement = document.querySelector('[data-flow-id]');
            const flowId = flowIdElement?.dataset?.flowId;
            let selectedMcpTools = [];
            
            if (flowId && flowId !== 'new') {
                const entryPointElement = document.querySelector('[data-entry-point]');
                const entryPoint = entryPointElement?.dataset?.entryPoint;
                
                if (entryPoint) {
                    try {
                        const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`);
                        if (agentResponse.ok) {
                            const agentData = await agentResponse.json();
                            const agentTools = agentData.tools || [];
                            selectedMcpTools = agentTools
                                .filter(t => t.tool_id.startsWith('mcp:'))
                                .map(t => t.tool_id);
                        }
                    } catch (error) {
                        console.error('Не удалось загрузить текущие MCP тулы агента:', error);
                    }
                }
            }
            
            const container = document.createElement('div');
            container.className = 'mcp-container';

            for (const server of servers) {
                if (!server.cached_tools || server.cached_tools.length === 0) {
                    continue;
                }

                const serverSection = document.createElement('div');
                serverSection.className = 'mcp-server-section';

                const serverHeader = document.createElement('div');
                serverHeader.className = 'mcp-server-header';
                
                const statusIcon = server.is_active
                    ? '<i class="ti ti-check-circle-fill text-success"></i>'
                    : '<i class="ti ti-x-circle-fill text-danger"></i>';

                serverHeader.innerHTML = `
                    <div class="mcp-server-title">
                        ${statusIcon}
                        <h5>${server.name}</h5>
                        <span class="mcp-server-count">${server.cached_tools.length} инструментов</span>
                    </div>
                `;

                serverSection.appendChild(serverHeader);

                const toolsGrid = document.createElement('div');
                toolsGrid.className = 'mcp-tools-grid';

                for (const toolId of server.cached_tools) {
                    const toolName = toolId.replace(/^mcp:.*?:/, '');
                    const mcpToolId = toolId;
                    const isChecked = selectedMcpTools.includes(mcpToolId);

                    const toolCard = document.createElement('div');
                    toolCard.className = 'mcp-tool-card';

                    toolCard.innerHTML = `
                        <input type="checkbox"
                               class="mcp-tool-checkbox"
                               id="mcp-tool-${server.server_id}-${toolName.replace(/\./g, '-')}"
                               data-mcp-tool-id="${mcpToolId}"
                               data-server-name="${server.name}"
                               data-tool-name="${toolName}"
                               ${isChecked ? 'checked' : ''}>
                        <label for="mcp-tool-${server.server_id}-${toolName.replace(/\./g, '-')}" class="mcp-tool-label">
                            <div class="mcp-tool-header">
                                <div class="mcp-tool-icon">
                                    <i class="ti ti-plugin"></i>
                                </div>
                                <div class="mcp-tool-check">
                                    <i class="ti ti-check-circle-fill"></i>
                                </div>
                            </div>
                            
                            <div class="mcp-tool-body">
                                <h4 class="mcp-tool-name">${toolName}</h4>
                                <div class="mcp-tool-server-tag">${server.name}</div>
                            </div>
                        </label>
                    `;

                    const checkbox = toolCard.querySelector('.mcp-tool-checkbox');
                    const label = toolCard.querySelector('.mcp-tool-label');

                    const syncCheckedState = () => {
                        if (checkbox && label) {
                            if (checkbox.checked) {
                                label.classList.add('checked');
                            } else {
                                label.classList.remove('checked');
                            }
                        }
                    };

                    checkbox.addEventListener('change', syncCheckedState);
                    syncCheckedState();

                    toolsGrid.appendChild(toolCard);
                }

                serverSection.appendChild(toolsGrid);
                container.appendChild(serverSection);
            }

            mcpSelector.innerHTML = '';
            mcpSelector.appendChild(container);
            
        } catch (error) {
            console.error('Ошибка загрузки MCP инструментов:', error);
            mcpSelector.innerHTML = `
                <div class="mcp-empty">
                    <i class="ti ti-exclamation-triangle"></i> 
                    Ошибка загрузки MCP инструментов
                </div>
            `;
        }
    }
}


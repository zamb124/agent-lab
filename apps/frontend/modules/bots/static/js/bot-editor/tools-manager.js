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
                toolsSelector.innerHTML = '<div class="tools-empty"><i class="ti ti-info-circle"></i> Нет доступных функций</div>';
                return;
            }

            // Группируем тулы по группам
            const groupedTools = new Map();
            const ungroupedTools = [];

            Array.from(toolsMap.values()).forEach(tool => {
                if (tool.group) {
                    if (!groupedTools.has(tool.group)) {
                        groupedTools.set(tool.group, []);
                    }
                    groupedTools.get(tool.group).push(tool);
                } else {
                    ungroupedTools.push(tool);
                }
            });

            const container = document.createElement('div');
            container.className = 'tools-container';

            // Секция "Способности" (группы)
            if (groupedTools.size > 0) {
                const abilitiesSection = document.createElement('div');
                abilitiesSection.className = 'tools-section';
                abilitiesSection.innerHTML = '<h4 class="tools-section-title"><i class="ti ti-apps"></i> Способности</h4>';

                const abilitiesGrid = document.createElement('div');
                abilitiesGrid.className = 'abilities-grid';

                Array.from(groupedTools.entries()).forEach(([groupName, tools]) => {
                    const groupCard = document.createElement('div');
                    groupCard.className = 'ability-group-card';

                    const toolCount = tools.length;
                    const selectedCount = tools.filter(t => selectedToolIds.includes(t.id)).length;
                    const isFullySelected = selectedCount === toolCount;
                    const isPartiallySelected = selectedCount > 0 && selectedCount < toolCount;

                    // Добавляем класс selected если группа выбрана
                    if (isFullySelected) {
                        groupCard.classList.add('selected');
                    }

                    // Переводим название группы через i18n
                    const translatedGroupName = app.i18n.t(`abilities.groups.${groupName}`, groupName);

                    // Создаем индикатор состояния группы
                    let indicatorElement = null;
                    if (isFullySelected) {
                        indicatorElement = document.createElement('i');
                        indicatorElement.className = 'ti ti-check';
                    } else if (isPartiallySelected) {
                        indicatorElement = document.createElement('div');
                        indicatorElement.className = 'partial-indicator';
                        indicatorElement.textContent = '●';
                    }

                    groupCard.innerHTML = `
                        <div class="ability-group-header">
                            <div class="ability-group-icon">
                                <i class="ti ti-apps"></i>
                            </div>
                            <div class="ability-group-info">
                                <h5 class="ability-group-name">${translatedGroupName}</h5>
                                <span class="ability-group-count">${toolCount} функций</span>
                            </div>
                            <div class="ability-group-selector">
                                <input type="checkbox"
                                       class="ability-group-checkbox"
                                       id="group-${groupName.replace(/\s+/g, '-').toLowerCase()}"
                                       ${isFullySelected ? 'checked' : ''}
                                       ${isPartiallySelected ? 'data-partial="true"' : ''}>
                                <label for="group-${groupName.replace(/\s+/g, '-').toLowerCase()}" class="ability-group-label">
                                    <div class="ability-group-check">
                                    </div>
                                </label>
                            </div>
                        </div>
                        <div class="ability-group-description">
                            ${tools.slice(0, 3).map(t => t.title || t.name).join(', ')}${toolCount > 3 ? '...' : ''}
                        </div>
                    `;

                    // Добавляем индикатор в DOM
                    if (indicatorElement) {
                        const checkDiv = groupCard.querySelector('.ability-group-check');
                        if (checkDiv) {
                            checkDiv.appendChild(indicatorElement);
                        }
                    }

                    // Синхронизируем CSS класс с состоянием чекбокса
                    const groupCheckbox = groupCard.querySelector('.ability-group-checkbox');
                    const groupLabel = groupCard.querySelector('.ability-group-label');

                    const syncGroupCheckedState = () => {
                        if (groupCheckbox && groupLabel) {
                            if (groupCheckbox.checked) {
                                groupLabel.classList.add('checked');
                            } else {
                                groupLabel.classList.remove('checked');
                            }
                        }
                    };

                    // Инициализируем состояние
                    syncGroupCheckedState();

                    // Обработчик клика по группе
                    const checkbox = groupCheckbox;
                    const label = groupLabel;

                    const toggleGroup = () => {
                        const isChecked = checkbox.checked;
                        syncGroupCheckedState(); // Синхронизируем CSS класс
                        tools.forEach(tool => {
                            const toolCheckbox = document.getElementById(`tool-${tool.id.replace(/\./g, '-').replace(/:/g, '-')}`);
                            if (toolCheckbox) {
                                toolCheckbox.checked = isChecked;
                                toolCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
                            }
                        });
                        updateGroupState(groupName, tools);
                    };

                    // Обработчик клика по всей карточке
                    groupCard.addEventListener('click', (e) => {
                        if (e.target !== checkbox && !checkbox.contains(e.target)) {
                            checkbox.checked = !checkbox.checked;
                            toggleGroup();
                        }
                    });

                    checkbox.addEventListener('change', toggleGroup);
                    checkbox.addEventListener('change', syncGroupCheckedState); // Синхронизируем при программном изменении

                    abilitiesGrid.appendChild(groupCard);
                });

                abilitiesSection.appendChild(abilitiesGrid);
                container.appendChild(abilitiesSection);
            }

            // Секция "Все Инструменты" (отдельные тулы)
            const allToolsSection = document.createElement('div');
            allToolsSection.className = 'tools-section';
            allToolsSection.innerHTML = '<h4 class="tools-section-title"><i class="ti ti-list"></i> Все Инструменты</h4>';

            const toolsList = document.createElement('div');
            toolsList.className = 'abilities-selector-grid';

            Array.from(toolsMap.values()).forEach(tool => {
                const toolItem = document.createElement('div');
                toolItem.className = 'ability-selector-card';

                const isChecked = selectedToolIds.includes(tool.id);
                const isNonPublic = !tool.is_public;
                const isAgent = tool.type === 'agent';
                const lockIcon = isNonPublic ? '<i class="ti ti-lock-fill"></i>' : '';

                const iconClass = isAgent ? 'agent-icon' : 'tool-icon';
                const iconName = isAgent ? 'robot' : 'tools';
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
                                <i class="ti ti-${iconName}"></i>
                            </div>
                            <div class="ability-header-right">
                                <div class="ability-selector-check">
                                    <i class="ti ti-check"></i>
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
                            ${tool.group ? `<div class="ability-group-tag">${tool.group}</div>` : ''}
                        </div>
                    </label>
                `;

                // Синхронизируем CSS класс с состоянием чекбокса
                const toolCheckbox = toolItem.querySelector('.ability-selector-checkbox');
                const toolLabelElement = toolItem.querySelector('.ability-selector-label');

                const syncCheckedState = () => {
                    if (toolCheckbox && toolLabelElement) {
                        if (toolCheckbox.checked) {
                            toolLabelElement.classList.add('checked');
                        } else {
                            toolLabelElement.classList.remove('checked');
                        }
                    }
                };

                // Синхронизируем при изменении чекбокса (включая клики по label)
                toolCheckbox.addEventListener('change', syncCheckedState);

                // Инициализируем начальное состояние
                syncCheckedState();

                toolsList.appendChild(toolItem);
            });

            allToolsSection.appendChild(toolsList);
            container.appendChild(allToolsSection);

            toolsSelector.innerHTML = '';
            toolsSelector.appendChild(container);

            // Функция обновления состояния группы
            function updateGroupState(groupName, tools) {
                const groupCheckbox = document.getElementById(`group-${groupName.replace(/\s+/g, '-').toLowerCase()}`);
                if (!groupCheckbox) return;

                const selectedCount = tools.filter(t => {
                    const toolCheckbox = document.getElementById(`tool-${t.id.replace(/\./g, '-').replace(/:/g, '-')}`);
                    return toolCheckbox && toolCheckbox.checked;
                }).length;

                const isFullySelected = selectedCount === tools.length;
                const isPartiallySelected = selectedCount > 0 && selectedCount < tools.length;

                groupCheckbox.checked = isFullySelected;
                groupCheckbox.setAttribute('data-partial', isPartiallySelected ? 'true' : 'false');

                // Обновляем иконку состояния группы
                const groupCheckElement = groupCheckbox.parentElement.querySelector('.ability-group-check');
                if (groupCheckElement) {
                    // Очищаем старое содержимое
                    groupCheckElement.innerHTML = '';

                    if (isFullySelected) {
                        const checkIcon = document.createElement('i');
                        checkIcon.className = 'ti ti-check-circle-fill';
                        groupCheckElement.appendChild(checkIcon);
                    } else if (isPartiallySelected) {
                        const partialDiv = document.createElement('div');
                        partialDiv.className = 'partial-indicator';
                        partialDiv.textContent = '●';
                        groupCheckElement.appendChild(partialDiv);
                    }
                }

                // Обновляем класс selected на карточке группы
                const groupCard = groupCheckbox.closest('.ability-group-card');
                if (groupCard) {
                    if (isFullySelected) {
                        groupCard.classList.add('selected');
                    } else {
                        groupCard.classList.remove('selected');
                    }

                    // Синхронизируем CSS класс для чекбокса
                    const groupLabel = groupCard.querySelector('.ability-group-label');
                    if (groupLabel) {
                        if (groupCheckbox.checked) {
                            groupLabel.classList.add('checked');
                        } else {
                            groupLabel.classList.remove('checked');
                        }
                    }
                }
            }

            // Обновляем состояния групп при изменении отдельных тулов
            document.addEventListener('change', (e) => {
                if (e.target.classList.contains('ability-selector-checkbox')) {
                    Array.from(groupedTools.entries()).forEach(([groupName, tools]) => {
                        updateGroupState(groupName, tools);
                    });
                }
            });
            
        } catch (error) {
            console.error('Ошибка загрузки тулов:', error);
            toolsSelector.innerHTML = '<div class="tools-empty"><i class="ti ti-exclamation-triangle"></i> Ошибка загрузки функций</div>';
        }
    }
}


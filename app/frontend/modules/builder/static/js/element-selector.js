/**
 * Компонент для выбора типа элемента (новый/существующий) при drag & drop
 */

import { FlowLayoutManager } from './drag-drop.js';

export default class ElementSelector {
    constructor(builder) {
        this.builder = builder;
        this.currentModalId = null;
        this.currentMenuElement = null;
        this.currentModalElement = null;
        this.pendingDropData = null;
        this.pendingPosition = null;
        this.pendingEvent = null;
    }

    /**
     * Показать меню выбора типа элемента
     */
    async showTypeSelection(dropData, position, event) {
        return new Promise((resolve, reject) => {
            this.pendingDropData = dropData;
            this.pendingPosition = position;
            this.pendingEvent = event;
            this.resolvePromise = resolve;
            this.rejectPromise = reject;

            const { type } = dropData;
            const elementType = type; // Используем type напрямую как elementType

            // Создаем минималистичное контекстное меню
            const menuElement = document.createElement('div');
            menuElement.className = 'element-type-context-menu';
            menuElement.innerHTML = `
                <div class="menu-layout">
                    <div class="menu-icon-column">
                        <i class="bi ${this.getElementIcon(elementType)} menu-main-icon"></i>
                    </div>
                    <div class="menu-options-column">
                        <button class="context-menu-item" data-action="new">
                            <div class="menu-item-title">Новый</div>
                        </button>
                        <button class="context-menu-item" data-action="existing">
                            <div class="menu-item-title">Существующий</div>
                        </button>
                    </div>
                </div>
            `;

            // Позиционируем меню рядом с курсором
            // Используем координаты из события drop
            let screenX = event.clientX + 10; // Немного смещаем вправо
            let screenY = event.clientY + 10; // Немного смещаем вниз

            // Проверяем, не выходит ли меню за границы экрана
            const menuWidth = 280; // Примерная ширина меню
            const menuHeight = 120; // Примерная высота меню
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;

            // Если меню выходит за правый край, показываем слева от курсора
            if (screenX + menuWidth > viewportWidth) {
                screenX = event.clientX - menuWidth - 10;
            }

            // Если меню выходит за нижний край, показываем выше курсора
            if (screenY + menuHeight > viewportHeight) {
                screenY = event.clientY - menuHeight - 10;
            }

            menuElement.style.position = 'fixed';
            menuElement.style.left = Math.max(10, screenX) + 'px'; // Минимум 10px от края
            menuElement.style.top = Math.max(10, screenY) + 'px';  // Минимум 10px от края
            menuElement.style.zIndex = '10000';

            // Добавляем в DOM
            document.body.appendChild(menuElement);
            this.currentMenuElement = menuElement;

            // Настраиваем обработчики кликов
            this.setupTypeSelectionHandlers();

            // Обработчик клика вне меню для закрытия
            setTimeout(() => {
                document.addEventListener('click', this.handleOutsideClick.bind(this), { once: true });
            }, 10);
        });
    }

    /**
     * Настройка обработчиков для кнопок выбора типа
     */
    setupTypeSelectionHandlers() {
        if (!this.currentMenuElement) return;

        const buttons = this.currentMenuElement.querySelectorAll('.context-menu-item');
        buttons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = button.dataset.action;
                this.handleTypeSelection(action);
            });
        });
    }

    /**
     * Обработка выбора типа элемента
     */
    async handleTypeSelection(action) {
        console.log('handleTypeSelection called with action:', action);
        this.hideMenu();

        try {
            if (action === 'new') {
                console.log('Creating new element');
                // Создаем новый элемент
                await this.createNewElement();
                this.resolvePromise(true);
            } else if (action === 'existing') {
                console.log('Showing existing elements selector');
                // Показываем список существующих элементов
                await this.showExistingElementsSelector();
                this.resolvePromise(true);
            }
        } catch (error) {
            console.error('Ошибка при выборе типа элемента:', error);
            this.rejectPromise(error);
        }
    }

    /**
     * Создание нового элемента
     */
    async createNewElement() {
        const { dropData, position } = { dropData: this.pendingDropData, position: this.pendingPosition };

        console.log('Creating new element:', dropData);

        // Для агентов показываем меню выбора типа
        if (dropData.nodeType === 'agent_node' || dropData.type === 'agent' || dropData.type === 'agent_node') {
            await this.showAgentTypeSelector(position);
            return;
        }

        // Определяем, какой тип создания использовать
        if (dropData.nodeType) {
            // Это palette node (новый формат) - у него есть nodeType
            await this.builder.dragDrop.createNodeFromPalette(dropData.nodeType, position);
        } else {
            // Старый формат (из сайдбара)
            switch (dropData.type) {
                case 'tool':
                case 'tool_node':
                    await this.builder.dragDrop.createToolNode(dropData.data, position);
                    break;
                case 'flow':
                case 'flow_node':
                    await this.builder.dragDrop.createFlowWithExpansion(dropData.data, position);
                    break;
                default:
                    console.warn('Неизвестный тип элемента для создания:', dropData.type);
            }
        }
    }

    /**
     * Показать меню выбора типа агента
     */
    async showAgentTypeSelector(position) {
        return new Promise((resolve, reject) => {
            this.pendingAgentTypePosition = position;
            this.resolveAgentTypePromise = resolve;
            this.rejectAgentTypePromise = reject;

            const menuElement = document.createElement('div');
            menuElement.className = 'agent-type-context-menu';
            menuElement.innerHTML = `
                <div class="menu-layout">
                    <div class="menu-icon-column">
                        <i class="bi bi-robot menu-main-icon"></i>
                    </div>
                    <div class="menu-options-column">
                        <button class="context-menu-item" data-action="react">
                            <div class="menu-item-title">React Agent</div>
                            <div class="menu-item-description">Агент с инструментами для выполнения задач</div>
                        </button>
                        <button class="context-menu-item" data-action="stategraph">
                            <div class="menu-item-title">StateGraph Agent</div>
                            <div class="menu-item-description">Агент с графом состояний для сложных сценариев</div>
                        </button>
                    </div>
                </div>
            `;

            // Позиционируем меню рядом с курсором
            let screenX = this.pendingEvent.clientX + 10;
            let screenY = this.pendingEvent.clientY + 10;

            const menuWidth = 280;
            const menuHeight = 120;
            const viewportWidth = window.innerWidth;
            const viewportHeight = window.innerHeight;

            if (screenX + menuWidth > viewportWidth) {
                screenX = this.pendingEvent.clientX - menuWidth - 10;
            }
            if (screenY + menuHeight > viewportHeight) {
                screenY = this.pendingEvent.clientY - menuHeight - 10;
            }

            menuElement.style.position = 'fixed';
            menuElement.style.left = Math.max(10, screenX) + 'px';
            menuElement.style.top = Math.max(10, screenY) + 'px';
            menuElement.style.zIndex = '10000';

            document.body.appendChild(menuElement);
            this.currentAgentTypeMenuElement = menuElement;

            this.setupAgentTypeSelectionHandlers();

            setTimeout(() => {
                document.addEventListener('click', this.handleOutsideAgentTypeMenuClick.bind(this), { once: true });
            }, 10);
        });
    }

    /**
     * Настройка обработчиков для выбора типа агента
     */
    setupAgentTypeSelectionHandlers() {
        if (!this.currentAgentTypeMenuElement) return;

        const buttons = this.currentAgentTypeMenuElement.querySelectorAll('.context-menu-item');
        buttons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = button.dataset.action;
                this.handleAgentTypeSelection(action);
            });
        });
    }

    /**
     * Обработка выбора типа агента
     */
    async handleAgentTypeSelection(agentType) {
        console.log('Selected agent type:', agentType);
        this.hideAgentTypeMenu();

        try {
            // Создаем агента выбранного типа
            await this.createAgentOfType(agentType, this.pendingAgentTypePosition);
            this.resolvePromise(true);
            if (this.resolveAgentTypePromise) {
                this.resolveAgentTypePromise(true);
            }
        } catch (error) {
            console.error('Ошибка создания агента:', error);
            if (this.rejectAgentTypePromise) {
                this.rejectAgentTypePromise(error);
            }
            this.rejectPromise(error);
        }
    }

    /**
     * Создание агента выбранного типа
     */
    async createAgentOfType(agentType, position) {
        console.log('Creating agent of type:', agentType, 'at position:', position);

        try {
            const requestData = {
                agent_type: agentType,
                name: agentType === 'react' ? 'Новый React Agent' : 'Новый StateGraph Agent',
                description: agentType === 'react' ? 'Агент с инструментами для выполнения задач' : 'Агент с графом состояний для сложных сценариев'
            };

            console.log('📤 Отправляем в API:', requestData);

            // Создаем агента через API с указанием типа
            const response = await fetch('/frontend/api/agents/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(requestData)
            });

            if (!response.ok) throw new Error('Ошибка создания агента');

            const agentData = await response.json();
            console.log('🤖 Создан агент через API:', agentData);
            console.log('🏷️ Тип агента из API:', agentData.type);

            // Создаем ноду на канвасе
            const nodeData = {
                id: `agent_${agentData.agent_id}_${Date.now()}`,
                type: 'agent_node',
                params: {
                    name: agentData.name,
                    agent_id: agentData.agent_id,
                    description: agentData.description,
                    type: agentType
                },
                ui: {
                    x: position.x,
                    y: position.y,
                    width: 180,
                    height: 80
                }
            };

            await this.builder.canvas.addNode(nodeData);

            const typeName = agentType === 'react' ? 'React Agent' : 'StateGraph Agent';
            this.builder.showNotification(`${typeName} "${agentData.name}" добавлен на канвас`, 'success');

        } catch (error) {
            console.error('Ошибка создания агента типа', agentType, ':', error);
            throw error;
        }
    }

    /**
     * Скрытие меню выбора типа агента
     */
    hideAgentTypeMenu() {
        if (this.currentAgentTypeMenuElement) {
            if (document.body.contains(this.currentAgentTypeMenuElement)) {
                document.body.removeChild(this.currentAgentTypeMenuElement);
            }
            this.currentAgentTypeMenuElement = null;
        }
    }

    /**
     * Обработчик клика вне меню выбора типа агента
     */
    handleOutsideAgentTypeMenuClick(event) {
        if (this.currentAgentTypeMenuElement && !this.currentAgentTypeMenuElement.contains(event.target)) {
            this.hideAgentTypeMenu();
            if (this.rejectAgentTypePromise) {
                this.rejectAgentTypePromise(new Error('Меню выбора типа агента закрыто без выбора'));
            }
        }
    }

    /**
     * Показать селектор существующих элементов
     */
    async showExistingElementsSelector() {
        const { dropData, position } = { dropData: this.pendingDropData, position: this.pendingPosition };
        const { type } = dropData;

        console.log('showExistingElementsSelector called with type:', type, 'dropData:', dropData);

        // Загружаем список существующих элементов
        let existingElements = [];
        let elementType = type;

        try {
            // Определяем тип элементов для загрузки
            if (type === 'palette_node' && dropData.nodeType) {
                // Элементы из palette - используем nodeType
                elementType = dropData.nodeType.replace('_node', '');
                console.log('Palette node, elementType:', elementType);
            } else if (type.includes('_node')) {
                // Новый формат (flow_node, agent_node, tool_node)
                elementType = type.replace('_node', '');
                console.log('Новый формат, elementType:', elementType);
            } else {
                // Старый формат или уже нормализованный
                console.log('Старый формат, elementType:', elementType);
            }

            // Загружаем элементы в зависимости от типа
            switch (elementType) {
                case 'flow':
                    existingElements = await this.loadExistingFlows();
                    break;
                case 'agent':
                    existingElements = await this.loadExistingAgents();
                    break;
                case 'tool':
                    existingElements = await this.loadExistingTools();
                    break;
                default:
                    console.warn('Неизвестный elementType:', elementType);
            }
        } catch (error) {
            console.error('Ошибка загрузки существующих элементов:', error);
            this.builder.showNotification('Ошибка загрузки списка элементов', 'error');
            return;
        }

        console.log('Загружено элементов:', existingElements.length, existingElements);
        this.showExistingElementsModal(existingElements, elementType, position);
    }

    /**
     * Загрузка существующих flows
     */
    async loadExistingFlows() {
        console.log('Загружаем flows...');
        const response = await fetch('/frontend/api/flows/');
        if (!response.ok) throw new Error('Не удалось загрузить flows');
        const flows = await response.json();
        console.log('Загружено flows:', flows);

        return flows.map(flow => ({
            id: flow.flow_id,
            name: flow.name,
            description: flow.description || '',
            type: 'flow'
        }));
    }

    /**
     * Загрузка существующих agents
     */
    async loadExistingAgents() {
        console.log('Загружаем agents...');
        const response = await fetch('/frontend/api/agents/');
        if (!response.ok) throw new Error('Не удалось загрузить agents');
        const agents = await response.json();
        console.log('Загружено agents:', agents);

        return agents.map(agent => ({
            id: agent.agent_id,
            name: agent.name,
            description: agent.description || '',
            type: 'agent'
        }));
    }

    /**
     * Загрузка существующих tools
     */
    async loadExistingTools() {
        console.log('Загружаем tools...');
        const response = await fetch('/frontend/api/tools/');
        if (!response.ok) throw new Error('Не удалось загрузить tools');
        const tools = await response.json();
        console.log('Загружено tools:', tools);

        return tools.map(tool => ({
            id: tool.id,
            name: tool.title || tool.name,
            description: tool.description || '',
            category: tool.category,
            code_mode: tool.code_mode,
            server: tool.server,
            group: tool.group,
            type: 'tool'
        }));
    }

    /**
     * Показать контекстное меню с выбором существующего элемента
     */
    showExistingElementsModal(elements, elementType, position) {
        const elementTypeName = this.getElementTypeName(elementType);

        // Создаем контекстное меню для выбора элементов
        const menuElement = document.createElement('div');
        menuElement.className = 'existing-elements-context-menu';

        const maxHeight = elements.length > 5 ? '300px' : 'auto';

        menuElement.innerHTML = `
            <div class="search-container">
                <div class="search-input-wrapper">
                    <i class="bi bi-search"></i>
                    <input type="text" class="search-input" placeholder="Поиск..." id="elementSearch">
                </div>
                ${elementType === 'tool' ? `
                    <div class="filter-badges">
                        <button class="filter-badge active" data-filter="all">
                            <i class="bi bi-list"></i> Все
                        </button>
                        <button class="filter-badge" data-filter="tools">
                            <i class="bi bi-tools"></i> Tools
                        </button>
                        <button class="filter-badge" data-filter="mcp">
                            <i class="bi bi-plugin"></i> MCP
                        </button>
                    </div>
                ` : ''}
            </div>

            <div class="elements-list" id="elementsList" style="max-height: ${maxHeight}; overflow-y: auto;">
                ${elements.map(element => `
                    <div class="element-item" 
                         data-element-id="${element.id}" 
                         data-element-type="${element.type}"
                         data-code-mode="${element.code_mode || ''}"
                         data-group="${element.group || ''}"
                         data-server="${element.server || ''}"
                         data-is-mcp="${element.code_mode === 'mcp_tool' || element.server ? 'true' : 'false'}">
                        <div class="element-icon">
                            <i class="bi ${this.getElementIcon(element.type)}"></i>
                        </div>
                        <div class="element-info">
                            <div class="element-name">
                                ${element.name}
                                ${element.code_mode === 'mcp_tool' || element.server ? '<span class="badge badge-mcp">MCP</span>' : ''}
                            </div>
                            <div class="element-description">${element.description || ''}</div>
                            ${element.category ? `<div class="element-category"><i class="bi bi-folder"></i> ${element.category}</div>` : ''}
                            ${element.group ? `<div class="element-group"><i class="bi bi-collection"></i> ${element.group}</div>` : ''}
                            ${element.server ? `<div class="element-server"><i class="bi bi-server"></i> ${element.server}</div>` : ''}
                        </div>
                    </div>
                `).join('')}
            </div>

            ${elements.length === 0 ? `
                <div class="no-elements">
                    <i class="bi bi-inbox"></i>
                    <p>Нет доступных ${elementTypeName}ов</p>
                </div>
            ` : ''}
        `;

        // Позиционируем меню рядом с предыдущим меню или курсором
        const canvasContainer = document.getElementById('canvasContainer');
        const rect = canvasContainer.getBoundingClientRect();

        // Используем позицию из drop события (нужно передать event)
        const event = this.pendingEvent || { clientX: rect.left + position.x, clientY: rect.top + position.y };
        let screenX = event.clientX + 20; // Смещаем правее предыдущего меню
        let screenY = event.clientY + 10;

        // Проверяем границы экрана
        const menuWidth = 320;
        const menuHeight = Math.min(400, elements.length * 60 + 120);
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;

        if (screenX + menuWidth > viewportWidth) {
            screenX = event.clientX - menuWidth - 20;
        }
        if (screenY + menuHeight > viewportHeight) {
            screenY = event.clientY - menuHeight - 10;
        }

        menuElement.style.position = 'fixed';
        menuElement.style.left = Math.max(10, screenX) + 'px';
        menuElement.style.top = Math.max(10, screenY) + 'px';
        menuElement.style.zIndex = '10001'; // Выше основного меню

        // Добавляем в DOM
        document.body.appendChild(menuElement);
        this.currentModalElement = menuElement; // Используем другое имя, чтобы не путать с основным меню

        // Настраиваем поиск и обработчики выбора
        this.setupExistingElementsHandlers(position);
    }

    /**
     * Настройка обработчиков для выбора существующего элемента
     */
    setupExistingElementsHandlers(position) {
        if (!this.currentModalElement) return;

        // Поиск
        const searchInput = this.currentModalElement.querySelector('#elementSearch');
        const elementsList = this.currentModalElement.querySelector('#elementsList');

        searchInput.addEventListener('input', (e) => {
            const searchTerm = e.target.value.toLowerCase();
            const items = elementsList.querySelectorAll('.element-item');

            items.forEach(item => {
                const name = item.querySelector('.element-name').textContent.toLowerCase();
                const description = item.querySelector('.element-description').textContent.toLowerCase();
                const group = item.dataset.group || '';
                const server = item.dataset.server || '';

                if (name.includes(searchTerm) || 
                    description.includes(searchTerm) || 
                    group.toLowerCase().includes(searchTerm) ||
                    server.toLowerCase().includes(searchTerm) ||
                    (searchTerm === 'mcp' && item.dataset.isMcp === 'true')) {
                    item.style.display = '';
                } else {
                    item.style.display = 'none';
                }
            });
        });
        
        // Фильтры (для тулов)
        const filterBadges = this.currentModalElement.querySelectorAll('.filter-badge');
        filterBadges.forEach(badge => {
            badge.addEventListener('click', (e) => {
                e.stopPropagation();
                const filter = badge.dataset.filter;
                
                // Обновляем активный фильтр
                filterBadges.forEach(b => b.classList.remove('active'));
                badge.classList.add('active');
                
                // Фильтруем элементы
                const items = elementsList.querySelectorAll('.element-item');
                items.forEach(item => {
                    if (filter === 'all') {
                        item.style.display = '';
                    } else if (filter === 'mcp') {
                        item.style.display = item.dataset.isMcp === 'true' ? '' : 'none';
                    } else if (filter === 'tools') {
                        item.style.display = item.dataset.isMcp === 'false' ? '' : 'none';
                    }
                });
            });
        });

        // Выбор элемента
        const items = this.currentModalElement.querySelectorAll('.element-item');
        items.forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                const elementId = item.dataset.elementId;
                const elementType = item.dataset.elementType;
                this.handleExistingElementSelection(elementId, elementType, position);
            });
        });

        // Обработчик клика вне меню для закрытия
        setTimeout(() => {
            document.addEventListener('click', this.handleOutsideModalClick.bind(this), { once: true });
        }, 10);
    }

    /**
     * Обработка выбора существующего элемента
     */
    async handleExistingElementSelection(elementId, elementType, position) {
        this.hideMenu();

        try {
            // Получаем полные данные элемента и создаем ноду
            switch (elementType) {
                case 'flow':
                    await this.createExistingFlowNode(elementId, position);
                    break;
                case 'agent':
                    await this.createExistingAgentNode(elementId, position);
                    break;
                case 'tool':
                    await this.createExistingToolNode(elementId, position);
                    break;
            }
            this.resolvePromise(true);
        } catch (error) {
            console.error('Ошибка создания элемента:', error);
            this.builder.showNotification('Ошибка создания элемента', 'error');
            this.rejectPromise(error);
        }
    }

    /**
     * Создание ноды существующего flow
     */
    async createExistingFlowNode(flowId, position) {
        console.log('Creating existing flow node:', flowId, 'at position:', position);

        // Получаем данные flow
        const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
        if (!response.ok) throw new Error('Не удалось получить данные flow');

        const flowData = await response.json();
        console.log('Flow data loaded:', flowData);

        // Создаем основную ноду flow
        const flowNodeData = {
            id: `flow_${flowId}_${Date.now()}`,
            type: 'flow_node',
            params: {
                name: flowData.name,
                flow_id: flowId,
                isEntryPoint: true
            },
            ui: {
                x: position.x,
                y: position.y,
                width: 180,
                height: 80
            }
        };

        const flowNode = await this.builder.canvas.addNode(flowNodeData);
        console.log('Flow node created:', flowNode);

        // Сохраняем полные данные flow
        if (!this.builder.currentFlow || this.builder.currentFlow.flow_id !== flowData.flow_id) {
            this.builder.currentFlow = flowData; // Сохраняем все данные, включая entry_point_agent
            this.builder.updateFlowInfo();
            this.builder.enableFlowActions();
        }
        
        // Обновляем тип entry_point агента и фильтруем палитру
        await this.builder.updateEntryPointAgentType();

        if (flowData.entry_point_agent) {
            console.log('Expanding flow recursively, entry_point_agent:', flowData.entry_point_agent);

            const layoutManager = new FlowLayoutManager();
            layoutManager.setBuilder(this.builder);

            // Проверяем, есть ли сохраненные позиции
            let shouldUseSavedPositions = false;
            if (flowData.canvas_data && flowData.canvas_data.nodes) {
                shouldUseSavedPositions = true;
                console.log('Using saved positions from canvas_data');
            }

            // Разворачиваем entry point agent из graph_definition с сохраненными позициями
            await this.builder.dragDrop.expandAgentRecursively(
                flowData.entry_point_agent,
                layoutManager.getNextPosition(position, 'agent', 0),
                flowNode.id,
                new Set(),
                layoutManager,
                0,
                shouldUseSavedPositions ? flowData.canvas_data : null
            );

            console.log('Flow expansion completed');

            // Подгоняем масштаб канваса
            setTimeout(() => this.builder.canvas.fitToScreen(), 500);
        } else {
            console.log('No entry_point_agent found in flow data');
        }

        this.builder.showNotification(`Flow "${flowData.name}" развернут на канве`, 'success');
    }

    /**
     * Создание ноды существующего agent
     */
    async createExistingAgentNode(agentId, position) {
        console.log('Creating existing agent node:', agentId, 'at position:', position);

        // Получаем данные агента
        const response = await fetch(`/frontend/api/agents/${encodeURIComponent(agentId)}`);
        if (!response.ok) throw new Error('Не удалось получить данные агента');

        const agentData = await response.json();
        console.log('Agent data loaded:', agentData);

        // Создаем ноду агента
        const nodeData = {
            id: `agent_${agentId}_${Date.now()}`,
            type: 'agent_node',
            params: {
                name: agentData.name,
                agent_id: agentId,
                description: agentData.description
            },
            ui: {
                x: position.x,
                y: position.y,
                width: 180,
                height: 80
            }
        };

        const agentNode = await this.builder.canvas.addNode(nodeData);
        console.log('Agent node created:', agentNode);

        // Разворачиваем тулы и субагенты этого агента
        console.log('Expanding agent tools for:', agentId);
        await this.builder.dragDrop.expandAgentTools(agentId, position, agentNode.id);

        this.builder.showNotification(`Агент "${agentData.name}" добавлен на канву`, 'success');
    }

    /**
     * Создание ноды существующего tool
     */
    async createExistingToolNode(toolId, position) {
        // Получаем данные тула
        const response = await fetch(`/frontend/api/tools/${encodeURIComponent(toolId)}`);
        if (!response.ok) throw new Error('Не удалось получить данные тула');

        const toolData = await response.json();

        // Создаем ноду
        const nodeData = {
            id: `tool_${toolId}_${Date.now()}`,
            type: 'tool_node',
            params: {
                name: toolData.title || toolData.name,
                tool_id: toolId,
                description: toolData.description,
                category: toolData.category
            },
            ui: {
                x: position.x,
                y: position.y,
                width: 180,
                height: 80
            }
        };

        await this.builder.canvas.addNode(nodeData);
        this.builder.showNotification(`Инструмент "${toolData.title || toolData.name}" добавлен на канву`, 'success');
    }

    /**
     * Получение названия типа элемента
     */
    getElementTypeName(type) {
        switch (type) {
            case 'flow':
            case 'flow_node':
            case 'palette_node':
                return 'Flow';
            case 'agent':
            case 'agent_node':
                return 'агента';
            case 'tool':
            case 'tool_node':
                return 'инструмент';
            case 'function_node':
                return 'функцию';
            case 'message_node':
                return 'сообщение';
            case 'router_node':
                return 'роутер';
            default:
                return 'элемент';
        }
    }

    /**
     * Получение иконки для типа элемента
     */
    getElementIcon(type) {
        switch (type) {
            case 'flow':
            case 'flow_node':
                return 'bi-diagram-3';
            case 'agent':
            case 'agent_node':
                return 'bi-robot';
            case 'tool':
            case 'tool_node':
                return 'bi-tools';
            case 'function_node':
                return 'bi-code-square';
            case 'message_node':
                return 'bi-chat-dots';
            case 'router_node':
                return 'bi-lightning';
            default:
                return 'bi-circle';
        }
    }

    /**
     * Скрытие меню выбора
     */
    hideMenu() {
        if (this.currentMenuElement) {
            if (document.body.contains(this.currentMenuElement)) {
                document.body.removeChild(this.currentMenuElement);
            }
            this.currentMenuElement = null;
        }
        if (this.currentModalElement) {
            if (document.body.contains(this.currentModalElement)) {
                document.body.removeChild(this.currentModalElement);
            }
            this.currentModalElement = null;
        }
        if (this.currentModalId) {
            window.modalManager.hide(this.currentModalId);
            this.currentModalId = null;
        }
    }

    /**
     * Обработчик клика вне меню
     */
    handleOutsideClick(event) {
        // Проверяем, был ли клик внутри меню
        if (this.currentMenuElement && !this.currentMenuElement.contains(event.target)) {
            this.hideMenu();
            // Отклоняем промис при закрытии меню без выбора
            if (this.rejectPromise) {
                this.rejectPromise(new Error('Меню закрыто без выбора'));
            }
        }
    }

    /**
     * Обработчик клика вне модального меню выбора элементов
     */
    handleOutsideModalClick(event) {
        // Проверяем, был ли клик внутри меню выбора элементов
        if (this.currentModalElement && !this.currentModalElement.contains(event.target)) {
            this.hideMenu();
            // Отклоняем промис при закрытии меню без выбора
            if (this.rejectPromise) {
                this.rejectPromise(new Error('Меню выбора элементов закрыто без выбора'));
            }
        }
    }

    /**
     * Обработчик закрытия модального окна
     */
    onModalClose() {
        this.currentModalId = null;
        this.pendingDropData = null;
        this.pendingPosition = null;

        // Отклоняем промис при закрытии окна без выбора
        if (this.rejectPromise) {
            this.rejectPromise(new Error('Модальное окно закрыто без выбора'));
        }
    }
}

// Экспортируем класс в глобальную область

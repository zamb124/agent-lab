import { EventEmitter } from '../core/EventEmitter.js';

/**
 * ElementSelector v3.0 - Менеджер выбора элементов при создании нод
 * Использует существующие стили из element-selector.css
 */
export class ElementSelector extends EventEmitter {
    constructor(canvas) {
        super();
        
        this.canvas = canvas;
        this.builder = canvas.builder;
        
        // Контекстное меню
        this.contextMenu = null;
        this.currentContext = null;
    }
    
    /**
     * Показать селектор для создания ноды
     */
    async showSelector(nodeType, position) {
        this.currentContext = { nodeType, position };
        
        console.log('🔍 ElementSelector: показываем селектор для', nodeType);
        
        // Показываем меню выбора: новый или существующий
        this.showTypeMenu(nodeType, position);
    }
    
    /**
     * Показать меню выбора типа (новый/существующий)
     */
    showTypeMenu(nodeType, position) {
        this.closeMenu();
        
        const iconMap = {
            'agent_node': 'bi-robot',
            'tool_node': 'bi-tools',
            'flow_node': 'bi-diagram-3'
        };
        
        const labelMap = {
            'agent_node': 'Agent',
            'tool_node': 'Tool',
            'flow_node': 'Flow'
        };
        
        const icon = iconMap[nodeType] || 'bi-square';
        const label = labelMap[nodeType] || 'Element';
        
        const html = `
            <div class="element-type-context-menu">
                <div class="menu-layout">
                    <div class="menu-icon-column">
                        <div class="menu-main-icon">
                            <i class="${icon}"></i>
                        </div>
                    </div>
                    <div class="menu-options-column">
                        <button class="context-menu-item" data-action="new">
                            <p class="menu-item-title">Создать новый</p>
                        </button>
                        <button class="context-menu-item" data-action="existing">
                            <p class="menu-item-title">Выбрать существующий</p>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        this.showContextMenu(html, position);
        
        // Обработчики кнопок
        const items = this.contextMenu.querySelectorAll('.context-menu-item');
        items.forEach(item => {
            item.addEventListener('click', async () => {
                const action = item.dataset.action;
                
                if (action === 'new') {
                    if (nodeType === 'agent_node') {
                        this.showNewAgentTypeMenu(position);
                    } else {
                        // Для tool и flow пока создаем простые
                        await this.createSimpleNode(nodeType, position);
                    }
                } else if (action === 'existing') {
                    this.showExistingElementsMenu(nodeType, position);
                }
            });
        });
    }
    
    /**
     * Показать меню выбора типа агента (ReAct/StateGraph)
     */
    showNewAgentTypeMenu(position) {
        this.closeMenu();
        
        const html = `
            <div class="element-type-context-menu">
                <div class="menu-layout">
                    <div class="menu-icon-column">
                        <div class="menu-main-icon">
                            <i class="bi-robot"></i>
                        </div>
                    </div>
                    <div class="menu-options-column">
                        <button class="context-menu-item" data-agent-type="react">
                            <p class="menu-item-title">ReAct Agent</p>
                        </button>
                        <button class="context-menu-item" data-agent-type="stategraph">
                            <p class="menu-item-title">StateGraph Agent</p>
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        this.showContextMenu(html, position);
        
        const items = this.contextMenu.querySelectorAll('.context-menu-item');
        items.forEach(item => {
            item.addEventListener('click', async () => {
                const agentType = item.dataset.agentType;
                await this.createNewAgent(agentType, position);
            });
        });
    }
    
    /**
     * Показать меню существующих элементов
     */
    async showExistingElementsMenu(nodeType, position) {
        this.closeMenu();
        
        const iconMap = {
            'agent_node': 'bi-robot',
            'tool_node': 'bi-tools',
            'flow_node': 'bi-diagram-3'
        };
        
        const labelMap = {
            'agent_node': 'агента',
            'tool_node': 'инструмент',
            'flow_node': 'flow'
        };
        
        const icon = iconMap[nodeType] || 'bi-square';
        const label = labelMap[nodeType] || 'элемент';
        
        // Для тулов добавляем фильтры
        const filtersHtml = nodeType === 'tool_node' ? `
            <div class="filter-badges">
                <button class="filter-badge active" data-filter="all">
                    <i class="bi bi-grid"></i>
                    <span>Все</span>
                </button>
                <button class="filter-badge" data-filter="tools">
                    <i class="bi bi-tools"></i>
                    <span>Tools</span>
                </button>
                <button class="filter-badge" data-filter="mcp">
                    <i class="bi bi-plugin"></i>
                    <span>MCP</span>
                </button>
            </div>
        ` : '';
        
        const html = `
            <div class="existing-elements-context-menu">
                <div class="search-container">
                    <div class="search-input-wrapper">
                        <i class="bi bi-search"></i>
                        <input type="text" 
                               class="search-input" 
                               placeholder="Поиск ${label}..." 
                               id="elementSearchInput">
                    </div>
                    ${filtersHtml}
                </div>
                <div class="elements-list" id="elementsList">
                    ${this.renderSkeletonLoader()}
                </div>
            </div>
        `;
        
        this.showContextMenu(html, position);
        
        // Настраиваем фильтры для тулов
        if (nodeType === 'tool_node') {
            this.setupFilters();
        }
        
        // Загружаем элементы
        if (nodeType === 'agent_node') {
            await this.loadAndRenderAgents();
        } else if (nodeType === 'tool_node') {
            await this.loadAndRenderTools();
        } else if (nodeType === 'flow_node') {
            await this.loadAndRenderFlows();
        }
    }
    
    /**
     * Рендеринг скелетона загрузки
     */
    renderSkeletonLoader() {
        return `
            <div class="skeleton-grid">
                ${Array(5).fill('').map(() => `
                    <div class="element-item skeleton-item">
                        <div class="element-icon skeleton skeleton-circle"></div>
                        <div class="element-info">
                            <div class="skeleton skeleton-text skeleton-width-60"></div>
                            <div class="skeleton skeleton-text skeleton-sm skeleton-width-40"></div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    }
    
    /**
     * Настройка фильтров
     */
    setupFilters() {
        const filterBadges = this.contextMenu.querySelectorAll('.filter-badge');
        
        filterBadges.forEach(badge => {
            badge.addEventListener('click', () => {
                const filter = badge.dataset.filter;
                
                filterBadges.forEach(b => b.classList.remove('active'));
                badge.classList.add('active');
                
                this.filterToolsByType(filter);
            });
        });
    }
    
    /**
     * Фильтрация тулов по типу
     */
    filterToolsByType(filter) {
        const items = this.contextMenu.querySelectorAll('.element-item');
        
        items.forEach(item => {
            const elementType = item.dataset.elementType;
            
            if (filter === 'all') {
                item.style.display = '';
            } else if (filter === 'mcp') {
                item.style.display = elementType === 'mcp' ? '' : 'none';
            } else if (filter === 'tools') {
                item.style.display = elementType === 'tool' ? '' : 'none';
            }
        });
    }
    
    /**
     * Загрузка и рендеринг агентов
     */
    async loadAndRenderAgents() {
        try {
            const response = await fetch('/frontend/api/agents/');
            if (!response.ok) throw new Error('Failed to load agents');
            
            const agents = await response.json();
            this.renderElements(agents, 'agent', (agent) => ({
                id: agent.agent_id,
                name: agent.name,
                icon: 'bi-robot',
                meta: agent.type,
                onClick: () => this.selectExistingAgent(agent.agent_id)
            }));
            
            this.setupSearch(agents, (agent, query) => 
                agent.name.toLowerCase().includes(query) || 
                agent.agent_id.toLowerCase().includes(query)
            );
        } catch (error) {
            console.error('❌ Ошибка загрузки агентов:', error);
            document.getElementById('elementsList').innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
        }
    }
    
    /**
     * Загрузка и рендеринг тулов
     */
    async loadAndRenderTools() {
        try {
            const response = await fetch('/frontend/api/tools/');
            if (!response.ok) throw new Error('Failed to load tools');
            
            const tools = await response.json();
            
            console.log('🔍 Загружено тулов:', tools.length);
            if (tools.length > 0) {
                console.log('🔍 Первый тул:', tools[0]);
                console.log('🔍 Ключи первого тула:', Object.keys(tools[0]));
                console.log('🔍 ID первого тула:', tools[0].tool_id, tools[0].id, tools[0].name);
            }
            
            // Рендерим тулы с группами и MCP badge
            this.renderToolsWithGroups(tools);
            
            console.log('🔍 Проверяем отрендеренные элементы:');
            const renderedItems = document.querySelectorAll('#elementsList .element-item');
            console.log('🔍 Количество элементов:', renderedItems.length);
            if (renderedItems.length > 0) {
                console.log('🔍 Первый элемент data-element-id:', renderedItems[0].dataset.elementId);
                console.log('🔍 Первый элемент data-tool-name:', renderedItems[0].dataset.toolName);
            }
            
            this.setupSearch(tools, (tool, query) => 
                (tool.name && tool.name.toLowerCase().includes(query)) || 
                (tool.tool_id && tool.tool_id.toLowerCase().includes(query)) ||
                (tool.description && tool.description.toLowerCase().includes(query)) ||
                (tool.group && tool.group.toLowerCase().includes(query))
            );
        } catch (error) {
            console.error('❌ Ошибка загрузки тулов:', error);
            document.getElementById('elementsList').innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
        }
    }
    
    /**
     * Рендеринг тулов с группами
     */
    renderToolsWithGroups(tools) {
        const container = document.getElementById('elementsList');
        
        if (tools.length === 0) {
            container.innerHTML = '<div class="empty-state">Нет инструментов</div>';
            return;
        }
        
        container.innerHTML = tools.map(tool => {
            const toolId = tool.tool_id || tool.id || tool.name;
            const isMcp = tool.server || tool.is_mcp;
            const mcpBadge = isMcp ? `<span class="badge-mcp">MCP</span>` : '';
            
            return `
                <div class="element-item" 
                     data-element-id="${toolId}" 
                     data-element-type="${isMcp ? 'mcp' : 'tool'}"
                     data-tool-name="${this.escapeHtml(tool.name)}">
                    <div class="element-icon">
                        <i class="bi-tools"></i>
                    </div>
                    <div class="element-info">
                        <p class="element-name">${this.escapeHtml(tool.name)}${mcpBadge}</p>
                        ${tool.description ? `<p class="element-desc">${this.escapeHtml(tool.description)}</p>` : ''}
                        ${tool.group ? `
                            <p class="element-group">
                                <i class="bi bi-folder"></i>
                                ${this.escapeHtml(tool.group)}
                            </p>
                        ` : ''}
                        ${isMcp && tool.server ? `
                            <p class="element-server">
                                <i class="bi bi-server"></i>
                                ${this.escapeHtml(tool.server)}
                            </p>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
        
        // Добавляем обработчики
        container.querySelectorAll('.element-item').forEach((el) => {
            el.addEventListener('click', () => {
                const toolId = el.dataset.elementId;
                const toolName = el.dataset.toolName;
                
                console.log('🖱️ Клик по тулу, ID:', toolId, 'Name:', toolName);
                
                if (!toolId || toolId === 'undefined') {
                    console.error('❌ toolId is undefined!', el);
                    return;
                }
                
                this.selectExistingTool(toolId, toolName);
            });
        });
    }
    
    /**
     * Загрузка и рендеринг flows
     */
    async loadAndRenderFlows() {
        try {
            const response = await fetch('/frontend/api/flows/');
            if (!response.ok) throw new Error('Failed to load flows');
            
            const flows = await response.json();
            this.renderElements(flows, 'flow', (flow) => ({
                id: flow.flow_id,
                name: flow.name,
                icon: 'bi-diagram-3',
                description: flow.description,
                onClick: () => this.selectExistingFlow(flow.flow_id)
            }));
            
            this.setupSearch(flows, (flow, query) => 
                flow.name.toLowerCase().includes(query) || 
                flow.flow_id.toLowerCase().includes(query)
            );
        } catch (error) {
            console.error('❌ Ошибка загрузки flows:', error);
            document.getElementById('elementsList').innerHTML = '<div class="empty-state">Ошибка загрузки</div>';
        }
    }
    
    /**
     * Универсальный рендеринг элементов
     */
    renderElements(items, type, mapFn) {
        const container = document.getElementById('elementsList');
        
        if (items.length === 0) {
            container.innerHTML = '<div class="empty-state">Нет элементов</div>';
            return;
        }
        
        const mapped = items.map(mapFn);
        
        container.innerHTML = mapped.map(item => `
            <div class="element-item" data-element-id="${item.id}">
                <div class="element-icon">
                    <i class="${item.icon}"></i>
                </div>
                <div class="element-info">
                    <p class="element-name">${this.escapeHtml(item.name)}</p>
                    ${item.description ? `<p class="element-desc">${this.escapeHtml(item.description)}</p>` : ''}
                    ${item.meta ? `<p class="element-meta">${item.meta}</p>` : ''}
                </div>
            </div>
        `).join('');
        
        // Добавляем обработчики
        container.querySelectorAll('.element-item').forEach((el, idx) => {
            el.addEventListener('click', mapped[idx].onClick);
        });
    }
    
    /**
     * Настройка поиска
     */
    setupSearch(items, filterFn) {
        const searchInput = document.getElementById('elementSearchInput');
        if (!searchInput) return;
        
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            
            if (!query) {
                // Показываем все элементы если поиск пустой
                const container = document.getElementById('elementsList');
                const itemElements = container.querySelectorAll('.element-item');
                itemElements.forEach(el => el.style.display = '');
                return;
            }
            
            const filtered = items.filter(item => filterFn(item, query));
            
            // Создаем Set ID-шников отфильтрованных элементов
            const filteredIds = new Set();
            filtered.forEach(item => {
                const id = item.agent_id || item.tool_id || item.flow_id || item.id || item.name;
                filteredIds.add(id);
            });
            
            // Показываем/скрываем элементы
            const container = document.getElementById('elementsList');
            const itemElements = container.querySelectorAll('.element-item');
            
            itemElements.forEach((el) => {
                const itemId = el.dataset.elementId;
                el.style.display = filteredIds.has(itemId) ? '' : 'none';
            });
        });
    }
    
    /**
     * Создание нового агента
     */
    async createNewAgent(agentType, position) {
        console.log('🆕 Создаем нового агента:', agentType);
        
        // TODO: Интеграция с формой создания агента
        const agentId = `new_${agentType}_agent_${Date.now()}`;
        
        const nodeData = {
            id: `agent_${Date.now()}`,
            type: 'agent_node',
            params: { 
                agent_id: agentId,
                type: agentType,
                name: `Новый ${agentType} агент`
            },
            ui: { 
                x: position.x, 
                y: position.y, 
                width: 200, 
                height: 100 
            }
        };
        
        await this.createNode(nodeData);
        this.closeSelector();
    }
    
    /**
     * Выбор существующего агента
     */
    async selectExistingAgent(agentId) {
        console.log('✅ Выбран агент:', agentId);
        
        if (!this.currentContext) {
            console.error('❌ currentContext is null');
            return;
        }
        
        // Загружаем данные агента для получения имени
        let agentName = 'Agent';
        try {
            const response = await fetch(`/frontend/api/agents/${encodeURIComponent(agentId)}`);
            if (response.ok) {
                const agent = await response.json();
                agentName = agent.name || agentName;
            }
        } catch (error) {
            console.warn('Не удалось загрузить имя агента');
        }
        
        const nodeData = {
            id: `agent_${Date.now()}`,
            type: 'agent_node',
            params: { 
                agent_id: agentId,
                name: agentName
            },
            ui: {
                x: this.currentContext.position.x,
                y: this.currentContext.position.y,
                width: 200,
                height: 100
            }
        };
        
        await this.createNode(nodeData);
        this.closeSelector();
    }
    
    /**
     * Выбор существующего тула
     */
    async selectExistingTool(toolId, toolName = null) {
        console.log('✅ Выбран тул:', toolId, 'имя:', toolName);
        
        if (!this.currentContext) {
            console.error('❌ currentContext is null');
            return;
        }
        
        // Если имя не передано, загружаем данные тула
        if (!toolName) {
            try {
                const response = await fetch(`/frontend/api/tools/${encodeURIComponent(toolId)}`);
                if (response.ok) {
                    const tool = await response.json();
                    toolName = tool.name || 'Tool';
                }
            } catch (error) {
                console.warn('Не удалось загрузить имя тула');
                toolName = 'Tool';
            }
        }
        
        const nodeData = {
            id: `tool_${Date.now()}`,
            type: 'tool_node',
            params: { 
                tool_id: toolId,
                name: toolName
            },
            ui: {
                x: this.currentContext.position.x,
                y: this.currentContext.position.y,
                width: 200,
                height: 100
            }
        };
        
        await this.createNode(nodeData);
        this.closeSelector();
    }
    
    /**
     * Выбор существующего flow
     */
    async selectExistingFlow(flowId) {
        console.log('✅ Выбран flow:', flowId);
        
        if (!this.currentContext) {
            console.error('❌ currentContext is null');
            return;
        }
        
        const nodeData = {
            id: `flow_${Date.now()}`,
            type: 'flow_node',
            params: { flow_id: flowId },
            ui: {
                x: this.currentContext.position.x,
                y: this.currentContext.position.y,
                width: 200,
                height: 100
            }
        };
        
        await this.createNode(nodeData);
        this.closeSelector();
    }
    
    /**
     * Создание простой ноды (для типов не требующих выбора)
     */
    async createSimpleNode(nodeType, position) {
        const typeNames = {
            'message_node': 'Message',
            'function_node': 'Function',
            'router_node': 'Router'
        };
        
        const nodeData = {
            id: `${nodeType}_${Date.now()}`,
            type: nodeType,
            params: {
                name: typeNames[nodeType] || 'Node'
            },
            ui: {
                x: position.x,
                y: position.y,
                width: 200,
                height: 100
            }
        };
        
        await this.createNode(nodeData);
        this.closeSelector();
    }
    
    /**
     * Создание ноды через Canvas
     */
    async createNode(nodeData) {
        try {
            const node = await this.canvas.addNode(nodeData);
            this.canvas.selectionManager.selectNode(node, false);
            
            this.emit('element:created', { node });
            
        } catch (error) {
            console.error('❌ Ошибка создания ноды:', error);
            alert('Ошибка создания элемента: ' + error.message);
        }
    }
    
    /**
     * Показать контекстное меню в позиции
     */
    showContextMenu(html, position) {
        const menu = document.createElement('div');
        menu.id = 'builderContextMenu';
        menu.style.position = 'fixed';
        menu.style.left = `${position.screenX || position.x}px`;
        menu.style.top = `${position.screenY || position.y}px`;
        menu.style.zIndex = '10000';
        menu.innerHTML = html;
        
        document.body.appendChild(menu);
        this.contextMenu = menu;
        
        // Закрытие по клику вне меню
        setTimeout(() => {
            this.setupOutsideClickHandler();
        }, 100);
        
        // ESC для закрытия
        this.handleEsc = (e) => {
            if (e.key === 'Escape') {
                this.closeSelector();
            }
        };
        document.addEventListener('keydown', this.handleEsc);
    }
    
    /**
     * Настройка закрытия по клику вне меню
     */
    setupOutsideClickHandler() {
        this.handleOutsideClick = (e) => {
            if (this.contextMenu && !this.contextMenu.contains(e.target)) {
                this.closeSelector();
            }
        };
        
        document.addEventListener('click', this.handleOutsideClick);
    }
    
    /**
     * Закрытие только меню (без очистки контекста)
     */
    closeMenu() {
        if (this.contextMenu) {
            this.contextMenu.remove();
            this.contextMenu = null;
        }
        
        if (this.handleEsc) {
            document.removeEventListener('keydown', this.handleEsc);
            this.handleEsc = null;
        }
        
        if (this.handleOutsideClick) {
            document.removeEventListener('click', this.handleOutsideClick);
            this.handleOutsideClick = null;
        }
    }
    
    /**
     * Полное закрытие селектора с очисткой контекста
     */
    closeSelector() {
        this.closeMenu();
        this.currentContext = null;
    }
    
    /**
     * Экранирование HTML
     */
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

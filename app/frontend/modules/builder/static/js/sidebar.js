/**
 * Управление боковой панелью Builder
 */
export default class BuilderSidebar {
    constructor(element, builder) {
        this.element = element;
        this.builder = builder;
        
        // Состояние
        this.currentTab = 'flows';
        this.isCollapsed = false;
        this.searchQuery = '';
        
        // Данные
        this.flows = [];
        this.agents = [];
        this.tools = [];
        
        // DOM элементы
        this.tabButtons = null;
        this.tabContents = null;
        this.searchInput = null;
        this.toggleBtn = null;
    }
    
    /**
     * Инициализация сайдбара
     */
    async init() {
        this.setupElements();
        this.setupEventListeners();
    }
    
    /**
     * Настройка DOM элементов
     */
    setupElements() {
        this.tabButtons = this.element.querySelectorAll('.tab-button');
        this.tabContents = this.element.querySelectorAll('.tab-content');
        this.searchInput = this.element.querySelector('#sidebarSearch');
        this.toggleBtn = this.element.querySelector('#sidebarToggle');
    }
    
    /**
     * Настройка обработчиков событий
     */
    setupEventListeners() {
        // Переключение табов
        this.tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tab = button.dataset.tab;
                this.switchTab(tab);
            });
        });
        
        // Поиск
        if (this.searchInput) {
            this.searchInput.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.toLowerCase();
                this.filterCurrentTab();
            });
        }
        
        // Сворачивание/разворачивание
        if (this.toggleBtn) {
            this.toggleBtn.addEventListener('click', () => {
                this.toggle();
            });
        }
    }
    
    /**
     * Переключение таба
     */
    switchTab(tabName) {
        if (this.currentTab === tabName) return;
        
        // Обновляем кнопки
        this.tabButtons.forEach(button => {
            button.classList.toggle('active', button.dataset.tab === tabName);
        });
        
        // Обновляем контент
        this.tabContents.forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}Tab`);
        });
        
        this.currentTab = tabName;
        
        // Загружаем данные если нужно
        this.loadTabData(tabName);
    }
    
    /**
     * Загрузка данных для таба
     */
    async loadTabData(tabName) {
        switch (tabName) {
            case 'flows':
                if (this.flows.length === 0) {
                    await this.loadFlows();
                }
                break;
            case 'agents':
                if (this.agents.length === 0) {
                    await this.loadAgents();
                }
                break;
            case 'tools':
                if (this.tools.length === 0) {
                    await this.loadTools();
                }
                break;
        }
    }
    
    /**
     * Загрузка списка флоу
     */
    async loadFlows() {
        try {
            const response = await fetch('/frontend/api/flows/');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            this.flows = await response.json();
            this.renderFlows();
            
        } catch (error) {
            console.error('Ошибка загрузки флоу:', error);
            this.showError('flows', 'Ошибка загрузки флоу');
        }
    }
    
    /**
     * Загрузка списка агентов
     */
    async loadAgents() {
        try {
            const response = await fetch('/frontend/api/agents/');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            this.agents = await response.json();
            this.renderAgents();
            
        } catch (error) {
            console.error('Ошибка загрузки агентов:', error);
            this.showError('agents', 'Ошибка загрузки агентов');
        }
    }
    
    /**
     * Загрузка списка тулов
     */
    async loadTools() {
        try {
            const response = await fetch('/frontend/api/tools/');
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            this.tools = await response.json();
            this.renderTools();
            
        } catch (error) {
            console.error('Ошибка загрузки тулов:', error);
            this.showError('tools', 'Ошибка загрузки тулов');
        }
    }
    
    /**
     * Рендеринг списка флоу
     */
    renderFlows() {
        const container = this.element.querySelector('#flowsList');
        if (!container) return;
        
        if (this.flows.length === 0) {
            container.innerHTML = this.getEmptyState('flows', 'Нет созданных флоу');
            return;
        }
        
        const filteredFlows = this.filterItems(this.flows, ['name', 'description']);
        
        container.innerHTML = filteredFlows.map(flow => this.renderFlowCard(flow)).join('');
        
        // Настраиваем обработчики
        this.setupFlowHandlers(container);
    }
    
    /**
     * Рендеринг списка агентов
     */
    renderAgents() {
        const container = this.element.querySelector('#agentsList');
        if (!container) return;
        
        if (this.agents.length === 0) {
            container.innerHTML = this.getEmptyState('agents', 'Нет созданных агентов');
            return;
        }
        
        const filteredAgents = this.filterItems(this.agents, ['name', 'description']);
        
        container.innerHTML = filteredAgents.map(agent => this.renderAgentCard(agent)).join('');
        
        // Настраиваем обработчики
        this.setupAgentHandlers(container);
    }
    
    /**
     * Рендеринг списка тулов
     */
    renderTools() {
        const container = this.element.querySelector('#toolsList');
        if (!container) return;
        
        if (this.tools.length === 0) {
            container.innerHTML = this.getEmptyState('tools', 'Нет доступных тулов');
            return;
        }
        
        const filteredTools = this.filterItems(this.tools, ['name', 'description', 'category', 'group', 'server']);
        
        // Для тулов оставляем простые карточки (они только для чтения)
        container.innerHTML = filteredTools.map(tool => this.renderToolCard(tool)).join('');
        
        // Настраиваем обработчики
        this.setupToolHandlers(container);
    }
    
    /**
     * Универсальный рендеринг расширяемой карточки
     */
    renderExpandableCard(item, type) {
        const cardData = this.getCardData(item, type);
        
        return `
            <div class="item-card expandable-card ${type}-card" 
                 data-${type}-id="${cardData.id}" 
                 data-model-type="${cardData.modelType}"
                 data-model-id="${cardData.id}"
                 draggable="true">
                
                <!-- Компактный вид -->
                <div class="card-compact-view">
                    <div class="card-header">
                        <div class="card-icon">
                            <i class="${cardData.icon}"></i>
                        </div>
                        <div class="card-title">${cardData.name}</div>
                        <div class="card-actions">
                            ${cardData.actions.map(action => `
                                <button class="btn-icon" data-action="${action.name}" title="${action.title}">
                                    <i class="${action.icon}"></i>
                                </button>
                            `).join('')}
                            <button class="btn-icon expand-btn" data-action="expand" title="Развернуть">
                                <i class="icon-chevron-down"></i>
                            </button>
                        </div>
                    </div>
                    
                    ${cardData.description ? `<div class="card-description">${cardData.description}</div>` : ''}
                    
                    <div class="card-meta">
                        ${cardData.meta.map(meta => `
                            <span class="meta-item">
                                <i class="${meta.icon}"></i>
                                ${meta.text}
                            </span>
                        `).join('')}
                    </div>
                    
                    ${cardData.tags.length > 0 ? `
                        <div class="card-tags">
                            ${cardData.tags.map(tag => `<span class="tag tag-${tag.type}">${tag.text}</span>`).join('')}
                        </div>
                    ` : ''}
                </div>
                
                <!-- Развернутый вид с формой -->
                <div class="card-expanded-view" style="display: none;">
                    <div class="card-form-container">
                        <!-- Форма будет загружена через HTMX -->
                        <div class="loading-placeholder">
                            <div class="loader"></div>
                            <span>Загрузка формы...</span>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
    
    /**
     * Получение данных для карточки в зависимости от типа
     */
    getCardData(item, type) {
        switch (type) {
            case 'flow':
                return this.getFlowCardData(item);
            case 'agent':
                return this.getAgentCardData(item);
            case 'tool':
                return this.getToolCardData(item);
            default:
                return this.getDefaultCardData(item);
        }
    }
    
    /**
     * Данные карточки флоу
     */
    getFlowCardData(flow) {
        const createdAt = flow.created_at ? new Date(flow.created_at).toLocaleDateString('ru-RU') : '—';
        const platforms = Object.keys(flow.platforms || {});
        
        return {
            id: flow.flow_id,
            modelType: 'flow',
            name: flow.name,
            description: flow.description,
            icon: 'icon-flow',
            actions: [
                { name: 'run', title: 'Запустить чат', icon: 'icon-play' },
                { name: 'edit', title: 'Редактировать', icon: 'icon-edit' },
                { name: 'delete', title: 'Удалить', icon: 'icon-trash' }
            ],
            meta: [
                { icon: 'icon-user', text: flow.entry_point_agent || "Не настроен" },
                { icon: 'icon-calendar', text: createdAt }
            ],
            tags: platforms.map(platform => ({ type: 'platform', text: platform }))
        };
    }
    
    /**
     * Данные карточки агента
     */
    getAgentCardData(agent) {
        const iconClass = agent.type === 'react' ? 'brain' : 'network';
        const toolsCount = agent.tools ? agent.tools.length : 0;
        
        return {
            id: agent.agent_id,
            modelType: 'agent',
            name: agent.name,
            description: agent.description,
            icon: `icon-${iconClass}`,
            actions: [
                { name: 'edit', title: 'Редактировать', icon: 'icon-edit' },
                { name: 'delete', title: 'Удалить', icon: 'icon-trash' }
            ],
            meta: [
                { icon: 'icon-type', text: agent.type.toUpperCase() },
                { icon: 'icon-tools', text: `${toolsCount} tools` }
            ],
            tags: [
                { type: agent.type, text: agent.type },
                { type: agent.code_mode === 'inline_code' ? 'inline' : 'reference', text: agent.code_mode === 'inline_code' ? 'Inline' : 'Reference' }
            ]
        };
    }
    
    /**
     * Данные карточки тула
     */
    getToolCardData(tool) {
        const requiredParams = tool.parameters?.required?.length || 0;
        
        return {
            id: tool.id,
            modelType: 'tool',
            name: tool.name,
            description: tool.description,
            icon: 'icon-tool',
            actions: [],
            meta: [
                { icon: 'icon-category', text: tool.category },
                { icon: 'icon-params', text: `${requiredParams} params` }
            ],
            tags: [
                { type: tool.category, text: tool.category }
            ]
        };
    }
    
    /**
     * Рендеринг карточки флоу (старый метод - оставляю для совместимости)
     */
    renderFlowCard(flow) {
        const createdAt = flow.created_at ? new Date(flow.created_at).toLocaleDateString('ru-RU') : '—';
        const platforms = Object.keys(flow.platforms || {});
        
        return `
            <div class="item-card flow-card" data-flow-id="${flow.flow_id}" draggable="true">
                <div class="card-header">
                    <div class="card-icon">
                        <i class="bi bi-diagram-3"></i>
                    </div>
                    <div class="card-title">${flow.name}</div>
                    <div class="card-actions">
                        <button class="btn-icon" data-action="run" title="Запустить чат">
                            <i class="bi bi-play-fill"></i>
                        </button>
                        <button class="btn-icon" data-action="edit" title="Редактировать">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn-icon" data-action="delete" title="Удалить">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
                
                ${flow.description ? `<div class="card-description">${flow.description}</div>` : ''}
                
                <div class="card-meta">
                    <span class="meta-item">
                        <i class="bi bi-person"></i>
                        ${flow.entry_point_agent || "Не настроен"}
                    </span>
                    <span class="meta-item">
                        <i class="bi bi-calendar"></i>
                        ${createdAt}
                    </span>
                </div>
                
                <div class="card-platforms">
                    ${platforms.map(platform => `<span class="platform-badge">${platform}</span>`).join('')}
                </div>
            </div>
        `;
    }
    
    /**
     * Рендеринг карточки агента
     */
    renderAgentCard(agent) {
        const iconClass = agent.type === 'react' ? 'bi-robot' : 'bi-share';
        const toolsCount = agent.tools ? agent.tools.length : 0;
        
        return `
            <div class="item-card agent-card" data-agent-id="${agent.agent_id}" draggable="true">
                <div class="card-header">
                    <div class="card-icon">
                        <i class="bi ${iconClass}"></i>
                    </div>
                    <div class="card-title">${agent.name}</div>
                    <div class="card-actions">
                        <button class="btn-icon" data-action="edit" title="Редактировать">
                            <i class="bi bi-pencil"></i>
                        </button>
                        <button class="btn-icon" data-action="delete" title="Удалить">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
                
                ${agent.description ? `<div class="card-description">${agent.description}</div>` : ''}
                
                <div class="card-meta">
                    <span class="meta-item">
                        <i class="bi bi-tag"></i>
                        ${agent.type.toUpperCase()}
                    </span>
                    <span class="meta-item">
                        <i class="bi bi-tools"></i>
                        ${toolsCount} tools
                    </span>
                </div>
                
                <div class="card-tags">
                    <span class="tag tag-${agent.type}">${agent.type}</span>
                    ${agent.code_mode === 'inline_code' 
                        ? '<span class="tag tag-inline">Inline</span>' 
                        : '<span class="tag tag-reference">Reference</span>'
                    }
                </div>
            </div>
        `;
    }
    
    /**
     * Рендеринг карточки тула
     */
    renderToolCard(tool) {
        const requiredParams = tool.parameters?.required?.length || 0;
        const isMcp = tool.code_mode === 'mcp_tool' || tool.server;
        const groupOrServer = isMcp ? (tool.server || tool.group) : (tool.group || tool.category);
        const iconClass = isMcp ? 'bi-plugin' : 'bi-wrench';
        
        return `
            <div class="item-card tool-card" data-tool-id="${tool.id}" draggable="true">
                <div class="card-header">
                    <div class="card-icon">
                        <i class="bi ${iconClass}"></i>
                    </div>
                    <div class="card-title">${tool.name}</div>
                    <div class="card-actions">
                        <button class="btn-icon" data-action="edit" title="Редактировать">
                            <i class="bi bi-pencil"></i>
                        </button>
                    </div>
                </div>
                
                ${tool.description ? `<div class="card-description">${tool.description}</div>` : ''}
                
                <div class="card-meta">
                    <span class="meta-item">
                        <i class="bi ${isMcp ? 'bi-server' : 'bi-folder'}"></i>
                        ${groupOrServer || (isMcp ? 'MCP' : 'general')}
                    </span>
                    <span class="meta-item">
                        <i class="bi bi-gear"></i>
                        ${requiredParams} params
                    </span>
                </div>
                
                <div class="card-tags">
                    <span class="tag tag-${tool.category}">${tool.category}</span>
                    ${isMcp ? '<span class="tag tag-mcp">MCP</span>' : ''}
                </div>
            </div>
        `;
    }
    
    /**
     * Настройка обработчиков для флоу
     */
    setupFlowHandlers(container) {
        container.querySelectorAll('.flow-card').forEach(card => {
            // Клик по карточке - загрузить флоу
            card.addEventListener('click', (e) => {
                if (e.target.closest('.card-actions')) return;
                
                const flowId = card.dataset.flowId;
                this.builder.loadFlow(flowId);
            });
            
            // Действия
            const runBtn = card.querySelector('[data-action="run"]');
            const editBtn = card.querySelector('[data-action="edit"]');
            const deleteBtn = card.querySelector('[data-action="delete"]');
            
            if (runBtn) {
                runBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const flowId = card.dataset.flowId;
                    const flow = this.flows.find(f => f.flow_id === flowId);
                    this.runFlow(flow);
                });
            }
            
            if (editBtn) {
                editBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const flowId = card.dataset.flowId;
                    const flow = this.flows.find(f => f.flow_id === flowId);
                    this.builder.showFlowEditor(flow);
                });
            }
            
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const flowId = card.dataset.flowId;
                    this.deleteFlow(flowId);
                });
            }
        });
    }
    
    /**
     * Настройка обработчиков для агентов
     */
    setupAgentHandlers(container) {
        container.querySelectorAll('.agent-card').forEach(card => {
            // Drag & Drop будет обрабатываться в BuilderDragDrop
            
            // Действия
            const editBtn = card.querySelector('[data-action="edit"]');
            const deleteBtn = card.querySelector('[data-action="delete"]');
            
            if (editBtn) {
                editBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const agentId = card.dataset.agentId;
                    this.editAgent(agentId);
                });
            }
            
            if (deleteBtn) {
                deleteBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const agentId = card.dataset.agentId;
                    this.deleteAgent(agentId);
                });
            }
        });
    }
    
    /**
     * Настройка обработчиков для тулов
     */
    setupToolHandlers(container) {
        container.querySelectorAll('.tool-card').forEach(card => {
            // Кнопка редактирования
            const editBtn = card.querySelector('[data-action="edit"]');
            if (editBtn) {
                editBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const toolId = card.dataset.toolId;
                    this.editTool(toolId);
                });
            }
        });
    }
    
    /**
     * Редактирование инструмента
     */
    async editTool(toolId) {
        try {
            const response = await fetch(`/frontend/models/tool/${toolId}?view=form`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const html = await response.text();
            
            // Оборачиваем в модальное окно
            const modalHtml = `
                <div class="modal show" style="display: flex !important;">
                    <div class="modal-backdrop show"></div>
                    <div class="modal-form-wrapper">
                        <button type="button" class="modal-close-btn" data-bs-dismiss="modal">
                            <i class="bi bi-x"></i>
                        </button>
                        ${html}
                    </div>
                </div>
            `;
            
            this.builder.showModal(modalHtml);
            
        } catch (error) {
            console.error('Ошибка показа редактора инструмента:', error);
            this.builder.showNotification('Ошибка показа редактора: ' + error.message, 'error');
        }
    }
    
    /**
     * Универсальная настройка обработчиков для расширяемых карточек
     */
    setupExpandableCardHandlers(container, type) {
        container.querySelectorAll(`.${type}-card`).forEach(card => {
            // Клик по карточке - загрузить на канвас (только для flow)
            if (type === 'flow') {
                card.addEventListener('click', (e) => {
                    if (e.target.closest('.card-actions') || e.target.closest('.card-expanded-view')) return;
                    
                    const flowId = card.dataset.flowId;
                    this.builder.loadFlow(flowId);
                });
            }
            
            // Кнопка разворачивания
            const expandBtn = card.querySelector('[data-action="expand"]');
            if (expandBtn) {
                expandBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.toggleCardExpansion(card);
                });
            }
            
            // Действия карточки
            this.setupCardActions(card, type);
        });
    }
    
    /**
     * Настройка действий карточки
     */
    setupCardActions(card, type) {
        const actions = card.querySelectorAll('[data-action]');
        
        actions.forEach(actionBtn => {
            const action = actionBtn.dataset.action;
            if (action === 'expand') return; // Уже обработано выше
            
            actionBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.handleCardAction(card, type, action);
            });
        });
    }
    
    /**
     * Обработка действий карточки
     */
    handleCardAction(card, type, action) {
        const itemId = card.dataset[`${type}Id`];
        
        switch (action) {
            case 'run':
                if (type === 'flow') {
                    const flow = this.flows.find(f => f.flow_id === itemId);
                    this.runFlow(flow);
                }
                break;
                
            case 'edit':
                this.editItem(itemId, type);
                break;
                
            case 'delete':
                this.deleteItem(itemId, type);
                break;
        }
    }
    
    /**
     * Переключение разворачивания карточки
     */
    async toggleCardExpansion(card) {
        const compactView = card.querySelector('.card-compact-view');
        const expandedView = card.querySelector('.card-expanded-view');
        const expandBtn = card.querySelector('.expand-btn i');
        const formContainer = card.querySelector('.card-form-container');
        
        const isExpanded = expandedView.style.display !== 'none';
        
        if (isExpanded) {
            // Сворачиваем
            expandedView.style.display = 'none';
            expandBtn.className = 'icon-chevron-down';
            card.classList.remove('expanded');
        } else {
            // Разворачиваем
            expandedView.style.display = 'block';
            expandBtn.className = 'icon-chevron-up';
            card.classList.add('expanded');
            
            // Загружаем форму если еще не загружена
            if (formContainer.querySelector('.loading-placeholder')) {
                await this.loadCardForm(card);
            }
        }
    }
    
    /**
     * Загрузка формы для карточки через HTMX
     */
    async loadCardForm(card) {
        const modelType = card.dataset.modelType;
        const modelId = card.dataset.modelId;
        const formContainer = card.querySelector('.card-form-container');
        
        try {
            // Используем существующий API для получения формы
            const response = await fetch(`/frontend/models/${modelType}/${modelId}?view=form`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const formHtml = await response.text();
            formContainer.innerHTML = formHtml;
            
            // Инициализируем HTMX для новых элементов
            if (typeof htmx !== 'undefined') {
                htmx.process(formContainer);
            }
            
        } catch (error) {
            console.error('Ошибка загрузки формы:', error);
            formContainer.innerHTML = `
                <div class="error-state">
                    <i class="icon-warning"></i>
                    <span>Ошибка загрузки формы</span>
                </div>
            `;
        }
    }
    
    /**
     * Фильтрация элементов
     */
    filterItems(items, searchFields) {
        if (!this.searchQuery) return items;
        
        return items.filter(item => {
            return searchFields.some(field => {
                const value = item[field];
                return value && value.toLowerCase().includes(this.searchQuery);
            });
        });
    }
    
    /**
     * Фильтрация текущего таба
     */
    filterCurrentTab() {
        switch (this.currentTab) {
            case 'flows':
                this.renderFlows();
                break;
            case 'agents':
                this.renderAgents();
                break;
            case 'tools':
                this.renderTools();
                break;
        }
    }
    
    /**
     * Сворачивание/разворачивание сайдбара
     */
    toggle() {
        this.isCollapsed = !this.isCollapsed;
        this.element.classList.toggle('collapsed', this.isCollapsed);
        
        // Обновляем иконку
        const icon = this.toggleBtn.querySelector('i');
        if (icon) {
            icon.className = this.isCollapsed ? 'icon-chevron-right' : 'icon-chevron-left';
        }
    }
    
    /**
     * Запуск флоу в чате
     */
    async runFlow(flow) {
        try {
            // Проверяем, что глобальный чат доступен
            if (!window.app || !window.app.chat) {
                this.builder.showNotification('Чат не инициализирован', 'error');
                return;
            }
            
            // Открываем чат с флоу
            await window.app.chat.open({
                agent_id: flow.flow_id,
                initial_message: `Привет! Запускаю флоу "${flow.name}"`,
                position: 'right',
                size: 'large'
            });
            
            this.builder.showNotification(`Чат с флоу "${flow.name}" открыт`, 'success');
            
        } catch (error) {
            console.error('Ошибка запуска чата с флоу:', error);
            this.builder.showNotification('Ошибка запуска чата: ' + error.message, 'error');
        }
    }
    
    /**
     * Удаление флоу
     */
    async deleteFlow(flowId) {
        if (!confirm('Вы уверены, что хотите удалить этот флоу?')) {
            return;
        }
        
        try {
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // Удаляем из локального массива
            this.flows = this.flows.filter(f => f.flow_id !== flowId);
            this.renderFlows();
            
            this.builder.showNotification('Флоу удален', 'success');
            
        } catch (error) {
            console.error('Ошибка удаления флоу:', error);
            this.builder.showNotification('Ошибка удаления флоу: ' + error.message, 'error');
        }
    }
    
    /**
     * Редактирование агента
     */
    async editAgent(agentId) {
        try {
            const response = await fetch(`/frontend/models/agent/${agentId}?view=form`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const html = await response.text();
            
            // Оборачиваем в модальное окно
            const modalHtml = `
                <div class="modal show" style="display: flex !important;">
                    <div class="modal-backdrop show"></div>
                    <div class="modal-form-wrapper">
                        <button type="button" class="modal-close-btn" data-bs-dismiss="modal">
                            <i class="bi bi-x"></i>
                        </button>
                        ${html}
                    </div>
                </div>
            `;
            
            this.builder.showModal(modalHtml);
            
        } catch (error) {
            console.error('Ошибка показа редактора агента:', error);
            this.builder.showNotification('Ошибка показа редактора: ' + error.message, 'error');
        }
    }
    
    /**
     * Удаление агента
     */
    async deleteAgent(agentId) {
        if (!confirm('Вы уверены, что хотите удалить этого агента?')) {
            return;
        }
        
        try {
            const response = await fetch(`/frontend/api/agents/${agentId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // Удаляем из локального массива
            this.agents = this.agents.filter(a => a.agent_id !== agentId);
            this.renderAgents();
            
            this.builder.showNotification('Агент удален', 'success');
            
        } catch (error) {
            console.error('Ошибка удаления агента:', error);
            this.builder.showNotification('Ошибка удаления агента: ' + error.message, 'error');
        }
    }
    
    /**
     * Показать ошибку
     */
    showError(tab, message) {
        const container = this.element.querySelector(`#${tab}List`);
        if (container) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">⚠️</div>
                    <div class="empty-state-title">Ошибка</div>
                    <div class="empty-state-description">${message}</div>
                </div>
            `;
        }
    }
    
    /**
     * Получить пустое состояние
     */
    getEmptyState(type, message) {
        const icons = {
            flows: '🔄',
            agents: '🤖',
            tools: '🔧'
        };
        
        return `
            <div class="empty-state">
                <div class="empty-state-icon">${icons[type] || '📭'}</div>
                <div class="empty-state-title">Пусто</div>
                <div class="empty-state-description">${message}</div>
            </div>
        `;
    }
}

// Экспортируем класс в глобальную область

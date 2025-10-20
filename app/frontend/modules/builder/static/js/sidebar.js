/**
 * BuilderSidebar v3.0 - Упрощенная версия для новой ООП архитектуры
 */
export default class BuilderSidebar {
    constructor(builder) {
        this.builder = builder;
        this.canvas = builder.canvas;
        this.element = document.getElementById('builderSidebar');
        
        // Состояние
        this.currentTab = 'flows';
        this.isCollapsed = false;
        
        // Данные
        this.flows = [];
        this.agents = [];
        this.tools = [];
        
        this.init();
    }
    
    /**
     * Инициализация
     */
    async init() {
        console.log('📑 Sidebar v3.0 инициализация...');
        
        if (!this.element) {
            console.warn('⚠️ Sidebar элемент не найден');
            return;
        }
        
        this.setupEventListeners();
        await this.loadInitialData();
        
        console.log('✅ Sidebar инициализирован');
    }
    
    /**
     * Настройка обработчиков
     */
    setupEventListeners() {
        // Переключение табов
        const tabButtons = this.element.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                const tab = button.dataset.tab;
                this.switchTab(tab);
            });
        });
        
        // Сворачивание
        const toggleBtn = this.element.querySelector('#sidebarToggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggle());
        }
        
        // Поиск
        const searchInput = this.element.querySelector('#sidebarSearch');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                this.filterItems(e.target.value);
            });
        }
    }
    
    /**
     * Загрузка начальных данных
     */
    async loadInitialData() {
        await Promise.all([
            this.loadFlows(),
            this.loadAgents(),
            this.loadTools()
        ]);
    }
    
    /**
     * Загрузка flows
     */
    async loadFlows() {
        try {
            const response = await fetch('/frontend/api/flows/');
            if (response.ok) {
                this.flows = await response.json();
                this.renderFlows();
            }
        } catch (error) {
            console.error('❌ Ошибка загрузки flows:', error);
        }
    }
    
    /**
     * Загрузка agents
     */
    async loadAgents() {
        try {
            const response = await fetch('/frontend/api/agents/');
            if (response.ok) {
                this.agents = await response.json();
                this.renderAgents();
            }
        } catch (error) {
            console.error('❌ Ошибка загрузки agents:', error);
        }
    }
    
    /**
     * Загрузка tools
     */
    async loadTools() {
        try {
            const response = await fetch('/frontend/api/tools/');
            if (response.ok) {
                this.tools = await response.json();
                this.renderTools();
            }
        } catch (error) {
            console.error('❌ Ошибка загрузки tools:', error);
        }
    }
    
    /**
     * Рендеринг flows
     */
    renderFlows() {
        const container = this.element.querySelector('#flowsTab .items-list');
        if (!container) return;
        
        if (this.flows.length === 0) {
            container.innerHTML = '<div class="empty-state">Нет flows</div>';
            return;
        }
        
        container.innerHTML = this.flows.map(flow => `
            <div class="sidebar-item" 
                 draggable="true" 
                 data-item-type="flow"
                 data-item-id="${flow.flow_id}">
                <i class="bi bi-diagram-3"></i>
                <span class="item-name">${flow.name}</span>
            </div>
        `).join('');
        
        this.setupDragForItems(container);
    }
    
    /**
     * Рендеринг agents
     */
    renderAgents() {
        const container = this.element.querySelector('#agentsTab .items-list');
        if (!container) return;
        
        if (this.agents.length === 0) {
            container.innerHTML = '<div class="empty-state">Нет agents</div>';
            return;
        }
        
        container.innerHTML = this.agents.map(agent => `
            <div class="sidebar-item" 
                 draggable="true" 
                 data-item-type="agent"
                 data-item-id="${agent.agent_id}">
                <i class="bi bi-robot"></i>
                <span class="item-name">${agent.name}</span>
                <span class="item-meta">${agent.type}</span>
            </div>
        `).join('');
        
        this.setupDragForItems(container);
    }
    
    /**
     * Рендеринг tools
     */
    renderTools() {
        const container = this.element.querySelector('#toolsTab .items-list');
        if (!container) return;
        
        if (this.tools.length === 0) {
            container.innerHTML = '<div class="empty-state">Нет tools</div>';
            return;
        }
        
        container.innerHTML = this.tools.map(tool => `
            <div class="sidebar-item" 
                 draggable="true" 
                 data-item-type="tool"
                 data-item-id="${tool.tool_id}">
                <i class="bi bi-tools"></i>
                <span class="item-name">${tool.name}</span>
            </div>
        `).join('');
        
        this.setupDragForItems(container);
    }
    
    /**
     * Настройка drag для элементов
     */
    setupDragForItems(container) {
        const items = container.querySelectorAll('.sidebar-item');
        
        items.forEach(item => {
            item.addEventListener('dragstart', (e) => {
                const itemType = item.dataset.itemType;
                const itemId = item.dataset.itemId;
                
                e.dataTransfer.effectAllowed = 'copy';
                e.dataTransfer.setData('application/x-sidebar-item', JSON.stringify({
                    type: itemType,
                    id: itemId
                }));
                
                item.classList.add('dragging');
                console.log('🎨 Drag из sidebar:', itemType, itemId);
            });
            
            item.addEventListener('dragend', (e) => {
                item.classList.remove('dragging');
            });
            
            // Двойной клик для быстрого добавления
            item.addEventListener('dblclick', () => {
                this.addItemToCanvas(item.dataset.itemType, item.dataset.itemId);
            });
        });
    }
    
    /**
     * Добавление элемента на canvas (по центру)
     * При двойном клике создаем ноду с известным ID элемента
     */
    async addItemToCanvas(itemType, itemId) {
        const centerPos = this.canvas.getCenterPosition();
        
        let nodeType;
        let params = {};
        
        switch (itemType) {
            case 'flow':
                nodeType = 'flow_node';
                params = { flow_id: itemId };
                break;
            case 'agent':
                nodeType = 'agent_node';
                params = { agent_id: itemId };
                break;
            case 'tool':
                nodeType = 'tool_node';
                params = { tool_id: itemId };
                break;
        }
        
        const nodeData = {
            id: `${nodeType}_${Date.now()}`,
            type: nodeType,
            params,
            ui: {
                x: centerPos.x,
                y: centerPos.y,
                width: 200,
                height: 100
            }
        };
        
        try {
            const node = await this.canvas.addNode(nodeData);
            console.log('✅ Элемент добавлен на canvas:', node.id);
            
            this.canvas.selectionManager.selectNode(node, false);
        } catch (error) {
            console.error('❌ Ошибка добавления элемента:', error);
        }
    }
    
    /**
     * Переключение таба
     */
    switchTab(tabName) {
        if (this.currentTab === tabName) return;
        
        console.log('📑 Переключение на таб:', tabName);
        
        // Обновляем кнопки
        const tabButtons = this.element.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.classList.toggle('active', button.dataset.tab === tabName);
        });
        
        // Обновляем контент
        const tabContents = this.element.querySelectorAll('.tab-content');
        tabContents.forEach(content => {
            content.classList.toggle('active', content.id === `${tabName}Tab`);
        });
        
        this.currentTab = tabName;
    }
    
    /**
     * Фильтрация элементов
     */
    filterItems(query) {
        const lowerQuery = query.toLowerCase();
        const activeTab = this.element.querySelector('.tab-content.active');
        if (!activeTab) return;
        
        const items = activeTab.querySelectorAll('.sidebar-item');
        items.forEach(item => {
            const name = item.querySelector('.item-name').textContent.toLowerCase();
            const matches = name.includes(lowerQuery);
            item.style.display = matches ? '' : 'none';
        });
    }
    
    /**
     * Сворачивание/разворачивание
     */
    toggle() {
        this.isCollapsed = !this.isCollapsed;
        this.element.classList.toggle('collapsed', this.isCollapsed);
        console.log('🔄 Sidebar collapsed:', this.isCollapsed);
    }
    
    /**
     * Обновление данных
     */
    async refresh() {
        console.log('🔄 Обновление данных sidebar...');
        await this.loadInitialData();
    }
}

/**
 * Главный класс Builder для визуального редактирования агентских флоу
 */
class Builder {
    constructor(options = {}) {
        this.options = {
            flowId: null,
            ...options
        };
        
        // Состояние
        this.currentFlow = null;
        this.selectedNodes = new Set();
        this.selectedEdges = new Set();
        
        // Компоненты
        this.sidebar = null;
        this.canvas = null;
        this.dragDrop = null;
        
        // DOM элементы
        this.container = null;
        this.sidebarEl = null;
        this.canvasEl = null;
        
        // Флаги
        this.isInitialized = false;
    }
    
    /**
     * Инициализация Builder
     */
    async init() {
        if (this.isInitialized) return;
        
        try {
            this.container = document.getElementById('builderContainer');
            this.sidebarEl = document.getElementById('builderSidebar');
            this.canvasEl = document.getElementById('builderCanvas');
            
            if (!this.container || !this.sidebarEl || !this.canvasEl) {
                throw new Error('Не найдены необходимые DOM элементы');
            }
            
            // Инициализируем компоненты
            await this.initComponents();
            
            // Настраиваем обработчики событий
            this.setupEventListeners();
            
            // Загружаем данные
            await this.loadInitialData();
            
            // Загружаем флоу если указан ID
            if (this.options.flowId) {
                await this.loadFlow(this.options.flowId);
            }
            
            // Инициализируем тему
            this.initTheme();
            
            this.isInitialized = true;
            this.showNotification('Builder инициализирован', 'success');
            
        } catch (error) {
            console.error('Ошибка инициализации Builder:', error);
            this.showNotification('Ошибка инициализации Builder: ' + error.message, 'error');
        }
    }
    
    /**
     * Инициализация компонентов
     */
    async initComponents() {
        // Загружаем модули
        await this.loadModules();
        
        // Инициализируем сайдбар
        this.sidebar = new BuilderSidebar(this.sidebarEl, this);
        await this.sidebar.init();
        
        // Инициализируем канвас
        this.canvas = new BuilderCanvas(this.canvasEl, this);
        await this.canvas.init();
        
        // Инициализируем drag & drop
        this.dragDrop = new BuilderDragDrop(this);
        await this.dragDrop.init();
    }
    
    /**
     * Загрузка модулей
     */
    async loadModules() {
        try {
            // Загружаем модули если они не загружены
            if (typeof BuilderSidebar === 'undefined') {
                await this.loadScript('/static/builder/js/sidebar.js');
            }
            
            if (typeof BuilderCanvas === 'undefined') {
                await this.loadScript('/static/builder/js/canvas.js');
            }
            
            if (typeof BuilderDragDrop === 'undefined') {
                await this.loadScript('/static/builder/js/drag-drop.js');
            }
            
        } catch (error) {
            console.error('Ошибка загрузки модулей:', error);
            throw error;
        }
    }
    
    /**
     * Загрузка скрипта
     */
    loadScript(src) {
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = src;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }
    
    /**
     * Настройка обработчиков событий
     */
    setupEventListeners() {
        // Кнопки тулбара
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        const themeToggleBtn = document.getElementById('themeToggleBtn');
        const clearCanvasBtn = document.getElementById('clearCanvasBtn');
        const searchAddBtn = document.getElementById('searchAddBtn');
        
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveCurrentFlow());
        }
        
        if (runBtn) {
            runBtn.addEventListener('click', () => this.runCurrentFlow());
        }
        
        if (searchAddBtn) {
            searchAddBtn.addEventListener('click', () => this.handleCreateNew());
        }
        
        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', () => this.toggleTheme());
        }
        
        if (clearCanvasBtn) {
            clearCanvasBtn.addEventListener('click', () => this.clearCanvas());
        }
        
        // Горячие клавиши
        document.addEventListener('keydown', (e) => this.handleKeydown(e));
        
        // Контекстное меню
        document.addEventListener('contextmenu', (e) => this.handleContextMenu(e));
        document.addEventListener('click', () => this.hideContextMenu());
    }
    
    /**
     * Загрузка начальных данных
     */
    async loadInitialData() {
        try {
            // Загружаем списки для сайдбара
            await this.sidebar.loadFlows();
            await this.sidebar.loadAgents();
            await this.sidebar.loadTools();
            
        } catch (error) {
            console.error('Ошибка загрузки данных:', error);
            this.showNotification('Ошибка загрузки данных', 'error');
        }
    }
    
    /**
     * Загрузка флоу
     */
    async loadFlow(flowId) {
        try {
            // Загружаем данные флоу
            const response = await fetch(`/frontend/builder/flows/${encodeURIComponent(flowId)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            this.currentFlow = await response.json();
            
            // Загружаем данные канваса
            const canvasResponse = await fetch(`/frontend/builder/flows/${encodeURIComponent(flowId)}/canvas`);
            if (canvasResponse.ok) {
                const canvasData = await canvasResponse.json();
                await this.canvas.loadGraph(canvasData);
                
                // Если канвас пустой, автоматически добавляем флоу
                if (!canvasData.nodes || canvasData.nodes.length === 0) {
                    console.log('📦 Канвас пустой, автоматически добавляем флоу');
                    await this.dragDrop.createFlowWithExpansion(
                        { 
                            id: this.currentFlow.flow_id, 
                            name: this.currentFlow.name 
                        }, 
                        this.canvas.getCenterPosition()
                    );
                }
            }
            
            // Обновляем UI
            this.updateFlowInfo();
            this.enableFlowActions();
            
            this.showNotification(`Флоу "${this.currentFlow.name}" загружен`, 'success');
            
        } catch (error) {
            console.error('Ошибка загрузки флоу:', error);
            this.showNotification('Ошибка загрузки флоу: ' + error.message, 'error');
        }
    }
    
    /**
     * Сохранение текущего флоу
     */
    async saveCurrentFlow() {
        if (!this.currentFlow) {
            this.showNotification('Нет активного флоу для сохранения', 'warning');
            return;
        }
        
        try {
            // Получаем данные канваса
            const canvasData = this.canvas.getGraphData();
            
            // Сохраняем канвас
            const response = await fetch(`/frontend/builder/flows/${encodeURIComponent(this.currentFlow.flow_id)}/canvas`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(canvasData)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            this.showNotification('Флоу сохранен', 'success');
            
        } catch (error) {
            console.error('Ошибка сохранения флоу:', error);
            this.showNotification('Ошибка сохранения: ' + error.message, 'error');
        }
    }
    
    /**
     * Запуск текущего флоу
     */
    async runCurrentFlow() {
        if (!this.currentFlow) {
            this.showNotification('Нет активного флоу для запуска', 'warning');
            return;
        }
        
        this.showNotification('Функция запуска флоу в разработке', 'info');
    }
    
    /**
     * Создание нового флоу
     */
    async handleCreateNew() {
        const activeTab = document.querySelector('.tab-button.active');
        if (!activeTab) return;
        
        const tabType = activeTab.dataset.tab;
        
        switch (tabType) {
            case 'flows':
                await this.createEmptyFlowOnCanvas();
                break;
            case 'agents':
                await this.createEmptyAgentOnCanvas();
                break;
            case 'tools':
                await this.createEmptyToolOnCanvas();
                break;
            default:
                console.warn('Неизвестный тип вкладки:', tabType);
        }
    }
    
    async createEmptyFlowOnCanvas() {
        try {
            // Проверяем что на канвасе нет флоу
            const hasFlow = Array.from(this.canvas.nodes.values())
                .some(node => node.data.type === 'flow_node');
            
            if (hasFlow) {
                this.showNotification('На канвасе уже есть Flow', 'warning');
                return;
            }
            
            // Получаем пустую модель Flow
            const response = await fetch('/frontend/builder/flows/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            
            if (!response.ok) throw new Error('Ошибка создания Flow');
            
            const flowData = await response.json();
            
            // Добавляем на канвас в центре
            const centerPos = this.canvas.getCenterPosition();
            await this.canvas.addNode({
                id: `flow_${flowData.flow_id}_${Date.now()}`,
                type: 'flow_node',
                params: {
                    name: flowData.name,
                    flow_id: flowData.flow_id,
                    description: flowData.description,
                    entry_point_agent: flowData.entry_point_agent,
                    isEntryPoint: true
                },
                ui: { x: centerPos.x, y: centerPos.y, width: 380, height: 200 }
            });
            
            // Устанавливаем как текущий флоу
            this.currentFlow = { flow_id: flowData.flow_id, name: flowData.name };
            this.updateFlowInfo();
            this.enableFlowActions();
            
            this.showNotification('Flow добавлен на канвас', 'success');
            
        } catch (error) {
            console.error('Ошибка создания Flow на канвасе:', error);
            this.showNotification('Ошибка создания Flow: ' + error.message, 'error');
        }
    }
    
    async createEmptyAgentOnCanvas() {
        try {
            // Получаем пустую модель Agent
            const response = await fetch('/frontend/builder/agents/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            
            if (!response.ok) throw new Error('Ошибка создания Agent');
            
            const agentData = await response.json();
            
            // Добавляем на канвас в центре
            const centerPos = this.canvas.getCenterPosition();
            await this.canvas.addNode({
                id: `agent_${agentData.agent_id}_${Date.now()}`,
                type: 'agent_node',
                params: {
                    name: agentData.name,
                    agent_id: agentData.agent_id,
                    description: agentData.description
                },
                ui: { x: centerPos.x, y: centerPos.y, width: 380, height: 200 }
            });
            
            this.showNotification('Agent добавлен на канвас', 'success');
            
        } catch (error) {
            console.error('Ошибка создания Agent на канвасе:', error);
            this.showNotification('Ошибка создания Agent: ' + error.message, 'error');
        }
    }
    
    async createEmptyToolOnCanvas() {
        try {
            // Получаем пустую модель Tool
            const response = await fetch('/frontend/builder/tools/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            
            if (!response.ok) throw new Error('Ошибка создания Tool');
            
            const toolData = await response.json();
            
            // Добавляем на канвас в центре
            const centerPos = this.canvas.getCenterPosition();
            await this.canvas.addNode({
                id: `tool_${toolData.tool_id}_${Date.now()}`,
                type: 'tool_node',
                params: {
                    name: toolData.name || "Новый инструмент",
                    tool_id: toolData.tool_id,
                    description: toolData.description
                },
                ui: { x: centerPos.x, y: centerPos.y, width: 380, height: 200 }
            });
            
            this.showNotification('Tool добавлен на канвас', 'success');
            
        } catch (error) {
            console.error('Ошибка создания Tool на канвасе:', error);
            this.showNotification('Ошибка создания Tool: ' + error.message, 'error');
        }
    }
    
    async createNewFlow() {
        try {
            // Показываем модальное окно создания флоу
            await this.showFlowEditor();
            
        } catch (error) {
            console.error('Ошибка создания флоу:', error);
            this.showNotification('Ошибка создания флоу: ' + error.message, 'error');
        }
    }
    
    /**
     * Показать редактор флоу
     */
    async showFlowEditor(flow = null) {
        try {
            const url = flow 
                ? `/frontend/models/flow/${encodeURIComponent(flow.flow_id)}?view=form`
                : '/frontend/models/flow/new?view=form';
                
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const html = await response.text();
            
            // Добавляем затемнение фона и кнопку закрытия поверх формы
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
            
            // Показываем модальное окно
            this.showModal(modalHtml);
            
        } catch (error) {
            console.error('Ошибка показа редактора флоу:', error);
            this.showNotification('Ошибка показа редактора: ' + error.message, 'error');
        }
    }
    
    /**
     * Обновление информации о флоу
     */
    updateFlowInfo() {
        const nameEl = document.getElementById('currentFlowName');
        if (nameEl) {
            nameEl.textContent = this.currentFlow ? this.currentFlow.name : 'Выберите или создайте Flow';
        }
    }
    
    /**
     * Включение действий с флоу
     */
    enableFlowActions() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        
        if (saveBtn) saveBtn.disabled = false;
        if (runBtn) runBtn.disabled = false;
    }
    
    /**
     * Обработка горячих клавиш
     */
    handleKeydown(e) {
        // Ctrl+S - сохранить
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            this.saveCurrentFlow();
        }
        
        // Delete - удалить выбранные элементы
        if (e.key === 'Delete') {
            this.deleteSelected();
        }
        
        // Escape - снять выделение
        if (e.key === 'Escape') {
            this.clearSelection();
            this.hideContextMenu();
        }
        
        // Ctrl+A - выделить все
        if (e.ctrlKey && e.key === 'a') {
            e.preventDefault();
            this.selectAll();
        }
    }
    
    /**
     * Обработка контекстного меню
     */
    handleContextMenu(e) {
        e.preventDefault();
        
        const contextMenu = document.getElementById('contextMenu');
        if (!contextMenu) return;
        
        // Определяем что под курсором
        const target = e.target.closest('.canvas-node, .edge');
        
        if (target) {
            // Показываем контекстное меню для элемента
            this.showContextMenu(e.clientX, e.clientY, target);
        } else {
            // Скрываем контекстное меню
            this.hideContextMenu();
        }
    }
    
    /**
     * Показать контекстное меню
     */
    showContextMenu(x, y, target) {
        const contextMenu = document.getElementById('contextMenu');
        if (!contextMenu) return;
        
        contextMenu.style.left = x + 'px';
        contextMenu.style.top = y + 'px';
        contextMenu.style.display = 'block';
        
        // Настраиваем обработчики
        const items = contextMenu.querySelectorAll('.context-menu-item');
        items.forEach(item => {
            item.onclick = () => {
                const action = item.dataset.action;
                this.handleContextAction(action, target);
                this.hideContextMenu();
            };
        });
    }
    
    /**
     * Скрыть контекстное меню
     */
    hideContextMenu() {
        const contextMenu = document.getElementById('contextMenu');
        if (contextMenu) {
            contextMenu.style.display = 'none';
        }
    }
    
    /**
     * Обработка действий контекстного меню
     */
    handleContextAction(action, target) {
        switch (action) {
            case 'edit':
                this.editElement(target);
                break;
            case 'duplicate':
                this.duplicateElement(target);
                break;
            case 'delete':
                this.deleteElement(target);
                break;
        }
    }
    
    /**
     * Редактирование элемента
     */
    editElement(target) {
        console.log('Редактирование элемента:', target);
        // TODO: Реализовать редактирование
    }
    
    /**
     * Дублирование элемента
     */
    duplicateElement(target) {
        console.log('Дублирование элемента:', target);
        // TODO: Реализовать дублирование
    }
    
    /**
     * Удаление элемента
     */
    deleteElement(target) {
        if (target.classList.contains('canvas-node')) {
            const nodeId = target.dataset.nodeId;
            this.canvas.removeNode(nodeId);
        } else if (target.classList.contains('edge')) {
            const edgeId = target.dataset.edgeId;
            this.canvas.removeEdge(edgeId);
        }
    }
    
    /**
     * Удаление выбранных элементов
     */
    deleteSelected() {
        this.selectedNodes.forEach(nodeId => {
            this.canvas.removeNode(nodeId);
        });
        
        this.selectedEdges.forEach(edgeId => {
            this.canvas.removeEdge(edgeId);
        });
        
        this.clearSelection();
    }
    
    /**
     * Снятие выделения
     */
    clearSelection() {
        this.selectedNodes.clear();
        this.selectedEdges.clear();
        
        // Обновляем визуальное выделение
        document.querySelectorAll('.canvas-node.selected').forEach(node => {
            node.classList.remove('selected');
        });
        
        document.querySelectorAll('.edge.selected').forEach(edge => {
            edge.classList.remove('selected');
        });
    }
    
    /**
     * Выделить все элементы
     */
    selectAll() {
        this.clearSelection();
        
        document.querySelectorAll('.canvas-node').forEach(node => {
            const nodeId = node.dataset.nodeId;
            this.selectedNodes.add(nodeId);
            node.classList.add('selected');
        });
        
        document.querySelectorAll('.edge').forEach(edge => {
            const edgeId = edge.dataset.edgeId;
            this.selectedEdges.add(edgeId);
            edge.classList.add('selected');
        });
    }
    
    /**
     * Показать модальное окно
     */
    showModal(html) {
        let modalContainer = document.getElementById('modalContainer');
        if (!modalContainer) {
            modalContainer = document.createElement('div');
            modalContainer.id = 'modalContainer';
            document.body.appendChild(modalContainer);
        }
        
        modalContainer.innerHTML = html;
        
        // Настраиваем форму для работы в модальном окне
        const form = modalContainer.querySelector('form');
        if (form) {
            // Убираем target и добавляем обработчик успешного сохранения
            form.removeAttribute('hx-target');
            form.setAttribute('hx-swap', 'none');
            
            // Обработчик успешного сохранения
            form.addEventListener('htmx:afterRequest', (event) => {
                if (event.detail.successful) {
                    this.showNotification('Изменения сохранены', 'success');
                    // Перезагружаем список в сайдбаре
                    if (this.sidebar) {
                        this.sidebar.loadFlows();
                    }
                }
            });
        }
        
        // Инициализируем HTMX для модального окна
        if (typeof htmx !== 'undefined') {
            htmx.process(modalContainer);
        }
        
        const modal = modalContainer.querySelector('.modal');
        if (modal) {
            modal.classList.add('show');
            
            // Обработчик закрытия
            const closeBtn = modal.querySelector('.btn-close, .modal-close-btn, [data-bs-dismiss="modal"]');
            if (closeBtn) {
                closeBtn.onclick = () => this.hideModal();
            }
            
            // Закрытие по клику на backdrop
            const backdrop = modal.querySelector('.modal-backdrop');
            if (backdrop) {
                backdrop.onclick = () => this.hideModal();
            }
            
            // Закрытие по Escape
            const escapeHandler = (e) => {
                if (e.key === 'Escape') {
                    this.hideModal();
                    document.removeEventListener('keydown', escapeHandler);
                }
            };
            document.addEventListener('keydown', escapeHandler);
        }
    }
    
    /**
     * Скрыть модальное окно
     */
    hideModal() {
        const modalContainer = document.getElementById('modalContainer');
        if (modalContainer) {
            const modal = modalContainer.querySelector('.modal');
            if (modal) {
                modal.classList.remove('show');
                setTimeout(() => {
                    modalContainer.innerHTML = '';
                }, 300);
            }
        }
    }
    
    /**
     * Показать уведомление
     */
    showNotification(message, type = 'info', duration = 3000) {
        console.log(`🔔 Показываем уведомление: ${message} (${type})`);
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        
        notification.innerHTML = `
            <div class="notification-header">
                <h6 class="notification-title">${this.getNotificationTitle(type)}</h6>
                <button class="notification-close">&times;</button>
            </div>
            <div class="notification-body">${message}</div>
        `;
        
        document.body.appendChild(notification);
        
        // Показываем уведомление
        setTimeout(() => {
            notification.classList.add('show');
            console.log('✅ Уведомление показано');
        }, 100);
        
        // Обработчик закрытия
        const closeBtn = notification.querySelector('.notification-close');
        closeBtn.onclick = () => this.hideNotification(notification);
        
        // Автоматическое скрытие
        if (duration > 0) {
            setTimeout(() => this.hideNotification(notification), duration);
        }
    }
    
    /**
     * Скрыть уведомление
     */
    hideNotification(notification) {
        notification.classList.remove('show');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }
    
    /**
     * Получить заголовок уведомления по типу
     */
    getNotificationTitle(type) {
        const titles = {
            success: 'Успешно',
            error: 'Ошибка',
            warning: 'Предупреждение',
            info: 'Информация'
        };
        return titles[type] || 'Уведомление';
    }
    
    /**
     * Инициализация темы
     */
    initTheme() {
        // Восстанавливаем тему из localStorage или используем темную по умолчанию
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
    }
    
    /**
     * Переключение темы
     */
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        this.showNotification(`Тема переключена на ${newTheme === 'dark' ? 'темную' : 'светлую'}`, 'info', 2000);
    }
    
    /**
     * Очистка канваса
     */
    clearCanvas() {
        if (this.canvas.nodes.size === 0) {
            this.showNotification('Канвас уже пуст', 'info');
            return;
        }
        
        if (confirm('Вы уверены, что хотите очистить канвас? Несохраненные изменения будут потеряны.')) {
            this.canvas.clearGraph();
            this.currentFlow = null;
            this.updateFlowInfo();
            this.disableFlowActions();
            this.showNotification('Канвас очищен', 'success');
        }
    }
    
    /**
     * Отключение действий с флоу
     */
    disableFlowActions() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        
        if (saveBtn) saveBtn.disabled = true;
        if (runBtn) runBtn.disabled = true;
    }
}

// Экспортируем класс в глобальную область
window.Builder = Builder;

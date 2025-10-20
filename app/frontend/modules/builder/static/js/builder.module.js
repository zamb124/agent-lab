/**
 * Builder Module - Визуальный редактор flows
 */

export default class BuilderModule {
    constructor(app) {
        this.app = app;
        this.name = 'builder';
        this.version = '2.0.0';
        
        this.Canvas = null;
        this.DragDrop = null;
        this.Palette = null;
        this.PropertiesPanel = null;
        this.ElementSelector = null;
        this.Sidebar = null;
        
        this.currentCanvas = null;
        this.currentDragDrop = null;
        this.palette = null;
        this.propertiesPanel = null;
        this.sidebar = null;
        
        this.currentFlow = null;
        this.entryPointAgentType = null; // 'react' или 'stategraph'
        this.selectedNodes = new Set();
        this.selectedEdges = new Set();
        this.isInitialized = false;
    }
    
    async init() {
        console.log('🎨 Инициализация Builder модуля v2.0');
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        
        if (this.isBuilderPage()) {
            this.setupButtonListeners();
            await this.loadDependencies();
            await this.initializeBuilder();
        }
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.builder = this;
    }
    
    isBuilderPage() {
        return window.location.pathname.startsWith('/frontend/builder');
    }
    
    async loadDependencies() {
        if (this.Canvas) {
            return;
        }
        
        console.log('📦 Загружаем зависимости Builder...');
        
        try {
            const [Canvas, Palette, PropertiesPanel, ElementSelector, DragDrop, Sidebar] = await Promise.all([
                import('/static/builder/js/canvas.js'),
                import('/static/builder/js/palette.js'),
                import('/static/builder/js/properties-panel.js'),
                import('/static/builder/js/element-selector.js'),
                import('/static/builder/js/drag-drop.js'),
                import('/static/builder/js/sidebar.js')
            ]);
            
            this.Canvas = Canvas.default;
            this.Palette = Palette.default;
            this.PropertiesPanel = PropertiesPanel.default;
            this.ElementSelector = ElementSelector.default;
            this.DragDrop = DragDrop.default;
            this.Sidebar = Sidebar.default;
            
            console.log('✅ Зависимости Builder загружены');
        } catch (error) {
            console.error('❌ Ошибка загрузки зависимостей Builder:', error);
            throw error;
        }
    }
    
    async initializeBuilder() {
        if (this.isInitialized) return;
        
        console.log('🎨 Инициализация Builder на странице');
        
        const container = document.getElementById('builderContainer');
        const canvasEl = document.getElementById('builderCanvas');
        
        if (!container || !canvasEl) {
            console.warn('⚠️ Builder DOM элементы не найдены');
            return;
        }
        
        try {
            await this.loadDependencies();
            
            await this.initComponents();
            
            const flowId = this.getFlowIdFromPage();
            if (flowId) {
                await this.loadFlow(flowId);
            }
            
            this.initTheme();
            this.isInitialized = true;
            
            this.showNotification('Builder инициализирован', 'success');
            
        } catch (error) {
            console.error('❌ Ошибка инициализации Builder:', error);
            this.showNotification('Ошибка инициализации Builder: ' + error.message, 'error');
        }
    }
    
    async initComponents() {
        console.log('🔧 Инициализация компонентов Builder...');
        
        this.palette = new this.Palette(this);
        await this.palette.init();
        console.log('✅ Palette создана');
        
        // Инициализируем палитру в активном состоянии (нет flow)
        this.updatePaletteForAgentType(null);
        
        this.propertiesPanel = new this.PropertiesPanel(this);
        await this.propertiesPanel.init();
        console.log('✅ PropertiesPanel создана');
        
        const canvasEl = document.getElementById('builderCanvas');
        this.currentCanvas = new this.Canvas(canvasEl, this);
        this.canvas = this.currentCanvas;
        await this.currentCanvas.init();
        console.log('✅ Canvas создан');
        
        this.currentDragDrop = new this.DragDrop(this);
        this.dragDrop = this.currentDragDrop;
        await this.currentDragDrop.init();
        console.log('✅ DragDrop создан и инициализирован');
    }
    
    getFlowIdFromPage() {
        const match = window.location.pathname.match(/\/frontend\/builder\/flow\/([^\/]+)/);
        return match ? match[1] : null;
    }
    
    setupEventListeners() {
        document.addEventListener('htmx:afterSettle', (e) => {
            if (e.target.id === 'content' && this.isBuilderPage()) {
                this.onPageLoad();
            }
        });
        
        window.addEventListener('popstate', () => {
            if (this.isBuilderPage()) {
                this.onPageLoad();
            } else {
                this.onPageUnload();
            }
        });
        
        document.addEventListener('keydown', (e) => this.handleKeydown(e));
        document.addEventListener('contextmenu', (e) => this.handleContextMenu(e));
        document.addEventListener('click', () => this.hideContextMenu());
    }
    
    setupButtonListeners() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        const themeToggleBtn = document.getElementById('themeToggleBtn');
        const clearCanvasBtn = document.getElementById('clearCanvasBtn');
        const searchAddBtn = document.getElementById('searchAddBtn');
        const resetToCodeBtn = document.getElementById('resetToCodeBtn');
        
        if (saveBtn) saveBtn.addEventListener('click', () => this.saveCurrentFlow());
        if (runBtn) runBtn.addEventListener('click', () => this.runCurrentFlow());
        if (searchAddBtn) searchAddBtn.addEventListener('click', () => this.handleCreateNew());
        if (themeToggleBtn) themeToggleBtn.addEventListener('click', () => this.toggleTheme());
        if (clearCanvasBtn) clearCanvasBtn.addEventListener('click', () => this.clearCanvas());
        if (resetToCodeBtn) resetToCodeBtn.addEventListener('click', () => this.resetToCode());
    }
    
    async onPageLoad() {
        console.log('📄 Builder страница загружена');
        this.setupButtonListeners();
        await this.initializeBuilder();
    }
    
    onPageUnload() {
        console.log('👋 Уход со страницы Builder');
        this.cleanup();
    }
    
    async loadFlow(flowId) {
        try {
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            this.currentFlow = await response.json();

            // Получаем тип entry_point агента
            await this.updateEntryPointAgentType();

            // Всегда разворачиваем из graph_definition
            const centerPos = this.currentCanvas.getCenterPosition();
            await this.currentDragDrop.createFlowWithExpansion(
                {
                    id: this.currentFlow.flow_id,
                    name: this.currentFlow.name
                },
                centerPos
            );

            // Применяем визуальные данные из canvas_data
            if (this.currentFlow.canvas_data) {
                console.log('🎨 Применяем визуальные данные canvas:', this.currentFlow.canvas_data);
                await this.applyCanvasVisualData(this.currentFlow.canvas_data);
            }

            // Обновляем порты нод в зависимости от типа агента
            this.updateNodePortsForAgentType(this.entryPointAgentType);

            this.updateFlowInfo();
            this.enableFlowActions();
            
            this.showNotification(`Флоу "${this.currentFlow.name}" загружен`, 'success');
            
        } catch (error) {
            console.error('Ошибка загрузки флоу:', error);
            this.showNotification('Ошибка загрузки флоу: ' + error.message, 'error');
        }
    }
    
    async updateEntryPointAgentType() {
        console.log('🔍 updateEntryPointAgentType вызван, currentFlow:', this.currentFlow);
        console.log('🔍 entry_point_agent:', this.currentFlow?.entry_point_agent);

        const oldAgentType = this.entryPointAgentType;

        if (!this.currentFlow || !this.currentFlow.entry_point_agent) {
            console.log('⚠️ Нет entry_point_agent, сбрасываем палитру');
            this.entryPointAgentType = null;
            this.updatePaletteForAgentType(null);
            this.updateNodePortsForAgentType(null);
            return;
        }

        try {
            console.log('🔄 Запрашиваем агента:', this.currentFlow.entry_point_agent);
            const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(this.currentFlow.entry_point_agent)}`);
            console.log('📡 Ответ агента:', agentResponse.status);

            if (agentResponse.ok) {
                const agent = await agentResponse.json();
                console.log('🤖 Получен агент:', agent);
                console.log('🏷️ Тип агента:', agent.type);
                console.log('🔍 Все поля агента:', Object.keys(agent));

                this.entryPointAgentType = agent.type; // 'react' или 'stategraph'
                console.log('🎯 Entry point agent type установлен:', this.entryPointAgentType);

                this.updatePaletteForAgentType(this.entryPointAgentType);

                // Если тип агента изменился, обновляем порты нод
                if (oldAgentType !== this.entryPointAgentType) {
                    console.log('🔄 Тип агента изменился, обновляем порты нод');
                    this.updateNodePortsForAgentType(this.entryPointAgentType);
                }
            } else {
                console.log('❌ Агент не найден, сбрасываем');
                this.entryPointAgentType = null;
                this.updatePaletteForAgentType(null);
                this.updateNodePortsForAgentType(null);
            }
        } catch (error) {
            console.error('❌ Ошибка получения типа агента:', error);
            this.entryPointAgentType = null;
            this.updatePaletteForAgentType(null);
            this.updateNodePortsForAgentType(null);
        }
    }
    
    updateNodePortsForAgentType(agentType) {
        console.log('🔌 updateNodePortsForAgentType вызван, тип агента:', agentType);

        // Обновляем порты всех tool_node на canvas
        for (const [nodeId, node] of this.currentCanvas.nodes) {
            if (node.data.type === 'tool_node') {
                console.log('🔄 Обновляем порты tool_node:', nodeId);
                this.currentCanvas.updateNodePorts(node, agentType);
            }
        }
    }

    updatePaletteForAgentType(agentType) {
        console.log('🎨 updatePaletteForAgentType вызван, тип агента:', agentType);
        console.log('🎨 Текущий entryPointAgentType:', this.entryPointAgentType);

        if (!this.palette) {
            console.warn('⚠️ Palette не инициализирована');
            return;
        }

        const paletteElement = document.getElementById('nodePalette');
        if (!paletteElement) {
            console.warn('⚠️ Элемент nodePalette не найден');
            return;
        }

        const paletteItems = paletteElement.querySelectorAll('.palette-item');
        console.log('📋 Найдено элементов палитры:', paletteItems.length);

        paletteItems.forEach(item => {
            const nodeType = item.dataset.nodeType;
            let isEnabled = false;

            console.log(`🔍 Проверяем элемент ${nodeType} для типа агента ${agentType}`);

            if (!agentType) {
                // null: flow для создания, agent для entry_point
                isEnabled = (nodeType === 'flow_node' || nodeType === 'agent_node');
                console.log(`  📝 Для null: ${nodeType} -> ${isEnabled ? 'enabled' : 'disabled'}`);
            } else if (agentType === 'react') {
                // react: tool, agent (визуально ноды, но сохраняются в tools[])
                isEnabled = (nodeType === 'tool_node' || nodeType === 'agent_node');
                console.log(`  ⚛️ Для react: ${nodeType} -> ${isEnabled ? 'enabled' : 'disabled'}`);
            } else if (agentType === 'stategraph') {
                // stategraph: все ноды кроме flow
                isEnabled = (nodeType !== 'flow_node');
                console.log(`  📊 Для stategraph: ${nodeType} -> ${isEnabled ? 'enabled' : 'disabled'}`);
            }

            if (isEnabled) {
                item.classList.remove('disabled');
                item.setAttribute('draggable', 'true');
                console.log(`  ✅ ${nodeType} включен`);
            } else {
                item.classList.add('disabled');
                item.setAttribute('draggable', 'false');
                console.log(`  ❌ ${nodeType} отключен`);
            }
        });

        console.log('✅ updatePaletteForAgentType завершен');
    }
    
    async applyCanvasVisualData(canvasData) {
        console.log('🎨 Применяем визуальные данные canvas:', canvasData);

        // Применяем позиции и размеры к существующим нодам
        for (const nodeData of canvasData.nodes || []) {
            const existingNode = this.currentCanvas.nodes.get(nodeData.id);
            if (existingNode && nodeData.ui) {
                console.log('📍 Применяем позицию к ноде:', nodeData.id, nodeData.ui);
                existingNode.x = nodeData.ui.x || existingNode.x;
                existingNode.y = nodeData.ui.y || existingNode.y;
                existingNode.width = nodeData.ui.width || existingNode.width;
                existingNode.height = nodeData.ui.height || existingNode.height;
                existingNode.element.style.left = `${existingNode.x}px`;
                existingNode.element.style.top = `${existingNode.y}px`;
                existingNode.element.style.width = `${existingNode.width}px`;
                existingNode.element.style.height = `${existingNode.height}px`;
            }
        }

        // Восстанавливаем дополнительные ноды (например, tool_node), которые не входят в graph_definition
        const existingNodeIds = new Set(this.currentCanvas.nodes.keys());
        for (const nodeData of canvasData.nodes || []) {
            if (!existingNodeIds.has(nodeData.id)) {
                console.log('📦 Восстанавливаем дополнительную ноду:', nodeData.id);

                const position = {
                    x: nodeData.ui?.x || 100,
                    y: nodeData.ui?.y || 100
                };

                const size = {
                    width: nodeData.ui?.width || 180,
                    height: nodeData.ui?.height || 80
                };

                // Создаем дополнительную ноду
                if (this.currentDragDrop && typeof this.currentDragDrop.createNodeFromData === 'function') {
                    await this.currentDragDrop.createNodeFromData(nodeData, position, size);
                } else {
                    console.error('❌ createNodeFromData method not found on currentDragDrop');
                }
            }
        }

        // Восстанавливаем связи
        for (const edgeData of canvasData.edges || []) {
            console.log('🔗 Восстанавливаем связь:', edgeData);

            const sourceNode = this.currentCanvas.nodes.get(edgeData.source);
            const targetNode = this.currentCanvas.nodes.get(edgeData.target);

            if (sourceNode && targetNode) {
                // Проверяем, нет ли уже такой связи
                const existingEdge = Array.from(this.currentCanvas.edges.values()).find(
                    edge => edge.source === edgeData.source && edge.target === edgeData.target
                );

                if (!existingEdge) {
                    this.currentCanvas.createConnection(edgeData.source, edgeData.target);
                }
            } else {
                console.warn('⚠️ Не найдены ноды для связи:', edgeData.source, edgeData.target);
            }
        }

        console.log('✅ Визуальные данные canvas применены');
    }

    async saveCurrentFlow() {
        if (!this.currentFlow) {
            this.showNotification('Нет активного флоу для сохранения', 'warning');
            return;
        }
        
        try {
            const canvasData = this.currentCanvas.getGraphData();

            // Backend сам обработает преобразование для ReAct/StateGraph
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(this.currentFlow.flow_id)}/canvas`, {
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
    
    async runCurrentFlow() {
        if (!this.currentFlow) {
            this.showNotification('Нет активного флоу для запуска', 'warning');
            return;
        }
        
        if (this.app.chat) {
            this.app.chat.open({
                agent_id: this.currentFlow.flow_id,
                session_id: null,
                title: this.currentFlow.name
            });
        } else {
            console.error('Chat manager не инициализирован');
            this.showNotification('Чат недоступен. Попробуйте обновить страницу.', 'error');
        }
    }
    
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
            const hasFlow = Array.from(this.currentCanvas.nodes.values())
                .some(node => node.data.type === 'flow_node');
            
            if (hasFlow) {
                this.showNotification('На канвасе уже есть Flow', 'warning');
                return;
            }
            
            const response = await fetch('/frontend/api/flows/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            
            if (!response.ok) throw new Error('Ошибка создания Flow');
            
            const flowData = await response.json();
            
            const centerPos = this.currentCanvas.getCenterPosition();
            await this.currentCanvas.addNode({
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
            const response = await fetch('/frontend/api/agents/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            
            if (!response.ok) throw new Error('Ошибка создания Agent');
            
            const agentData = await response.json();
            
            const centerPos = this.currentCanvas.getCenterPosition();
            await this.currentCanvas.addNode({
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
            const response = await fetch('/frontend/api/tools/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            
            if (!response.ok) throw new Error('Ошибка создания Tool');
            
            const toolData = await response.json();
            
            const centerPos = this.currentCanvas.getCenterPosition();
            await this.currentCanvas.addNode({
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
    
    updateFlowInfo() {
        const nameEl = document.getElementById('currentFlowName');
        if (nameEl) {
            nameEl.textContent = this.currentFlow ? this.currentFlow.name : 'Выберите или создайте Flow';
        }
    }
    
    enableFlowActions() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        const resetBtn = document.getElementById('resetToCodeBtn');
        
        if (saveBtn) saveBtn.disabled = false;
        if (runBtn) runBtn.disabled = false;
        if (resetBtn) resetBtn.disabled = false;
    }
    
    disableFlowActions() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        const resetBtn = document.getElementById('resetToCodeBtn');
        
        if (saveBtn) saveBtn.disabled = true;
        if (runBtn) runBtn.disabled = true;
        if (resetBtn) resetBtn.disabled = true;
    }
    
    handleKeydown(e) {
        if (e.ctrlKey && e.key === 's') {
            e.preventDefault();
            this.saveCurrentFlow();
        }
        
        if (e.key === 'Delete') {
            this.deleteSelected();
        }
        
        if (e.key === 'Escape') {
            this.clearSelection();
            this.hideContextMenu();
        }
        
        if (e.ctrlKey && e.key === 'a') {
            e.preventDefault();
            this.selectAll();
        }
    }
    
    handleContextMenu(e) {
        if (!this.isBuilderPage()) {
            return;
        }
        
        const target = e.target.closest('.canvas-node, .edge');
        
        if (target) {
            e.preventDefault();
            this.showContextMenu(e.clientX, e.clientY, target);
        } else {
            this.hideContextMenu();
        }
    }
    
    showContextMenu(x, y, target) {
        const contextMenu = document.getElementById('contextMenu');
        if (!contextMenu) return;
        
        contextMenu.classList.remove('hidden');
        contextMenu.style.left = x + 'px';
        contextMenu.style.top = y + 'px';
        contextMenu.style.display = 'block';
        
        const items = contextMenu.querySelectorAll('.context-menu-item');
        items.forEach(item => {
            item.onclick = () => {
                const action = item.dataset.action;
                this.handleContextAction(action, target);
                this.hideContextMenu();
            };
        });
    }
    
    hideContextMenu() {
        const contextMenu = document.getElementById('contextMenu');
        if (contextMenu) {
            contextMenu.classList.add('hidden');
            contextMenu.style.display = 'none';
        }
    }
    
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
    
    editElement(target) {
        console.log('Редактирование элемента:', target);
    }
    
    duplicateElement(target) {
        console.log('Дублирование элемента:', target);
    }
    
    deleteElement(target) {
        if (target.classList.contains('canvas-node')) {
            const nodeId = target.dataset.nodeId;
            this.currentCanvas.removeNode(nodeId);
        } else if (target.classList.contains('edge')) {
            const edgeId = target.dataset.edgeId;
            this.currentCanvas.removeEdge(edgeId);
        }
    }
    
    deleteSelected() {
        this.selectedNodes.forEach(nodeId => {
            this.currentCanvas.removeNode(nodeId);
        });
        
        this.selectedEdges.forEach(edgeId => {
            this.currentCanvas.removeEdge(edgeId);
        });
        
        this.clearSelection();
    }
    
    clearSelection() {
        this.selectedNodes.clear();
        this.selectedEdges.clear();
        
        document.querySelectorAll('.canvas-node.selected').forEach(node => {
            node.classList.remove('selected');
        });
        
        document.querySelectorAll('.edge.selected').forEach(edge => {
            edge.classList.remove('selected');
        });
    }
    
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
    
    initTheme() {
        const savedTheme = localStorage.getItem('theme') || 'dark';
        document.documentElement.setAttribute('data-theme', savedTheme);
    }
    
    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        this.showNotification(`Тема переключена на ${newTheme === 'dark' ? 'темную' : 'светлую'}`, 'info', 2000);
    }
    
    clearCanvas() {
        if (this.currentCanvas.nodes.size === 0) {
            this.showNotification('Канвас уже пуст', 'info');
            return;
        }
        
        if (confirm('Вы уверены, что хотите очистить канвас? Несохраненные изменения будут потеряны.')) {
            this.currentCanvas.clearGraph();
            this.currentFlow = null;
            this.entryPointAgentType = null;
            this.updateFlowInfo();
            this.disableFlowActions();
            // Сбрасываем палитру в активное состояние
            this.updatePaletteForAgentType(null);
            this.showNotification('Канвас очищен', 'success');
        }
    }
    
    async resetToCode() {
        if (!this.currentFlow) {
            this.showNotification('Нет активного флоу', 'warning');
            return;
        }
        
        if (!confirm('Сбросить к коду? Canvas будет пересоздан из graph_definition.')) {
            return;
        }
        
        try {
            const flowId = this.currentFlow.flow_id;
            
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}/canvas`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({nodes: [], edges: [], entry_point: null})
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            this.currentCanvas.clearGraph();
            
            await this.loadFlow(flowId);
            this.showNotification('Canvas сброшен к коду и перезагружен', 'success');
            
        } catch (error) {
            console.error('Ошибка сброса:', error);
            this.showNotification('Ошибка: ' + error.message, 'error');
        }
    }
    
    showNotification(message, type = 'info', duration = 3000) {
        if (this.app && this.app.showNotification) {
            const appType = {
                'success': 'success',
                'error': 'danger',
                'warning': 'warning',
                'info': 'info'
            }[type] || 'info';
            
            const appDuration = (type === 'error' || type === 'warning') ? 8000 : duration;
            
            this.app.showNotification(message, appType, appDuration);
        } else {
            const icon = {
                'success': '✅',
                'error': '❌',
                'warning': '⚠️',
                'info': 'ℹ️'
            }[type] || 'ℹ️';
            
            console.log(`${icon} ${message}`);
        }
    }
    
    openFlow(flowId) {
        window.location.href = `/frontend/builder/flow/${flowId}`;
    }
    
    createNewFlow() {
        console.log('Creating new flow');
    }
    
    cleanup() {
        if (this.currentCanvas && typeof this.currentCanvas.destroy === 'function') {
            this.currentCanvas.destroy();
        }
        if (this.currentDragDrop && typeof this.currentDragDrop.destroy === 'function') {
            this.currentDragDrop.destroy();
        }
        
        this.currentCanvas = null;
        this.currentDragDrop = null;
    }
    
    destroy() {
        console.log('🧹 Builder модуль выгружен');
        this.cleanup();
    }
}

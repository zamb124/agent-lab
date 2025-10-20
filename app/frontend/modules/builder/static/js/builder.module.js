/**
 * Builder Module v3.0 - Визуальный редактор flows
 * Полностью переписан на ООП архитектуре
 */

export default class BuilderModule {
    constructor(app) {
        this.app = app;
        this.name = 'builder';
        this.version = '3.0.0';
        
        // Зависимости (lazy load)
        this.CanvasCore = null;
        this.Palette = null;
        this.PropertiesPanel = null;
        this.Sidebar = null;
        
        // Компоненты
        this.canvas = null;
        this.palette = null;
        this.propertiesPanel = null;
        this.sidebar = null;
        
        // Состояние
        this.currentFlow = null;
        this.entryPointAgentType = null;
        this.isInitialized = false;
    }
    
    /**
     * Инициализация модуля
     */
    async init() {
        console.log('🎨 Builder Module v3.0 - Новая ООП архитектура');
        console.log('📍 Current path:', window.location.pathname);
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        
        if (this.isBuilderPage()) {
            console.log('✅ На странице Builder, загружаем...');
            await this.onPageLoad();
        } else {
            console.log('⏭️ Не страница Builder, пропускаем инициализацию');
        }
        
        return this;
    }
    
    /**
     * Глобальные функции
     */
    setupGlobalFunctions() {
        window.builder = this;
        window.openFlow = (flowId) => this.openFlow(flowId);
        window.saveFlow = () => this.saveFlow();
        window.clearCanvas = () => this.clearCanvas();
    }
    
    /**
     * Проверка страницы Builder
     */
    isBuilderPage() {
        return window.location.pathname.startsWith('/frontend/builder');
    }
    
    /**
     * Event listeners для HTMX навигации
     */
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
    }
    
    /**
     * Загрузка зависимостей
     */
    async loadDependencies() {
        if (this.CanvasCore) return;
        
        console.log('📦 Загружаем компоненты Builder...');
        
        const [CanvasCore, Palette, PropertiesPanel, Sidebar] = await Promise.all([
            import('/static/builder/js/canvas/CanvasCore.js'),
            import('/static/builder/js/palette.js'),
            import('/static/builder/js/properties-panel.js'),
            import('/static/builder/js/sidebar.js')
        ]);
        
        this.CanvasCore = CanvasCore.CanvasCore;
        this.Palette = Palette.default;
        this.PropertiesPanel = PropertiesPanel.default;
        this.Sidebar = Sidebar.default;
        
        console.log('✅ Компоненты Builder загружены');
    }
    
    /**
     * Загрузка страницы Builder
     */
    async onPageLoad() {
        console.log('📄 Builder страница загружена');
        
        this.setupButtonListeners();
        await this.initializeBuilder();
    }
    
    /**
     * Выгрузка страницы
     */
    onPageUnload() {
        console.log('👋 Уход со страницы Builder');
        this.cleanup();
    }
    
    /**
     * Инициализация Builder
     */
    async initializeBuilder() {
        if (this.isInitialized) {
            console.log('⏭️ Builder уже инициализирован');
            return;
        }
        
        console.log('🎨 Инициализация Builder...');
        
        const container = document.getElementById('builderContainer');
        const canvasEl = document.getElementById('builderCanvas');
        
        console.log('🔍 DOM элементы:', { container: !!container, canvasEl: !!canvasEl });
        
        if (!container || !canvasEl) {
            console.warn('⚠️ Builder DOM элементы не найдены');
            return;
        }

        try {
            console.log('📦 Начинаем загрузку зависимостей...');
            await this.loadDependencies();
            console.log('✅ Зависимости загружены');
            console.log('🔍 CanvasCore class:', this.CanvasCore);
            
            // Создаем Canvas (ООП архитектура)
            console.log('🏗️ Создаем экземпляр CanvasCore...');
            this.canvas = new this.CanvasCore(canvasEl, this);
            console.log('✅ Экземпляр создан, вызываем init()...');
            await this.canvas.init();
            console.log('✅ Canvas.init() завершен');
            
            // Создаем UI компоненты
            console.log('🎨 Создаем UI компоненты...');
            this.palette = new this.Palette(this);
            this.propertiesPanel = new this.PropertiesPanel(this);
            this.sidebar = new this.Sidebar(this);
            
            // Подписываемся на события Canvas
            console.log('🔗 Подписываемся на события...');
            this.subscribeToCanvasEvents();
            
            // Кнопки управления
            console.log('🔘 Настраиваем кнопки zoom...');
            this.setupZoomButtons();
            
            this.isInitialized = true;
            
            console.log('✅ Builder полностью инициализирован');
            
            // Автозагрузка flow из URL
            await this.loadFlowFromURL();
            
        } catch (error) {
            console.error('❌ Ошибка инициализации Builder:', error);
            this.showNotification('Ошибка инициализации Builder', 'danger');
        }
    }
    
    /**
     * Подписка на события Canvas
     */
    subscribeToCanvasEvents() {
        this.canvas.on('node:added', async ({ node }) => {
            console.log('Нода добавлена:', node.id);
            this.palette?.updatePaletteState();
            
            // Если добавлен FlowNode
            if (node.type === 'flow_node') {
                // Если новый Flow (без flow_id) - сразу сохраняем чтобы создать в БД
                if (!node.data.params?.flow_id) {
                    const result = await node.save();
                    if (!result.success) {
                        this.showNotification('Ошибка создания Flow: ' + result.error, 'danger');
                        return;
                    }
                }
                
                // Обновляем состояние после сохранения
                if (node.flowData) {
                    this.currentFlow = node.flowData;
                } else if (node.data.params?.flow_id) {
                    node.flowData = await node.fetchFlowData(node.data.params.flow_id);
                    this.currentFlow = node.flowData;
                }
                
                this.updateFlowInfo();
                this.enableFlowActions();
                await this.updateEntryPointAgentType();
                
                // Автосохранение canvas_data
                await this.saveCanvasData();
            }
            
            // Если добавлен AgentNode
            if (node.type === 'agent_node') {
                // Если новый агент - сразу сохраняем чтобы создать в БД
                const agentId = node.data.params?.agent_id;
                if (!agentId || agentId.startsWith('new_')) {
                    const result = await node.save();
                    if (!result.success) {
                        this.showNotification('Ошибка создания агента: ' + result.error, 'danger');
                    }
                }
            }
            
            // Если есть currentFlow - автосохранение при добавлении любой ноды
            if (this.currentFlow && node.type !== 'flow_node') {
                await this.saveCanvasData();
            }
        });
        
        this.canvas.on('node:removed', ({ nodeId }) => {
            console.log('Нода удалена:', nodeId);
            this.palette?.updatePaletteState();
            
            // Если удален FlowNode - деактивируем кнопки
            const hasFlow = Array.from(this.canvas.nodes.values()).some(n => n.type === 'flow_node');
            if (!hasFlow) {
                this.currentFlow = null;
                this.disableFlowActions();
            }
        });
        
        this.canvas.on('selection:changed', ({ nodes, edges }) => {
            if (nodes.length === 1) {
                this.propertiesPanel?.show(nodes[0]);
            } else if (nodes.length === 0) {
                this.propertiesPanel?.hide();
            }
        });
        
        this.canvas.on('edge:created', ({ edge }) => {
            console.log('Связь создана:', edge.id);
            this.updateFlowEntryPointIfNeeded(edge);
            this.palette?.updatePaletteState();
        });
        
        this.canvas.on('graph:loaded', () => {
            console.log('Граф загружен');
            this.palette?.updatePaletteState();
        });
        
        this.canvas.on('node:edit', ({ node }) => {
            console.log('✏️ Редактирование ноды:', node.id);
            this.propertiesPanel?.show(node);
        });
    }
    
    /**
     * Настройка кнопок zoom
     */
    setupZoomButtons() {
        const zoomInBtn = document.getElementById('zoomInBtn');
        const zoomOutBtn = document.getElementById('zoomOutBtn');
        const fitToScreenBtn = document.getElementById('fitToScreenBtn');
        
        if (zoomInBtn) {
            zoomInBtn.addEventListener('click', () => {
                this.canvas.interactionManager.zoomIn();
            });
        }
        
        if (zoomOutBtn) {
            zoomOutBtn.addEventListener('click', () => {
                this.canvas.interactionManager.zoomOut();
            });
        }
        
        if (fitToScreenBtn) {
            fitToScreenBtn.addEventListener('click', () => {
                this.canvas.interactionManager.fitToScreen();
            });
        }
    }
    
    /**
     * Настройка кнопок в header
     */
    setupButtonListeners() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        const clearBtn = document.getElementById('clearCanvasBtn');
        
        if (saveBtn) {
            saveBtn.addEventListener('click', () => this.saveFlow());
        }
        
        if (runBtn) {
            runBtn.addEventListener('click', () => this.runFlow());
        }
        
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearCanvas());
        }
    }
    
    /**
     * Запуск flow для тестирования
     */
    async runFlow() {
        if (!this.currentFlow) {
            this.showNotification('Нет открытого flow', 'warning');
            return;
        }
        
        console.log('▶️ Запуск flow:', this.currentFlow.flow_id);
        
        // TODO: Интеграция с тестовым запуском flow
        this.showNotification('Функция запуска в разработке', 'info');
    }
    
    /**
     * Загрузка flow из URL
     */
    async loadFlowFromURL() {
        // Проверяем URL: /frontend/builder/flow/{flow_id}
        const pathMatch = window.location.pathname.match(/\/frontend\/builder\/flow\/([^/]+)/);
        
        if (pathMatch) {
            const flowId = pathMatch[1];
            console.log('🔗 Обнаружен flow в URL:', flowId);
            await this.openAndExpandFlow(flowId);
            return;
        }
        
        // Или через query параметр
        const urlParams = new URLSearchParams(window.location.search);
        const flowIdParam = urlParams.get('flow_id');
        
        if (flowIdParam) {
            console.log('🔗 Обнаружен flow в параметрах:', flowIdParam);
            await this.openAndExpandFlow(flowIdParam);
        }
    }
    
    /**
     * Открытие и рекурсивное разворачивание flow
     */
    async openAndExpandFlow(flowId) {
        try {
            console.log('📂 Загружаем и разворачиваем flow:', flowId);
            
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            this.currentFlow = await response.json();
            
            // Обновляем тип entry_point агента
            await this.updateEntryPointAgentType();
            
            // Очищаем canvas
            this.canvas.clearGraph();
            
            // Создаем FlowNode в центре
            const centerPos = this.canvas.getCenterPosition();
            
            const flowNodeData = {
                id: `flow_${Date.now()}`,
                type: 'flow_node',
                params: {
                    flow_id: flowId,
                    isEntryPoint: true
                },
                ui: {
                    x: centerPos.x - 100,
                    y: centerPos.y - 50,
                    width: 200,
                    height: 100
                }
            };
            
            // Добавляем FlowNode (автоматически развернется через autoExpand)
            const flowNode = await this.canvas.addNode(flowNodeData);
            
            // Fit to screen после разворачивания
            setTimeout(() => {
                this.canvas.interactionManager.fitToScreen();
            }, 500);
            
            this.updateFlowInfo();
            this.enableFlowActions();
            this.showNotification(`Flow "${this.currentFlow.name}" развернут`, 'success');
            
        } catch (error) {
            console.error('❌ Ошибка разворачивания flow:', error);
            this.showNotification('Ошибка загрузки flow', 'danger');
        }
    }
    
    /**
     * Открытие flow (без разворачивания)
     */
    async openFlow(flowId) {
        try {
            console.log('📂 Загружаем flow:', flowId);
            
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            this.currentFlow = await response.json();
            
            // Обновляем тип entry_point агента
            await this.updateEntryPointAgentType();
            
            // Загружаем граф из graph_definition
            if (this.currentFlow.graph_definition) {
                await this.canvas.loadGraph(this.currentFlow.graph_definition);
            }
            
            // Применяем визуальные данные из canvas_data
            if (this.currentFlow.canvas_data) {
                this.applyCanvasVisualData(this.currentFlow.canvas_data);
            }
            
            this.updateFlowInfo();
            this.enableFlowActions();
            this.showNotification(`Flow "${this.currentFlow.name}" загружен`, 'success');
            
        } catch (error) {
            console.error('❌ Ошибка загрузки flow:', error);
            this.showNotification('Ошибка загрузки flow', 'danger');
        }
    }
    
    /**
     * Обновление типа entry_point агента
     */
    async updateEntryPointAgentType() {
        if (!this.currentFlow?.entry_point_agent) {
            this.entryPointAgentType = null;
            this.palette?.updateForAgentType(null);
            return;
        }
        
        try {
            const response = await fetch(`/frontend/api/agents/${encodeURIComponent(this.currentFlow.entry_point_agent)}`);
            
            if (response.ok) {
                const agent = await response.json();
                this.entryPointAgentType = agent.type;
                this.palette?.updateForAgentType(agent.type);
                
                console.log('🎯 Entry point agent type:', this.entryPointAgentType);
            }
        } catch (error) {
            console.error('❌ Ошибка получения типа агента:', error);
        }
    }
    
    /**
     * Применение визуальных данных
     */
    applyCanvasVisualData(canvasData) {
        if (canvasData.zoom) {
            this.canvas.zoom = canvasData.zoom;
        }
        
        if (canvasData.panX !== undefined) {
            this.canvas.panX = canvasData.panX;
        }
        
        if (canvasData.panY !== undefined) {
            this.canvas.panY = canvasData.panY;
        }
        
        this.canvas.updateTransform();
    }
    
    /**
     * Быстрое сохранение canvas_data (только позиции нод)
     */
    async saveCanvasData() {
        if (!this.currentFlow) {
            return;
        }
        
        try {
            console.log('💾 Автосохранение canvas_data...');
            
            const graphData = this.canvas.getGraphData();
            
            const canvasData = {
                zoom: this.canvas.zoom,
                panX: this.canvas.panX,
                panY: this.canvas.panY,
                nodes: {}
            };
            
            this.canvas.nodes.forEach((node, nodeId) => {
                canvasData.nodes[nodeId] = {
                    x: node.x,
                    y: node.y,
                    width: node.width,
                    height: node.height
                };
            });
            
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(this.currentFlow.flow_id)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    graph_definition: graphData,
                    canvas_data: canvasData
                })
            });
            
            if (response.ok) {
                console.log('✅ Canvas data автосохранен');
            }
            
        } catch (error) {
            console.error('❌ Ошибка автосохранения canvas_data:', error);
        }
    }
    
    /**
     * Сохранение flow
     */
    async saveFlow() {
        if (!this.currentFlow) {
            this.showNotification('Нет открытого flow', 'warning');
            return;
        }
        
        try {
            console.log('💾 Сохранение flow...');
            
            // Находим FlowNode на canvas
            const flowNode = Array.from(this.canvas.nodes.values()).find(n => n.type === 'flow_node');
            
            if (!flowNode) {
                this.showNotification('На canvas нет FlowNode', 'warning');
                return;
            }
            
            // Вызываем рекурсивное сохранение у FlowNode
            const result = await flowNode.save();
            
            if (result.success) {
                this.showNotification('Flow сохранен', 'success');
            } else {
                this.showNotification('Ошибка сохранения: ' + result.error, 'danger');
            }
            
        } catch (error) {
            console.error('❌ Ошибка сохранения flow:', error);
            this.showNotification('Ошибка сохранения flow', 'danger');
        }
    }
    
    /**
     * Очистка canvas
     */
    clearCanvas() {
        if (confirm('Очистить canvas? Несохраненные изменения будут потеряны.')) {
            this.canvas.clearGraph();
            this.currentFlow = null;
            this.disableFlowActions();
            this.showNotification('Canvas очищен', 'success');
        }
    }
    
    /**
     * Обновление entry_point при создании связи
     */
    async updateFlowEntryPointIfNeeded(edge) {
        console.log('🔗 updateFlowEntryPointIfNeeded вызван:', edge);
        
        if (!this.currentFlow) {
            console.log('⚠️ Нет currentFlow');
            return;
        }
        
        const sourceNode = this.canvas.nodes.get(edge.source);
        console.log('🔍 Source node:', {
            id: edge.source,
            node: sourceNode,
            type: sourceNode?.type,
            isEntryPoint: sourceNode?.data.params?.isEntryPoint
        });
        
        if (sourceNode?.type === 'flow_node' && sourceNode.data.params?.isEntryPoint) {
            const targetNode = this.canvas.nodes.get(edge.target);
            
            if (targetNode?.type === 'agent_node') {
                const agentId = targetNode.data.params?.agent_id;
                
                console.log('🔗 Создана связь Flow → Agent:', {
                    agentId,
                    'agentData': targetNode.agentData,
                    'params.type': targetNode.data.params?.type,
                    'agentData.type': targetNode.agentData?.type
                });
                
                if (agentId && agentId !== this.currentFlow.entry_point_agent) {
                    await this.updateFlowEntryPointAgent(this.currentFlow.flow_id, agentId, targetNode);
                }
            }
        }
    }
    
    /**
     * Обновление entry_point_agent у flow
     */
    async updateFlowEntryPointAgent(flowId, agentId, agentNode = null) {
        try {
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entry_point_agent: agentId })
            });
            
            if (response.ok) {
                this.currentFlow.entry_point_agent = agentId;
                
                // Если есть агент-нода, берем тип из неё напрямую
                if (agentNode) {
                    const agentType = agentNode.agentData?.type || agentNode.data.params?.type;
                    console.log('🎯 Обновление entryPointAgentType:', {
                        'agentType': agentType,
                        'agentData': agentNode.agentData,
                        'params': agentNode.data.params
                    });
                    
                    if (agentType) {
                        this.entryPointAgentType = agentType;
                        this.palette?.updateForAgentType(agentType);
                        console.log('✅ Entry point agent type установлен:', agentType);
                    } else {
                        console.warn('⚠️ Тип агента не найден, загружаем из API');
                        await this.updateEntryPointAgentType();
                    }
                } else {
                    await this.updateEntryPointAgentType();
                }
                
                console.log('✅ Entry point обновлен:', agentId);
            }
        } catch (error) {
            console.error('❌ Ошибка обновления entry_point:', error);
        }
    }
    
    /**
     * Обновление информации о flow
     */
    updateFlowInfo() {
        const flowNameEl = document.getElementById('currentFlowName');
        if (flowNameEl && this.currentFlow) {
            flowNameEl.textContent = this.currentFlow.name;
        }
    }
    
    /**
     * Активация кнопок flow
     */
    enableFlowActions() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        
        if (saveBtn) saveBtn.disabled = false;
        if (runBtn) runBtn.disabled = false;
    }
    
    /**
     * Деактивация кнопок flow
     */
    disableFlowActions() {
        const saveBtn = document.getElementById('saveFlowBtn');
        const runBtn = document.getElementById('runFlowBtn');
        
        if (saveBtn) saveBtn.disabled = true;
        if (runBtn) runBtn.disabled = true;
    }
    
    /**
     * Показ уведомления
     */
    showNotification(message, type = 'info') {
        console.log(`[${type.toUpperCase()}] ${message}`);
        
        // Используем глобальную систему уведомлений
        if (window.app && window.app.showNotification) {
            window.app.showNotification(message, type);
        } else {
            // Fallback если app не загружен
            if (type === 'error' || type === 'danger') {
                alert(message);
            }
        }
    }
    
    /**
     * Cleanup при выгрузке
     */
    cleanup() {
        if (this.canvas) {
            this.canvas.destroy();
            this.canvas = null;
        }
        
        this.palette = null;
        this.propertiesPanel = null;
        this.sidebar = null;
        this.currentFlow = null;
        this.isInitialized = false;
    }
    
    /**
     * Destroy модуля
     */
    destroy() {
        console.log('🧹 Builder модуль выгружен');
        this.cleanup();
    }
}


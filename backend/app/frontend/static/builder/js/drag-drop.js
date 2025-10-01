/**
 * Drag & Drop функциональность для Builder
 */
class BuilderDragDrop {
    constructor(builder) {
        this.builder = builder;
        
        // Состояние
        this.isDragging = false;
        this.draggedElement = null;
        this.draggedData = null;
        this.dropZone = null;
        
        // Настройки
        this.config = {
            dragThreshold: 5, // Минимальное расстояние для начала drag
            dropZoneClass: 'drop-zone',
            draggingClass: 'dragging'
        };
    }
    
    /**
     * Инициализация Drag & Drop
     */
    async init() {
        this.setupDropZone();
        this.setupDragSources();
    }
    
    /**
     * Настройка зоны сброса
     */
    setupDropZone() {
        const canvasContainer = document.getElementById('canvasContainer');
        if (!canvasContainer) return;
        
        // Создаем индикатор зоны сброса
        this.dropZone = document.createElement('div');
        this.dropZone.className = this.config.dropZoneClass;
        this.dropZone.innerHTML = `
            <div class="drop-zone-content">
                <i class="icon-plus"></i>
                <span>Перетащите элемент сюда</span>
            </div>
        `;
        canvasContainer.appendChild(this.dropZone);
        
        // Обработчики для зоны сброса
        canvasContainer.addEventListener('dragover', (e) => this.handleDragOver(e));
        canvasContainer.addEventListener('dragenter', (e) => this.handleDragEnter(e));
        canvasContainer.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        canvasContainer.addEventListener('drop', (e) => this.handleDrop(e));
    }
    
    /**
     * Настройка источников перетаскивания
     */
    setupDragSources() {
        // Настраиваем drag для элементов сайдбара
        this.setupSidebarDrag();
        
        // Переодически проверяем новые элементы
        this.observer = new MutationObserver(() => {
            this.setupSidebarDrag();
        });
        
        const sidebar = document.getElementById('builderSidebar');
        if (sidebar) {
            this.observer.observe(sidebar, {
                childList: true,
                subtree: true
            });
        }
    }
    
    /**
     * Настройка drag для элементов сайдбара
     */
    setupSidebarDrag() {
        // Flows
        document.querySelectorAll('.flow-card[draggable="true"]').forEach(card => {
            if (!card.dataset.dragSetup) {
                this.setupElementDrag(card, 'flow');
                card.dataset.dragSetup = 'true';
            }
        });
        
        // Agents
        document.querySelectorAll('.agent-card[draggable="true"]').forEach(card => {
            if (!card.dataset.dragSetup) {
                this.setupElementDrag(card, 'agent');
                card.dataset.dragSetup = 'true';
            }
        });
        
        // Tools
        document.querySelectorAll('.tool-card[draggable="true"]').forEach(card => {
            if (!card.dataset.dragSetup) {
                this.setupElementDrag(card, 'tool');
                card.dataset.dragSetup = 'true';
            }
        });
    }
    
    /**
     * Настройка drag для конкретного элемента
     */
    setupElementDrag(element, type) {
        element.addEventListener('dragstart', (e) => this.handleDragStart(e, type));
        element.addEventListener('dragend', (e) => this.handleDragEnd(e));
        
        // Альтернативный drag через mouse events для лучшего контроля
        let mouseDownPos = null;
        let isDragStarted = false;
        
        element.addEventListener('mousedown', (e) => {
            // Игнорируем клики по кнопкам действий
            if (e.target.closest('.card-actions')) return;
            
            mouseDownPos = { x: e.clientX, y: e.clientY };
            isDragStarted = false;
        });
        
        element.addEventListener('mousemove', (e) => {
            if (!mouseDownPos || isDragStarted) return;
            
            const distance = Math.sqrt(
                Math.pow(e.clientX - mouseDownPos.x, 2) + 
                Math.pow(e.clientY - mouseDownPos.y, 2)
            );
            
            if (distance > this.config.dragThreshold) {
                this.startCustomDrag(element, type, e);
                isDragStarted = true;
            }
        });
        
        element.addEventListener('mouseup', () => {
            mouseDownPos = null;
            isDragStarted = false;
        });
    }
    
    /**
     * Обработка начала drag
     */
    handleDragStart(e, type) {
        this.isDragging = true;
        this.draggedElement = e.target;
        
        // Получаем данные элемента
        this.draggedData = this.getElementData(e.target, type);
        
        // Устанавливаем данные для transfer
        e.dataTransfer.setData('application/json', JSON.stringify({
            type: type,
            data: this.draggedData
        }));
        
        e.dataTransfer.effectAllowed = 'copy';
        
        // Добавляем класс для визуального эффекта
        e.target.classList.add(this.config.draggingClass);
        
        console.log('Drag started:', type, this.draggedData);
    }
    
    /**
     * Начало кастомного drag
     */
    startCustomDrag(element, type, e) {
        this.isDragging = true;
        this.draggedElement = element;
        this.draggedData = this.getElementData(element, type);
        
        // Создаем ghost элемент
        const ghost = this.createDragGhost(element);
        document.body.appendChild(ghost);
        
        // Показываем зону сброса
        this.showDropZone();
        
        // Добавляем класс для визуального эффекта
        element.classList.add(this.config.draggingClass);
        
        // Обработчики для кастомного drag
        const handleMouseMove = (e) => {
            this.updateDragGhost(ghost, e);
        };
        
        const handleMouseUp = (e) => {
            document.removeEventListener('mousemove', handleMouseMove);
            document.removeEventListener('mouseup', handleMouseUp);
            
            // Проверяем, над канвасом ли мы
            const canvasContainer = document.getElementById('canvasContainer');
            const rect = canvasContainer.getBoundingClientRect();
            
            if (e.clientX >= rect.left && e.clientX <= rect.right &&
                e.clientY >= rect.top && e.clientY <= rect.bottom) {
                
                // Создаем событие drop
                const dropEvent = new MouseEvent('drop', {
                    clientX: e.clientX,
                    clientY: e.clientY,
                    bubbles: true
                });
                
                this.handleDrop(dropEvent);
            }
            
            // Очищаем
            this.cleanupCustomDrag(ghost);
        };
        
        document.addEventListener('mousemove', handleMouseMove);
        document.addEventListener('mouseup', handleMouseUp);
    }
    
    /**
     * Создание ghost элемента для drag
     */
    createDragGhost(element) {
        const ghost = element.cloneNode(true);
        ghost.classList.add('drag-ghost');
        ghost.style.position = 'fixed';
        ghost.style.pointerEvents = 'none';
        ghost.style.zIndex = '1000';
        ghost.style.opacity = '0.8';
        ghost.style.transform = 'scale(0.9)';
        ghost.style.width = element.offsetWidth + 'px';
        
        return ghost;
    }
    
    /**
     * Обновление позиции ghost элемента
     */
    updateDragGhost(ghost, e) {
        ghost.style.left = (e.clientX + 10) + 'px';
        ghost.style.top = (e.clientY + 10) + 'px';
    }
    
    /**
     * Очистка кастомного drag
     */
    cleanupCustomDrag(ghost) {
        if (ghost && ghost.parentNode) {
            ghost.parentNode.removeChild(ghost);
        }
        
        this.hideDropZone();
        
        if (this.draggedElement) {
            this.draggedElement.classList.remove(this.config.draggingClass);
        }
        
        this.isDragging = false;
        this.draggedElement = null;
        this.draggedData = null;
    }
    
    /**
     * Получение данных элемента
     */
    getElementData(element, type) {
        switch (type) {
            case 'flow':
                return {
                    id: element.dataset.flowId,
                    type: 'flow',
                    name: element.querySelector('.card-title')?.textContent || 'Flow'
                };
                
            case 'agent':
                return {
                    id: element.dataset.agentId,
                    type: 'agent',
                    name: element.querySelector('.card-title')?.textContent || 'Agent'
                };
                
            case 'tool':
                return {
                    id: element.dataset.toolId,
                    type: 'tool',
                    name: element.querySelector('.card-title')?.textContent || 'Tool'
                };
                
            default:
                return null;
        }
    }
    
    /**
     * Обработка drag over
     */
    handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    }
    
    /**
     * Обработка drag enter
     */
    handleDragEnter(e) {
        e.preventDefault();
        this.showDropZone();
    }
    
    /**
     * Обработка drag leave
     */
    handleDragLeave(e) {
        // Проверяем, действительно ли мы покинули зону
        const rect = e.currentTarget.getBoundingClientRect();
        if (e.clientX < rect.left || e.clientX > rect.right ||
            e.clientY < rect.top || e.clientY > rect.bottom) {
            this.hideDropZone();
        }
    }
    
    /**
     * Обработка drop
     */
    async handleDrop(e) {
        e.preventDefault();
        this.hideDropZone();
        
        let dropData = null;
        
        // Пытаемся получить данные из dataTransfer
        try {
            const transferData = e.dataTransfer?.getData('application/json');
            if (transferData) {
                dropData = JSON.parse(transferData);
            }
        } catch (error) {
            console.warn('Не удалось получить данные из dataTransfer:', error);
        }
        
        // Если нет данных в dataTransfer, используем текущие draggedData
        if (!dropData && this.draggedData) {
            dropData = {
                type: this.draggedData.type,
                data: this.draggedData
            };
        }
        
        if (!dropData) {
            console.warn('Нет данных для drop');
            return;
        }
        
        // Вычисляем позицию на канвасе
        const position = this.getCanvasPosition(e);
        
        // Создаем элемент на канвасе
        await this.createCanvasElement(dropData, position);
        
        console.log('Drop completed:', dropData, position);
    }
    
    /**
     * Обработка окончания drag
     */
    handleDragEnd(e) {
        this.hideDropZone();
        
        if (this.draggedElement) {
            this.draggedElement.classList.remove(this.config.draggingClass);
        }
        
        this.isDragging = false;
        this.draggedElement = null;
        this.draggedData = null;
    }
    
    /**
     * Показать зону сброса
     */
    showDropZone() {
        if (this.dropZone) {
            this.dropZone.classList.add('active');
        }
    }
    
    /**
     * Скрыть зону сброса
     */
    hideDropZone() {
        if (this.dropZone) {
            this.dropZone.classList.remove('active');
        }
    }
    
    /**
     * Получение позиции на канвасе
     */
    getCanvasPosition(e) {
        const canvasContainer = document.getElementById('canvasContainer');
        const rect = canvasContainer.getBoundingClientRect();
        
        // Учитываем трансформацию канваса
        const canvas = this.builder.canvas;
        const x = (e.clientX - rect.left - canvas.panX) / canvas.zoom;
        const y = (e.clientY - rect.top - canvas.panY) / canvas.zoom;
        
        return { x, y };
    }
    
    /**
     * Создание элемента на канвасе
     */
    async createCanvasElement(dropData, position) {
        const { type, data } = dropData;
        
        try {
            // Проверяем, что первым элементом может быть только флоу
            if (this.builder.canvas.nodes.size === 0 && type !== 'flow') {
                this.builder.showNotification('Первым элементом на канвасе должен быть Flow', 'warning');
                return;
            }
            
            switch (type) {
                case 'agent':
                    await this.createAgentNode(data, position);
                    break;
                    
                case 'tool':
                    await this.createToolNode(data, position);
                    break;
                    
                case 'flow':
                    await this.createFlowWithExpansion(data, position);
                    break;
                    
                default:
                    console.warn('Неизвестный тип элемента:', type);
            }
            
        } catch (error) {
            console.error('Ошибка создания элемента на канвасе:', error);
            this.builder.showNotification('Ошибка создания элемента: ' + error.message, 'error');
        }
    }
    
    /**
     * Создание ноды агента
     */
    async createAgentNode(agentData, position) {
        const nodeData = {
            id: `agent_${agentData.id}_${Date.now()}`,
            type: 'agent_node',
            params: {
                name: agentData.name,
                agent_id: agentData.id,
                isEntryPoint: false
            },
            ui: {
                x: position.x,
                y: position.y,
                width: 200,
                height: 100
            }
        };
        
        const agentNode = await this.builder.canvas.addNode(nodeData);
        
        // Разворачиваем тулы и субагенты этого агента
        await this.expandAgentTools(agentData.id, position, agentNode.id);
        
        this.builder.showNotification(`Агент "${agentData.name}" добавлен на канвас`, 'success');
    }
    
    /**
     * Создание ноды тула
     */
    async createToolNode(toolData, position) {
        const nodeData = {
            id: `tool_${toolData.id}_${Date.now()}`,
            type: 'tool_node',
            params: {
                name: toolData.name,
                tool_id: toolData.id
            },
            ui: {
                x: position.x,
                y: position.y,
                width: 180,
                height: 80
            }
        };
        
        await this.builder.canvas.addNode(nodeData);
        this.builder.showNotification(`Тул "${toolData.name}" добавлен на канвас`, 'success');
    }
    
    /**
     * Создание флоу с рекурсивным разворачиванием
     */
    async createFlowWithExpansion(flowData, position) {
        try {
            // Создаем основную ноду флоу
            const flowNodeData = {
                id: `flow_${flowData.id}_${Date.now()}`,
                type: 'flow_node',
                params: {
                    name: flowData.name,
                    flow_id: flowData.id,
                    isEntryPoint: true
                },
                ui: {
                    x: position.x,
                    y: position.y,
                    width: 220,
                    height: 120
                }
            };
            
            const flowNode = await this.builder.canvas.addNode(flowNodeData);
            
            // Устанавливаем текущий флоу в Builder
            this.builder.currentFlow = { flow_id: flowData.id, name: flowData.name };
            this.builder.updateFlowInfo();
            this.builder.enableFlowActions();
            
            // Получаем данные флоу с сервера
            const flowResponse = await fetch(`/frontend/builder/flows/${flowData.id}`);
            if (!flowResponse.ok) {
                throw new Error(`Не удалось загрузить флоу: ${flowResponse.statusText}`);
            }
            
            const fullFlowData = await flowResponse.json();
            
            // Если у флоу есть entry_point_agent, начинаем рекурсивное разворачивание
            if (fullFlowData.entry_point_agent) {
                const layoutManager = new FlowLayoutManager();
                await this.expandAgentRecursively(
                    fullFlowData.entry_point_agent,
                    layoutManager.getNextPosition(position, 'agent', 0),
                    flowNode.id,
                    new Set(), // Для предотвращения циклических зависимостей
                    layoutManager,
                    0 // Уровень глубины
                );
            }
            
            // Подгоняем масштаб канваса
            setTimeout(() => this.builder.canvas.fitToScreen(), 500);
            
            this.builder.showNotification(`Флоу "${flowData.name}" развернут на канвасе`, 'success');
            
        } catch (error) {
            console.error('Ошибка разворачивания флоу:', error);
            this.builder.showNotification('Ошибка разворачивания флоу: ' + error.message, 'error');
        }
    }
    
    /**
     * Создание простой ноды флоу (без разворачивания)
     */
    async createFlowNode(flowData, position) {
        const nodeData = {
            id: `flow_${flowData.id}_${Date.now()}`,
            type: 'flow_node',
            params: {
                name: flowData.name,
                flow_id: flowData.id
            },
            ui: {
                x: position.x,
                y: position.y,
                width: 220,
                height: 120
            }
        };
        
        await this.builder.canvas.addNode(nodeData);
        this.builder.showNotification(`Флоу "${flowData.name}" добавлен на канвас`, 'success');
    }
    
    /**
     * Рекурсивное разворачивание агента и его зависимостей
     */
    async expandAgentRecursively(agentId, position, parentNodeId, visitedAgents, layoutManager, depth) {
        // Предотвращаем циклические зависимости
        if (visitedAgents.has(agentId)) {
            console.warn(`Циклическая зависимость обнаружена для агента: ${agentId}`);
            return null;
        }
        
        visitedAgents.add(agentId);
        
        try {
            // Получаем данные агента
            const agentResponse = await fetch(`/frontend/builder/agents/${agentId}`);
            if (!agentResponse.ok) {
                console.warn(`Агент ${agentId} не найден: ${agentResponse.statusText}`);
                return null;
            }
            
            const agentData = await agentResponse.json();
            
            // Создаем ноду агента
            const agentNodeData = {
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
                    width: 200,
                    height: 100
                }
            };
            
            const agentNode = await this.builder.canvas.addNode(agentNodeData);
            
            // Создаем связь с родительским элементом
            if (parentNodeId) {
                const edgeId = `${parentNodeId}-${agentNode.id}`;
                const edgeData = {
                    id: edgeId,
                    source: parentNodeId,
                    target: agentNode.id,
                    type: 'default'
                };
                this.builder.canvas.addEdge(edgeData);
            }
            
            // Добавляем тулы и субагенты
            if (agentData.tools && agentData.tools.length > 0) {
                for (let i = 0; i < agentData.tools.length; i++) {
                    const toolRef = agentData.tools[i];
                    const toolPosition = layoutManager.getNextPosition(position, 'tool', depth + 1, i);
                    
                    // Проверяем, это тул или агент
                    if (toolRef.tool_id.startsWith('agent:')) {
                        // Это субагент
                        const subAgentId = toolRef.tool_id.replace('agent:', '');
                        await this.expandAgentRecursively(
                            subAgentId,
                            toolPosition,
                            agentNode.id,
                            new Set(visitedAgents),
                            layoutManager,
                            depth + 1
                        );
                    } else {
                        // Это тул
                        await this.expandToolRecursively(
                            toolRef.tool_id,
                            toolPosition,
                            agentNode.id
                        );
                    }
                }
            }
            
            // Если агент имеет граф с другими агентами, разворачиваем их
            if (agentData.graph_definition && agentData.graph_definition.nodes) {
                let childIndex = 0;
                for (const node of agentData.graph_definition.nodes) {
                    if (node.type === 'agent_node' && node.params.agent_id && node.params.agent_id !== agentId) {
                        const childPosition = layoutManager.getNextPosition(position, 'agent', depth + 1, childIndex);
                        await this.expandAgentRecursively(
                            node.params.agent_id,
                            childPosition,
                            agentNode.id,
                            new Set(visitedAgents), // Создаем новый Set для каждой ветки
                            layoutManager,
                            depth + 1
                        );
                        childIndex++;
                    }
                }
            }
            
            return agentNode;
            
        } catch (error) {
            console.error(`Ошибка разворачивания агента ${agentId}:`, error);
            return null;
        }
    }
    
    /**
     * Разворачивание тула
     */
    async expandToolRecursively(toolId, position, parentNodeId) {
        try {
            // Кодируем toolId для URL (заменяем точки на слеши для корректного роутинга)
            const encodedToolId = encodeURIComponent(toolId);
            
            // Получаем данные тула
            const toolResponse = await fetch(`/frontend/builder/tools/${encodedToolId}`);
            if (!toolResponse.ok) {
                console.warn(`Тул ${toolId} не найден: ${toolResponse.statusText}`);
                return null;
            }
            
            const toolData = await toolResponse.json();
            
            // Создаем ноду тула
            const toolNodeData = {
                id: `tool_${toolId}_${Date.now()}`,
                type: 'tool_node',
                params: {
                    name: toolData.name,
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
            
            const toolNode = await this.builder.canvas.addNode(toolNodeData);
            
            // Создаем связь с родительским агентом
            if (parentNodeId) {
                const edgeId = `${parentNodeId}-${toolNode.id}`;
                const edgeData = {
                    id: edgeId,
                    source: parentNodeId,
                    target: toolNode.id,
                    type: 'tool_connection'
                };
                this.builder.canvas.addEdge(edgeData);
            }
            
            return toolNode;
            
        } catch (error) {
            console.error(`Ошибка разворачивания тула ${toolId}:`, error);
            return null;
        }
    }
    
    /**
     * Разворачивание тулов и субагентов для отдельно добавленного агента
     */
    async expandAgentTools(agentId, position, parentNodeId) {
        try {
            // Получаем данные агента
            const agentResponse = await fetch(`/frontend/builder/agents/${agentId}`);
            if (!agentResponse.ok) {
                console.warn(`Агент ${agentId} не найден: ${agentResponse.statusText}`);
                return;
            }
            
            const agentData = await agentResponse.json();
            
            // Разворачиваем тулы и субагенты
            if (agentData.tools && agentData.tools.length > 0) {
                const layoutManager = new FlowLayoutManager();
                
                for (let i = 0; i < agentData.tools.length; i++) {
                    const toolRef = agentData.tools[i];
                    const toolPosition = layoutManager.getNextPosition(position, 'tool', 1, i);
                    
                    // Проверяем, это тул или агент
                    if (toolRef.tool_id.startsWith('agent:')) {
                        // Это субагент
                        const subAgentId = toolRef.tool_id.replace('agent:', '');
                        await this.expandAgentRecursively(
                            subAgentId,
                            toolPosition,
                            parentNodeId,
                            new Set([agentId]), // Предотвращаем циклы
                            layoutManager,
                            1
                        );
                    } else {
                        // Это тул
                        await this.expandToolRecursively(
                            toolRef.tool_id,
                            toolPosition,
                            parentNodeId
                        );
                    }
                }
            }
            
        } catch (error) {
            console.error(`Ошибка разворачивания тулов агента ${agentId}:`, error);
        }
    }
    
    /**
     * Очистка при уничтожении
     */
    destroy() {
        if (this.observer) {
            this.observer.disconnect();
        }
        
        if (this.dropZone && this.dropZone.parentNode) {
            this.dropZone.parentNode.removeChild(this.dropZone);
        }
    }
}

/**
 * Менеджер для автоматического размещения элементов при разворачивании флоу
 */
class FlowLayoutManager {
    constructor() {
        this.config = {
            horizontalSpacing: 300,  // Расстояние между уровнями по горизонтали
            verticalSpacing: 150,    // Расстояние между элементами по вертикали
            toolOffset: 200,        // Смещение для тулов
            toolSpacing: 180        // Расстояние между тулами
        };
    }
    
    /**
     * Получить следующую позицию для элемента
     */
    getNextPosition(parentPosition, elementType, depth, index = 0) {
        switch (elementType) {
            case 'agent':
                return {
                    x: parentPosition.x + this.config.horizontalSpacing,
                    y: parentPosition.y + (index * this.config.verticalSpacing)
                };
                
            case 'tool':
                return {
                    x: parentPosition.x + this.config.toolOffset,
                    y: parentPosition.y + this.config.verticalSpacing + (index * this.config.toolSpacing)
                };
                
            case 'flow':
                return {
                    x: parentPosition.x + this.config.horizontalSpacing,
                    y: parentPosition.y
                };
                
            default:
                return {
                    x: parentPosition.x + this.config.horizontalSpacing,
                    y: parentPosition.y + (index * this.config.verticalSpacing)
                };
        }
    }
    
    /**
     * Вычислить оптимальное расположение для дерева элементов
     */
    calculateTreeLayout(rootPosition, treeData) {
        // TODO: Реализовать более сложный алгоритм размещения дерева
        // Например, алгоритм Reingold-Tilford для красивого размещения деревьев
        return rootPosition;
    }
}

// Экспортируем классы в глобальную область
window.BuilderDragDrop = BuilderDragDrop;
window.FlowLayoutManager = FlowLayoutManager;

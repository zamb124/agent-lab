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
        if (!canvasContainer) {
            console.error('❌ canvasContainer не найден!');
            return;
        }
        
        console.log('✅ Настраиваем drop zone для canvas');
        
        // Обработчики для зоны сброса
        canvasContainer.addEventListener('dragover', (e) => this.handleDragOver(e));
        canvasContainer.addEventListener('dragenter', (e) => this.handleDragEnter(e));
        canvasContainer.addEventListener('dragleave', (e) => this.handleDragLeave(e));
        canvasContainer.addEventListener('drop', (e) => this.handleDrop(e));
        
        console.log('✅ Drop zone настроен');
    }
    
    /**
     * Настройка источников перетаскивания
     */
    setupDragSources() {
        // Palette настраивается отдельно в palette.js
        console.log('✅ Drag sources инициализированы');
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
        e.stopPropagation();
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
        e.stopPropagation();
        
        console.log('🎯 DROP EVENT!', e);
        console.log('📦 dataTransfer types:', e.dataTransfer.types);
        
        let dropData = null;
        
        // Проверяем данные из palette (новый формат)
        const nodeType = e.dataTransfer?.getData('application/x-node-type');
        console.log('🔍 Проверка nodeType:', nodeType);
        
        if (nodeType) {
            console.log('🎨 Drop из palette:', nodeType);
            dropData = {
                type: 'palette_node',
                nodeType: nodeType
            };
        } else {
            // Пытаемся получить данные из dataTransfer (старый формат)
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
        const { type, data, nodeType } = dropData;
        
        try {
            // Проверяем, что первым элементом может быть только flow
            const isFirstNode = this.builder.canvas.nodes.size === 0;
            const actualType = (type === 'palette_node' && nodeType) ? nodeType : type;
            
            if (isFirstNode && actualType !== 'flow' && actualType !== 'flow_node') {
                this.builder.showNotification('Первым элементом на канвасе должен быть Flow', 'warning');
                return;
            }
            
            // Обработка нового формата (palette_node)
            if (type === 'palette_node' && nodeType) {
                await this.createNodeFromPalette(nodeType, position);
                return;
            }
            
            // Обработка старого формата
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
            console.error('❌ Ошибка создания элемента на канвасе:', error);
            console.error('Stack trace:', error.stack);
            this.builder.showNotification('Ошибка создания элемента: ' + error.message, 'error');
        }
    }
    
    /**
     * Создание ноды из palette (новый формат)
     */
    async createNodeFromPalette(nodeType, position) {
        const nodeId = `${nodeType}_${Date.now()}`;
        
        const nodeData = {
            id: nodeId,
            type: nodeType,
            params: {
                name: this.getDefaultNodeName(nodeType),
                description: this.getDefaultNodeDescription(nodeType)
            },
            ui: {
                x: position.x - 90,
                y: position.y - 40,
                width: 180,
                height: 80
            }
        };
        
        // Для flow, agent и tool нужно создать сущность в БД
        if (nodeType === 'flow_node') {
            const response = await fetch('/frontend/api/flows/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            const flowData = await response.json();
            nodeData.params.flow_id = flowData.flow_id;
            nodeData.params.name = flowData.name;
        } else if (nodeType === 'agent_node') {
            const response = await fetch('/frontend/api/agents/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            const agentData = await response.json();
            nodeData.params.agent_id = agentData.agent_id;
            nodeData.params.name = agentData.name;
        } else if (nodeType === 'tool_node') {
            const response = await fetch('/frontend/api/tools/', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({})
            });
            const toolData = await response.json();
            nodeData.params.tool_id = toolData.tool_id;
            nodeData.params.name = toolData.name || 'New Tool';
        } else if (nodeType === 'function_node' || nodeType === 'router_node' || nodeType === 'message_node') {
            // Эти типы нод не требуют создания сущностей в БД
            // Параметры уже установлены в nodeData
            console.log(`✅ Создание ${nodeType} без API вызова`);
        } else {
            console.warn(`⚠️ Неизвестный тип ноды: ${nodeType}`);
        }
        
        await this.builder.canvas.addNode(nodeData);
        console.log(`✅ ${nodeData.params.name} добавлен на канвас`);
        
        // Показываем успешную нотификацию
        const nodeTypeName = this.getDefaultNodeName(nodeType).replace('New ', '');
        this.builder.showNotification(`${nodeTypeName} добавлен на канвас`, 'success');
    }
    
    /**
     * Получение имени по умолчанию для типа ноды
     */
    getDefaultNodeName(nodeType) {
        const names = {
            'flow_node': 'New Flow',
            'agent_node': 'New Agent',
            'tool_node': 'New Tool',
            'function_node': 'New Function',
            'message_node': 'New Message',
            'router_node': 'New Router'
        };
        return names[nodeType] || 'New Node';
    }
    
    /**
     * Получение описания по умолчанию для типа ноды
     */
    getDefaultNodeDescription(nodeType) {
        const descs = {
            'flow_node': 'Entry point',
            'agent_node': 'AI agent',
            'tool_node': 'Function call',
            'function_node': 'Custom code',
            'message_node': 'Send message',
            'router_node': 'Router logic'
        };
        return descs[nodeType] || '';
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
                    width: 180,
                    height: 80
                }
            };
            
            const flowNode = await this.builder.canvas.addNode(flowNodeData);
            
            // Устанавливаем текущий флоу в Builder, если еще не установлен
            if (!this.builder.currentFlow || this.builder.currentFlow.flow_id !== flowData.id) {
                this.builder.currentFlow = { flow_id: flowData.id, name: flowData.name };
                this.builder.updateFlowInfo();
                this.builder.enableFlowActions();
            }
            
            // Получаем данные флоу с сервера, если еще не загружены
            let fullFlowData;
            if (this.builder.currentFlow && this.builder.currentFlow.flow_id === flowData.id && this.builder.currentFlow.entry_point_agent !== undefined) {
                // Используем уже загруженные данные
                fullFlowData = this.builder.currentFlow;
                console.log('📦 Используем уже загруженные данные флоу');
            } else {
                const flowResponse = await fetch(`/frontend/api/flows/${encodeURIComponent(flowData.id)}`);
                if (!flowResponse.ok) {
                    throw new Error(`Не удалось загрузить флоу: ${flowResponse.statusText}`);
                }
                fullFlowData = await flowResponse.json();
            }
            
            // Если у флоу есть entry_point_agent, начинаем рекурсивное разворачивание
            console.log('🔍 Проверка entry_point_agent:', fullFlowData.entry_point_agent);
            
            if (fullFlowData.entry_point_agent) {
                console.log('✅ Entry point agent найден, начинаем разворачивание');
                
                const layoutManager = new FlowLayoutManager();
                layoutManager.setBuilder(this.builder);
                console.log('🔧 FlowLayoutManager создан с builder:', !!this.builder, 'canvas:', !!this.builder?.canvas);
                
                // Проверяем, есть ли сохраненные позиции на канвасе
                let shouldUseSavedPositions = false;
                if (fullFlowData.canvas_data && fullFlowData.canvas_data.nodes) {
                    shouldUseSavedPositions = true;
                    console.log('Найдены сохраненные позиции элементов, используем их вместо автоматического размещения');
                }
                
                console.log('🚀 Запускаем expandAgentRecursively для:', fullFlowData.entry_point_agent);
                
                await this.expandAgentRecursively(
                    fullFlowData.entry_point_agent,
                    layoutManager.getNextPosition(position, 'agent', 0),
                    flowNode.id,
                    new Set(),
                    layoutManager,
                    0,
                    shouldUseSavedPositions ? fullFlowData.canvas_data : null
                );
                
                console.log('✅ Разворачивание завершено');
            } else {
                console.log('⚠️ У Flow нет entry_point_agent');
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
    async expandAgentRecursively(agentId, position, parentNodeId, visitedAgents, layoutManager, depth, savedCanvasData = null) {
        // Предотвращаем циклические зависимости
        if (visitedAgents.has(agentId)) {
            console.warn(`Циклическая зависимость обнаружена для агента: ${agentId}`);
            return null;
        }
        
        visitedAgents.add(agentId);
        
        try {
            // Получаем данные агента
            const agentResponse = await fetch(`/frontend/api/agents/${agentId}`);
            if (!agentResponse.ok) {
                console.warn(`Агент ${agentId} не найден: ${agentResponse.statusText}`);
                return null;
            }
            
            const agentData = await agentResponse.json();
            
            // Проверяем сохраненные позиции для этого агента
            let finalPosition = position;
            if (savedCanvasData && savedCanvasData.nodes) {
                const savedNode = savedCanvasData.nodes.find(node => 
                    node.type === 'agent_node' && node.params.agent_id === agentId
                );
                if (savedNode && savedNode.ui) {
                    finalPosition = { x: savedNode.ui.x, y: savedNode.ui.y };
                    console.log(`Используем сохраненную позицию для агента ${agentId}: (${finalPosition.x}, ${finalPosition.y})`);
                }
            }
            
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
                    x: finalPosition.x,
                    y: finalPosition.y,
                    width: 180,
                    height: 80
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
                    let toolPosition = layoutManager.getNextPosition(finalPosition, 'tool', depth + 1, i);
                    
                    // Проверяем сохраненные позиции для этого инструмента
                    if (savedCanvasData && savedCanvasData.nodes) {
                        const savedToolNode = savedCanvasData.nodes.find(node => 
                            node.type === 'tool_node' && node.params.tool_id === toolRef.tool_id
                        );
                        if (savedToolNode && savedToolNode.ui) {
                            toolPosition = { x: savedToolNode.ui.x, y: savedToolNode.ui.y };
                            console.log(`Используем сохраненную позицию для инструмента ${toolRef.tool_id}: (${toolPosition.x}, ${toolPosition.y})`);
                        }
                    }
                    
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
                            depth + 1,
                            savedCanvasData // Передаем сохраненные данные для субагентов
                        );
                    } else {
                        // Это тул
                        await this.expandToolRecursively(
                            toolRef.tool_id,
                            toolPosition,
                            agentNode.id,
                            savedCanvasData // Передаем сохраненные данные для инструментов
                        );
                    }
                }
            }
            
            // Если это StateGraph агент с graph_definition - разворачиваем граф
            if (agentData.type === 'stategraph' && agentData.graph_definition) {
                console.log(`📊 StateGraph агент обнаружен: ${agentId}, разворачиваем граф`);
                await this.expandGraphDefinition(
                    agentData.graph_definition,
                    finalPosition,
                    agentNode.id,
                    layoutManager,
                    depth,
                    savedCanvasData
                );
            }
            // Иначе для ReAct агентов разворачиваем tools
            else if (agentData.tools && agentData.tools.length > 0) {
                for (let i = 0; i < agentData.tools.length; i++) {
                    const toolRef = agentData.tools[i];
                    let toolPosition = layoutManager.getNextPosition(finalPosition, 'tool', depth + 1, i);
                    
                    // Проверяем сохраненные позиции для этого инструмента
                    if (savedCanvasData && savedCanvasData.nodes) {
                        const savedToolNode = savedCanvasData.nodes.find(node => 
                            node.type === 'tool_node' && node.params.tool_id === toolRef.tool_id
                        );
                        if (savedToolNode && savedToolNode.ui) {
                            toolPosition = { x: savedToolNode.ui.x, y: savedToolNode.ui.y };
                            console.log(`Используем сохраненную позицию для инструмента ${toolRef.tool_id}: (${toolPosition.x}, ${toolPosition.y})`);
                        }
                    }
                    
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
                            depth + 1,
                            savedCanvasData
                        );
                    } else {
                        // Это тул
                        await this.expandToolRecursively(
                            toolRef.tool_id,
                            toolPosition,
                            agentNode.id,
                            savedCanvasData
                        );
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
     * Разворачивание graph_definition (для StateGraph агентов)
     */
    async expandGraphDefinition(graphDef, basePosition, parentNodeId, layoutManager, depth, savedCanvasData) {
        console.log(`📊 Разворачиваем граф с ${graphDef.nodes.length} нодами и ${graphDef.edges.length} ребрами`);
        
        const createdNodes = new Map();
        
        // Создаем все ноды графа
        for (let i = 0; i < graphDef.nodes.length; i++) {
            const graphNode = graphDef.nodes[i];
            const nodeId = graphNode.id;
            
            console.log(`📦 GraphNode[${nodeId}]:`, {
                type: graphNode.type,
                inline_code: graphNode.inline_code ? 'есть' : 'нет',
                function_path: graphNode.function_path || 'нет',
                code_mode: graphNode.code_mode,
                params: graphNode.params
            });
            
            // Проверяем есть ли у этой ноды conditional edges (router)
            const hasConditionalEdges = graphDef.edges.some(edge => 
                edge.source === nodeId && edge.condition_type === 'router'
            );
            
            // Если это function_node с conditional edges - делаем router_node
            let nodeType = graphNode.type;
            if (nodeType === 'function_node' && hasConditionalEdges) {
                nodeType = 'router_node';
                console.log(`🔄 ${nodeId}: function_node → router_node (есть router edges)`);
            }
            
            // Рассчитываем позицию
            let nodePosition = layoutManager.getNextPosition(basePosition, 'agent', depth + 1, i);
            
            // Определяем тип ноды и параметры
            let nodeData = {
                id: `${nodeType}_${nodeId}_${Date.now()}`,
                type: nodeType,
                params: {
                    name: nodeId,
                    description: graphNode.description || this.getDefaultNodeDescription(nodeType),
                    ...graphNode.params
                },
                // Копируем поля из GraphNode на верхний уровень
                inline_code: graphNode.inline_code || null,
                function_path: graphNode.function_path || null,
                code_mode: graphNode.code_mode || 'code_reference',
                ui: {
                    x: nodePosition.x,
                    y: nodePosition.y,
                    width: 180,
                    height: 80
                }
            };
            
            // Создаем ноду на канвасе
            const canvasNode = await this.builder.canvas.addNode(nodeData);
            createdNodes.set(nodeId, canvasNode.id);
            
            console.log(`✅ Создана нода графа: ${nodeId} (${nodeType})`);
        }
        
        // Создаем edges между нодами графа
        for (const edge of graphDef.edges) {
            if (edge.source === 'START' || edge.target === 'END') {
                // Пропускаем специальные ноды START/END
                continue;
            }
            
            const sourceCanvasId = createdNodes.get(edge.source);
            const targetCanvasId = createdNodes.get(edge.target);
            
            if (sourceCanvasId && targetCanvasId) {
                const edgeData = {
                    id: `${sourceCanvasId}-${targetCanvasId}`,
                    source: sourceCanvasId,
                    target: targetCanvasId,
                    type: edge.condition_type === 'router' ? 'conditional' : 'default'
                };
                
                this.builder.canvas.addEdge(edgeData);
                console.log(`🔗 Создана связь: ${edge.source} → ${edge.target}`);
            }
        }
        
        // Связываем entry_point графа с родительской нодой
        if (parentNodeId && graphDef.entry_point) {
            let realEntryPoint = graphDef.entry_point;
            
            // Если entry_point это START, находим куда START ведет
            if (realEntryPoint === 'START') {
                const startEdge = graphDef.edges.find(edge => edge.source === 'START');
                if (startEdge) {
                    realEntryPoint = startEdge.target;
                    console.log(`🔍 Entry point START → ${realEntryPoint}`);
                }
            }
            
            const entryNodeCanvasId = createdNodes.get(realEntryPoint);
            if (entryNodeCanvasId) {
                const edgeData = {
                    id: `${parentNodeId}-${entryNodeCanvasId}`,
                    source: parentNodeId,
                    target: entryNodeCanvasId,
                    type: 'default'
                };
                this.builder.canvas.addEdge(edgeData);
                console.log(`🔗 Связан parent с entry_point: ${parentNodeId} → ${realEntryPoint}`);
            }
        }
        
        console.log(`✅ Граф развернут: ${graphDef.nodes.length} нод, ${graphDef.edges.length} связей`);
    }
    
    /**
     * Разворачивание тула
     */
    async expandToolRecursively(toolId, position, parentNodeId, savedCanvasData = null) {
        try {
            // Кодируем toolId для URL (заменяем точки на слеши для корректного роутинга)
            const encodedToolId = encodeURIComponent(toolId);
            
            // Получаем данные тула
            const toolResponse = await fetch(`/frontend/api/tools/${encodedToolId}`);
            if (!toolResponse.ok) {
                console.warn(`Тул ${toolId} не найден: ${toolResponse.statusText}`);
                return null;
            }
            
            const toolData = await toolResponse.json();
            
            // Проверяем сохраненные позиции для этого инструмента
            let finalPosition = position;
            if (savedCanvasData && savedCanvasData.nodes) {
                const savedNode = savedCanvasData.nodes.find(node => 
                    node.type === 'tool_node' && node.params.tool_id === toolId
                );
                if (savedNode && savedNode.ui) {
                    finalPosition = { x: savedNode.ui.x, y: savedNode.ui.y };
                    console.log(`Используем сохраненную позицию для инструмента ${toolId}: (${finalPosition.x}, ${finalPosition.y})`);
                }
            }
            
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
                    x: finalPosition.x,
                    y: finalPosition.y,
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
            const agentResponse = await fetch(`/frontend/api/agents/${agentId}`);
            if (!agentResponse.ok) {
                console.warn(`Агент ${agentId} не найден: ${agentResponse.statusText}`);
                return;
            }
            
            const agentData = await agentResponse.json();
            
            // Разворачиваем тулы и субагенты
            if (agentData.tools && agentData.tools.length > 0) {
                const layoutManager = new FlowLayoutManager();
                layoutManager.setBuilder(this.builder);
                console.log('🔧 FlowLayoutManager создан с builder:', !!this.builder, 'canvas:', !!this.builder?.canvas);
                
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
            horizontalSpacing: 280,  // Расстояние между уровнями по горизонтали (для компактных кубиков)
            verticalSpacing: 140,    // Расстояние между элементами по вертикали
            toolOffset: 200,        // Смещение для тулов
            toolSpacing: 120        // Расстояние между тулами
        };
    }
    
    /**
     * Установить ссылку на builder для доступа к canvas
     */
    setBuilder(builder) {
        this.builder = builder;
    }
    
    /**
     * Проверка пересечения с существующими нодами
     */
    checkCollision(x, y, width = 180, height = 80) {
        if (!this.builder || !this.builder.canvas || !this.builder.canvas.nodes) {
            console.warn('⚠️ checkCollision: нет доступа к canvas');
            return false;
        }
        
        const canvas = this.builder.canvas;
        
        const margin = 20;
        console.log(`🔍 Проверяем пересечение для (${x}, ${y}) размер ${width}x${height} с ${canvas.nodes.size} нодами`);
        
        for (const node of canvas.nodes.values()) {
            const nodeWidth = node.width || 180;
            const nodeHeight = node.height || 80;
            
            // Проверяем пересечение прямоугольников с учетом margin
            const collision = x < node.x + nodeWidth + margin &&
                             x + width + margin > node.x &&
                             y < node.y + nodeHeight + margin &&
                             y + height + margin > node.y;
            
            if (collision) {
                console.log(`❌ Пересечение с нодой (${node.x}, ${node.y}) размер ${nodeWidth}x${nodeHeight}`);
                return true; // Есть пересечение
            }
        }
        
        return false; // Нет пересечений
    }
    
    /**
     * Найти свободную позицию рядом с предложенной
     */
    findFreePosition(initialX, initialY, elementType) {
        // Если нет доступа к canvas, возвращаем исходную позицию
        if (!this.builder || !this.builder.canvas) {
            console.warn('FlowLayoutManager: нет доступа к canvas, пропускаем проверку пересечений');
            return { x: initialX, y: initialY };
        }
        
        let x = initialX;
        let y = initialY;
        const stepY = 250; // Увеличили шаг по вертикали (размер карточки + отступ)
        const stepX = 450; // Шаг по горизонтали
        const maxAttempts = 30; // Увеличили попытки
        
        for (let attempt = 0; attempt < maxAttempts; attempt++) {
            if (!this.checkCollision(x, y)) {
                if (attempt > 0) {
                    console.log(`✅ Найдена свободная позиция: (${x}, ${y}) после ${attempt} попыток`);
                }
                return { x, y };
            }
            
            // Сначала пробуем вниз (3 попытки)
            if (attempt < 3) {
                y += stepY;
            }
            // Потом правее и снова вниз
            else if (attempt % 4 === 0) {
                x += stepX;
                y = initialY;
            } else {
                y += stepY;
            }
        }
        
        console.warn('⚠️ Не нашли свободное место за 30 попыток, используем исходную позицию');
        return { x: initialX, y: initialY };
    }
    
    /**
     * Получить следующую позицию для элемента
     */
    getNextPosition(parentPosition, elementType, depth, index = 0) {
        let proposedPosition;
        
        switch (elementType) {
            case 'agent':
                proposedPosition = {
                    x: parentPosition.x + this.config.horizontalSpacing,
                    y: parentPosition.y + (index * this.config.verticalSpacing)
                };
                break;
                
            case 'tool':
                proposedPosition = {
                    x: parentPosition.x + this.config.toolOffset,
                    y: parentPosition.y + this.config.verticalSpacing + (index * this.config.toolSpacing)
                };
                break;
                
            case 'flow':
                proposedPosition = {
                    x: parentPosition.x + this.config.horizontalSpacing,
                    y: parentPosition.y
                };
                break;
                
            default:
                proposedPosition = {
                    x: parentPosition.x + this.config.horizontalSpacing,
                    y: parentPosition.y + (index * this.config.verticalSpacing)
                };
        }
        
        // Проверяем на пересечения и ищем свободную позицию
        return this.findFreePosition(proposedPosition.x, proposedPosition.y, elementType);
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

/**
 * NodePalette v3.0 - Палитра компонентов для новой ООП архитектуры
 */

export default class NodePalette {
    constructor(builder) {
        this.builder = builder;
        this.canvas = builder.canvas;
        this.element = document.getElementById('nodePalette');
        
        this.nodeTypes = {
            'flow_node': {
                icon: 'bi-diagram-3',
                color: '#3b82f6',
                label: 'Flow',
                desc: 'Entry point'
            },
            'agent_node': {
                icon: 'bi-robot',
                color: '#8b5cf6',
                label: 'Agent',
                desc: 'AI agent'
            },
            'tool_node': {
                icon: 'bi-tools',
                color: '#10b981',
                label: 'Tool',
                desc: 'Function call'
            },
            'function_node': {
                icon: 'bi-code-square',
                color: '#f59e0b',
                label: 'Function',
                desc: 'Custom code'
            },
            'message_node': {
                icon: 'bi-chat-dots',
                color: '#06b6d4',
                label: 'Message',
                desc: 'Send message'
            },
            'router_node': {
                icon: 'bi-lightning',
                color: '#ef4444',
                label: 'Router',
                desc: 'Router logic'
            }
        };
        
        this.init();
    }
    
    init() {
        console.log('🎨 Palette v3.0 инициализация...');
        this.setupDragFromPalette();
        this.setupDropOnCanvas();
        this.setupCollapseButton();
        this.updatePaletteState();
        console.log('✅ Palette инициализирована');
    }
    
    /**
     * Настройка drag из палитры
     */
    setupDragFromPalette() {
        const paletteItems = this.element.querySelectorAll('.palette-item');
        console.log(`📋 Найдено ${paletteItems.length} элементов палитры`);
        
        paletteItems.forEach(item => {
            item.addEventListener('dragstart', (e) => this.handleDragStart(e));
            item.addEventListener('dragend', (e) => this.handleDragEnd(e));
        });
    }
    
    /**
     * Настройка drop на canvas
     */
    setupDropOnCanvas() {
        const canvasContainer = document.getElementById('canvasContainer');
        if (!canvasContainer) return;
        
        canvasContainer.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'copy';
        });
        
        canvasContainer.addEventListener('drop', (e) => this.handleDrop(e));
    }
    
    /**
     * Настройка кнопки сворачивания
     */
    setupCollapseButton() {
        const collapseBtn = document.getElementById('collapsePaletteBtn');
        if (collapseBtn) {
            collapseBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggleCollapse();
            });
        }
        
        const header = document.getElementById('paletteHeader');
        if (header) {
            header.addEventListener('click', () => this.toggleCollapse());
        }
    }
    
    /**
     * Начало перетаскивания из палитры
     */
    handleDragStart(e) {
        const paletteItem = e.target.closest('.palette-item');
        const nodeType = paletteItem.dataset.nodeType;
        
        // Валидация: можно ли драгать этот элемент
        const canDrag = this.canDragNodeType(nodeType);
        
        if (!canDrag.allowed) {
            e.preventDefault();
            console.warn('⚠️ Нельзя добавить элемент:', canDrag.reason);
            this.builder.showNotification(canDrag.reason, 'warning');
            return;
        }
        
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('application/x-node-type', nodeType);
        e.dataTransfer.setData('text/plain', nodeType);
        
        paletteItem.classList.add('dragging');
        
        console.log('🎨 Начало drag из palette:', nodeType);
    }
    
    /**
     * Завершение перетаскивания
     */
    handleDragEnd(e) {
        e.target.closest('.palette-item').classList.remove('dragging');
    }
    
    /**
     * Drop на canvas - создание ноды
     */
    async handleDrop(e) {
        e.preventDefault();
        
        const nodeType = e.dataTransfer.getData('application/x-node-type');
        if (!nodeType) return;
        
        console.log('📦 Drop на canvas:', nodeType);
        
        // Вычисляем позицию на canvas с учетом zoom и pan
        const canvasContainer = document.getElementById('canvasContainer');
        const rect = canvasContainer.getBoundingClientRect();
        
        const canvasX = (e.clientX - rect.left - this.canvas.panX) / this.canvas.zoom;
        const canvasY = (e.clientY - rect.top - this.canvas.panY) / this.canvas.zoom;
        
        const position = { 
            x: canvasX, 
            y: canvasY,
            screenX: e.clientX,
            screenY: e.clientY
        };
        
        // Для agent, tool, flow показываем селектор выбора
        const needsSelector = ['agent_node', 'tool_node', 'flow_node'].includes(nodeType);
        
        if (needsSelector) {
            await this.canvas.elementSelector.showSelector(nodeType, position);
        } else {
            // Для message, function, router создаем сразу
            await this.createSimpleNode(nodeType, position);
        }
    }
    
    /**
     * Создание простой ноды без селектора
     */
    async createSimpleNode(nodeType, position) {
        const nodeData = {
            id: `${nodeType}_${Date.now()}`,
            type: nodeType,
            params: {
                name: this.nodeTypes[nodeType]?.label || 'Node'
            },
            ui: { 
                x: position.x, 
                y: position.y, 
                width: 200, 
                height: 100 
            }
        };
        
        try {
            const node = await this.canvas.addNode(nodeData);
            console.log('✅ Нода создана:', node.id);
            
            this.canvas.selectionManager.selectNode(node, false);
            
        } catch (error) {
            console.error('❌ Ошибка создания ноды:', error);
        }
    }
    
    /**
     * Валидация: можно ли добавить элемент данного типа
     */
    canDragNodeType(nodeType) {
        const nodesCount = this.canvas.nodes.size;
        const hasFlow = Array.from(this.canvas.nodes.values()).some(n => n.type === 'flow_node');
        const hasAgent = Array.from(this.canvas.nodes.values()).some(n => n.type === 'agent_node');
        const entryPointAgentType = this.builder.entryPointAgentType;
        
        console.log(`🔍 canDragNodeType(${nodeType}):`, {
            nodesCount,
            hasFlow,
            hasAgent,
            entryPointAgentType
        });
        
        // Правило 1: Первым может быть только flow
        if (nodesCount === 0 && nodeType !== 'flow_node') {
            return { 
                allowed: false, 
                reason: 'Первым элементом может быть только Flow' 
            };
        }
        
        // Правило 2: Нельзя добавить второй flow
        if (nodeType === 'flow_node' && hasFlow) {
            return { 
                allowed: false, 
                reason: 'Flow уже существует на canvas' 
            };
        }
        
        // Правило 3: Если есть flow, но нет агента - только agent доступен
        if (hasFlow && !hasAgent && nodeType !== 'agent_node') {
            return { 
                allowed: false, 
                reason: 'Сначала добавьте Agent и соедините с Flow' 
            };
        }
        
        // Правило 4: Если нет entry_point агента - ограничиваем
        if (!entryPointAgentType && nodeType !== 'flow_node' && nodeType !== 'agent_node') {
            return { 
                allowed: false, 
                reason: 'Сначала соедините Flow с Agent' 
            };
        }
        
        // Правило 5: Для ReAct агента - только agent и tool
        if (entryPointAgentType === 'react') {
            const allowedForReact = ['agent_node', 'tool_node'];
            if (!allowedForReact.includes(nodeType)) {
                return { 
                    allowed: false, 
                    reason: 'Для ReAct агента доступны только Agent и Tool' 
                };
            }
        }
        
        // Правило 6: Для StateGraph - все доступно (кроме второго flow который уже проверен выше)
        if (entryPointAgentType === 'stategraph') {
            return { allowed: true };
        }
        
        return { allowed: true };
    }
    
    /**
     * Сворачивание/разворачивание палитры
     */
    toggleCollapse() {
        this.element.classList.toggle('collapsed');
        console.log('🔄 Palette collapsed:', this.element.classList.contains('collapsed'));
    }
    
    /**
     * Обновление палитры для типа агента
     */
    updateForAgentType(agentType) {
        console.log('🎯 Palette.updateForAgentType вызван:', agentType);
        console.log('🎯 Builder.entryPointAgentType:', this.builder.entryPointAgentType);
        this.updatePaletteState();
        console.log('✅ Palette.updatePaletteState() завершен');
    }
    
    /**
     * Обновление состояния элементов палитры (доступны/недоступны)
     */
    updatePaletteState() {
        const paletteItems = this.element.querySelectorAll('.palette-item');
        
        paletteItems.forEach(item => {
            const nodeType = item.dataset.nodeType;
            const validation = this.canDragNodeType(nodeType);
            
            if (validation.allowed) {
                item.classList.remove('disabled');
                item.setAttribute('draggable', 'true');
                item.title = '';
            } else {
                item.classList.add('disabled');
                item.setAttribute('draggable', 'false');
                item.title = validation.reason;
            }
        });
    }
}


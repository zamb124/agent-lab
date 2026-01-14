/**
 * Agent Canvas Event Handlers
 * Обработчики событий Drawflow и DOM
 */

export function setupEvents(component) {
    component._editor.on('nodeUnselected', () => {
        component.emit('node-unselected');
    });

    component._editor.on('nodeRemoved', (id) => {
        component.nodeConfigs.delete(id.toString());
    });

    // Сохраняем обработчик для возможности отключения
    component._connectionCreatedHandler = (connection) => {
        console.log('[AgentCanvas] connectionCreated event:', {
            connection,
            isImporting: component._isImporting,
            willShowModal: !component._isImporting
        });
        
        if (!component._isImporting) {
            component._pendingConnection = connection;
            component._showEdgeConditionModal(
                connection.output_id,
                connection.input_id,
                ''
            );
        }
        component.emit('connection-created', { connection });
        component._updateVirtualNodes();
        
        if (!component._isImporting) {
            component._saveSnapshot();
        }
    };
    
    component._editor.on('connectionCreated', component._connectionCreatedHandler);

    component._editor.on('connectionRemoved', (connection) => {
        const key = `${connection.output_id}-${connection.input_id}`;
        component.edgeConditions.delete(key);
        component._edgeLabelsManager?.remove(connection.output_id, connection.input_id);
        component.emit('connection-removed', { connection });
        component._updateVirtualNodes();
        
        if (!component._isImporting) {
            component._saveSnapshot();
        }
    });
    
    component._editor.on('zoom', () => {
        component._updateVirtualNodes();
        component._edgeLabelsManager?.updatePositions();
        component._updateAllErrorTooltipPositions();
    });
    
    component._editor.on('translate', () => {
        component._updateVirtualNodes();
        component._edgeLabelsManager?.updatePositions();
        component._updateAllErrorTooltipPositions();
    });
    
    component._editor.on('nodeMoved', () => {
        component._updateVirtualNodes();
        component._edgeLabelsManager?.updatePositions();
        component._updateAllErrorTooltipPositions();
    });
    
    setupConnectionClickHandling(component);
}

export function setupConnectionClickHandling(component) {
    // Обработка contextmenu для связей теперь в setupContextMenu
    // Этот метод можно удалить, но оставляем для совместимости
}

export function setupDragDrop(component) {
    const container = component.querySelector('#drawflow-area');
    
    container.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    });

    container.addEventListener('drop', async (e) => {
        e.preventDefault();
        
        const data = e.dataTransfer.getData('application/json');
        if (!data) return;
        
        const nodeType = JSON.parse(data);
        
        const rect = container.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const zoom = component._editor.zoom;
        const translateX = component._editor.canvas_x;
        const translateY = component._editor.canvas_y;
        
        const posX = (x - translateX) / zoom;
        const posY = (y - translateY) / zoom;

        await component._addNode(nodeType, posX, posY);
    });
}

export function setupContextMenu(component) {
    const container = component.querySelector('#drawflow-area');
    
    container.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        
        // Сначала проверяем клик по связи
        const path = e.target.closest('.main-path');
        if (path) {
            e.stopPropagation();
            
            const parent = path.closest('.connection');
            if (!parent) return;
            
            const classes = parent.className.split(' ');
            let outputId = null;
            let inputId = null;
            
            for (const cls of classes) {
                if (cls.startsWith('node_in_node-')) {
                    inputId = cls.replace('node_in_node-', '');
                } else if (cls.startsWith('node_out_node-')) {
                    outputId = cls.replace('node_out_node-', '');
                }
            }
            
            if (outputId && inputId) {
                const key = `${outputId}-${inputId}`;
                const currentCondition = component.edgeConditions.get(key) || '';
                
                component._showConnectionContextMenu(e.clientX, e.clientY, outputId, inputId, currentCondition);
            }
            return;
        }
        
        // Если не по связи, проверяем клик по ноде
        const nodeEl = e.target.closest('.drawflow-node');
        if (!nodeEl) {
            component.contextMenu = null;
            return;
        }
        
        const drawflowId = nodeEl.id.replace('node-', '');
        const config = component.nodeConfigs.get(drawflowId);
        
        if (config) {
            const hasBreakpoint = component.breakpointManager?.hasBreakpoint(config.nodeId) || false;
            
            component.contextMenu = {
                x: e.clientX,
                y: e.clientY,
                drawflowId,
                nodeId: config.nodeId,
                isEntry: component.entryNodeId === drawflowId,
                hasBreakpoint,
            };
        }
    });
}

export function setupNodeClickHandling(component) {
    const container = component.querySelector('#drawflow-area');
    if (!container) return;

    let mouseDownPos = null;
    let mouseDownTime = 0;

    container.addEventListener('mousedown', (e) => {
        const node = e.target.closest('.drawflow-node');
        if (node) {
            mouseDownPos = { x: e.clientX, y: e.clientY };
            mouseDownTime = Date.now();
        }
    });

    container.addEventListener('mouseup', (e) => {
        const node = e.target.closest('.drawflow-node');
        if (!node || !mouseDownPos) {
            mouseDownPos = null;
            return;
        }

        const deltaX = Math.abs(e.clientX - mouseDownPos.x);
        const deltaY = Math.abs(e.clientY - mouseDownPos.y);
        const deltaTime = Date.now() - mouseDownTime;

        if (deltaX < 5 && deltaY < 5 && deltaTime < 300) {
            const nodeId = node.id.replace('node-', '');
            const config = component.nodeConfigs.get(nodeId);
            if (config) {
                component.emit('node-selected', {
                    nodeId: config.nodeId,
                    nodeConfig: {
                        ...config,
                        config: { ...config.config }
                    },
                    drawflowId: nodeId,
                });
            }
        }

        mouseDownPos = null;
    });
}


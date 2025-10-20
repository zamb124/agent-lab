import { EventEmitter } from '../core/EventEmitter.js';

/**
 * Менеджер для управления соединениями между нодами
 */
export class ConnectionManager extends EventEmitter {
    constructor(canvas) {
        super();
        
        this.canvas = canvas;
        this.edges = new Map();
        this.tempEdge = null;
        this.connectionStart = null;
        this.isConnecting = false;
    }
    
    /**
     * Начало создания соединения
     */
    startConnection(port) {
        if (port.type !== 'output') {
            console.warn('Соединение можно начать только с выходного порта');
            return;
        }
        
        this.isConnecting = true;
        this.connectionStart = port;
        
        port.setConnecting(true);
        
        this.tempEdge = this.createTempEdge();
        this.canvas.edgesGroup.appendChild(this.tempEdge);
        
        this.emit('connection:start', { port });
    }
    
    /**
     * Обновление временного соединения
     */
    updateConnection(mouseX, mouseY) {
        if (!this.isConnecting || !this.tempEdge || !this.connectionStart) {
            return;
        }
        
        const startPoint = this.connectionStart.getPosition();
        const endPoint = { x: mouseX, y: mouseY };
        
        const path = this.createBezierPath(startPoint, endPoint);
        this.tempEdge.setAttribute('d', path);
    }
    
    /**
     * Завершение создания соединения
     */
    finishConnection(targetPort) {
        if (!this.isConnecting || !this.connectionStart) {
            this.cancelConnection();
            return;
        }
        
        if (!targetPort || targetPort.type !== 'input') {
            this.cancelConnection();
            return;
        }
        
        const sourceNode = this.connectionStart.node;
        const targetNode = targetPort.node;
        
        const validation = this.validateConnection(sourceNode, targetNode);
        if (!validation.valid) {
            console.warn('Невалидное соединение:', validation.reason);
            this.cancelConnection();
            return;
        }
        
        this.createEdge(sourceNode.id, targetNode.id);
        this.cleanupConnection();
    }
    
    /**
     * Отмена создания соединения
     */
    cancelConnection() {
        this.cleanupConnection();
    }
    
    /**
     * Очистка временного соединения
     */
    cleanupConnection() {
        if (this.connectionStart) {
            this.connectionStart.setConnecting(false);
        }
        
        this.tempEdge?.remove();
        this.tempEdge = null;
        this.connectionStart = null;
        this.isConnecting = false;
        
        this.emit('connection:end');
    }
    
    /**
     * Создание временного SVG пути
     */
    createTempEdge() {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.classList.add('temp-edge');
        return path;
    }
    
    /**
     * Создание Bezier пути
     */
    createBezierPath(start, end) {
        const dx = end.x - start.x;
        const controlPointOffset = Math.min(Math.abs(dx) * 0.5, 100);
        
        const cp1x = start.x + controlPointOffset;
        const cp1y = start.y;
        const cp2x = end.x - controlPointOffset;
        const cp2y = end.y;
        
        return `M ${start.x} ${start.y} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${end.x} ${end.y}`;
    }
    
    /**
     * Валидация соединения
     */
    validateConnection(sourceNode, targetNode) {
        if (sourceNode.id === targetNode.id) {
            return { valid: false, reason: 'Нельзя соединить ноду саму с собой' };
        }
        
        const existingEdge = Array.from(this.edges.values()).find(edge => 
            edge.source === sourceNode.id && edge.target === targetNode.id
        );
        
        if (existingEdge) {
            return { valid: false, reason: 'Соединение уже существует' };
        }
        
        if (this.wouldCreateCycle(sourceNode.id, targetNode.id)) {
            return { valid: false, reason: 'Соединение создаст цикл' };
        }
        
        return { valid: true };
    }
    
    /**
     * Проверка на создание цикла
     */
    wouldCreateCycle(sourceId, targetId) {
        const visited = new Set();
        const stack = [targetId];
        
        while (stack.length > 0) {
            const current = stack.pop();
            
            if (current === sourceId) {
                return true;
            }
            
            if (visited.has(current)) {
                continue;
            }
            
            visited.add(current);
            
            const outgoingEdges = Array.from(this.edges.values()).filter(e => e.source === current);
            outgoingEdges.forEach(edge => stack.push(edge.target));
        }
        
        return false;
    }
    
    /**
     * Создание связи
     */
    createEdge(sourceId, targetId) {
        const edgeId = `edge_${sourceId}_${targetId}_${Date.now()}`;
        
        const edge = {
            id: edgeId,
            source: sourceId,
            target: targetId,
            element: null
        };
        
        edge.element = this.createEdgeElement(edge);
        this.canvas.edgesGroup.appendChild(edge.element);
        
        this.edges.set(edgeId, edge);
        
        const sourceNode = this.canvas.nodes.get(sourceId);
        const targetNode = this.canvas.nodes.get(targetId);
        
        if (sourceNode && targetNode) {
            const outputPort = sourceNode.getPort('output');
            const inputPort = targetNode.getPort('input');
            
            if (outputPort) outputPort.addConnection(edgeId);
            if (inputPort) inputPort.addConnection(edgeId);
        }
        
        this.updateEdgePosition(edge);
        
        this.emit('edge:created', { edge });
        
        return edge;
    }
    
    /**
     * Создание SVG элемента связи
     */
    createEdgeElement(edge) {
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.classList.add('edge');
        g.dataset.edgeId = edge.id;
        
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.classList.add('edge-path');
        
        g.appendChild(path);
        
        return g;
    }
    
    /**
     * Обновление позиции связи
     */
    updateEdgePosition(edge) {
        const sourceNode = this.canvas.nodes.get(edge.source);
        const targetNode = this.canvas.nodes.get(edge.target);
        
        if (!sourceNode || !targetNode || !edge.element) {
            return;
        }
        
        const startPoint = sourceNode.getConnectionPoint('output');
        const endPoint = targetNode.getConnectionPoint('input');
        
        const path = this.createBezierPath(startPoint, endPoint);
        const pathElement = edge.element.querySelector('.edge-path');
        
        if (pathElement) {
            pathElement.setAttribute('d', path);
        }
    }
    
    /**
     * Удаление связи
     */
    removeEdge(edgeId) {
        const edge = this.edges.get(edgeId);
        if (!edge) return;
        
        const sourceNode = this.canvas.nodes.get(edge.source);
        const targetNode = this.canvas.nodes.get(edge.target);
        
        if (sourceNode) {
            const outputPort = sourceNode.getPort('output');
            outputPort?.removeConnection(edgeId);
        }
        
        if (targetNode) {
            const inputPort = targetNode.getPort('input');
            inputPort?.removeConnection(edgeId);
        }
        
        edge.element?.remove();
        this.edges.delete(edgeId);
        
        this.emit('edge:removed', { edgeId });
    }
    
    /**
     * Обновление всех связей ноды
     */
    updateNodeEdges(nodeId) {
        const relatedEdges = Array.from(this.edges.values()).filter(
            edge => edge.source === nodeId || edge.target === nodeId
        );
        
        relatedEdges.forEach(edge => this.updateEdgePosition(edge));
    }
    
    /**
     * Получение всех связей
     */
    getAllEdges() {
        return Array.from(this.edges.values());
    }
    
    /**
     * Очистка всех связей
     */
    clear() {
        this.edges.forEach((edge, edgeId) => {
            this.removeEdge(edgeId);
        });
        
        this.cleanupConnection();
    }
}


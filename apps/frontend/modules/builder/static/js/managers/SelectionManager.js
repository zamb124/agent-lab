import { EventEmitter } from '../core/EventEmitter.js';

/**
 * Менеджер для управления выделением нод и связей
 */
export class SelectionManager extends EventEmitter {
    constructor(canvas) {
        super();
        
        this.canvas = canvas;
        this.selectedNodes = new Set();
        this.selectedEdges = new Set();
        this.selectionBox = null;
        this.selectionStart = null;
        this.isSelecting = false;
    }
    
    /**
     * Выделение ноды
     */
    selectNode(node, multiSelect = false) {
        if (!multiSelect) {
            this.clearSelection();
        }
        
        if (this.selectedNodes.has(node)) {
            return;
        }
        
        this.selectedNodes.add(node);
        node.select();
        
        this.emit('selection:changed', { 
            nodes: Array.from(this.selectedNodes),
            edges: Array.from(this.selectedEdges)
        });
    }
    
    /**
     * Снятие выделения с ноды
     */
    deselectNode(node) {
        if (!this.selectedNodes.has(node)) {
            return;
        }
        
        this.selectedNodes.delete(node);
        node.deselect();
        
        this.emit('selection:changed', { 
            nodes: Array.from(this.selectedNodes),
            edges: Array.from(this.selectedEdges)
        });
    }
    
    /**
     * Переключение выделения ноды
     */
    toggleNode(node) {
        if (this.selectedNodes.has(node)) {
            this.deselectNode(node);
        } else {
            this.selectNode(node, true);
        }
    }
    
    /**
     * Выделение связи
     */
    selectEdge(edgeId, multiSelect = false) {
        if (!multiSelect) {
            this.clearSelection();
        }
        
        if (this.selectedEdges.has(edgeId)) {
            return;
        }
        
        this.selectedEdges.add(edgeId);
        
        const edge = this.canvas.connectionManager.edges.get(edgeId);
        if (edge?.element) {
            edge.element.classList.add('selected');
        }
        
        this.emit('selection:changed', { 
            nodes: Array.from(this.selectedNodes),
            edges: Array.from(this.selectedEdges)
        });
    }
    
    /**
     * Снятие выделения со связи
     */
    deselectEdge(edgeId) {
        if (!this.selectedEdges.has(edgeId)) {
            return;
        }
        
        this.selectedEdges.delete(edgeId);
        
        const edge = this.canvas.connectionManager.edges.get(edgeId);
        if (edge?.element) {
            edge.element.classList.remove('selected');
        }
        
        this.emit('selection:changed', { 
            nodes: Array.from(this.selectedNodes),
            edges: Array.from(this.selectedEdges)
        });
    }
    
    /**
     * Очистка всех выделений
     */
    clearSelection() {
        this.selectedNodes.forEach(node => node.deselect());
        this.selectedNodes.clear();
        
        this.selectedEdges.forEach(edgeId => {
            const edge = this.canvas.connectionManager.edges.get(edgeId);
            if (edge?.element) {
                edge.element.classList.remove('selected');
            }
        });
        this.selectedEdges.clear();
        
        this.emit('selection:cleared');
    }
    
    /**
     * Начало выделения областью
     */
    startBoxSelection(x, y) {
        this.isSelecting = true;
        this.selectionStart = { x, y };
        
        this.selectionBox = document.createElement('div');
        this.selectionBox.className = 'selection-box';
        this.selectionBox.style.left = `${x}px`;
        this.selectionBox.style.top = `${y}px`;
        
        this.canvas.overlay.appendChild(this.selectionBox);
    }
    
    /**
     * Обновление выделения областью
     */
    updateBoxSelection(currentX, currentY) {
        if (!this.isSelecting || !this.selectionBox || !this.selectionStart) {
            return;
        }
        
        const x = Math.min(this.selectionStart.x, currentX);
        const y = Math.min(this.selectionStart.y, currentY);
        const width = Math.abs(currentX - this.selectionStart.x);
        const height = Math.abs(currentY - this.selectionStart.y);
        
        this.selectionBox.style.left = `${x}px`;
        this.selectionBox.style.top = `${y}px`;
        this.selectionBox.style.width = `${width}px`;
        this.selectionBox.style.height = `${height}px`;
        
        this.selectNodesInBox(x, y, width, height);
    }
    
    /**
     * Завершение выделения областью
     */
    finishBoxSelection() {
        this.isSelecting = false;
        this.selectionStart = null;
        
        if (this.selectionBox) {
            this.selectionBox.remove();
            this.selectionBox = null;
        }
    }
    
    /**
     * Выделение нод в области
     */
    selectNodesInBox(x, y, width, height) {
        this.clearSelection();
        
        this.canvas.nodes.forEach(node => {
            const nodeX = node.x;
            const nodeY = node.y;
            const nodeRight = nodeX + node.width;
            const nodeBottom = nodeY + node.height;
            
            const boxRight = x + width;
            const boxBottom = y + height;
            
            const intersects = !(nodeRight < x || nodeX > boxRight || nodeBottom < y || nodeY > boxBottom);
            
            if (intersects) {
                this.selectNode(node, true);
            }
        });
    }
    
    /**
     * Выделение всех нод
     */
    selectAll() {
        this.canvas.nodes.forEach(node => {
            this.selectNode(node, true);
        });
    }
    
    /**
     * Получение выделенных нод
     */
    getSelectedNodes() {
        return Array.from(this.selectedNodes);
    }
    
    /**
     * Получение выделенных связей
     */
    getSelectedEdges() {
        return Array.from(this.selectedEdges);
    }
    
    /**
     * Проверка наличия выделения
     */
    hasSelection() {
        return this.selectedNodes.size > 0 || this.selectedEdges.size > 0;
    }
    
    /**
     * Удаление выделенных элементов
     */
    deleteSelected() {
        const nodesToDelete = Array.from(this.selectedNodes);
        const edgesToDelete = Array.from(this.selectedEdges);
        
        this.clearSelection();
        
        nodesToDelete.forEach(node => {
            this.canvas.removeNode(node.id);
        });
        
        edgesToDelete.forEach(edgeId => {
            this.canvas.connectionManager.removeEdge(edgeId);
        });
        
        this.emit('selection:deleted', { 
            nodesCount: nodesToDelete.length,
            edgesCount: edgesToDelete.length
        });
    }
}


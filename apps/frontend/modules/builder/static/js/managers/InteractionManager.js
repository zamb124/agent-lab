import { EventEmitter } from '../core/EventEmitter.js';

/**
 * Менеджер для управления взаимодействиями: zoom, pan, drag
 */
export class InteractionManager extends EventEmitter {
    constructor(canvas) {
        super();
        
        this.canvas = canvas;
        
        // Состояние
        this.isPanning = false;
        this.isDragging = false;
        this.draggedNodes = new Set();
        this.lastMousePos = null;
        this.dragStartPositions = new Map();
        
        // Настройки
        this.minZoom = 0.1;
        this.maxZoom = 3;
        this.zoomStep = 0.02;
    }
    
    /**
     * Обработка zoom (колесико мыши)
     */
    handleWheel(e) {
        e.preventDefault();
        
        const container = this.canvas.element.querySelector('#canvasContainer');
        const rect = container.getBoundingClientRect();
        
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        const delta = e.deltaY > 0 ? -this.zoomStep : this.zoomStep;
        const newZoom = Math.max(this.minZoom, Math.min(this.maxZoom, this.canvas.zoom + delta));
        
        if (newZoom === this.canvas.zoom) return;
        
        const zoomRatio = newZoom / this.canvas.zoom;
        
        this.canvas.panX = mouseX - (mouseX - this.canvas.panX) * zoomRatio;
        this.canvas.panY = mouseY - (mouseY - this.canvas.panY) * zoomRatio;
        this.canvas.zoom = newZoom;
        
        this.canvas.updateTransform();
        this.emit('zoom:changed', { zoom: newZoom });
    }
    
    /**
     * Zoom In
     */
    zoomIn() {
        const newZoom = Math.min(this.maxZoom, this.canvas.zoom + 0.1);
        this.setZoom(newZoom);
    }
    
    /**
     * Zoom Out
     */
    zoomOut() {
        const newZoom = Math.max(this.minZoom, this.canvas.zoom - 0.1);
        this.setZoom(newZoom);
    }
    
    /**
     * Установка zoom
     */
    setZoom(newZoom) {
        this.canvas.zoom = newZoom;
        this.canvas.updateTransform();
        this.emit('zoom:changed', { zoom: newZoom });
    }
    
    /**
     * Fit to screen
     */
    fitToScreen() {
        if (this.canvas.nodes.size === 0) {
            this.canvas.zoom = 1;
            this.canvas.panX = 0;
            this.canvas.panY = 0;
            this.canvas.updateTransform();
            return;
        }
        
        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;
        
        this.canvas.nodes.forEach(node => {
            minX = Math.min(minX, node.x);
            minY = Math.min(minY, node.y);
            maxX = Math.max(maxX, node.x + node.width);
            maxY = Math.max(maxY, node.y + node.height);
        });
        
        const graphWidth = maxX - minX;
        const graphHeight = maxY - minY;
        
        const container = this.canvas.element.querySelector('#canvasContainer');
        const rect = container.getBoundingClientRect();
        
        const padding = 100;
        const zoomX = (rect.width - padding * 2) / graphWidth;
        const zoomY = (rect.height - padding * 2) / graphHeight;
        
        this.canvas.zoom = Math.min(zoomX, zoomY, 1);
        
        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        
        this.canvas.panX = rect.width / 2 - centerX * this.canvas.zoom;
        this.canvas.panY = rect.height / 2 - centerY * this.canvas.zoom;
        
        this.canvas.updateTransform();
        this.emit('zoom:changed', { zoom: this.canvas.zoom });
    }
    
    /**
     * Начало панорамирования
     */
    startPanning(e) {
        if (e.button !== 0 || e.target.closest('.canvas-node')) {
            return;
        }
        
        this.isPanning = true;
        this.lastMousePos = { x: e.clientX, y: e.clientY };
        
        this.emit('pan:start');
    }
    
    /**
     * Обновление панорамирования
     */
    updatePanning(e) {
        if (!this.isPanning || !this.lastMousePos) return;
        
        const dx = e.clientX - this.lastMousePos.x;
        const dy = e.clientY - this.lastMousePos.y;
        
        this.canvas.panX += dx;
        this.canvas.panY += dy;
        
        this.lastMousePos = { x: e.clientX, y: e.clientY };
        
        this.canvas.updateTransform();
    }
    
    /**
     * Завершение панорамирования
     */
    stopPanning() {
        if (!this.isPanning) return;
        
        this.isPanning = false;
        this.lastMousePos = null;
        
        this.emit('pan:end');
    }
    
    /**
     * Начало перетаскивания нод
     */
    startDragging(node, e) {
        this.isDragging = true;
        
        const selectedNodes = this.canvas.selectionManager.getSelectedNodes();
        
        if (selectedNodes.includes(node)) {
            this.draggedNodes = new Set(selectedNodes);
        } else {
            this.draggedNodes = new Set([node]);
        }
        
        this.lastMousePos = { x: e.clientX, y: e.clientY };
        
        this.draggedNodes.forEach(n => {
            this.dragStartPositions.set(n.id, { x: n.x, y: n.y });
            n.startDrag();
        });
        
        this.emit('drag:start', { nodes: Array.from(this.draggedNodes) });
    }
    
    /**
     * Обновление перетаскивания
     */
    updateDragging(e) {
        if (!this.isDragging || !this.lastMousePos) return;
        
        const dx = (e.clientX - this.lastMousePos.x) / this.canvas.zoom;
        const dy = (e.clientY - this.lastMousePos.y) / this.canvas.zoom;
        
        this.draggedNodes.forEach(node => {
            const newX = node.x + dx;
            const newY = node.y + dy;
            node.setPosition(newX, newY);
            
            this.canvas.connectionManager.updateNodeEdges(node.id);
        });
        
        this.lastMousePos = { x: e.clientX, y: e.clientY };
    }
    
    /**
     * Завершение перетаскивания
     */
    stopDragging() {
        if (!this.isDragging) return;
        
        this.draggedNodes.forEach(node => {
            node.stopDrag();
        });
        
        this.emit('drag:end', { 
            nodes: Array.from(this.draggedNodes),
            positions: Array.from(this.dragStartPositions)
        });
        
        this.isDragging = false;
        this.draggedNodes.clear();
        this.dragStartPositions.clear();
        this.lastMousePos = null;
    }
    
    /**
     * Преобразование координат экрана в координаты канваса
     */
    screenToCanvas(screenX, screenY) {
        return {
            x: (screenX - this.canvas.panX) / this.canvas.zoom,
            y: (screenY - this.canvas.panY) / this.canvas.zoom
        };
    }
    
    /**
     * Преобразование координат канваса в координаты экрана
     */
    canvasToScreen(canvasX, canvasY) {
        return {
            x: canvasX * this.canvas.zoom + this.canvas.panX,
            y: canvasY * this.canvas.zoom + this.canvas.panY
        };
    }
}


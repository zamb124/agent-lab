import { EventEmitter } from '../core/EventEmitter.js';
import { NodeFactory } from '../core/NodeFactory.js';
import { ConnectionManager } from '../managers/ConnectionManager.js';
import { SelectionManager } from '../managers/SelectionManager.js';
import { InteractionManager } from '../managers/InteractionManager.js';
import { ElementSelector } from '../managers/ElementSelector.js';
import { ContextMenuManager } from '../managers/ContextMenuManager.js';

/**
 * Ядро Canvas - координатор всех компонентов
 */
export class CanvasCore extends EventEmitter {
    constructor(element, builder) {
        super();
        
        this.element = element;
        this.builder = builder;
        
        // SVG элементы
        this.svg = null;
        this.nodesGroup = null;
        this.edgesGroup = null;
        this.overlay = null;
        
        // Состояние трансформации
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        
        // Коллекции
        this.nodes = new Map();
        
        // Менеджеры
        this.nodeFactory = null;
        this.connectionManager = null;
        this.selectionManager = null;
        this.interactionManager = null;
        this.elementSelector = null;
        this.contextMenuManager = null;
    }
    
    /**
     * Инициализация canvas
     */
    async init() {
        console.log('🎨 CanvasCore.init() начало');
        
        try {
            console.log('📐 Настройка DOM элементов...');
            this.setupElements();
            
            console.log('⚙️ Настройка менеджеров...');
            this.setupManagers();
            
            console.log('🔗 Настройка событий...');
            this.setupEventListeners();
            
            console.log('🎯 Обновление трансформации...');
            this.updateTransform();
            
            this.emit('canvas:ready');
            console.log('✅ CanvasCore инициализирован');
        } catch (error) {
            console.error('❌ Ошибка инициализации CanvasCore:', error);
            throw error;
        }
    }
    
    /**
     * Настройка DOM элементов
     */
    setupElements() {
        this.svg = this.element.querySelector('#canvasSvg');
        this.nodesGroup = this.element.querySelector('#nodesGroup');
        this.edgesGroup = this.element.querySelector('#edgesGroup');
        this.overlay = this.element.querySelector('#canvasOverlay');
        
        if (!this.svg || !this.nodesGroup || !this.edgesGroup || !this.overlay) {
            throw new Error('Не найдены необходимые элементы canvas');
        }
    }
    
    /**
     * Настройка менеджеров
     */
    setupManagers() {
        this.nodeFactory = new NodeFactory(this);
        this.connectionManager = new ConnectionManager(this);
        this.selectionManager = new SelectionManager(this);
        this.interactionManager = new InteractionManager(this);
        this.elementSelector = new ElementSelector(this);
        this.contextMenuManager = new ContextMenuManager(this);
        
        // Делаем менеджеры доступными глобально
        if (this.builder) {
            this.builder.elementSelector = this.elementSelector;
            this.builder.contextMenuManager = this.contextMenuManager;
        }
        
        // Подписываемся на события менеджеров
        this.subscribeToManagers();
    }
    
    /**
     * Подписка на события менеджеров
     */
    subscribeToManagers() {
        // События нод
        this.on('node:moved', ({ node }) => {
            this.connectionManager.updateNodeEdges(node.id);
        });
        
        // События портов
        this.on('port:mousedown', ({ node, port, event }) => {
            this.connectionManager.startConnection(port);
        });
        
        // События нод - клик
        this.on('node:click', ({ node, event }) => {
            const multiSelect = event.ctrlKey || event.metaKey;
            
            if (multiSelect) {
                this.selectionManager.toggleNode(node);
            } else {
                this.selectionManager.selectNode(node, false);
            }
        });
        
        // События нод - начало drag
        this.on('node:mousedown', ({ node, event }) => {
            if (event.button !== 0) return;
            
            this.interactionManager.startDragging(node, event);
        });
        
        // События нод - контекстное меню
        this.on('node:contextmenu', ({ node, event }) => {
            this.contextMenuManager.showNodeMenu(node, event);
        });
        
        // События контекстного меню - редактирование
        this.contextMenuManager.on('node:edit', ({ node }) => {
            this.emit('node:edit', { node });
        });
        
        // События связей - пробрасываем от ConnectionManager
        this.connectionManager.on('edge:created', (data) => {
            this.emit('edge:created', data);
        });
    }
    
    /**
     * Настройка обработчиков событий
     */
    setupEventListeners() {
        const container = this.element.querySelector('#canvasContainer');
        
        // Зум
        container.addEventListener('wheel', (e) => {
            this.interactionManager.handleWheel(e);
        });
        
        // Панорамирование и drag
        container.addEventListener('mousedown', (e) => {
            if (e.target.closest('.canvas-node')) {
                // Drag ноды - обрабатывается в подписке на node:mousedown
                return;
            }
            
            // Панорамирование
            this.interactionManager.startPanning(e);
        });
        
        container.addEventListener('mousemove', (e) => {
            if (this.connectionManager.isConnecting) {
                const rect = this.svg.getBoundingClientRect();
                const mouseX = (e.clientX - rect.left - this.panX) / this.zoom;
                const mouseY = (e.clientY - rect.top - this.panY) / this.zoom;
                this.connectionManager.updateConnection(mouseX, mouseY);
            } else if (this.interactionManager.isDragging) {
                this.interactionManager.updateDragging(e);
            } else if (this.interactionManager.isPanning) {
                this.interactionManager.updatePanning(e);
            }
        });
        
        container.addEventListener('mouseup', (e) => {
            if (this.connectionManager.isConnecting) {
                const targetPort = e.target.closest('.port');
                if (targetPort) {
                    const nodeElement = targetPort.closest('.canvas-node');
                    const nodeId = nodeElement?.dataset.nodeId;
                    const portId = targetPort.dataset.portId;
                    
                    if (nodeId) {
                        const node = this.nodes.get(nodeId);
                        const port = node?.getPort(portId);
                        
                        this.connectionManager.finishConnection(port);
                    } else {
                        this.connectionManager.cancelConnection();
                    }
                } else {
                    this.connectionManager.cancelConnection();
                }
            }
            
            this.interactionManager.stopDragging();
            this.interactionManager.stopPanning();
        });
        
        container.addEventListener('mouseleave', () => {
            this.connectionManager.cancelConnection();
            this.interactionManager.stopDragging();
            this.interactionManager.stopPanning();
        });
        
        
        // Клавиатура
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Delete' || e.key === 'Backspace') {
                if (!e.target.matches('input, textarea')) {
                    e.preventDefault();
                    this.selectionManager.deleteSelected();
                }
            }
            
            if ((e.ctrlKey || e.metaKey) && e.key === 'a') {
                if (!e.target.matches('input, textarea')) {
                    e.preventDefault();
                    this.selectionManager.selectAll();
                }
            }
        });
    }
    
    /**
     * Добавление ноды
     */
    async addNode(nodeData, options = {}) {
        const node = await this.nodeFactory.createNode(nodeData);
        
        // Монтируем ноду
        node.mount(this.overlay);
        
        // Сохраняем в коллекции
        this.nodes.set(node.id, node);
        
        // Подписываемся на события ноды
        node.on('node:moved', (data) => this.emit('node:moved', data));
        node.on('node:click', (data) => this.emit('node:click', data));
        node.on('node:mousedown', (data) => this.emit('node:mousedown', data));
        node.on('node:contextmenu', (data) => this.emit('node:contextmenu', data));
        node.on('port:mousedown', (data) => this.emit('port:mousedown', data));
        
        this.emit('node:added', { node });
        
        // Автоматическое разворачивание любой ноды (если не отключено)
        if (options.autoExpand !== false) {
            await this.expandNode(node, options.layoutManager);
        }
        
        return node;
    }
    
    /**
     * Рекурсивное разворачивание ноды
     */
    async expandNode(node, layoutManager = null) {
        console.log('🌳 Разворачиваем ноду:', node.id, node.type);
        
        // Используем переданный layoutManager или создаем новый
        if (!layoutManager) {
            const { LayoutManager } = await import('/static/builder/js/managers/LayoutManager.js');
            layoutManager = new LayoutManager();
        }
        
        try {
            await node.expand(layoutManager);
            console.log('✅ Нода развернута:', node.id);
        } catch (error) {
            console.error('❌ Ошибка разворачивания ноды:', error);
        }
    }
    
    /**
     * Удаление ноды
     */
    removeNode(nodeId, cascadeDelete = true) {
        const node = this.nodes.get(nodeId);
        if (!node) return;
        
        // Удаляем связанные edges
        if (cascadeDelete) {
            const relatedEdges = this.connectionManager.getAllEdges().filter(
                edge => edge.source === nodeId || edge.target === nodeId
            );
            
            relatedEdges.forEach(edge => {
                this.connectionManager.removeEdge(edge.id);
            });
        }
        
        // Уничтожаем ноду
        node.destroy();
        this.nodes.delete(nodeId);
        
        this.emit('node:removed', { nodeId });
    }
    
    /**
     * Загрузка графа
     */
    async loadGraph(graphData) {
        console.log('🎨 loadGraph called with:', graphData);
        this.clearGraph();

        if (!graphData || !graphData.nodes) {
            console.log('⚠️ loadGraph: no graphData or nodes');
            return;
        }

        console.log(`📦 loadGraph: loading ${graphData.nodes.length} nodes and ${graphData.edges?.length || 0} edges`);

        for (const nodeData of graphData.nodes) {
            const processedNodeData = { ...nodeData };

            // НЕ используем ui из graphData - координаты будут применены отдельно из canvas_data
            delete processedNodeData.ui;
            if (processedNodeData.params?.ui) {
                delete processedNodeData.params.ui;
            }

            console.log(`➕ loadGraph: adding node ${nodeData.id} without ui (will be applied later)`);
            await this.addNode(processedNodeData, { autoExpand: false });
        }

        if (graphData.edges) {
            for (const edgeData of graphData.edges) {
                console.log(`🔗 loadGraph: creating edge ${edgeData.source} -> ${edgeData.target}`);
                this.connectionManager.createEdge(edgeData.source, edgeData.target);
            }
        }

        console.log('✅ loadGraph: emitting graph:loaded event with nodes count:', this.nodes.size);
        this.emit('graph:loaded', { graphData });
    }
    
    /**
     * Получение данных графа
     */
    getGraphData() {
        const nodes = Array.from(this.nodes.values()).map(node => node.toJSON());
        const edges = this.connectionManager.getAllEdges().map(edge => ({
            id: edge.id,
            source: edge.source,
            target: edge.target
        }));

        return { nodes, edges };
    }
    
    /**
     * Очистка графа
     */
    clearGraph() {
        this.nodes.forEach((node, nodeId) => {
            this.removeNode(nodeId, false);
        });
        
        this.connectionManager.clear();
        this.selectionManager.clearSelection();
        
        this.emit('graph:cleared');
    }
    
    /**
     * Обновление трансформации
     */
    updateTransform() {
        if (!this.nodesGroup) return;
        
        this.nodesGroup.setAttribute(
            'transform',
            `translate(${this.panX}, ${this.panY}) scale(${this.zoom})`
        );
        
        this.edgesGroup.setAttribute(
            'transform',
            `translate(${this.panX}, ${this.panY}) scale(${this.zoom})`
        );
        
        this.overlay.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
        
        this.updateZoomIndicator();
    }
    
    /**
     * Обновление индикатора zoom
     */
    updateZoomIndicator() {
        const zoomIndicator = document.getElementById('zoomIndicator');
        if (zoomIndicator) {
            zoomIndicator.textContent = `${Math.round(this.zoom * 100)}%`;
        }
    }
    
    /**
     * Получение центральной позиции
     */
    getCenterPosition() {
        const container = this.element.querySelector('#canvasContainer');
        const rect = container.getBoundingClientRect();
        
        const centerX = (rect.width / 2 - this.panX) / this.zoom;
        const centerY = (rect.height / 2 - this.panY) / this.zoom;
        
        return { x: centerX, y: centerY };
    }
    
    /**
     * Уничтожение canvas
     */
    destroy() {
        this.clearGraph();
        this.removeAllListeners();
        
        this.nodes = null;
        this.nodeFactory = null;
        this.connectionManager = null;
        this.selectionManager = null;
        this.interactionManager = null;
    }
}


import { EventEmitter } from './EventEmitter.js';
import { Port } from './Port.js';

/**
 * Базовый класс для всех нод
 */
export class BaseNode extends EventEmitter {
    constructor(data, canvas) {
        super();
        
        this.id = data.id;
        this.type = data.type;
        this.data = data;
        this.canvas = canvas;
        
        this.x = data.ui?.x || 0;
        this.y = data.ui?.y || 0;
        this.width = data.ui?.width || 200;
        this.height = data.ui?.height || 100;
        
        this.element = null;
        this.ports = new Map();
        this.selected = false;
        this.dragging = false;
    }
    
    /**
     * Lifecycle: Создание ноды
     */
    async create() {
        this.element = await this.createDOMElement();
        this.setupElement();
        await this.createPorts();
        this.attachEventHandlers();
        
        this.emit('node:created', { node: this });
        return this;
    }
    
    /**
     * Настройка DOM элемента
     */
    setupElement() {
        if (!this.element) return;
        
        this.element.dataset.nodeId = this.id;
        this.element.dataset.nodeType = this.type;
        this.element.className = 'canvas-node';
        this.updateTransform();
    }
    
    /**
     * Lifecycle: Монтирование в DOM
     */
    mount(container) {
        if (!this.element) {
            console.error('Попытка монтировать несозданную ноду');
            return;
        }
        
        container.appendChild(this.element);
        this.updateSizeFromDOM();
        
        this.emit('node:mounted', { node: this });
    }
    
    /**
     * Lifecycle: Обновление данных
     */
    update(newData) {
        const oldData = this.data;
        this.data = { ...this.data, ...newData };
        
        this.emit('node:updated', { node: this, oldData, newData });
    }
    
    /**
     * Обновление отображения ноды (перерисовка контента)
     */
    async updateDisplay() {
        if (!this.element) return;
        
        // Создаем временный элемент для получения нового HTML
        const tempElement = await this.createDOMElement();
        
        // Обновляем только innerHTML, не трогая сам элемент
        this.element.innerHTML = tempElement.innerHTML;
        
        // Перемонтируем порты на обновленный элемент
        this.ports.forEach(port => port.mount(this.element));
    }
    
    /**
     * Lifecycle: Уничтожение ноды
     */
    destroy() {
        this.emit('node:beforeDestroy', { node: this });
        
        this.detachEventHandlers();
        this.ports.forEach(port => port.destroy());
        this.ports.clear();
        this.element?.remove();
        this.removeAllListeners();
        
        this.element = null;
        
        this.emit('node:destroyed', { node: this });
    }
    
    /**
     * Рекурсивное разворачивание ноды
     * Переопределяется в подклассах для загрузки дочерних элементов
     */
    async expand(layoutManager) {
        return [];
    }
    
    /**
     * Получение дочерних нод
     */
    getChildNodes() {
        const childEdges = Array.from(this.canvas.connectionManager.edges.values())
            .filter(edge => edge.source === this.id);
        
        return childEdges.map(edge => this.canvas.nodes.get(edge.target)).filter(Boolean);
    }
    
    /**
     * Получение всех достижимых потомков рекурсивно
     */
    getAllDescendantNodes() {
        const descendants = [];
        const visited = new Set();
        
        const collect = (node) => {
            if (visited.has(node.id)) {
                return;
            }
            visited.add(node.id);
            descendants.push(node);
            
            const children = node.getChildNodes();
            children.forEach(child => collect(child));
        };
        
        const directChildren = this.getChildNodes();
        directChildren.forEach(child => collect(child));
        
        return descendants;
    }
    
    /**
     * Абстрактный метод: создание DOM элемента
     * Должен быть переопределен в подклассах
     */
    async createDOMElement() {
        throw new Error('BaseNode.createDOMElement() must be implemented');
    }
    
    /**
     * Абстрактный метод: создание портов
     * Должен быть переопределен в подклассах
     */
    async createPorts() {
        throw new Error('BaseNode.createPorts() must be implemented');
    }
    
    /**
     * Создание порта
     */
    createPort(id, type, label = null) {
        const port = new Port({ id, type, node: this, label });
        
        port.on('port:mousedown', ({ port, event }) => {
            this.emit('port:mousedown', { node: this, port, event });
        });
        
        this.ports.set(id, port);
        return port;
    }
    
    /**
     * Монтирование портов в DOM
     */
    mountPorts() {
        this.ports.forEach(port => port.mount(this.element));
    }
    
    /**
     * Получение порта по ID
     */
    getPort(portId) {
        return this.ports.get(portId);
    }
    
    /**
     * Привязка обработчиков событий
     */
    attachEventHandlers() {
        if (!this.element) return;
        
        this.handleMouseDown = this.onMouseDown.bind(this);
        this.handleClick = this.onClick.bind(this);
        this.handleContextMenu = this.onContextMenu.bind(this);
        
        this.element.addEventListener('mousedown', this.handleMouseDown);
        this.element.addEventListener('click', this.handleClick);
        this.element.addEventListener('contextmenu', this.handleContextMenu);
    }
    
    /**
     * Отвязка обработчиков событий
     */
    detachEventHandlers() {
        if (!this.element) return;
        
        if (this.handleMouseDown) {
            this.element.removeEventListener('mousedown', this.handleMouseDown);
            this.handleMouseDown = null;
        }
        
        if (this.handleClick) {
            this.element.removeEventListener('click', this.handleClick);
            this.handleClick = null;
        }
        
        if (this.handleContextMenu) {
            this.element.removeEventListener('contextmenu', this.handleContextMenu);
            this.handleContextMenu = null;
        }
    }
    
    /**
     * Обработка mousedown
     */
    onMouseDown(e) {
        if (e.button !== 0) return;
        
        // Игнорируем клики по портам - они обрабатываются отдельно
        if (e.target.closest('.port')) {
            return;
        }
        
        this.emit('node:mousedown', { node: this, event: e });
    }
    
    /**
     * Обработка клика
     */
    onClick(e) {
        if (e.button !== 0) return;
        
        this.emit('node:click', { node: this, event: e });
    }
    
    /**
     * Обработка контекстного меню (правый клик)
     */
    onContextMenu(e) {
        e.preventDefault();
        this.emit('node:contextmenu', { node: this, event: e });
    }
    
    /**
     * Обновление позиции
     */
    setPosition(x, y) {
        this.x = x;
        this.y = y;
        this.updateTransform();
        
        this.emit('node:moved', { node: this, x, y });
    }
    
    /**
     * Обновление трансформации
     */
    updateTransform() {
        if (!this.element) return;
        this.element.style.transform = `translate3d(${this.x}px, ${this.y}px, 0)`;
    }
    
    /**
     * Обновление размеров из DOM
     */
    updateSizeFromDOM() {
        if (!this.element) return;
        
        setTimeout(() => {
            const rect = this.element.getBoundingClientRect();
            this.width = rect.width / this.canvas.zoom;
            this.height = rect.height / this.canvas.zoom;
            
            this.emit('node:resized', { node: this, width: this.width, height: this.height });
        }, 50);
    }
    
    /**
     * Выделение ноды
     */
    select() {
        if (this.selected) return;
        
        this.selected = true;
        this.element?.classList.add('selected');
        
        this.emit('node:selected', { node: this });
    }
    
    /**
     * Снятие выделения
     */
    deselect() {
        if (!this.selected) return;
        
        this.selected = false;
        this.element?.classList.remove('selected');
        
        this.emit('node:deselected', { node: this });
    }
    
    /**
     * Начало перетаскивания
     */
    startDrag() {
        this.dragging = true;
        this.element?.classList.add('dragging');
        
        this.emit('node:dragstart', { node: this });
    }
    
    /**
     * Завершение перетаскивания
     */
    stopDrag() {
        this.dragging = false;
        this.element?.classList.remove('dragging');
        
        this.emit('node:dragend', { node: this });
    }
    
    /**
     * Получение центральной точки ноды
     */
    getCenter() {
        return {
            x: this.x + this.width / 2,
            y: this.y + this.height / 2
        };
    }
    
    /**
     * Получение точки соединения
     */
    getConnectionPoint(portType) {
        const center = this.getCenter();
        
        if (portType === 'input') {
            return { x: this.x, y: center.y };
        } else {
            return { x: this.x + this.width, y: center.y };
        }
    }
    
    /**
     * Сериализация в JSON (для canvas_data)
     */
    toJSON() {
        return {
            id: this.id,
            type: this.type,
            ...this.data,
            ui: {
                x: this.x,
                y: this.y,
                width: this.width,
                height: this.height
            }
        };
    }
    
    /**
     * Сериализация в graph_definition формат
     * Переопределяется в подклассах для сохранения дочерних элементов
     */
    async serializeToGraph() {
        return {
            id: this.id,
            type: this.type,
            params: this.data.params || {}
        };
    }
    
    /**
     * Рекурсивное сохранение ноды и всех дочерних элементов
     * Переопределяется в подклассах (FlowNode, AgentNode)
     */
    async save() {
        console.log('💾 BaseNode.save() - нет реализации для', this.type);
        return { success: true };
    }
}



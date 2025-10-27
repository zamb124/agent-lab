import { EventEmitter } from './EventEmitter.js';

/**
 * Порт для соединения нод
 */
export class Port extends EventEmitter {
    constructor({ id, type, node, label = null }) {
        super();
        
        this.id = id;
        this.type = type; // 'input' или 'output'
        this.node = node;
        this.label = label;
        this.element = null;
        this.connections = new Set();
    }
    
    /**
     * Создание DOM элемента порта
     */
    createElement() {
        const port = document.createElement('div');
        port.className = `port ${this.type}-port`;
        port.dataset.portType = this.type;
        port.dataset.portId = this.id;
        
        const dot = document.createElement('div');
        dot.className = 'port-dot';
        port.appendChild(dot);
        
        // Добавляем лейбл если есть
        if (this.label) {
            const labelEl = document.createElement('span');
            labelEl.className = 'port-label';
            labelEl.textContent = this.label;
            port.appendChild(labelEl);
        }
        
        return port;
    }
    
    /**
     * Монтирование порта в DOM
     */
    mount(parentElement) {
        if (this.element) {
            console.warn('Порт уже смонтирован');
            return;
        }
        
        this.element = this.createElement();
        
        const portsContainer = this.getOrCreatePortsContainer(parentElement);
        const portsGroup = this.getOrCreatePortsGroup(portsContainer);
        
        portsGroup.appendChild(this.element);
        this.attachEventHandlers();
    }
    
    /**
     * Получение или создание контейнера портов
     */
    getOrCreatePortsContainer(parentElement) {
        let container = parentElement.querySelector('.node-ports');
        if (!container) {
            container = document.createElement('div');
            container.className = 'node-ports';
            parentElement.appendChild(container);
        }
        return container;
    }
    
    /**
     * Получение или создание группы портов (input/output)
     */
    getOrCreatePortsGroup(container) {
        const groupClass = `${this.type}-ports`;
        let group = container.querySelector(`.${groupClass}`);
        if (!group) {
            group = document.createElement('div');
            group.className = groupClass;
            container.appendChild(group);
        }
        return group;
    }
    
    /**
     * Привязка обработчиков событий
     */
    attachEventHandlers() {
        if (!this.element) return;
        
        this.handleMouseDown = this.onMouseDown.bind(this);
        this.element.addEventListener('mousedown', this.handleMouseDown);
    }
    
    /**
     * Отвязка обработчиков событий
     */
    detachEventHandlers() {
        if (!this.element || !this.handleMouseDown) return;
        
        this.element.removeEventListener('mousedown', this.handleMouseDown);
        this.handleMouseDown = null;
    }
    
    /**
     * Обработка клика по порту
     */
    onMouseDown(e) {
        e.stopPropagation();
        this.emit('port:mousedown', { port: this, event: e });
    }
    
    /**
     * Добавление соединения
     */
    addConnection(edgeId) {
        this.connections.add(edgeId);
        this.updateConnectionState();
    }
    
    /**
     * Удаление соединения
     */
    removeConnection(edgeId) {
        this.connections.delete(edgeId);
        this.updateConnectionState();
    }
    
    /**
     * Обновление визуального состояния
     */
    updateConnectionState() {
        if (!this.element) return;
        
        if (this.connections.size > 0) {
            this.element.classList.add('connected');
        } else {
            this.element.classList.remove('connected');
        }
    }
    
    /**
     * Подсветка порта
     */
    highlight() {
        if (!this.element) return;
        this.element.classList.add('highlight');
    }
    
    /**
     * Снятие подсветки
     */
    unhighlight() {
        if (!this.element) return;
        this.element.classList.remove('highlight');
    }
    
    /**
     * Активация состояния соединения
     */
    setConnecting(isConnecting) {
        if (!this.element) return;
        
        if (isConnecting) {
            this.element.classList.add('connecting');
        } else {
            this.element.classList.remove('connecting');
        }
    }
    
    /**
     * Получение позиции порта на канвасе
     */
    getPosition() {
        if (!this.element) return { x: 0, y: 0 };
        
        const rect = this.element.getBoundingClientRect();
        const canvas = this.node.canvas;
        
        const x = (rect.left + rect.width / 2 - canvas.panX) / canvas.zoom;
        const y = (rect.top + rect.height / 2 - canvas.panY) / canvas.zoom;
        
        return { x, y };
    }
    
    /**
     * Уничтожение порта
     */
    destroy() {
        this.detachEventHandlers();
        this.removeAllListeners();
        this.element?.remove();
        this.element = null;
        this.connections.clear();
    }
}


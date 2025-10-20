/**
 * Управление канвасом Builder на базе SVG + Vanilla JS
 */

export function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export default class BuilderCanvas {
    constructor(element, builder) {
        this.element = element;
        this.builder = builder;
        
        // SVG элементы
        this.svg = null;
        this.nodesGroup = null;
        this.edgesGroup = null;
        this.overlay = null;
        
        // Состояние
        this.nodes = new Map();
        this.edges = new Map();
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
        
        // Взаимодействие
        this.isDragging = false;
        this.isPanning = false;
        this.isConnecting = false;
        this.draggedNode = null;
        this.connectionStart = null;
        this.tempEdge = null;
        
        // Выделение
        this.isSelecting = false;
        this.selectionBox = null;
        this.selectionStart = null;
        
        // Настройки
        this.config = {
            nodeWidth: 200,
            nodeHeight: 100,
            gridSize: 20,
            minZoom: 0.1,
            maxZoom: 3,
            zoomStep: 0.02  // Очень плавное масштабирование (2% за скролл)
        };
        
        // Throttling для обновления связей
        this.edgeUpdateThrottle = null;
    }
    
    /**
     * Инициализация канваса
     */
    async init() {
        this.setupElements();
        this.setupEventListeners();
        this.updateTransform();
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
            throw new Error('Не найдены необходимые элементы канваса');
        }
    }
    
    /**
     * Настройка обработчиков событий
     */
    setupEventListeners() {
        const canvasContainer = this.element.querySelector('#canvasContainer');
        
        // Зум и панорамирование на контейнере канваса
        canvasContainer.addEventListener('wheel', (e) => this.handleWheel(e));
        canvasContainer.addEventListener('mousedown', (e) => this.handleMouseDown(e));
        canvasContainer.addEventListener('mousemove', (e) => this.handleMouseMove(e));
        canvasContainer.addEventListener('mouseup', (e) => this.handleMouseUp(e));
        canvasContainer.addEventListener('mouseleave', (e) => this.handleMouseLeave(e));
        
        // Кнопки зума
        const zoomInBtn = document.getElementById('zoomInBtn');
        const zoomOutBtn = document.getElementById('zoomOutBtn');
        const fitToScreenBtn = document.getElementById('fitToScreenBtn');
        
        if (zoomInBtn) zoomInBtn.addEventListener('click', () => this.zoomIn());
        if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => this.zoomOut());
        if (fitToScreenBtn) fitToScreenBtn.addEventListener('click', () => this.fitToScreen());
        
        // Предотвращаем контекстное меню на SVG
        this.svg.addEventListener('contextmenu', (e) => e.preventDefault());
    }
    
    /**
     * Загрузка графа
     */
    async loadGraph(graphData) {
        try {
            // Очищаем текущий граф
            this.clearGraph();
            
            // Загружаем ноды
            if (graphData.nodes) {
                for (const nodeData of graphData.nodes) {
                    await this.addNode(nodeData);
                }
            }
            
            // Загружаем связи
            if (graphData.edges) {
                for (const edgeData of graphData.edges) {
                    this.addEdge(edgeData);
                }
            }
            
            // Подгоняем масштаб
            setTimeout(() => this.fitToScreen(), 100);
            
        } catch (error) {
            console.error('Ошибка загрузки графа:', error);
            throw error;
        }
    }
    
    /**
     * Получение данных графа
     */
    getGraphData() {
        const nodes = Array.from(this.nodes.values()).map(node => ({
            ...node.data,
            ui: {
                x: node.x,
                y: node.y,
                width: node.width,
                height: node.height
            }
        }));
        
        const edges = Array.from(this.edges.values()).map(edge => edge.data);
        
        return {
            nodes,
            edges,
            entry_point: this.getEntryPoint()
        };
    }
    
    /**
     * Добавление ноды
     */
    async addNode(nodeData) {
        const node = {
            id: nodeData.id,
            data: nodeData,
            x: nodeData.ui?.x || 0,
            y: nodeData.ui?.y || 0,
            width: nodeData.ui?.width || this.config.nodeWidth,
            height: nodeData.ui?.height || this.config.nodeHeight,
            element: null
        };
        
        // Создаем HTML элемент ноды
        node.element = await this.createNodeElement(node);
        
        // Добавляем в overlay
        this.overlay.appendChild(node.element);
        
        // Сохраняем в коллекции
        this.nodes.set(node.id, node);
        
        // Обновляем размеры из реального DOM элемента
        setTimeout(() => {
            const rect = node.element.getBoundingClientRect();
            node.width = rect.width / this.zoom;
            node.height = rect.height / this.zoom;
            this.updateNodeEdges(node);
        }, 50);
        
        // Настраиваем обработчики
        this.setupNodeHandlers(node);
        
        return node;
    }
    
    /**
     * Создание HTML элемента ноды (простой кубик)
     */
    async createNodeElement(node) {
        const element = document.createElement('div');
        element.className = `canvas-node`;
        element.dataset.nodeId = node.id;
        element.dataset.nodeType = node.data.type;
        element.style.transform = `translate3d(${node.x}px, ${node.y}px, 0)`;
        
        await this.createSimpleNodeElement(element, node);
        
        return element;
    }
    
    /**
     * Создание редактируемой ноды с формой
     */
    async createEditableNodeElement(element, node) {
        let modelType, modelId;
        
        if (node.data.type === 'agent_node') {
            modelType = 'agent';
            modelId = node.data.params?.agent_id;
        } else if (node.data.type === 'flow_node') {
            modelType = 'flow';
            modelId = node.data.params?.flow_id;
        } else if (node.data.type === 'tool_node') {
            modelType = 'tool';
            modelId = node.data.params?.tool_id;
        }

        if (!modelId) {
            await this.createSimpleNodeElement(element, node);
            return;
        }

        // Сохраняем данные для загрузки формы
        element.dataset.modelType = modelType;
        element.dataset.modelId = modelId;

        // Показываем загрузчик (порты добавятся после загрузки формы)
        element.innerHTML = `
            <div class="node-loading">
                <div class="loader"></div>
                <span>Загрузка...</span>
            </div>
        `;
        
        // Загружаем форму программно
        setTimeout(() => {
            this.loadNodeForm(element, modelType, modelId);
        }, 100);
    }
    
    /**
     * Создание ноды тула
     */
    async createToolNodeElement(element, node) {
        const toolId = node.data.params?.tool_id;
        
        if (!toolId) {
            await this.createSimpleNodeElement(element, node);
            return;
        }
        
        try {
            // Пытаемся загрузить данные тула из БД
            const encodedToolId = encodeURIComponent(toolId);
            const response = await fetch(`/frontend/api/tools/${encodedToolId}`);
            
            if (response.ok) {
                const toolData = await response.json();
                
                // Создаем расширенную карточку тула с информацией (порты добавятся отдельно)
                element.innerHTML = `
                    <div class="tool-node-content">
                        <div class="node-header">
                            <div class="node-icon">
                                <i class="icon-tool"></i>
                            </div>
                            <div class="node-title">${toolData.name}</div>
                        </div>
                        
                        ${toolData.description ? `<div class="node-description">${toolData.description}</div>` : ''}
                        
                        <div class="tool-info">
                            <div class="tool-category">
                                <span class="tag tag-${toolData.category}">${toolData.category}</span>
                            </div>
                            
                            ${toolData.cost > 0 ? `
                                <div class="tool-cost">
                                    <i class="icon-cost"></i>
                                    ${toolData.cost} ₽
                                </div>
                            ` : ''}
                            
                            ${toolData.parameters && toolData.parameters.required ? `
                                <div class="tool-params">
                                    <small>Параметры: ${toolData.parameters.required.join(', ')}</small>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                `;
                
                // Добавляем порты через централизованный метод
                this.addPortsToNodeElement(element, node);
            } else {
                // Если тул не найден в БД, используем простую ноду
                await this.createSimpleNodeElement(element, node);
            }
            
        } catch (error) {
            console.warn('Ошибка загрузки данных тула:', error);
            await this.createSimpleNodeElement(element, node);
        }
    }
    
    /**
     * Создание простой ноды (минималистичный кубик)
     */
    async createSimpleNodeElement(element, node) {
        const nodeType = node.data.type;
        const nodeName = node.data.params?.name || this.getNodeTypeName(nodeType);
        let nodeDesc = node.data.params?.description || this.getNodeTypeDesc(nodeType);
        
        // Обрезаем название до 30 символов
        const displayName = nodeName.length > 30 ? nodeName.substring(0, 27) + '...' : nodeName;
        
        // Обрезаем описание до 25 символов
        if (nodeDesc && nodeDesc.length > 25) {
            nodeDesc = nodeDesc.substring(0, 22) + '...';
        }
        
        const iconClass = this.getNodeIcon(nodeType);
        const iconType = this.getNodeIconType(nodeType);
        
        // Экранируем HTML
        const escapedName = escapeHtml(displayName);
        const escapedDesc = escapeHtml(nodeDesc);
        
        element.innerHTML = `
            <div class="node-simple-content">
                <div class="node-simple-icon ${iconType}">
                    <i class="${iconClass}"></i>
                </div>
                <div class="node-simple-info">
                    <div class="node-simple-title">${escapedName}</div>
                    <div class="node-simple-desc">${escapedDesc}</div>
                </div>
            </div>
        `;
        
        // Добавляем порты через централизованный метод
        this.addPortsToNodeElement(element, node);
    }
    
    /**
     * Загрузка формы для ноды
     */
    async loadNodeForm(element, modelType, modelId) {
        try {
            console.log('🔄 Загружаем форму для ноды:', modelType, modelId);
            
            const url = `/frontend/models/${modelType}/${modelId}?view=form`;
            
            console.log('📡 URL для загрузки формы:', url);
            
            const response = await fetch(url);
            
            console.log('📡 Ответ сервера:', response.status, response.statusText);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const formHtml = await response.text();
            console.log('📄 Получен HTML длиной:', formHtml.length);
            
            element.innerHTML = formHtml;

            // После загрузки формы добавляем порты в зависимости от типа ноды и агента
            const node = this.nodes.get(element.dataset.nodeId);
            if (node) {
                this.addPortsToNodeElement(element, node);
            } else {
                console.warn('⚠️ Нода не найдена при загрузке формы:', element.dataset.nodeId);
            }
            
            // Инициализируем HTMX для новых элементов
            if (typeof htmx !== 'undefined') {
                htmx.process(element);
            }
            
            // Добавляем кнопки (i) для описаний полей
            this.addFieldInfoButtons(element);
            
            // Настраиваем автосохранение для полей
            this.setupAutoSave(element, modelType, modelId);
            
            // Обновляем размеры ноды после загрузки формы (с задержкой для рендеринга)
            setTimeout(() => {
                this.updateNodeSizeFromElement(element);
            }, 50);
            
            console.log('✅ Форма загружена для ноды');
            
        } catch (error) {
            console.error('❌ Ошибка загрузки формы для ноды:', error);
            element.innerHTML = `
                <div class="node-error">
                    <i class="icon-warning"></i>
                    <span>Ошибка загрузки</span>
                    <small>${error.message}</small>
                </div>
            `;
            
            // Добавляем порты даже при ошибке
            const node = this.nodes.get(element.dataset.nodeId);
            if (node) {
                this.addPortsToNodeElement(element, node);
            }
        }
    }
    
    /**
     * Добавление кнопок (i) для описаний полей
     */
    addFieldInfoButtons(element) {
        // Находим все поля с описанием
        const fieldDescriptions = element.querySelectorAll('.field-description');
        
        fieldDescriptions.forEach(description => {
            const field = description.closest('.field');
            if (!field) return;
            
            const label = field.querySelector('.field-label');
            if (!label) return;
            
            // Проверяем, что кнопка еще не добавлена
            if (label.querySelector('.field-info-btn')) return;
            
            // Создаем кнопку (i)
            const infoBtn = document.createElement('button');
            infoBtn.type = 'button';
            infoBtn.className = 'field-info-btn';
            infoBtn.setAttribute('data-toggle', 'tooltip');
            infoBtn.title = description.textContent.trim();
            infoBtn.innerHTML = '<i class="bi bi-info-circle"></i>';
            
            // Добавляем кнопку к label
            label.appendChild(infoBtn);
            
            // Скрываем оригинальное описание
            description.style.display = 'none';
        });
        
        // Также обрабатываем поля, которые не используют base_field.html
        const customLabels = element.querySelectorAll('label:not(.field-label)');
        customLabels.forEach(label => {
            const field = label.closest('.field, div');
            if (!field) return;
            
            // Ищем описание рядом с label
            let description = label.nextElementSibling;
            while (description && !description.classList.contains('field-description') && 
                   !description.textContent.includes('Описание') && 
                   description.tagName !== 'DIV') {
                description = description.nextElementSibling;
            }
            
            if (description && description.classList.contains('field-description')) {
                // Проверяем, что кнопка еще не добавлена
                if (label.querySelector('.field-info-btn')) return;
                
                // Создаем кнопку (i)
                const infoBtn = document.createElement('button');
                infoBtn.type = 'button';
                infoBtn.className = 'field-info-btn';
                infoBtn.setAttribute('data-toggle', 'tooltip');
                infoBtn.title = description.textContent.trim();
                infoBtn.innerHTML = '<i class="bi bi-info-circle"></i>';
                
                // Добавляем кнопку к label
                label.appendChild(infoBtn);
                
                // Скрываем оригинальное описание
                description.style.display = 'none';
            }
        });
    }
    
    /**
     * Настройка автосохранения для полей формы
     */
    setupAutoSave(element, modelType, modelId) {
        // Ищем контейнер с полями (теперь это не form, а div#form-fields)
        const formFields = element.querySelector('#form-fields');
        if (!formFields) {
            console.warn('Не найден #form-fields для автосохранения');
            return;
        }
        
        // Добавляем автосохранение для всех полей
        const inputs = formFields.querySelectorAll('input, textarea, select');
        
        inputs.forEach(input => {
            // Убираем существующие HTMX атрибуты если есть
            input.removeAttribute('hx-put');
            input.removeAttribute('hx-trigger');
            
            // Добавляем автосохранение
            input.setAttribute('hx-put', `/frontend/models/${modelType}/${modelId}`);
            input.setAttribute('hx-ext', 'json-enc');
            input.setAttribute('hx-trigger', 'change delay:500ms');
            input.setAttribute('hx-swap', 'none');
            input.setAttribute('hx-on::after-request', 
                `if(event.detail.successful) { 
                    console.log('✅ Поле сохранено:', '${input.name}'); 
                } else { 
                    console.error('❌ Ошибка сохранения поля:', '${input.name}'); 
                }`
            );
        });
        
        // Инициализируем HTMX для обновленных элементов
        if (typeof htmx !== 'undefined') {
            htmx.process(formFields);
        }
    }
    
    /**
     * Добавление портов к ноде
     */
    /**
     * Получение центральной позиции канваса
     */
    getCenterPosition() {
        const canvasContainer = this.element.querySelector('#canvasContainer');
        const rect = canvasContainer.getBoundingClientRect();
        
        // Центр видимой области с учетом трансформации
        const centerX = (rect.width / 2 - this.panX) / this.zoom;
        const centerY = (rect.height / 2 - this.panY) / this.zoom;
        
        return { x: centerX, y: centerY };
    }
    
    /**
     * Получение иконки по типу ноды
     */
    getNodeIcon(nodeType) {
        const icons = {
            'flow_node': 'bi bi-diagram-3',
            'agent_node': 'bi bi-robot',
            'tool_node': 'bi bi-tools',
            'function_node': 'bi bi-code-square',
            'message_node': 'bi bi-chat-dots',
            'router_node': 'bi bi-lightning'
        };
        return icons[nodeType] || 'bi bi-square';
    }
    
    /**
     * Получение типа иконки (для CSS класса)
     */
    getNodeIconType(nodeType) {
        const types = {
            'flow_node': 'flow',
            'agent_node': 'agent',
            'tool_node': 'tool',
            'function_node': 'function',
            'message_node': 'message',
            'router_node': 'router'
        };
        return types[nodeType] || 'default';
    }
    
    /**
     * Получение названия типа ноды
     */
    getNodeTypeName(nodeType) {
        const names = {
            'flow_node': 'Flow',
            'agent_node': 'Agent',
            'tool_node': 'Tool',
            'function_node': 'Function',
            'message_node': 'Message',
            'router_node': 'Router'
        };
        return names[nodeType] || 'Node';
    }
    
    /**
     * Получение описания типа ноды
     */
    getNodeTypeDesc(nodeType) {
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
     * Настройка обработчиков для ноды
     */
    setupNodeHandlers(node) {
        const element = node.element;
        
        // Drag & Drop ноды
        element.addEventListener('mousedown', (e) => this.handleNodeMouseDown(e, node));
        
        // Клик по ноде (только левая кнопка)
        element.addEventListener('mousedown', (e) => {
            if (e.button === 0) {
                this.handleNodeClick(e, node);
            }
        });
        
        // Порты для соединений
        const ports = element.querySelectorAll('.port');
        ports.forEach(port => {
            port.addEventListener('mousedown', (e) => this.handlePortMouseDown(e, node, port));
        });
        
        // Действия ноды
        const editBtn = element.querySelector('[data-action="edit"]');
        if (editBtn) {
            editBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.editNode(node);
            });
        }
    }
    
    /**
     * Добавление связи
     */
    addEdge(edgeData) {
        const edge = {
            id: edgeData.id,
            data: edgeData,
            source: edgeData.source,
            target: edgeData.target,
            element: null
        };
        
        // Создаем SVG элемент связи
        edge.element = this.createEdgeElement(edge);
        
        // Добавляем в SVG
        this.edgesGroup.appendChild(edge.element);
        
        // Сохраняем в коллекции
        this.edges.set(edge.id, edge);
        
        // Обновляем позицию связи
        this.updateEdgePosition(edge);
        
        return edge;
    }
    
    /**
     * Создание SVG элемента связи
     */
    createEdgeElement(edge) {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.classList.add('edge');
        path.dataset.edgeId = edge.id;
        path.dataset.source = edge.source;
        path.dataset.target = edge.target;
        path.dataset.type = edge.type || 'default';
        
        // Обработчики для связи
        path.addEventListener('click', (e) => this.handleEdgeClick(e, edge));
        
        return path;
    }
    
    /**
     * Обновление позиции связи
     */
    updateEdgePosition(edge) {
        const sourceNode = this.nodes.get(edge.source);
        const targetNode = this.nodes.get(edge.target);
        
        if (!sourceNode || !targetNode) {
            console.warn('Не найдены ноды для связи:', edge.source, edge.target);
            return;
        }
        
        // Вычисляем точки подключения
        const sourcePoint = this.getNodeConnectionPoint(sourceNode, 'output');
        const targetPoint = this.getNodeConnectionPoint(targetNode, 'input');
        
        // Создаем кривую Безье
        const path = this.createBezierPath(sourcePoint, targetPoint);
        
        edge.element.setAttribute('d', path);
    }
    
    /**
     * Обновление размеров ноды из DOM элемента
     */
    updateNodeSizeFromElement(element) {
        const nodeId = element.dataset.nodeId;
        const node = this.nodes.get(nodeId);
        
        if (!node) return;
        
        // Получаем реальные размеры элемента
        const rect = element.getBoundingClientRect();
        
        // Обновляем размеры ноды с учетом зума
        node.width = rect.width / this.zoom;
        node.height = rect.height / this.zoom;
        
        // Обновляем связи этой ноды
        this.updateNodeEdges(node);
    }
    
    /**
     * Получение точки подключения ноды
     */
    getNodeConnectionPoint(node, type) {
        const centerX = node.x + node.width / 2;
        const centerY = node.y + node.height / 2;
        
        if (type === 'output') {
            // Выходной порт справа
            return {
                x: node.x + node.width,
                y: centerY
            };
        } else {
            // Входной порт слева
            return {
                x: node.x,
                y: centerY
            };
        }
    }
    
    /**
     * Создание кривой Безье для связи
     */
    createBezierPath(start, end) {
        const dx = end.x - start.x;
        const controlOffset = Math.abs(dx) * 0.5;
        
        const cp1x = start.x + controlOffset;
        const cp1y = start.y;
        const cp2x = end.x - controlOffset;
        const cp2y = end.y;
        
        return `M ${start.x} ${start.y} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${end.x} ${end.y}`;
    }
    
    /**
     * Обработка колеса мыши (зум или прокрутка карточки)
     */
    handleWheel(e) {
        // Проверяем, находится ли курсор над любой нодой
        const targetNode = e.target.closest('.canvas-node');
        
        if (targetNode) {
            // Если курсор над карточкой, блокируем зум канваса
            e.preventDefault();
            
            // Если карточка выделена, пытаемся прокрутить её содержимое
            if (targetNode.classList.contains('selected')) {
                const scrollableArea = targetNode.querySelector('.card-body');
                
                if (scrollableArea) {
                    // Прокручиваем содержимое карточки
                    scrollableArea.scrollTop += e.deltaY;
                }
            }
            
            // В любом случае не делаем зум, если курсор над карточкой
            return;
        }
        
        // Если курсор НЕ над карточкой, делаем зум канваса
        e.preventDefault();
        
        const canvasContainer = this.element.querySelector('#canvasContainer');
        const rect = canvasContainer.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        // Адаптивный шаг масштабирования в зависимости от скорости прокрутки
        const scrollSpeed = Math.abs(e.deltaY);
        let adaptiveStep = this.config.zoomStep;
        
        // Если прокручивают быстро - увеличиваем шаг, если медленно - уменьшаем
        if (scrollSpeed > 100) {
            adaptiveStep = this.config.zoomStep * 2; // Быстрая прокрутка (4%)
        } else if (scrollSpeed < 30) {
            adaptiveStep = this.config.zoomStep * 0.5; // Очень медленная прокрутка (1%)
        }
        
        const delta = e.deltaY > 0 ? -adaptiveStep : adaptiveStep;
        const newZoom = Math.max(this.config.minZoom, Math.min(this.config.maxZoom, this.zoom + delta));
        
        if (newZoom !== this.zoom) {
            // Зум к точке курсора
            const zoomRatio = newZoom / this.zoom;
            this.panX = mouseX - (mouseX - this.panX) * zoomRatio;
            this.panY = mouseY - (mouseY - this.panY) * zoomRatio;
            this.zoom = newZoom;
            
            this.updateTransform();
        }
    }
    
    /**
     * Обработка нажатия мыши
     */
    handleMouseDown(e) {
        // Проверяем, что клик не по ноде или порту
        const isOnNode = e.target.closest('.canvas-node');
        const isOnPort = e.target.closest('.port');
        const isOnEdge = e.target.closest('.edge');
        
        if (!isOnNode && !isOnPort && !isOnEdge) {
            // Начинаем панорамирование только если клик по пустому месту
            this.startPanning(e);
        }
    }
    
    /**
     * Обработка движения мыши
     */
    handleMouseMove(e) {
        if (this.isPanning) {
            this.updatePanning(e);
        } else if (this.isDragging && this.draggedNode) {
            this.updateNodeDrag(e);
        } else if (this.isConnecting && this.tempEdge) {
            this.updateTempEdge(e);
        }
    }
    
    /**
     * Обработка отпускания мыши
     */
    handleMouseUp(e) {
        if (this.isPanning) {
            this.stopPanning();
        } else if (this.isDragging) {
            this.stopNodeDrag();
        } else if (this.isConnecting) {
            this.finishConnection(e);
        }
    }
    
    /**
     * Обработка покидания мыши
     */
    handleMouseLeave(e) {
        this.handleMouseUp(e);
    }
    
    /**
     * Начало панорамирования
     */
    startPanning(e) {
        this.isPanning = true;
        this.lastPanX = e.clientX;
        this.lastPanY = e.clientY;
        
        const canvasContainer = this.element.querySelector('#canvasContainer');
        canvasContainer.classList.add('panning');
    }
    
    /**
     * Обновление панорамирования
     */
    updatePanning(e) {
        const dx = e.clientX - this.lastPanX;
        const dy = e.clientY - this.lastPanY;
        
        this.panX += dx;
        this.panY += dy;
        
        this.lastPanX = e.clientX;
        this.lastPanY = e.clientY;
        
        this.updateTransform();
    }
    
    /**
     * Остановка панорамирования
     */
    stopPanning() {
        this.isPanning = false;
        
        const canvasContainer = this.element.querySelector('#canvasContainer');
        canvasContainer.classList.remove('panning');
    }
    
    /**
     * Обработка нажатия на ноду
     */
    handleNodeMouseDown(e, node) {
        // Игнорируем drag если клик по элементам форм
        const formElements = ['input', 'textarea', 'select', 'button'];
        if (formElements.includes(e.target.tagName.toLowerCase())) {
            return;
        }
        
        // Игнорируем drag если клик по элементам с классами форм
        if (e.target.closest('input, textarea, select, button, .field-input, .form-control')) {
            return;
        }
        
        e.stopPropagation();
        
        // Запоминаем начальную позицию для определения клика vs drag
        this.mouseDownStartX = e.clientX;
        this.mouseDownStartY = e.clientY;
        this.mouseDownTime = Date.now();
        
        this.isDragging = true;
        this.draggedNode = node;
        this.dragStartX = e.clientX;
        this.dragStartY = e.clientY;
        this.nodeStartX = node.x;
        this.nodeStartY = node.y;
        
        node.element.classList.add('dragging');
        
        // Добавляем класс для оптимизации
        const canvasContainer = this.element.querySelector('#canvasContainer');
        canvasContainer.classList.add('dragging-node');
    }
    
    /**
     * Обновление перетаскивания ноды
     */
    updateNodeDrag(e) {
        if (!this.draggedNode) return;
        
        const dx = (e.clientX - this.dragStartX) / this.zoom;
        const dy = (e.clientY - this.dragStartY) / this.zoom;
        
        this.draggedNode.x = this.nodeStartX + dx;
        this.draggedNode.y = this.nodeStartY + dy;
        
        // Привязка к сетке
        if (e.shiftKey) {
            this.draggedNode.x = Math.round(this.draggedNode.x / this.config.gridSize) * this.config.gridSize;
            this.draggedNode.y = Math.round(this.draggedNode.y / this.config.gridSize) * this.config.gridSize;
        }
        
        // Обновляем позицию ноды немедленно
        this.updateNodePosition(this.draggedNode);
        
        // Обновляем связи с throttling для производительности
        this.throttledUpdateNodeEdges(this.draggedNode);
    }
    
    /**
     * Остановка перетаскивания ноды
     */
    stopNodeDrag() {
        if (this.draggedNode) {
            // Определяем был ли это клик или drag
            const timeDiff = Date.now() - this.mouseDownTime;
            const distanceMoved = Math.sqrt(
                Math.pow(this.dragStartX - this.mouseDownStartX, 2) +
                Math.pow(this.dragStartY - this.mouseDownStartY, 2)
            );
            
            const wasClick = timeDiff < 200 && distanceMoved < 5;
            
            this.draggedNode.element.classList.remove('dragging');
            
            // Убираем класс оптимизации
            const canvasContainer = this.element.querySelector('#canvasContainer');
            canvasContainer.classList.remove('dragging-node');
            
            // Финальное обновление связей
            this.updateNodeEdges(this.draggedNode);
            
            // Очищаем throttle
            if (this.edgeUpdateThrottle) {
                clearTimeout(this.edgeUpdateThrottle);
                this.edgeUpdateThrottle = null;
            }
            
            // Если это был клик - открываем properties panel
            if (wasClick && this.builder.propertiesPanel) {
                console.log('👆 Клик на ноду, открываем properties panel');
                this.builder.propertiesPanel.show(this.draggedNode);
            }
            
            this.draggedNode = null;
        }
        this.isDragging = false;
    }
    
    /**
     * Обновление позиции ноды
     */
    updateNodePosition(node) {
        // Используем translate3d для аппаратного ускорения
        node.element.style.transform = `translate3d(${node.x}px, ${node.y}px, 0)`;
    }
    
    /**
     * Обновление связей ноды
     */
    updateNodeEdges(node) {
        // Обновляем все связи, связанные с этой нодой
        this.edges.forEach(edge => {
            if (edge.source === node.id || edge.target === node.id) {
                this.updateEdgePosition(edge);
            }
        });
    }
    
    /**
     * Throttled обновление связей ноды для производительности
     */
    throttledUpdateNodeEdges(node) {
        // Отменяем предыдущий запрос если есть
        if (this.edgeUpdateFrame) {
            cancelAnimationFrame(this.edgeUpdateFrame);
        }
        
        // Используем requestAnimationFrame для плавности (синхронно с экраном)
        this.edgeUpdateFrame = requestAnimationFrame(() => {
            this.updateNodeEdges(node);
            this.edgeUpdateFrame = null;
        });
    }
    
    /**
     * Обработка клика по ноде
     */
    handleNodeClick(e, node) {
        e.stopPropagation();
        
        // Игнорируем правую кнопку мыши
        if (e.button === 2) {
            return;
        }
        
        // Выделение ноды
        if (e.ctrlKey || e.metaKey) {
            this.toggleNodeSelection(node);
        } else {
            this.selectNode(node);
        }
    }
    
    /**
     * Выделение ноды
     */
    selectNode(node) {
        // Снимаем выделение с других нод
        this.nodes.forEach(n => {
            n.element.classList.remove('selected');
        });
        
        // Выделяем текущую ноду
        node.element.classList.add('selected');
        this.builder.selectedNodes.clear();
        this.builder.selectedNodes.add(node.id);
    }
    
    /**
     * Переключение выделения ноды
     */
    toggleNodeSelection(node) {
        if (node.element.classList.contains('selected')) {
            node.element.classList.remove('selected');
            this.builder.selectedNodes.delete(node.id);
        } else {
            node.element.classList.add('selected');
            this.builder.selectedNodes.add(node.id);
        }
    }
    
    /**
     * Обработка нажатия на порт
     */
    handlePortMouseDown(e, node, port) {
        e.stopPropagation();
        
        this.isConnecting = true;
        this.connectionStart = { node, port };
        
        // Создаем временную связь
        this.tempEdge = this.createTempEdge();
        this.edgesGroup.appendChild(this.tempEdge);
        
        port.classList.add('connecting');
    }
    
    /**
     * Создание временной связи
     */
    createTempEdge() {
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.classList.add('temp-edge');
        return path;
    }
    
    /**
     * Обновление временной связи
     */
    updateTempEdge(e) {
        if (!this.tempEdge || !this.connectionStart) return;
        
        const rect = this.svg.getBoundingClientRect();
        const mouseX = (e.clientX - rect.left - this.panX) / this.zoom;
        const mouseY = (e.clientY - rect.top - this.panY) / this.zoom;
        
        const startPoint = this.getNodeConnectionPoint(this.connectionStart.node, 'output');
        const endPoint = { x: mouseX, y: mouseY };
        
        const path = this.createBezierPath(startPoint, endPoint);
        this.tempEdge.setAttribute('d', path);
    }
    
    /**
     * Завершение соединения
     */
    finishConnection(e) {
        console.log('🎯 finishConnection вызван');
        if (!this.isConnecting || !this.connectionStart) {
            console.log('❌ Нет активного соединения');
            return;
        }

        // Ищем целевой порт
        const targetPort = e.target.closest('.port');
        const targetNode = e.target.closest('.canvas-node');

        console.log('🎯 targetPort:', targetPort, 'targetNode:', targetNode);

        if (targetPort && targetNode && targetPort.dataset.portType === 'input') {
            const targetNodeId = targetNode.dataset.nodeId;
            const sourceNodeId = this.connectionStart.node.id;

            console.log('🔗 Попытка соединения:', sourceNodeId, '->', targetNodeId);

            if (targetNodeId !== sourceNodeId) {
                // Валидируем подключение
                console.log('🔍 Валидируем подключение...');
                if (this.validateConnection(sourceNodeId, targetNodeId)) {
                    console.log('✅ Валидация прошла, создаем соединение');
                    this.createConnection(sourceNodeId, targetNodeId);
                } else {
                    console.log('❌ Валидация не прошла');
                    // Показываем ошибку валидации
                    this.builder.showNotification('Недопустимое подключение', 'error');
                }
            } else {
                console.log('⚠️ Попытка соединить нод с самим собой');
            }
        } else {
            console.log('❌ Целевой порт не найден или не input');
        }

        // Очищаем временные элементы
        this.cleanupConnection();
    }
    
    /**
     * Валидация подключения между нодами
     */
    validateConnection(sourceId, targetId) {
        console.log(`🚀 validateConnection вызвана: ${sourceId} -> ${targetId}`);

        const sourceNode = this.nodes.get(sourceId);
        const targetNode = this.nodes.get(targetId);

        if (!sourceNode || !targetNode) {
            console.log('❌ Один из нодов не найден');
            return false;
        }

        const sourceType = sourceNode.data.type;
        const targetType = targetNode.data.type;

        console.log(`🔍 Валидация: ${sourceType} -> ${targetType}`);

        // Получаем тип entry_point агента из builder
        const entryPointAgentType = this.builder.entryPointAgentType;
        const targetAgentId = targetNode.data.params?.agent_id;
        const entryPointAgentId = this.builder.currentFlow?.entry_point_agent;

        // ЕДИНАЯ КАРТА ПРАВИЛ СОЕДИНЕНИЙ
        const CONNECTION_RULES = {
            // ReAct агент правила
            react: {
                // Агент может соединяться с множеством tools и агентов
                agent_node: {
                    can_connect_to: ['tool_node', 'agent_node'],
                    max_incoming: -1, // неограничено
                    max_outgoing: 1   // выходной порт может иметь только 1 соединение
                },
                // Tool не имеет выходного порта (конечная нода)
                tool_node: {
                    can_connect_to: [], // tool не может быть источником
                    max_incoming: 1,
                    max_outgoing: 0
                }
            },

            // StateGraph агент правила
            stategraph: {
                // StateGraph агент может быть соединен только с 1 нодой любого типа
                agent_node: {
                    can_connect_to: ['tool_node', 'agent_node', 'function_node', 'router_node', 'message_node'],
                    max_incoming: entryPointAgentId && targetAgentId === entryPointAgentId ? 1 : -1,
                    max_outgoing: 1
                },
                // Все ноды могут иметь выходной порт, но выходной порт может иметь только 1 соединение
                tool_node: {
                    can_connect_to: ['tool_node', 'agent_node', 'function_node', 'router_node', 'message_node'],
                    max_incoming: 1,
                    max_outgoing: 1
                },
                function_node: {
                    can_connect_to: ['tool_node', 'agent_node', 'function_node', 'router_node', 'message_node'],
                    max_incoming: 1,
                    max_outgoing: 1
                },
                router_node: {
                    can_connect_to: ['tool_node', 'agent_node', 'function_node', 'router_node', 'message_node'],
                    max_incoming: 2, // роутер может иметь множество входящих соединений
                    max_outgoing: 1
                },
                message_node: {
                    can_connect_to: ['tool_node', 'agent_node', 'function_node', 'router_node', 'message_node'],
                    max_incoming: 1,
                    max_outgoing: 1
                }
            },

            // Общие правила для всех типов агентов
            common: {
                flow_node: {
                    can_connect_to: ['tool_node', 'agent_node', 'function_node', 'router_node', 'message_node'],
                    max_incoming: 0, // flow не может быть целью
                    max_outgoing: 1  // flow может иметь только 1 entry point
                }
            }
        };

        // Определяем правила для текущего типа агента
        const agentRules = CONNECTION_RULES[entryPointAgentType] || {};
        const sourceRules = agentRules[sourceType] || CONNECTION_RULES.common[sourceType];
        const targetRules = agentRules[targetType] || CONNECTION_RULES.common[targetType];

        // Проверяем базовые правила
        if (sourceType === 'flow_node') {
            // Flow может подключаться к любой ноде кроме другого Flow
            if (targetType === 'flow_node') {
                console.warn(`Flow не может подключаться к другому Flow`);
                return false;
            }

            // У Flow может быть только одно подключение (entry point)
            const existingConnections = Array.from(this.edges.values())
                .filter(edge => edge.data.source === sourceId);

            if (existingConnections.length > 0) {
                console.warn('У Flow уже есть подключение (entry point)');
                this.builder.showNotification('У Flow может быть только один entry point', 'warning');
                return false;
            }

            return true;
        }

        if (sourceId === targetId) {
            console.warn('Нельзя подключить ноду к самой себе');
            return false;
        }

        if (targetType === 'flow_node') {
            console.warn(`${sourceType} не может подключаться к Flow`);
            return false;
        }

        // Проверяем правила для source типа
        if (sourceRules) {
            // Проверяем, может ли source подключаться к target типу
            if (!sourceRules.can_connect_to.includes(targetType)) {
                console.warn(`${sourceType} не может подключаться к ${targetType}`);
                return false;
            }

            // Проверяем исходящие соединения source
            if (sourceRules.max_outgoing >= 0) {
                const outgoingConnections = Array.from(this.edges.values())
                    .filter(edge => edge.data.source === sourceId);

                if (outgoingConnections.length >= sourceRules.max_outgoing) {
                    console.warn(`${sourceType} может иметь максимум ${sourceRules.max_outgoing} исходящих соединений`);
                    this.builder.showNotification(`${sourceType} может иметь максимум ${sourceRules.max_outgoing} исходящих соединений`, 'warning');
                    return false;
                }
            }
        }

        // Проверяем правила для target типа
        if (targetRules) {
            // Проверяем входящие соединения target
            if (targetRules.max_incoming >= 0) {
                const incomingConnections = Array.from(this.edges.values())
                    .filter(edge => edge.data.target === targetId);

                if (incomingConnections.length >= targetRules.max_incoming) {
                    console.warn(`${targetType} может иметь максимум ${targetRules.max_incoming} входящих соединений`);
                    this.builder.showNotification(`${targetType} может иметь максимум ${targetRules.max_incoming} входящих соединений`, 'warning');
                    return false;
                }
            }
        }

        console.log('✅ Соединение разрешено по правилам');
        return true;
    }
    
    /**
     * Добавление портов к элементу ноды
     */
    addPortsToNodeElement(element, node) {
        const nodeType = node.data.type;
        const agentType = this.builder.entryPointAgentType;

        console.log('🔌 Добавляем порты к ноде:', node.id, 'тип ноды:', nodeType, 'тип агента:', agentType);

        // Удаляем старые порты если есть
        const existingPorts = element.querySelector('.node-ports');
        if (existingPorts) {
            console.log('🗑️ Удаляем существующие порты');
            existingPorts.remove();
        }

        let portsHtml = '';

        if (nodeType === 'flow_node') {
            portsHtml = `
                <div class="node-ports">
                    <div class="output-ports">
                        <div class="port output-port" data-port-type="output" data-port-id="output">
                            <div class="port-dot"></div>
                        </div>
                    </div>
                </div>
            `;
        } else if (nodeType === 'tool_node') {
            // Для tool_node: если агент ReAct - только входной порт, иначе оба
            // По умолчанию (если тип агента неизвестен) - создаем оба порта
            if (agentType === 'react') {
                console.log('🔧 Tool node для ReAct агента - только входной порт');
                portsHtml = `
                    <div class="node-ports">
                        <div class="input-ports">
                            <div class="port input-port" data-port-type="input" data-port-id="input">
                                <div class="port-dot"></div>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                console.log('🔧 Tool node для StateGraph агента или тип неизвестен - оба порта');
                portsHtml = `
                    <div class="node-ports">
                        <div class="input-ports">
                            <div class="port input-port" data-port-type="input" data-port-id="input">
                                <div class="port-dot"></div>
                            </div>
                        </div>
                        <div class="output-ports">
                            <div class="port output-port" data-port-type="output" data-port-id="output">
                                <div class="port-dot"></div>
                            </div>
                        </div>
                    </div>
                `;
            }
        } else {
            // Для agent, function, router, message - оба порта
            portsHtml = `
                <div class="node-ports">
                    <div class="input-ports">
                        <div class="port input-port" data-port-type="input" data-port-id="input">
                            <div class="port-dot"></div>
                        </div>
                    </div>
                    <div class="output-ports">
                        <div class="port output-port" data-port-type="output" data-port-id="output">
                            <div class="port-dot"></div>
                        </div>
                    </div>
                </div>
            `;
        }

        if (!portsHtml) {
            console.error('❌ Не удалось создать HTML для портов, тип ноды:', nodeType);
            return;
        }

        console.log('📝 Добавляем порты, HTML:', portsHtml.substring(0, 100) + '...');

        // Добавляем порты в конец элемента
        element.insertAdjacentHTML('beforeend', portsHtml);

        // Проверяем, что порты добавились
        const addedPorts = element.querySelector('.node-ports');
        if (addedPorts) {
            const inputPorts = addedPorts.querySelectorAll('.input-port');
            const outputPorts = addedPorts.querySelectorAll('.output-port');
            console.log('✅ Порты добавлены:', {
                input: inputPorts.length,
                output: outputPorts.length
            });
            
            // Настраиваем обработчики только для портов (не для всей ноды)
            // Обработчики для самой ноды устанавливаются в addNode
            const ports = addedPorts.querySelectorAll('.port');
            ports.forEach(port => {
                port.addEventListener('mousedown', (e) => this.handlePortMouseDown(e, node, port));
            });
        } else {
            console.error('❌ Порты НЕ добавились к элементу!');
        }
    }

    /**
     * Обновление портов ноды при изменении типа агента
     */
    updateNodePorts(node, agentType) {
        console.log('🔧 updateNodePorts для ноды:', node.id, 'тип агента:', agentType, 'тип ноды:', node.data.type);

        if (node.data.type !== 'tool_node') {
            return; // Пока только для tool_node
        }

        const portsContainer = node.element.querySelector('.node-ports');
        if (!portsContainer) {
            console.warn('⚠️ Контейнер портов не найден для ноды:', node.id);
            return;
        }

        // Определяем, какие порты должны быть
        const shouldHaveOutputPort = agentType !== 'react';
        const hasOutputPort = portsContainer.querySelector('.output-ports') !== null;

        console.log('🔍 Проверка портов:', { shouldHaveOutputPort, hasOutputPort });

        // Если порты уже правильные, ничего не делаем
        if (shouldHaveOutputPort === hasOutputPort) {
            console.log('✅ Порты уже правильные, пропускаем обновление');
            return;
        }

        console.log('🔄 Порты нужно обновить, пересоздаем...');

        // Очищаем старые порты
        portsContainer.innerHTML = '';

        // Создаем новые порты
        let newPortsHtml = '';

        if (agentType === 'react') {
            // В ReAct tool - конечная нода, только входной порт
            console.log('🔧 Создаем порты для ReAct: только входной');
            newPortsHtml = `
                <div class="input-ports">
                    <div class="port input-port" data-port-type="input" data-port-id="input">
                        <div class="port-dot"></div>
                    </div>
                </div>
            `;
        } else if (agentType === 'stategraph') {
            // В StateGraph tool может быть промежуточной нодой, оба порта
            console.log('🔧 Создаем порты для StateGraph: оба порта');
            newPortsHtml = `
                <div class="input-ports">
                    <div class="port input-port" data-port-type="input" data-port-id="input">
                        <div class="port-dot"></div>
                    </div>
                </div>
                <div class="output-ports">
                    <div class="port output-port" data-port-type="output" data-port-id="output">
                        <div class="port-dot"></div>
                    </div>
                </div>
            `;
        } else {
            // По умолчанию оба порта (на случай, если тип агента не определен)
            console.log('🔧 Создаем порты по умолчанию (agentType =', agentType, '): оба порта');
            newPortsHtml = `
                <div class="input-ports">
                    <div class="port input-port" data-port-type="input" data-port-id="input">
                        <div class="port-dot"></div>
                    </div>
                </div>
                <div class="output-ports">
                    <div class="port output-port" data-port-type="output" data-port-id="output">
                        <div class="port-dot"></div>
                    </div>
                </div>
            `;
        }

        portsContainer.innerHTML = newPortsHtml;

        // Перепривязываем обработчики событий к новым портам
        this.setupNodeHandlers(node);

        console.log('✅ Порты ноды обновлены:', node.id);
    }

    /**
     * Создание соединения
     */
    createConnection(sourceId, targetId) {
        console.log('🔗 createConnection вызван:', sourceId, '->', targetId);
        const edgeId = `${sourceId}-${targetId}`;

        // Проверяем, что связь не существует
        if (this.edges.has(edgeId)) {
            console.log('⚠️ Связь уже существует:', edgeId);
            return;
        }

        const edgeData = {
            id: edgeId,
            source: sourceId,
            target: targetId,
            type: 'default'
        };

        this.addEdge(edgeData);
        console.log('✅ Связь создана:', edgeId);

        // Проверяем, нужно ли обновить entry_point_agent
        console.log('🔄 Вызываем updateFlowEntryPointIfNeeded');
        this.updateFlowEntryPointIfNeeded(sourceId, targetId);
    }
    
    /**
     * Обновление entry_point_agent при создании связи flow -> agent
     */
    updateFlowEntryPointIfNeeded(sourceId, targetId) {
        console.log('🎯 updateFlowEntryPointIfNeeded вызван:', sourceId, '->', targetId);

        const sourceNode = this.nodes.get(sourceId);
        const targetNode = this.nodes.get(targetId);

        console.log('📦 sourceNode:', sourceNode);
        console.log('📦 targetNode:', targetNode);

        if (!sourceNode || !targetNode) {
            console.log('❌ Один из нодов не найден');
            return;
        }

        console.log('🏷️ sourceNode.type:', sourceNode.type, 'targetNode.type:', targetNode.type);
        console.log('🏷️ sourceNode.data:', sourceNode.data, 'targetNode.data:', targetNode.data);

        // Проверяем типы нодов (может быть в data или напрямую)
        const sourceType = sourceNode.type || sourceNode.data?.type;
        const targetType = targetNode.type || targetNode.data?.type;

        console.log('🏷️ sourceType:', sourceType, 'targetType:', targetType);

        // Проверяем, что source - flow_node, а target - agent_node
        if (sourceType === 'flow_node' && targetType === 'agent_node') {
            const flowId = sourceNode.params?.flow_id || sourceNode.data?.params?.flow_id;
            const agentId = targetNode.params?.agent_id || targetNode.data?.params?.agent_id;

            console.log('🔍 flowId:', flowId, 'agentId:', agentId);

            if (flowId && agentId) {
                console.log('🔄 Обновляю entry_point_agent для flow:', flowId, 'на agent:', agentId);
                this.updateFlowEntryPointAgent(flowId, agentId);
            } else {
                console.log('❌ flowId или agentId пустые');
            }
        } else {
            console.log('❌ Типы нодов не подходят для обновления entry_point_agent');
        }
    }

    /**
     * Сброс entry_point_agent при удалении связи flow -> agent
     */
    resetFlowEntryPointIfNeeded(sourceId, targetId) {
        console.log('🎯 resetFlowEntryPointIfNeeded вызван:', sourceId, '->', targetId);

        const sourceNode = this.nodes.get(sourceId);
        const targetNode = this.nodes.get(targetId);

        if (!sourceNode || !targetNode) return;

        // Проверяем типы нодов (может быть в data или напрямую)
        const sourceType = sourceNode.type || sourceNode.data?.type;
        const targetType = targetNode.type || targetNode.data?.type;

        console.log('🏷️ reset - sourceType:', sourceType, 'targetType:', targetType);

        // Проверяем, что удаляется связь flow_node -> agent_node
        if (sourceType === 'flow_node' && targetType === 'agent_node') {
            const flowId = sourceNode.params?.flow_id || sourceNode.data?.params?.flow_id;
            const agentId = targetNode.params?.agent_id || targetNode.data?.params?.agent_id;

            if (flowId && agentId) {
                console.log('🔄 Сбрасываю entry_point_agent для flow:', flowId, '(был agent:', agentId, ')');
                this.resetFlowEntryPointAgent(flowId, agentId);
            }
        }
    }

    /**
     * Обновление entry_point_agent во флоу
     */
    async updateFlowEntryPointAgent(flowId, agentId) {
        try {
            // Получаем текущий флоу
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
            if (!response.ok) {
                throw new Error('Не удалось получить данные флоу');
            }

            const flowData = await response.json();

            // Обновляем entry_point_agent
            flowData.entry_point_agent = agentId;

            // Сохраняем обновленный флоу
            const updateResponse = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(flowData)
            });

            if (!updateResponse.ok) {
                throw new Error('Не удалось обновить entry_point_agent');
            }

            // Обновляем currentFlow в builder
            this.builder.currentFlow = flowData;

            // Обновляем тип entry_point агента и фильтруем палитру
            await this.builder.updateEntryPointAgentType();

            console.log('✅ entry_point_agent успешно обновлен:', agentId);

        } catch (error) {
            console.error('❌ Ошибка обновления entry_point_agent:', error);
            this.builder.showNotification('Ошибка обновления entry_point_agent: ' + error.message, 'error');
        }
    }

    /**
     * Сброс entry_point_agent во флоу
     */
    async resetFlowEntryPointAgent(flowId, removedAgentId) {
        try {
            // Получаем текущий флоу
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`);
            if (!response.ok) {
                throw new Error('Не удалось получить данные флоу');
            }

            const flowData = await response.json();

            // Проверяем, что удаляемый агент действительно был entry_point_agent
            if (flowData.entry_point_agent === removedAgentId) {
                // Сбрасываем entry_point_agent
                flowData.entry_point_agent = null;

                // Сохраняем обновленный флоу
                const updateResponse = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(flowData)
                });

                if (!updateResponse.ok) {
                    throw new Error('Не удалось сбросить entry_point_agent');
                }

                // Обновляем currentFlow в builder
                this.builder.currentFlow = flowData;

                // Обновляем тип entry_point агента и фильтруем палитру
                await this.builder.updateEntryPointAgentType();

                console.log('✅ entry_point_agent успешно сброшен');
            }

        } catch (error) {
            console.error('❌ Ошибка сброса entry_point_agent:', error);
            this.builder.showNotification('Ошибка сброса entry_point_agent: ' + error.message, 'error');
        }
    }

    /**
     * Очистка соединения
     */
    cleanupConnection() {
        if (this.tempEdge) {
            this.tempEdge.remove();
            this.tempEdge = null;
        }
        
        if (this.connectionStart) {
            this.connectionStart.port.classList.remove('connecting');
            this.connectionStart = null;
        }
        
        this.isConnecting = false;
    }
    
    /**
     * Обработка клика по связи
     */
    handleEdgeClick(e, edge) {
        e.stopPropagation();
        
        // Выделение связи
        this.selectEdge(edge);
    }
    
    /**
     * Выделение связи
     */
    selectEdge(edge) {
        // Снимаем выделение с других связей
        this.edges.forEach(e => {
            e.element.classList.remove('selected');
        });
        
        // Выделяем текущую связь
        edge.element.classList.add('selected');
        this.builder.selectedEdges.clear();
        this.builder.selectedEdges.add(edge.id);
    }
    
    /**
     * Получение дочерних нод (зависимых элементов)
     */
    getChildNodes(nodeId) {
        const children = [];
        this.edges.forEach(edge => {
            if (edge.data.source === nodeId) {
                children.push(edge.data.target);
            }
        });
        return children;
    }
    
    /**
     * Удаление ноды с каскадным удалением зависимых элементов
     */
    removeNode(nodeId, cascadeDelete = true) {
        const node = this.nodes.get(nodeId);
        if (!node) return;
        
        // Если каскадное удаление включено, удаляем все зависимые элементы справа
        if (cascadeDelete) {
            const childNodes = this.getChildNodes(nodeId);
            childNodes.forEach(childId => {
                // Рекурсивно удаляем дочерние ноды
                this.removeNode(childId, true);
            });
        }
        
        // Удаляем все связи с этой нодой
        const edgesToRemove = [];
        this.edges.forEach(edge => {
            if (edge.data.source === nodeId || edge.data.target === nodeId) {
                edgesToRemove.push(edge.id);
            }
        });
        
        edgesToRemove.forEach(edgeId => this.removeEdge(edgeId));
        
        // Удаляем ноду
        node.element.remove();
        this.nodes.delete(nodeId);
    }
    
    /**
     * Удаление связи
     */
    removeEdge(edgeId) {
        const edge = this.edges.get(edgeId);
        if (!edge) return;

        // Проверяем, нужно ли сбросить entry_point_agent
        this.resetFlowEntryPointIfNeeded(edge.source, edge.target);

        edge.element.remove();
        this.edges.delete(edgeId);

        console.log('🗑️ Связь удалена:', edgeId);
    }
    
    /**
     * Редактирование ноды
     */
    editNode(node) {
        console.log('Редактирование ноды:', node);
        // TODO: Показать модальное окно редактирования
    }
    
    /**
     * Очистка графа
     */
    clearGraph() {
        this.nodes.forEach(node => node.element.remove());
        this.edges.forEach(edge => edge.element.remove());
        this.nodes.clear();
        this.edges.clear();
    }
    
    /**
     * Зум +
     */
    zoomIn() {
        const newZoom = Math.min(this.config.maxZoom, this.zoom + this.config.zoomStep);
        if (newZoom !== this.zoom) {
            this.zoom = newZoom;
            this.updateTransform();
        }
    }
    
    /**
     * Зум -
     */
    zoomOut() {
        const newZoom = Math.max(this.config.minZoom, this.zoom - this.config.zoomStep);
        if (newZoom !== this.zoom) {
            this.zoom = newZoom;
            this.updateTransform();
        }
    }
    
    /**
     * Подогнать к экрану
     */
    fitToScreen() {
        if (this.nodes.size === 0) return;
        
        // Вычисляем границы всех нод
        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;
        
        this.nodes.forEach(node => {
            minX = Math.min(minX, node.x);
            minY = Math.min(minY, node.y);
            maxX = Math.max(maxX, node.x + node.width);
            maxY = Math.max(maxY, node.y + node.height);
        });
        
        const contentWidth = maxX - minX;
        const contentHeight = maxY - minY;
        
        const rect = this.svg.getBoundingClientRect();
        const padding = 50;
        
        const scaleX = (rect.width - padding * 2) / contentWidth;
        const scaleY = (rect.height - padding * 2) / contentHeight;
        
        this.zoom = Math.min(scaleX, scaleY, this.config.maxZoom);
        this.panX = (rect.width - contentWidth * this.zoom) / 2 - minX * this.zoom;
        this.panY = (rect.height - contentHeight * this.zoom) / 2 - minY * this.zoom;
        
        this.updateTransform();
    }
    
    /**
     * Обновление трансформации
     */
    updateTransform() {
        // Обновляем overlay
        this.overlay.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
        
        // Обновляем SVG группы
        const transform = `translate(${this.panX}, ${this.panY}) scale(${this.zoom})`;
        this.nodesGroup.setAttribute('transform', transform);
        this.edgesGroup.setAttribute('transform', transform);
        
        // Обновляем индикатор зума
        this.updateZoomIndicator();
    }
    
    /**
     * Обновление индикатора зума
     */
    updateZoomIndicator() {
        const zoomLevel = document.querySelector('.zoom-level');
        if (zoomLevel) {
            zoomLevel.textContent = `${Math.round(this.zoom * 100)}%`;
        }
    }
    
    /**
     * Получение точки входа
     */
    getEntryPoint() {
        // Ищем ноду, помеченную как entry point
        for (const node of this.nodes.values()) {
            if (node.data.params?.isEntryPoint) {
                return node.id;
            }
        }
        
        // Если нет явной точки входа, возвращаем первую ноду
        const firstNode = this.nodes.values().next().value;
        return firstNode ? firstNode.id : null;
    }
    
    /**
     * Обновление визуализации ноды после изменения данных
     */
    async updateNodeFromData(node) {
        if (!node || !node.element) return;
        
        // Сохраняем текущую позицию
        const currentX = node.x;
        const currentY = node.y;
        
        // Пересоздаем содержимое ноды
        await this.createSimpleNodeElement(node.element, node);
        
        // Восстанавливаем позицию
        node.x = currentX;
        node.y = currentY;
        node.element.style.transform = `translate3d(${node.x}px, ${node.y}px, 0)`;
        
        // Обновляем обработчики
        this.setupNodeHandlers(node);
        
        console.log('✅ Нода обновлена:', node.id);
    }
    
    /**
     * Дублирование ноды
     */
    duplicateNode(node) {
        const duplicatedData = {
            ...node.data,
            id: `${node.data.type}_${Date.now()}`,
            ui: {
                x: node.x + 50,
                y: node.y + 50,
                width: node.width,
                height: node.height
            }
        };
        
        return this.addNode(duplicatedData);
    }
}

// Экспортируем класс в глобальную область

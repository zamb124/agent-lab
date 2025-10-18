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
        
        // Показываем загрузчик
        element.innerHTML = `
            <div class="node-loading">
                <div class="loader"></div>
                <span>Загрузка...</span>
            </div>
            
            <!-- Порты для подключения -->
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
                
                // Создаем расширенную карточку тула с информацией
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
                    
                    <!-- Порты для подключения -->
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
        
        // Определяем какие порты нужны
        let portsHtml = '';
        
        if (nodeType === 'flow_node') {
            // Flow: только выходной порт (entry point)
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
            // Tool: только входной порт (конечная нода)
            portsHtml = `
                <div class="node-ports">
                    <div class="input-ports">
                        <div class="port input-port" data-port-type="input" data-port-id="input">
                            <div class="port-dot"></div>
                        </div>
                    </div>
                </div>
            `;
        } else if (nodeType === 'message_node') {
            // Message: только входной порт
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
            // Agent, Function, Conditional: оба порта
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
            
            ${portsHtml}
        `;
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
            
            // Инициализируем HTMX для новых элементов
            if (typeof htmx !== 'undefined') {
                htmx.process(element);
            }
            
            // Добавляем кнопки (i) для описаний полей
            this.addFieldInfoButtons(element);
            
            // Настраиваем автосохранение для полей
            this.setupAutoSave(element, modelType, modelId);
            
            // Добавляем порты для соединений
            this.addNodePorts(element);
            
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
                
                <!-- Порты для подключения -->
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
    addNodePorts(element) {
        // Проверяем, что порты еще не добавлены
        if (element.querySelector('.node-ports')) return;
        
        const nodeType = element.dataset.nodeType;
        
        // Создаем контейнер портов
        const portsContainer = document.createElement('div');
        portsContainer.className = 'node-ports';
        
        let portsHTML = '';
        
        // Определяем какие порты нужны для каждого типа
        if (nodeType === 'flow_node') {
            // Flow: только выходной порт (entry point)
            portsHTML = `
                <div class="output-ports">
                    <div class="port output-port" data-port-type="output" data-port-id="output">
                        <div class="port-dot"></div>
                    </div>
                </div>
            `;
        } else if (nodeType === 'tool_node') {
            // Tool: только входной порт
            portsHTML = `
                <div class="input-ports">
                    <div class="port input-port" data-port-type="input" data-port-id="input">
                        <div class="port-dot"></div>
                    </div>
                </div>
            `;
        } else if (nodeType === 'agent_node') {
            // Проверяем тип агента из данных ноды
            const node = this.nodes.get(element.dataset.nodeId);
            const agentType = node?.data?.params?.type;
            
            if (agentType === 'stategraph') {
                // StateGraph: только входной порт (законченный граф)
                portsHTML = `
                    <div class="input-ports">
                        <div class="port input-port" data-port-type="input" data-port-id="input">
                            <div class="port-dot"></div>
                        </div>
                    </div>
                `;
            } else {
                // ReAct Agent: оба порта (может принимать и отдавать)
                portsHTML = `
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
        }
        
        portsContainer.innerHTML = portsHTML;
        
        // Добавляем порты к ноде
        element.appendChild(portsContainer);
        
        // Настраиваем обработчики для портов
        const ports = portsContainer.querySelectorAll('.port');
        ports.forEach(port => {
            port.addEventListener('mousedown', (e) => {
                const node = this.nodes.get(element.dataset.nodeId);
                if (node) {
                    this.handlePortMouseDown(e, node, port);
                }
            });
        });
    }
    
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
        
        // Отладка
        console.log('🔗 Обновлена связь:', edge.id, 'path:', path);
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
        if (!this.isConnecting || !this.connectionStart) return;
        
        // Ищем целевой порт
        const targetPort = e.target.closest('.port');
        const targetNode = e.target.closest('.canvas-node');
        
        if (targetPort && targetNode && targetPort.dataset.portType === 'input') {
            const targetNodeId = targetNode.dataset.nodeId;
            const sourceNodeId = this.connectionStart.node.id;
            
            if (targetNodeId !== sourceNodeId) {
                // Валидируем подключение
                if (this.validateConnection(sourceNodeId, targetNodeId)) {
                    this.createConnection(sourceNodeId, targetNodeId);
                } else {
                    // Показываем ошибку валидации
                    this.builder.showNotification('Недопустимое подключение', 'error');
                }
            }
        }
        
        // Очищаем временные элементы
        this.cleanupConnection();
    }
    
    /**
     * Валидация подключения между нодами
     */
    validateConnection(sourceId, targetId) {
        const sourceNode = this.nodes.get(sourceId);
        const targetNode = this.nodes.get(targetId);
        
        if (!sourceNode || !targetNode) return false;
        
        const sourceType = sourceNode.data.type;
        const targetType = targetNode.data.type;
        
        console.log(`🔍 Валидация: ${sourceType} -> ${targetType}`);
        
        // Правила подключений для StateGraph нод:
        // Flow -> любая нода с input портом
        // Agent, Function, Router, Message -> любая нода с input портом
        // Tool -> ничего (конечная нода, нет output порта)
        
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
        
        if (sourceType === 'tool_node') {
            // Tool - конечная нода, не может быть источником
            console.warn('Tool не может быть источником подключения');
            return false;
        }
        
        // Для всех остальных типов (agent, function, router, message) - разрешаем
        // Они могут подключаться к любой ноде кроме flow и самих себя
        if (targetType === 'flow_node') {
            console.warn(`${sourceType} не может подключаться к Flow`);
            return false;
        }
        
        if (sourceId === targetId) {
            console.warn('Нельзя подключить ноду к самой себе');
            return false;
        }
        
        return true;
    }
    
    /**
     * Создание соединения
     */
    createConnection(sourceId, targetId) {
        const edgeId = `${sourceId}-${targetId}`;
        
        // Проверяем, что связь не существует
        if (this.edges.has(edgeId)) return;
        
        const edgeData = {
            id: edgeId,
            source: sourceId,
            target: targetId,
            type: 'default'
        };
        
        this.addEdge(edgeData);
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
        
        edge.element.remove();
        this.edges.delete(edgeId);
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

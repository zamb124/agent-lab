/**
 * FlowCanvas - визуальный редактор графа на Drawflow
 * Использует Light DOM для совместимости с глобальными CSS Drawflow
 * 
 * Архитектура:
 * - index.js: главный класс компонента с логикой
 * - templates.js: HTML шаблоны
 * - events.js: event handlers
 * - drawflow.css: глобальные стили
 * - drawflow-injector.js: инжектор стилей
 */
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FlowsStore } from '../../../store/flows.store.js';
import { EdgeLabelsManager } from '../edge-labels.js';
import { renderCanvas } from './templates.js';
import { setupEvents, setupDragDrop, setupContextMenu, setupNodeClickHandling } from './events.js';
import { injectDrawflowStyles } from './drawflow-injector.js';

const NODE_TYPE_ICON_NAMES = {
    'llm_node': 'llm_node',
    'code': 'code',
    'external_api': 'globe',
    'remote_flow': 'cloud',
    'flow': 'workflow',
    'mcp': 'mcp',
    'channel': 'send',
};

const RESOURCE_TYPE_ICON_NAMES = {
    'code': 'code',
    'rag': 'search',
    'files': 'folder',
    'prompt': 'chat',
    'llm': 'bot',
    'secret': 'key',
    'http': 'globe',
    'cache': 'database',
};

const RESOURCE_TYPE_COLORS = {
    'code': '#8b5cf6',
    'rag': '#3b82f6',
    'files': '#f59e0b',
    'prompt': '#10b981',
    'llm': '#ec4899',
    'secret': '#ef4444',
    'http': '#06b6d4',
    'cache': '#14b8a6',
};

/** Иконки бейджа channel-ноды (правый нижний угол), имена из ICON_MAP. Email — doc-detail, т.к. mail/email дают тот же svg что send. */
const CHANNEL_NODE_BADGE_ICONS = {
    telegram: 'send',
    email: 'doc-detail',
    whatsapp: 'chat',
    sms: 'server',
    webhook: 'globe',
};

const CHANNEL_NODE_BADGE_TITLES = {
    telegram: 'Telegram',
    email: 'Email',
    whatsapp: 'WhatsApp',
    sms: 'SMS',
    webhook: 'Webhook',
};

export class FlowCanvas extends PlatformElement {
    createRenderRoot() {
        return this;
    }

    static properties = {
        nodeConfigs: { type: Object },
        entryNodeId: { type: String },
        nodeIdCounter: { type: Number },
        contextMenu: { type: Object },
        connectionContextMenu: { type: Object },
        edgeConditions: { type: Object },
    };

    constructor() {
        super();
        this.flowConfig = null;
        this._editor = null;
        this.nodeConfigs = new Map();
        this.resourceConfigs = new Map();
        this.entryNodeId = null;
        this.nodeIdCounter = 1;
        this.resourceIdCounter = 1;
        this.contextMenu = null;
        this.connectionContextMenu = null;
        this.resourceContextMenu = null;
        this._edgeLabelsManager = null;
        this.edgeConditions = new Map();
        this._pendingConnection = null;
        this._isImporting = false;
        this._resourceElements = new Map();
        
        this._handleClickOutside = this._handleClickOutside.bind(this);
        this._handleNodeClick = this._handleNodeClick.bind(this);
        this._handleResourceClick = this._handleResourceClick.bind(this);
        this._zoomIn = this._zoomIn.bind(this);
        this._zoomOut = this._zoomOut.bind(this);
        this._zoomReset = this._zoomReset.bind(this);
        this._setAsEntryPoint = this._setAsEntryPoint.bind(this);
        this._deleteNode = this._deleteNode.bind(this);
        this._duplicateNode = this._duplicateNode.bind(this);
        this._toggleBreakpoint = this._toggleBreakpoint.bind(this);
        this._deleteResource = this._deleteResource.bind(this);
        
        this.breakpointManager = null;
        
        this.state = this.use(s => ({
            activeTool: s.editor.activeTool,
            historyPosition: s.editor.historyPosition,
            historyStack: s.editor.historyStack,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        injectDrawflowStyles();
        document.addEventListener('click', this._handleClickOutside);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._handleClickOutside);
    }

    firstUpdated() {
        this._initDrawflow();
    }
    
    updated(changedProperties) {
        super.updated(changedProperties);
        
        if (changedProperties.has('state')) {
            const prevState = changedProperties.get('state');
            const currentState = this.state.value;
            
            if (prevState?.activeTool !== currentState.activeTool) {
                this._applyActiveTool(currentState.activeTool);
            }
            
            if (prevState?.historyPosition !== currentState.historyPosition) {
                this._applyHistorySnapshot();
            }
        }
    }

    _handleClickOutside() {
        if (this.contextMenu) {
            this.contextMenu = null;
        }
        if (this.connectionContextMenu) {
            this.connectionContextMenu = null;
        }
    }

    _initDrawflow() {
        const container = this.querySelector('#drawflow-area');
        
        if (!container) {
            console.error('[FlowCanvas] #drawflow-area container not found');
            return;
        }
        
        if (typeof Drawflow === 'undefined') {
            console.error('[FlowCanvas] Drawflow library not loaded');
            return;
        }

        this._editor = new Drawflow(container);
        this._editor.reroute = true;
        this._editor.reroute_fix_curvature = true;
        this._editor.force_first_input = false;
        this._editor.start();

        this._edgeLabelsManager = new EdgeLabelsManager(
            container,
            this._editor,
            (fromId, toId, currentCondition) => this._showEdgeConditionModal(fromId, toId, currentCondition)
        );

        setupEvents(this);
        setupDragDrop(this);
        setupContextMenu(this);
        setupNodeClickHandling(this);
    }

    _handleNodeClick(e) {
        const node = e.target.closest('.drawflow-node');
        if (!node) return;

        const nodeId = node.id.replace('node-', '');
        const config = this.nodeConfigs.get(nodeId);
        if (config) {
            this.emit('node-selected', {
                nodeId: config.nodeId,
                nodeConfig: {
                    ...config,
                    config: { ...config.config }
                },
                drawflowId: nodeId,
            });
        }
    }
    
    _applyActiveTool(tool) {
        if (!this._editor) return;
        
        if (tool === 'select') {
            this._editor.editor_mode = 'fixed';
        } else if (tool === 'add') {
            this._editor.editor_mode = 'edit';
        }
    }
    
    _applyHistorySnapshot() {
        const snapshot = FlowsStore.getCurrentHistorySnapshot();
        if (!snapshot) return;
        
        this._isImporting = true;
        
        this._editor.clear();
        this._editor.import(snapshot.drawflowData);
        
        this.nodeConfigs = new Map(snapshot.nodeConfigs);
        this.edgeConditions = new Map(snapshot.edgeConditions);
        this.entryNodeId = snapshot.entryNodeId;
        
        this._renderAllNodes();
        this._edgeLabelsManager?.updateAll();
        
        this._isImporting = false;
    }
    
    _saveSnapshot() {
        if (!this._editor) return;
        
        const snapshot = {
            drawflowData: this._editor.export(),
            nodeConfigs: new Map(this.nodeConfigs),
            edgeConditions: new Map(this.edgeConditions),
            entryNodeId: this.entryNodeId,
            timestamp: Date.now(),
        };
        
        FlowsStore.pushHistory(snapshot);
    }

    _setAsEntryPoint() {
        if (this.contextMenu) {
            const drawflowId = parseInt(this.contextMenu.drawflowId);
            this._setEntryNode(drawflowId);
            this.contextMenu = null;
        }
    }

    _deleteNode() {
        if (this.contextMenu) {
            const nodeId = this.contextMenu.nodeId;
            this.removeNode(nodeId);
            this.emit('node-deleted', { nodeId });
            this.contextMenu = null;
            this._saveSnapshot();
        }
    }

    _duplicateNode() {
        if (this.contextMenu) {
            const config = this.nodeConfigs.get(this.contextMenu.drawflowId);
            if (config) {
                const nodeType = {
                    type: config.type,
                    name: config.name,
                    color: config.color,
                };
                const nodeData = this._editor.getNodeFromId(parseInt(this.contextMenu.drawflowId));
                if (!nodeData) {
                    throw new Error(`[FlowCanvas] Node data not found for drawflowId: ${this.contextMenu.drawflowId}`);
                }
                const posX = nodeData.pos_x + 50;
                const posY = nodeData.pos_y + 50;
                this._addNode(nodeType, posX, posY);
            }
            this.contextMenu = null;
        }
    }

    _toggleBreakpoint() {
        if (this.contextMenu && this.breakpointManager) {
            const nodeId = this.contextMenu.nodeId;
            this.breakpointManager.toggleBreakpoint(nodeId);
            this.contextMenu = null;
        }
    }

    _handleResourceClick(e) {
        const resourceEl = e.target.closest('.resource-block');
        if (!resourceEl) return;
        
        const resourceId = resourceEl.dataset.resourceId;
        const config = this.resourceConfigs.get(resourceId);
        if (config) {
            this.emit('resource-selected', {
                resourceId,
                resourceConfig: { ...config },
            });
        }
    }

    _deleteResource() {
        if (this.resourceContextMenu) {
            const resourceId = this.resourceContextMenu.resourceId;
            this.removeResource(resourceId);
            this.emit('resource-deleted', { resourceId });
            this.resourceContextMenu = null;
            this._saveSnapshot();
        }
    }

    async addResource(resourceType, posX, posY) {
        const resourceId = `${resourceType.type}_${this.resourceIdCounter++}`;
        const color = RESOURCE_TYPE_COLORS[resourceType.type] || '#6b7280';
        
        const resourceEl = this._createResourceElement(resourceId, resourceType, posX, posY);
        
        const drawflowEl = this.querySelector('#drawflow-area .drawflow');
        if (drawflowEl) {
            drawflowEl.appendChild(resourceEl);
        }
        
        this._resourceElements.set(resourceId, resourceEl);
        this.resourceConfigs.set(resourceId, {
            resourceId,
            type: resourceType.type,
            config: {},
            color,
            name: resourceType.name,
            position: { x: posX, y: posY },
        });
        
        this._setupResourceDrag(resourceEl, resourceId);
        
        this.emit('resource-added', { resourceId, resourceType });
        this._saveSnapshot();
        
        return resourceId;
    }

    _createResourceElement(resourceId, resourceType, posX, posY, language = null) {
        const color = RESOURCE_TYPE_COLORS[resourceType.type] || '#6b7280';
        const bgColor = color + '20';
        const iconName = RESOURCE_TYPE_ICON_NAMES[resourceType.type] || 'box';
        
        // Language badge для code ресурсов - SVG иконки (в правом нижнем углу блока)
        let langBadge = '';
        if (resourceType.type === 'code' && language) {
            const langIcon = language === 'javascript' ? 'javascript' : 'python';
            langBadge = `
                <div class="resource-lang-badge" data-lang="${language}" style="
                    position: absolute;
                    bottom: -4px;
                    right: -4px;
                    width: 18px;
                    height: 18px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 10;
                "><platform-icon name="${langIcon}" size="18" colored></platform-icon></div>
            `;
        }
        
        const el = document.createElement('div');
        el.className = 'resource-block';
        el.dataset.resourceId = resourceId;
        el.style.cssText = `
            position: absolute;
            left: ${posX}px;
            top: ${posY}px;
            min-width: 120px;
            padding: 10px 14px;
            background: var(--glass-solid-medium);
            border: 2px solid ${color}40;
            border-radius: 12px;
            cursor: move;
            user-select: none;
            z-index: 2;
            display: flex;
            align-items: center;
            gap: 10px;
            transition: box-shadow 0.15s ease, border-color 0.15s ease;
        `;
        
        el.innerHTML = `
            <div class="resource-icon" style="
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: ${bgColor};
                display: flex;
                align-items: center;
                justify-content: center;
                color: ${color};
                flex-shrink: 0;
            ">
                <platform-icon name="${iconName}" size="16"></platform-icon>
            </div>
            <div class="resource-info">
                <div class="resource-name" style="
                    font-size: 13px;
                    font-weight: 500;
                    color: var(--text-primary);
                ">${resourceId}</div>
                <div class="resource-type" style="
                    font-size: 11px;
                    color: var(--text-tertiary);
                ">${resourceType.name}</div>
            </div>
            ${langBadge}
        `;
        
        el.addEventListener('click', this._handleResourceClick);
        
        el.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.resourceContextMenu = {
                x: e.clientX,
                y: e.clientY,
                resourceId,
            };
            this.requestUpdate();
        });
        
        return el;
    }

    _setupResourceDrag(el, resourceId) {
        let isDragging = false;
        let startX, startY, origX, origY;
        
        el.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            isDragging = true;
            startX = e.clientX;
            startY = e.clientY;
            origX = parseInt(el.style.left) || 0;
            origY = parseInt(el.style.top) || 0;
            el.style.zIndex = '100';
            e.preventDefault();
        });
        
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            
            const zoom = this._editor?.zoom || 1;
            const dx = (e.clientX - startX) / zoom;
            const dy = (e.clientY - startY) / zoom;
            
            el.style.left = `${origX + dx}px`;
            el.style.top = `${origY + dy}px`;
        });
        
        document.addEventListener('mouseup', () => {
            if (!isDragging) return;
            isDragging = false;
            el.style.zIndex = '2';
            
            const config = this.resourceConfigs.get(resourceId);
            if (config) {
                config.position = {
                    x: parseInt(el.style.left) || 0,
                    y: parseInt(el.style.top) || 0,
                };
            }
        });
    }

    removeResource(resourceId) {
        const el = this._resourceElements.get(resourceId);
        if (el) {
            el.remove();
            this._resourceElements.delete(resourceId);
        }
        this.resourceConfigs.delete(resourceId);
    }

    updateResourceConfig(resourceId, config) {
        const existing = this.resourceConfigs.get(resourceId);
        if (existing) {
            const oldLanguage = existing.config?.language;
            existing.config = config;
            
            // Обновляем language badge для code ресурсов
            if (existing.type === 'code' && config.language !== oldLanguage) {
                this._updateResourceLanguageBadge(resourceId, config.language);
            }
        }
    }
    
    _updateResourceLanguageBadge(resourceId, language) {
        const el = this._resourceElements.get(resourceId);
        if (!el) return;
        
        let badge = el.querySelector('.resource-lang-badge');
        
        if (!language) {
            if (badge) badge.remove();
            return;
        }
        
        const langIcon = language === 'javascript' ? 'javascript' : 'python';
        
        if (badge) {
            badge.setAttribute('data-lang', language);
            badge.innerHTML = `<platform-icon name="${langIcon}" size="18" colored></platform-icon>`;
        } else {
            badge = document.createElement('div');
            badge.className = 'resource-lang-badge';
            badge.setAttribute('data-lang', language);
            badge.style.cssText = `
                position: absolute;
                bottom: -4px;
                right: -4px;
                width: 18px;
                height: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 10;
            `;
            badge.innerHTML = `<platform-icon name="${langIcon}" size="18" colored></platform-icon>`;
            el.appendChild(badge);
        }
    }

    getResourcesData() {
        const resources = {};
        for (const [resourceId, config] of this.resourceConfigs.entries()) {
            resources[resourceId] = {
                type: config.type,
                config: config.config || {},
                position: config.position,
            };
        }
        return resources;
    }

    /**
     * Установить BreakpointManager
     */
    setBreakpointManager(manager) {
        this.breakpointManager = manager;
        
        // Слушаем события breakpoint manager
        if (manager) {
            manager.addEventListener('breakpoint-toggled', (e) => {
                this._updateBreakpointIndicator(e.detail.nodeId, e.detail.enabled);
            });
            
            manager.addEventListener('breakpoint-hit', (e) => {
                this._showBreakpointHit(e.detail.nodeId);
            });
            
            manager.addEventListener('breakpoint-cleared', (e) => {
                this._clearBreakpointHit(e.detail.nodeId);
            });
        }
    }

    /**
     * Обновить индикатор breakpoint
     */
    _updateBreakpointIndicator(nodeId, enabled) {
        for (const [drawflowId, config] of this.nodeConfigs.entries()) {
            if (config.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (!nodeEl) {
                    console.warn(`[FlowCanvas] Node element not found for drawflowId=${drawflowId}`);
                    continue;
                }

                const agentNode = nodeEl.querySelector('.agent-node');
                if (!agentNode) {
                    console.warn(`[FlowCanvas] .agent-node not found in node-${drawflowId}`);
                    continue;
                }
                
                const existingIndicator = agentNode.querySelector('.node-breakpoint-indicator');
                if (existingIndicator) {
                    existingIndicator.remove();
                }

                if (enabled) {
                    const indicator = document.createElement('div');
                    indicator.className = 'node-breakpoint-indicator';
                    agentNode.appendChild(indicator);
                }
            }
        }
    }

    /**
     * Показать что breakpoint сработал
     */
    _showBreakpointHit(nodeId) {
        for (const [drawflowId, config] of this.nodeConfigs.entries()) {
            if (config.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (nodeEl) {
                    nodeEl.classList.add('breakpoint-active');
                }
            }
        }
    }

    /**
     * Убрать подсветку breakpoint hit
     */
    _clearBreakpointHit(nodeId) {
        for (const [drawflowId, config] of this.nodeConfigs.entries()) {
            if (config.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (nodeEl) {
                    nodeEl.classList.remove('breakpoint-active');
                }
            }
        }
    }

    _showEdgeConditionModal(fromId, toId, currentCondition = null) {
        const fromConfig = this.nodeConfigs.get(fromId.toString());
        const toConfig = this.nodeConfigs.get(toId.toString());
        
        if (!fromConfig || !toConfig) return;

        const variables = this._getAgentVariables();
        const stateVariables = this._getStateVariables();
        const sourceNodeConfig = fromConfig.config || {};
        
        let modal = document.querySelector('edge-condition-modal');
        if (!modal) {
            modal = document.createElement('edge-condition-modal');
            document.body.appendChild(modal);
        }

        modal.fromNode = fromConfig.nodeId;
        modal.toNode = toConfig.nodeId;
        modal.condition = currentCondition;
        modal.variables = variables;
        modal.sourceNodeConfig = sourceNodeConfig;
        modal.stateVariables = stateVariables;

        const handleConditionSaved = (e) => {
            const { condition } = e.detail;
            const key = `${fromId}-${toId}`;
            
            if (condition) {
                this.edgeConditions.set(key, condition);
                if (this._edgeLabelsManager) {
                    const labelText = this._getConditionLabelText(condition);
                    this._edgeLabelsManager.add(fromId, toId, labelText);
                }
            } else {
                this.edgeConditions.delete(key);
                if (this._edgeLabelsManager) {
                    this._edgeLabelsManager.remove(fromId, toId);
                }
            }
            
            this._pendingConnection = null;
            modal.removeEventListener('condition-saved', handleConditionSaved);
        };

        modal.addEventListener('condition-saved', handleConditionSaved);
        modal.addEventListener('close', () => {
            this._pendingConnection = null;
            modal.removeEventListener('condition-saved', handleConditionSaved);
        }, { once: true });

        modal.showModal();
    }

    _getConditionLabelText(condition) {
        if (!condition) return '';
        
        if (typeof condition === 'string') {
            return condition;
        }
        
        if (condition.type === 'simple') {
            const value = isNaN(condition.value) ? `'${condition.value}'` : condition.value;
            return `${condition.variable} ${condition.operator} ${value}`;
        }
        
        if (condition.type === 'python') {
            return 'Python';
        }
        
        return '';
    }

    _getStateVariables() {
        if (!this.flowConfig) {
            return [];
        }
        
        const variables = this.flowConfig.variables;
        if (!variables) {
            return [];
        }
        
        if (Array.isArray(variables)) {
            return variables.map(v => typeof v === 'object' ? v.name || v.key : v);
        }
        
        if (typeof variables === 'object') {
            return Object.keys(variables);
        }
        
        return [];
    }

    _showConnectionContextMenu(x, y, fromId, toId, currentCondition) {
        this.connectionContextMenu = {
            x,
            y,
            fromId,
            toId,
            currentCondition
        };
        this.requestUpdate();
    }

    _onEditConnectionCondition() {
        if (this.connectionContextMenu) {
            const { fromId, toId, currentCondition } = this.connectionContextMenu;
            this._showEdgeConditionModal(fromId, toId, currentCondition);
            this.connectionContextMenu = null;
        }
    }

    _onDeleteConnection() {
        if (this.connectionContextMenu) {
            const { fromId, toId } = this.connectionContextMenu;
            this._editor.removeSingleConnection(fromId, toId, 'output_1', 'input_1');
            this.connectionContextMenu = null;
        }
    }

    _getAgentVariables() {
        if (!this.flowConfig) {
            return [];
        }
        if (!this.flowConfig.variables) {
            return [];
        }
        if (Array.isArray(this.flowConfig.variables)) {
            return this.flowConfig.variables.map(v => v.name || v);
        }
        if (typeof this.flowConfig.variables === 'object') {
            return Object.keys(this.flowConfig.variables);
        }
        
        return ['route', 'status', 'category', 'result', 'type'];
    }

    async _addNode(nodeType, posX, posY) {
        const nodeId = `${nodeType.type}_${this.nodeIdCounter++}`;
        const isEntry = this.nodeConfigs.size === 0;
        
        const nodeHtml = await this._createNodeHtml(nodeId, nodeType, isEntry);
        
        const drawflowId = this._editor.addNode(
            nodeId,
            1, 1,
            posX, posY,
            nodeType.type,
            { nodeId, type: nodeType.type },
            nodeHtml
        );

        this.nodeConfigs.set(drawflowId.toString(), {
            nodeId,
            type: nodeType.type,
            config: {},
            color: nodeType.color,
            name: nodeType.name,
        });

        if (isEntry) {
            this._setEntryNode(drawflowId);
        }

        this.emit('node-added', { nodeId, nodeType, drawflowId });
        this._updateVirtualNodes();
        this._saveSnapshot();
        
        return drawflowId;
    }

    async _createNodeHtml(nodeId, nodeType, isEntry = false, isInherited = false) {
        const iconName = NODE_TYPE_ICON_NAMES[nodeType.type];
        if (!iconName) throw new Error(`No icon mapping for type: ${nodeType.type}`);
        await this.icon.load(iconName);
        
        return this._createNodeHtmlSync(nodeId, nodeType, isEntry, isInherited);
    }

    _createNodeHtmlSync(nodeId, nodeType, isEntry = false, isInherited = false, language = null, channelId = null) {
        const bgColor = nodeType.color + '20';
        const entryBadge = isEntry 
            ? '<div class="agent-node-entry-badge">▶</div>' 
            : '';
        const inheritedBadge = isInherited
            ? '<div class="agent-node-inherited-badge" title="Inherited from base"><svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 3v10M8 3l-3 3M8 3l3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>'
            : '';
        
        // Бейдж языка для code нод - используем SVG иконки
        let languageBadge = '';
        if (nodeType.type === 'code' && language) {
            const langIcon = language === 'javascript' ? 'javascript' : 'python';
            languageBadge = `<div class="agent-node-lang-badge" data-lang="${language}" title="${language}"><platform-icon name="${langIcon}" size="14" colored></platform-icon></div>`;
        }

        let channelBadge = '';
        if (nodeType.type === 'channel' && channelId) {
            const chIcon = CHANNEL_NODE_BADGE_ICONS[channelId] || 'send';
            const chTitle = CHANNEL_NODE_BADGE_TITLES[channelId] || channelId;
            channelBadge = `<div class="agent-node-lang-badge agent-node-channel-badge" data-channel="${channelId}" title="${chTitle}"><platform-icon name="${chIcon}" size="14"></platform-icon></div>`;
        }
        
        const iconName = NODE_TYPE_ICON_NAMES[nodeType.type];
        let iconSvg = this.icon.getFromCache(iconName);
        
        iconSvg = iconSvg
            .replace(/<svg/, '<svg width="16" height="16"')
            .replace(/\s+width="[^"]*"/g, ' width="16"')
            .replace(/\s+height="[^"]*"/g, ' height="16"');
        
        return `
            ${inheritedBadge}
            <div class="agent-node">
                ${entryBadge}
                <div class="agent-node-icon" style="background: ${bgColor}; color: ${nodeType.color};">
                    ${iconSvg}
                </div>
                <div class="agent-node-info">
                    <div class="agent-node-name">${nodeId}</div>
                    <div class="agent-node-type">${nodeType.name || nodeType.type}</div>
                </div>
                ${languageBadge}
                ${channelBadge}
            </div>
        `;
    }

    async _preloadIcons(nodes) {
        const iconNames = new Set();
        for (const n of Object.values(nodes)) {
            const iconName = NODE_TYPE_ICON_NAMES[n.type];
            if (!iconName) throw new Error(`No icon mapping for type: ${n.type}`);
            iconNames.add(iconName);
        }
        for (const ic of Object.values(CHANNEL_NODE_BADGE_ICONS)) {
            iconNames.add(ic);
        }
        await this.icon.preload([...iconNames]);
    }

    _setEntryNode(drawflowId) {
        if (this.entryNodeId) {
            const oldNodeEl = this.querySelector(`#node-${this.entryNodeId}`);
            if (oldNodeEl) {
                oldNodeEl.classList.remove('is-entry-node');
                const oldBadge = oldNodeEl.querySelector('.agent-node-entry-badge');
                if (oldBadge) oldBadge.remove();
            }
        }
        
        this.entryNodeId = drawflowId.toString();
        const newNodeEl = this.querySelector(`#node-${drawflowId}`);
        if (newNodeEl) {
            newNodeEl.classList.add('is-entry-node');
            const agentNode = newNodeEl.querySelector('.agent-node');
            if (agentNode && !agentNode.querySelector('.agent-node-entry-badge')) {
                const badge = document.createElement('div');
                badge.className = 'agent-node-entry-badge';
                badge.textContent = '▶';
                agentNode.appendChild(badge);
            }
        }
        
        this._updateVirtualNodes();
    }

    _updateVirtualNodes() {
        const exported = this._editor.export();
        if (!exported) {
            throw new Error('[FlowCanvas] Editor export failed');
        }
        if (!exported.drawflow) {
            throw new Error('[FlowCanvas] Drawflow data missing');
        }
        if (!exported.drawflow.Home) {
            throw new Error('[FlowCanvas] Home data missing');
        }
        if (!exported.drawflow.Home.data) {
            throw new Error('[FlowCanvas] Home.data missing');
        }

        const homeData = exported.drawflow.Home.data;

        this.querySelectorAll('.virtual-end-bundle').forEach((el) => el.remove());
        const legacySvg = this.querySelector('.virtual-connections-svg');
        if (legacySvg) {
            legacySvg.remove();
        }

        if (Object.keys(homeData).length === 0) {
            return;
        }
        
        const endNodeIds = [];
        for (const [drawflowId, nodeData] of Object.entries(homeData)) {
            if (!nodeData.outputs) {
                endNodeIds.push(drawflowId);
                continue;
            }

            const hasOutputConnections = Object.values(nodeData.outputs).some(
                output => output.connections && output.connections.length > 0
            );
            
            if (!hasOutputConnections) {
                endNodeIds.push(drawflowId);
            }
        }
        
        endNodeIds.forEach((drawflowId) => {
            const nodeData = homeData[drawflowId];
            if (!nodeData) return;

            const nodeEl = this.querySelector(`#node-${drawflowId}`);
            if (!nodeEl) return;

            nodeEl.appendChild(this._createVirtualEndBundle());
        });
    }

    _createVirtualEndBundle() {
        const bundle = document.createElement('div');
        bundle.className = 'virtual-end-bundle';
        bundle.setAttribute('aria-hidden', 'true');

        const segment = document.createElement('div');
        segment.className = 'virtual-end-line';

        const marker = document.createElement('div');
        marker.className = 'virtual-end-marker';
        marker.textContent = 'END';

        bundle.append(segment, marker);
        return bundle;
    }

    _getNodeColor(type) {
        const colors = {
            'llm_node': '#f59e0b',
            'code': '#8b5cf6',
            'external_api': '#06b6d4',
            'remote_flow': '#3b82f6',
            'flow': '#ec4899',
            'mcp': '#14b8a6',
            'channel': '#10b981',
        };
        
        const color = colors[type];
        if (!color) throw new Error(`No color mapping for node type: ${type}`);
        
        return color;
    }

    getData() {
        const exported = this._editor.export();
        if (!exported) {
            throw new Error('[FlowCanvas] Editor export failed');
        }
        if (!exported.drawflow) {
            throw new Error('[FlowCanvas] Drawflow data missing');
        }
        if (!exported.drawflow.Home) {
            throw new Error('[FlowCanvas] Home data missing');
        }
        if (!exported.drawflow.Home.data) {
            throw new Error('[FlowCanvas] Home.data missing');
        }

        const homeData = exported.drawflow.Home.data;
        
        const nodes = {};
        const edges = [];

        for (const [drawflowId, nodeData] of Object.entries(homeData)) {
            const savedConfig = this.nodeConfigs.get(drawflowId);
            if (!savedConfig) {
                throw new Error(`[FlowCanvas] Node config not found for drawflowId: ${drawflowId}`);
            }

            const nodeId = savedConfig.nodeId;
            if (!nodeId) {
                throw new Error(`[FlowCanvas] nodeId missing in config for drawflowId: ${drawflowId}`);
            }

            const nodeType = savedConfig.type;
            if (!nodeType) {
                throw new Error(`[FlowCanvas] Node type missing for nodeId: ${nodeId}`);
            }

            const config = savedConfig.config || {};

            nodes[nodeId] = {
                type: nodeType,
                nodeId: nodeId,
                ...config,
                position: {
                    x: Math.round(nodeData.pos_x),
                    y: Math.round(nodeData.pos_y),
                },
            };

            if (!nodeData.outputs) {
                continue;
            }

            const outputs = nodeData.outputs;
            for (const [, outputData] of Object.entries(outputs)) {
                if (!outputData.connections) {
                    continue;
                }

                const connections = outputData.connections;
                for (const conn of connections) {
                    const targetDrawflowId = conn.node;
                    const targetConfig = this.nodeConfigs.get(String(targetDrawflowId));
                    if (!targetConfig) {
                        throw new Error(`[FlowCanvas] Target node config not found for drawflowId: ${targetDrawflowId}`);
                    }

                    const targetNodeId = targetConfig.nodeId;
                    if (!targetNodeId) {
                        throw new Error(`[FlowCanvas] Target nodeId missing for drawflowId: ${targetDrawflowId}`);
                    }

                    const edge = {
                        from: nodeId,
                        to: targetNodeId,
                    };
                    
                    const conditionKey = `${drawflowId}-${targetDrawflowId}`;
                    const condition = this.edgeConditions.get(conditionKey);
                    if (condition) {
                        edge.condition = condition;
                    }
                    
                    edges.push(edge);
                }
            }
        }

        const entryConfig = this.nodeConfigs.get(this.entryNodeId);
        const entry = entryConfig ? entryConfig.nodeId : null;

        const resources = this.getResourcesData();

        return { nodes, edges, entry, resources };
    }

    updateNodeConfig(nodeId, config) {
        console.log('[FlowCanvas] updateNodeConfig called:', { nodeId, config });
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                console.log('[FlowCanvas] Found node, old config:', nodeConfig.config);
                const oldLanguage = nodeConfig.config?.language;
                const oldChannel = nodeConfig.config?.channel;
                nodeConfig.config = config;
                console.log('[FlowCanvas] Updated config:', nodeConfig.config);
                
                // Обновляем language badge если язык изменился
                if (nodeConfig.type === 'code' && config.language !== oldLanguage) {
                    this._updateLanguageBadge(drawflowId, config.language);
                }
                if (nodeConfig.type === 'channel' && config.channel !== oldChannel) {
                    this._updateChannelBadge(drawflowId, config.channel);
                }
                break;
            }
        }
    }
    
    _updateLanguageBadge(drawflowId, language) {
        const nodeEl = this.querySelector(`#node-${drawflowId}`);
        if (!nodeEl) return;
        
        let badge = nodeEl.querySelector('.agent-node-lang-badge');
        const agentNode = nodeEl.querySelector('.agent-node');
        
        if (!language) {
            if (badge) badge.remove();
            return;
        }
        
        const langIcon = language === 'javascript' ? 'javascript' : 'python';
        
        if (badge) {
            badge.setAttribute('data-lang', language);
            badge.setAttribute('title', language);
            badge.innerHTML = `<platform-icon name="${langIcon}" size="14" colored></platform-icon>`;
        } else if (agentNode) {
            badge = document.createElement('div');
            badge.className = 'agent-node-lang-badge';
            badge.setAttribute('data-lang', language);
            badge.setAttribute('title', language);
            badge.innerHTML = `<platform-icon name="${langIcon}" size="14" colored></platform-icon>`;
            agentNode.appendChild(badge);
        }
    }

    _updateChannelBadge(drawflowId, channelId) {
        const nodeEl = this.querySelector(`#node-${drawflowId}`);
        if (!nodeEl) return;

        let badge = nodeEl.querySelector('.agent-node-channel-badge');
        const agentNode = nodeEl.querySelector('.agent-node');

        if (!channelId) {
            if (badge) badge.remove();
            return;
        }

        const iconName = CHANNEL_NODE_BADGE_ICONS[channelId] || 'send';
        const title = CHANNEL_NODE_BADGE_TITLES[channelId] || channelId;

        void this.icon.load(iconName).then(() => {
            const el = this.querySelector(`#node-${drawflowId}`);
            if (!el) return;
            const ag = el.querySelector('.agent-node');
            if (!ag) return;

            let b = el.querySelector('.agent-node-channel-badge');
            const inner = `<platform-icon name="${iconName}" size="14"></platform-icon>`;
            if (b) {
                b.setAttribute('data-channel', channelId);
                b.setAttribute('title', title);
                b.innerHTML = inner;
            } else {
                b = document.createElement('div');
                b.className = 'agent-node-lang-badge agent-node-channel-badge';
                b.setAttribute('data-channel', channelId);
                b.setAttribute('title', title);
                b.innerHTML = inner;
                ag.appendChild(b);
            }
        });
    }

    /**
     * Обновляет nodeId ноды
     * @param {string} oldId - текущий nodeId
     * @param {string} newId - новый nodeId
     * @returns {boolean} - успешно ли обновление
     */
    updateNodeId(oldId, newId) {
        console.log('[FlowCanvas] updateNodeId called:', { oldId, newId });
        
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === oldId) {
                // Обновляем nodeId в конфиге
                nodeConfig.nodeId = newId;
                
                // Обновляем отображение имени в DOM
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (nodeEl) {
                    const nameEl = nodeEl.querySelector('.agent-node-name');
                    if (nameEl) {
                        nameEl.textContent = newId;
                    }
                }
                
                console.log('[FlowCanvas] Node ID updated successfully:', { drawflowId, oldId, newId });
                this._saveSnapshot();
                return true;
            }
        }
        
        console.warn('[FlowCanvas] Node not found for updateNodeId:', oldId);
        return false;
    }

    removeNode(nodeId) {
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                this._editor.removeNodeId(`node-${drawflowId}`);
                this.nodeConfigs.delete(drawflowId);
                this._updateVirtualNodes();
                break;
            }
        }
    }

    setNodeStatus(nodeId, status) {
        console.log(`[FlowCanvas] setNodeStatus: nodeId="${nodeId}", status="${status}"`);
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (nodeEl) {
                    nodeEl.classList.remove('node-running', 'node-completed', 'node-error');
                    
                    if (status && status !== 'null') {
                        nodeEl.classList.add(`node-${status}`);
                        console.log(`[FlowCanvas] Added class "node-${status}"`);
                    }
                }
                break;
            }
        }
    }

    highlightNode(nodeId, status) {
        this.setNodeStatus(nodeId, status);
    }

    clearNodeHighlight(nodeId) {
        this.setNodeStatus(nodeId, null);
    }

    clearAllHighlights() {
        this.clearAllStatuses();
    }

    clearAllStatuses() {
        const nodes = this.querySelectorAll('.drawflow-node');
        nodes.forEach(node => {
            node.classList.remove('node-running', 'node-completed', 'node-error');
        });
        this.clearAllNodeErrors();
    }

    setBreakpointStatus(nodeId, hasBreakpoint, isActive) {
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (nodeEl) {
                    const agentNode = nodeEl.querySelector('.agent-node');
                    const indicator = agentNode?.querySelector('.node-breakpoint-indicator');
                    
                    if (hasBreakpoint && !indicator && agentNode) {
                        const newIndicator = document.createElement('div');
                        newIndicator.className = 'node-breakpoint-indicator';
                        agentNode.appendChild(newIndicator);
                    } else if (!hasBreakpoint && indicator) {
                        indicator.remove();
                    }
                    
                    if (isActive) {
                        nodeEl.classList.add('breakpoint-active');
                    } else {
                        nodeEl.classList.remove('breakpoint-active');
                    }
                }
                break;
            }
        }
    }

    showNodeError(nodeId, errorMessage) {
        console.log(`[FlowCanvas] showNodeError: nodeId="${nodeId}", error="${errorMessage}"`);
        
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                console.log(`[FlowCanvas] Found node element:`, nodeEl);
                
                if (nodeEl) {
                    // Удаляем старый tooltip если есть
                    this.clearNodeError(nodeId);
                    
                    // Создаем контейнер для tooltips если его нет
                    let tooltipContainer = document.querySelector('.node-error-tooltips-container');
                    console.log(`[FlowCanvas] Existing container:`, tooltipContainer);
                    
                    if (!tooltipContainer) {
                        tooltipContainer = document.createElement('div');
                        tooltipContainer.className = 'node-error-tooltips-container';
                        document.body.appendChild(tooltipContainer);
                        console.log(`[FlowCanvas] Container appended to body`);
                    }
                    
                    // Получаем абсолютную позицию ноды на странице
                    const nodeRect = nodeEl.getBoundingClientRect();
                    
                    console.log(`[FlowCanvas] Node rect:`, nodeRect);
                    
                    const errorTooltip = document.createElement('div');
                    errorTooltip.className = 'node-error-tooltip';
                    errorTooltip.dataset.nodeId = nodeId;
                    errorTooltip.dataset.drawflowId = drawflowId;
                    
                    // Позиционируем fixed относительно viewport
                    const topPosition = nodeRect.top - 12;
                    const leftPosition = nodeRect.left + nodeRect.width / 2;
                    
                    console.log(`[FlowCanvas] Tooltip position: top=${topPosition}, left=${leftPosition}`);
                    
                    errorTooltip.style.top = `${topPosition}px`;
                    errorTooltip.style.left = `${leftPosition}px`;
                    errorTooltip.style.transform = 'translate(-50%, -100%)';
                    
                    errorTooltip.innerHTML = `
                        <div class="node-error-content">
                            <div class="node-error-message">${this._escapeHtml(errorMessage)}</div>
                            <div class="node-error-actions">
                                <button class="node-error-copy" title="Копировать">
                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                    </svg>
                                </button>
                                <button class="node-error-close" title="Закрыть">×</button>
                            </div>
                        </div>
                    `;
                    
                    const copyBtn = errorTooltip.querySelector('.node-error-copy');
                    const closeBtn = errorTooltip.querySelector('.node-error-close');
                    
                    copyBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        
                        // Fallback для копирования если clipboard API недоступен
                        if (navigator.clipboard && navigator.clipboard.writeText) {
                            navigator.clipboard.writeText(errorMessage).then(() => {
                                copyBtn.innerHTML = '✓';
                                setTimeout(() => {
                                    copyBtn.innerHTML = `
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                        </svg>
                                    `;
                                }, 1500);
                            }).catch(err => {
                                console.error('[FlowCanvas] Ошибка копирования:', err);
                                this._fallbackCopyTextToClipboard(errorMessage, copyBtn);
                            });
                        } else {
                            this._fallbackCopyTextToClipboard(errorMessage, copyBtn);
                        }
                    });
                    
                    closeBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        console.log('[FlowCanvas] Close button clicked');
                        this._removeTooltipWithAnimation(errorTooltip);
                    });
                    
                    tooltipContainer.appendChild(errorTooltip);
                    console.log(`[FlowCanvas] Tooltip appended:`, errorTooltip);
                    console.log(`[FlowCanvas] Tooltip computed style:`, getComputedStyle(errorTooltip));
                }
                break;
            }
        }
    }

    _updateTooltipPosition(tooltip, drawflowId) {
        const nodeEl = this.querySelector(`#node-${drawflowId}`);
        
        if (nodeEl) {
            const nodeRect = nodeEl.getBoundingClientRect();
            const topPosition = nodeRect.top - 12;
            const leftPosition = nodeRect.left + nodeRect.width / 2;
            
            tooltip.style.top = `${topPosition}px`;
            tooltip.style.left = `${leftPosition}px`;
        }
    }

    _updateAllErrorTooltipPositions() {
        const tooltipContainer = document.querySelector('.node-error-tooltips-container');
        if (tooltipContainer) {
            const tooltips = tooltipContainer.querySelectorAll('.node-error-tooltip');
            tooltips.forEach(tooltip => {
                const drawflowId = tooltip.dataset.drawflowId;
                if (drawflowId) {
                    this._updateTooltipPosition(tooltip, drawflowId);
                }
            });
        }
    }

    clearNodeError(nodeId) {
        const tooltipContainer = document.querySelector('.node-error-tooltips-container');
        if (tooltipContainer) {
            const tooltip = tooltipContainer.querySelector(`[data-node-id="${nodeId}"]`);
            if (tooltip) {
                this._removeTooltipWithAnimation(tooltip);
            }
        }
    }

    clearAllNodeErrors() {
        const tooltipContainer = document.querySelector('.node-error-tooltips-container');
        if (tooltipContainer) {
            const errorTooltips = tooltipContainer.querySelectorAll('.node-error-tooltip');
            errorTooltips.forEach(tooltip => this._removeTooltipWithAnimation(tooltip));
        }
    }

    _removeTooltipWithAnimation(tooltip) {
        tooltip.classList.add('hiding');
        setTimeout(() => {
            tooltip.remove();
        }, 300);
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    _fallbackCopyTextToClipboard(text, button) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.top = '0';
        textArea.style.left = '0';
        textArea.style.opacity = '0';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            const successful = document.execCommand('copy');
            if (successful) {
                button.innerHTML = '✓';
                setTimeout(() => {
                    button.innerHTML = `
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                    `;
                }, 1500);
            } else {
                console.error('[FlowCanvas] Fallback: не удалось скопировать');
            }
        } catch (err) {
            console.error('[FlowCanvas] Fallback: ошибка копирования', err);
        }
        
        document.body.removeChild(textArea);
    }

    async loadData(data, inherited = null) {
        console.log('[FlowCanvas] loadData called with:', { 
            nodes: Object.keys(data?.nodes || {}), 
            edges: data?.edges?.length,
            entry: data?.entry,
            inherited,
            isImporting: this._isImporting,
            stackTrace: new Error().stack
        });
        
        if (!this._editor) throw new Error('Editor not initialized');
        if (!data.nodes) throw new Error('Data.nodes required');
        
        if (this._isImporting) {
            console.warn('[FlowCanvas] Import already in progress, skipping duplicate loadData call');
            return;
        }
        
        console.log('[FlowCanvas] Clearing editor...');
        console.log('[FlowCanvas] Editor state before clear:', {
            drawflow: this._editor.drawflow,
            nodeCount: Object.keys(this._editor.drawflow?.drawflow?.Home?.data || {}).length
        });
        
        console.log('[FlowCanvas] Setting _isImporting = true');
        this._isImporting = true;
        
        this._editor.clear();
        
        console.log('[FlowCanvas] Editor state after clear:', {
            drawflow: this._editor.drawflow,
            nodeCount: Object.keys(this._editor.drawflow?.drawflow?.Home?.data || {}).length
        });
        
        console.log('[FlowCanvas] Editor cleared, adding nodes...');
        this.nodeConfigs.clear();
        this.entryNodeId = null;
        this.edgeConditions.clear();
        if (this._edgeLabelsManager) {
            this._edgeLabelsManager.clear();
        }
        this.nodeIdCounter = 1;
        
        // Очищаем ресурсы
        for (const el of this._resourceElements.values()) {
            el.remove();
        }
        this._resourceElements.clear();
        this.resourceConfigs.clear();
        this.resourceIdCounter = 1;
        
        if (this._edgeLabelsManager) {
            this._edgeLabelsManager._setupContainer();
        }
        this.querySelector('.virtual-connections-svg')?.remove();

        const { nodes, edges = [], entry, resources = {} } = data;
        const nodePositions = new Map();
        const inheritedNodeIds = inherited ? (inherited.nodeIds || new Set()) : new Set();

        await this._preloadIcons(nodes);

        let index = 0;
        for (const [nodeId, nodeConfig] of Object.entries(nodes)) {
            const isEntry = nodeId === entry;
            const isInherited = inheritedNodeIds.has(nodeId);
            const color = this._getNodeColor(nodeConfig.type);
            const nodeType = {
                type: nodeConfig.type,
                name: nodeConfig.type,
                color,
            };
            
            const posX = nodeConfig.position ? nodeConfig.position.x : 250 + (index % 2) * 280;
            const posY = nodeConfig.position ? nodeConfig.position.y : 80 + Math.floor(index / 2) * 120;
            
            const language = nodeConfig.type === 'code' ? (nodeConfig.language || 'python') : null;
            const channelId =
                nodeConfig.type === 'channel' ? (nodeConfig.channel || 'telegram') : null;
            const nodeHtml = this._createNodeHtmlSync(
                nodeId,
                nodeType,
                isEntry,
                isInherited,
                language,
                channelId
            );
            
            console.log('[FlowCanvas] Adding node:', {
                nodeId,
                drawflowId: this.nodeIdCounter,
                type: nodeType.type,
                stackTrace: new Error().stack
            });
            
            const drawflowId = this._editor.addNode(
                nodeId,
                1, 1,
                posX, posY,
                nodeConfig.type,
                { nodeId, type: nodeConfig.type, config: nodeConfig },
                nodeHtml
            );

            const { type, position, ...configFields } = nodeConfig;

            this.nodeConfigs.set(drawflowId.toString(), {
                nodeId,
                type: nodeConfig.type,
                config: configFields,
                color,
                isInherited,
            });

            nodePositions.set(nodeId, drawflowId);
            
            if (isEntry) {
                this._setEntryNode(drawflowId);
            }
            
            if (isInherited) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (!nodeEl) throw new Error(`Node element not found: ${drawflowId}`);
                nodeEl.classList.add('node-inherited');
            }
            
            this.nodeIdCounter++;
            index++;
        }

        // Временно отключаем событие connectionCreated
        if (this._connectionCreatedHandler) {
            this._editor.removeListener('connectionCreated', this._connectionCreatedHandler);
        }

        for (const edge of edges) {
            const fromId = nodePositions.get(edge.from);
            const toId = nodePositions.get(edge.to);
            if (!fromId || !toId) {
                console.warn(`[FlowCanvas] Skipping invalid edge: ${edge.from} -> ${edge.to} (fromId: ${fromId}, toId: ${toId})`);
                continue;
            }
            
            this._editor.addConnection(fromId, toId, 'output_1', 'input_1');
            
            if (edge.condition) {
                const key = `${fromId}-${toId}`;
                this.edgeConditions.set(key, edge.condition);
            }
        }
        
        // Включаем событие обратно
        if (this._connectionCreatedHandler) {
            this._editor.on('connectionCreated', this._connectionCreatedHandler);
        }
        
        this._isImporting = false;
        console.log('[FlowCanvas] Import completed successfully');
        
        for (const edge of edges) {
            if (edge.condition) {
                const fromId = nodePositions.get(edge.from);
                const toId = nodePositions.get(edge.to);
                if (fromId && toId) {
                    const labelText = this._getConditionLabelText(edge.condition);
                    this._edgeLabelsManager?.add(fromId, toId, labelText);
                }
            }
        }
        
        // Загружаем ресурсы
        for (const [resourceId, resourceConfig] of Object.entries(resources)) {
            const resourceType = {
                type: resourceConfig.type,
                name: resourceConfig.type,
            };
            const posX = resourceConfig.position?.x ?? 50;
            const posY = resourceConfig.position?.y ?? 50;
            
            const el = this._createResourceElement(resourceId, resourceType, posX, posY);
            const drawflowEl = this.querySelector('#drawflow-area .drawflow');
            if (drawflowEl) {
                drawflowEl.appendChild(el);
            }
            
            this._resourceElements.set(resourceId, el);
            this.resourceConfigs.set(resourceId, {
                resourceId,
                type: resourceConfig.type,
                config: resourceConfig.config || {},
                color: RESOURCE_TYPE_COLORS[resourceConfig.type] || '#6b7280',
                name: resourceConfig.type,
                position: { x: posX, y: posY },
            });
            
            this._setupResourceDrag(el, resourceId);
            this.resourceIdCounter++;
        }
        
        this._updateVirtualNodes();
    }

    _zoomIn() {
        if (!this._editor) {
            throw new Error('[FlowCanvas] Editor not initialized');
        }
        this._editor.zoom_in();
    }

    _zoomOut() {
        if (!this._editor) {
            throw new Error('[FlowCanvas] Editor not initialized');
        }
        this._editor.zoom_out();
    }

    _zoomReset() {
        if (!this._editor) {
            throw new Error('[FlowCanvas] Editor not initialized');
        }
        this._editor.zoom_reset();
    }

    render() {
        return renderCanvas(this);
    }
}

customElements.define('flow-canvas', FlowCanvas);



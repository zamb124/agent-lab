/**
 * AgentCanvas - визуальный редактор графа на Drawflow
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
import { AgentsStore } from '../../../store/agents.store.js';
import { EdgeLabelsManager } from '../edge-labels.js';
import { renderCanvas } from './templates.js';
import { setupEvents, setupDragDrop, setupContextMenu, setupNodeClickHandling } from './events.js';
import { injectDrawflowStyles } from './drawflow-injector.js';

const NODE_TYPE_ICON_NAMES = {
    'react_node': 'agent',
    'function': 'code',
    'tool': 'tool',
    'external_api': 'globe',
    'remote_agent': 'cloud',
    'agent': 'workflow',
    'mcp': 'mcp',
};

export class AgentCanvas extends PlatformElement {
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
        endNodeEls: { type: Array },
    };

    constructor() {
        super();
        this.agentConfig = null;
        this._editor = null;
        this.nodeConfigs = new Map();
        this.entryNodeId = null;
        this.nodeIdCounter = 1;
        this.contextMenu = null;
        this.connectionContextMenu = null;
        this._edgeLabelsManager = null;
        this.edgeConditions = new Map();
        this._pendingConnection = null;
        this._isImporting = false;
        this.endNodeEls = [];
        this._virtualConnectionsSvg = null;
        
        this._handleClickOutside = this._handleClickOutside.bind(this);
        this._handleNodeClick = this._handleNodeClick.bind(this);
        this._zoomIn = this._zoomIn.bind(this);
        this._zoomOut = this._zoomOut.bind(this);
        this._zoomReset = this._zoomReset.bind(this);
        this._setAsEntryPoint = this._setAsEntryPoint.bind(this);
        this._deleteNode = this._deleteNode.bind(this);
        this._duplicateNode = this._duplicateNode.bind(this);
        this._toggleBreakpoint = this._toggleBreakpoint.bind(this);
        
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
            console.error('[AgentCanvas] #drawflow-area container not found');
            return;
        }
        
        if (typeof Drawflow === 'undefined') {
            console.error('[AgentCanvas] Drawflow library not loaded');
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
        const snapshot = AgentsStore.getCurrentHistorySnapshot();
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
        
        AgentsStore.pushHistory(snapshot);
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
                    throw new Error(`[AgentCanvas] Node data not found for drawflowId: ${this.contextMenu.drawflowId}`);
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
                    console.warn(`[AgentCanvas] Node element not found for drawflowId=${drawflowId}`);
                    continue;
                }

                const agentNode = nodeEl.querySelector('.agent-node');
                if (!agentNode) {
                    console.warn(`[AgentCanvas] .agent-node not found in node-${drawflowId}`);
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

    _showEdgeConditionModal(fromId, toId, currentCondition = '') {
        const fromConfig = this.nodeConfigs.get(fromId.toString());
        const toConfig = this.nodeConfigs.get(toId.toString());
        
        if (!fromConfig || !toConfig) return;

        const variables = this._getAgentVariables();
        
        let modal = document.querySelector('edge-condition-modal');
        if (!modal) {
            modal = document.createElement('edge-condition-modal');
            document.body.appendChild(modal);
        }

        modal.fromNode = fromConfig.nodeId;
        modal.toNode = toConfig.nodeId;
        modal.condition = currentCondition;
        modal.variables = variables;

        const handleConditionSaved = (e) => {
            const { condition } = e.detail;
            const key = `${fromId}-${toId}`;
            
            if (condition) {
                this.edgeConditions.set(key, condition);
                if (this._edgeLabelsManager) {
                    this._edgeLabelsManager.add(fromId, toId, condition);
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

    _showConnectionContextMenu(x, y, fromId, toId, currentCondition) {
        this.connectionContextMenu = {
            x,
            y,
            fromId,
            toId,
            currentCondition
        };
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
        if (!this.agentConfig) {
            return [];
        }
        if (!this.agentConfig.variables) {
            return [];
        }
        if (Array.isArray(this.agentConfig.variables)) {
            return this.agentConfig.variables.map(v => v.name || v);
        }
        if (typeof this.agentConfig.variables === 'object') {
            return Object.keys(this.agentConfig.variables);
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

    _createNodeHtmlSync(nodeId, nodeType, isEntry = false, isInherited = false) {
        const bgColor = nodeType.color + '20';
        const entryBadge = isEntry 
            ? '<div class="agent-node-entry-badge">▶</div>' 
            : '';
        const inheritedBadge = isInherited
            ? '<div class="agent-node-inherited-badge" title="Inherited from base"><svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 3v10M8 3l-3 3M8 3l3 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></div>'
            : '';
        
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
            </div>
        `;
    }

    async _preloadIcons(nodes) {
        const iconNames = [...new Set(
            Object.values(nodes).map(n => {
                const iconName = NODE_TYPE_ICON_NAMES[n.type];
                if (!iconName) throw new Error(`No icon mapping for type: ${n.type}`);
                return iconName;
            })
        )];
        
        await this.icon.preload(iconNames);
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
            throw new Error('[AgentCanvas] Editor export failed');
        }
        if (!exported.drawflow) {
            throw new Error('[AgentCanvas] Drawflow data missing');
        }
        if (!exported.drawflow.Home) {
            throw new Error('[AgentCanvas] Home data missing');
        }
        if (!exported.drawflow.Home.data) {
            throw new Error('[AgentCanvas] Home.data missing');
        }

        const homeData = exported.drawflow.Home.data;
        
        this.endNodeEls.forEach(el => el.remove());
        this.endNodeEls = [];
        
        this._ensureVirtualConnectionsSvg();
        
        if (this._virtualConnectionsSvg) {
            this._virtualConnectionsSvg.innerHTML = '';
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
        
        endNodeIds.forEach((drawflowId, index) => {
            const nodeData = homeData[drawflowId];
            if (!nodeData) return;
            
            const endNodeEl = this._createEndNode(index);
            if (!endNodeEl) return;
            
            this.endNodeEls.push(endNodeEl);
            
            const nodeEl = this.querySelector(`#node-${drawflowId}`);
            if (nodeEl) {
                const nodeWidth = nodeEl.offsetWidth || 180;
                const endX = nodeData.pos_x + nodeWidth + 60;
                const endY = nodeData.pos_y + 10;
                
                endNodeEl.style.left = `${endX}px`;
                endNodeEl.style.top = `${endY}px`;
                
                const nodeRight = nodeData.pos_x + nodeWidth;
                const nodeCenterY = nodeData.pos_y + 35;
                const endLeft = endX;
                const endCenterY = endY + 16;
                
                this._drawVirtualConnection(nodeRight, nodeCenterY, endLeft, endCenterY);
            }
        });
    }

    _ensureVirtualConnectionsSvg() {
        const drawflowArea = this.querySelector('#drawflow-area');
        if (!drawflowArea) return;
        
        const drawflowEl = drawflowArea.querySelector('.drawflow');
        if (!drawflowEl) return;
        
        if (!this._virtualConnectionsSvg) {
            this._virtualConnectionsSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            this._virtualConnectionsSvg.setAttribute('class', 'virtual-connections-svg');
            this._virtualConnectionsSvg.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 10000px;
                height: 10000px;
                pointer-events: none;
                z-index: 1;
                overflow: visible;
            `;
            drawflowEl.appendChild(this._virtualConnectionsSvg);
        }
    }

    _createEndNode(index) {
        const drawflowArea = this.querySelector('#drawflow-area');
        if (!drawflowArea) return null;
        
        const drawflowEl = drawflowArea.querySelector('.drawflow');
        if (!drawflowEl) return null;
        
        const endNode = document.createElement('div');
        endNode.className = 'virtual-end-node';
        endNode.style.cssText = `
            position: absolute;
            width: 80px;
            height: 32px;
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.25) 100%);
            border: 2px solid rgba(16, 185, 129, 0.4);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 600;
            color: rgba(16, 185, 129, 0.9);
            pointer-events: none;
            z-index: 3;
        `;
        endNode.textContent = 'END';
        
        drawflowEl.appendChild(endNode);
        return endNode;
    }

    _drawVirtualConnection(x1, y1, x2, y2) {
        if (!this._virtualConnectionsSvg) return;
        
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        
        const midX = (x1 + x2) / 2;
        const d = `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`;
        
        path.setAttribute('d', d);
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke', 'rgba(16, 185, 129, 0.5)');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('stroke-dasharray', '6 4');
        path.setAttribute('stroke-linecap', 'round');
        
        this._virtualConnectionsSvg.appendChild(path);
    }

    _getNodeColor(type) {
        const colors = {
            'react_node': '#f59e0b',
            'function': '#8b5cf6',
            'tool': '#10b981',
            'external_api': '#06b6d4',
            'remote_agent': '#3b82f6',
            'agent': '#ec4899',
            'mcp': '#14b8a6',
        };
        
        const color = colors[type];
        if (!color) throw new Error(`No color mapping for node type: ${type}`);
        
        return color;
    }

    getData() {
        const exported = this._editor.export();
        if (!exported) {
            throw new Error('[AgentCanvas] Editor export failed');
        }
        if (!exported.drawflow) {
            throw new Error('[AgentCanvas] Drawflow data missing');
        }
        if (!exported.drawflow.Home) {
            throw new Error('[AgentCanvas] Home data missing');
        }
        if (!exported.drawflow.Home.data) {
            throw new Error('[AgentCanvas] Home.data missing');
        }

        const homeData = exported.drawflow.Home.data;
        
        const nodes = {};
        const edges = [];

        for (const [drawflowId, nodeData] of Object.entries(homeData)) {
            const savedConfig = this.nodeConfigs.get(drawflowId);
            if (!savedConfig) {
                throw new Error(`[AgentCanvas] Node config not found for drawflowId: ${drawflowId}`);
            }

            const nodeId = savedConfig.nodeId;
            if (!nodeId) {
                throw new Error(`[AgentCanvas] nodeId missing in config for drawflowId: ${drawflowId}`);
            }

            const nodeType = savedConfig.type;
            if (!nodeType) {
                throw new Error(`[AgentCanvas] Node type missing for nodeId: ${nodeId}`);
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
                        throw new Error(`[AgentCanvas] Target node config not found for drawflowId: ${targetDrawflowId}`);
                    }

                    const targetNodeId = targetConfig.nodeId;
                    if (!targetNodeId) {
                        throw new Error(`[AgentCanvas] Target nodeId missing for drawflowId: ${targetDrawflowId}`);
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

        return { nodes, edges, entry };
    }

    updateNodeConfig(nodeId, config) {
        console.log('[AgentCanvas] updateNodeConfig called:', { nodeId, config });
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                console.log('[AgentCanvas] Found node, old config:', nodeConfig.config);
                // Полностью заменяем config, а не делаем merge
                nodeConfig.config = config;
                console.log('[AgentCanvas] Updated config:', nodeConfig.config);
                break;
            }
        }
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
        console.log(`[AgentCanvas] setNodeStatus: nodeId="${nodeId}", status="${status}"`);
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                if (nodeEl) {
                    nodeEl.classList.remove('node-running', 'node-completed', 'node-error');
                    
                    if (status && status !== 'null') {
                        nodeEl.classList.add(`node-${status}`);
                        console.log(`[AgentCanvas] Added class "node-${status}"`);
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
        console.log(`[AgentCanvas] showNodeError: nodeId="${nodeId}", error="${errorMessage}"`);
        
        for (const [drawflowId, nodeConfig] of this.nodeConfigs.entries()) {
            if (nodeConfig.nodeId === nodeId) {
                const nodeEl = this.querySelector(`#node-${drawflowId}`);
                console.log(`[AgentCanvas] Found node element:`, nodeEl);
                
                if (nodeEl) {
                    // Удаляем старый tooltip если есть
                    this.clearNodeError(nodeId);
                    
                    // Создаем контейнер для tooltips если его нет
                    let tooltipContainer = document.querySelector('.node-error-tooltips-container');
                    console.log(`[AgentCanvas] Existing container:`, tooltipContainer);
                    
                    if (!tooltipContainer) {
                        tooltipContainer = document.createElement('div');
                        tooltipContainer.className = 'node-error-tooltips-container';
                        document.body.appendChild(tooltipContainer);
                        console.log(`[AgentCanvas] Container appended to body`);
                    }
                    
                    // Получаем абсолютную позицию ноды на странице
                    const nodeRect = nodeEl.getBoundingClientRect();
                    
                    console.log(`[AgentCanvas] Node rect:`, nodeRect);
                    
                    const errorTooltip = document.createElement('div');
                    errorTooltip.className = 'node-error-tooltip';
                    errorTooltip.dataset.nodeId = nodeId;
                    errorTooltip.dataset.drawflowId = drawflowId;
                    
                    // Позиционируем fixed относительно viewport
                    const topPosition = nodeRect.top - 12;
                    const leftPosition = nodeRect.left + nodeRect.width / 2;
                    
                    console.log(`[AgentCanvas] Tooltip position: top=${topPosition}, left=${leftPosition}`);
                    
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
                                console.error('[AgentCanvas] Ошибка копирования:', err);
                                this._fallbackCopyTextToClipboard(errorMessage, copyBtn);
                            });
                        } else {
                            this._fallbackCopyTextToClipboard(errorMessage, copyBtn);
                        }
                    });
                    
                    closeBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        console.log('[AgentCanvas] Close button clicked');
                        this._removeTooltipWithAnimation(errorTooltip);
                    });
                    
                    tooltipContainer.appendChild(errorTooltip);
                    console.log(`[AgentCanvas] Tooltip appended:`, errorTooltip);
                    console.log(`[AgentCanvas] Tooltip computed style:`, getComputedStyle(errorTooltip));
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
                console.error('[AgentCanvas] Fallback: не удалось скопировать');
            }
        } catch (err) {
            console.error('[AgentCanvas] Fallback: ошибка копирования', err);
        }
        
        document.body.removeChild(textArea);
    }

    async loadData(data, inherited = null) {
        console.log('[AgentCanvas] loadData called with:', { 
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
            console.warn('[AgentCanvas] Import already in progress, skipping duplicate loadData call');
            return;
        }
        
        console.log('[AgentCanvas] Clearing editor...');
        console.log('[AgentCanvas] Editor state before clear:', {
            drawflow: this._editor.drawflow,
            nodeCount: Object.keys(this._editor.drawflow?.drawflow?.Home?.data || {}).length
        });
        
        console.log('[AgentCanvas] Setting _isImporting = true');
        this._isImporting = true;
        
        this._editor.clear();
        
        console.log('[AgentCanvas] Editor state after clear:', {
            drawflow: this._editor.drawflow,
            nodeCount: Object.keys(this._editor.drawflow?.drawflow?.Home?.data || {}).length
        });
        
        console.log('[AgentCanvas] Editor cleared, adding nodes...');
        this.nodeConfigs.clear();
        this.entryNodeId = null;
        this.edgeConditions.clear();
        if (this._edgeLabelsManager) {
            this._edgeLabelsManager.clear();
        }
        this.nodeIdCounter = 1;
        
        if (this._edgeLabelsManager) {
            this._edgeLabelsManager._setupContainer();
        }
        this._virtualConnectionsSvg = null;

        const { nodes, edges = [], entry } = data;
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
            
            const nodeHtml = this._createNodeHtmlSync(nodeId, nodeType, isEntry, isInherited);
            
            console.log('[AgentCanvas] Adding node:', {
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
                console.warn(`[AgentCanvas] Skipping invalid edge: ${edge.from} -> ${edge.to} (fromId: ${fromId}, toId: ${toId})`);
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
        console.log('[AgentCanvas] Import completed successfully');
        
        for (const edge of edges) {
            if (edge.condition) {
                const fromId = nodePositions.get(edge.from);
                const toId = nodePositions.get(edge.to);
                if (fromId && toId) {
                    this._edgeLabelsManager?.add(fromId, toId, edge.condition);
                }
            }
        }
        
        this._updateVirtualNodes();
    }

    _zoomIn() {
        if (!this._editor) {
            throw new Error('[AgentCanvas] Editor not initialized');
        }
        this._editor.zoom_in();
    }

    _zoomOut() {
        if (!this._editor) {
            throw new Error('[AgentCanvas] Editor not initialized');
        }
        this._editor.zoom_out();
    }

    _zoomReset() {
        if (!this._editor) {
            throw new Error('[AgentCanvas] Editor not initialized');
        }
        this._editor.zoom_reset();
    }

    render() {
        return renderCanvas(this);
    }
}

customElements.define('agent-canvas', AgentCanvas);



/**
 * EdgeLabelsManager - управление отображением условий на линиях связи
 */
export class EdgeLabelsManager {
    constructor(canvasElement, editor, onLabelClick, host) {
        this.canvasElement = canvasElement;
        this.editor = editor;
        this.onLabelClick = onLabelClick;
        this._host = host;
        this.labels = new Map();
        
        this._setupContainer();
        this._setupListeners();
    }

    _setupContainer() {
        const drawflowEl = this.canvasElement.querySelector('.drawflow');
        if (!drawflowEl) {
            this.container = null;
            return;
        }
        
        let container = drawflowEl.querySelector('.edge-labels-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'edge-labels-container';
            container.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                pointer-events: none;
                z-index: 2;
            `;
            drawflowEl.appendChild(container);
        }
        this.container = container;
    }

    _setupListeners() {
        this.editor.on('zoom', () => this.updatePositions());
        this.editor.on('translate', () => this.updatePositions());
        this.editor.on('nodeMoved', () => this.updatePositions());
    }

    add(fromId, toId, condition) {
        if (!condition) return;
        
        if (!this.container) {
            this._setupContainer();
            if (!this.container) return;
        }
        
        const key = `${fromId}-${toId}`;
        
        let label = this.labels.get(key);
        if (!label) {
            label = document.createElement('div');
            label.className = 'edge-label';
            label.dataset.from = fromId;
            label.dataset.to = toId;
            label.style.pointerEvents = 'auto';
            
            label.addEventListener('click', (e) => {
                e.stopPropagation();
                if (this.onLabelClick) {
                    this.onLabelClick(fromId, toId, condition);
                }
            });
            
            this.container.appendChild(label);
            this.labels.set(key, label);
        }
        
        label.textContent = condition;
        label.title = this._host.i18n.t('edge_labels.condition_title', { condition });
        
        this._updateLabelPosition(fromId, toId);
    }

    remove(fromId, toId) {
        const key = `${fromId}-${toId}`;
        const label = this.labels.get(key);
        
        if (label) {
            label.remove();
            this.labels.delete(key);
        }
    }

    update(fromId, toId, condition) {
        if (!condition) {
            this.remove(fromId, toId);
            return;
        }
        
        const key = `${fromId}-${toId}`;
        const label = this.labels.get(key);
        
        if (label) {
            label.textContent = condition;
            label.title = this._host.i18n.t('edge_labels.condition_title', { condition });
            this._updateLabelPosition(fromId, toId);
        } else {
            this.add(fromId, toId, condition);
        }
    }

    updatePositions() {
        for (const [key] of this.labels) {
            const [fromId, toId] = key.split('-');
            this._updateLabelPosition(fromId, toId);
        }
    }

    _updateLabelPosition(fromId, toId) {
        const label = this.labels.get(`${fromId}-${toId}`);
        if (!label) return;
        
        const position = this._getLabelPosition(fromId, toId);
        if (position) {
            label.style.left = `${position.x}px`;
            label.style.top = `${position.y}px`;
            label.style.transform = `translate(-50%, -50%) rotate(${position.angle}deg)`;
        }
    }

    _getLabelPosition(fromId, toId) {
        const drawflowEl = this.canvasElement.querySelector('.drawflow');
        if (!drawflowEl) return null;
        
        const fromNode = drawflowEl.querySelector(`#node-${fromId}`);
        const toNode = drawflowEl.querySelector(`#node-${toId}`);
        
        if (!fromNode || !toNode) return null;
        
        const fromData = this.editor.getNodeFromId(parseInt(fromId));
        const toData = this.editor.getNodeFromId(parseInt(toId));
        
        if (!fromData || !toData) return null;
        
        const fromWidth = fromNode.offsetWidth || 180;
        const fromHeight = fromNode.offsetHeight || 70;
        const toWidth = toNode.offsetWidth || 180;
        const toHeight = toNode.offsetHeight || 70;
        
        const fromX = fromData.pos_x + fromWidth;
        const fromY = fromData.pos_y + fromHeight / 2;
        const toX = toData.pos_x;
        const toY = toData.pos_y + toHeight / 2;
        
        const midX = (fromX + toX) / 2;
        const midY = (fromY + toY) / 2;
        
        const angle = Math.atan2(toY - fromY, toX - fromX) * (180 / Math.PI);
        
        return {
            x: midX,
            y: midY,
            angle: angle,
        };
    }

    clear() {
        for (const label of this.labels.values()) {
            label.remove();
        }
        this.labels.clear();
    }

    getCondition(fromId, toId) {
        const key = `${fromId}-${toId}`;
        const label = this.labels.get(key);
        return label ? label.textContent : '';
    }

    hasLabel(fromId, toId) {
        const key = `${fromId}-${toId}`;
        return this.labels.has(key);
    }
}


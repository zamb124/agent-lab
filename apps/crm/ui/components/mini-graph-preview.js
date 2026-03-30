import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CRMStore } from '../store/crm.store.js';

function _resolveNodeColor(node) {
    if (node.access === false) {
        return '#7f7f8f';
    }
    const entityType = typeof node.entity_type === 'string' ? node.entity_type.trim() : '';
    if (!entityType) {
        return '#bca8ff';
    }
    const entityTypes = CRMStore.state.entities.entityTypes;
    if (!Array.isArray(entityTypes)) {
        return '#bca8ff';
    }
    const match = entityTypes.find((t) => t.type_id === entityType);
    if (!match || typeof match.color !== 'string' || !match.color.trim()) {
        return '#bca8ff';
    }
    return match.color.trim();
}

function _truncate(text, max) {
    if (typeof text !== 'string') {
        return '';
    }
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function _createLabelSprite(text, color, fontSize) {
    if (!window.THREE || typeof window.THREE.CanvasTexture !== 'function') {
        throw new Error('THREE.js is not available');
    }
    const label = _truncate(text, 20);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) {
        throw new Error('Cannot create canvas 2d context');
    }
    ctx.font = `700 ${fontSize}px Inter, sans-serif`;
    const tw = Math.max(16, Math.ceil(ctx.measureText(label).width));
    canvas.width = tw + 14;
    canvas.height = fontSize + 10;
    ctx.font = `700 ${fontSize}px Inter, sans-serif`;
    ctx.fillStyle = color;
    ctx.textBaseline = 'middle';
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    ctx.shadowColor = isDark ? 'rgba(5,7,12,0.9)' : 'rgba(255,255,255,0.9)';
    ctx.shadowBlur = 4;
    ctx.strokeStyle = isDark ? 'rgba(5,7,12,0.85)' : 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 3;
    ctx.strokeText(label, 6, canvas.height / 2);
    ctx.fillText(label, 6, canvas.height / 2);
    const texture = new window.THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    const material = new window.THREE.SpriteMaterial({
        map: texture,
        transparent: true,
        depthTest: false,
        depthWrite: false,
    });
    const sprite = new window.THREE.Sprite(material);
    sprite.scale.set(canvas.width * 0.06, canvas.height * 0.06, 1);
    sprite.renderOrder = 999;
    return sprite;
}

export class MiniGraphPreview extends PlatformElement {
    static properties = {
        entityId: { type: String },
        maxDepth: { type: Number },
        width: { type: String },
        height: { type: String },
        _loading: { state: true },
        _error: { state: true },
        _graphNodes: { state: true },
        _graphEdges: { state: true },
    };

    static styles = [
        ...PlatformElement.styles,
        css`
            :host {
                display: block;
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid var(--glass-border-subtle);
            }
            .mini-canvas {
                width: 100%;
                height: 100%;
                position: relative;
            }
            .mini-empty {
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100%;
                color: var(--text-tertiary);
                font-size: 12px;
            }
        `,
    ];

    constructor() {
        super();
        this.entityId = '';
        this.maxDepth = 2;
        this.width = '100%';
        this.height = '240px';
        this._loading = false;
        this._error = '';
        this._graphNodes = [];
        this._graphEdges = [];
        this._graphInstance = null;
    }

    firstUpdated() {
        if (this.entityId) {
            this._loadAndRender();
        }
    }

    updated(changed) {
        if (changed.has('entityId') && this.entityId) {
            this._loadAndRender();
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._destroyGraph();
    }

    async _loadAndRender() {
        if (!this.entityId) {
            return;
        }
        this._loading = true;
        this._error = '';
        this._destroyGraph();
        const response = await this.crmApi.getInfluenceGraph(this.entityId, { max_depth: this.maxDepth });
        const nodes = response.nodes || [];
        const edges = response.edges || [];
        this._graphNodes = nodes;
        this._graphEdges = edges;
        this._loading = false;
        if (nodes.length === 0) {
            return;
        }
        await this.updateComplete;
        this._initGraph();
    }

    _initGraph() {
        const factory = window.ForceGraph3D;
        if (typeof factory !== 'function') {
            throw new Error('ForceGraph3D is not available in window');
        }
        const container = this.renderRoot?.querySelector('.mini-canvas');
        if (!container) {
            throw new Error('Mini graph canvas container not found');
        }
        const canvasBg = getComputedStyle(document.documentElement)
            .getPropertyValue('--bg-secondary').trim() || '#1a1a2e';
        const labelColor = getComputedStyle(document.documentElement)
            .getPropertyValue('--text-primary').trim() || '#f0f4ff';

        const sceneNodes = this._graphNodes.map((node) => {
            const id = node.entity_id || node.id;
            const isCenter = id === this.entityId;
            return {
                ...node,
                id,
                name: node.name || node.label || id,
                color: _resolveNodeColor(node),
                size: isCenter ? 2.4 : 1.2,
                level: isCenter ? 0 : (node.level ?? 1),
            };
        });
        const sceneLinks = this._graphEdges.map((edge) => ({
            source: edge.source_id || edge.source_entity_id || edge.source,
            target: edge.target_id || edge.target_entity_id || edge.target,
        }));

        this._graphInstance = factory()(container)
            .backgroundColor(canvasBg)
            .width(container.clientWidth)
            .height(container.clientHeight)
            .showNavInfo(false)
            .cooldownTicks(60)
            .warmupTicks(40)
            .nodeRelSize(4)
            .nodeColor((n) => n.color)
            .nodeVal((n) => n.size)
            .nodeLabel(() => '')
            .nodeThreeObject((node) => {
                const sprite = _createLabelSprite(node.name || node.id, labelColor, 16);
                sprite.position.set(0, (node.size || 1) * 2, 0);
                return sprite;
            })
            .nodeThreeObjectExtend(true)
            .linkColor(() => '#9ba3bf')
            .linkWidth(0.6)
            .linkOpacity(0.4)
            .enableNodeDrag(true)
            .onNodeClick((node) => {
                this.emit('entity-open', { entityId: node.id });
            })
            .onNodeDragEnd((node) => {
                node.fx = node.x;
                node.fy = node.y;
                node.fz = 0;
            })
            .onEngineStop(() => {
                if (!this._graphInstance) {
                    return;
                }
                this._flattenZ();
            })
            .graphData({ nodes: sceneNodes, links: sceneLinks });

        // Фиксируем z-координаты при каждом тике симуляции
        this._graphInstance.d3Force('flatZ', () => {
            const gd = this._graphInstance.graphData();
            if (!gd?.nodes) {
                return;
            }
            gd.nodes.forEach((n) => { n.z = 0; n.fz = 0; });
        });

        // Камера сверху вниз по z-оси
        requestAnimationFrame(() => {
            if (!this._graphInstance) {
                return;
            }
            const camera = this._graphInstance.camera();
            camera.position.set(0, 0, 280);
            camera.lookAt(0, 0, 0);
            const controls = this._graphInstance.controls();
            if (controls) {
                controls.enableRotate = false;
            }
        });
    }

    _flattenZ() {
        if (!this._graphInstance) {
            return;
        }
        const gd = this._graphInstance.graphData();
        if (!gd?.nodes) {
            return;
        }
        gd.nodes.forEach((n) => { n.z = 0; n.fz = 0; });
    }

    _destroyGraph() {
        if (this._graphInstance) {
            this._graphInstance._destructor?.();
            this._graphInstance = null;
        }
    }

    render() {
        const hostStyle = `width:${this.width};height:${this.height}`;

        if (this._loading) {
            return html`<div style="${hostStyle}" class="mini-empty">Загрузка графа...</div>`;
        }
        if (this._error) {
            return html`<div style="${hostStyle}" class="mini-empty">${this._error}</div>`;
        }
        if (!this._loading && this._graphNodes.length === 0 && this.entityId) {
            return html`<div style="${hostStyle}" class="mini-empty">Нет связей</div>`;
        }
        return html`<div class="mini-canvas" style="${hostStyle}"></div>`;
    }
}

customElements.define('mini-graph-preview', MiniGraphPreview);

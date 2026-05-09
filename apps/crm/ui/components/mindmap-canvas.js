/**
 * Mind map — SVG: дерево от корня с Bézier-связями, палитра типов.
 *
 * Полноэкранный режим: pan/zoom внутри `.viewport` с `preserveAspectRatio xMidYMid meet`.
 *
 * Compact-режим (`<crm-mindmap-canvas compact>` — мини-превью на странице сущности): SVG
 * подбирает размер по соотношению естественной высоты контента (`viewportWidth * vbH / vbW`,
 * единица viewBox = пиксель по горизонтали) к высоте `.viewport` с учётом множителя
 * `compactZoom` (диапазон 0.5..3, по умолчанию 1):
 * - при `compactZoom === 1` и контенте, влезающем по высоте — SVG на 100% `.viewport`,
 *   выравнивание `xMidYMid meet`, скролла нет (короткое дерево заполняет контейнер);
 * - при `compactZoom === 1` и контенте выше контейнера — SVG получает явную пиксельную
 *   высоту `naturalH`, выравнивание `xMidYMin meet`, вертикальный скролл `.viewport`;
 * - при `compactZoom !== 1` — SVG получает явные пиксельные `width = viewportW * z` и
 *   `height = naturalH * z`, выравнивание `xMidYMin meet`; `.viewport` прокручивается
 *   и по горизонтали, и по вертикали.
 *
 * Управление масштабом в compact-режиме — снаружи через property `compactZoom`. Колесо мыши
 * с зажатым Ctrl/Meta эмитит `compact-zoom-change` { value } (обычное колесо — нативный скролл
 * `.viewport`).
 *
 * Вход: graphNodes, graphEdges, rootEntityId, entityTypeColors / entityTypeIcons (plain object),
 * defaultAccent; левый клик — `node-click` (на стороне workspace: корень + пересборка);
 * двойной клик — `node-dblclick`; ПКМ — `node-contextmenu` { node, screenX, screenY }.
 */

import { html, svg, css, unsafeCSS } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { readMindmapView, writeMindmapView } from '../utils/mindmap-view-preference.js';

const LEVEL_GAP = 340;
const LEAF_BLOCK = 58;
const V_GAP_SIBLINGS = 36;
const ROOT_CENTER_FILL = '#64748b';
const ICON_SLOT = 34;
const NODE_H = 44;
/** Скругление ноды в user space SVG и в CSS foreignObject; обводка рисуется отдельным inset-rect. */
const MM_NODE_CORNER_RX = 12;

const BRANCH_PALETTE = [
    '#22c55e',
    '#eab308',
    '#f97316',
    '#ef4444',
    '#a855f7',
    '#06b6d4',
    '#ec4899',
    '#84cc16',
];

/**
 * @param {unknown} edge
 * @returns {{ source: string, target: string } | null}
 */
function _edgeEndpoints(edge) {
    if (!edge || typeof edge !== 'object') {
        return null;
    }
    const sourceRaw = edge.source_id !== undefined ? edge.source_id : edge.source_entity_id;
    const targetRaw = edge.target_id !== undefined ? edge.target_id : edge.target_entity_id;
    const source = typeof sourceRaw === 'string' ? sourceRaw.trim() : '';
    const target = typeof targetRaw === 'string' ? targetRaw.trim() : '';
    if (source.length === 0 || target.length === 0) {
        return null;
    }
    return { source, target };
}

/**
 * @param {string} rootId
 * @param {Array<unknown>} edges
 * @returns {Map<string, string[]>}
 */
function _buildAdjacency(rootId, edges) {
    const adj = new Map();
    const ensure = (id) => {
        if (!adj.has(id)) {
            adj.set(id, []);
        }
    };
    ensure(rootId);
    for (const raw of edges) {
        const ep = _edgeEndpoints(raw);
        if (ep === null) {
            continue;
        }
        ensure(ep.source);
        ensure(ep.target);
        adj.get(ep.source).push(ep.target);
        adj.get(ep.target).push(ep.source);
    }
    return adj;
}

/**
 * @param {string} rootId
 * @param {Map<string, string[]>} adj
 * @returns {{ treeChildren: Map<string, string[]>, reachable: Set<string> }}
 */
function _bfsTree(rootId, adj) {
    const treeChildren = new Map();
    const reachable = new Set();
    const queue = [rootId];
    reachable.add(rootId);
    while (queue.length > 0) {
        const u = queue.shift();
        const nbrs = adj.get(u);
        if (!nbrs) {
            continue;
        }
        for (const v of nbrs) {
            if (reachable.has(v)) {
                continue;
            }
            reachable.add(v);
            if (!treeChildren.has(u)) {
                treeChildren.set(u, []);
            }
            treeChildren.get(u).push(v);
            queue.push(v);
        }
    }
    return { treeChildren, reachable };
}

/**
 * @param {Map<string, string[]>} treeChildren
 * @param {string} rootId
 * @returns {Map<string, number>}
 */
function _computeSubtreeBlockHeights(treeChildren, rootId) {
    const heights = new Map();
    function walk(id) {
        const kids = treeChildren.get(id);
        if (!kids || kids.length === 0) {
            heights.set(id, LEAF_BLOCK);
            return LEAF_BLOCK;
        }
        let sum = 0;
        for (const c of kids) {
            sum += walk(c);
        }
        sum += (kids.length - 1) * V_GAP_SIBLINGS;
        heights.set(id, sum);
        return sum;
    }
    walk(rootId);
    return heights;
}

/**
 * @param {Map<string, { label: string, entity_type: string, access?: boolean }>} labelMap
 * @param {string} id
 * @returns {string}
 */
function _labelFromMap(labelMap, id) {
    const row = labelMap.get(id);
    if (row && typeof row.label === 'string' && row.label.length > 0) {
        return row.label;
    }
    return id;
}

/**
 * @param {string} label
 * @returns {number}
 */
function _nodeWidthPx(label) {
    const text = typeof label === 'string' ? label : '';
    const len = text.length > 48 ? 48 : text.length;
    const textW = Math.ceil(len * 7.4);
    const width = ICON_SLOT + 12 + textW + 20;
    return Math.min(340, Math.max(148, width));
}

/**
 * @param {string} nodeId
 * @param {number} depth
 * @param {number} yTop
 * @param {Map<string, string[]>} treeChildren
 * @param {Map<string, number>} heights
 * @param {Map<string, { label: string, entity_type: string, access?: boolean }>} labelMap
 * @param {Map<string, { x: number, y: number, depth: number, w: number, h: number }>} positions
 */
function _layoutSubtree(nodeId, depth, yTop, treeChildren, heights, labelMap, positions) {
    const label = _labelFromMap(labelMap, nodeId);
    const w = _nodeWidthPx(label);
    const h = NODE_H;
    const kids = treeChildren.get(nodeId);
    if (!kids || kids.length === 0) {
        const cy = yTop + LEAF_BLOCK / 2;
        positions.set(nodeId, { x: depth * LEVEL_GAP, y: cy, depth, w, h });
        return;
    }
    let cursor = yTop;
    for (const c of kids) {
        const block = heights.get(c);
        if (typeof block !== 'number') {
            throw new Error('Mindmap layout: missing subtree height');
        }
        _layoutSubtree(c, depth + 1, cursor, treeChildren, heights, labelMap, positions);
        cursor += block + V_GAP_SIBLINGS;
    }
    const firstId = kids[0];
    const lastId = kids[kids.length - 1];
    const firstPos = positions.get(firstId);
    const lastPos = positions.get(lastId);
    if (!firstPos || !lastPos) {
        throw new Error('Mindmap layout: child position missing');
    }
    const py = (firstPos.y + lastPos.y) / 2;
    positions.set(nodeId, { x: depth * LEVEL_GAP, y: py, depth, w, h });
}

/**
 * @param {number} minX
 * @param {number} minY
 * @param {number} maxX
 * @param {number} maxY
 * @param {number} pad
 * @returns {{ vbX: number, vbY: number, vbW: number, vbH: number }}
 */
function _finalizeViewBox(minX, minY, maxX, maxY, pad) {
    const finite =
        Number.isFinite(minX)
        && Number.isFinite(minY)
        && Number.isFinite(maxX)
        && Number.isFinite(maxY);
    if (!finite) {
        return { vbX: 0, vbY: 0, vbW: 1200, vbH: 800 };
    }
    const spanX = maxX - minX;
    const spanY = maxY - minY;
    const MIN_W = 400;
    const MIN_H = 320;
    const vbW = Math.max(MIN_W, spanX + pad * 2);
    const vbH = Math.max(MIN_H, spanY + pad * 2);
    const vbX = minX - pad - (vbW - spanX - pad * 2) / 2;
    const vbY = minY - pad - (vbH - spanY - pad * 2) / 2;
    return { vbX, vbY, vbW, vbH };
}

/**
 * Контрольные точки той же кубики, что и `_curveBetween` ниже.
 *
 * @param {{ x: number, y: number, w: number, h: number }} pa
 * @param {{ x: number, y: number, w: number, h: number }} pb
 */
function _mindmapBezierControlPoints(pa, pb) {
    const x1 = pa.x + pa.w / 2;
    const y1 = pa.y;
    const x2 = pb.x - pb.w / 2;
    const y2 = pb.y;
    const dx = Math.max(48, (x2 - x1) * 0.45);
    return {
        p0: { x: x1, y: y1 },
        p1: { x: x1 + dx, y: y1 },
        p2: { x: x2 - dx, y: y2 },
        p3: { x: x2, y: y2 },
    };
}

/**
 * @param {number} t
 * @param {{ x: number, y: number }} p0
 * @param {{ x: number, y: number }} p1
 * @param {{ x: number, y: number }} p2
 * @param {{ x: number, y: number }} p3
 */
function _cubicBezierPoint(t, p0, p1, p2, p3) {
    const mt = 1 - t;
    const mt2 = mt * mt;
    const mt3 = mt2 * mt;
    const t2 = t * t;
    const t3 = t2 * t;
    const x = mt3 * p0.x + 3 * mt2 * t * p1.x + 3 * mt * t2 * p2.x + t3 * p3.x;
    const y = mt3 * p0.y + 3 * mt2 * t * p1.y + 3 * mt * t2 * p2.y + t3 * p3.y;
    return { x, y };
}

/**
 * @param {number} t
 */
function _cubicBezierTangent(t, p0, p1, p2, p3) {
    const mt = 1 - t;
    const t2 = t * t;
    const mt2 = mt * mt;
    const tx = 3 * mt2 * (p1.x - p0.x) + 6 * mt * t * (p2.x - p1.x) + 3 * t2 * (p3.x - p2.x);
    const ty = 3 * mt2 * (p1.y - p0.y) + 6 * mt * t * (p2.y - p1.y) + 3 * t2 * (p3.y - p2.y);
    return { x: tx, y: ty };
}

/**
 * Угол в градусах для читаемой горизонтальной подписи вдоль касательной.
 *
 * @param {number} tx
 * @param {number} ty
 */
function _readableTangentAngleDeg(tx, ty) {
    let deg = (Math.atan2(ty, tx) * 180) / Math.PI;
    if (deg > 90) deg -= 180;
    if (deg < -90) deg += 180;
    return deg;
}

/**
 * @param {unknown[]} edges
 * @param {string} a
 * @param {string} b
 */
function _relationshipTypeForUndirectedPair(edges, a, b) {
    if (!Array.isArray(edges)) {
        return '';
    }
    for (const raw of edges) {
        const ep = _edgeEndpoints(raw);
        if (ep === null) {
            continue;
        }
        if ((ep.source === a && ep.target === b) || (ep.source === b && ep.target === a)) {
            const rt = raw.relationship_type;
            return typeof rt === 'string' ? rt.trim() : '';
        }
    }
    return '';
}

export class CRMMindmapCanvas extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        graphNodes: { type: Array },
        graphEdges: { type: Array },
        rootEntityId: { type: String },
        entityTypeColors: { type: Object },
        entityTypeIcons: { type: Object },
        defaultAccent: { type: String },
        fitNonce: { type: Number },
        compact: { type: Boolean, reflect: true },
        compactZoom: { type: Number },
        relationshipTypeLabels: { type: Object },
        selectedNodeId: { type: String, attribute: 'selected-node-id' },
        highlightNodeIds: { type: Array },
        /** Смещение в единицах viewBox (совместимо с wheel/pan). */
        _panUx: { state: true },
        _panUy: { state: true },
        _zoom: { state: true },
        _dragging: { state: true },
        _dragStart: { state: true },
        _viewportWidthPx: { state: true },
        _viewportHeightPx: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
                height: 100%;
                min-height: 200px;
                background: var(--bg-secondary);
                touch-action: none;
            }
            .viewport {
                position: relative;
                width: 100%;
                height: 100%;
                overflow: hidden;
            }
            :host([compact]) .viewport {
                overflow: auto;
                touch-action: pan-x pan-y;
                overscroll-behavior: contain;
            }
            .scene {
                width: 100%;
                height: 100%;
            }
            :host([compact]) .scene {
                width: 100%;
                height: auto;
                min-height: 100%;
            }
            svg.mindmap-svg {
                display: block;
                width: 100%;
                height: 100%;
            }
            :host([compact]) svg.mindmap-svg {
                height: 100%;
                min-height: 220px;
            }
            .edge-path {
                fill: none;
                stroke-linecap: round;
                opacity: 0.92;
            }
            .mm-edge-label {
                font-family: var(--font-sans, system-ui);
                font-size: 11px;
                font-weight: 600;
                fill: var(--text-secondary);
                paint-order: stroke fill;
                stroke: var(--bg-secondary);
                stroke-width: 3px;
                stroke-linejoin: round;
                pointer-events: none;
            }
            .node-hit {
                cursor: grab;
            }
            .node-hit:active {
                cursor: grabbing;
            }
            foreignObject.mm-fo {
                overflow: visible;
            }
            .mm-node-inner {
                display: flex;
                align-items: center;
                gap: 10px;
                height: 100%;
                padding: 0 12px 0 8px;
                box-sizing: border-box;
                border-radius: ${unsafeCSS(`${MM_NODE_CORNER_RX}px`)};
                font-family: var(--font-sans, system-ui);
                font-size: 13px;
                font-weight: 600;
                color: var(--text-primary);
                user-select: none;
                pointer-events: none;
            }
            .mm-node-inner.mm-root-text {
                color: var(--text-inverse);
            }
            .mm-label {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
        `,
    ];

    constructor() {
        super();
        this.graphNodes = [];
        this.graphEdges = [];
        this.rootEntityId = '';
        this.entityTypeColors = {};
        this.entityTypeIcons = {};
        this.defaultAccent = '#6366f1';
        this.fitNonce = 0;
        this.compact = false;
        this.compactZoom = 1;
        this.relationshipTypeLabels = {};
        this.selectedNodeId = '';
        this.highlightNodeIds = [];
        this._panUx = 0;
        this._panUy = 0;
        this._zoom = 1;
        this._dragging = false;
        this._dragStart = { x: 0, y: 0, panUx: 0, panUy: 0 };
        /** @type {Map<string, { x: number, y: number, depth: number, w: number, h: number }> | null} */
        this._lastNodePositions = null;
        /** @type {string} */
        this._viewHydrationKey = '';
        /** @type {ReturnType<typeof setTimeout> | null} */
        this._persistTimer = null;
        this._viewportWidthPx = 0;
        this._viewportHeightPx = 0;
        /** @type {ResizeObserver | null} */
        this._viewportResizeObserver = null;
    }

    firstUpdated() {
        super.firstUpdated?.();
        this._installViewportResizeObserver();
    }

    disconnectedCallback() {
        this._flushPersistMindmapView();
        this._teardownViewportResizeObserver();
        super.disconnectedCallback();
    }

    _installViewportResizeObserver() {
        if (typeof ResizeObserver === 'undefined') {
            return;
        }
        const root = this.renderRoot;
        const viewport = root ? root.querySelector('.viewport') : null;
        if (!viewport) {
            return;
        }
        this._teardownViewportResizeObserver();
        this._viewportResizeObserver = new ResizeObserver(() => {
            const w = viewport.clientWidth;
            const h = viewport.clientHeight;
            if (Number.isFinite(w) && w > 0 && Math.abs(w - this._viewportWidthPx) >= 1) {
                this._viewportWidthPx = w;
            }
            if (Number.isFinite(h) && h > 0 && Math.abs(h - this._viewportHeightPx) >= 1) {
                this._viewportHeightPx = h;
            }
        });
        this._viewportResizeObserver.observe(viewport);
        const initialW = viewport.clientWidth;
        if (Number.isFinite(initialW) && initialW > 0) {
            this._viewportWidthPx = initialW;
        }
        const initialH = viewport.clientHeight;
        if (Number.isFinite(initialH) && initialH > 0) {
            this._viewportHeightPx = initialH;
        }
    }

    _teardownViewportResizeObserver() {
        if (this._viewportResizeObserver !== null) {
            this._viewportResizeObserver.disconnect();
            this._viewportResizeObserver = null;
        }
    }

    updated(changed) {
        super.updated(changed);
        const compact = this.compact === true;
        if (changed.has('fitNonce')) {
            this._panUx = 0;
            this._panUy = 0;
            this._zoom = 1;
            const ridFit = typeof this.rootEntityId === 'string' ? this.rootEntityId.trim() : '';
            if (ridFit.length > 0) {
                writeMindmapView(ridFit, compact, {
                    zoom: 1,
                    panUx: 0,
                    panUy: 0,
                });
            }
        }
        if (changed.has('rootEntityId') || changed.has('compact')) {
            const rid = typeof this.rootEntityId === 'string' ? this.rootEntityId.trim() : '';
            const ck = `${rid}:${compact}`;
            if (rid.length > 0 && this._viewHydrationKey !== ck) {
                this._viewHydrationKey = ck;
                if (compact) {
                    this._zoom = 1;
                    this._panUx = 0;
                    this._panUy = 0;
                } else {
                    const stored = readMindmapView(rid, compact);
                    if (stored !== null) {
                        this._zoom = stored.zoom;
                        this._panUx = stored.panUx;
                        this._panUy = stored.panUy;
                    } else {
                        this._zoom = 1;
                        this._panUx = 0;
                        this._panUy = 0;
                    }
                }
            }
        }
    }

    /**
     * @returns {void}
     */
    _schedulePersistMindmapView() {
        const compact = this.compact === true;
        if (compact) {
            return;
        }
        const rid = typeof this.rootEntityId === 'string' ? this.rootEntityId.trim() : '';
        if (rid.length === 0) {
            return;
        }
        if (this._persistTimer !== null) {
            window.clearTimeout(this._persistTimer);
        }
        this._persistTimer = window.setTimeout(() => {
            this._persistTimer = null;
            writeMindmapView(rid, compact, {
                zoom: this._zoom,
                panUx: this._panUx,
                panUy: this._panUy,
            });
        }, 280);
    }

    /**
     * @returns {void}
     */
    _flushPersistMindmapView() {
        if (this._persistTimer !== null) {
            window.clearTimeout(this._persistTimer);
            this._persistTimer = null;
        }
        const compact = this.compact === true;
        if (compact) {
            return;
        }
        const rid = typeof this.rootEntityId === 'string' ? this.rootEntityId.trim() : '';
        if (rid.length === 0) {
            return;
        }
        writeMindmapView(rid, compact, {
            zoom: this._zoom,
            panUx: this._panUx,
            panUy: this._panUy,
        });
    }

    /**
     * @returns {Map<string, { label: string, entity_type: string, access?: boolean }>}
     */
    _labelMap() {
        const map = new Map();
        for (const raw of this.graphNodes) {
            if (!raw || typeof raw !== 'object') {
                continue;
            }
            const idRaw = raw.entity_id !== undefined ? raw.entity_id : raw.id;
            const id = typeof idRaw === 'string' ? idRaw.trim() : '';
            if (id.length === 0) {
                continue;
            }
            const nameRaw = raw.name !== undefined ? raw.name : raw.label;
            const label = typeof nameRaw === 'string' && nameRaw.trim().length > 0 ? nameRaw.trim() : id;
            const etRaw = raw.entity_type;
            const entityType = typeof etRaw === 'string' ? etRaw.trim() : '';
            const access = raw.access === false ? false : true;
            map.set(id, { label, entity_type: entityType, access });
        }
        return map;
    }

    /**
     * @param {string} entityType
     * @param {boolean} access
     * @returns {string}
     */
    _typeColor(entityType, access) {
        if (access === false) {
            return '#94a3b8';
        }
        if (typeof entityType === 'string' && entityType.length > 0) {
            const raw = this.entityTypeColors[entityType];
            if (typeof raw === 'string' && raw.trim().length > 0) {
                return raw.trim();
            }
        }
        const d = this.defaultAccent;
        if (typeof d !== 'string' || d.trim().length === 0) {
            throw new Error('CRMMindmapCanvas: defaultAccent required');
        }
        return d.trim();
    }

    /**
     * @param {string} entityType
     * @param {boolean} access
     * @returns {string}
     */
    _typeIcon(entityType, access) {
        if (access === false) {
            return 'eye-off';
        }
        if (typeof entityType === 'string' && entityType.length > 0) {
            const raw = this.entityTypeIcons[entityType];
            if (typeof raw === 'string' && raw.trim().length > 0) {
                return raw.trim();
            }
        }
        return 'layers';
    }

    /**
     * @param {string} rootId
     * @param {Map<string, string[]>} treeChildren
     * @returns {Map<string, string>}
     */
    _branchStrokeByNode(rootId, treeChildren) {
        const strokeByNode = new Map();
        strokeByNode.set(rootId, ROOT_CENTER_FILL);
        const kids = treeChildren.get(rootId);
        if (!kids || kids.length === 0) {
            return strokeByNode;
        }
        kids.forEach((childId, idx) => {
            const stroke = BRANCH_PALETTE[idx % BRANCH_PALETTE.length];
            const stack = [childId];
            while (stack.length > 0) {
                const u = stack.pop();
                strokeByNode.set(u, stroke);
                const next = treeChildren.get(u);
                if (next) {
                    for (const v of next) {
                        stack.push(v);
                    }
                }
            }
        });
        return strokeByNode;
    }

    /**
     * @param {{ x: number, y: number, w: number, h: number }} pa
     * @param {{ x: number, y: number, w: number, h: number }} pb
     * @returns {string}
     */
    _curveBetween(pa, pb) {
        const x1 = pa.x + pa.w / 2;
        const y1 = pa.y;
        const x2 = pb.x - pb.w / 2;
        const y2 = pb.y;
        const dx = Math.max(48, (x2 - x1) * 0.45);
        return `M ${x1} ${y1} C ${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`;
    }

    /**
     * Единый масштаб «единица viewBox → пиксель экрана» при preserveAspectRatio meet.
     *
     * @param {{ vbW: number, vbH: number }} bbox
     * @param {number} hw
     * @param {number} hh
     * @returns {number}
     */
    _viewBoxPixelsPerUnit(bbox, hw, hh) {
        return Math.min(hw / bbox.vbW, hh / bbox.vbH);
    }

    /**
     * @param {PointerEvent} e
     */
    _onWheel(e) {
        if (this.compact === true) {
            if (!(e.ctrlKey || e.metaKey)) {
                return;
            }
            e.preventDefault();
            const cur = this._normalizedCompactZoom();
            const delta = e.deltaY > 0 ? 0.9 : 1.111;
            const next = Math.max(0.5, Math.min(3, cur * delta));
            if (Math.abs(next - cur) < 0.001) {
                return;
            }
            this.emit('compact-zoom-change', { value: next });
            return;
        }
        e.preventDefault();
        const bbox = this._lastSceneBBox;
        const root = this.shadowRoot;
        const viewport = root ? root.querySelector('.viewport') : null;
        if (!bbox || !viewport) {
            return;
        }
        const hw = viewport.clientWidth;
        const hh = viewport.clientHeight;
        if (hw <= 0 || hh <= 0) {
            return;
        }
        const delta = e.deltaY > 0 ? 0.92 : 1.09;
        const prev = this._zoom;
        const next = Math.max(0.12, Math.min(4, prev * delta));
        const cx = bbox.vbX + bbox.vbW / 2;
        const cy = bbox.vbY + bbox.vbH / 2;
        const ratio = next / prev;
        this._panUx = cx + (this._panUx - cx) * ratio;
        this._panUy = cy + (this._panUy - cy) * ratio;
        this._zoom = next;
        this._schedulePersistMindmapView();
    }

    /**
     * @returns {number}
     */
    _normalizedCompactZoom() {
        const z = typeof this.compactZoom === 'number' && Number.isFinite(this.compactZoom)
            ? this.compactZoom
            : 1;
        return Math.max(0.5, Math.min(3, z));
    }

    /**
     * @param {PointerEvent} e
     */
    _onPointerDownScene(e) {
        const t = e.target;
        if (t && typeof t.closest === 'function' && t.closest('.node-hit')) {
            return;
        }
        if (e.button !== 0) {
            return;
        }
        if (this.compact === true) {
            return;
        }
        e.preventDefault();
        this._dragging = true;
        this._dragStart = {
            x: e.clientX,
            y: e.clientY,
            panUx: this._panUx,
            panUy: this._panUy,
        };
        if (e.currentTarget instanceof HTMLElement) {
            e.currentTarget.setPointerCapture(e.pointerId);
        }
    }

    /**
     * @param {PointerEvent} e
     */
    _onPointerMoveScene(e) {
        if (!this._dragging) {
            return;
        }
        const bbox = this._lastSceneBBox;
        const root = this.shadowRoot;
        const viewport = root ? root.querySelector('.viewport') : null;
        if (!bbox || !viewport) {
            return;
        }
        const hw = viewport.clientWidth;
        const hh = viewport.clientHeight;
        if (hw <= 0 || hh <= 0) {
            return;
        }
        const sigma = this._viewBoxPixelsPerUnit(bbox, hw, hh);
        if (!Number.isFinite(sigma) || sigma <= 0) {
            return;
        }
        const dx = e.clientX - this._dragStart.x;
        const dy = e.clientY - this._dragStart.y;
        this._panUx = this._dragStart.panUx + dx / sigma;
        this._panUy = this._dragStart.panUy + dy / sigma;
    }

    /**
     * @param {PointerEvent} e
     */
    _onPointerUpScene(e) {
        if (!this._dragging) {
            return;
        }
        this._dragging = false;
        if (e.currentTarget instanceof HTMLElement) {
            try {
                e.currentTarget.releasePointerCapture(e.pointerId);
            } catch {
                /* noop */
            }
        }
        this._schedulePersistMindmapView();
    }

    /**
     * @param {string} relTypeId
     * @returns {string}
     */
    _edgeRelationshipCaption(relTypeId) {
        const k = typeof relTypeId === 'string' ? relTypeId.trim() : '';
        if (k.length === 0) {
            return '';
        }
        const map = this.relationshipTypeLabels;
        let raw = k;
        if (map && typeof map === 'object' && Object.prototype.hasOwnProperty.call(map, k)) {
            const v = map[k];
            if (typeof v === 'string' && v.trim().length > 0) {
                raw = v.trim();
            }
        }
        const maxLen = this.compact === true ? 18 : 26;
        return raw.length > maxLen ? `${raw.slice(0, maxLen - 1)}\u2026` : raw;
    }

    _renderSvg() {
        const rootId = typeof this.rootEntityId === 'string' ? this.rootEntityId.trim() : '';
        const edges = Array.isArray(this.graphEdges) ? this.graphEdges : [];

        const labelMap = this._labelMap();
        const nodeIds = new Set(labelMap.keys());
        const filteredEdges = edges.filter((raw) => {
            const ep = _edgeEndpoints(raw);
            if (ep === null) {
                return false;
            }
            return nodeIds.has(ep.source) && nodeIds.has(ep.target);
        });
        const adj = _buildAdjacency(rootId, filteredEdges);
        const { treeChildren, reachable } = _bfsTree(rootId, adj);

        const heights = _computeSubtreeBlockHeights(treeChildren, rootId);
        const positions = new Map();
        _layoutSubtree(rootId, 0, 0, treeChildren, heights, labelMap, positions);

        const strokeByNode = this._branchStrokeByNode(rootId, treeChildren);

        let minX = Infinity;
        let minY = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        for (const id of reachable) {
            const p = positions.get(id);
            if (!p || typeof p.x !== 'number') {
                continue;
            }
            const halfW = p.w / 2;
            const halfH = p.h / 2;
            minX = Math.min(minX, p.x - halfW);
            maxX = Math.max(maxX, p.x + halfW);
            minY = Math.min(minY, p.y - halfH);
            maxY = Math.max(maxY, p.y + halfH);
        }
        const pad = this.compact ? 28 : 48;
        const { vbX, vbY, vbW, vbH } = _finalizeViewBox(minX, minY, maxX, maxY, pad);
        this._lastSceneBBox = { vbX, vbY, vbW, vbH };
        this._lastNodePositions = positions;

        const edgePaths = [];
        const edgeLabels = [];
        for (const id of reachable) {
            const kids = treeChildren.get(id);
            if (!kids || kids.length === 0) {
                continue;
            }
            const pa = positions.get(id);
            for (const c of kids) {
                const pb = positions.get(c);
                if (!pa || !pb) {
                    continue;
                }
                const stroke = strokeByNode.get(c);
                const strokeColor = typeof stroke === 'string' && stroke.length > 0 ? stroke : '#94a3b8';
                const depth = typeof pb.depth === 'number' ? pb.depth : 1;
                const strokeWidth = Math.max(1.2, 3.2 - depth * 0.35);
                const d = this._curveBetween(pa, pb);
                edgePaths.push({ d, stroke: strokeColor, strokeWidth });
                const bp = _mindmapBezierControlPoints(pa, pb);
                const { p0, p1, p2, p3 } = bp;
                const mid = _cubicBezierPoint(0.5, p0, p1, p2, p3);
                const tan = _cubicBezierTangent(0.5, p0, p1, p2, p3);
                const angleDeg = _readableTangentAngleDeg(tan.x, tan.y);
                const tx = tan.x;
                const ty = tan.y;
                const tlen = Math.hypot(tx, ty);
                const nx = tlen > 1e-6 ? -ty / tlen : 0;
                const ny = tlen > 1e-6 ? tx / tlen : -1;
                const lift = this.compact === true ? 10 : 12;
                const lx = mid.x + nx * lift;
                const ly = mid.y + ny * lift;
                const relTypeId = _relationshipTypeForUndirectedPair(filteredEdges, id, c);
                const cap = this._edgeRelationshipCaption(relTypeId);
                if (cap.length > 0) {
                    edgeLabels.push({
                        x: lx,
                        y: ly,
                        angleDeg,
                        text: cap,
                    });
                }
            }
        }

        const nodeEls = [];
        for (const id of reachable) {
            const p = positions.get(id);
            if (!p) {
                continue;
            }
            const meta = labelMap.get(id);
            const label = _labelFromMap(labelMap, id);
            const isRoot = id === rootId;
            const entityType = meta && typeof meta.entity_type === 'string' ? meta.entity_type : '';
            const access = meta && meta.access === false ? false : true;
            const accent = this._typeColor(entityType, access);
            const iconName = this._typeIcon(entityType, access);
            const displayLabel = label.length > 46 ? `${label.slice(0, 44)}…` : label;
            const innerCls = isRoot ? 'mm-node-inner mm-root-text' : 'mm-node-inner';
            const sel = typeof this.selectedNodeId === 'string' ? this.selectedNodeId.trim() : '';
            const hlList = Array.isArray(this.highlightNodeIds) ? this.highlightNodeIds : [];
            const isSel = sel.length > 0 && id === sel;
            const isHl = hlList.includes(id);
            let ringStroke = accent;
            if (isSel) {
                ringStroke = '#ffffff';
            } else if (isHl) {
                ringStroke = '#f59e0b';
            }
            const sw = isSel ? 3 : 2;
            const inset = sw / 2;
            const innerW = p.w - sw;
            const innerH = p.h - sw;
            const rxStroke =
                innerW > 0 && innerH > 0 ? Math.max(0, MM_NODE_CORNER_RX - inset) : 0;
            const fillBg = isRoot ? accent : '#ffffff';
            const fo = html`
                <div xmlns="http://www.w3.org/1999/xhtml" class=${innerCls}>
                    <platform-icon name=${iconName} size=${this.compact ? '14' : '18'}></platform-icon>
                    <span class="mm-label">${displayLabel}</span>
                </div>
            `;
            nodeEls.push(svg`
                <g
                    class="node-hit"
                    transform="translate(${p.x - p.w / 2} ${p.y - p.h / 2})"
                    role="button"
                    tabindex="0"
                    @pointerdown=${(e) => e.stopPropagation()}
                    @click=${(e) => {
                        e.stopPropagation();
                        this.emit('node-click', { node: { id }, event: e });
                    }}
                    @dblclick=${(e) => {
                        e.stopPropagation();
                        this.emit('node-dblclick', { node: { id } });
                    }}
                    @contextmenu=${(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        this.emit('node-contextmenu', {
                            node: { id },
                            screenX: e.clientX,
                            screenY: e.clientY,
                        });
                    }}
                >
                    <rect
                        width="${p.w}"
                        height="${p.h}"
                        rx="${MM_NODE_CORNER_RX}"
                        ry="${MM_NODE_CORNER_RX}"
                        fill=${fillBg}
                        fill-opacity="${isRoot ? 1 : 0.94}"
                    />
                    ${innerW > 0 && innerH > 0
                        ? svg`
                            <rect
                                x="${inset}"
                                y="${inset}"
                                width="${innerW}"
                                height="${innerH}"
                                rx="${rxStroke}"
                                ry="${rxStroke}"
                                fill="none"
                                stroke=${ringStroke}
                                stroke-width="${sw}"
                                stroke-linejoin="round"
                            />
                        `
                        : null}
                    <foreignObject class="mm-fo" x="0" y="0" width="${p.w}" height="${p.h}">
                        ${fo}
                    </foreignObject>
                </g>
            `);
        }

        const cx = vbX + vbW / 2;
        const cy = vbY + vbH / 2;
        const gx = this._panUx;
        const gy = this._panUy;
        const gz = this._zoom;
        const graphTransform = `translate(${gx} ${gy}) translate(${cx} ${cy}) scale(${gz}) translate(${-cx} ${-cy})`;

        const compact = this.compact === true;
        const containerW = this._viewportWidthPx;
        const containerH = this._viewportHeightPx;
        const cz = compact ? this._normalizedCompactZoom() : 1;
        const naturalH =
            compact && Number.isFinite(containerW) && containerW > 0 && vbW > 0
                ? (containerW * vbH) / vbW
                : 0;
        const scaledH = naturalH * cz;
        const scaledW = containerW * cz;
        const compactNeedsScroll =
            compact && scaledH > 0 && containerH > 0 && (scaledH > containerH || cz !== 1);
        let svgStyle = '';
        if (compact) {
            if (cz !== 1 && containerW > 0) {
                svgStyle = `width:${Math.round(scaledW)}px;height:${Math.max(220, Math.round(scaledH))}px;`;
            } else if (compactNeedsScroll) {
                svgStyle = `height:${Math.max(220, Math.round(scaledH))}px;`;
            }
        }
        const aspectAlign = compactNeedsScroll ? 'xMidYMin meet' : 'xMidYMid meet';

        return svg`
            <svg
                class="mindmap-svg"
                style=${svgStyle}
                xmlns="http://www.w3.org/2000/svg"
                viewBox="${vbX} ${vbY} ${vbW} ${vbH}"
                preserveAspectRatio=${aspectAlign}
            >
                <g transform="${graphTransform}">
                    ${edgePaths.map(
                        (row) => svg`
                            <path
                                class="edge-path"
                                fill="none"
                                d=${row.d}
                                stroke=${row.stroke}
                                stroke-width="${row.strokeWidth}"
                            ></path>
                        `,
                    )}
                    ${edgeLabels.map(
                        (lb) => svg`
                            <text
                                class="mm-edge-label"
                                x=${lb.x}
                                y=${lb.y}
                                transform="rotate(${lb.angleDeg} ${lb.x} ${lb.y})"
                                text-anchor="middle"
                                dominant-baseline="middle"
                            >${lb.text}</text>
                        `,
                    )}
                    ${nodeEls}
                </g>
            </svg>
        `;
    }

    /**
     * @param {MouseEvent} e
     */
    _onViewportClick(e) {
        const t = e.target;
        if (t && typeof t.closest === 'function' && t.closest('.node-hit')) {
            return;
        }
        this.emit('canvas-click');
    }

    /**
     * @param {string} nodeId
     * @returns {void}
     */
    flyToNode(nodeId) {
        const id = typeof nodeId === 'string' ? nodeId.trim() : '';
        if (id.length === 0) {
            throw new Error('CRMMindmapCanvas.flyToNode: nodeId required');
        }
        const positions = this._lastNodePositions;
        const bbox = this._lastSceneBBox;
        const root = this.shadowRoot;
        const viewport = root ? root.querySelector('.viewport') : null;
        if (!positions || !bbox || !viewport) {
            return;
        }
        const p = positions.get(id);
        if (!p) {
            return;
        }
        const hw = viewport.clientWidth;
        const hh = viewport.clientHeight;
        if (hw <= 0 || hh <= 0) {
            return;
        }
        const sigma = this._viewBoxPixelsPerUnit(bbox, hw, hh);
        if (!Number.isFinite(sigma) || sigma <= 0) {
            return;
        }
        const cx = bbox.vbX + bbox.vbW / 2;
        const cy = bbox.vbY + bbox.vbH / 2;
        const nx = p.x;
        const ny = p.y;
        this._panUx = cx - nx;
        this._panUy = cy - ny;
        this.requestUpdate();
        this._schedulePersistMindmapView();
    }

    /**
     * @param {string} nodeId
     * @returns {void}
     */
    expandToNode(nodeId) {
        this.flyToNode(nodeId);
    }

    render() {
        const rootId = typeof this.rootEntityId === 'string' ? this.rootEntityId.trim() : '';
        if (rootId.length === 0) {
            return html``;
        }
        const nodes = Array.isArray(this.graphNodes) ? this.graphNodes : [];
        if (nodes.length === 0) {
            return html``;
        }
        const svgTpl = this._renderSvg();
        return html`
            <div
                class="viewport"
                @wheel=${this._onWheel}
                @pointerdown=${this._onPointerDownScene}
                @pointermove=${this._onPointerMoveScene}
                @pointerup=${this._onPointerUpScene}
                @pointercancel=${this._onPointerUpScene}
                @click=${this._onViewportClick}
            >
                <div class="scene">${svgTpl}</div>
            </div>
        `;
    }
}

customElements.define('crm-mindmap-canvas', CRMMindmapCanvas);

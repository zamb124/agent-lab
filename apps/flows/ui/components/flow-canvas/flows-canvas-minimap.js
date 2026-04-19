/**
 * flows-canvas-minimap — мини-карта канваса.
 *
 * Источники:
 *   - useOp('flows/editor').state.skillsData.nodes — позиции нод;
 *   - useOp('flows/editor').state.viewBox — текущая viewport.
 *
 * Click+drag по minimap → диспатч `setViewBox`. Collapse-режим прячет SVG,
 * оставляя круглую кнопку.
 */

import { html, css, svg } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { getNodeTypeMeta, getCategoryToken } from '../../constants/node-icons.js';

const MINIMAP_W = 200;
const MINIMAP_H = 140;
const NODE_W_REAL = 200;
const NODE_H_REAL = 72;

export class FlowsCanvasMinimap extends PlatformElement {
    static properties = {
        _collapsed: { state: true },
        _drag: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                bottom: var(--space-3);
                right: var(--space-3);
                z-index: 6;
            }
            .pill {
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-medium);
                overflow: hidden;
            }
            .pill[data-collapsed] {
                width: 36px; height: 36px;
                border-radius: var(--radius-full);
                display: flex; align-items: center; justify-content: center;
                cursor: pointer;
                color: var(--text-secondary);
            }
            .pill[data-collapsed]:hover { color: var(--accent); }
            .map-host {
                position: relative;
                width: ${MINIMAP_W}px;
                height: ${MINIMAP_H}px;
            }
            .toggle-btn {
                position: absolute;
                top: 4px; right: 4px;
                width: 22px; height: 22px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-sm);
                border: none;
                background: var(--glass-solid-medium);
                color: var(--text-tertiary);
                cursor: pointer;
                z-index: 1;
            }
            .toggle-btn:hover { color: var(--accent); }
            svg.map { display: block; width: 100%; height: 100%; cursor: pointer; }
            rect.viewport {
                fill: var(--accent-subtle);
                stroke: var(--accent);
                stroke-width: 1;
                pointer-events: none;
            }
            rect.node-marker {
                opacity: 0.85;
            }
            rect.node-marker.cat-core { fill: var(--accent); }
            rect.node-marker.cat-integrations { fill: var(--info); }
            rect.node-marker.cat-flow { fill: var(--accent-secondary); }
            rect.node-marker.cat-hitl { fill: var(--warning); }
        `,
    ];

    constructor() {
        super();
        this._collapsed = false;
        this._drag = null;
        this._editor = this.useOp('flows/editor');
    }

    _bounds(nodes) {
        const entries = Object.values(nodes);
        if (entries.length === 0) return { minX: 0, minY: 0, maxX: 1600, maxY: 1000 };
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const node of entries) {
            const x = Number(node.pos_x) || 0;
            const y = Number(node.pos_y) || 0;
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (x + NODE_W_REAL > maxX) maxX = x + NODE_W_REAL;
            if (y + NODE_H_REAL > maxY) maxY = y + NODE_H_REAL;
        }
        const pad = 200;
        return { minX: minX - pad, minY: minY - pad, maxX: maxX + pad, maxY: maxY + pad };
    }

    _onMapClick(e) {
        const state = this._editor.state || {};
        const skillsData = state.skillsData || { nodes: {} };
        const nodes = skillsData.nodes || {};
        const b = this._bounds(nodes);
        const rect = e.currentTarget.getBoundingClientRect();
        const fx = (e.clientX - rect.left) / rect.width;
        const fy = (e.clientY - rect.top) / rect.height;
        const worldW = b.maxX - b.minX;
        const worldH = b.maxY - b.minY;
        const cx = b.minX + worldW * fx;
        const cy = b.minY + worldH * fy;
        const vb = state.viewBox || { x: 0, y: 0, w: 1600, h: 1000 };
        this._editor.setViewBox({ viewBox: { x: cx - vb.w / 2, y: cy - vb.h / 2, w: vb.w, h: vb.h } });
    }

    _toggle() {
        this._collapsed = !this._collapsed;
    }

    render() {
        if (this._collapsed) {
            return html`
                <div class="pill" data-collapsed @click=${this._toggle} title=${this.t('canvas.minimap.expand')}>
                    <platform-icon name="layers" size="16"></platform-icon>
                </div>
            `;
        }
        const state = this._editor.state || {};
        const skillsData = state.skillsData || { nodes: {} };
        const nodes = skillsData.nodes || {};
        const b = this._bounds(nodes);
        const worldW = b.maxX - b.minX;
        const worldH = b.maxY - b.minY;
        const vb = state.viewBox || { x: 0, y: 0, w: 1600, h: 1000 };
        return html`
            <div class="pill">
                <div class="map-host">
                    <button class="toggle-btn" type="button" @click=${this._toggle} title=${this.t('canvas.minimap.collapse')}>
                        <platform-icon name="minimize" size="12"></platform-icon>
                    </button>
                    <svg class="map" viewBox=${`${b.minX} ${b.minY} ${worldW} ${worldH}`} @click=${this._onMapClick}>
                        ${Object.values(nodes).map((node) => {
                            const meta = getNodeTypeMeta(node.type);
                            return svg`
                                <rect
                                    class="node-marker cat-${meta.category}"
                                    x=${node.pos_x || 0}
                                    y=${node.pos_y || 0}
                                    width=${NODE_W_REAL}
                                    height=${NODE_H_REAL}
                                    rx="8"
                                ></rect>
                            `;
                        })}
                        <rect class="viewport" x=${vb.x} y=${vb.y} width=${vb.w} height=${vb.h}></rect>
                    </svg>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-canvas-minimap', FlowsCanvasMinimap);

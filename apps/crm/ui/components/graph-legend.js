/**
 * graph-legend — легенда графа: список цветов entity_type, hint текущего режима,
 * выбранный node/edge.
 *
 * Чисто-презентационный компонент: только props и render, без emit/dispatch.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class CRMGraphLegend extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        nodes: { type: Array },
        entityTypeColors: { type: Object, attribute: 'entity-type-colors' },
        canvasHint: { type: String, attribute: 'canvas-hint' },
        selectedNodeId: { type: String, attribute: 'selected-node-id' },
        selectedEdgeId: { type: String, attribute: 'selected-edge-id' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                gap: 8px;
                padding: 10px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: 14px;
                backdrop-filter: blur(6px);
                pointer-events: none;
                color: var(--text-secondary);
            }

            .row {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }

            .legend-item {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            .dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                flex-shrink: 0;
            }

            .hint-pill,
            .node-pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

            @media (max-width: 1199px) {
                :host { max-width: 320px; }
            }

            @media (max-width: 767px) {
                :host { padding: 6px 8px; }
                .row { gap: 6px; }
            }
        `,
    ];

    constructor() {
        super();
        this.nodes = [];
        this.entityTypeColors = {};
        this.canvasHint = '';
        this.selectedNodeId = '';
        this.selectedEdgeId = '';
    }

    _getVisibleTypes() {
        const palette = this.entityTypeColors instanceof Map
            ? this.entityTypeColors
            : new Map(Object.entries(this.entityTypeColors));

        const seen = new Set();
        const result = [];
        for (const node of this.nodes) {
            const typeId = typeof node.entity_type === 'string' ? node.entity_type.trim() : '';
            if (!typeId || typeId === 'hidden' || seen.has(typeId)) continue;
            seen.add(typeId);
            result.push({ typeId, color: palette.get(typeId) || '#888' });
        }
        return result;
    }

    render() {
        const visibleTypes = this._getVisibleTypes();
        const dash = '\u2014';

        return html`
            <div class="row">
                ${visibleTypes.map(({ typeId, color }) => html`
                    <div class="legend-item">
                        <span class="dot" style="background:${color}"></span>${typeId}
                    </div>
                `)}
                <div class="legend-item"><span class="dot" style="background:#7f7f8f"></span>${this.t('graph.legend_hidden')}</div>
                <div class="legend-item"><span class="dot" style="background:#41d36d"></span>${this.t('graph.legend_path_directed')}</div>
                <div class="legend-item"><span class="dot" style="background:#f2c94c"></span>${this.t('graph.legend_path_undirected')}</div>
            </div>
            <div class="row">
                <span class="hint-pill">${this.canvasHint}</span>
                <span class="node-pill">${this.t('graph.legend_node_label')}: ${this.selectedNodeId || dash}</span>
                <span class="node-pill">${this.t('graph.legend_edge_label')}: ${this.selectedEdgeId || dash}</span>
            </div>
        `;
    }
}

customElements.define('crm-graph-legend', CRMGraphLegend);

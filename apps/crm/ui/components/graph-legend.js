import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class GraphLegend extends PlatformElement {
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

            .hint-pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }

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
                :host {
                    max-width: 320px;
                }
            }

            @media (max-width: 767px) {
                :host {
                    padding: 6px 8px;
                }

                .row {
                    gap: 6px;
                }
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
        const colors = this.entityTypeColors instanceof Map
            ? this.entityTypeColors
            : new Map(Object.entries(this.entityTypeColors));

        return Array.from(new Set(
            this.nodes
                .map((node) => {
                    const typeId = typeof node.entity_type === 'string' ? node.entity_type.trim() : '';
                    return typeId;
                })
                .filter((typeId) => typeId.length > 0 && typeId !== 'hidden'),
        )).map((typeId) => ({ typeId, color: colors.get(typeId) || '#888' }));
    }

    render() {
        const visibleTypes = this._getVisibleTypes();

        return html`
            <div class="row">
                ${visibleTypes.map(({ typeId, color }) => html`
                    <div class="legend-item">
                        <span class="dot" style="background:${color}"></span>${typeId}
                    </div>
                `)}
                <div class="legend-item"><span class="dot" style="background:#7f7f8f"></span> Hidden</div>
                <div class="legend-item"><span class="dot" style="background:#41d36d"></span> Path directed</div>
                <div class="legend-item"><span class="dot" style="background:#f2c94c"></span> Path undirected</div>
            </div>
            <div class="row">
                <span class="hint-pill">${this.canvasHint}</span>
                <span class="node-pill">node: ${this.selectedNodeId || '\u2014'}</span>
                <span class="node-pill">edge: ${this.selectedEdgeId || '\u2014'}</span>
            </div>
        `;
    }
}

customElements.define('graph-legend', GraphLegend);

/**
 * platform-sparkline — мини line/area chart для time series.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const SVG_WIDTH = 240;
const SVG_HEIGHT = 64;
const SVG_PADDING = 4;

export class PlatformSparkline extends PlatformElement {
    static properties = {
        points: { type: Array },
        stroke: { type: String },
        fill: { type: String },
        emptyLabel: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            svg {
                width: 100%;
                height: auto;
                display: block;
            }
            .empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.points = [];
        this.stroke = 'var(--accent)';
        this.fill = 'color-mix(in srgb, var(--accent) 18%, transparent)';
        this.emptyLabel = '';
    }

    _buildPath() {
        if (!Array.isArray(this.points) || this.points.length === 0) {
            return null;
        }
        const values = this.points.map((point) => {
            if (typeof point.value !== 'number' || !Number.isFinite(point.value)) {
                throw new Error('platform-sparkline: point.value must be finite number');
            }
            return point.value;
        });
        const maxValue = Math.max(...values, 1);
        const minValue = Math.min(...values, 0);
        const range = maxValue - minValue;
        const innerWidth = SVG_WIDTH - (SVG_PADDING * 2);
        const innerHeight = SVG_HEIGHT - (SVG_PADDING * 2);
        const coords = values.map((value, index) => {
            const x = SVG_PADDING + ((index / Math.max(values.length - 1, 1)) * innerWidth);
            const normalized = range === 0 ? 0.5 : (value - minValue) / range;
            const y = SVG_PADDING + innerHeight - (normalized * innerHeight);
            return { x, y };
        });
        const linePath = coords.map((coord, index) => `${index === 0 ? 'M' : 'L'} ${coord.x} ${coord.y}`).join(' ');
        const areaPath = `${linePath} L ${coords[coords.length - 1].x} ${SVG_HEIGHT - SVG_PADDING} L ${coords[0].x} ${SVG_HEIGHT - SVG_PADDING} Z`;
        return { linePath, areaPath };
    }

    render() {
        const paths = this._buildPath();
        if (!paths) {
            return html`<div class="empty">${this.emptyLabel}</div>`;
        }
        return html`
            <svg viewBox="0 0 ${SVG_WIDTH} ${SVG_HEIGHT}" preserveAspectRatio="none" role="img" aria-hidden="true">
                <path d=${paths.areaPath} fill=${this.fill} stroke="none"></path>
                <path d=${paths.linePath} fill="none" stroke=${this.stroke} stroke-width="2" stroke-linecap="round" stroke-linejoin="round"></path>
            </svg>
        `;
    }
}

customElements.define('platform-sparkline', PlatformSparkline);

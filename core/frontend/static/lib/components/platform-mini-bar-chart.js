/**
 * platform-mini-bar-chart — горизонтальная stacked bar chart.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formatPlatformNumber } from '@platform/lib/utils/format-platform-number.js';

export class PlatformMiniBarChart extends PlatformElement {
    static properties = {
        segments: { type: Array },
        locale: { type: String },
        emptyLabel: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .track {
                display: flex;
                width: 100%;
                min-height: 10px;
                border-radius: var(--radius-full);
                overflow: hidden;
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
            }
            .segment {
                min-width: 2px;
                transition: flex-grow var(--duration-normal) var(--easing-default);
            }
            .legend {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2) var(--space-4);
                margin-top: var(--space-2);
            }
            .legend-item {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
            }
            .swatch {
                width: 8px;
                height: 8px;
                border-radius: var(--radius-full);
                flex-shrink: 0;
            }
            .empty {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.segments = [];
        this.locale = 'en';
        this.emptyLabel = '';
    }

    _total() {
        let sum = 0;
        for (const segment of this.segments) {
            if (typeof segment.value !== 'number' || !Number.isFinite(segment.value)) {
                throw new Error('platform-mini-bar-chart: segment.value must be finite number');
            }
            sum += segment.value;
        }
        return sum;
    }

    render() {
        const total = this._total();
        if (total <= 0) {
            return html`<div class="empty">${this.emptyLabel}</div>`;
        }
        return html`
            <div class="track" role="img" aria-hidden="true">
                ${this.segments.filter((segment) => segment.value > 0).map((segment) => html`
                    <div
                        class="segment"
                        style="flex-grow: ${segment.value}; background: ${segment.color};"
                    ></div>
                `)}
            </div>
            <div class="legend">
                ${this.segments.map((segment) => html`
                    <span class="legend-item">
                        <span class="swatch" style="background: ${segment.color};"></span>
                        <span>${segment.label}</span>
                        <span>${formatPlatformNumber(segment.value, this.locale)}</span>
                    </span>
                `)}
            </div>
        `;
    }
}

customElements.define('platform-mini-bar-chart', PlatformMiniBarChart);

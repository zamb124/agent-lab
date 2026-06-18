/**
 * platform-metric-card — метрика с анимированным значением.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './platform-animated-number.js';

export class PlatformMetricCard extends PlatformElement {
    static properties = {
        label: { type: String },
        value: { type: Number },
        locale: { type: String },
        tone: { type: String },
        refreshing: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                height: 100%;
            }
            .card {
                position: relative;
                box-sizing: border-box;
                height: 100%;
                display: flex;
                flex-direction: column;
                padding: var(--space-3);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                overflow: hidden;
            }
            .card.tone-accent {
                border-color: color-mix(in srgb, var(--accent) 40%, transparent);
            }
            .card.tone-warn {
                border-color: color-mix(in srgb, var(--warning) 45%, transparent);
            }
            .card.tone-danger {
                border-color: color-mix(in srgb, var(--error) 45%, transparent);
            }
            .label {
                flex: 0 0 auto;
                min-height: calc(1.35em * 2);
                font-size: var(--text-xs);
                line-height: 1.35;
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
                display: -webkit-box;
                -webkit-box-orient: vertical;
                -webkit-line-clamp: 2;
                overflow: hidden;
            }
            .value-row {
                flex: 0 0 auto;
                display: flex;
                align-items: baseline;
                gap: var(--space-2);
                margin-top: var(--space-2);
            }
            .value {
                font-size: var(--text-xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .refresh-indicator {
                width: 6px;
                height: 6px;
                border-radius: var(--radius-full);
                background: var(--accent);
                opacity: 0;
                transform: scale(0.8);
                transition: opacity var(--duration-fast) var(--easing-default);
            }
            .refresh-indicator.active {
                opacity: 1;
                animation: metric-card-pulse 1.2s ease-in-out infinite;
            }
            @keyframes metric-card-pulse {
                0%, 100% { transform: scale(0.85); opacity: 0.35; }
                50% { transform: scale(1); opacity: 1; }
            }
        `,
    ];

    constructor() {
        super();
        this.label = '';
        this.value = 0;
        this.locale = 'en';
        this.tone = '';
        this.refreshing = false;
    }

    render() {
        const toneClass = this.tone ? `tone-${this.tone}` : '';
        return html`
            <div class="card ${toneClass}">
                <div class="label">${this.label}</div>
                <div class="value-row">
                    <div class="value">
                        <platform-animated-number
                            .value=${this.value}
                            .locale=${this.locale}
                        ></platform-animated-number>
                    </div>
                    <span class="refresh-indicator ${this.refreshing ? 'active' : ''}"></span>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-metric-card', PlatformMetricCard);

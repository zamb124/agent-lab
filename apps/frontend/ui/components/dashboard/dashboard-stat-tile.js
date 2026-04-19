/**
 * dashboard-stat-tile — пресентейшнл-плитка одной метрики (icon + label + value).
 *
 * Никаких подписок на state, никаких HTTP. Только props.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

const TONE_COLORS = {
    accent: 'var(--accent)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    info: 'var(--info)',
};

export class DashboardStatTile extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        icon: { type: String },
        label: { type: String },
        value: { type: String },
        tone: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
            }
            .tile {
                display: flex;
                gap: var(--space-3);
                align-items: center;
                padding: var(--space-4) var(--space-5);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-soft);
                backdrop-filter: blur(var(--glass-blur-soft));
                -webkit-backdrop-filter: blur(var(--glass-blur-soft));
                border: 1px solid var(--glass-border-subtle);
                transition: transform var(--duration-normal) var(--easing-default),
                            border-color var(--duration-normal) var(--easing-default);
            }
            .tile:hover {
                transform: translateY(-2px);
                border-color: var(--glass-border-glow);
            }
            .icon {
                width: 44px;
                height: 44px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--tile-tone) 18%, transparent);
                color: var(--tile-tone);
                flex-shrink: 0;
            }
            .body { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
            .label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
            }
            .value {
                font-size: var(--text-xl);
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
        `,
    ];

    constructor() {
        super();
        this.icon = '';
        this.label = '';
        this.value = '';
        this.tone = 'accent';
    }

    render() {
        const tone = TONE_COLORS[this.tone] === undefined ? TONE_COLORS.accent : TONE_COLORS[this.tone];
        return html`
            <div class="tile" style="--tile-tone: ${tone}">
                <div class="icon">
                    <platform-icon name=${this.icon} size="22"></platform-icon>
                </div>
                <div class="body">
                    <div class="label">${this.label}</div>
                    <div class="value">${this.value}</div>
                </div>
            </div>
        `;
    }
}

customElements.define('dashboard-stat-tile', DashboardStatTile);

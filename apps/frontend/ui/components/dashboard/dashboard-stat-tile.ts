/**
 * dashboard-stat-tile — пресентейшнл-плитка одной метрики (icon + label + value).
 *
 * Никаких подписок на state, никаких HTTP. Только props.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

function hasOwnKey<T extends object>(catalog: T, key: string): key is Extract<keyof T, string> {
    return Object.prototype.hasOwnProperty.call(catalog, key);
}

const TONE_COLORS = {
    accent: 'var(--accent)',
    success: 'var(--success)',
    warning: 'var(--warning)',
    info: 'var(--info)',
};

export class DashboardStatTile extends PlatformElement {
    static i18nNamespace = 'frontend';

    static override properties: PropertyDeclarations = {
        icon: { type: String },
        label: { type: String },
        value: { type: String },
        tone: { type: String },
    }
    declare icon: string;
    declare label: string;
    declare value: string;
    declare tone: string;
;

    static override styles: CSSResultGroup = [
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
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(var(--glass-blur-soft));
                -webkit-backdrop-filter: blur(var(--glass-blur-soft));
                border: 1px solid var(--glass-border-subtle);
                transition: transform var(--motion-duration-layout) var(--motion-ease-standard),
                            border-color var(--motion-duration-layout) var(--motion-ease-standard);
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

    override render(): TemplateResult {
        const tone = hasOwnKey(TONE_COLORS, this.tone) ? TONE_COLORS[this.tone] : TONE_COLORS.accent;
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

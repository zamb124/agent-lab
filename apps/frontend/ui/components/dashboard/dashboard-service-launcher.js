/**
 * dashboard-service-launcher — компактная плитка «иконка приложения» для мобильной
 * сетки сервисов на /dashboard. Только props, без подписок на bus.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

const HEALTH_DOT = {
    healthy: 'var(--success)',
    unhealthy: 'var(--error)',
    loading: 'var(--text-tertiary)',
};

export class DashboardServiceLauncher extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        nameKey: { type: String, attribute: 'name-key' },
        logoSrc: { type: String, attribute: 'logo-src' },
        href: { type: String },
        brandFrom: { type: String, attribute: 'brand-from' },
        brandTo: { type: String, attribute: 'brand-to' },
        healthState: { type: String, attribute: 'health-state' },
        disabled: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .tile {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-2);
                text-align: center;
                text-decoration: none;
                color: inherit;
                padding: var(--space-2);
                border-radius: var(--radius-xl);
                transition: transform var(--duration-normal) var(--easing-default);
            }
            a.tile:active { transform: scale(0.96); }
            .icon-wrap {
                position: relative;
                width: 64px;
                height: 64px;
                border-radius: var(--radius-2xl);
                background: linear-gradient(145deg,
                    color-mix(in srgb, var(--brand-from) 35%, var(--glass-solid-medium)) 0%,
                    color-mix(in srgb, var(--brand-to) 28%, var(--glass-solid-medium)) 100%);
                border: 1px solid var(--glass-border-medium);
                box-shadow: var(--glass-shadow-medium);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2);
            }
            .icon-wrap img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            .health-dot {
                position: absolute;
                top: 4px;
                right: 4px;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: var(--health-dot-color);
                box-shadow: 0 0 6px var(--health-dot-color);
                border: 2px solid var(--glass-solid-medium);
            }
            .label {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: 1.25;
                max-width: 100%;
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
            }
            .tile--disabled {
                cursor: not-allowed;
                pointer-events: none;
                opacity: 0.72;
            }
        `,
    ];

    constructor() {
        super();
        this.nameKey = '';
        this.logoSrc = '';
        this.href = '';
        this.brandFrom = '#6366f1';
        this.brandTo = '#0ea5e9';
        this.healthState = 'loading';
        this.disabled = false;
    }

    render() {
        const dotColor = HEALTH_DOT[this.healthState];
        const brandStyle = `--brand-from: ${this.brandFrom}; --brand-to: ${this.brandTo}; --health-dot-color: ${dotColor};`;
        const title = this.t(this.nameKey, null, 'platform');
        const iconBlock = html`
            <div class="icon-wrap" style=${brandStyle}>
                <span class="health-dot" aria-hidden="true"></span>
                <img src=${this.logoSrc} alt="" />
            </div>
        `;
        const label = html`<span class="label">${title}</span>`;
        if (this.disabled) {
            return html`
                <div class="tile tile--disabled" style=${brandStyle} aria-label=${title}>
                    ${iconBlock}
                    ${label}
                </div>
            `;
        }
        return html`
            <a class="tile" href=${this.href} aria-label=${title} style=${brandStyle}>
                ${iconBlock}
                ${label}
            </a>
        `;
    }
}

customElements.define('dashboard-service-launcher', DashboardServiceLauncher);

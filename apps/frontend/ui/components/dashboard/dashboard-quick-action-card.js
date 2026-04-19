/**
 * dashboard-quick-action-card — кнопка-карточка одного быстрого действия.
 *
 * Презентация: иконка + заголовок + описание, кликабельная плитка.
 * При активации (клик / Enter / Space) эмитит DOM-событие `activate`
 * для родителя — никакой логики о роутах/модалках внутри не знает.
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

export class DashboardQuickActionCard extends PlatformElement {
    static i18nNamespace = 'frontend';

    static properties = {
        icon: { type: String },
        title: { type: String },
        description: { type: String },
        tone: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            button {
                width: 100%;
                display: flex;
                align-items: flex-start;
                gap: var(--space-4);
                padding: var(--space-5);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-medium));
                -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
                text-align: left;
                cursor: pointer;
                font: inherit;
                transition: transform var(--duration-normal) var(--easing-default),
                            border-color var(--duration-normal) var(--easing-default),
                            box-shadow var(--duration-normal) var(--easing-default);
            }
            button:hover {
                transform: translateY(-3px);
                border-color: var(--glass-border-glow);
                box-shadow: var(--glass-shadow-strong);
            }
            button:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 2px;
            }
            .icon {
                width: 44px;
                height: 44px;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: color-mix(in srgb, var(--card-tone) 18%, transparent);
                color: var(--card-tone);
            }
            .body { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
            .title {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                font-size: var(--text-base);
            }
            .description {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
            }
        `,
    ];

    constructor() {
        super();
        this.icon = '';
        this.title = '';
        this.description = '';
        this.tone = 'accent';
    }

    _onClick() {
        this.emit('activate');
    }

    _onKeyDown(e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this.emit('activate');
        }
    }

    render() {
        const tone = TONE_COLORS[this.tone] === undefined ? TONE_COLORS.accent : TONE_COLORS[this.tone];
        return html`
            <button type="button"
                    style="--card-tone: ${tone}"
                    @click=${this._onClick}
                    @keydown=${this._onKeyDown}>
                <span class="icon">
                    <platform-icon name=${this.icon} size="22"></platform-icon>
                </span>
                <span class="body">
                    <span class="title">${this.title}</span>
                    <span class="description">${this.description}</span>
                </span>
            </button>
        `;
    }
}

customElements.define('dashboard-quick-action-card', DashboardQuickActionCard);

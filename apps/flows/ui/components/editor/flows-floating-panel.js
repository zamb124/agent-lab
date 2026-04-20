/**
 * flows-floating-panel — chrome для property/resource панелей.
 *
 * Glass-карточка, прибита к правому краю редактор-shell. Поддерживает:
 *   - slideIn-анимацию при mount;
 *   - режим `expanded`: разворачивается на 94vw × 94vh с backdrop;
 *   - подсветка `lara-glow` при push-событии `flows/lara/node_updated` (3.2s).
 *
 * Заголовок берёт icon + colorToken (CSS-переменная) из родителя.
 *
 * Слот по умолчанию для содержимого (property-panel или resource-property-panel).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsFloatingPanel extends PlatformElement {
    static properties = {
        headerIcon: { type: String, attribute: 'header-icon' },
        headerTitle: { type: String, attribute: 'header-title' },
        colorToken: { type: String, attribute: 'color-token' },
        expanded: { type: Boolean, reflect: true },
        _laraGlow: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                bottom: var(--space-3);
                width: 420px;
                z-index: 5;
                display: flex;
                flex-direction: column;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-xl);
                box-shadow: var(--glass-shadow-strong);
                overflow: hidden;
                animation: slideInPanel 250ms cubic-bezier(0.22, 1, 0.36, 1);
                transition:
                    top var(--duration-slow) var(--easing-smooth),
                    right var(--duration-slow) var(--easing-smooth),
                    left var(--duration-slow) var(--easing-smooth),
                    width var(--duration-slow) var(--easing-smooth),
                    height var(--duration-slow) var(--easing-smooth);
            }

            :host([expanded]) {
                position: fixed;
                top: 3vh;
                left: 50%;
                right: auto;
                bottom: auto;
                width: min(1200px, 94vw);
                height: 94vh;
                transform: translateX(-50%);
                z-index: 25100;
                animation: none;
                box-shadow: 0 32px 100px rgba(0, 0, 0, 0.45), 0 0 0 1px var(--glass-border-medium);
            }

            .panel-backdrop {
                position: fixed;
                inset: 0;
                background: rgba(0, 0, 0, 0);
                z-index: 0;
                pointer-events: none;
                transition: background 400ms var(--easing-smooth);
                display: none;
            }

            :host([expanded]) .panel-backdrop {
                display: block;
                background: color-mix(in oklab, var(--bg-primary) 60%, transparent);
                pointer-events: auto;
                backdrop-filter: blur(6px);
            }

            .panel-header {
                display: flex; align-items: center; justify-content: space-between;
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                flex-shrink: 0;
                position: relative;
                z-index: 1;
            }
            .panel-title {
                display: flex; align-items: center; gap: var(--space-2);
                min-width: 0;
            }
            .panel-icon {
                width: 32px; height: 32px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-sm);
            }
            :host([expanded]) .panel-icon {
                width: 40px; height: 40px;
                border-radius: var(--radius-md);
            }
            .panel-name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
            }
            :host([expanded]) .panel-name { font-size: var(--text-lg); }

            .panel-actions {
                display: flex; align-items: center; gap: var(--space-1);
                flex-shrink: 0;
            }
            .panel-btn {
                width: 32px; height: 32px;
                display: flex; align-items: center; justify-content: center;
                background: transparent; border: none;
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
                cursor: pointer;
                transition: background var(--duration-fast), color var(--duration-fast);
            }
            .panel-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .panel-btn.expand:hover { color: var(--accent); }

            .panel-body {
                flex: 1;
                min-height: 0;
                overflow: auto;
                padding: 0;
                position: relative;
                z-index: 1;
            }
            :host(:not([expanded])) .panel-body {
                padding: 0;
            }
            :host([expanded]) .panel-body {
                overflow: hidden;
                padding: 0;
            }
            .panel-body[data-lara-glow] {
                animation: laraNodeGlow 3.2s ease-out;
            }

            @keyframes slideInPanel {
                from { opacity: 0; transform: translateX(40px) scale(0.95); }
                to   { opacity: 1; transform: translateX(0) scale(1); }
            }

            @keyframes laraNodeGlow {
                0%   { box-shadow: inset 0 0 0 1px var(--accent), inset 0 0 0 9999px var(--accent-subtle); background: var(--accent-subtle); }
                40%  { box-shadow: inset 0 0 0 1px var(--accent), inset 0 0 0 9999px var(--accent-subtle); }
                100% { box-shadow: inset 0 0 0 1px transparent,   inset 0 0 0 9999px transparent; background: transparent; }
            }
        `,
    ];

    constructor() {
        super();
        this.headerIcon = 'box';
        this.headerTitle = '';
        this.colorToken = 'var(--accent)';
        this.expanded = false;
        this._laraGlow = false;
        this.useEvent('flows/lara/node_updated', () => {
            this._laraGlow = true;
            window.setTimeout(() => { this._laraGlow = false; }, 3200);
        });
    }

    _toggleExpand() {
        const next = !this.expanded;
        this.emit('expand-change', { expanded: next });
    }

    _close() {
        this.emit('close');
    }

    render() {
        return html`
            <div class="panel-backdrop" @click=${() => this.emit('expand-change', { expanded: false })}></div>
            <div class="panel-header">
                <div class="panel-title">
                    <div class="panel-icon" style=${`background: color-mix(in oklab, ${this.colorToken} 15%, transparent); color: ${this.colorToken};`}>
                        <platform-icon name=${this.headerIcon} size="18"></platform-icon>
                    </div>
                    <div class="panel-name">${this.headerTitle}</div>
                </div>
                <div class="panel-actions">
                    <button class="panel-btn expand" type="button" title=${this.t(this.expanded ? 'floating_panel.collapse' : 'floating_panel.expand')} @click=${this._toggleExpand}>
                        <platform-icon name=${this.expanded ? 'minimize' : 'fullscreen'} size="14"></platform-icon>
                    </button>
                    <button class="panel-btn" type="button" title=${this.t('floating_panel.close')} @click=${this._close}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </button>
                </div>
            </div>
            <div class="panel-body" ?data-lara-glow=${this._laraGlow}>
                <slot></slot>
            </div>
        `;
    }
}

customElements.define('flows-floating-panel', FlowsFloatingPanel);

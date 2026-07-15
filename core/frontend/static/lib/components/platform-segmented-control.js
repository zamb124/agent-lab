/**
 * platform-segmented-control — pill segmented selector (tabs / mode toggle).
 *
 * Items: { value, label?, icon?, title?, disabled?, indicator?, closable? }
 * Events: change { value }, segment-close { value }
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

/**
 * @param {unknown} item
 * @returns {{ value: string, label: string, icon: string, title: string, disabled: boolean, indicator: boolean, closable: boolean } | null}
 */
function _normalizeItem(item) {
    if (!item || typeof item !== 'object') {
        return null;
    }
    const value = item.value;
    if (typeof value !== 'string' || value.length === 0) {
        return null;
    }
    const label = typeof item.label === 'string' ? item.label : '';
    const icon = typeof item.icon === 'string' ? item.icon : '';
    const title = typeof item.title === 'string' && item.title.length > 0
        ? item.title
        : (label.length > 0 ? label : value);
    return {
        value,
        label,
        icon,
        title,
        disabled: Boolean(item.disabled),
        indicator: Boolean(item.indicator),
        closable: Boolean(item.closable),
    };
}

export class PlatformSegmentedControl extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: String },
        items: { type: Array },
        density: { type: String, reflect: true },
        iconOnly: { type: Boolean, attribute: 'icon-only', reflect: true },
        fullWidth: { type: Boolean, attribute: 'full-width', reflect: true },
        orientation: { type: String, reflect: true },
        ariaLabel: { type: String, attribute: 'aria-label' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                max-width: 100%;
                min-width: 0;
            }
            :host([full-width]) {
                display: flex;
                width: 100%;
            }
            .root {
                display: inline-flex;
                align-items: stretch;
                gap: 2px;
                padding: 3px;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                max-width: 100%;
                min-width: 0;
                box-sizing: border-box;
            }
            :host([full-width]) .root {
                width: 100%;
            }
            :host([orientation='vertical']) {
                display: flex;
                width: 100%;
            }
            :host([orientation='vertical']) .root {
                flex-direction: column;
                width: 100%;
                align-items: stretch;
            }
            :host([orientation='vertical']) .segment-wrap {
                width: 100%;
            }
            :host([orientation='vertical']) .segment {
                width: 100%;
                justify-content: flex-start;
                padding: 0 var(--space-3);
            }
            .segment-wrap {
                display: inline-flex;
                align-items: stretch;
                border-radius: var(--radius-full);
                flex-shrink: 0;
                max-width: 100%;
            }
            :host([full-width]) .segment-wrap {
                flex: 1 1 0;
                min-width: 0;
            }
            .segment {
                position: relative;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-1);
                border: none;
                border-radius: inherit;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font: inherit;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                transition: var(--motion-transition-interactive);
                box-sizing: border-box;
                white-space: nowrap;
            }
            :host([density='dense']) .segment {
                min-height: 32px;
                padding: 0 var(--space-2);
            }
            :host([density='compact']) .segment {
                min-height: 28px;
                padding: 0 var(--space-2);
                font-size: var(--text-xs);
            }
            :host(:not([density])) .segment,
            :host([density='default']) .segment {
                min-height: 36px;
                padding: 0 var(--space-3);
            }
            :host([icon-only]) .segment {
                width: 36px;
                min-width: 36px;
                padding: 0;
            }
            :host([icon-only][density='dense']) .segment {
                width: 32px;
                min-width: 32px;
            }
            :host([full-width]) .segment {
                flex: 1 1 0;
                min-width: 0;
            }
            .segment:hover:not(:disabled) {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .segment[data-active='true'] {
                background: var(--accent-subtle);
                color: var(--accent);
                box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 24%, transparent);
            }
            .segment:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .segment-label {
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .indicator {
                position: absolute;
                top: 2px;
                right: 2px;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--warning);
                box-shadow: 0 0 6px var(--warning);
                pointer-events: none;
            }
            .segment-close {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 24px;
                min-width: 24px;
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                font: inherit;
                font-size: 16px;
                line-height: 1;
                padding: 0;
            }
            .segment-close:hover {
                color: var(--error);
            }
            .segment-wrap[data-active='true'] .segment-close {
                color: var(--text-secondary);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.items = [];
        this.density = 'default';
        this.iconOnly = false;
        this.fullWidth = false;
        this.orientation = 'horizontal';
        this.ariaLabel = '';
    }

    _normalizedItems() {
        const out = [];
        for (const raw of this.items) {
            const item = _normalizeItem(raw);
            if (item) {
                out.push(item);
            }
        }
        return out;
    }

    _select(item) {
        if (item.disabled || item.value === this.value) {
            return;
        }
        this.value = item.value;
        this.emit('change', { value: item.value });
    }

    _close(e, item) {
        e.stopPropagation();
        this.emit('segment-close', { value: item.value });
    }

    render() {
        const items = this._normalizedItems();
        const groupLabel = typeof this.ariaLabel === 'string' && this.ariaLabel.length > 0
            ? this.ariaLabel
            : nothing;
        return html`
            <div class="root" role="group" aria-label=${groupLabel}>
                ${items.map((item) => {
                    const active = item.value === this.value;
                    return html`
                        <div class="segment-wrap" data-active=${active ? 'true' : 'false'}>
                            <button
                                type="button"
                                class="segment"
                                data-active=${active ? 'true' : 'false'}
                                title=${item.title}
                                aria-label=${item.title}
                                aria-pressed=${active ? 'true' : 'false'}
                                ?disabled=${item.disabled}
                                @click=${() => this._select(item)}
                            >
                                ${item.icon
                                    ? html`<platform-icon name=${item.icon} size="14"></platform-icon>`
                                    : nothing}
                                ${!this.iconOnly && item.label
                                    ? html`<span class="segment-label">${item.label}</span>`
                                    : nothing}
                                ${item.indicator ? html`<span class="indicator"></span>` : nothing}
                            </button>
                            ${item.closable
                                ? html`
                                    <button
                                        type="button"
                                        class="segment-close"
                                        title=${this.t('platform.segmented_close')}
                                        aria-label=${this.t('platform.segmented_close')}
                                        @click=${(e) => this._close(e, item)}
                                    >×</button>
                                `
                                : nothing}
                        </div>
                    `;
                })}
            </div>
        `;
    }
}

customElements.define('platform-segmented-control', PlatformSegmentedControl);

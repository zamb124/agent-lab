import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../tag-input.js';

export class PlatformFieldArray extends PlatformElement {
    static properties = {
        value: { type: Array },
        mode: { type: String },
        disabled: { type: Boolean },
        flat: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }

            .view-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }

            .chip {
                display: inline-flex;
                align-items: center;
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                background: var(--glass-tint-medium);
                color: var(--text-primary);
                border-radius: var(--radius-sm);
                border: 1px solid var(--glass-border-subtle);
            }

            .empty {
                font-size: var(--text-sm);
                color: var(--text-disabled);
                font-style: italic;
            }
        `,
    ];

    constructor() {
        super();
        this.value = [];
        this.mode = 'view';
        this.disabled = false;
        this.flat = false;
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.detail.tags },
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        const items = Array.isArray(this.value) ? this.value : [];

        if (this.mode === 'view') {
            if (items.length === 0) {
                return html`<span class="empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
            }
            return html`
                <div class="view-chips">
                    ${items.map(item => html`<span class="chip">${item}</span>`)}
                </div>
            `;
        }

        return html`
            <tag-input
                .tags=${items}
                placeholder=${(this.t('platform_field.array_placeholder') || 'platform_field.array_placeholder')}
                ?readonly=${this.disabled}
                ?flat=${this.flat === true}
                @change=${this._onChange}
            ></tag-input>
        `;
    }
}

customElements.define('platform-field-array', PlatformFieldArray);

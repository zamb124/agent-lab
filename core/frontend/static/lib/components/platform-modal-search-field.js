/**
 * Компактный поиск для header/toolbar/sidebar модалок: dense pill, radius-full, glass-фон.
 */
import { html, css } from '../../assets/js/lit/lit.min.js';
import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';
import './fields/platform-field.js';

export class PlatformModalSearchField extends PlatformElement {
    static properties = {
        value: { type: String },
        placeholder: { type: String },
        layout: { type: String, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                box-sizing: border-box;
                font-size: var(--text-sm);
                line-height: 1;
                --field-pill-bg: var(--glass-tint-medium);
                --field-pill-border: var(--glass-border-subtle);
                --field-pill-compact-radius: var(--radius-full);
                --field-pill-compact-padding-y: 4px;
                --field-pill-compact-padding-x: 10px;
                --field-pill-dense-padding-y: 2px;
                --field-pill-dense-padding-x: 10px;
                --field-pill-compact-input-size: var(--text-sm);
                --field-pill-compact-input-weight: var(--font-normal);
                --field-pill-compact-gap: 2px;
            }

            :host([layout='header']) {
                flex: 0 1 220px;
                max-width: min(220px, 34vw);
                min-width: 120px;
            }

            :host([layout='toolbar']) {
                flex: 0 0 170px;
                max-width: 170px;
                min-width: 140px;
            }

            :host([layout='fill']) {
                width: 100%;
                min-width: 0;
            }

            platform-field {
                display: block;
                width: 100%;
            }

            platform-icon[slot='prefix'] {
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.placeholder = '';
        this.layout = 'header';
    }

    /**
     * @param {CustomEvent<{ value?: unknown }>} e
     */
    _onChange(e) {
        const rawValue = e.detail?.value;
        if (typeof rawValue !== 'string') {
            throw new TypeError('platform-modal-search-field: change expects string detail.value');
        }
        this.emit('change', { value: rawValue });
    }

    render() {
        return html`
            <platform-field
                type="string"
                mode="edit"
                pill-density="dense"
                input-type="search"
                .value=${this.value}
                .placeholder=${this.placeholder}
                @change=${this._onChange}
            >
                <platform-icon slot="prefix" name="search" size="12"></platform-icon>
            </platform-field>
        `;
    }
}

customElements.define('platform-modal-search-field', PlatformModalSearchField);

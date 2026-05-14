import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../tag-input.js';

/**
 * type="array": свободный ввод через tag-input или ограничение `config.allowed_values`.
 * `config.preserve_case: true` — без toLowerCase при свободном вводе (см. tag-input preserve-case).
 */
export class PlatformFieldArray extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: Array },
        mode: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
        placeholder: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                width: 100%;
            }

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

            .allowed-wrap {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                min-height: var(--input-height);
                box-sizing: border-box;
            }

            .allowed-wrap:focus-within {
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-subtle);
            }

            .enum-chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px var(--space-2);
                font-size: var(--text-sm);
                background: var(--accent-subtle);
                color: var(--accent);
                border-radius: var(--radius-full);
            }

            .enum-chip button {
                background: none;
                border: none;
                padding: 0;
                margin: 0;
                color: var(--accent);
                cursor: pointer;
                font-size: var(--text-base);
                line-height: 1;
            }

            .add-select {
                flex: 1;
                min-width: 120px;
                border: none;
                background: transparent;
                color: var(--text-primary);
                padding: 4px;
                font: inherit;
                outline: none;
                cursor: pointer;
            }
        `,
    ];

    constructor() {
        super();
        this.value = [];
        this.mode = 'view';
        this.disabled = false;
        this.config = {};
        this.placeholder = '';
    }

    _cfg() {
        return this.config !== null && typeof this.config === 'object' ? this.config : {};
    }

    _allowedValues() {
        const raw = this._cfg().allowed_values;
        if (!Array.isArray(raw) || raw.length === 0) {
            return [];
        }
        const out = [];
        for (let i = 0; i < raw.length; i += 1) {
            if (typeof raw[i] !== 'string' || raw[i] === '') {
                throw new Error(`platform-field-array: config.allowed_values[${i}] must be non-empty string`);
            }
            out.push(raw[i]);
        }
        return out;
    }

    _preserveCase() {
        return this._cfg().preserve_case === true;
    }

    _resolvedPlaceholder() {
        if (typeof this.placeholder === 'string' && this.placeholder !== '') {
            return this.placeholder;
        }
        const t = this.t('platform_field.array_placeholder');
        if (typeof t !== 'string' || t === '') {
            throw new Error('platform-field-array: array_placeholder i18n missing');
        }
        return t;
    }

    _emitValue(next) {
        this.value = Array.isArray(next) ? [...next] : [];
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: next },
            bubbles: true,
            composed: true,
        }));
    }

    _onTagInputChange(e) {
        e.stopPropagation();
        if (!e.detail || !Array.isArray(e.detail.tags)) {
            return;
        }
        const tags = e.detail.tags;
        this._emitValue(tags);
    }

    _onSelectAdd(e) {
        e.stopPropagation();
        const sel = e.target;
        if (!(sel instanceof HTMLSelectElement)) {
            throw new Error('platform-field-array: expected select change');
        }
        const v = sel.value;
        sel.value = '';
        if (!v) return;
        const allowed = this._allowedValues();
        if (!allowed.includes(v)) {
            throw new Error('platform-field-array: value not in allowed_values');
        }
        const list = Array.isArray(this.value) ? [...this.value] : [];
        if (list.includes(v)) return;
        this._emitValue([...list, v]);
    }

    _removeAllowedAt(index) {
        const list = Array.isArray(this.value) ? [...this.value] : [];
        if (index < 0 || index >= list.length) {
            throw new Error('platform-field-array: remove index out of range');
        }
        list.splice(index, 1);
        this._emitValue(list);
    }

    render() {
        const items = Array.isArray(this.value) ? this.value : [];
        const allowed = this._allowedValues();
        const enumMode = allowed.length > 0;
        const placeholder = this._resolvedPlaceholder();

        if (this.mode === 'view') {
            if (items.length === 0) {
                return html`<span class="field-pill-empty">${this.t('platform_field.empty_value')}</span>`;
            }
            return html`
                <div class="view-chips">
                    ${items.map((item) => html`<span class="chip">${item}</span>`)}
                </div>
            `;
        }

        if (this.disabled) {
            return html`
                <div class="view-chips">
                    ${items.map((item) => html`<span class="chip">${item}</span>`)}
                </div>
            `;
        }

        if (enumMode) {
            const available = allowed.filter((x) => !items.includes(x));
            return html`
                <div class="allowed-wrap">
                    ${items.map((tag, i) => html`
                        <span class="enum-chip">
                            ${tag}
                            <button
                                type="button"
                                aria-label=${this.t('platform_field.array_remove_value')}
                                @click=${() => this._removeAllowedAt(i)}
                            >×</button>
                        </span>
                    `)}
                    <select
                        class="add-select"
                        data-canon="combobox"
                        aria-label=${placeholder}
                        @change=${this._onSelectAdd}
                    >
                        <option value="">${placeholder}</option>
                        ${available.map((v) => html`<option value=${v}>${v}</option>`)}
                    </select>
                </div>
            `;
        }

        return html`
            <tag-input
                .tags=${items}
                placeholder=${placeholder}
                ?preserve-case=${this._preserveCase()}
                ?readonly=${this.disabled}
                @change=${this._onTagInputChange}
            ></tag-input>
        `;
    }
}

customElements.define('platform-field-array', PlatformFieldArray);

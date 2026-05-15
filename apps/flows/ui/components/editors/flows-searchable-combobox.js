/**
 * flows-searchable-combobox — одна строка: поиск по options, выбор из списка
 * или произвольный id при blur. Событие: emit('change', { value }).
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

/**
 * @param {unknown} o
 * @returns {{ value: string, label: string } | null}
 */
function _asOption(o) {
    if (!o || typeof o !== 'object') {
        return null;
    }
    const value = o.value;
    const label = o.label;
    if (typeof value !== 'string') {
        return null;
    }
    if (typeof label !== 'string') {
        return { value, label: value };
    }
    return { value, label };
}

export class FlowsSearchableCombobox extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        value: { type: String },
        options: { type: Array },
        label: { type: String },
        placeholder: { type: String },
        emptyLabel: { type: String },
        ariaLabel: { type: String },
        compact: { type: Boolean, reflect: true },
        _open: { type: Boolean, state: true },
        _input: { type: String, state: true },
        _editing: { type: Boolean, state: true },
    };

    static styles = [
        ...PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }
            .root {
                position: relative;
                width: 100%;
                min-width: 0;
            }
            .combo-field {
                width: 100%;
                box-sizing: border-box;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: var(--field-pill-gap, 4px);
                padding: var(--field-pill-padding-y, 8px) var(--field-pill-padding-x, 12px);
                border-radius: var(--field-pill-radius, var(--radius-lg, 12px));
                border: 1px solid var(--field-pill-border, var(--border-default));
                background: var(--field-pill-bg, var(--glass-solid-subtle));
            }
            .combo-field.plain {
                display: block;
                padding: 0;
                border: none;
                border-radius: 0;
                background: transparent;
            }
            :host([compact]) .combo-field:not(.plain) {
                --field-pill-gap: var(--field-pill-compact-gap, 4px);
                --field-pill-padding-y: var(--field-pill-compact-padding-y, 6px);
                --field-pill-padding-x: var(--field-pill-compact-padding-x, 12px);
                --field-pill-radius: var(--field-pill-compact-radius, var(--radius-md, 8px));
                --field-pill-input-size: var(--field-pill-compact-input-size, var(--text-sm, 14px));
                --field-pill-input-weight: var(--field-pill-compact-input-weight, var(--font-medium, 500));
                --field-pill-number-spin-height: 34px;
                gap: var(--field-pill-gap);
                padding: var(--field-pill-padding-y) var(--field-pill-padding-x);
                border-radius: var(--field-pill-radius);
            }
            .combo-field:focus-within {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            .combo-field.plain:focus-within {
                border-color: transparent;
                box-shadow: none;
            }
            .combo-label {
                display: block;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--field-pill-label-size, var(--text-xs, 12px));
                line-height: var(--field-pill-label-line, 1.1);
                font-weight: var(--field-pill-label-weight, var(--font-semibold, 600));
                text-transform: uppercase;
                letter-spacing: var(--field-pill-label-letter, 0.04em);
                color: var(--field-pill-label-color, var(--text-tertiary));
            }
            input {
                width: 100%;
                box-sizing: border-box;
                min-width: 0;
                min-height: var(--field-pill-number-spin-height, 38px);
                padding: 0;
                border: none;
                border-radius: 0;
                background: transparent;
                color: var(--field-pill-input-color, var(--text-primary));
                font: inherit;
                font-size: var(--field-pill-input-size, var(--text-sm, 14px));
                font-weight: var(--field-pill-input-weight, var(--font-medium, 500));
                line-height: var(--field-pill-input-line, 1.35);
                outline: none;
            }
            :host([compact]) input {
                min-height: var(--field-pill-number-spin-height);
            }
            .combo-field.plain input {
                min-height: var(--input-height, 40px);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: inherit;
                font-weight: inherit;
            }
            input::placeholder {
                color: var(--text-disabled);
                font-weight: var(--font-normal, 400);
            }
            input:focus {
                outline: none;
            }
            .combo-field.plain input:focus {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            .list {
                position: absolute;
                top: 100%;
                left: 0;
                right: 0;
                margin: var(--space-1) 0 0;
                padding: var(--space-1) 0;
                list-style: none;
                max-height: 12rem;
                overflow-y: auto;
                z-index: 50;
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                box-shadow: var(--shadow-md, 0 4px 16px rgba(0, 0, 0, 0.12));
            }
            .item {
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
            .item:hover,
            .item[aria-selected="true"] {
                background: var(--accent-subtle);
            }
            .item-muted {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.options = Object.freeze([]);
        this.label = '';
        this.placeholder = '';
        this.emptyLabel = '';
        this.ariaLabel = '';
        this.compact = false;
        this._open = false;
        this._input = '';
        this._editing = false;
        /** @type {number | null} */
        this._blurHandle = null;
    }

    _opts() {
        const src = this.options;
        if (!Array.isArray(src)) {
            return [];
        }
        const out = [];
        for (const raw of src) {
            const o = _asOption(raw);
            if (o) {
                out.push(o);
            }
        }
        return out;
    }

    _displayForValue(v) {
        if (v === null || v === undefined || v === '') {
            return '';
        }
        const s = String(v);
        for (const o of this._opts()) {
            if (o.value === s) {
                if (o.label.length > 0) {
                    return o.label;
                }
                return o.value;
            }
        }
        return s;
    }

    _queryLower() {
        return this._input.trim().toLowerCase();
    }

    _filtered() {
        const all = this._opts();
        const q = this._queryLower();
        if (q.length === 0) {
            return all;
        }
        const out = [];
        for (const o of all) {
            if (o.value.toLowerCase().indexOf(q) >= 0) {
                out.push(o);
            } else if (o.label.toLowerCase().indexOf(q) >= 0) {
                out.push(o);
            }
        }
        return out;
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('value') && !this._editing) {
            this._input = this._displayForValue(this.value);
        }
        if (changed.has('options') && !this._editing) {
            this._input = this._displayForValue(this.value);
        }
    }

    _emitIfChanged(next) {
        const s = next === null || next === undefined ? '' : String(next);
        if (s === this.value) {
            return;
        }
        this.value = s;
        this.emit('change', { value: s });
    }

    _commit() {
        const t = this._input.trim();
        if (t.length === 0) {
            this._emitIfChanged('');
            this._input = '';
            return;
        }
        for (const o of this._opts()) {
            if (o.value === t) {
                this._emitIfChanged(o.value);
                this._input = o.label.length > 0 ? o.label : o.value;
                return;
            }
            if (o.label === t) {
                this._emitIfChanged(o.value);
                this._input = o.label.length > 0 ? o.label : o.value;
                return;
            }
        }
        const f = this._filtered();
        if (f.length === 1) {
            const o = f[0];
            this._emitIfChanged(o.value);
            this._input = o.label.length > 0 ? o.label : o.value;
            return;
        }
        this._emitIfChanged(t);
        this._input = t;
    }

    /**
     * Сохраняет введённое значение без ожидания blur (нужно перед внешним «Применить»).
     */
    flush() {
        this._clearBlurHandle();
        this._editing = false;
        this._open = false;
        this._commit();
    }

    _selectOption(v, display) {
        const s = v === null || v === undefined ? '' : String(v);
        this._emitIfChanged(s);
        this._input = display;
        this._open = false;
    }

    _onFocus() {
        this._clearBlurHandle();
        this._editing = true;
        this._open = true;
    }

    _onInput(e) {
        const t = e.target;
        this._input = t && 'value' in t ? t.value : '';
        this._open = true;
    }

    _onBlur() {
        this._editing = false;
        this._clearBlurHandle();
        this._blurHandle = window.setTimeout(() => {
            this._blurHandle = null;
            this._open = false;
            this._commit();
        }, 200);
    }

    _clearBlurHandle() {
        if (this._blurHandle !== null && this._blurHandle !== undefined) {
            window.clearTimeout(this._blurHandle);
            this._blurHandle = null;
        }
    }

    _onEmptyMouseDown(e) {
        e.preventDefault();
        this._clearBlurHandle();
        this._editing = false;
        this._selectOption('', '');
    }

    _onOptionMouseDown(e, o) {
        e.preventDefault();
        this._clearBlurHandle();
        this._editing = false;
        const disp = o.label.length > 0 ? o.label : o.value;
        this._selectOption(o.value, disp);
    }

    disconnectedCallback() {
        this._clearBlurHandle();
        super.disconnectedCallback();
    }

    _listItems() {
        const hasEmpty = typeof this.emptyLabel === 'string' && this.emptyLabel.length > 0;
        const rows = this._filtered();
        if (!this._open) {
            return null;
        }
        return html`
            <ul class="list" role="listbox">
                ${hasEmpty
                    ? html`
                        <li
                            class="item item-muted"
                            role="option"
                            @mousedown=${this._onEmptyMouseDown}
                        >${this.emptyLabel}</li>
                    `
                    : null}
                ${rows.map(
                    (o) => html`
                        <li
                            class="item"
                            role="option"
                            @mousedown=${(e) => this._onOptionMouseDown(e, o)}
                        >
                            <div>${o.label.length > 0 ? o.label : o.value}</div>
                            <div class="item-muted">${o.value}</div>
                        </li>
                    `,
                )}
            </ul>
        `;
    }

    render() {
        const hasLabel = typeof this.label === 'string' && this.label.length > 0;
        const aria = typeof this.ariaLabel === 'string' && this.ariaLabel.length > 0
            ? this.ariaLabel
            : this.placeholder;
        const tip =
            typeof this.ariaLabel === 'string' && this.ariaLabel.length > 0
                ? this.ariaLabel
                : (typeof this.placeholder === 'string' && this.placeholder.length > 0 ? this.placeholder : '');
        return html`
            <div class="root">
                <div class="combo-field ${hasLabel ? '' : 'plain'}">
                    ${hasLabel ? html`<span class="combo-label">${this.label}</span>` : nothing}
                    <input
                        data-canon="combobox"
                        type="text"
                        .value=${this._input}
                        placeholder=${this.placeholder}
                        aria-label=${aria}
                        title=${tip.length > 0 ? tip : nothing}
                        @focus=${this._onFocus}
                        @input=${this._onInput}
                        @blur=${this._onBlur}
                    />
                </div>
                ${this._listItems()}
            </div>
        `;
    }
}

customElements.define('flows-searchable-combobox', FlowsSearchableCombobox);

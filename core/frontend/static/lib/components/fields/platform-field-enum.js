import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

/**
 * Канонический enum-подкомпонент.
 *
 * `config.values` поддерживает две формы:
 *   1. Массив строк: `['active', 'archived']`
 *   2. Массив объектов `{value, label}`: `[{ value: 'active', label: 'Активно' }, ...]`
 *
 * `view`-режим выводит `label` (или `value`, если label не задан).
 * `edit`-режим рисует `<select>` с `<option value=value>label</option>`.
 * Плейсхолдер «значение по умолчанию»: `{ value: '', label: '...' }` (пустой value допустим только с непустым label).
 * Сырой `''` в массиве строк запрещён — используйте объект с label.
 *
 * Для динамического списка с длинным lookup'ом (например, выбор flow) — передавайте
 * массив объектов; иначе пользователь видит технический id вместо человекочитаемого имени.
 */

function _normalizeOption(raw) {
    if (typeof raw === 'string') {
        if (raw === '') {
            throw new Error(
                "platform-field-enum: empty string in values[] is invalid; use { value: '', label: '...' }",
            );
        }
        return { value: raw, label: raw };
    }
    if (raw && typeof raw === 'object') {
        if (!('value' in raw) || typeof raw.value !== 'string') {
            throw new Error('platform-field-enum: option.value must be a string');
        }
        const value = raw.value;
        if (value === '') {
            if (typeof raw.label !== 'string' || raw.label.length === 0) {
                throw new Error(
                    'platform-field-enum: option with empty value requires non-empty option.label',
                );
            }
            return { value: '', label: raw.label };
        }
        const label = typeof raw.label === 'string' && raw.label.length > 0 ? raw.label : value;
        return { value, label };
    }
    throw new Error(`platform-field-enum: option must be string or {value, label}; got ${typeof raw}`);
}

export class PlatformFieldEnum extends PlatformElement {
    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            .enum-chip {
                display: inline-flex;
                align-items: center;
                padding: var(--space-1) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--field-pill-input-weight);
                background: var(--accent-subtle);
                color: var(--text-primary);
                border-radius: var(--radius-full);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.mode = 'view';
        this.disabled = false;
        this.config = {};
    }

    get _enumOptions() {
        const c = this.config;
        if (!c || typeof c !== 'object') {
            return [];
        }
        const v = c.values;
        if (!Array.isArray(v)) {
            return [];
        }
        return v.map(_normalizeOption);
    }

    _labelFor(value) {
        for (const opt of this._enumOptions) {
            if (opt.value === value) {
                return opt.label;
            }
        }
        return value;
    }

    _onChange(e) {
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: e.target.value },
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        if (this.mode === 'view') {
            if (this.value == null || this.value === '') {
                return html`<span class="field-pill-empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
            }
            return html`<span class="enum-chip">${this._labelFor(this.value)}</span>`;
        }

        const options = this._enumOptions;
        const hasEmptyValueOption = options.some((o) => o.value === '');
        const blankOption = hasEmptyValueOption
            ? null
            : html`<option value="">--</option>`;
        return html`
            <select
                class="field-pill-select"
                .value=${this.value ?? ''}
                ?disabled=${this.disabled}
                @change=${this._onChange}
            >
                ${blankOption}
                ${options.map((opt) => html`
                    <option value=${opt.value} ?selected=${this.value === opt.value}>${opt.label}</option>
                `)}
            </select>
        `;
    }
}

customElements.define('platform-field-enum', PlatformFieldEnum);

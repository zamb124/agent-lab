import { html, css, nothing } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

/**
 * Enum — `platform-field` type `enum`.
 *
 * `config.values`: строки `['active', ...]` или `{ value, label }[]`.
 * Пустой string как value только через `{ value: '', label: '...' }`.
 *
 * Edit: выпадающий список в стиле field-pill с **инлайн-поиском** (одно поле
 * фильтрует label/value). Нативный `<select>` не используется.
 *
 * Если в `values` нет option с `value: ''`, в начало списка добавляется
 * синтетическая строка «пустое значение» (подпись — i18n `enum_blank_fallback`),
 * эквивалент прежнему префикс-`<option value="">`.
 */

function normalizeOption(raw) {
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
        const optValue = raw.value;
        if (optValue === '') {
            if (typeof raw.label !== 'string' || raw.label.length === 0) {
                throw new Error(
                    'platform-field-enum: option with empty value requires non-empty option.label',
                );
            }
            return { value: '', label: raw.label };
        }
        const label = typeof raw.label === 'string' && raw.label.length > 0 ? raw.label : optValue;
        return { value: optValue, label };
    }
    throw new Error(`platform-field-enum: option must be string or {value, label}; got ${typeof raw}`);
}

function normalizedQuery(raw) {
    return raw == null ? '' : String(raw).trim().toLowerCase();
}

export class PlatformFieldEnum extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
        placeholder: { type: String },
        _filterQuery: { type: String, state: true },
        _listOpen: { type: Boolean, state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
                width: 100%;
                flex: 1;
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
        this.placeholder = '';
        this._filterQuery = '';
        this._listOpen = false;
        this._skipBlurSync = false;
        this._deferOptionFilter = false;
        this._listDomId = `pf-enum-${Math.random().toString(36).slice(2, 11)}`;
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (this.mode !== 'edit') {
            return;
        }
        if (changed.has('value') || changed.has('config')) {
            this._filterQuery = this._displayTextSyncedToValue();
        }
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
        return v.map(normalizeOption);
    }

    get _displayOptions() {
        const opts = this._enumOptions.slice();
        const hasEmpty = opts.some((o) => o.value === '');
        if (!hasEmpty) {
            const blankLabel = this.t('platform_field.enum_blank_fallback')
                ?? 'platform_field.enum_blank_fallback';
            opts.unshift({ value: '', label: blankLabel });
        }
        return opts;
    }

    /** @returns {{ value: string, label: string }[]} */
    get _filteredDisplayOptions() {
        const opts = this._displayOptions;
        if (this._deferOptionFilter) {
            return opts.slice();
        }
        const q = normalizedQuery(this._filterQuery);
        if (!q.length) {
            return opts.slice();
        }
        return opts.filter(
            (o) =>
                normalizedQuery(o.label).includes(q)
                || normalizedQuery(o.value).includes(q),
        );
    }

    /**
     * @param {string} value
     * @returns {string}
     */
    _labelForValue(value) {
        const normalized = value ?? '';
        for (const opt of this._displayOptions) {
            if (opt.value === normalized) {
                return opt.label;
            }
        }
        if (normalized === '') {
            return '';
        }
        return typeof value === 'string' ? value : String(value ?? '');
    }

    /**
     * @returns {string}
     */
    _displayTextSyncedToValue() {
        const v = this.value ?? '';
        return this._labelForValue(typeof v === 'string' ? v : String(v));
    }

    /** @param {MouseEvent} e */
    _onOptionMouseDown(e) {
        e.preventDefault();
    }

    /** @param {{ value: string, label: string }} opt */
    _pickOption(opt) {
        if (this.disabled) return;
        this._skipBlurSync = true;
        this._listOpen = false;
        this._deferOptionFilter = false;
        this._filterQuery = opt.label;
        const nextDetail = typeof opt.value === 'string' ? opt.value : String(opt.value);
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: nextDetail },
            bubbles: true,
            composed: true,
        }));
        this.requestUpdate();
    }

    _onFocus() {
        if (this.disabled) return;
        this._listOpen = true;
        this._deferOptionFilter = true;
    }

    /** @param {FocusEvent & { relatedTarget?: EventTarget | null }} e */
    _onBlur() {
        window.setTimeout(() => {
            if (this._skipBlurSync) {
                this._skipBlurSync = false;
                this._deferOptionFilter = false;
                this.requestUpdate();
                return;
            }
            this._deferOptionFilter = false;
            this._listOpen = false;
            const q = normalizedQuery(this._filterQuery);
            if (q.length > 0) {
                const exact = this._displayOptions.filter(
                    (o) =>
                        normalizedQuery(o.label) === q
                        || normalizedQuery(o.value) === q,
                );
                if (exact.length === 1 && exact[0].value !== (this.value ?? '')) {
                    this.dispatchEvent(new CustomEvent('change', {
                        detail: { value: exact[0].value },
                        bubbles: true,
                        composed: true,
                    }));
                }
            }
            this._filterQuery = this._displayTextSyncedToValue();
            this.requestUpdate();
        }, 160);
    }

    /** @param {InputEvent} e */
    _onFilterInput(e) {
        const t = e.target;
        if (!(t instanceof HTMLInputElement)) return;
        if (this.disabled) return;
        this._deferOptionFilter = false;
        this._filterQuery = t.value;
        this._listOpen = true;
    }

    /** @param {KeyboardEvent} e */
    _onFilterKeydown(e) {
        if (this.disabled) return;
        if (e.key === 'Escape') {
            e.stopPropagation();
            this._filterQuery = this._displayTextSyncedToValue();
            this._listOpen = false;
            this._deferOptionFilter = false;
            const t = e.target;
            if (t instanceof HTMLElement) t.blur();
            this.requestUpdate();
            return;
        }
        if (e.key === 'Enter') {
            e.preventDefault();
            if (!this._listOpen) {
                return;
            }
            const visible = this._filteredDisplayOptions;
            if (visible.length === 1) {
                this._pickOption(visible[0]);
            }
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!this._listOpen) {
                this._listOpen = true;
                this._deferOptionFilter = true;
                this.requestUpdate();
            }
        }
    }

    render() {
        if (this.mode === 'view') {
            if (this.value == null || this.value === '') {
                return html`<span class="field-pill-empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
            }
            const v = typeof this.value === 'string' ? this.value : String(this.value);
            return html`<span class="enum-chip">${this._labelForValue(v)}</span>`;
        }

        const ph = typeof this.placeholder === 'string' && this.placeholder !== ''
            ? this.placeholder
            : (this.t('platform_field.enum_search_placeholder')
                ?? 'platform_field.enum_search_placeholder');
        const ariaList = this.t('platform_field.enum_list_aria') ?? 'platform_field.enum_list_aria';

        const list = this._filteredDisplayOptions;

        const listBody = list.length === 0
            ? html`<li class="field-pill-enum-empty" role="option" aria-disabled="true">${this.t('platform_field.enum_no_matches') ?? 'platform_field.enum_no_matches'}</li>`
            : list.map((opt) => html`
                  <li
                      class=${`field-pill-enum-opt${(this.value ?? '') === opt.value ? ' field-pill-enum-opt--selected' : ''}`}
                      role="option"
                      aria-selected=${(this.value ?? '') === opt.value ? 'true' : 'false'}
                      data-enum-value=${opt.value}
                      @mousedown=${this._onOptionMouseDown}
                      @click=${() => this._pickOption(opt)}
                  >
                      ${opt.label}
                  </li>
              `);

        return html`
            <div class="field-pill-enum-wrap">
                <input
                    class="field-pill-input field-pill-enum-input"
                    type="text"
                    spellcheck="false"
                    autocomplete="off"
                    data-canon="search-as-you-type"
                    role="combobox"
                    aria-expanded=${this._listOpen && !this.disabled ? 'true' : 'false'}
                    aria-controls=${this._listDomId}
                    aria-autocomplete="list"
                    id=${`${this._listDomId}-input`}
                    placeholder=${ph}
                    .value=${this._filterQuery}
                    ?disabled=${this.disabled}
                    @input=${this._onFilterInput}
                    @focus=${this._onFocus}
                    @blur=${this._onBlur}
                    @keydown=${this._onFilterKeydown}
                />
                <span class="field-pill-enum-chevron" aria-hidden="true"></span>
                ${this._listOpen && !this.disabled
                    ? html`
                          <ul
                              id=${this._listDomId}
                              class="field-pill-enum-list"
                              role="listbox"
                              aria-label=${ariaList}
                          >
                              ${listBody}
                          </ul>
                      `
                    : nothing}
            </div>
        `;
    }
}

customElements.define('platform-field-enum', PlatformFieldEnum);

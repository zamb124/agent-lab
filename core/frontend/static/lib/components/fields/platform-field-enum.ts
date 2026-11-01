import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { isPlainRecord } from '../../events/payload.js';
import '../platform-popover.js';
import type { PlatformPopover } from '../platform-popover.js';

function enumText(value: string | null | undefined): string {
    return value === undefined || value === null ? '' : value;
}

/**
 * Перечисление — type `enum` у `platform-field`.
 *
 * `config.values`: строки `['active', ...]` или `{ value, label }[]`.
 * Пустой string как value только через `{ value: '', label: '...' }`.
 *
 * Edit: выпадающий список в стиле field-pill с **инлайн-поиском** (одно поле
 * фильтрует label/value). Нативный `<select>` не используется.
 *
 * Список живёт в `platform-popover`: он уносит слой в `document.body`, поэтому
 * список не обрезается `overflow` предков (floating panel, скролл редактора
 * ноды) и лежит выше панелей с большим z-index. Позиционирование, закрытие по
 * клику мимо и по Escape — тоже на попапе.
 *
 * Если в `values` нет option с `value: ''`, в начало списка добавляется
 * синтетическая строка «пустое значение» (подпись — i18n `enum_blank_fallback`),
 * эквивалент прежнему префикс-`<option value="">`.
 */

interface EnumOption {
    value: string;
    label: string;
}

function normalizeOption(raw: unknown): EnumOption {
    if (typeof raw === 'string') {
        if (raw === '') {
            throw new Error(
                "platform-field-enum: empty string in values[] is invalid; use { value: '', label: '...' }",
            );
        }
        return { value: raw, label: raw };
    }
    if (isPlainRecord(raw)) {
        const optValue = raw.value;
        if (typeof optValue !== 'string') {
            throw new Error('platform-field-enum: option.value must be a string');
        }
        const labelRaw = raw.label;
        if (optValue === '') {
            if (typeof labelRaw !== 'string' || labelRaw.length === 0) {
                throw new Error(
                    'platform-field-enum: option with empty value requires non-empty option.label',
                );
            }
            return { value: '', label: labelRaw };
        }
        const label = typeof labelRaw === 'string' && labelRaw.length > 0 ? labelRaw : optValue;
        return { value: optValue, label };
    }
    throw new Error(`platform-field-enum: option must be string or {value, label}; got ${typeof raw}`);
}

function normalizedQuery(raw: unknown): string {
    return raw == null ? '' : String(raw).trim().toLowerCase();
}

export class PlatformFieldEnum extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        value: { type: String },
        mode: { type: String },
        disabled: { type: Boolean },
        config: { type: Object },
        placeholder: { type: String },
        _filterQuery: { type: String, state: true },
        _listOpen: { type: Boolean, state: true },
    };

    declare value: string | null;
    declare mode: string;
    declare disabled: boolean;
    declare config: Record<string, unknown>;
    declare placeholder: string;
    declare _filterQuery: string;
    declare _listOpen: boolean;

    // Не реактивное поле: anchor нужен popover'у только в момент `?open`,
    // а `_listOpen` и так вызывает ререндер — state-поле давало лишний
    // update-цикл и варнинг "scheduled an update after an update completed".
    _anchor: HTMLElement | null;
    _skipBlurSync: boolean;
    _deferOptionFilter: boolean;
    _listDomId: string;

    static override styles: CSSResultGroup = [
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

            .enum-list {
                margin: 0;
                padding: var(--space-1) 0;
                list-style: none;
            }

            .enum-option {
                margin: 0;
                padding: var(--space-2) var(--space-3);
                cursor: pointer;
                font-size: var(--field-pill-readonly-muted-size);
                font-weight: var(--font-medium);
                line-height: var(--leading-tight);
                color: var(--text-primary);
            }

            .enum-option:hover,
            .enum-option:focus {
                outline: none;
                background: var(--accent-subtle);
            }

            .enum-option--selected {
                background: var(--glass-solid-subtle);
                font-weight: var(--font-semibold);
            }

            .enum-option--selected:hover {
                background: var(--accent-subtle);
            }

            .enum-empty {
                margin: 0;
                padding: var(--space-2) var(--space-3);
                font-size: var(--field-pill-readonly-muted-size);
                color: var(--text-tertiary);
                list-style: none;
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
        this._anchor = null;
    }

    override firstUpdated(changed: PropertyValues<this>): void {
        super.firstUpdated(changed);
        this._ensureAnchor();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (this._listOpen && !this.disabled) {
            // Список меняет высоту при фильтрации, поэтому попап пересчитывается
            // после каждого обновления содержимого.
            this.renderRoot?.querySelector<PlatformPopover>('platform-popover')?.reposition();
        }
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (this.mode !== 'edit') {
            return;
        }
        // Якорь до рендера, в котором popover открывается, — `.anchor` уже
        // связан к моменту `?open` (DOM существует: `_listOpen` поднимается
        // только пользовательским жестом после первого рендера).
        if (this._listOpen) {
            this._ensureAnchor();
        }
        // Пока список открыт — не затирать поисковый ввод при смене reference
        // `.config` у родителя (новый object на каждый render).
        if (this._listOpen) {
            return;
        }
        if (changed.has('value') || changed.has('config')) {
            this._filterQuery = this._displayTextSyncedToValue();
        }
    }

    /**
     * Якорь нужен до showPopover: иначе слой открывается без позиции
     * (static top-left) и outside-dismiss с null-anchor гасит его жестом открытия.
     */
    _ensureAnchor(): HTMLElement | null {
        if (this._anchor instanceof HTMLElement) {
            return this._anchor;
        }
        const wrap = this.renderRoot?.querySelector?.('.field-pill-enum-wrap');
        if (wrap instanceof HTMLElement) {
            this._anchor = wrap;
            return wrap;
        }
        return null;
    }

    get _enumOptions(): EnumOption[] {
        const config = this.config;
        if (!isPlainRecord(config)) {
            return [];
        }
        const values = config.values;
        if (!Array.isArray(values)) {
            return [];
        }
        const items: unknown[] = [];
        for (const item of values) items.push(item);
        return items.map(normalizeOption);
    }

    get _displayOptions(): EnumOption[] {
        const opts = this._enumOptions.slice();
        const hasEmpty = opts.some((o) => o.value === '');
        if (!hasEmpty) {
            const blankLabel = this.t('platform_field.enum_blank_fallback')
                ?? 'platform_field.enum_blank_fallback';
            opts.unshift({ value: '', label: blankLabel });
        }
        return opts;
    }

    get _filteredDisplayOptions(): EnumOption[] {
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

    _labelForValue(value: string | null | undefined): string {
        const normalized = enumText(value);
        for (const opt of this._displayOptions) {
            if (opt.value === normalized) {
                return opt.label;
            }
        }
        return normalized;
    }

    _displayTextSyncedToValue(): string {
        return this._labelForValue(enumText(this.value));
    }

    _renderList(): TemplateResult {
        const ariaList = this.t('platform_field.enum_list_aria') ?? 'platform_field.enum_list_aria';
        const list = this._filteredDisplayOptions;
        const listBody = list.length === 0
            ? html`<li class="enum-empty" role="option" aria-disabled="true">${this.t('platform_field.enum_no_matches') ?? 'platform_field.enum_no_matches'}</li>`
            : list.map((opt) => html`
                  <li
                      class=${`enum-option${enumText(this.value) === opt.value ? ' enum-option--selected' : ''}`}
                      role="option"
                      aria-selected=${enumText(this.value) === opt.value ? 'true' : 'false'}
                      data-enum-value=${opt.value}
                      @mousedown=${this._onOptionMouseDown}
                      @click=${() => this._pickOption(opt)}
                  >
                      ${opt.label}
                  </li>
              `);

        return html`
            <ul
                id=${this._listDomId}
                class="enum-list"
                role="listbox"
                aria-label=${ariaList}
            >
                ${listBody}
            </ul>
        `;
    }

    _onPopoverDismiss(): void {
        this._listOpen = false;
        this._deferOptionFilter = false;
        this._filterQuery = this._displayTextSyncedToValue();
        this.requestUpdate();
    }

    _onOptionMouseDown(e: MouseEvent): void {
        e.preventDefault();
    }

    _pickOption(opt: EnumOption): void {
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

    _openList(): void {
        if (this.disabled) return;
        this._ensureAnchor();
        this._listOpen = true;
        this._deferOptionFilter = true;
    }

    _onFocus(): void {
        if (this.disabled) return;
        this._openList();
    }

    _onChevronMouseDown(e: MouseEvent): void {
        e.preventDefault();
    }

    _onChevronClick(e: MouseEvent): void {
        e.preventDefault();
        e.stopPropagation();
        if (this.disabled) return;
        this._openList();
        const input = this.renderRoot?.querySelector('input.field-pill-enum-input');
        if (input instanceof HTMLInputElement) {
            input.focus();
        }
    }

    _onBlur(): void {
        window.setTimeout(() => {
            if (this._skipBlurSync) {
                this._skipBlurSync = false;
                this._deferOptionFilter = false;
                this.requestUpdate();
                return;
            }
            const popover = this.renderRoot?.querySelector('platform-popover');
            if (popover && document.activeElement && popover.contains(document.activeElement)) {
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
                const chosen = exact[0];
                if (exact.length === 1) {
                    if (chosen === undefined) {
                        throw new Error('platform-field-enum: exact option missing');
                    }
                    if (chosen.value !== enumText(this.value)) {
                        this.dispatchEvent(new CustomEvent('change', {
                            detail: { value: chosen.value },
                            bubbles: true,
                            composed: true,
                        }));
                    }
                }
            }
            this._filterQuery = this._displayTextSyncedToValue();
            this.requestUpdate();
        }, 160);
    }

    _onFilterInput(e: InputEvent): void {
        const t = e.target;
        if (!(t instanceof HTMLInputElement)) return;
        if (this.disabled) return;
        this._deferOptionFilter = false;
        this._filterQuery = t.value;
        this._listOpen = true;
    }

    _onFilterKeydown(e: KeyboardEvent): void {
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
                const only = visible[0];
                if (only === undefined) {
                    throw new Error('platform-field-enum: option missing');
                }
                this._pickOption(only);
            }
        }
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            if (!this._listOpen) {
                this._openList();
            }
        }
    }

    override render(): TemplateResult {
        if (this.mode === 'view') {
            if (this.value == null || this.value === '') {
                return html`<span class="field-pill-empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
            }
            const v = typeof this.value === 'string' ? this.value : String(this.value);
            return html`<span class="enum-chip">${this._labelForValue(v)}</span>`;
        }

        const ph = typeof this.placeholder === 'string' ? this.placeholder : '';
        const ariaList = this.t('platform_field.enum_list_aria') ?? 'platform_field.enum_list_aria';

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
                <button
                    class="field-pill-enum-chevron"
                    type="button"
                    aria-label=${ariaList}
                    aria-controls=${this._listDomId}
                    aria-expanded=${this._listOpen && !this.disabled ? 'true' : 'false'}
                    ?disabled=${this.disabled}
                    @mousedown=${this._onChevronMouseDown}
                    @click=${this._onChevronClick}
                ></button>
            </div>
            <platform-popover
                trigger="manual"
                role="listbox"
                placement="bottom-start"
                match-width
                offset="4"
                .anchor=${this._anchor}
                ?open=${this._listOpen && !this.disabled}
                @popover-dismiss=${this._onPopoverDismiss}
            >
                ${this._listOpen && !this.disabled ? this._renderList() : nothing}
            </platform-popover>
        `;
    }
}

customElements.define('platform-field-enum', PlatformFieldEnum);

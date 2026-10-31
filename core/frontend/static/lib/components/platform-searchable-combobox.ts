/**
 * platform-searchable-combobox — pill combobox: search options or commit free-form id on blur.
 * Emits `change` with `{ value }`. `flush()` commits without waiting for blur.
 *
 * Optional create-on-the-fly:
 *   - `createLabel` — row when query empty (e.g. "Create new…")
 *   - `createQueryLabel` — template with `{{query}}` when typed text has no exact match
 *   - emits `create` with `{ query: string }` (trimmed input; may be empty)
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { isPlainRecord } from '../events/payload.js';
import { PlatformPopover } from './platform-popover.js';
import './fields/platform-field-shell.js';

/**
 * @param {unknown} o
 * @returns {{ value: string, label: string } | null}
 */
export interface ComboboxOption {
    value: string;
    label: string;
}

function _asOption(o: unknown): ComboboxOption | null {
    if (!isPlainRecord(o)) {
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

/**
 * @param {string} template
 * @param {string} query
 */
function _formatCreateQueryLabel(template: string, query: string): string {
    if (template.indexOf('{{query}}') >= 0) {
        return template.split('{{query}}').join(query);
    }
    return `${template} ${query}`.trim();
}

export class PlatformSearchableCombobox extends PlatformElement {
    static override properties: PropertyDeclarations = {
        value: { type: String },
        options: { type: Array },
        label: { type: String },
        placeholder: { type: String },
        emptyLabel: { type: String },
        createLabel: { type: String },
        createQueryLabel: { type: String },
        ariaLabel: { type: String, attribute: 'aria-label' },
        compact: { type: Boolean, reflect: true },
        _open: { type: Boolean, state: true },
        _input: { type: String, state: true },
        _editing: { type: Boolean, state: true },
        _anchor: { state: true },
    };
    declare value: string;
    declare options: unknown[];
    declare label: string;
    declare placeholder: string;
    declare emptyLabel: string;
    declare createLabel: string;
    declare createQueryLabel: string;
    declare ariaLabel: string;
    declare compact: boolean;
    declare _open: boolean;
    declare _input: string;
    declare _editing: boolean;
    declare _anchor: HTMLElement | null;

    private _blurHandle: number | null;

    static override styles: CSSResultGroup = [
        ...(Array.isArray(PlatformElement.styles) ? PlatformElement.styles : [PlatformElement.styles]),
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
            .field-pill.plain {
                display: block;
                padding: 0;
                border: none;
                border-radius: 0;
                background: transparent;
            }
            .field-pill.plain:focus-within {
                border-color: transparent;
                box-shadow: none;
            }
            /* Компактные токены на :host — наследуются и в slotted input, и в shell. */
            :host([compact]) {
                --field-pill-input-size: var(--field-pill-compact-input-size);
                --field-pill-input-weight: var(--field-pill-compact-input-weight);
            }
            input {
                width: 100%;
                box-sizing: border-box;
                min-width: 0;
                min-height: var(--field-pill-number-spin-height);
                padding: 0;
                border: none;
                border-radius: 0;
                background: transparent;
                color: var(--field-pill-input-color);
                font: inherit;
                font-size: var(--field-pill-input-size);
                font-weight: var(--field-pill-input-weight);
                line-height: var(--field-pill-input-line);
                outline: none;
            }
            :host([compact]) input {
                min-height: var(--field-pill-number-spin-height);
            }
            .field-pill.plain input {
                min-height: var(--input-height);
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
                font-weight: var(--font-normal);
            }
            .field-pill.plain input:focus {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            .list {
                margin: 0;
                padding: var(--space-1) 0;
                list-style: none;
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
            .item-create {
                color: var(--accent);
                font-weight: var(--font-medium);
                border-top: 1px solid var(--border-subtle);
                margin-top: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.options = [];
        this.label = '';
        this.placeholder = '';
        this.emptyLabel = '';
        this.createLabel = '';
        this.createQueryLabel = '';
        this.ariaLabel = '';
        this.compact = false;
        this._open = false;
        this._input = '';
        this._editing = false;
        this._anchor = null;
        this._blurHandle = null;
    }

    _onPopoverDismiss() {
        this._open = false;
    }

    _opts(): ComboboxOption[] {
        const src = this.options;
        if (!Array.isArray(src)) {
            return [];
        }
        const out: ComboboxOption[] = [];
        for (const raw of src) {
            const o = _asOption(raw);
            if (o) {
                out.push(o);
            }
        }
        return out;
    }

    _displayForValue(v: unknown): string {
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

    _filtered(): ComboboxOption[] {
        const all = this._opts();
        const q = this._queryLower();
        if (q.length === 0) {
            return all;
        }
        const out: ComboboxOption[] = [];
        for (const o of all) {
            if (o.value.toLowerCase().indexOf(q) >= 0) {
                out.push(o);
            } else if (o.label.toLowerCase().indexOf(q) >= 0) {
                out.push(o);
            }
        }
        return out;
    }



    _emitIfChanged(next: unknown): void {
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
        const single = f.length === 1 ? f[0] : undefined;
        if (single) {
            this._emitIfChanged(single.value);
            this._input = single.label.length > 0 ? single.label : single.value;
            return;
        }
        this._emitIfChanged(t);
        this._input = t;
    }

    flush() {
        this._clearBlurHandle();
        this._editing = false;
        this._open = false;
        this._commit();
    }

    _selectOption(v: unknown, display: string): void {
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

    _onInput(e: Event) {
        const t = e.target;
        this._input = t && 'value' in t ? String(t.value) : '';
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

    _onEmptyMouseDown(e: Event) {
        e.preventDefault();
        this._clearBlurHandle();
        this._editing = false;
        this._selectOption('', '');
    }

    _onOptionMouseDown(e: Event, o: ComboboxOption): void {
        e.preventDefault();
        this._clearBlurHandle();
        this._editing = false;
        const disp = o.label.length > 0 ? o.label : o.value;
        this._selectOption(o.value, disp);
    }

    _createRow(): { query: string; label: string } | null {
        const baseCreate = typeof this.createLabel === 'string' ? this.createLabel.trim() : '';
        const queryTemplate = typeof this.createQueryLabel === 'string'
            ? this.createQueryLabel.trim()
            : '';
        if (baseCreate.length === 0 && queryTemplate.length === 0) {
            return null;
        }
        const query = this._input.trim();
        if (query.length === 0) {
            if (baseCreate.length === 0) {
                return null;
            }
            return { query: '', label: baseCreate };
        }
        for (const o of this._opts()) {
            if (o.value === query || o.label === query) {
                return null;
            }
        }
        if (queryTemplate.length > 0) {
            return { query, label: _formatCreateQueryLabel(queryTemplate, query) };
        }
        if (baseCreate.length === 0) {
            return null;
        }
        return { query, label: `${baseCreate}: ${query}` };
    }

    _onCreateMouseDown(e: Event) {
        e.preventDefault();
        this._clearBlurHandle();
        this._editing = false;
        this._open = false;
        const query = this._input.trim();
        this.emit('create', { query });
    }

    override disconnectedCallback(): void {
        this._clearBlurHandle();
        super.disconnectedCallback();
    }

    _listItems() {
        const hasEmpty = typeof this.emptyLabel === 'string' && this.emptyLabel.length > 0;
        const rows = this._filtered();
        const createRow = this._createRow();
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
                    (o: ComboboxOption) => html`
                        <li
                            class="item"
                            role="option"
                            @mousedown=${(e: Event) => this._onOptionMouseDown(e, o)}
                        >
                            <div>${o.label.length > 0 ? o.label : o.value}</div>
                            <div class="item-muted">${o.value}</div>
                        </li>
                    `,
                )}
                ${createRow
                    ? html`
                        <li
                            class="item item-create"
                            role="option"
                            data-create="true"
                            @mousedown=${this._onCreateMouseDown}
                        >${createRow.label}</li>
                    `
                    : null}
            </ul>
        `;
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (this._anchor === null) {
            const field = this.renderRoot?.querySelector?.('platform-field-shell')
                ?? this.renderRoot?.querySelector?.('.field-pill');
            if (field instanceof HTMLElement) {
                this._anchor = field;
            }
        }
        if (this._open) {
            const popover = this.renderRoot.querySelector('platform-popover');
            if (!(popover instanceof PlatformPopover)) {
                throw new Error('platform-searchable-combobox: open list popover is missing');
            }
            popover.reposition();
        }
        if ((changed.has('value') || changed.has('options')) && !this._editing) {
            this._input = this._displayForValue(this.value);
        }
    }

    override render(): TemplateResult {
        const hasLabel = typeof this.label === 'string' && this.label.length > 0;
        const aria = typeof this.ariaLabel === 'string' && this.ariaLabel.length > 0
            ? this.ariaLabel
            : this.placeholder;
        const tip =
            typeof this.ariaLabel === 'string' && this.ariaLabel.length > 0
                ? this.ariaLabel
                : (typeof this.placeholder === 'string' && this.placeholder.length > 0 ? this.placeholder : '');
        const floated = this._input.length > 0 || this._editing;
        const input = html`
            <input
                class="field-pill-input"
                data-canon="combobox"
                type="text"
                .value=${this._input}
                placeholder=${floated || !hasLabel ? this.placeholder : ''}
                aria-label=${aria}
                title=${tip.length > 0 ? tip : nothing}
                @focus=${this._onFocus}
                @input=${this._onInput}
                @blur=${this._onBlur}
            />
        `;
        return html`
            <div class="root">
                ${hasLabel
                    ? html`
                        <platform-field-shell
                            .label=${this.label}
                            ?floated=${floated}
                            editable
                            density=${this.compact ? 'compact' : 'default'}
                        >
                            ${input}
                        </platform-field-shell>
                    `
                    : html`<div class="field-pill plain">${input}</div>`}
                <platform-popover
                    trigger="manual"
                    role="listbox"
                    placement="bottom-start"
                    match-width
                    offset="4"
                    .anchor=${this._anchor}
                    ?open=${this._open}
                    @popover-dismiss=${this._onPopoverDismiss}
                >
                    ${this._listItems()}
                </platform-popover>
            </div>
        `;
    }
}

customElements.define('platform-searchable-combobox', PlatformSearchableCombobox);

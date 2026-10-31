import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { formStyles } from '../styles/shared/form.styles.js';
import './fields/platform-field-shell.js';
import {
    CRON_FIELD_PRESET_CUSTOM,
    CRON_FIELD_PRESETS,
    findMatchingPresetId,
    getCronForPresetId,
    normalizeCronString,
} from '../utils/cron-field.js';

function selectValue(event: Event): string {
    const target = event.composedPath()[0];
    if (!(target instanceof HTMLSelectElement)) {
        throw new Error('platform-cron-field: select target must be a select');
    }
    return target.value;
}

function inputValue(event: Event): string {
    const target = event.composedPath()[0];
    if (!(target instanceof HTMLInputElement)) {
        throw new Error('platform-cron-field: input target must be an input');
    }
    return target.value;
}

export class PlatformCronField extends PlatformElement {
    static i18nNamespace = 'platform';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        formStyles,
        css`
            :host {
                display: block;
                width: 100%;
            }
            .stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-2, 8px);
            }
            .custom {
                font-family: var(--font-mono);
                font-size: var(--text-sm, 14px);
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        value: { type: String },
        label: { type: String },
        name: { type: String },
        error: { type: String },
        disabled: { type: Boolean, reflect: true },
        placeholder: { type: String },
        _selectId: { type: String, state: true },
        _customText: { type: String, state: true },
    };

    declare value: string;
    declare label: string;
    declare name: string;
    declare error: string;
    declare disabled: boolean;
    declare placeholder: string;
    declare _selectId: string;
    declare _customText: string;

    constructor() {
        super();
        this.value = '';
        this.label = '';
        this.name = '';
        this.error = '';
        this.disabled = false;
        this.placeholder = '';
        this._selectId = CRON_FIELD_PRESET_CUSTOM;
        this._customText = '';
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('value')) {
            this._syncFromValue(this.value);
        }
    }

    override firstUpdated(changed: PropertyValues<this>): void {
        super.firstUpdated(changed);
        this._syncFromValue(this.value);
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        const sel = this.renderRoot?.querySelector<HTMLSelectElement>('select.form-select');
        if (sel && sel.value !== this._selectId) {
            sel.value = this._selectId;
        }
    }

    _syncFromValue(v: unknown): void {
        const s = typeof v === 'string' ? v : '';
        const id = findMatchingPresetId(s);
        if (id) {
            this._selectId = id;
        } else {
            this._selectId = CRON_FIELD_PRESET_CUSTOM;
        }
        this._customText = normalizeCronString(s);
    }

    _emitBoth(val: string): void {
        this.emit('input', { value: val });
        this.emit('change', { value: val });
    }

    _onSelectChange(e: Event): void {
        const id = selectValue(e);
        const wasId = this._selectId;
        this._selectId = id;
        if (id === CRON_FIELD_PRESET_CUSTOM) {
            if (wasId !== CRON_FIELD_PRESET_CUSTOM) {
                const c = getCronForPresetId(wasId);
                this._customText = c === null ? '' : c;
            }
            this._emitBoth(this._customText);
            return;
        }
        const cron = getCronForPresetId(id);
        if (cron === null) {
            this._emitBoth(this._customText);
            return;
        }
        this._customText = cron;
        this._emitBoth(cron);
    }

    _onCustomInput(e: Event): void {
        this._customText = inputValue(e);
        this.emit('input', { value: this._customText });
    }

    _onCustomChange(e: Event): void {
        this._customText = inputValue(e);
        this.emit('change', { value: this._customText });
    }

    override render(): TemplateResult {
        const showCustom = this._selectId === CRON_FIELD_PRESET_CUSTOM;
        return html`
            <platform-field-shell
                .label=${this.label}
                .error=${this.error}
                floated
                ?editable=${!this.disabled}
                ?disabled=${this.disabled}
            >
                <div class="stack">
                    <select
                        class="form-select"
                        .value=${this._selectId}
                        name=${!showCustom && this.name ? this.name : nothing}
                        ?disabled=${this.disabled}
                        @change=${this._onSelectChange}
                    >
                        ${CRON_FIELD_PRESETS.map(
                            (p: { id: string }) => html`
                                <option value=${p.id}>${this.t(`cron_field.preset_${p.id}`)}</option>
                            `,
                        )}
                        <option value=${CRON_FIELD_PRESET_CUSTOM}>
                            ${this.t('cron_field.preset_custom')}
                        </option>
                    </select>
                    ${showCustom
                        ? html`
                              <input
                                  type="text"
                                  class="form-input custom"
                                  name=${this.name || nothing}
                                  spellcheck="false"
                                  autocomplete="off"
                                  .value=${this._customText}
                                  placeholder=${this.placeholder}
                                  ?disabled=${this.disabled}
                                  @input=${this._onCustomInput}
                                  @change=${this._onCustomChange}
                              />
                              <p class="form-hint">${this.t('cron_field.custom_help')}</p>
                          `
                        : nothing}
                </div>
            </platform-field-shell>
        `;
    }
}

customElements.define('platform-cron-field', PlatformCronField);

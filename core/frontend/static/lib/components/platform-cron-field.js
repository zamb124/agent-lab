import { html, css, nothing } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import { formStyles } from '../styles/shared/form.styles.js';
import {
    CRON_FIELD_PRESET_CUSTOM,
    CRON_FIELD_PRESETS,
    findMatchingPresetId,
    getCronForPresetId,
    normalizeCronString,
} from '../utils/cron-field.js';

export class PlatformCronField extends PlatformElement {
    static i18nNamespace = 'platform';

    static styles = [
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
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: var(--text-sm, 14px);
            }
        `,
    ];

    static properties = {
        value: { type: String },
        name: { type: String },
        disabled: { type: Boolean, reflect: true },
        placeholder: { type: String },
        _selectId: { type: String, state: true },
        _customText: { type: String, state: true },
    };

    constructor() {
        super();
        this.value = '';
        this.name = '';
        this.disabled = false;
        this.placeholder = '';
        this._selectId = CRON_FIELD_PRESET_CUSTOM;
        this._customText = '';
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        if (changed.has('value')) {
            this._syncFromValue(this.value);
        }
    }

    firstUpdated() {
        super.firstUpdated();
        this._syncFromValue(this.value);
    }

    updated(changed) {
        super.updated(changed);
        const sel = this.renderRoot.querySelector('select.form-select');
        if (sel && sel.value !== this._selectId) {
            sel.value = this._selectId;
        }
    }

    _syncFromValue(v) {
        const s = typeof v === 'string' ? v : '';
        const id = findMatchingPresetId(s);
        if (id) {
            this._selectId = id;
        } else {
            this._selectId = CRON_FIELD_PRESET_CUSTOM;
        }
        this._customText = normalizeCronString(s);
    }

    _emitBoth(val) {
        this.emit('input', { value: val });
        this.emit('change', { value: val });
    }

    _onSelectChange(e) {
        const id = e.target.value;
        const wasId = this._selectId;
        this._selectId = id;
        if (id === CRON_FIELD_PRESET_CUSTOM) {
            if (wasId !== CRON_FIELD_PRESET_CUSTOM) {
                const c = getCronForPresetId(wasId);
                this._customText = c;
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

    _onCustomInput(e) {
        this._customText = e.target.value;
        this.emit('input', { value: this._customText });
    }

    _onCustomChange(e) {
        this._customText = e.target.value;
        this.emit('change', { value: this._customText });
    }

    render() {
        const showCustom = this._selectId === CRON_FIELD_PRESET_CUSTOM;
        return html`
            <div class="stack">
                <select
                    class="form-select"
                    .value=${this._selectId}
                    name=${!showCustom && this.name ? this.name : nothing}
                    ?disabled=${this.disabled}
                    @change=${this._onSelectChange}
                >
                    ${CRON_FIELD_PRESETS.map(
                        (p) => html`
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
        `;
    }
}

customElements.define('platform-cron-field', PlatformCronField);

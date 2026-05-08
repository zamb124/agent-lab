import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';

/**
 * @param {number} step
 * @returns {number}
 */
function fractionDigitsFromPositiveStep(step) {
    if (!Number.isFinite(step) || step <= 0) {
        throw new Error('platform-field-number: step must be a finite positive number');
    }
    const s = step.toString();
    const eIdx = s.indexOf('e-');
    if (eIdx !== -1) {
        const exp = parseInt(s.slice(eIdx + 2), 10);
        if (!Number.isFinite(exp)) {
            throw new Error('platform-field-number: invalid step exponent');
        }
        return exp;
    }
    const dot = s.indexOf('.');
    if (dot === -1) {
        return 0;
    }
    return s.length - dot - 1;
}

export class PlatformFieldNumber extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        value: {},
        mode: { type: String },
        disabled: { type: Boolean },
        placeholder: { type: String },
        integer: { type: Boolean },
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

            .field-pill-readonly-text {
                font-variant-numeric: tabular-nums;
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.mode = 'view';
        this.disabled = false;
        this.placeholder = '';
        this.integer = false;
    }

    _onInput(e) {
        const raw = e.target.value;
        if (raw === '') {
            this.dispatchEvent(new CustomEvent('change', {
                detail: { value: null },
                bubbles: true,
                composed: true,
            }));
            return;
        }

        const parsed = this.integer ? parseInt(raw, 10) : parseFloat(raw);
        if (Number.isNaN(parsed)) return;

        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: parsed },
            bubbles: true,
            composed: true,
        }));
    }

    _formatDisplay(val) {
        if (val == null) return null;
        if (typeof val === 'number') {
            return this.integer ? String(Math.round(val)) : String(val);
        }
        return String(val);
    }

    _nudgeStep() {
        return this.integer ? 1 : 0.1;
    }

    /**
     * @param {number} direction
     */
    _nudge(direction) {
        if (this.mode !== 'edit' || this.disabled) return;
        if (direction !== 1 && direction !== -1) {
            throw new Error('platform-field-number: direction must be 1 or -1');
        }
        const root = this.renderRoot;
        const input = root.querySelector('.field-pill-number-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('platform-field-number: input not found');
        }
        const step = this._nudgeStep();
        const raw = input.value.trim();
        let current;
        if (raw === '') {
            current = 0;
        } else {
            current = this.integer ? parseInt(raw, 10) : parseFloat(raw);
            if (Number.isNaN(current)) {
                return;
            }
        }
        const nextRaw = current + direction * step;
        const next = this.integer
            ? nextRaw
            : parseFloat(nextRaw.toFixed(fractionDigitsFromPositiveStep(step)));
        this.dispatchEvent(new CustomEvent('change', {
            detail: { value: next },
            bubbles: true,
            composed: true,
        }));
    }

    /**
     * @param {'up' | 'down'} dir
     */
    _spinChevron(dir) {
        const d = dir === 'up'
            ? 'M5 .5 L9.5 6.5 H.5z'
            : 'M5 6.5 L9.5 .5 H.5z';
        return html`
            <svg width="11" height="7" viewBox="0 0 10 7" aria-hidden="true">
                <path fill="currentColor" d=${d} />
            </svg>
        `;
    }

    render() {
        if (this.mode === 'view') {
            const formatted = this._formatDisplay(this.value);
            return formatted != null
                ? html`<span class="field-pill-readonly-text">${formatted}</span>`
                : html`<span class="field-pill-empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
        }

        const incLabel = this.t('platform_field.number_increment') || 'platform_field.number_increment';
        const decLabel = this.t('platform_field.number_decrement') || 'platform_field.number_decrement';

        return html`
            <div class="field-pill-number">
                <input
                    type="number"
                    class="field-pill-input field-pill-number-input"
                    step=${this.integer ? '1' : 'any'}
                    .value=${this.value != null ? String(this.value) : ''}
                    placeholder=${this.placeholder}
                    ?disabled=${this.disabled}
                    @input=${this._onInput}
                />
                <div class="field-pill-number-spin">
                    <button
                        type="button"
                        class="field-pill-number-spin-btn field-pill-number-spin-btn-up"
                        aria-label=${incLabel}
                        title=${incLabel}
                        ?disabled=${this.disabled}
                        @mousedown=${(e) => e.preventDefault()}
                        @click=${() => this._nudge(1)}
                    >
                        ${this._spinChevron('up')}
                    </button>
                    <button
                        type="button"
                        class="field-pill-number-spin-btn field-pill-number-spin-btn-down"
                        aria-label=${decLabel}
                        title=${decLabel}
                        ?disabled=${this.disabled}
                        @mousedown=${(e) => e.preventDefault()}
                        @click=${() => this._nudge(-1)}
                    >
                        ${this._spinChevron('down')}
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-field-number', PlatformFieldNumber);

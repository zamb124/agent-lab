/**
 * Модальное окно пополнения баланса через YooMoney.
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { I18nNs } from '@platform/services/i18n/i18n.service.js';

const MIN_AMOUNT = 100;
const MAX_AMOUNT = 1_000_000;

export class TopupModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .topup-info {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                margin-bottom: var(--space-6);
            }

            .info-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .info-icon {
                color: var(--accent);
                flex-shrink: 0;
            }

            .how-it-works {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                line-height: 1.6;
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-lg);
                margin-top: var(--space-2);
            }

            .how-it-works-title {
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                margin-bottom: var(--space-2);
            }

            .error-text {
                color: var(--error);
                font-size: var(--text-xs);
                margin-top: var(--space-1);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        _amount: { state: true },
        _submitting: { state: true },
        _error: { state: true },
    };

    constructor() {
        super();
        this._amount = '';
        this._submitting = false;
        this._error = '';
    }

    _tb(key, params) {
        return this.i18n.t(key, params ?? {}, I18nNs.BILLING);
    }

    _validate() {
        const amount = parseFloat(this._amount);
        if (!this._amount || isNaN(amount)) {
            return this._tb('validation.min_amount', { amount: String(MIN_AMOUNT) });
        }
        if (amount < MIN_AMOUNT) {
            return this._tb('validation.min_amount', { amount: String(MIN_AMOUNT) });
        }
        if (amount > MAX_AMOUNT) {
            return this._tb('validation.max_amount', { amount: String(MAX_AMOUNT) });
        }
        return '';
    }

    async _handleSubmit() {
        const validationError = this._validate();
        if (validationError) {
            this._error = validationError;
            return;
        }

        this._submitting = true;
        this._error = '';

        const billingService = this.services.get('billing');
        const amount = parseFloat(this._amount);

        const result = await billingService.topup(amount);

        if (result.payment_url) {
            window.location.href = result.payment_url;
        }

        this._submitting = false;
    }

    _onAmountInput(e) {
        this._amount = e.target.value;
        this._error = '';
    }

    renderBody() {
        return html`
            <div class="form-group">
                <label class="form-label">${this._tb('modal.amount_label')}</label>
                <input
                    class="form-input"
                    type="number"
                    min="${MIN_AMOUNT}"
                    max="${MAX_AMOUNT}"
                    step="1"
                    placeholder="${this._tb('modal.amount_placeholder')}"
                    .value=${this._amount}
                    @input=${this._onAmountInput}
                    ?disabled=${this._submitting}
                />
                <div class="form-hint">
                    ${this._tb('modal.amount_help', {
                        min_amount: `${MIN_AMOUNT}`,
                        max_amount: `${MAX_AMOUNT}`,
                    })}
                </div>
                ${this._error ? html`<div class="error-text">${this._error}</div>` : ''}
            </div>

            <div class="topup-info">
                <div class="info-item">
                    <span class="info-icon">+</span>
                    <span>${this._tb('modal.card_payment')}</span>
                </div>
                <div class="info-item">
                    <span class="info-icon">+</span>
                    <span>${this._tb('modal.secure_transaction')}</span>
                </div>
                <div class="info-item">
                    <span class="info-icon">+</span>
                    <span>${this._tb('modal.instant_crediting')}</span>
                </div>
            </div>

            <div class="how-it-works">
                <div class="how-it-works-title">${this._tb('modal.how_it_works')}</div>
                ${this._tb('modal.process_description')}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <button
                class="btn btn-primary"
                @click=${this._handleSubmit}
                ?disabled=${this._submitting || !this._amount}
            >
                ${this._submitting
                    ? this._tb('creating_payment')
                    : this._tb('modal.proceed_to_payment')}
            </button>
        `;
    }
}

customElements.define('topup-modal', TopupModal);

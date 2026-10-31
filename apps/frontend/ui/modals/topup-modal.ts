/**
 * Модалка пополнения — пополнение баланса компании.
 *
 * Сабмит вызывает `billingTopupOp` через useOp; effect редиректит на
 * payment_url, поэтому модалка просто закрывается после dispatch.
 */
import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { formatPlatformCurrencyRub } from '@platform/lib/utils/format-platform-number.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';

const AMOUNT_MIN = 100;
const AMOUNT_PRESETS = Object.freeze([100, 500, 1000, 5000]);

export class FrontendTopupModal extends PlatformFormModal {
    static modalKind = 'frontend.billing_topup';
    static i18nNamespace = 'frontend';

    static override styles: CSSResultGroup = [
        PlatformFormModal.styles,
        css`
            :host {
                --modal-body-min-block-size: 0px;
            }

            :host .fullscreen-btn {
                display: none !important;
            }

            form {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            .presets {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: var(--space-2);
            }

            @media (max-width: 480px) {
                .presets {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
            }
        `,
    ];

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        _amount: { state: true },
    }
    declare _amount: unknown;
;

    constructor() {
        super();
        this._amount = AMOUNT_MIN;
        this.size = 'sm';
        this._topup = this.useOp('frontend/billing_topup');
        this._locale = this.select((s) => {
            const locale = s.i18n.locale;
            if (typeof locale !== 'string' || locale.length === 0) {
                throw new Error('FrontendTopupModal: i18n.locale is required');
            }
            return locale;
        });
    }
    private _topup: OpController;
    private _locale: SelectController<any>;


    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('topup_modal.header');
    }

    override renderSaveHeaderButton() {
        return html``;
    }

    override validateForm() {
        const errors: Record<string, string> = {};
        const amount =
            typeof this._amount === 'number' && Number.isFinite(this._amount) ? this._amount : null;
        if (amount === null) {
            errors.amount = this.t('topup_modal.err_amount_required');
            return errors;
        }
        if (amount <= 0) {
            errors.amount = this.t('topup_modal.err_amount_invalid');
        } else if (amount < AMOUNT_MIN) {
            errors.amount = this.t('topup_modal.err_amount_min');
        }
        return errors;
    }

    override async handleSubmit() {
        if (typeof this._amount !== 'number' || !Number.isFinite(this._amount)) {
            throw new Error('FrontendTopupModal.handleSubmit: amount is required');
        }
        this._topup.run({ amount: this._amount });
        this.closeAfterSave();
    }

    _setAmount(amount: number) {
        this._amount = amount;
        this.isDirty = true;
    }

    override renderBody() {
        const amountNum = typeof this._amount === 'number' && Number.isFinite(this._amount) ? this._amount : null;
        const locale = this._locale.value;
        return html`
            <form @submit=${this._onSubmit} @input=${() => { this.isDirty = true; }}>
                <platform-field
                    type="number"
                    mode="edit"
                    .label=${this.t('topup_modal.label_amount')}
                    .hint=${this.t('topup_modal.amount_hint')}
                    .value=${amountNum}
                    @change=${(e: CustomEvent) => {
                        if (!e.detail) {
                            throw new Error('topup modal: amount change expects detail');
                        }
                        const v = e.detail.value;
                        if (v !== null && typeof v !== 'number') {
                            throw new Error('topup modal: amount expects numeric detail.value or null');
                        }
                        this._setAmount(v);
                    }}
                ></platform-field>
                <div class="presets" role="group" aria-label=${this.t('topup_modal.presets_label')}>
                    ${AMOUNT_PRESETS.map((preset) => html`
                        <platform-button
                            block
                            density="compact"
                            variant=${amountNum === preset ? 'primary' : 'ghost'}
                            type="button"
                            @click=${() => this._setAmount(preset)}
                        >
                            ${formatPlatformCurrencyRub(preset, locale, {
                                minimumFractionDigits: 0,
                                maximumFractionDigits: 0,
                            })}
                        </platform-button>
                    `)}
                </div>
                ${this.renderFieldError('amount')}
            </form>
        `;
    }

    override renderFooter() {
        const busy = this.loading || this._topup.busy;
        const canSubmit =
            typeof this._amount === 'number'
            && Number.isFinite(this._amount)
            && this._amount >= AMOUNT_MIN
            && !busy;
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('topup_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${!canSubmit}
                    @click=${() => this._performSave()}
                >
                    ${busy
                        ? this.t('topup_modal.submitting')
                        : this.t('topup_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-topup-modal', FrontendTopupModal);
registerModalKind(FrontendTopupModal.modalKind, 'frontend-topup-modal');

/**
 * Базовый класс для модальных окон с формой
 * Использует shared form стили (DRY)
 */
import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import { platformConfirm } from './platform-confirm-modal.js';

export class PlatformFormModal extends PlatformModal {
    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .form-actions {
                display: flex;
                gap: var(--space-3, 12px);
                justify-content: flex-end;
                width: 100%;
            }
        `
    ];

    static override get properties(): PropertyDeclarations {
        return {
            loading: { type: Boolean },
            isDirty: { type: Boolean },
        };
    }

    declare loading: boolean;
    declare isDirty: boolean;

    formErrors: Record<string, string>;
    _unsavedCloseDialogActive: boolean;

    constructor() {
        super();
        this.loading = false;
        this.isDirty = false;
        this.formErrors = {};
        this._unsavedCloseDialogActive = false;
    }

    override async close(): Promise<void> {
        if (this._unsavedCloseDialogActive) {
            return;
        }
        if (this.isDirty) {
            this._unsavedCloseDialogActive = true;
            try {
                const ok = await platformConfirm(this.t('form_modal.unsaved_close'), {
                    title: this.t('form_modal.unsaved_confirm_title'),
                    confirmText: this.t('form_modal.unsaved_confirm_discard'),
                    cancelText: this.t('form_modal.unsaved_confirm_keep'),
                    variant: 'warning',
                    confirmVariant: 'danger',
                });
                if (!ok) {
                    return;
                }
            } finally {
                this._unsavedCloseDialogActive = false;
            }
        }
        super.close();
    }

    /**
     * Закрытие модалки после успешного submit без подтверждения dirty-формы.
     * isDirty чистится перед super.close(), который дёрнет dispatch UI_MODAL_CLOSE.
     */
    closeAfterSave(): void {
        this.isDirty = false;
        super.close();
    }

    getFormData(): Record<string, FormDataEntryValue> {
        const form = this.shadowRoot?.querySelector('form');
        if (!form) return {};

        const formData = new FormData(form);
        const data: Record<string, FormDataEntryValue> = {};

        for (const [key, value] of formData.entries()) {
            data[key] = value;
        }

        return data;
    }

    validateForm(): Record<string, string> {
        return {};
    }

    async handleSubmit(_data: Record<string, FormDataEntryValue>): Promise<void> {
        throw new Error('handleSubmit must be implemented');
    }

    _saveHeaderTitle(): string {
        return (this.t('modal.save') || 'modal.save');
    }

    async _performSave(): Promise<void> {
        const errors = this.validateForm();
        if (Object.keys(errors).length > 0) {
            this.formErrors = errors;
            return;
        }

        this.formErrors = {};
        this.loading = true;

        const data = this.getFormData();
        await this.handleSubmit(data);

        this.loading = false;
    }

    async _onSubmit(e: SubmitEvent): Promise<void> {
        e.preventDefault();
        await this._performSave();
    }

    override renderSaveHeaderButton(): TemplateResult {
        return this._renderHeaderSaveIcon({
            onClick: () => void this._performSave(),
            disabled: this.loading,
            title: this.loading
                ? (this.t('modal.saving') || 'modal.saving')
                : this._saveHeaderTitle(),
        });
    }

    resetForm(): void {
        const form = this.shadowRoot?.querySelector('form');
        form?.reset();
        this.formErrors = {};
    }

    fieldError(fieldName: string): string {
        const error = this.formErrors[fieldName];
        return error ? String(error) : '';
    }

    renderFieldError(fieldName: string): TemplateResult | null {
        const error = this.formErrors[fieldName];
        if (!error) return null;
        return html`<div class="form-error">${error}</div>`;
    }

    override renderFooter(): TemplateResult {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${this.close}>
                    ${(this.t('form_modal.cancel') || 'form_modal.cancel')}
                </button>
            </div>
        `;
    }
}

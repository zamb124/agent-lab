/**
 * Базовый класс для модальных окон с формой
 * Использует shared form стили (DRY)
 */
import { html, css } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import { platformConfirm } from './platform-confirm-modal.js';

export class PlatformFormModal extends PlatformModal {
    static styles = [
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

    static get properties() {
        return {
            loading: { type: Boolean },
            isDirty: { type: Boolean },
        };
    }

    constructor() {
        super();
        this.loading = false;
        this.isDirty = false;
        this.formErrors = {};
        /** @type {boolean} */
        this._unsavedCloseDialogActive = false;
    }

    async close() {
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
    closeAfterSave() {
        this.isDirty = false;
        super.close();
    }

    getFormData() {
        const form = this.shadowRoot.querySelector('form');
        if (!form) return {};
        
        const formData = new FormData(form);
        const data = {};
        
        for (const [key, value] of formData.entries()) {
            data[key] = value;
        }
        
        return data;
    }

    validateForm() {
        return {};
    }

    async handleSubmit(data) {
        throw new Error('handleSubmit must be implemented');
    }

    _saveHeaderTitle() {
        return (this.t('modal.save') || 'modal.save');
    }

    async _performSave() {
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

    async _onSubmit(e) {
        e.preventDefault();
        await this._performSave();
    }

    renderSaveHeaderButton() {
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this.loading,
            title: this.loading
                ? (this.t('modal.saving') || 'modal.saving')
                : this._saveHeaderTitle(),
        });
    }

    resetForm() {
        const form = this.shadowRoot.querySelector('form');
        form?.reset();
        this.formErrors = {};
    }

    renderFieldError(fieldName) {
        const error = this.formErrors[fieldName];
        if (!error) return null;
        return html`<div class="form-error">${error}</div>`;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${this.close}>
                    ${(this.t('form_modal.cancel') || 'form_modal.cancel')}
                </button>
            </div>
        `;
    }
}

/**
 * Базовый класс для модальных окон с формой
 * Использует shared form стили (DRY)
 */
import { html, css } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles } from '../styles/shared/button.styles.js';

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
    }

    close() {
        const msg = this.i18n.t('form_modal.unsaved_close', {}, 'shell');
        if (this.isDirty && !confirm(msg)) {
            return;
        }
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
        return this.i18n.t('modal.save', {}, 'shell');
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
                ? this.i18n.t('modal.saving', {}, 'shell')
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
                    ${this.i18n.t('form_modal.cancel', {}, 'shell')}
                </button>
            </div>
        `;
    }
}

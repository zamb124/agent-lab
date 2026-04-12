/**
 * Namespace Create Modal - создание нового namespace
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-icon.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';

export class NamespaceCreateModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        _name: { state: true },
        _description: { state: true },
        _loading: { state: true },
    };
    
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        formStyles,
        css`
            .form {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            .modal-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
            }

            .modal-header-buttons {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }

            .header-icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 36px;
                height: 36px;
                padding: 0;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }

            .header-icon-btn:hover:not(:disabled) {
                background: var(--glass-tint-subtle, rgba(0, 0, 0, 0.06));
                color: var(--text-primary);
            }

            .header-icon-btn:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
        `
    ];
    
    constructor() {
        super();
        this._name = '';
        this._description = '';
        this._loading = false;
        this._resolveSubmit = null;
        this._rejectSubmit = null;
    }
    
    waitForSubmit() {
        return new Promise((resolve, reject) => {
            this._resolveSubmit = resolve;
            this._rejectSubmit = reject;
        });
    }
    
    _handleNameChange(e) {
        this._name = e.target.value;
    }
    
    _handleDescriptionChange(e) {
        this._description = e.target.value;
    }
    
    _handleSubmit() {
        if (!this._name.trim()) {
            return;
        }

        this._resolveSubmit?.({
            name: this._name.trim(),
            description: this._description.trim(),
        });
        this._resolveSubmit = null;
        this._rejectSubmit = null;
        this.close();
    }

    _handleClose() {
        this.close();
        this._rejectSubmit?.(new Error('cancelled'));
        this._rejectSubmit = null;
        this._resolveSubmit = null;
    }
    
    render() {
        return html`
            <svg style="position: absolute; width: 0; height: 0; overflow: hidden;">
                <defs>
                    <filter id="liquidGlassFilter" x="-10%" y="-10%" width="120%" height="120%">
                        <feTurbulence 
                            type="fractalNoise" 
                            baseFrequency="0.012 0.012" 
                            numOctaves="3" 
                            seed="15"
                            result="noise"
                        />
                        <feDisplacementMap 
                            in="SourceGraphic" 
                            in2="noise" 
                            scale="6" 
                            xChannelSelector="R" 
                            yChannelSelector="G"
                        />
                    </filter>
                </defs>
            </svg>
            <div class="modal-overlay" @click=${this._handleClose}>
                <div class="modal md" @click=${(e) => e.stopPropagation()}>
                    <div class="modal-header">
                        <h2 class="modal-title">${this.i18n.t('modals.create_namespace.title')}</h2>
                        <div class="modal-header-buttons">
                            <button
                                type="button"
                                class="header-icon-btn"
                                title=${this._loading
                                    ? this.i18n.t('modals.create_namespace.creating')
                                    : this.i18n.t('modals.create_namespace.create')}
                                aria-label=${this._loading
                                    ? this.i18n.t('modals.create_namespace.creating')
                                    : this.i18n.t('modals.create_namespace.create')}
                                ?disabled=${!this._name.trim() || this._loading}
                                @click=${this._handleSubmit}
                            >
                                <platform-icon name="save" size="16"></platform-icon>
                            </button>
                            <button class="close-button" @click=${this._handleClose}>✕</button>
                        </div>
                    </div>
                    <div class="modal-content">
                        <div class="form">
                            <div class="form-group">
                                <label class="form-label">${this.i18n.t('modals.create_namespace.name_label')}</label>
                                <input 
                                    class="form-input"
                                    type="text" 
                                    placeholder=${this.i18n.t('modals.create_namespace.name_placeholder')}
                                    .value=${this._name}
                                    @input=${this._handleNameChange}
                                />
                                <span class="form-hint">
                                    ${this.i18n.t('modals.create_namespace.name_hint')}
                                </span>
                            </div>
                            <div class="form-group">
                                <label class="form-label">${this.i18n.t('modals.create_namespace.description_label')}</label>
                                <textarea 
                                    class="form-textarea"
                                    placeholder=${this.i18n.t('modals.create_namespace.description_placeholder')}
                                    .value=${this._description}
                                    @input=${this._handleDescriptionChange}
                                    rows="3"
                                ></textarea>
                            </div>
                        </div>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" @click=${this._handleClose}>
                            ${this.i18n.t('modals.create_namespace.cancel')}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('namespace-create-modal', NamespaceCreateModal);

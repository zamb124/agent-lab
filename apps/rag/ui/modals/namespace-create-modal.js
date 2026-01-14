/**
 * Namespace Create Modal - создание нового namespace
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
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
            description: this._description.trim()
        });
    }
    
    _handleClose() {
        this._rejectSubmit?.(new Error('cancelled'));
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
                        <h2 class="modal-title">Создать namespace</h2>
                        <button class="close-button" @click=${this._handleClose}>✕</button>
                    </div>
                    <div class="modal-content">
                        <div class="form">
                            <div class="form-group">
                                <label class="form-label">Название</label>
                                <input 
                                    class="form-input"
                                    type="text" 
                                    placeholder="my-namespace"
                                    .value=${this._name}
                                    @input=${this._handleNameChange}
                                />
                                <span class="form-hint">
                                    Уникальное имя для namespace (латиница, цифры, дефисы)
                                </span>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Описание</label>
                                <textarea 
                                    class="form-textarea"
                                    placeholder="Опишите назначение namespace..."
                                    .value=${this._description}
                                    @input=${this._handleDescriptionChange}
                                    rows="3"
                                ></textarea>
                            </div>
                        </div>
                    </div>
                    <div class="modal-actions">
                        <button class="btn btn-secondary" @click=${this._handleClose}>
                            Отмена
                        </button>
                        <button 
                            class="btn btn-primary" 
                            @click=${this._handleSubmit}
                            ?disabled=${!this._name.trim() || this._loading}
                        >
                            ${this._loading ? 'Создание...' : 'Создать'}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('namespace-create-modal', NamespaceCreateModal);

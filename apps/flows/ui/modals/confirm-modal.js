/**
 * ConfirmModal - модальное окно подтверждения действий
 * Наследуется от PlatformModal (DRY)
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class ConfirmModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            .modal-message {
                font-size: var(--text-base, 16px);
                color: var(--text-secondary);
                line-height: 1.5;
            }
            
            .confirm-actions {
                display: flex;
                gap: var(--space-3, 12px);
                justify-content: flex-end;
                width: 100%;
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        title: { type: String },
        subtitle: { type: String },
        message: { type: String },
        variant: { type: String },
        confirmText: { type: String },
        cancelText: { type: String },
        confirmVariant: { type: String },
    };

    constructor() {
        super();
        this.size = 'sm';
        this.title = 'Подтверждение действия';
        this.subtitle = '';
        this.message = 'Вы уверены что хотите продолжить?';
        this.variant = 'warning';
        this.confirmText = 'Да, продолжить';
        this.cancelText = 'Нет, отменить';
        this.confirmVariant = 'primary';
        this._resolvePromise = null;
    }

    async confirm(options = {}) {
        Object.assign(this, options);
        this.showModal();
        
        return new Promise((resolve) => {
            this._resolvePromise = resolve;
        });
    }

    waitForConfirm() {
        return new Promise((resolve) => {
            this._resolvePromise = resolve;
        });
    }

    _onConfirm() {
        if (this._resolvePromise) {
            this._resolvePromise(true);
            this._resolvePromise = null;
        }
        this.emit('confirm');
        this.close();
    }

    _onCancel() {
        if (this._resolvePromise) {
            this._resolvePromise(false);
            this._resolvePromise = null;
        }
        this.emit('cancel');
        this.close();
    }

    _getIconName() {
        switch (this.variant) {
            case 'danger':
                return 'notification-error';
            case 'warning':
                return 'notification-warning';
            case 'info':
                return 'notification-info';
            default:
                return 'notification-warning';
        }
    }

    renderHeader() {
        return html`
            <div class="modal-icon ${this.variant}">
                <platform-icon name="${this._getIconName()}" size="24"></platform-icon>
            </div>
            <div style="flex: 1;">
                <h2 class="modal-title">${this.title}</h2>
                ${this.subtitle ? html`<div class="modal-subtitle">${this.subtitle}</div>` : ''}
            </div>
        `;
    }

    renderBody() {
        return html`
            <div class="modal-message">${this.message}</div>
        `;
    }

    renderFooter() {
        const confirmClass = this.confirmVariant === 'danger' ? 'btn-danger' : 'btn-primary';
        return html`
            <div class="confirm-actions">
                <button type="button" class="btn btn-secondary" @click=${this._onCancel}>
                    ${this.cancelText}
                </button>
                <button type="button" class="btn ${confirmClass}" @click=${this._onConfirm}>
                    ${this.confirmText}
                </button>
            </div>
        `;
    }
}

customElements.define('confirm-modal', ConfirmModal);

/**
 * Helper функция для быстрого вызова confirm модалки
 * @param {string} message - Текст сообщения
 * @param {Object} options - Дополнительные опции
 * @returns {Promise<boolean>}
 */
export async function confirm(message, options = {}) {
    let modal = document.querySelector('confirm-modal');
    
    if (!modal) {
        modal = document.createElement('confirm-modal');
        document.body.appendChild(modal);
    }
    
    return await modal.confirm({ message, ...options });
}

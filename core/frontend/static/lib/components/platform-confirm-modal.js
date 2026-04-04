/**
 * PlatformConfirmModal — диалог подтверждения (glass-стек платформы).
 *
 * Режимы:
 * - Две кнопки: Promise<boolean>
 * - Три кнопки (extraText): Promise<'confirm'|'cancel'|'extra'>
 * - Только OK (hideCancel): Promise<void> при подтверждении; при закрытии без OK — undefined
 */
import { html, css } from 'lit';
import { PlatformModal } from './glass-modal.js';
import { buttonStyles } from '../styles/shared/button.styles.js';
import './platform-icon.js';

export class PlatformConfirmModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
            :host .fullscreen-btn {
                display: none !important;
            }

            .confirm-header-leading {
                display: flex;
                align-items: center;
                gap: var(--space-3, 12px);
                flex: 1;
                min-width: 0;
            }

            .modal-icon {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg, 12px);
                background: var(--glass-tint-medium, rgba(255, 255, 255, 0.08));
            }

            .modal-icon.warning {
                color: var(--warning, #f59e0b);
            }

            .modal-icon.danger {
                color: var(--error, #f43f5e);
            }

            .modal-icon.info {
                color: var(--accent, #10b981);
            }

            .confirm-title-block {
                flex: 1;
                min-width: 0;
            }

            .confirm-title-block .modal-title {
                white-space: normal;
                overflow: visible;
                text-overflow: unset;
                font-size: var(--text-lg, 18px);
                line-height: 1.3;
            }

            .modal-subtitle {
                margin-top: var(--space-1, 4px);
                font-size: var(--text-sm, 14px);
                color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
                line-height: 1.4;
            }

            .modal-message {
                font-size: var(--text-base, 16px);
                color: var(--text-secondary, rgba(255, 255, 255, 0.65));
                line-height: 1.5;
            }

            .confirm-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-3, 12px);
                justify-content: flex-end;
                width: 100%;
            }

            .modal-actions .confirm-actions {
                margin: 0;
            }
        `,
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
        extraText: { type: String },
        extraVariant: { type: String },
        hideCancel: { type: Boolean, attribute: 'hide-cancel' },
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
        this.extraText = '';
        this.extraVariant = 'danger';
        this.hideCancel = false;
        /** @type {((v: boolean | string | undefined) => void) | null} */
        this._resolvePromise = null;
    }

    _getIconName() {
        switch (this.variant) {
            case 'danger':
                return 'notification-error';
            case 'info':
                return 'notification-info';
            case 'warning':
            default:
                return 'notification-warning';
        }
    }

    /**
     * @param {Record<string, unknown>} options
     * @returns {Promise<boolean|string|void>}
     */
    async confirm(options = {}) {
        Object.assign(this, options);
        this.showModal();
        return new Promise((resolve) => {
            this._resolvePromise = resolve;
        });
    }

    _settle(value) {
        if (!this._resolvePromise) {
            return;
        }
        const fn = this._resolvePromise;
        this._resolvePromise = null;
        fn(value);
    }

    close() {
        if (this.open && this._resolvePromise) {
            this.emit('cancel');
            if (this.hideCancel) {
                this._settle(undefined);
            } else if (this.extraText) {
                this._settle('cancel');
            } else {
                this._settle(false);
            }
        }
        super.close();
    }

    waitForConfirm() {
        return new Promise((resolve) => {
            this._resolvePromise = resolve;
        });
    }

    _onConfirm() {
        if (!this._resolvePromise) {
            super.close();
            return;
        }
        this.emit('confirm');
        if (this.extraText) {
            this._settle('confirm');
        } else if (this.hideCancel) {
            this._settle(undefined);
        } else {
            this._settle(true);
        }
        super.close();
    }

    _onCancel() {
        if (!this._resolvePromise) {
            super.close();
            return;
        }
        this.emit('cancel');
        if (this.extraText) {
            this._settle('cancel');
        } else {
            this._settle(false);
        }
        super.close();
    }

    _onExtra() {
        if (!this._resolvePromise) {
            super.close();
            return;
        }
        this.emit('extra');
        this._settle('extra');
        super.close();
    }

    render() {
        const modalClasses = [
            'modal',
            this.size,
            this._isFullscreen ? 'fullscreen' : '',
            this._isDragging ? 'dragging' : '',
            this.open && this._panelEnterActive ? 'panel-enter-active' : '',
        ]
            .filter(Boolean)
            .join(' ');

        const confirmClass =
            this.confirmVariant === 'danger' ? 'btn-danger' : 'btn-primary';
        const extraClass = this.extraVariant === 'danger' ? 'btn-danger' : 'btn-secondary';

        return html`
            <div class="modal-svg-hidden" aria-hidden="true">
                <svg width="0" height="0">
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
            </div>

            <div class="modal-overlay" @click=${this._handleOverlayClick}>
                <div class="modal-scrim" aria-hidden="true" @click=${() => this.close()}></div>
                <div
                    class="${modalClasses}"
                    style="${this._getModalStyle()}"
                    @animationend=${this._handlePanelEnterAnimationEnd}
                    @click=${(e) => e.stopPropagation()}
                    role="dialog"
                    aria-modal="true"
                    aria-labelledby="confirm-modal-title"
                >
                    <div class="modal-header confirm-modal-header" @mousedown=${this._handleMouseDown}>
                        <div class="confirm-header-leading">
                            <div class="modal-icon ${this.variant}">
                                <platform-icon name="${this._getIconName()}" size="24"></platform-icon>
                            </div>
                            <div class="confirm-title-block">
                                <h2 class="modal-title confirm-title" id="confirm-modal-title">${this.title}</h2>
                                ${this.subtitle
                                    ? html`<div class="modal-subtitle">${this.subtitle}</div>`
                                    : ''}
                            </div>
                        </div>
                        <div class="header-buttons">
                            <button
                                class="header-btn fullscreen-btn"
                                @click=${this.toggleFullscreen}
                                title="${this._isFullscreen ? 'Свернуть' : 'На весь экран'}"
                                tabindex="-1"
                                aria-hidden="true"
                            >
                                <platform-icon
                                    name="${this._isFullscreen ? 'minimize' : 'maximize'}"
                                    size="16"
                                ></platform-icon>
                            </button>
                            <button class="header-btn" @click=${() => this.close()} title="Закрыть" type="button">
                                <platform-icon name="close" size="16"></platform-icon>
                            </button>
                        </div>
                    </div>

                    <div class="modal-content">
                        <div class="modal-message">${this.message}</div>
                    </div>

                    <div class="modal-actions">
                        <div class="confirm-actions">
                            ${this.extraText
                                ? html`
                                      <button
                                          type="button"
                                          class="btn ${extraClass}"
                                          @click=${this._onExtra}
                                      >
                                          ${this.extraText}
                                      </button>
                                  `
                                : ''}
                            ${this.hideCancel
                                ? ''
                                : html`
                                      <button
                                          type="button"
                                          class="btn btn-secondary"
                                          @click=${this._onCancel}
                                      >
                                          ${this.cancelText}
                                      </button>
                                  `}
                            <button type="button" class="btn ${confirmClass}" @click=${this._onConfirm}>
                                ${this.confirmText}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-confirm-modal', PlatformConfirmModal);

function getOrCreatePlatformConfirmModal() {
    let el = document.querySelector('platform-confirm-modal');
    if (!el) {
        el = document.createElement('platform-confirm-modal');
        document.body.appendChild(el);
    }
    return el;
}

/**
 * Хелпер: две кнопки → Promise<boolean>; три (extraText) → Promise<'confirm'|'cancel'|'extra'>; только OK → Promise<void>.
 *
 * @param {string} message
 * @param {Record<string, unknown>} [options]
 * @returns {Promise<boolean|string|void>}
 */
export async function platformConfirm(message, options = {}) {
    const modal = getOrCreatePlatformConfirmModal();
    return modal.confirm({ message, ...options });
}

export { platformConfirm as confirm };

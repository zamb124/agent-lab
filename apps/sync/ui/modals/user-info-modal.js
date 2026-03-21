/**
 * UserInfoModal — модалка с профилем отправителя
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class UserInfoModal extends PlatformElement {
    static properties = {
        open: { type: Boolean },
        sender: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        glassStyles,
        buttonStyles,
        css`
            .backdrop {
                position: fixed;
                inset: 0;
                z-index: 50;
                background: rgba(0, 0, 0, 0.4);
                display: flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-6);
            }

            .modal {
                width: 100%;
                max-width: 480px;
                border-radius: var(--radius-2xl);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-medium);
                backdrop-filter: blur(var(--glass-blur-strong));
                padding: var(--space-5);
            }

            .modal-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                margin-bottom: var(--space-4);
            }

            .modal-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }

            .close-btn {
                background: transparent;
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                cursor: pointer;
                font-size: var(--text-xs);
                padding: 4px 10px;
                transition: all var(--duration-fast);
            }

            .close-btn:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }

            .fields {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                font-size: var(--text-sm);
            }

            .field-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: 2px;
            }

            .field-value {
                color: var(--text-primary);
                word-break: break-all;
            }
        `
    ];

    constructor() {
        super();
        this.open = false;
        this.sender = null;
    }

    _close() {
        this.emit('close');
    }

    render() {
        if (!this.open || !this.sender) return html``;

        return html`
            <div class="backdrop" @click=${this._close}>
                <div class="modal" @click=${(e) => e.stopPropagation()}>
                    <div class="modal-header">
                        <span class="modal-title">Профиль</span>
                        <button class="close-btn" @click=${this._close}>Закрыть</button>
                    </div>
                    <div class="fields">
                        <div>
                            <div class="field-label">display_name</div>
                            <div class="field-value">${this.sender.display_name}</div>
                        </div>
                        <div>
                            <div class="field-label">user_id</div>
                            <div class="field-value">${this.sender.id}</div>
                        </div>
                        ${this.sender.avatar_url ? html`
                            <div>
                                <div class="field-label">avatar_url</div>
                                <div class="field-value">${this.sender.avatar_url}</div>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }
}

customElements.define('user-info-modal', UserInfoModal);

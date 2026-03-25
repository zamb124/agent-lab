/**
 * UserInfoModal — модалка с профилем отправителя
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class UserInfoModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        sender: { type: Object },
    };

    static styles = [
        PlatformModal.styles,
        buttonStyles,
        css`
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
        `,
    ];

    constructor() {
        super();
        this.title = 'Профиль';
        this.size = 'md';
        this.sender = null;
    }

    close() {
        super.close();
        this.emit('close');
    }

    renderHeader() {
        return 'Профиль';
    }

    renderBody() {
        if (!this.sender) {
            return html``;
        }
        const s = this.sender;
        return html`
            <div class="fields">
                <div>
                    <div class="field-label">display_name</div>
                    <div class="field-value">${s.display_name}</div>
                </div>
                <div>
                    <div class="field-label">user_id</div>
                    <div class="field-value">${s.user_id}</div>
                </div>
                ${s.avatar_url
                    ? html`
                        <div>
                            <div class="field-label">avatar_url</div>
                            <div class="field-value">${s.avatar_url}</div>
                        </div>
                    `
                    : ''}
            </div>
        `;
    }

    renderFooter() {
        return html``;
    }

    render() {
        if (!this.open || !this.sender) {
            return html``;
        }
        return super.render();
    }
}

customElements.define('user-info-modal', UserInfoModal);

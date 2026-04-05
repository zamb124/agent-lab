/**
 * Access Request Modal - Запрос доступа к чужой сущности
 * Использует PlatformModal с fullscreen и drag поддержкой
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { CRMStore } from '../store/crm.store.js';
import '@platform/lib/components/platform-icon.js';

export class AccessRequestModal extends PlatformModal {
    static properties = {
        ...PlatformModal.properties,
        entityId: { type: String },
        entityName: { type: String },
        _message: { state: true },
        _includeDeps: { state: true },
        _maxDepth: { state: true },
        _sending: { state: true },
    };

    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .form-grid {
                display: grid;
                gap: var(--space-4);
            }

            .entity-preview {
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }

            .entity-preview-icon {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-selected-bg);
                color: var(--crm-selected-text);
                border-radius: var(--radius-lg);
            }

            .entity-preview-name {
                font-size: var(--text-base);
                font-weight: 500;
                color: var(--text-primary);
            }

            .checkbox-group {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
                cursor: pointer;
            }

            .checkbox-group:hover {
                background: var(--crm-surface);
            }

            .checkbox-group input[type="checkbox"] {
                margin-top: 2px;
                width: 18px;
                height: 18px;
                cursor: pointer;
            }

            .checkbox-content {
                flex: 1;
            }

            .checkbox-label {
                font-size: var(--text-sm);
                font-weight: 500;
                color: var(--text-primary);
            }

            .checkbox-description {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
            }

            .depth-slider {
                margin-top: var(--space-3);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-lg);
            }

            .depth-slider-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--space-2);
            }

            .depth-slider-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .depth-slider-value {
                font-size: var(--text-sm);
                font-weight: 500;
                color: var(--accent);
            }

            .depth-slider input[type="range"] {
                width: 100%;
                cursor: pointer;
            }

            .info-box {
                padding: var(--space-3);
                background: var(--crm-info-bg);
                border: 1px solid var(--crm-info-stroke);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .info-box-title {
                font-weight: 500;
                color: var(--crm-info-text);
                margin-bottom: var(--space-1);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }

            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                transition: all var(--duration-fast);
            }

            .btn-secondary {
                background: var(--crm-button-secondary-bg);
                border: 1px solid var(--crm-button-secondary-bg);
                color: var(--crm-button-secondary-text);
            }

            .btn-secondary:hover {
                background: var(--crm-button-secondary-hover);
                border-color: var(--crm-button-secondary-hover);
                color: var(--crm-button-secondary-text);
            }

            .btn-primary {
                background: var(--crm-button-primary-bg);
                border: 1px solid var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }

            .btn-primary:hover:not(:disabled) {
                background: var(--crm-button-primary-hover);
                border-color: var(--crm-button-primary-hover);
            }

            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        `
    ];

    constructor() {
        super();
        this.size = 'md';
        this.entityId = null;
        this.entityName = '';
        this._message = '';
        this._includeDeps = false;
        this._maxDepth = 1;
        this._sending = false;
    }

    renderHeader() {
        return this.i18n.t('access_request_modal.title');
    }

    _onMessageInput(e) {
        this._message = e.target.value;
    }

    _onIncludeDepsChange(e) {
        this._includeDeps = e.target.checked;
    }

    _onMaxDepthChange(e) {
        this._maxDepth = parseInt(e.target.value, 10);
    }

    async _onSendRequest() {
        this._sending = true;

        const crmApi = this.services.get('crmApi');
        await CRMStore.createAccessRequest(
            crmApi,
            this.entityId,
            this._message.trim() || null,
            this._includeDeps,
            this._maxDepth
        );

        this._sending = false;
        this.success(this.i18n.t('access_request_modal.success_sent'));
        this.close();
    }

    renderBody() {
        return html`
            <div class="form-grid">
                <div class="entity-preview">
                    <div class="entity-preview-icon">
                        <platform-icon name="folder" size="20"></platform-icon>
                    </div>
                    <div class="entity-preview-name">
                        ${this.entityName || this.i18n.t('access_request_modal.entity_fallback')}
                    </div>
                </div>

                <div class="info-box">
                    <div class="info-box-title">${this.i18n.t('access_request_modal.how_title')}</div>
                    <div>${this.i18n.t('access_request_modal.how_body')}</div>
                </div>

                <div class="form-group">
                    <label class="form-label">${this.i18n.t('access_request_modal.message_label')}</label>
                    <textarea
                        class="form-textarea"
                        rows="3"
                        placeholder=${this.i18n.t('access_requests.message_placeholder')}
                        .value=${this._message}
                        @input=${this._onMessageInput}
                    ></textarea>
                </div>

                <label class="checkbox-group" @click=${(e) => {
                    if (e.target.tagName !== 'INPUT') {
                        const checkbox = this.renderRoot.querySelector('#include-deps');
                        checkbox.checked = !checkbox.checked;
                        this._includeDeps = checkbox.checked;
                    }
                }}>
                    <input
                        type="checkbox"
                        id="include-deps"
                        .checked=${this._includeDeps}
                        @change=${this._onIncludeDepsChange}
                    />
                    <div class="checkbox-content">
                        <div class="checkbox-label">${this.i18n.t('access_request_modal.include_related')}</div>
                        <div class="checkbox-description">
                            ${this.i18n.t('access_request_modal.include_related_hint')}
                        </div>
                    </div>
                </label>

                ${this._includeDeps ? html`
                    <div class="depth-slider">
                        <div class="depth-slider-header">
                            <span class="depth-slider-label">${this.i18n.t('access_request_modal.depth_label')}</span>
                            <span class="depth-slider-value">${this._maxDepth}</span>
                        </div>
                        <input
                            type="range"
                            min="1"
                            max="5"
                            .value=${this._maxDepth}
                            @input=${this._onMaxDepthChange}
                        />
                    </div>
                ` : ''}
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const title = this._sending
            ? this.i18n.t('access_request_modal.sending')
            : this.i18n.t('access_requests.send_request');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSendRequest(),
            disabled: this._sending,
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button
                    type="button"
                    class="btn btn-secondary"
                    @click=${() => this.close()}
                >
                    ${this.i18n.t('cancel', {}, 'common')}
                </button>
            </div>
        `;
    }
}

customElements.define('access-request-modal', AccessRequestModal);

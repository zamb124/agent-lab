/**
 * CRMAccessRequestModal — запрос доступа к чужой сущности.
 *
 * Props:
 *   - entityId: string — обязательный, сущность, на которую запрашивается доступ.
 *
 * Поток:
 *   1. На open: `entitiesResource.get(entityId)` подгружает имя/тип/namespace
 *      для шапки (если у пользователя есть хотя бы read-видимость).
 *   2. Форма:
 *        - message: textarea (max 1000), не обязательный.
 *        - include_dependencies: чекбокс.
 *        - max_depth: range 1..5 (виден только если include_dependencies).
 *   3. Submit: `accessRequestsResource.create({
 *        resource_type: 'entity', resource_id: entityId, message?,
 *        include_dependencies, max_depth
 *      })`.
 *   4. На CREATED — close(); на CREATE_FAILED — показать ошибку в footer.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

const ENTITIES_NAME = 'crm/entities';
const ACCESS_REQUESTS_NAME = 'crm/access_requests';

const MESSAGE_MAX = 1000;
const DEPTH_MIN = 1;
const DEPTH_MAX = 5;

export class CRMAccessRequestModal extends PlatformModal {
    static modalKind = 'crm.access_request';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        entityId: { type: String },
        _message: { state: true },
        _includeDeps: { state: true },
        _maxDepth: { state: true },
        _submitFailedMessage: { state: true },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .body {
                display: grid;
                gap: var(--space-4);
                padding: var(--space-2) 0;
            }
            .entity-head {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .entity-head .icon {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: var(--crm-selected-bg);
                color: var(--accent);
                border-radius: var(--radius-md);
            }
            .entity-head .meta { display: grid; gap: 2px; min-width: 0; }
            .entity-head .name {
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .entity-head .sub {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .info-box {
                padding: var(--space-3);
                background: var(--crm-selected-bg);
                border: 1px solid var(--accent);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                display: grid;
                gap: var(--space-1);
            }
            .info-box .info-title {
                font-weight: 600;
                color: var(--accent);
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }
            .field-label {
                font-size: var(--text-xs);
                font-weight: 600;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .text-area {
                width: 100%;
                min-height: 96px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-family: inherit;
                box-sizing: border-box;
                resize: vertical;
            }
            .checkbox-row {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .checkbox-row input[type="checkbox"] {
                margin-top: 2px;
                width: 18px;
                height: 18px;
                cursor: pointer;
            }
            .checkbox-row .check-content {
                display: grid;
                gap: 2px;
            }
            .checkbox-row .check-label {
                font-size: var(--text-sm);
                font-weight: 500;
                color: var(--text-primary);
            }
            .checkbox-row .check-desc {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .depth-control {
                display: grid;
                gap: var(--space-2);
                padding: var(--space-3);
                background: var(--crm-surface-muted);
                border: 1px solid var(--crm-stroke);
                border-radius: var(--radius-md);
            }
            .depth-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .depth-header .depth-label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .depth-header .depth-value {
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--accent);
            }
            .depth-control input[type="range"] {
                width: 100%;
                cursor: pointer;
            }
            .char-count {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                text-align: right;
            }
            .footer-actions {
                display: flex;
                gap: var(--space-3);
                justify-content: flex-end;
                width: 100%;
            }
            .footer-actions .submit-error {
                margin-right: auto;
                color: var(--color-danger);
                font-size: var(--text-sm);
                align-self: center;
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid transparent;
            }
            .btn-secondary {
                background: var(--crm-surface);
                border-color: var(--crm-stroke);
                color: var(--text-secondary);
            }
            .btn-secondary:hover {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-primary {
                background: var(--accent);
                border-color: var(--accent);
                color: white;
            }
            .btn-primary:hover:not(:disabled) {
                filter: brightness(1.05);
            }
            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.entityId = '';

        this._message = '';
        this._includeDeps = false;
        this._maxDepth = 1;
        this._submitFailedMessage = '';

        this._entities = this.useResource(ENTITIES_NAME);
        this._accessRequests = this.useResource(ACCESS_REQUESTS_NAME);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.entityId !== 'string' || this.entityId.length === 0) {
            throw new Error('CRMAccessRequestModal: prop "entityId" required');
        }

        this.useEvent(this._accessRequests.resource.events.CREATED, () => this.close());
        this.useEvent(this._accessRequests.resource.events.CREATE_FAILED, (event) => {
            const message = event && event.payload && typeof event.payload.message === 'string'
                ? event.payload.message
                : this.t('access_request_modal.submit_failed');
            this._submitFailedMessage = message;
        });

        this._entities.get(this.entityId);
    }

    _entity() {
        const item = this._entities.byId[this.entityId];
        return item === undefined ? null : item;
    }

    _onMessageChange(e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('CRMAccessRequestModal: message field expects change detail.value string');
        }
        const value = e.detail.value;
        if (value.length <= MESSAGE_MAX) {
            this._message = value;
        } else {
            this._message = value.slice(0, MESSAGE_MAX);
        }
        this._submitFailedMessage = '';
    }

    _onIncludeDepsChange(e) {
        this._includeDeps = Boolean(e.target.checked);
    }

    _onDepthChange(e) {
        const value = parseInt(e.target.value, 10);
        if (Number.isFinite(value) && value >= DEPTH_MIN && value <= DEPTH_MAX) {
            this._maxDepth = value;
        }
    }

    _isBusy() {
        return this._accessRequests.loading;
    }

    _onSubmit() {
        const trimmed = this._message.trim();
        const payload = {
            resource_type: 'entity',
            resource_id: this.entityId,
            include_dependencies: this._includeDeps,
            max_depth: this._maxDepth,
        };
        if (trimmed.length > 0) {
            payload.message = trimmed;
        }
        this._submitFailedMessage = '';
        this._accessRequests.create(payload);
    }

    renderHeader() {
        return this.t('access_request_modal.header');
    }

    renderBody() {
        const entity = this._entity();
        return html`
            <div class="body">
                ${this._renderEntityHead(entity)}
                <div class="info-box">
                    <span class="info-title">
                        <platform-icon name="info" size="14"></platform-icon>
                        ${this.t('access_request_modal.how_title')}
                    </span>
                    <span>${this.t('access_request_modal.how_body')}</span>
                </div>
                ${this._renderMessageField()}
                ${this._renderIncludeDeps()}
                ${this._includeDeps ? this._renderDepthSlider() : nothing}
            </div>
        `;
    }

    _renderEntityHead(entity) {
        if (entity === null) {
            return html`
                <div class="entity-head">
                    <div class="icon">
                        <platform-icon name="link" size="18"></platform-icon>
                    </div>
                    <div class="meta">
                        <div class="name">${this.entityId}</div>
                        <div class="sub">${this.t('access_request_modal.loading_entity')}</div>
                    </div>
                </div>
            `;
        }
        return html`
            <div class="entity-head">
                <div class="icon">
                    <platform-icon name="link" size="18"></platform-icon>
                </div>
                <div class="meta">
                    <div class="name">${entity.name}</div>
                    <div class="sub">${entity.namespace} · ${entity.entity_type}</div>
                </div>
            </div>
        `;
    }

    _renderMessageField() {
        return html`
            <div>
                <platform-field
                    type="text"
                    mode="edit"
                    label=${this.t('access_request_modal.message_label')}
                    placeholder=${this.t('access_request_modal.message_placeholder')}
                    .value=${this._message}
                    @change=${this._onMessageChange}
                ></platform-field>
                <div class="char-count">${this._message.length} / ${MESSAGE_MAX}</div>
            </div>
        `;
    }

    _renderIncludeDeps() {
        return html`
            <label class="checkbox-row">
                <input
                    type="checkbox"
                    .checked=${this._includeDeps}
                    @change=${this._onIncludeDepsChange}
                />
                <div class="check-content">
                    <span class="check-label">${this.t('access_request_modal.include_deps_label')}</span>
                    <span class="check-desc">${this.t('access_request_modal.include_deps_desc')}</span>
                </div>
            </label>
        `;
    }

    _renderDepthSlider() {
        return html`
            <div class="depth-control">
                <div class="depth-header">
                    <span class="depth-label">${this.t('access_request_modal.depth_label')}</span>
                    <span class="depth-value">${this._maxDepth}</span>
                </div>
                <input
                    type="range"
                    min=${DEPTH_MIN}
                    max=${DEPTH_MAX}
                    step="1"
                    .value=${String(this._maxDepth)}
                    @input=${this._onDepthChange}
                />
            </div>
        `;
    }

    renderFooter() {
        const busy = this._isBusy();
        return html`
            <div class="footer-actions">
                ${this._submitFailedMessage.length > 0
                    ? html`<span class="submit-error">${this._submitFailedMessage}</span>`
                    : nothing}
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('access_request_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-primary"
                    ?disabled=${busy}
                    @click=${() => this._onSubmit()}
                >
                    ${busy ? this.t('access_request_modal.submitting') : this.t('access_request_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-access-request-modal', CRMAccessRequestModal);
registerModalKind(CRMAccessRequestModal.modalKind, 'crm-access-request-modal');

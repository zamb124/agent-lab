/**
 * CRMEntityDeleteModal — единое подтверждение удаления любой CRM-entity.
 *
 * Свойства:
 *   - entityId: string                     — обязательный, id сущности.
 *   - redirectRoute?: string = 'entities'  — куда `navigate` после успешного
 *     удаления. Для note передаётся 'notes'.
 *
 * Поток:
 *   1. На open `entitiesResource.get(entityId)` подгружает имя/тип сущности
 *      для шапки и текста подтверждения.
 *   2. По кнопке «Удалить» → `entitiesResource.remove(entityId)`. Toast про
 *      успех/ошибку фабрика выдаёт сама через `toastKeys.remove` /
 *      `toastKeys.remove_error` (настроено в `entitiesResource`).
 *   3. На `entitiesResource.events.REMOVED` для нашего entityId — закрываем
 *      модалку и `navigate(this.redirectRoute)`.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

const ENTITIES_NAME = 'crm/entities';

export class CRMEntityDeleteModal extends PlatformModal {
    static modalKind = 'crm.entity_delete';
    static i18nNamespace = 'crm';

    static properties = {
        ...PlatformModal.properties,
        entityId: { type: String },
        redirectRoute: { type: String },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .body {
                display: grid;
                gap: var(--space-4);
                padding: var(--space-2) 0;
            }
            .warn-icon {
                width: 56px;
                height: 56px;
                margin: 0 auto;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                background: rgba(255, 96, 96, 0.12);
                color: var(--color-danger, #ef4444);
                border-radius: 50%;
            }
            .question {
                text-align: center;
                font-size: var(--text-base);
                color: var(--text-primary);
                margin: 0;
            }
            .entity-name {
                text-align: center;
                color: var(--text-primary);
                font-weight: 600;
                font-size: var(--text-lg);
                word-break: break-word;
            }
            .entity-type {
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }
            .hint {
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }

            .footer-actions {
                display: flex;
                gap: var(--space-2);
                justify-content: flex-end;
                width: 100%;
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface);
                color: var(--text-secondary);
            }
            .btn:hover:not(:disabled) {
                background: var(--crm-surface-muted);
                color: var(--text-primary);
            }
            .btn-danger {
                background: var(--color-danger, #ef4444);
                color: white;
                border-color: var(--color-danger, #ef4444);
            }
            .btn-danger:hover:not(:disabled) { filter: brightness(1.05); }
            .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        `,
    ];

    constructor() {
        super();
        this.size = 'sm';
        this.entityId = '';
        this.redirectRoute = 'entities';

        this._entities = this.useResource(ENTITIES_NAME);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof this.entityId !== 'string' || this.entityId.length === 0) {
            throw new Error('CRMEntityDeleteModal: prop "entityId" required');
        }
        if (typeof this.redirectRoute !== 'string' || this.redirectRoute.length === 0) {
            throw new Error('CRMEntityDeleteModal: prop "redirectRoute" must be non-empty string');
        }
        this._entities.get(this.entityId);

        this.useEvent(this._entities.resource.events.REMOVED, (event) => {
            const payload = event && event.payload;
            const idField = this._entities.resource.idField;
            const removedId = payload && typeof payload[idField] === 'string' ? payload[idField] : null;
            if (removedId !== this.entityId) return;
            this.close();
            this.navigate(this.redirectRoute);
        });
    }

    _entity() {
        const item = this._entities.byId[this.entityId];
        return item === undefined ? null : item;
    }

    _onConfirm() {
        this._entities.remove(this.entityId);
    }

    renderHeader() {
        return this.t('entity_delete_modal.header');
    }

    renderBody() {
        const entity = this._entity();
        const title = entity !== null && typeof entity.name === 'string' && entity.name.length > 0
            ? entity.name
            : this.t('entity_delete_modal.unknown_entity');
        const entityType = entity !== null && typeof entity.entity_type === 'string' && entity.entity_type.length > 0
            ? entity.entity_type
            : '';
        return html`
            <div class="body">
                <div class="warn-icon">
                    <platform-icon name="trash" size="24"></platform-icon>
                </div>
                <p class="question">${this.t('entity_delete_modal.question')}</p>
                <div class="entity-name">${title}</div>
                ${entityType.length > 0 ? html`<div class="entity-type">${entityType}</div>` : nothing}
                <p class="hint">${this.t('entity_delete_modal.hint')}</p>
                ${entity === null ? html`<div style="text-align:center;"><glass-spinner></glass-spinner></div>` : nothing}
            </div>
        `;
    }

    renderFooter() {
        const busy = this._entities.isBusy(this.entityId);
        return html`
            <div class="footer-actions">
                <button type="button" class="btn" @click=${() => this.close()} ?disabled=${busy}>
                    ${this.t('entity_delete_modal.cancel')}
                </button>
                <button
                    type="button"
                    class="btn btn-danger"
                    ?disabled=${busy}
                    @click=${() => this._onConfirm()}
                >
                    ${busy
                        ? this.t('entity_delete_modal.deleting')
                        : this.t('entity_delete_modal.confirm')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-entity-delete-modal', CRMEntityDeleteModal);
registerModalKind(CRMEntityDeleteModal.modalKind, 'crm-entity-delete-modal');

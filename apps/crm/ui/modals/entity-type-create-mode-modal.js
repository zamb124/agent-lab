/**
 * Выбор способа создания типа: пустой черновик или каталог типов полей.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-icon.js';
import { CRM_ENTITY_TYPE_CREATE_MODE_CHOSEN } from '../utils/entity-type-create-events.js';

export class CRMEntityTypeCreateModeModal extends PlatformModal {
    static modalKind = 'crm.entity_type_create_mode';
    static i18nNamespace = 'crm';

    static styles = [
        ...PlatformModal.styles,
        css`
            :host {
                --modal-width: min(440px, calc(100vw - 24px));
            }
            .hint {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                margin: 0 0 var(--space-4) 0;
                line-height: 1.45;
            }
            .choices {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .choice {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                text-align: left;
                cursor: pointer;
                font: inherit;
                width: 100%;
                box-sizing: border-box;
            }
            .choice:hover {
                border-color: var(--accent);
                background: rgba(99, 102, 241, 0.08);
            }
            .choice-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-weight: 600;
                font-size: var(--text-sm);
            }
            .choice-desc {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: 1.4;
                margin: 0;
            }
            .footer-actions {
                display: flex;
                justify-content: flex-end;
                width: 100%;
            }
            .btn {
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-md);
                font-size: var(--text-sm);
                font-weight: 500;
                cursor: pointer;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
            }
            .btn:hover {
                background: var(--crm-surface-muted, rgba(255, 255, 255, 0.06));
                color: var(--text-primary);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
    }

    _chooseBlank() {
        this.dispatch(CRM_ENTITY_TYPE_CREATE_MODE_CHOSEN, { mode: 'blank' });
        this.close();
    }

    _chooseFromPresets() {
        this.dispatch(CRM_ENTITY_TYPE_CREATE_MODE_CHOSEN, { mode: 'from_presets' });
        this.close();
    }

    renderHeader() {
        return this.t('entity_type_create_mode_modal.title');
    }

    renderBody() {
        return html`
            <p class="hint">${this.t('entity_type_create_mode_modal.intro')}</p>
            <div class="choices">
                <button type="button" class="choice" @click=${this._chooseBlank}>
                    <span class="choice-title">
                        <platform-icon name="plus" size="18"></platform-icon>
                        ${this.t('entity_type_create_mode_modal.option_blank_title')}
                    </span>
                    <p class="choice-desc">${this.t('entity_type_create_mode_modal.option_blank_desc')}</p>
                </button>
                <button type="button" class="choice" @click=${this._chooseFromPresets}>
                    <span class="choice-title">
                        <platform-icon name="layout-grid" size="18"></platform-icon>
                        ${this.t('entity_type_create_mode_modal.option_presets_title')}
                    </span>
                    <p class="choice-desc">${this.t('entity_type_create_mode_modal.option_presets_desc')}</p>
                </button>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn" @click=${() => this.close()}>
                    ${this.t('entity_type_create_mode_modal.cancel')}
                </button>
            </div>
        `;
    }
}

customElements.define('crm-entity-type-create-mode-modal', CRMEntityTypeCreateModeModal);
registerModalKind(CRMEntityTypeCreateModeModal.modalKind, 'crm-entity-type-create-mode-modal');

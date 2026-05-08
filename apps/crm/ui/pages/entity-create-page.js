/**
 * CRMEntityCreatePage — страница создания сущности.
 *
 * Паттерн host-toolbar: кнопки Cancel / Create рендерит страница через slot="actions"
 * в page-header, карточка получает host-toolbar и рендерит только двухколоночный контент.
 * Состояние кнопок синхронизируется через DOM-событие crm-entity-card-toolbar-state,
 * которое карточка эмитит в updated().
 */

import { html, css, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/entity-card.js';

export class CRMEntityCreatePage extends PlatformPage {
    static i18nNamespace = 'crm';

    static properties = {
        _saveDisabled: { state: true },
        _submitting: { state: true },
    };

    static styles = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                width: 100%;
                height: 100%;
                min-height: 0;
                overflow: hidden;
            }
            .create-shell {
                display: flex;
                flex-direction: column;
                flex: 1 1 0%;
                min-height: 0;
                width: 100%;
                overflow: hidden;
            }
            .breadcrumbs-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
                margin-top: var(--space-2);
                margin-bottom: var(--space-2);
            }
            .header-wrap {
                flex-shrink: 0;
                padding: 0 var(--space-4);
            }
            .create-header-actions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-2);
            }
            .body {
                flex: 1;
                min-height: 0;
                overflow: hidden;
                display: flex;
            }
            .body crm-entity-card {
                flex: 1;
                width: 100%;
                min-height: 0;
            }
            .toolbar-pill {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                min-height: 40px;
                padding: 0 18px;
                border: none;
                border-radius: 20px;
                font-size: var(--text-sm);
                font-weight: 600;
                cursor: pointer;
            }
            .toolbar-pill:disabled {
                opacity: 0.5;
                cursor: not-allowed;
            }
            .toolbar-pill-primary {
                background: var(--crm-button-primary-bg);
                color: var(--crm-button-primary-text);
            }
            .toolbar-pill-primary:hover:not(:disabled) {
                background: var(--crm-button-primary-hover);
            }
            .toolbar-pill-ghost {
                background: var(--crm-surface-tint-strong);
                color: var(--text-secondary);
            }
            .toolbar-pill-ghost:hover:not(:disabled) {
                background: var(--glass-tint-strong);
                color: var(--text-primary);
            }
        `,
    ];

    constructor() {
        super();
        this._saveDisabled = true;
        this._submitting = false;
        this._onCardToolbarStateBound = this._onCardToolbarState.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        if (this.shadowRoot) {
            this.shadowRoot.addEventListener('crm-entity-card-toolbar-state', this._onCardToolbarStateBound);
        }
    }

    disconnectedCallback() {
        if (this.shadowRoot) {
            this.shadowRoot.removeEventListener('crm-entity-card-toolbar-state', this._onCardToolbarStateBound);
        }
        super.disconnectedCallback();
    }

    _onCardToolbarState(ev) {
        const d = ev.detail;
        if (!d || typeof d.saveDisabled !== 'boolean' || typeof d.submitting !== 'boolean') {
            throw new Error('crm-entity-card-toolbar-state: invalid detail');
        }
        this._saveDisabled = d.saveDisabled;
        this._submitting = d.submitting;
    }

    _getCard() {
        return this.shadowRoot.querySelector('crm-entity-card');
    }

    _onToolbarSave() {
        this._getCard().triggerSave();
    }

    _onToolbarCancel() {
        this._getCard().triggerCreateCancel();
    }

    render() {
        return html`
            <div class="create-shell">
                <div class="breadcrumbs-wrap">
                    <platform-breadcrumbs current-label=${this.t('routes.entity_new')}></platform-breadcrumbs>
                </div>
                <div class="header-wrap">
                    <page-header title=${this.t('entity_detail_page.create_title')}>
                        <div slot="actions" class="create-header-actions">
                            <button
                                type="button"
                                class="toolbar-pill toolbar-pill-ghost"
                                @click=${() => this._onToolbarCancel()}
                            >
                                ${this.t('entity_modal.action_cancel')}
                            </button>
                            <button
                                type="button"
                                class="toolbar-pill toolbar-pill-primary"
                                ?disabled=${this._saveDisabled || this._submitting}
                                @click=${() => this._onToolbarSave()}
                            >
                                ${this._submitting
                                    ? html`<glass-spinner size="16"></glass-spinner>`
                                    : nothing}
                                ${this._submitting
                                    ? this.t('entity_modal.action_saving')
                                    : this.t('entity_modal.action_create')}
                            </button>
                        </div>
                    </page-header>
                </div>
                <div class="body">
                    <crm-entity-card
                        surface="page"
                        panel-mode="create"
                        host-toolbar
                        @entity-created=${this._onEntityCreated}
                        @create-cancelled=${() => this.navigate('entities')}
                    ></crm-entity-card>
                </div>
            </div>
        `;
    }

    _onEntityCreated(event) {
        const d = event.detail;
        if (!d || typeof d.entity_id !== 'string') {
            throw new Error('entity-created: entity_id required');
        }
        this.navigate('entity', { itemId: d.entity_id });
    }
}

customElements.define('crm-entity-create-page', CRMEntityCreatePage);

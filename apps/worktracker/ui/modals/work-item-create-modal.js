/**
 * WorkItemCreateModal — создание задачи WorkItem на текущей доске.
 *
 * `useForm('worktracker/work_item_create_form')` → submit диспатчит
 * `workItemsResource.events.CREATE_REQUESTED`. После CREATED — closeAfterSave.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

const FORM_NAME = 'worktracker/work_item_create_form';
const WORK_ITEMS_NAME = 'worktracker/work_items';

export class WorkItemCreateModal extends PlatformFormModal {
    static modalKind = 'worktracker.work_item_create';
    static i18nNamespace = 'worktracker';

    static properties = {
        boardId: { type: String },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-3); }
            .footer-actions {
                display: flex; gap: var(--space-3);
                justify-content: flex-end; width: 100%;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this.boardId = '';
        this._workItems = this.useResource(WORK_ITEMS_NAME);
        this._form = this.useForm(FORM_NAME);
    }

    connectedCallback() {
        super.connectedCallback();
        this._form.openForm({ title: '', description: '', board_id: this.boardId || '', priority: 'normal' });
        this.useEvent(this._workItems.resource.events.CREATED, () => this.closeAfterSave());
    }

    disconnectedCallback() {
        this._form.close();
        super.disconnectedCallback();
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        const draft = this._form.draft;
        this.isDirty = typeof draft.title === 'string' && draft.title.length > 0;
    }

    _onTitleChange(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._form.setField('title', v);
    }

    _onDescriptionChange(e) {
        const v = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
        this._form.setField('description', v);
    }

    async _performSave() {
        this._form.setField('board_id', this.boardId || '');
        this._form.submit();
    }

    renderHeader() { return this.t('work_item_create_modal.header'); }

    renderSaveHeaderButton() {
        const draft = this._form.draft;
        const has_title = typeof draft.title === 'string' && draft.title.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !has_title,
            title: this.t('work_item_create_modal.submit'),
        });
    }

    _renderFieldError(field) {
        const error_key = this._form.errors[field];
        if (!error_key) return null;
        return html`<div class="form-error">${this.t(error_key)}</div>`;
    }

    renderBody() {
        const draft = this._form.draft;
        return html`
            <form class="form-grid" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    pill-density="compact"
                    .label=${this.t('work_item_create_modal.label_title')}
                    .placeholder=${this.t('work_item_create_modal.title_placeholder')}
                    .value=${draft.title}
                    ?disabled=${this._form.submitting}
                    @change=${this._onTitleChange}
                ></platform-field>
                ${this._renderFieldError('title')}
                <platform-field
                    type="text"
                    mode="edit"
                    pill-density="compact"
                    .label=${this.t('work_item_create_modal.label_description')}
                    .value=${draft.description}
                    ?disabled=${this._form.submitting}
                    @change=${this._onDescriptionChange}
                ></platform-field>
            </form>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('work_item_create_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => this._performSave()}>
                    ${this._form.submitting
                        ? this.t('work_item_create_modal.saving')
                        : this.t('work_item_create_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('worktracker-work-item-create-modal', WorkItemCreateModal);
registerModalKind(WorkItemCreateModal.modalKind, 'worktracker-work-item-create-modal');

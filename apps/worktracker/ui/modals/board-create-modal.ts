/**
 * BoardCreateModal — создание канбан-доски.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import type { PropertyValues } from 'lit';
import type { ResourceController, FormController } from '@platform/lib/base/use-resource.js';

const FORM_NAME = 'worktracker/board_create_form';
const BOARDS_NAME = 'worktracker/boards';

export class WorktrackerBoardCreateModal extends PlatformFormModal {
    static modalKind = 'worktracker.board_create';
    static i18nNamespace = 'worktracker';

    private _boards: ResourceController;
    private _form: FormController;

    static override styles = [
        PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-4); }
        `,
    ];

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this._boards = this.useResource(BOARDS_NAME);
        this._form = this.useForm(FORM_NAME);
    }

    override connectedCallback() {
        super.connectedCallback();
        this._form.openForm({ name: '' });
        this.useEvent(this._boards.resource.events.CREATED, () => {
            this.closeAfterSave();
        });
    }

    override disconnectedCallback() {
        this._form.close();
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>) {
        super.willUpdate(changed);
        const draft = this._form.draft;
        this.isDirty = typeof draft.name === 'string' && draft.name.trim().length > 0;
    }

    override async _performSave(): Promise<void> {
        this._form.submit();
    }

    override renderHeader() {
        return this.t('board_create_modal.header');
    }

    override renderSaveHeaderButton() {
        const draft = this._form.draft;
        const hasName = typeof draft.name === 'string' && draft.name.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !hasName,
            title: this.t('board_create_modal.submit'),
        });
    }

    override renderBody() {
        const draft = this._form.draft;
        const nameErrorKey = this._form.errors.name;
        return html`
            <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); void this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('board_create_modal.label_name')}
                    .placeholder=${this.t('board_create_modal.name_placeholder')}
                    .value=${draft.name}
                    .error=${nameErrorKey ? this.t(nameErrorKey) : ''}
                    ?disabled=${this._form.submitting}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => {
                        const value = e.detail && typeof e.detail.value === 'string' ? e.detail.value : '';
                        this._form.setField('name', value);
                    }}
                ></platform-field>
            </form>
        `;
    }

    override renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('board_create_modal.cancel')}
                </button>
                <button type="button" class="btn btn-primary"
                        ?disabled=${this._form.submitting}
                        @click=${() => this._performSave()}>
                    ${this._form.submitting
                        ? this.t('board_create_modal.saving')
                        : this.t('board_create_modal.submit')}
                </button>
            </div>
        `;
    }
}

customElements.define('worktracker-board-create-modal', WorktrackerBoardCreateModal);
registerModalKind(WorktrackerBoardCreateModal.modalKind, 'worktracker-board-create-modal');

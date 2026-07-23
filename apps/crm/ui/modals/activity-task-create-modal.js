/**
 * CRMActivityTaskCreateModal — создание пары CRMEntity(task) + WorkItem.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';

const FORM_NAME = 'crm/activity_task_create_form';
const CREATE_OP = 'crm/activity_task_create';

export class CRMActivityTaskCreateModal extends PlatformFormModal {
    static modalKind = 'crm.activity_task_create';
    static i18nNamespace = 'crm';

    static properties = {
        namespace: { type: String },
    };

    static styles = [
        ...PlatformFormModal.styles,
        css`
            .form-grid { display: grid; gap: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this.namespace = 'default';
        this._form = this.useForm(FORM_NAME);
        this._createOp = this.useOp(CREATE_OP);
    }

    connectedCallback() {
        super.connectedCallback();
        const ns = typeof this.namespace === 'string' && this.namespace.length > 0
            ? this.namespace
            : 'default';
        this._form.openForm({
            title: '',
            description: '',
            namespace: ns,
            priority: 'normal',
            due_date: '',
        });
        this.useEvent(this._createOp.op.events.SUCCEEDED, () => {
            this.closeAfterSave();
        });
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

    async _performSave() {
        const draft = this._form.draft;
        const title = typeof draft.title === 'string' ? draft.title.trim() : '';
        if (!title) {
            return;
        }
        this._form.setField('namespace', typeof this.namespace === 'string' && this.namespace.length > 0
            ? this.namespace
            : 'default');
        this._form.submit();
    }

    renderHeader() {
        return this.t('tasks_page.create_title');
    }

    renderSaveHeaderButton() {
        const draft = this._form.draft;
        const hasTitle = typeof draft.title === 'string' && draft.title.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !hasTitle,
            title: this.t('tasks_page.create'),
        });
    }

    renderBody() {
        const draft = this._form.draft;
        return html`
            <form class="form-grid" @submit=${(e) => { e.preventDefault(); this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tasks_page.field_title')}
                    .value=${draft.title}
                    @change=${(e) => this._form.setField('title', e.detail.value)}
                ></platform-field>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('tasks_page.field_description')}
                    .value=${draft.description}
                    @change=${(e) => this._form.setField('description', e.detail.value)}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    .label=${this.t('tasks_page.field_priority')}
                    .value=${draft.priority}
                    .config=${{
                        values: [
                            { value: 'low', label: this.t('tasks_page.priority_low') },
                            { value: 'normal', label: this.t('tasks_page.priority_normal') },
                            { value: 'high', label: this.t('tasks_page.priority_high') },
                            { value: 'urgent', label: this.t('tasks_page.priority_urgent') },
                        ],
                    }}
                    @change=${(e) => this._form.setField('priority', e.detail.value)}
                ></platform-field>
                <platform-field
                    type="date"
                    mode="edit"
                    .label=${this.t('tasks_page.field_due')}
                    .value=${draft.due_date}
                    @change=${(e) => this._form.setField('due_date', e.detail.value || '')}
                ></platform-field>
            </form>
        `;
    }
}

customElements.define('crm-activity-task-create-modal', CRMActivityTaskCreateModal);
registerModalKind(CRMActivityTaskCreateModal.modalKind, 'crm-activity-task-create-modal');

/**
 * CRMActivityTaskCreateModal — создание пары CRMEntity(task) + WorkItem.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import type {
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
} from 'lit';
import type {
    FormController,
    OpController,
} from '@platform/lib/base/use-resource.js';

const FORM_NAME = 'crm/activity_task_create_form';
const CREATE_OP = 'crm/activity_task_create';

export class CRMActivityTaskCreateModal extends PlatformFormModal {
    static modalKind = 'crm.activity_task_create';
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        namespace: { type: String },
    };
    declare namespace: string;

    static override styles: CSSResultGroup = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .form-grid { display: grid; gap: var(--space-3); }
        `,
    ];

    private _form: FormController;
    private _createOp: OpController;

    constructor() {
        super();
        this.size = 'sm';
        this.headerSavePrimary = true;
        this.namespace = '';
        this._form = this.useForm(FORM_NAME);
        this._createOp = this.useOp(CREATE_OP);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.namespace !== 'string' || this.namespace.length === 0) {
            throw new Error('CRMActivityTaskCreateModal: namespace required');
        }
        this._form.openForm({
            title: '',
            description: '',
            namespace: this.namespace,
            priority: 'normal',
            due_date: '',
        });
        this.useEvent(this._createOp.op.events.SUCCEEDED, () => {
            this.closeAfterSave();
        });
    }

    override disconnectedCallback(): void {
        this._form.close();
        super.disconnectedCallback();
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        const draft = this._form.draft;
        this.isDirty = typeof draft.title === 'string' && draft.title.length > 0;
    }

    override async _performSave() {
        const draft = this._form.draft;
        const title = typeof draft.title === 'string' ? draft.title.trim() : '';
        if (!title) {
            return;
        }
        if (typeof this.namespace !== 'string' || this.namespace.length === 0) {
            throw new Error('CRMActivityTaskCreateModal._performSave: namespace required');
        }
        this._form.setField('namespace', this.namespace);
        this._form.submit();
    }

    override renderHeader() {
        return this.t('tasks_page.create_title');
    }

    override renderSaveHeaderButton() {
        const draft = this._form.draft;
        const hasTitle = typeof draft.title === 'string' && draft.title.trim().length > 0;
        return this._renderHeaderSaveIcon({
            onClick: () => this._performSave(),
            disabled: this._form.submitting || !hasTitle,
            title: this.t('tasks_page.create'),
        });
    }

    override renderBody() {
        const draft = this._form.draft;
        return html`
            <form class="form-grid" @submit=${(e: Event) => { e.preventDefault(); this._performSave(); }}>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('tasks_page.field_title')}
                    .value=${draft.title}
                    @change=${(e: CustomEvent) => this._form.setField('title', e.detail.value)}
                ></platform-field>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('tasks_page.field_description')}
                    .value=${draft.description}
                    @change=${(e: CustomEvent) => this._form.setField('description', e.detail.value)}
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
                    @change=${(e: CustomEvent) => this._form.setField('priority', e.detail.value)}
                ></platform-field>
                <platform-field
                    type="date"
                    mode="edit"
                    .label=${this.t('tasks_page.field_due')}
                    .value=${draft.due_date}
                    @change=${(e: CustomEvent) => { const due = (e as CustomEvent).detail.value;
                        if (due === null || due === undefined || due === '') {
                            this._form.setField('due_date', '');
                            return;
                        }
                        if (typeof due !== 'string') {
                            throw new Error('CRMActivityTaskCreateModal: due_date must be string');
                        }
                        this._form.setField('due_date', due);
                    }}
                ></platform-field>
            </form>
        `;
    }
}

customElements.define('crm-activity-task-create-modal', CRMActivityTaskCreateModal);
registerModalKind(CRMActivityTaskCreateModal.modalKind, 'crm-activity-task-create-modal');

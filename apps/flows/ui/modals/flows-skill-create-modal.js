/**
 * flows-skill-create-modal — создание skill для flow.
 *
 * Использует useOp('flows/skill_create'). После успеха страница редактора
 * загружает обновлённый flow через push `flows/skill/created` (см. Stage 10).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

const SKILL_ID_PATTERN = /^[a-z][a-z0-9_]*$/;

export class FlowsSkillCreateModal extends PlatformFormModal {
    static modalKind = 'flows.skill_create';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        _skillId: { state: true },
        _name: { state: true },
        _description: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field input, .field textarea {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
            }
            .field textarea { min-height: 72px; resize: vertical; }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .form-error { color: var(--error); font-size: var(--text-xs); }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this._skillId = '';
        this._name = '';
        this._description = '';
        this._createSkill = this.useOp('flows/skill_create');
        this._flows = this.useResource('flows/flows');
    }

    renderHeader() {
        return html`<h3>${this.t('skill_create_modal.title')}</h3>`;
    }

    renderBody() {
        const validId = SKILL_ID_PATTERN.test(this._skillId);
        return html`
            <div class="field">
                <label>${this.t('skill_create_modal.field_skill_id')}</label>
                <input
                    type="text"
                    .value=${this._skillId}
                    placeholder="my_skill"
                    @input=${(e) => { this._skillId = e.target.value; this.isDirty = true; }}
                />
                ${this._skillId && !validId
                    ? html`<div class="form-error">${this.t('skill_create_modal.err_skill_id_pattern')}</div>`
                    : ''}
            </div>
            <div class="field">
                <label>${this.t('skill_create_modal.field_name')}</label>
                <input
                    type="text"
                    .value=${this._name}
                    @input=${(e) => { this._name = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="field">
                <label>${this.t('skill_create_modal.field_description')}</label>
                <textarea
                    .value=${this._description}
                    @input=${(e) => { this._description = e.target.value; this.isDirty = true; }}
                ></textarea>
            </div>
        `;
    }

    renderFooter() {
        const validId = SKILL_ID_PATTERN.test(this._skillId);
        const validName = this._name.trim().length > 0;
        return html`
            <platform-button @click=${() => this.close()}>${this.t('skill_create_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!(validId && validName)} @click=${this._onSubmit}>
                ${this.t('skill_create_modal.action_create')}
            </platform-button>
        `;
    }

    async _onSubmit() {
        if (!this.flowId) return;
        await this._createSkill.run({
            flow_id: this.flowId,
            body: {
                skill_id: this._skillId.trim(),
                name: this._name.trim(),
                description: this._description,
                nodes: {},
                edges: [],
            },
        });
        await this._flows.get(this.flowId);
        this.closeAfterSave();
    }
}

customElements.define('flows-skill-create-modal', FlowsSkillCreateModal);
registerModalKind(FlowsSkillCreateModal.modalKind, 'flows-skill-create-modal');

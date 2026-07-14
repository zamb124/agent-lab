/**
 * Create Agent Skill from scratch.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-button.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';

const SKILL_ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const DEFAULT_BODY = `# Skill

1. Describe the goal
2. List the steps
3. Call unlocked tools when needed
`;

export class FlowsAgentSkillCreateModal extends PlatformFormModal {
    static modalKind = 'flows.agent_skill_create';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        onCreated: { attribute: false },
        _agentSkillId: { state: true },
        _name: { state: true },
        _description: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        glassStyles,
        css`
            .stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .hint {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.4;
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'md';
        this.onCreated = null;
        this._agentSkillId = '';
        this._name = '';
        this._description = '';
        this._skills = this.useResource('flows/agent_skills');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('open') && this.open) {
            this._agentSkillId = '';
            this._name = '';
            this._description = '';
            this.isDirty = false;
        }
    }

    renderHeader() {
        return html`<h3>${this.t('agent_skill_create_modal.title')}</h3>`;
    }

    _canSubmit() {
        return (
            SKILL_ID_PATTERN.test(this._agentSkillId)
            && this._name.trim().length > 0
            && this._description.trim().length > 0
            && !this._skills.createInFlight
        );
    }

    async handleSubmit() {
        if (!this._canSubmit()) return;
        const payload = {
            agent_skill_id: this._agentSkillId.trim(),
            name: this._name.trim(),
            description: this._description.trim(),
            body_markdown: DEFAULT_BODY,
            tool_refs: [],
            depends_on: [],
            references: [],
            assets: [],
            activation: 'explicit',
        };
        const requested = this._skills.create(payload);
        if (!requested || typeof requested.id !== 'string') {
            return;
        }
        const item = await this._waitCreated(requested.id);
        if (typeof this.onCreated === 'function') {
            this.onCreated(item);
        }
        this.closeAfterSave();
    }

    _waitCreated(requestedId) {
        const bus = this._skills.bus;
        const successType = this._skills.resource.events.CREATED;
        const failedType = this._skills.resource.events.CREATE_FAILED;
        return new Promise((resolve, reject) => {
            let offSuccess = null;
            let offFailed = null;
            const cleanup = () => {
                if (typeof offSuccess === 'function') offSuccess();
                if (typeof offFailed === 'function') offFailed();
            };
            offSuccess = bus.subscribeType(successType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const item = event.payload && typeof event.payload.item === 'object'
                    ? event.payload.item
                    : null;
                resolve(item);
            });
            offFailed = bus.subscribeType(failedType, (event) => {
                if (!event.meta || event.meta.causation_id !== requestedId) return;
                cleanup();
                const message = event.payload && typeof event.payload.message === 'string'
                    ? event.payload.message
                    : 'create failed';
                reject(new Error(message));
            });
        });
    }

    renderBody() {
        return html`
            <div class="stack">
                <p class="hint">${this.t('agent_skill_create_modal.intro')}</p>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('agent_skill_create_modal.field_id')}
                    .hint=${this.t('agent_skill_create_modal.field_id_hint')}
                    .placeholder=${this.t('agent_skill_create_modal.field_id_placeholder')}
                    .value=${this._agentSkillId}
                    @change=${(e) => {
                        this._agentSkillId = typeof e.detail?.value === 'string' ? e.detail.value.trim() : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('agent_skill_create_modal.field_name')}
                    .value=${this._name}
                    @change=${(e) => {
                        this._name = typeof e.detail?.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
                <platform-field
                    type="text"
                    mode="edit"
                    .label=${this.t('agent_skill_create_modal.field_description')}
                    .hint=${this.t('agent_skill_create_modal.field_description_hint')}
                    .value=${this._description}
                    @change=${(e) => {
                        this._description = typeof e.detail?.value === 'string' ? e.detail.value : '';
                        this.isDirty = true;
                    }}
                ></platform-field>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button variant="ghost" @click=${() => this.close()}>
                ${this.t('common.action_cancel')}
            </platform-button>
            <platform-button
                variant="primary"
                ?disabled=${!this._canSubmit()}
                @click=${() => this.handleSubmit()}
            >
                ${this.t('common.action_create')}
            </platform-button>
        `;
    }
}

customElements.define('flows-agent-skill-create-modal', FlowsAgentSkillCreateModal);
registerModalKind(FlowsAgentSkillCreateModal.modalKind, 'flows-agent-skill-create-modal');

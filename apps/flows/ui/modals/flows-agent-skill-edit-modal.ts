/**
 * Edit Agent Skill in a modal. The editor is the same component the Skill Library uses.
 */

import type { ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '../components/agent-skills/flows-agent-skill-editor.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';

function eventDetail(event: Event): Record<string, unknown> | null {
    if (!(event instanceof CustomEvent) || !isPlainObject(event.detail)) {
        return null;
    }
    return event.detail;
}

function skillName(skill: unknown): string | null {
    if (!isPlainObject(skill)) {
        return null;
    }
    const name = skill.name;
    return typeof name === 'string' && name.length > 0 ? name : null;
}
import { AGENT_SKILL_ICON, mapAgentSkillItem } from '../_helpers/agent-skill-map.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

export class FlowsAgentSkillEditModal extends PlatformModal {
    static modalKind = 'flows.agent_skill_edit';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        agentSkillId: { type: String, attribute: false },
        onSaved: { attribute: false },
        onDuplicated: { attribute: false },
        onDeleted: { attribute: false },
        _skill: { state: true },
        _loadPhase: { state: true },
        _activeSkillId: { state: true },
    }
    declare agentSkillId: string;
    declare onSaved: any;
    declare onDuplicated: any;
    declare onDeleted: any;
    declare _skill: any;
    declare _loadPhase: string;
    declare _activeSkillId: string;
;

    static override styles: CSSResultGroup = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .body-wrap {
                box-sizing: border-box;
                width: 100%;
                min-width: 0;
                min-height: 280px;
                max-height: min(90vh, 1400px);
                overflow: auto;
            }
            .loading,
            .error {
                display: flex;
                justify-content: center;
                align-items: center;
                gap: var(--space-2);
                min-height: 200px;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .modal-header {
                padding: var(--space-3) var(--space-4) var(--space-2) var(--space-4);
                gap: var(--space-2);
            }
            .skill-edit-title {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .skill-edit-title platform-icon {
                color: var(--accent);
            }
        `,
    ];
    private _skills: ResourceController;

    constructor() {
        super();
        this.size = 'full';
        this.agentSkillId = '';
        this.onSaved = null;
        this.onDuplicated = null;
        this.onDeleted = null;
        this._skill = null;
        this._loadPhase = 'idle';
        this._activeSkillId = '';
        this._skills = this.useResource('flows/agent_skills');
    }

    override willUpdate(changed: PropertyValues<this>): void {
        if ((changed.has('open') && this.open) || (changed.has('agentSkillId') && this.open)) {
            void this._loadSkill(asString(this.agentSkillId));
        }
        super.willUpdate?.(changed);
    }

    async _loadSkill(agentSkillId: any) {
        const id = asString(agentSkillId).trim();
        this._activeSkillId = id;
        this._skill = null;
        if (id.length === 0) {
            this._loadPhase = 'error';
            return;
        }
        this._loadPhase = 'loading';
        const fromList = asArray(this._skills.items).find((item) => isPlainObject(item) && item.agent_skill_id === id);
        if (fromList) {
            this._skill = fromList;
        }
        try {
            const loaded = await this._skills.fetchItem(id);
            if (this._activeSkillId !== id) {
                return;
            }
            this._skill = mapAgentSkillItem(loaded);
            this._loadPhase = 'ready';
        } catch (_err) {
            if (this._activeSkillId !== id) {
                return;
            }
            this._loadPhase = 'error';
            this._skill = null;
        }
    }

    _catalogItems() {
        return asArray(this._skills.items);
    }

    _onSaved(e: Event) {
        const detail = eventDetail(e);
        if (detail === null || !isPlainObject(detail.item)) {
            return;
        }
        const skillId = detail.item.agent_skill_id;
        if (typeof skillId !== 'string') {
            return;
        }
        this._skill = detail.item;
        if (typeof this.onSaved === 'function') {
            this.onSaved({ agent_skill_id: skillId, item: detail.item });
        }
    }

    _onDeleted(e: Event) {
        const detail = eventDetail(e);
        const id = detail === null ? undefined : detail.agent_skill_id;
        if (typeof this.onDeleted === 'function' && typeof id === 'string') {
            this.onDeleted({ agent_skill_id: id });
        }
        this.close();
    }

    async _onDuplicated(e: Event) {
        const detail = eventDetail(e);
        if (detail === null) {
            return;
        }
        const fromId = asString(detail.fromId);
        const toId = asString(detail.toId);
        const skill = detail.skill && typeof detail.skill === 'object' ? detail.skill : null;
        if (typeof this.onDuplicated === 'function') {
            this.onDuplicated({ fromId, toId, skill });
        }
        if (toId.length > 0) {
            this.agentSkillId = toId;
            await this._loadSkill(toId);
        }
    }

    override renderHeader() {
        const named = skillName(this._skill);
        const name = named === null ? asString(this._activeSkillId) : named;
        return html`
            <span class="skill-edit-title">
                <platform-icon name=${AGENT_SKILL_ICON} size="18"></platform-icon>
                <span>${this.t('agent_skill_edit_modal.title', { name })}</span>
            </span>
        `;
    }

    override renderBody() {
        if (this._loadPhase === 'loading' || this._loadPhase === 'idle') {
            return html`<div class="body-wrap"><div class="loading"><glass-spinner></glass-spinner></div></div>`;
        }
        if (this._loadPhase === 'error' || !this._skill) {
            return html`<div class="body-wrap"><div class="error">${this.t('agent_skill_edit_modal.error')}</div></div>`;
        }
        return html`
            <div class="body-wrap">
                <flows-agent-skill-editor
                    .skill=${this._skill}
                    .catalogItems=${this._catalogItems()}
                    @skills-saved=${this._onSaved}
                    @skills-deleted=${this._onDeleted}
                    @skills-duplicated=${this._onDuplicated}
                ></flows-agent-skill-editor>
            </div>
        `;
    }

    override renderFooter() {
        return nothing;
    }
}

customElements.define('flows-agent-skill-edit-modal', FlowsAgentSkillEditModal);
registerModalKind(FlowsAgentSkillEditModal.modalKind, 'flows-agent-skill-edit-modal');

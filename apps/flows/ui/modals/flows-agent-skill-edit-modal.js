/**
 * Edit Agent Skill in a modal — same <flows-agent-skill-editor> as Skill Library.
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '../components/agent-skills/flows-agent-skill-editor.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { AGENT_SKILL_ICON, mapAgentSkillItem } from '../_helpers/agent-skill-map.js';

export class FlowsAgentSkillEditModal extends PlatformModal {
    static modalKind = 'flows.agent_skill_edit';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        agentSkillId: { type: String, attribute: false },
        onSaved: { attribute: false },
        onDuplicated: { attribute: false },
        onDeleted: { attribute: false },
        _skill: { state: true },
        _loadPhase: { state: true },
        _activeSkillId: { state: true },
    };

    static styles = [
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
        `,
    ];

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

    willUpdate(changed) {
        if ((changed.has('open') && this.open) || (changed.has('agentSkillId') && this.open)) {
            void this._loadSkill(asString(this.agentSkillId));
        }
        super.willUpdate?.(changed);
    }

    async _loadSkill(agentSkillId) {
        const id = asString(agentSkillId).trim();
        this._activeSkillId = id;
        this._skill = null;
        if (id.length === 0) {
            this._loadPhase = 'error';
            return;
        }
        this._loadPhase = 'loading';
        const fromList = asArray(this._skills.items).find((item) => item.agent_skill_id === id);
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

    _onSaved(e) {
        const item = e?.detail?.item;
        if (item && typeof item.agent_skill_id === 'string') {
            this._skill = item;
            if (typeof this.onSaved === 'function') {
                this.onSaved({ agent_skill_id: item.agent_skill_id, item });
            }
        }
    }

    _onDeleted(e) {
        const id = e?.detail?.agent_skill_id;
        if (typeof this.onDeleted === 'function' && typeof id === 'string') {
            this.onDeleted({ agent_skill_id: id });
        }
        this.close();
    }

    async _onDuplicated(e) {
        const detail = e?.detail;
        if (!isPlainObject(detail)) {
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

    renderHeader() {
        const name = this._skill && typeof this._skill.name === 'string' && this._skill.name.length > 0
            ? this._skill.name
            : asString(this._activeSkillId);
        return html`
            <span class="skill-edit-title">
                <platform-icon name=${AGENT_SKILL_ICON} size="18"></platform-icon>
                <span>${this.t('agent_skill_edit_modal.title', { name })}</span>
            </span>
        `;
    }

    renderBody() {
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

    renderFooter() {
        return nothing;
    }
}

customElements.define('flows-agent-skill-edit-modal', FlowsAgentSkillEditModal);
registerModalKind(FlowsAgentSkillEditModal.modalKind, 'flows-agent-skill-edit-modal');

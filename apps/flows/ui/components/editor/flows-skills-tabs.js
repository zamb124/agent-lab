/**
 * flows-skills-tabs — табы skills с кнопками удаления и создания.
 *
 * Источник: useResource('flows/flows').get(flowId) → flow.skills (объект).
 *
 * Actions:
 *   - select skill → this.navigate('flow_editor' | 'flow_editor_skill', ...)
 *   - delete skill → useOp('flows/skill_remove').run({ flow_id, skill_id })
 *   - create skill → this.openModal('flows.skill_create', { flowId })
 *
 * `base` — синтетический skill, не редактируется и не удаляется.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsSkillsTabs extends PlatformElement {
    static properties = {
        flowId: { type: String },
        activeSkillId: { type: String, attribute: 'active-skill-id' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                overflow-x: auto;
                scrollbar-width: thin;
            }
            .tabs-row {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex: 1;
                min-width: 0;
            }
            .tab-wrap {
                display: inline-flex;
                align-items: stretch;
                border-radius: var(--radius-sm);
                overflow: hidden;
                border: 1px solid transparent;
                transition: border-color var(--duration-fast);
            }
            .tab-wrap:hover { border-color: var(--border-subtle); }
            .tab-wrap[active] {
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            .tab {
                padding: 4px var(--space-2);
                background: transparent;
                border: none;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                font-family: inherit;
            }
            .tab-wrap[active] .tab { color: var(--accent); }
            .tab-close {
                width: 22px;
                display: flex; align-items: center; justify-content: center;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: 16px;
                line-height: 1;
                font-family: inherit;
            }
            .tab-close:hover { color: var(--error); }
            .add-skill-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 4px var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px dashed var(--border-default);
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-family: inherit;
                cursor: pointer;
                transition: all var(--duration-fast);
                margin-left: auto;
                flex-shrink: 0;
            }
            .add-skill-btn:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-subtle); }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.activeSkillId = 'base';
        this._flows = this.useResource('flows/flows');
        this._skillDelete = this.useOp('flows/skill_remove');
    }

    _selectSkill(skillId) {
        if (skillId === 'base') {
            this.navigate('flow_editor', { flowId: this.flowId });
        } else {
            this.navigate('flow_editor_skill', { flowId: this.flowId, skillId });
        }
    }

    _create() {
        this.openModal('flows.skill_create', { flowId: this.flowId });
    }

    async _deleteSkill(e, skillId) {
        e.stopPropagation();
        if (!this.flowId || skillId === 'base') return;
        await this._skillDelete.run({ flow_id: this.flowId, skill_id: skillId });
        if (this.activeSkillId === skillId) {
            this.navigate('flow_editor', { flowId: this.flowId });
        }
    }

    render() {
        const flow = (this._flows.items || []).find((f) => f && f.flow_id === this.flowId);
        const skillIds = flow && flow.skills ? Object.keys(flow.skills) : [];
        return html`
            <div class="tabs-row">
                <div class="tab-wrap" ?active=${this.activeSkillId === 'base'}>
                    <button class="tab" type="button" @click=${() => this._selectSkill('base')}>
                        ${this.t('skills_tabs.base')}
                    </button>
                </div>
                ${skillIds.map((sid) => html`
                    <div class="tab-wrap" ?active=${this.activeSkillId === sid}>
                        <button class="tab" type="button" @click=${() => this._selectSkill(sid)}>
                            ${flow.skills[sid] && flow.skills[sid].name ? flow.skills[sid].name : sid}
                        </button>
                        <button
                            class="tab-close"
                            type="button"
                            title=${this.t('skills_tabs.delete')}
                            @click=${(e) => this._deleteSkill(e, sid)}
                        >×</button>
                    </div>
                `)}
            </div>
            <button class="add-skill-btn" type="button" @click=${this._create}>
                <platform-icon name="plus" size="14"></platform-icon>
                ${this.t('skills_tabs.add')}
            </button>
        `;
    }
}

customElements.define('flows-skills-tabs', FlowsSkillsTabs);

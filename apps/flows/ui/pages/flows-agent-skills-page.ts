/**
 * Skill Library — master-detail catalog for Agent Skills.
 */

import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '../components/agent-skills/flows-agent-skills-list.js';
import '../components/agent-skills/flows-agent-skill-editor.js';
import '../components/agent-skills/flows-agent-skills-how-it-works.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import type { PlatformEvent } from '@platform/lib/events/contract.js';

function eventPayload(event: PlatformEvent): Record<string, unknown> | null {
    return isPlainObject(event.payload) ? event.payload : null;
}

function eventDetail(event: Event): Record<string, unknown> | null {
    if (!(event instanceof CustomEvent) || !isPlainObject(event.detail)) return null;
    return event.detail;
}
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsAgentSkillsPage extends PlatformPage {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        _selectedId: { state: true },
        _query: { state: true },
        _selectedSkill: { state: true },
    }
    declare _selectedId: string;
    declare _query: string;
    declare _selectedSkill: any;
;

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                height: 100%;
                min-height: 0;
                box-sizing: border-box;
            }
            .workspace {
                display: grid;
                grid-template-columns: minmax(280px, 360px) minmax(0, 1fr);
                gap: var(--space-4);
                flex: 1;
                min-height: 0;
            }
            .rail,
            .pane {
                min-height: 0;
                height: 100%;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            .pane {
                overflow: auto;
                padding-right: 2px;
            }
            .pane-empty {
                display: flex;
                flex-direction: column;
                justify-content: center;
                min-height: 100%;
                padding: var(--space-4);
            }
            .header-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            @media (max-width: 900px) {
                .workspace {
                    grid-template-columns: 1fr;
                    grid-template-rows: minmax(220px, 40%) minmax(0, 1fr);
                }
            }
        `,
    ];
    private _skills: ResourceController;
    private _ensureSeed: OpController;

    constructor() {
        super();
        this._selectedId = '';
        this._query = '';
        this._selectedSkill = null;
        this._skills = this.useResource('flows/agent_skills', { autoload: false });
        this._ensureSeed = this.useOp('flows/agent_skills_ensure_seed');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._ensureCatalog();
        this.useEvent('flows/agent_skills/created', (event: PlatformEvent) => {
            const payload = eventPayload(event);
            const item = payload !== null && isPlainObject(payload.item) ? payload.item : null;
            const skillId = item === null ? undefined : item.agent_skill_id;
            if (typeof skillId === 'string') {
                this._selectSkill(skillId);
            }
        });
        this.useEvent('flows/agent_skills/removed', (event: PlatformEvent) => {
            const payload = eventPayload(event);
            const id = payload === null ? undefined : payload.agent_skill_id;
            if (typeof id === 'string' && id === this._selectedId) {
                this._selectedId = '';
                this._selectedSkill = null;
            }
        });
    }

    async _ensureCatalog() {
        await this._ensureSeed.run({});
        await this._skills.load({ limit: 200, offset: 0 });
    }

    async _selectSkill(agentSkillId: any) {
        const id = asString(agentSkillId);
        this._selectedId = id;
        if (id.length === 0) {
            this._selectedSkill = null;
            return;
        }
        const fromList = asArray(this._skills.items).find((item) => item.agent_skill_id === id);
        if (fromList) {
            this._selectedSkill = fromList;
        }
        const loaded = await this._skills.fetchItem(id);
        this._selectedSkill = loaded;
    }

    _onListSelect(e: Event) {
        const detail = eventDetail(e);
        const id = detail === null ? undefined : detail.agent_skill_id;
        if (typeof id === 'string') {
            void this._selectSkill(id);
        }
    }

    _onQuery(e: Event) {
        const detail = eventDetail(e);
        const query = detail === null ? undefined : detail.query;
        this._query = typeof query === 'string' ? query : '';
    }

    _openCreate() {
        this.openModal('flows.agent_skill_create', {
            onCreated: (item: any) => {
                if (item && typeof item.agent_skill_id === 'string') {
                    void this._selectSkill(item.agent_skill_id);
                }
            },
        });
    }

    _openImport() {
        this.openModal('flows.agent_skill_import', {
            onImported: (item: any) => {
                if (item && typeof item.agent_skill_id === 'string') {
                    void this._skills.load({ limit: 200, offset: 0 });
                    void this._selectSkill(item.agent_skill_id);
                }
            },
        });
    }

    _onHowAction(e: Event) {
        const detail = eventDetail(e);
        const action = detail === null ? undefined : detail.action;
        if (action === 'create') {
            this._openCreate();
            return;
        }
        if (action === 'import') {
            this._openImport();
            return;
        }
        if (action === 'example') {
            this.navigate('flow_chat', { flowId: 'lara' });
        }
    }

    _onSaved(e: Event) {
        const detail = eventDetail(e);
        const item = detail !== null && isPlainObject(detail.item) ? detail.item : null;
        const skillId = item === null ? undefined : item.agent_skill_id;
        if (typeof skillId === 'string') {
            this._selectedSkill = item;
            this._selectedId = skillId;
        }
    }

    _onDeleted() {
        this._selectedId = '';
        this._selectedSkill = null;
    }

    _onDuplicated(e: Event) {
        const detail = eventDetail(e);
        const toId = detail === null ? undefined : detail.toId;
        const skill = detail !== null && isPlainObject(detail.skill) ? detail.skill : null;
        if (typeof toId === 'string' && toId.length > 0) {
            if (skill && typeof skill === 'object') {
                this._selectedSkill = skill;
                this._selectedId = toId;
            }
            void this._selectSkill(toId);
        }
    }

    override render(): TemplateResult {
        const items = asArray(this._skills.items);
        const hasSelection = typeof this._selectedId === 'string' && this._selectedId.length > 0;
        return html`
            <platform-breadcrumbs></platform-breadcrumbs>
            <page-header title=${this.t('agent_skills.page_title')} subtitle=${this.t('agent_skills.page_subtitle')}>
                <div slot="actions" class="header-actions">
                    <platform-button variant="secondary" density="compact" @click=${this._openImport}>
                        <platform-icon name="upload" size="16"></platform-icon>
                        ${this.t('agent_skills.action_import')}
                    </platform-button>
                    <platform-button variant="primary" density="compact" @click=${this._openCreate}>
                        <platform-icon name="plus" size="16"></platform-icon>
                        ${this.t('agent_skills.action_create')}
                    </platform-button>
                </div>
            </page-header>
            <div class="workspace">
                <div class="rail">
                    <flows-agent-skills-list
                        .items=${items}
                        .selectedId=${this._selectedId}
                        .query=${this._query}
                        ?loading=${this._skills.loading || this._ensureSeed.busy}
                        @skills-select=${this._onListSelect}
                        @skills-query=${this._onQuery}
                    ></flows-agent-skills-list>
                </div>
                <div class="pane">
                    ${hasSelection && this._selectedSkill
                        ? html`
                            <flows-agent-skill-editor
                                .skill=${this._selectedSkill}
                                .catalogItems=${items}
                                @skills-saved=${this._onSaved}
                                @skills-deleted=${this._onDeleted}
                                @skills-duplicated=${this._onDuplicated}
                            ></flows-agent-skill-editor>
                        `
                        : html`
                            <div class="pane-empty">
                                <flows-agent-skills-how-it-works
                                    show-actions
                                    @agent-skills-action=${this._onHowAction}
                                ></flows-agent-skills-how-it-works>
                            </div>
                        `}
                </div>
            </div>
        `;
    }
}

customElements.define('flows-agent-skills-page', FlowsAgentSkillsPage);

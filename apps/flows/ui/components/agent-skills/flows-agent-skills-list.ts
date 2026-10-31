/**
 * Left-rail catalog list for Skill Library.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import { AGENT_SKILL_ICON } from '../../_helpers/agent-skill-map.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsAgentSkillsList extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        items: { type: Array },
        selectedId: { type: String, attribute: 'selected-id' },
        loading: { type: Boolean },
        query: { type: String },
    }
    declare items: readonly unknown[];
    declare selectedId: string;
    declare loading: boolean;
    declare query: string;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 0;
                height: 100%;
            }
            .list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                overflow: auto;
                flex: 1;
                min-height: 0;
                padding-right: 2px;
            }
            .card {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--bg-elevated);
                cursor: pointer;
                text-align: left;
                color: inherit;
                font: inherit;
            }
            .card:hover {
                border-color: var(--border-strong, var(--accent));
            }
            .card[data-selected='true'] {
                border-color: var(--accent);
                box-shadow: inset 0 0 0 1px var(--accent);
            }
            .card-name {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-sm);
                font-weight: 600;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                min-width: 0;
            }
            .card-name platform-icon {
                flex-shrink: 0;
                color: var(--accent);
            }
            .card-name-text {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .card-desc {
                margin: 0;
                font-size: var(--text-xs);
                color: var(--text-secondary);
                line-height: 1.35;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
            }
            .badges {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                margin-top: var(--space-1);
            }
            .badge {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                border-radius: var(--radius-full, 999px);
                background: var(--bg-surface);
                color: var(--text-tertiary);
                font-size: 11px;
            }
            .empty {
                padding: var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
                text-align: center;
            }
            .loading {
                display: flex;
                justify-content: center;
                padding: var(--space-6);
            }
        `,
    ];

    constructor() {
        super();
        this.items = [];
        this.selectedId = '';
        this.loading = false;
        this.query = '';
    }

    _onQuery(e: Event) {
        const detail = e instanceof CustomEvent ? e.detail : null;
        const value = isPlainObject(detail) ? detail.value : undefined;
        this.emit('skills-query', { query: typeof value === 'string' ? value : '' });
    }

    _select(id: string) {
        this.emit('skills-select', { agent_skill_id: id });
    }

    _filtered(): Record<string, unknown>[] {
        const q = this.query.trim().toLowerCase();
        const matched: Record<string, unknown>[] = [];
        for (const item of this.items) {
            if (!isPlainObject(item)) {
                throw new Error('flows-agent-skills-list: skill item must be an object');
            }
            if (q.length === 0) {
                matched.push(item);
                continue;
            }
            const name = skillString(item, 'name').toLowerCase();
            const description = skillString(item, 'description').toLowerCase();
            const id = skillId(item).toLowerCase();
            if (name.includes(q) || description.includes(q) || id.includes(q)) matched.push(item);
        }
        return matched;
    }

    override render(): TemplateResult {
        const filtered = this._filtered();
        return html`
            <platform-field
                type="string"
                input-type="search"
                mode="edit"
                .placeholder=${this.t('agent_skills.search_placeholder')}
                .value=${this.query}
                @change=${this._onQuery}
            ></platform-field>
            ${this.loading
                ? html`<div class="loading"><platform-spinner size="24"></platform-spinner></div>`
                : html`
                    <div class="list">
                        ${filtered.length === 0
                            ? html`<platform-empty-state icon="agent" title=${this.t('agent_skills.list_empty')}></platform-empty-state>`
                            : filtered.map((item) => {
                                const id = skillId(item);
                                const toolsCount = skillListLength(item, 'tool_refs');
                                const depsCount = skillListLength(item, 'depends_on');
                                return html`
                                    <article
                                        class="card"
                                        role="button"
                                        tabindex="0"
                                        data-selected=${id === this.selectedId ? 'true' : 'false'}
                                        @click=${() => this._select(id)}
                                        @keydown=${(e: KeyboardEvent) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault();
                                                this._select(id);
                                            }
                                        }}
                                    >
                                        <span class="card-name">
                                            <platform-icon name=${AGENT_SKILL_ICON} size="16"></platform-icon>
                                            <span class="card-name-text">${skillString(item, 'name')}</span>
                                        </span>
                                        <p class="card-desc">${skillString(item, 'description')}</p>
                                        <div class="badges">
                                            ${toolsCount > 0
                                                ? html`<span class="badge"><platform-icon name="wrench" size="12"></platform-icon>${this.t('agent_skills.badge_tools', { n: toolsCount })}</span>`
                                                : nothing}
                                            ${depsCount > 0
                                                ? html`<span class="badge"><platform-icon name="link" size="12"></platform-icon>${this.t('agent_skills.badge_depends', { n: depsCount })}</span>`
                                                : nothing}
                                        </div>
                                    </article>
                                `;
                            })}
                    </div>
                `}
        `;
    }
}

customElements.define('flows-agent-skills-list', FlowsAgentSkillsList);

function skillString(item: Record<string, unknown>, field: string): string {
    const value = item[field];
    if (typeof value !== 'string') {
        throw new Error(`flows-agent-skills-list: ${field} must be a string`);
    }
    return value;
}

function skillId(item: Record<string, unknown>): string {
    const value = skillString(item, 'agent_skill_id');
    if (value === '') {
        throw new Error('flows-agent-skills-list: agent_skill_id must be a non-empty string');
    }
    return value;
}

function skillListLength(item: Record<string, unknown>, field: string): number {
    const value = item[field];
    if (value === undefined || value === null) return 0;
    if (!Array.isArray(value)) {
        throw new Error(`flows-agent-skills-list: ${field} must be an array`);
    }
    return value.length;
}

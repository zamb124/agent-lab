/**
 * Left-rail catalog list for Skill Library.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { AGENT_SKILL_ICON } from '../../_helpers/agent-skill-map.js';

export class FlowsAgentSkillsList extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        items: { type: Array },
        selectedId: { type: String, attribute: 'selected-id' },
        loading: { type: Boolean },
        query: { type: String },
    };

    static styles = [
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

    _onQuery(e) {
        const value = e?.detail?.value;
        this.emit('skills-query', { query: typeof value === 'string' ? value : '' });
    }

    _select(id) {
        this.emit('skills-select', { agent_skill_id: id });
    }

    _filtered() {
        const items = Array.isArray(this.items) ? this.items : [];
        const q = typeof this.query === 'string' ? this.query.trim().toLowerCase() : '';
        if (q.length === 0) return items;
        return items.filter((item) => {
            const name = typeof item.name === 'string' ? item.name.toLowerCase() : '';
            const desc = typeof item.description === 'string' ? item.description.toLowerCase() : '';
            const id = typeof item.agent_skill_id === 'string' ? item.agent_skill_id.toLowerCase() : '';
            return name.includes(q) || desc.includes(q) || id.includes(q);
        });
    }

    render() {
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
                ? html`<div class="loading"><glass-spinner size="24"></glass-spinner></div>`
                : html`
                    <div class="list">
                        ${filtered.length === 0
                            ? html`<div class="empty">${this.t('agent_skills.list_empty')}</div>`
                            : filtered.map((item) => {
                                const id = item.agent_skill_id;
                                const toolsCount = Array.isArray(item.tool_refs) ? item.tool_refs.length : 0;
                                const depsCount = Array.isArray(item.depends_on) ? item.depends_on.length : 0;
                                return html`
                                    <article
                                        class="card"
                                        role="button"
                                        tabindex="0"
                                        data-selected=${id === this.selectedId ? 'true' : 'false'}
                                        @click=${() => this._select(id)}
                                        @keydown=${(e) => {
                                            if (e.key === 'Enter' || e.key === ' ') {
                                                e.preventDefault();
                                                this._select(id);
                                            }
                                        }}
                                    >
                                        <span class="card-name">
                                            <platform-icon name=${AGENT_SKILL_ICON} size="16"></platform-icon>
                                            <span class="card-name-text">${item.name}</span>
                                        </span>
                                        <p class="card-desc">${item.description}</p>
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

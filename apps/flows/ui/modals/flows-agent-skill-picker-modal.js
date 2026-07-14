/**
 * Pick Agent Skills from company catalog (attach to llm_node).
 */

import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-modal-search-field.js';
import '@platform/lib/components/platform-picker-card.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { panelShellStyles } from '@platform/lib/styles/shared/panel-shell.styles.js';
import { glassStyles } from '@platform/lib/styles/shared/glass.styles.js';
import { asArray, asString } from '../_helpers/flows-resolvers.js';
import { AGENT_SKILL_ICON } from '../_helpers/agent-skill-map.js';

export class FlowsAgentSkillPickerModal extends PlatformModal {
    static modalKind = 'flows.agent_skill_picker';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        excludeIds: { type: Array, attribute: false },
        onPick: { attribute: false },
        onPickBatch: { attribute: false },
        _query: { state: true },
        _selected: { state: true },
    };

    static styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        panelShellStyles,
        glassStyles,
        css`
            .stack {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
                gap: var(--space-3);
                align-content: start;
            }
            platform-picker-card {
                min-width: 0;
                --platform-picker-card-padding: var(--space-3);
            }
            .card-meta {
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
                background: var(--glass-solid-medium);
                color: var(--text-tertiary);
                font-size: 11px;
                line-height: 1.3;
            }
            .loading {
                display: flex;
                justify-content: center;
                padding: var(--space-6);
            }
            .empty {
                padding: var(--space-6);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
            .footer-row {
                display: flex;
                flex-wrap: wrap;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
            }
            .footer-actions {
                display: flex;
                gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.excludeIds = [];
        this.onPick = null;
        this.onPickBatch = null;
        this._query = '';
        this._selected = [];
        this._skills = this.useResource('flows/agent_skills', { autoload: false });
        this._ensureSeed = this.useOp('flows/agent_skills_ensure_seed');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('open') && this.open) {
            this._query = '';
            this._selected = [];
            void this._ensureCatalog();
        }
    }

    async _ensureCatalog() {
        await this._ensureSeed.run({});
        await this._skills.load({ limit: 200, offset: 0 });
    }

    renderHeader() {
        return html`<h3>${this.t('agent_skill_picker_modal.title')}</h3>`;
    }

    _excluded() {
        return new Set(asArray(this.excludeIds).map((id) => asString(id)).filter((id) => id.length > 0));
    }

    _filtered() {
        const excluded = this._excluded();
        const q = this._query.trim().toLowerCase();
        return asArray(this._skills.items).filter((item) => {
            const id = asString(item.agent_skill_id);
            if (id.length === 0 || excluded.has(id)) return false;
            if (q.length === 0) return true;
            const name = asString(item.name).toLowerCase();
            const desc = asString(item.description).toLowerCase();
            return name.includes(q) || desc.includes(q) || id.includes(q);
        });
    }

    _emptyMessageKey() {
        const catalogCount = asArray(this._skills.items).length;
        if (catalogCount === 0) {
            return 'agent_skill_picker_modal.empty';
        }
        return 'agent_skill_picker_modal.empty_all_attached';
    }

    _toggle(id) {
        if (this._selected.includes(id)) {
            this._selected = this._selected.filter((x) => x !== id);
            return;
        }
        this._selected = [...this._selected, id];
    }

    _confirm() {
        const selectedItems = asArray(this._skills.items).filter((item) =>
            this._selected.includes(item.agent_skill_id),
        );
        if (typeof this.onPickBatch === 'function') {
            this.onPickBatch(selectedItems);
        } else if (typeof this.onPick === 'function' && selectedItems.length === 1) {
            this.onPick(selectedItems[0]);
        }
        this.close();
    }

    _openLibrary() {
        this.close();
        this.navigate('agent_skills');
    }

    _cardMeta(item) {
        const toolsCount = asArray(item.tool_refs).length;
        const depsCount = asArray(item.depends_on).length;
        const refsCount = asArray(item.references).length;
        const assetsCount = asArray(item.assets).length;
        const activation = asString(item.activation);
        const activationKey = activation === 'auto'
            ? 'agent_skills.activation_auto'
            : activation === 'explicit'
                ? 'agent_skills.activation_explicit'
                : '';
        return html`
            <div class="card-meta">
                <span class="badge"><platform-icon name="wrench" size="12"></platform-icon>${this.t('agent_skills.badge_tools', { n: toolsCount })}</span>
                ${depsCount > 0
                    ? html`<span class="badge"><platform-icon name="link" size="12"></platform-icon>${this.t('agent_skills.badge_depends', { n: depsCount })}</span>`
                    : nothing}
                ${refsCount > 0
                    ? html`<span class="badge"><platform-icon name="file" size="12"></platform-icon>${this.t('agent_skills.badge_references', { n: refsCount })}</span>`
                    : nothing}
                ${assetsCount > 0
                    ? html`<span class="badge"><platform-icon name="paperclip" size="12"></platform-icon>${this.t('agent_skills.badge_assets', { n: assetsCount })}</span>`
                    : nothing}
                ${activationKey.length > 0
                    ? html`<span class="badge"><platform-icon name="target" size="12"></platform-icon>${this.t(activationKey)}</span>`
                    : nothing}
            </div>
        `;
    }

    renderBody() {
        const items = this._filtered();
        return html`
            <div class="stack">
                <platform-modal-search-field
                    layout="fill"
                    .value=${this._query}
                    .placeholder=${this.t('agent_skill_picker_modal.search')}
                    @change=${(e) => {
                        this._query = typeof e.detail?.value === 'string' ? e.detail.value : '';
                    }}
                ></platform-modal-search-field>
                ${this._skills.loading || this._ensureSeed.busy
                    ? html`<div class="loading"><glass-spinner></glass-spinner></div>`
                    : items.length === 0
                        ? html`<div class="empty">${this.t(this._emptyMessageKey())}</div>`
                        : html`
                            <div class="grid">
                                ${items.map((item) => {
                                    const selected = this._selected.includes(item.agent_skill_id);
                                    return html`
                                        <platform-picker-card
                                            ?selected=${selected}
                                            .title=${item.name}
                                            .subtitle=${item.description}
                                            @click=${() => this._toggle(item.agent_skill_id)}
                                        >
                                            <platform-icon slot="icon" name=${AGENT_SKILL_ICON} size="20"></platform-icon>
                                            ${this._cardMeta(item)}
                                        </platform-picker-card>
                                    `;
                                })}
                            </div>
                        `}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="footer-row">
                <platform-button variant="ghost" density="compact" @click=${this._openLibrary}>
                    <platform-icon name="external-link" size="14"></platform-icon>
                    ${this.t('agent_skill_picker_modal.open_library')}
                </platform-button>
                <div class="footer-actions">
                    <platform-button variant="ghost" @click=${() => this.close()}>
                        ${this.t('common.action_cancel')}
                    </platform-button>
                    <platform-button
                        variant="primary"
                        ?disabled=${this._selected.length === 0}
                        @click=${this._confirm}
                    >
                        ${this.t('agent_skill_picker_modal.add', { n: this._selected.length })}
                    </platform-button>
                </div>
            </div>
        `;
    }
}

customElements.define('flows-agent-skill-picker-modal', FlowsAgentSkillPickerModal);
registerModalKind(FlowsAgentSkillPickerModal.modalKind, 'flows-agent-skill-picker-modal');

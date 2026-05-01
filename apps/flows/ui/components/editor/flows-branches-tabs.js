/**
 * flows-branches-tabs — табы веток (branches) с кнопками удаления и создания.
 *
 * Источник: useResource('flows/flows').get(flowId) → flow.branches (объект).
 *
 * Actions:
 *   - select branch → this.navigate('flow_editor' | 'flow_editor_branch', ...)
 *   - delete branch → useOp('flows/branch_remove').run({ flow_id, branch_id })
 *   - create branch → this.openModal('flows.branch_create', { flowId })
 *
 * `base` — синтетическая базовая ветка, не редактируется и не удаляется.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import { asArray } from '../../_helpers/flows-resolvers.js';

export class FlowsBranchesTabs extends PlatformElement {
    static properties = {
        flowId: { type: String },
        activeBranchId: { type: String, attribute: 'active-branch-id' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: var(--space-2) var(--space-4);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
                overflow-x: auto;
                overflow-y: hidden;
                scrollbar-width: thin;
            }
            .tabs-row {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                width: max-content;
                min-width: 100%;
            }
            .tab-wrap {
                display: inline-flex;
                align-items: stretch;
                border-radius: var(--radius-full);
                overflow: hidden;
                border: 1px solid transparent;
                background: transparent;
                transition: all var(--duration-fast);
                flex-shrink: 0;
                white-space: nowrap;
            }
            .tab-wrap:hover { background: var(--glass-solid-medium); }
            .tab-wrap[active] {
                background: var(--glass-solid-strong);
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-subtle);
            }
            .tab {
                padding: 6px var(--space-3);
                background: transparent;
                border: none;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                font-family: inherit;
                white-space: nowrap;
            }
            .tab-wrap[active] .tab { color: var(--accent); }
            .tab-close {
                width: 24px;
                display: flex; align-items: center; justify-content: center;
                background: transparent;
                border: none;
                color: var(--text-tertiary);
                cursor: pointer;
                font-size: 16px;
                line-height: 1;
                font-family: inherit;
                flex-shrink: 0;
            }
            .tab-close:hover { color: var(--error); }
            .add-branch-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 6px var(--space-3);
                border-radius: var(--radius-full);
                border: 1.5px dashed var(--border-default);
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-sm);
                font-family: inherit;
                cursor: pointer;
                transition: all var(--duration-fast);
                margin-left: var(--space-2);
                flex-shrink: 0;
                white-space: nowrap;
            }
            .add-branch-btn:hover { color: var(--accent); border-color: var(--accent); background: var(--accent-subtle); }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.activeBranchId = 'base';
        this._flows = this.useResource('flows/flows');
        this._branchRemove = this.useOp('flows/branch_remove');
    }

    _selectBranch(branchId) {
        if (branchId === 'base') {
            this.navigate('flow_editor', { flowId: this.flowId });
        } else {
            this.navigate('flow_editor_branch', { flowId: this.flowId, branchId });
        }
    }

    _create() {
        this.openModal('flows.branch_create', { flowId: this.flowId });
    }

    async _deleteBranch(e, branchId) {
        e.stopPropagation();
        if (!this.flowId || branchId === 'base') return;
        await this._branchRemove.run({ flow_id: this.flowId, branch_id: branchId });
        if (this.activeBranchId === branchId) {
            this.navigate('flow_editor', { flowId: this.flowId });
        }
    }

    render() {
        const flow = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
        const branchIds = flow && flow.branches ? Object.keys(flow.branches) : [];
        return html`
            <div class="tabs-row">
                <div class="tab-wrap" ?active=${this.activeBranchId === 'base'}>
                    <button class="tab" type="button" @click=${() => this._selectBranch('base')}>
                        ${this.t('branches_tabs.base')}
                    </button>
                </div>
                ${branchIds.map((bid) => html`
                    <div class="tab-wrap" ?active=${this.activeBranchId === bid}>
                        <button class="tab" type="button" @click=${() => this._selectBranch(bid)}>
                            ${flow.branches[bid] && flow.branches[bid].name ? flow.branches[bid].name : bid}
                        </button>
                        <button
                            class="tab-close"
                            type="button"
                            title=${this.t('branches_tabs.delete')}
                            @click=${(e) => this._deleteBranch(e, bid)}
                        >×</button>
                    </div>
                `)}
                <button class="add-branch-btn" type="button" @click=${this._create}>
                    <platform-icon name="plus" size="14"></platform-icon>
                    ${this.t('branches_tabs.add')}
                </button>
            </div>
        `;
    }
}

customElements.define('flows-branches-tabs', FlowsBranchesTabs);

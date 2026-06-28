/**
 * flows-variables-modal — flow variables + embedded company variables panel.
 *
 * Flow variables — editor draft (VariableEntry).
 * Company variables — shared platform-company-variables-panel (secrets API).
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/variables/platform-company-variables-panel.js';
import './flows-variable-editor-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';

const SCOPE_COMPANY = 'company';
const SCOPE_FLOW = 'flow';

function _normalizeFlowVar(raw) {
    if (raw === null || raw === undefined) {
        return { value: '', secret: false, public: false, title: null, description: null, order: null };
    }
    if (typeof raw === 'object' && !Array.isArray(raw) && 'value' in raw) {
        return {
            value: raw.value,
            secret: Boolean(raw.secret),
            public: Boolean(raw.public),
            title: typeof raw.title === 'string' ? raw.title : null,
            description: typeof raw.description === 'string' ? raw.description : null,
            order: typeof raw.order === 'number' ? raw.order : null,
        };
    }
    return { value: raw, secret: false, public: false, title: null, description: null, order: null };
}

function _stringifyVarValue(value, secret) {
    if (secret) return '***';
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return value;
    return JSON.stringify(value);
}

export class FlowsVariablesModal extends PlatformModal {
    static modalKind = 'flows.variables';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        scope: { type: String },
        flowId: { type: String },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .flows-vars-section { margin-bottom: var(--space-4); }
            .flows-vars-section:last-child { margin-bottom: 0; }
            .flows-vars-section-title {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin: 0 0 var(--space-2) 0;
            }
            .flows-vars-hint {
                padding: var(--space-2) var(--space-3);
                margin-bottom: var(--space-3);
                background: var(--accent-subtle, var(--info-bg));
                border: 1px dashed var(--accent, var(--info));
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
            }
            :host .modal.lg {
                width: fit-content;
                max-width: min(96vw, 1100px);
                min-width: 0;
            }
            .flows-vars-table {
                width: 100%;
                border-collapse: collapse;
                color: var(--text-secondary);
            }
            .flows-vars-table th,
            .flows-vars-table td {
                padding: var(--space-2);
                text-align: left;
                border-bottom: 1px solid var(--border-subtle);
                vertical-align: middle;
            }
            .flows-vars-table th {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
            }
            .flows-vars-empty { padding: var(--space-4); text-align: center; color: var(--text-tertiary); }
            .flows-vars-badge {
                font-size: var(--text-xs);
                padding: 2px 6px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-tertiary);
            }
            .flows-vars-badge.flow { color: var(--accent); border-color: var(--accent); }
            .flows-header-action-create {
                width: 28px;
                height: 28px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 0;
                border: none;
                border-radius: var(--radius-full, 50%);
                cursor: pointer;
                color: var(--platform-btn-primary-text, #ffffff);
                background: var(--platform-btn-primary-bg, #99a6f9);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.scope = SCOPE_COMPANY;
        this.flowId = '';
        this._editor = this.useOp('flows/editor');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('scope') && this.scope !== SCOPE_COMPANY && this.scope !== SCOPE_FLOW) {
            throw new Error(`flows-variables-modal: invalid scope "${this.scope}"`);
        }
        if (this.scope === SCOPE_FLOW && !this.flowId) {
            throw new Error('flows-variables-modal: flowId required for scope="flow"');
        }
    }

    _flowVariablesEntries() {
        const state = this._editor.state;
        const skills = isPlainObject(state.branchData) ? state.branchData : null;
        const skillVars = skills !== null && isPlainObject(skills.variables) ? skills.variables : {};
        return Object.entries(skillVars).map(([key, raw]) => ({
            key,
            ...(_normalizeFlowVar(raw)),
            scope: SCOPE_FLOW,
        }));
    }

    _createFlow() {
        this.openModal('flows.variable_editor', {
            flowId: this.flowId,
        });
    }

    _editFlow(entry) {
        this.openModal('flows.variable_editor', {
            flowId: this.flowId,
            variableKey: entry.key,
            variableValue: typeof entry.value === 'string' ? entry.value : JSON.stringify(entry.value),
            variableSecret: entry.secret,
            variablePublic: entry.public,
            variableTitle: entry.title ?? '',
            variableDescription: entry.description ?? '',
            variableOrder: entry.order === null || entry.order === undefined ? '' : String(entry.order),
        });
    }

    async _deleteFlow(entry) {
        const ok = await platformConfirm(
            this.t('variables_modal.delete_message', { key: entry.key }),
            {
                title: this.t('variables_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('variables_modal.action_delete'),
                cancelText: this.t('variables_modal.action_cancel'),
            },
        );
        if (!ok) return;
        const state = this._editor.state;
        const skillsData = state.branchData;
        const nextVars = { ...skillsData.variables };
        delete nextVars[entry.key];
        this._editor.updateBranchData({ data: { ...skillsData, variables: nextVars } });
        this._editor.setDirty({ dirty: true });
        this.toast('flows:toast.variable_applied', { type: 'success' });
    }

    _renderFlowRow(entry) {
        return html`
            <tr>
                <td><code>${entry.key}</code></td>
                <td>${entry.secret
                    ? html`<em>${this.t('variables_modal.value_secret')}</em>`
                    : _stringifyVarValue(entry.value, false)}</td>
                <td><span class="flows-vars-badge flow">${this.t('variables_modal.badge_flow')}</span></td>
                <td class="actions">
                    <platform-button @click=${() => this._editFlow(entry)}>
                        <platform-icon name="edit" size="14"></platform-icon>
                    </platform-button>
                    <platform-button danger @click=${() => this._deleteFlow(entry)}>
                        <platform-icon name="trash" size="14"></platform-icon>
                    </platform-button>
                </td>
            </tr>
        `;
    }

    _renderFlowTable(rows) {
        if (rows.length === 0) {
            return html`<div class="flows-vars-empty">${this.t('variables_modal.empty_flow')}</div>`;
        }
        return html`
            <table class="flows-vars-table">
                <thead>
                    <tr>
                        <th>${this.t('variables_modal.col_key')}</th>
                        <th>${this.t('variables_modal.col_value')}</th>
                        <th>${this.t('variables_modal.col_source')}</th>
                        <th>${this.t('variables_modal.col_actions')}</th>
                    </tr>
                </thead>
                <tbody>${rows.map((entry) => this._renderFlowRow(entry))}</tbody>
            </table>
        `;
    }

    renderHeader() {
        return this.scope === SCOPE_FLOW
            ? this.t('variables_modal.title_flow')
            : this.t('variables_modal.title_company');
    }

    renderHeaderActions() {
        if (this.scope !== SCOPE_FLOW) {
            return '';
        }
        const createLabel = this.t('variables_modal.action_create');
        return html`
            <button
                type="button"
                class="flows-header-action-create"
                title=${createLabel}
                aria-label=${createLabel}
                @click=${() => this._createFlow()}
            >
                <platform-icon name="plus" size="16"></platform-icon>
            </button>
        `;
    }

    renderBody() {
        if (this.scope === SCOPE_FLOW) {
            const flowRows = this._flowVariablesEntries();
            return html`
                <div class="flows-vars-hint">${this.t('variables_modal.hint_flow_overrides_company')}</div>
                <section class="flows-vars-section">
                    <h3 class="flows-vars-section-title">${this.t('variables_modal.section_flow')}</h3>
                    ${this._renderFlowTable(flowRows)}
                </section>
                <section class="flows-vars-section">
                    <h3 class="flows-vars-section-title">${this.t('variables_modal.section_company')}</h3>
                    <platform-company-variables-panel compact show-help></platform-company-variables-panel>
                </section>
            `;
        }
        return html`
            <platform-company-variables-panel></platform-company-variables-panel>
        `;
    }
}

customElements.define('flows-variables-modal', FlowsVariablesModal);
registerModalKind(FlowsVariablesModal.modalKind, 'flows-variables-modal');

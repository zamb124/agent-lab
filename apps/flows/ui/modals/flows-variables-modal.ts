/**
 * flows-variables-modal — flow variables + embedded company variables panel.
 *
 * Flow variables — editor draft (VariableEntry).
 * Company variables — shared platform-company-variables-panel (secrets API).
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformConfirm } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/variables/platform-company-variables-panel.js';
import './flows-variable-editor-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-empty-state.js';
import { isPlainObject } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

const SCOPE_COMPANY = 'company';
const SCOPE_FLOW = 'flow';

interface FlowVarEntry {
    key: string;
    value: unknown;
    secret: boolean;
    public: boolean;
    title: string | null;
    description: string | null;
    order: number | null;
    scope: string;
}

function _normalizeFlowVar(raw: unknown): Omit<FlowVarEntry, 'key' | 'scope'> {
    if (raw === null || raw === undefined) {
        return { value: '', secret: false, public: false, title: null, description: null, order: null };
    }
    if (isPlainObject(raw) && 'value' in raw) {
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

function _stringifyVarValue(value: unknown, secret: boolean) {
    if (secret) return '***';
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return value;
    return JSON.stringify(value);
}

export class FlowsVariablesModal extends PlatformModal {
    static modalKind = 'flows.variables';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        scope: { type: String },
        flowId: { type: String },
    }
    declare scope: string;
    declare flowId: string;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
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
                background: var(--accent-subtle);
                border: 1px dashed var(--accent);
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
            .flows-vars-table td.actions {
                white-space: nowrap;
                text-align: right;
            }
            .flows-vars-actions {
                display: inline-flex;
                align-items: center;
                justify-content: flex-end;
                gap: var(--space-1);
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
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;

    constructor() {
        super();
        this.size = 'lg';
        this.scope = SCOPE_COMPANY;
        this.flowId = '';
        this._editor = this.useOp('flows/editor');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('scope') && this.scope !== SCOPE_COMPANY && this.scope !== SCOPE_FLOW) {
            throw new Error(`flows-variables-modal: invalid scope "${this.scope}"`);
        }
        if (this.scope === SCOPE_FLOW && !this.flowId) {
            throw new Error('flows-variables-modal: flowId required for scope="flow"');
        }
    }

    _flowVariablesEntries(): FlowVarEntry[] {
        const state = this._editor.state;
        const branchData = isPlainObject(state.branchData) ? state.branchData : null;
        const variables = branchData === null ? undefined : branchData.variables;
        const skillVars = isPlainObject(variables) ? variables : {};
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

    _editFlow(entry: FlowVarEntry) {
        this.openModal('flows.variable_editor', {
            flowId: this.flowId,
            variableKey: entry.key,
            variableValue: typeof entry.value === 'string' ? entry.value : JSON.stringify(entry.value),
            variableSecret: entry.secret,
            variablePublic: entry.public,
            variableTitle: entry.title === undefined || entry.title === null ? '' : String(entry.title),
            variableDescription: entry.description === undefined || entry.description === null ? '' : String(entry.description),
            variableOrder: entry.order === null || entry.order === undefined ? '' : String(entry.order),
        });
    }

    async _deleteFlow(entry: FlowVarEntry) {
        const ok = await platformConfirm(
            this.t('variables_modal.delete_message', { key: entry.key }),
            {
                title: this.t('variables_modal.delete_title'),
                variant: 'danger',
                confirmVariant: 'danger',
                confirmText: this.t('variables_modal.action_delete'),
                cancelText: this.t('common.action_cancel'),
            },
        );
        if (!ok) return;
        const state = this._editor.state;
        const skillsData = state.branchData;
        if (!isPlainObject(skillsData)) {
            throw new Error('flows-variables-modal: branchData required');
        }
        const nextVars = isPlainObject(skillsData.variables) ? { ...skillsData.variables } : {};
        delete nextVars[entry.key];
        this._editor.updateBranchData({ data: { ...skillsData, variables: nextVars } });
        this._editor.setDirty({ dirty: true });
        this.toast('flows:toast.variable_applied', { type: 'success' });
    }

    _renderFlowRow(entry: FlowVarEntry) {
        return html`
            <tr>
                <td><code>${entry.key}</code></td>
                <td>${entry.secret
                    ? html`<em>${this.t('variables_modal.value_secret')}</em>`
                    : _stringifyVarValue(entry.value, false)}</td>
                <td><span class="flows-vars-badge flow">${this.t('variables_modal.badge_flow')}</span></td>
                <td class="actions">
                    <div class="flows-vars-actions">
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            title=${this.t('variables_modal.action_edit')}
                            aria-label=${this.t('variables_modal.action_edit')}
                            @click=${() => this._editFlow(entry)}
                        >
                            <platform-icon name="edit" size="14"></platform-icon>
                        </platform-button>
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            danger
                            title=${this.t('variables_modal.action_delete')}
                            aria-label=${this.t('variables_modal.action_delete')}
                            @click=${() => this._deleteFlow(entry)}
                        >
                            <platform-icon name="trash" size="14"></platform-icon>
                        </platform-button>
                    </div>
                </td>
            </tr>
        `;
    }

    _renderFlowTable(rows: readonly FlowVarEntry[]) {
        if (rows.length === 0) {
            return html`<platform-empty-state icon="database" title=${this.t('variables_modal.empty_flow')}></platform-empty-state>`;
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

    override renderHeader() {
        return this.scope === SCOPE_FLOW
            ? this.t('variables_modal.title_flow')
            : this.t('variables_modal.title_company');
    }

    override renderHeaderActions() {
        if (this.scope !== SCOPE_FLOW) {
            return '';
        }
        const createLabel = this.t('variables_modal.action_create');
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                title=${createLabel}
                aria-label=${createLabel}
                @click=${() => this._createFlow()}
            >
                <platform-icon name="plus" size="16"></platform-icon>
            </platform-button>
        `;
    }

    override renderBody() {
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

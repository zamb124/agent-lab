/**
 * flows-variable-mapping-modal — создание входящего маппинга переменной.
 *
 * Открывается при перетаскивании output-переменной одной ноды на другую ноду
 * канваса. Пишет `input_mapping[targetParam] = "@state:<sourcePath>"` в целевую
 * ноду. Если между нодами нет пути по рёбрам исполнения — предлагает
 * дополнительно создать ребро A -> B (иначе данные не дойдут в рантайме).
 */

import type { OpController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';
import { asArray, asObject, isPlainObject } from '../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

export class FlowsVariableMappingModal extends PlatformModal {
    static modalKind = 'flows.variable_mapping';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        fromNodeId: { type: String },
        fromNodeName: { type: String },
        targetNodeId: { type: String },
        targetNodeName: { type: String },
        sourcePath: { type: String },
        sourceType: { type: String },
        pathExists: { type: Boolean },
        _targetParam: { state: true },
        _createEdge: { state: true },
        _hydrated: { state: true },
    }
    declare fromNodeId: string;
    declare fromNodeName: string;
    declare targetNodeId: string;
    declare targetNodeName: string;
    declare sourcePath: string;
    declare sourceType: string;
    declare pathExists: boolean;
    declare _targetParam: string;
    declare _createEdge: boolean;
    declare _hydrated: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            .summary {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin: 0 0 var(--space-4);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                flex-wrap: wrap;
            }
            .chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .chip .type {
                color: var(--text-tertiary);
                font-weight: var(--font-medium);
                font-size: var(--text-xs);
            }
            .arrow {
                color: var(--text-tertiary);
                font-weight: var(--font-bold);
            }
            .field-group {
                margin-bottom: var(--space-4);
            }
            .suggestions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                margin-top: var(--space-2);
            }
            .suggestion {
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-xs);
                cursor: pointer;
            }
            .suggestion:hover {
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }
            .edge-note {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--warning-bg);
                border: 1px solid var(--warning-border);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                margin-bottom: var(--space-4);
            }
            .edge-note platform-icon {
                color: var(--warning);
                flex-shrink: 0;
            }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;

    constructor() {
        super();
        this.size = 'md';
        this.fromNodeId = '';
        this.fromNodeName = '';
        this.targetNodeId = '';
        this.targetNodeName = '';
        this.sourcePath = '';
        this.sourceType = 'any';
        this.pathExists = true;
        this._targetParam = '';
        this._createEdge = true;
        this._hydrated = false;
        this._editor = this.useOp('flows/editor');
    }

    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        if (changed.has('sourcePath') || changed.has('targetNodeId') || (changed.has('open') && this.open)) {
            this._hydrated = false;
        }
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (!this._hydrated && this.open && this.sourcePath) {
            this._targetParam = this._defaultTargetParam();
            this._createEdge = !this.pathExists;
            this._hydrated = true;
        }
    }

    _defaultTargetParam() {
        const path = typeof this.sourcePath === 'string' ? this.sourcePath : '';
        const parts = path.split('.');
        const leaf = parts[parts.length - 1] || path;
        return leaf;
    }

    _targetDataflowNode() {
        const dataflow = this._editor.state.dataflow;
        if (!isPlainObject(dataflow)) return null;
        const nodes = dataflow.nodes;
        if (!isPlainObject(nodes)) return null;
        const info = nodes[this.targetNodeId];
        return isPlainObject(info) ? info : null;
    }

    _paramSuggestions() {
        const info = this._targetDataflowNode();
        const out = [];
        const seen = new Set();
        const requiredInputs = info === null ? null : info.required_inputs;
        const required = Array.isArray(requiredInputs) ? requiredInputs : [];
        for (const req of required) {
            const name = req && typeof req.name === 'string' ? req.name : '';
            if (name && !seen.has(name)) {
                seen.add(name);
                out.push(name);
            }
        }
        return out;
    }

    override renderHeader() {
        return html`${this.t('variable_mapping_modal.title')}`;
    }

    override renderBody() {
        const suggestions = this._paramSuggestions();
        return html`
            <div class="summary">
                <span class="chip">${this.fromNodeName || this.fromNodeId}</span>
                <span class="chip">${this.sourcePath}<span class="type">${this.sourceType}</span></span>
                <span class="arrow" aria-hidden="true">→</span>
                <span class="chip">${this.targetNodeName || this.targetNodeId}</span>
            </div>
            <div class="field-group">
                <platform-field
                    type="string"
                    mode="edit"
                    .label=${this.t('variable_mapping_modal.field_param')}
                    .value=${this._targetParam}
                    @change=${(e: CustomEvent) => {
                        this._targetParam = typeof e.detail.value === 'string' ? e.detail.value : '';
                    }}
                ></platform-field>
                ${suggestions.length > 0
                    ? html`
                        <div class="suggestions">
                            ${suggestions.map((name) => html`
                                <article
                                    class="suggestion"
                                    role="button"
                                    tabindex="0"
                                    @click=${() => { this._targetParam = name; }}
                                    @keydown=${(e: Event) => {
                                        if (!(e instanceof KeyboardEvent)) return;
                                        if (e.key === 'Enter' || e.key === ' ') {
                                            e.preventDefault();
                                            this._targetParam = name;
                                        }
                                    }}
                                >${name}</article>
                            `)}
                        </div>
                    `
                    : nothing}
            </div>
            ${!this.pathExists
                ? html`
                    <div class="edge-note">
                        <platform-icon name="alert-triangle" size="16"></platform-icon>
                        <span>${this.t('variable_mapping_modal.no_path_note', { from: this.fromNodeName || this.fromNodeId, to: this.targetNodeName || this.targetNodeId })}</span>
                    </div>
                    <div class="field-group">
                        <platform-field
                            type="boolean"
                            mode="edit"
                            .label=${this.t('variable_mapping_modal.field_create_edge')}
                            .value=${this._createEdge}
                            @change=${(e: CustomEvent) => {
                                this._createEdge = Boolean(e.detail.value);
                            }}
                        ></platform-field>
                    </div>
                `
                : nothing}
        `;
    }

    override renderFooter() {
        const valid = (this._targetParam.trim() as any).length > 0 && this.targetNodeId && this.sourcePath;
        return html`
            <platform-button @click=${() => this.close()}>${this.t('common.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!valid} @click=${this._confirm}>
                ${this.t('variable_mapping_modal.action_map')}
            </platform-button>
        `;
    }

    _confirm() {
        const data = this._editor.state?.branchData;
        const param = (this._targetParam.trim() as any);
        if (!data || !this.targetNodeId || !param || !this.sourcePath) {
            this.close();
            return;
        }
        const nodes = { ...asObject(data.nodes) };
        const target = nodes[this.targetNodeId];
        if (!isPlainObject(target)) {
            this.close();
            return;
        }
        const existingMapping = asObject(target.input_mapping);
        const inputMapping = { ...existingMapping, [param]: `@state:${this.sourcePath}` };
        nodes[this.targetNodeId] = { ...target, input_mapping: inputMapping };
        let edges = asArray(data.edges);
        if (!this.pathExists && this._createEdge) {
            const exists = edges.some(
                (edge) => isPlainObject(edge) && edge.from_node === this.fromNodeId && edge.to_node === this.targetNodeId,
            );
            if (!exists) {
                edges = [...edges, { from_node: this.fromNodeId, to_node: this.targetNodeId }];
            }
        }
        const next = { ...data, nodes, edges };
        (this._editor.updateBranchData({ data: next }) as any);
        (this._editor.pushHistory({ snapshot: next }) as any);
        (this._editor.setDirty({ dirty: true }) as any);
        (this._editor.selectNode({ nodeId: this.targetNodeId }) as any);
        this.close();
    }
}

customElements.define('flows-variable-mapping-modal', FlowsVariableMappingModal);
registerModalKind(FlowsVariableMappingModal.modalKind, 'flows-variable-mapping-modal');

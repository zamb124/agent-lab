/**
 * flows-edge-condition-modal — редактирование условия рёбер.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

export class FlowsEdgeConditionModal extends PlatformFormModal {
    static modalKind = 'flows.edge_condition';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        edgeIndex: { type: Number },
        _condition: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            textarea {
                padding: var(--space-2);
                min-height: 96px; resize: vertical;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
        `,
    ];

    constructor() {
        super();
        this.edgeIndex = -1;
        this._condition = '';
        this._hydrated = false;
        this._editor = this.useOp('flows/editor');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.edgeIndex >= 0) {
            const edges = this._editor.state?.skillsData?.edges || [];
            const edge = edges[this.edgeIndex];
            if (edge) {
                this._condition = edge.condition || '';
                this._hydrated = true;
            }
        }
    }

    renderHeader() { return html`<h3>${this.t('edge_condition_modal.title')}</h3>`; }

    renderBody() {
        return html`
            <div class="field">
                <label>${this.t('edge_condition_modal.field_condition')}</label>
                <textarea
                    .value=${this._condition}
                    @input=${(e) => { this._condition = e.target.value; this.isDirty = true; }}
                ></textarea>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('edge_condition_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._save}>${this.t('edge_condition_modal.action_save')}</platform-button>
        `;
    }

    _save() {
        const data = this._editor.state?.skillsData;
        if (!data || this.edgeIndex < 0) return;
        const edges = [...(data.edges || [])];
        edges[this.edgeIndex] = { ...edges[this.edgeIndex], condition: this._condition };
        this._editor.updateSkillsData({ data: { ...data, edges } });
        this._editor.setDirty({ dirty: true });
        this.closeAfterSave();
    }
}

customElements.define('flows-edge-condition-modal', FlowsEdgeConditionModal);
registerModalKind(FlowsEdgeConditionModal.modalKind, 'flows-edge-condition-modal');

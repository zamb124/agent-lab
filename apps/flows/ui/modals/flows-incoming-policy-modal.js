/**
 * flows-incoming-policy-modal — incoming policy ноды (any/all/N).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

const POLICIES = ['any', 'all'];

export class FlowsIncomingPolicyModal extends PlatformFormModal {
    static modalKind = 'flows.incoming_policy';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        nodeId: { type: String },
        _policy: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            select {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
        `,
    ];

    constructor() {
        super();
        this.nodeId = '';
        this._policy = 'any';
        this._hydrated = false;
        this._editor = this.useOp('flows/editor');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.nodeId) {
            const node = this._editor.state?.skillsData?.nodes?.[this.nodeId];
            if (node) {
                this._policy = node.incoming_policy || 'any';
                this._hydrated = true;
            }
        }
    }

    renderHeader() { return html`<h3>${this.t('incoming_policy_modal.title')}</h3>`; }

    renderBody() {
        return html`
            <div class="field">
                <label>${this.t('incoming_policy_modal.field_policy')}</label>
                <select
                    .value=${this._policy}
                    @change=${(e) => { this._policy = e.target.value; this.isDirty = true; }}
                >
                    ${POLICIES.map((p) => html`<option value=${p}>${p}</option>`)}
                </select>
            </div>
        `;
    }

    renderFooter() {
        return html`
            <platform-button @click=${() => this.close()}>${this.t('incoming_policy_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" @click=${this._save}>${this.t('incoming_policy_modal.action_save')}</platform-button>
        `;
    }

    _save() {
        const data = this._editor.state?.skillsData;
        if (!data || !this.nodeId) return;
        const nodes = { ...(data.nodes || {}) };
        const node = nodes[this.nodeId];
        if (!node) return;
        nodes[this.nodeId] = { ...node, incoming_policy: this._policy };
        this._editor.updateSkillsData({ data: { ...data, nodes } });
        this._editor.setDirty({ dirty: true });
        this.closeAfterSave();
    }
}

customElements.define('flows-incoming-policy-modal', FlowsIncomingPolicyModal);
registerModalKind(FlowsIncomingPolicyModal.modalKind, 'flows-incoming-policy-modal');

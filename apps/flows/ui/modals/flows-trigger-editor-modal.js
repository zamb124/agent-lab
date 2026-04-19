/**
 * flows-trigger-editor-modal — создание/редактирование триггера flow.
 *
 * Использует useOp('flows/trigger_create') / useOp('flows/trigger_update').
 * После сохранения — `dispatch('flows/triggers/list_requested')` для перезагрузки.
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';

const TRIGGER_ID_PATTERN = /^[a-z][a-z0-9_]*$/;
const TRIGGER_TYPES = Object.freeze(['telegram', 'webhook']);

export class FlowsTriggerEditorModal extends PlatformFormModal {
    static modalKind = 'flows.trigger_editor';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformFormModal.properties,
        flowId: { type: String },
        trigger: { type: Object },
        _triggerId: { state: true },
        _name: { state: true },
        _type: { state: true },
        _enabled: { state: true },
        _configJson: { state: true },
        _inputMappingJson: { state: true },
        _hydrated: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            .field input, .field select, .field textarea {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font: inherit;
            }
            .field textarea { min-height: 96px; resize: vertical; font-family: var(--font-mono); font-size: var(--text-xs); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .checkbox-row { display: flex; align-items: center; gap: var(--space-2); margin-bottom: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.trigger = null;
        this._triggerId = '';
        this._name = '';
        this._type = 'telegram';
        this._enabled = true;
        this._configJson = '{}';
        this._inputMappingJson = '{}';
        this._hydrated = false;
        this._create = this.useOp('flows/trigger_create');
        this._update = this.useOp('flows/trigger_update');
        this._list = this.useOp('flows/triggers_list');
    }

    updated(changed) {
        super.updated?.(changed);
        if (!this._hydrated && this.trigger) {
            const t = this.trigger;
            this._triggerId = t.trigger_id || '';
            this._name = t.name || '';
            this._type = t.type || 'telegram';
            this._enabled = Boolean(t.enabled);
            this._configJson = JSON.stringify(t.config || {}, null, 2);
            this._inputMappingJson = JSON.stringify(t.input_mapping || {}, null, 2);
            this._hydrated = true;
        }
    }

    renderHeader() {
        return html`<h3>${this.t(this.trigger ? 'trigger_editor_modal.title_edit' : 'trigger_editor_modal.title_create')}</h3>`;
    }

    renderBody() {
        const editing = Boolean(this.trigger);
        return html`
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_id')}</label>
                <input
                    type="text"
                    .value=${this._triggerId}
                    ?disabled=${editing}
                    @input=${(e) => { this._triggerId = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_name')}</label>
                <input
                    type="text"
                    .value=${this._name}
                    @input=${(e) => { this._name = e.target.value; this.isDirty = true; }}
                />
            </div>
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_type')}</label>
                <select
                    .value=${this._type}
                    ?disabled=${editing}
                    @change=${(e) => { this._type = e.target.value; this.isDirty = true; }}
                >
                    ${TRIGGER_TYPES.map((t) => html`<option value=${t}>${t}</option>`)}
                </select>
            </div>
            <div class="checkbox-row">
                <input
                    type="checkbox"
                    id="flows-trigger-enabled"
                    .checked=${this._enabled}
                    @change=${(e) => { this._enabled = e.target.checked; this.isDirty = true; }}
                />
                <label for="flows-trigger-enabled">${this.t('trigger_editor_modal.field_enabled')}</label>
            </div>
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_config_json')}</label>
                <textarea
                    .value=${this._configJson}
                    @input=${(e) => { this._configJson = e.target.value; this.isDirty = true; }}
                ></textarea>
            </div>
            <div class="field">
                <label>${this.t('trigger_editor_modal.field_input_mapping_json')}</label>
                <textarea
                    .value=${this._inputMappingJson}
                    @input=${(e) => { this._inputMappingJson = e.target.value; this.isDirty = true; }}
                ></textarea>
            </div>
        `;
    }

    renderFooter() {
        const validId = TRIGGER_ID_PATTERN.test(this._triggerId);
        const validName = this._name.trim().length > 0;
        return html`
            <platform-button @click=${() => this.close()}>${this.t('trigger_editor_modal.action_cancel')}</platform-button>
            <platform-button variant="primary" ?disabled=${!(validId && validName)} @click=${this._onSubmit}>
                ${this.t('trigger_editor_modal.action_save')}
            </platform-button>
        `;
    }

    async _onSubmit() {
        if (!this.flowId) return;
        const config = JSON.parse(this._configJson);
        const inputMapping = JSON.parse(this._inputMappingJson);
        if (this.trigger) {
            await this._update.run({
                flow_id: this.flowId,
                trigger_id: this._triggerId,
                body: {
                    name: this._name.trim(),
                    enabled: this._enabled,
                    config,
                    input_mapping: inputMapping,
                },
            });
        } else {
            await this._create.run({
                flow_id: this.flowId,
                body: {
                    trigger_id: this._triggerId.trim(),
                    name: this._name.trim(),
                    type: this._type,
                    enabled: this._enabled,
                    config,
                    input_mapping: inputMapping,
                },
            });
        }
        await this._list.run({ flow_id: this.flowId });
        this.closeAfterSave();
    }
}

customElements.define('flows-trigger-editor-modal', FlowsTriggerEditorModal);
registerModalKind(FlowsTriggerEditorModal.modalKind, 'flows-trigger-editor-modal');

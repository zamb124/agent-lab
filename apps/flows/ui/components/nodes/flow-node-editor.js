/**
 * FlowNodeEditor - нода type: flow (вложенный flow / subflow)
 */
import { html } from 'lit';
import { BaseNodeEditor } from './base-node-editor.js';

export class FlowNodeEditor extends BaseNodeEditor {
    constructor() {
        super();
        this._nodeType = 'flow';
    }

    renderFields() {
        const config = this.nodeConfig;
        const showCommonFields = !this.expanded;
        
        return html`
            ${showCommonFields ? html`
                ${this.renderNodeIdField()}
                
                <div class="form-group">
                    <div class="form-label">
                        <span class="form-label-text">${this.i18n.t('node_modal.common.field_name')}</span>
                    </div>
                    <input 
                        type="text" 
                        class="form-input"
                        .value=${config.name || ''}
                        @change=${(e) => this._onInputChange('name', e.target.value)}
                    />
                </div>
            ` : ''}
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">${this.i18n.t('node_modal.flow.editor_flow_id')}</span>
                </div>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${config.flow_id || ''}
                    @change=${(e) => this._onInputChange('flow_id', e.target.value)}
                    placeholder="nested_flow"
                />
            </div>
            
            <div class="form-group">
                <div class="form-label">
                    <span class="form-label-text">${this.i18n.t('node_modal.remote_flow.skill_id_label')}</span>
                </div>
                <input 
                    type="text" 
                    class="form-input"
                    .value=${config.skill_id || 'default'}
                    @change=${(e) => this._onInputChange('skill_id', e.target.value)}
                />
            </div>
            
            ${this.renderMappingSection()}
            
            ${this._renderTestPanel()}
        `;
    }
}

customElements.define('flow-node-editor', FlowNodeEditor);



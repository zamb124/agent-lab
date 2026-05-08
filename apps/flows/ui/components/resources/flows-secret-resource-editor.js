/**
 * flows-secret-resource-editor — ресурс secret.
 *
 * Поля точно по `SecretResourceConfig`:
 *   - key (str): @var:KEY ссылка
 *
 * Поля `value` в модели нет — секреты хранятся через core/variables.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-resource-editor.js';

export class FlowsSecretResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); padding: 0 var(--space-3); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .hint { font-size: var(--text-xs); color: var(--text-tertiary); }
            input {
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
        this.resourceId = '';
        this.resource = null;
        this.compactHeader = false;
    }

    _emitConfig(patch) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    _onKey(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-secret-resource-editor: key change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-secret-resource-editor: key detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-secret-resource-editor: key string required');
        }
        this._emitConfig({ key: v });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const key = typeof cfg.key === 'string' ? cfg.key : '';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'secret'}
                .compactHeader=${this.compactHeader}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <div class="field">
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('secret_resource_editor.key')}
                            .placeholder=${'MY_SECRET_KEY'}
                            .value=${key}
                            @change=${this._onKey}
                        ></platform-field>
                        <div class="hint">${this.t('secret_resource_editor.hint')}</div>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-secret-resource-editor', FlowsSecretResourceEditor);

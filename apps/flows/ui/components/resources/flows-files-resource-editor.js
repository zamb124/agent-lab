/**
 * flows-files-resource-editor — ресурс files (whitelist file patterns).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';

export class FlowsFilesResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
    };

    static styles = [
        css`
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); padding: 0 var(--space-3); }
            .field textarea {
                padding: var(--space-2); min-height: 96px; resize: vertical;
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
            }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
    }

    _emitConfig(config) {
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...(this.resource?.config || {}), ...config } } });
    }

    render() {
        const cfg = this.resource?.config || {};
        const patterns = Array.isArray(cfg.allowed_patterns) ? cfg.allowed_patterns.join('\n') : '';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'files'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings">
                    <div class="field">
                        <label>${this.t('files_resource_editor.field_patterns')}</label>
                        <textarea
                            placeholder="*.md\n*.txt"
                            .value=${patterns}
                            @input=${(e) => this._emitConfig({
                                allowed_patterns: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean),
                            })}
                        ></textarea>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-files-resource-editor', FlowsFilesResourceEditor);

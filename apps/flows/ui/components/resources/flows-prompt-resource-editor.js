/**
 * flows-prompt-resource-editor — ресурс prompt (Jinja-шаблон).
 *
 * Поля точно по `PromptResourceConfig`:
 *   - template (str, Jinja2)
 *   - variables (dict<str, Any>)
 *
 * Кнопка Render preview → useOp('flows/prompt_render').
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-resource-editor.js';
import '../editors/flows-json-field-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsPromptResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .body { padding: 0 var(--space-3); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-3); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .preview {
                padding: var(--space-2);
                background: var(--glass-solid-medium);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                white-space: pre-wrap;
                font-size: var(--text-sm);
                color: var(--text-primary);
            }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.compactHeader = false;
        this._render = this.useOp('flows/prompt_render');
    }

    _emitConfig(patch) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    async _onRenderPreview(template, variables) {
        await this._render.run({ template, variables });
    }

    _onTemplate(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-prompt-resource-editor: template change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-prompt-resource-editor: template detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-prompt-resource-editor: template string required');
        }
        this._emitConfig({ template: v });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const template = typeof cfg.template === 'string' ? cfg.template : '';
        const variables = cfg.variables && typeof cfg.variables === 'object' ? cfg.variables : {};
        const variablesJson = JSON.stringify(variables, null, 2);
        const preview = this._render.lastResult?.rendered;
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'prompt'}
                .compactHeader=${this.compactHeader}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <platform-field
                        mode="edit"
                        type="text"
                        .label=${this.t('prompt_resource_editor.template')}
                        .value=${template}
                        @change=${this._onTemplate}
                    ></platform-field>
                    <div class="field">
                        <label>${this.t('prompt_resource_editor.variables')}</label>
                        <flows-json-field-editor
                            .value=${variablesJson}
                            @change=${(e) => { if (e.detail && 'parsed' in e.detail) this._emitConfig({ variables: e.detail.parsed && typeof e.detail.parsed === 'object' ? e.detail.parsed : {} }); }}
                        ></flows-json-field-editor>
                    </div>
                    <glass-button size="sm" variant="secondary"
                        ?disabled=${this._render.busy}
                        @click=${() => this._onRenderPreview(template, variables)}>
                        <platform-icon name="play"></platform-icon>
                        ${this.t('prompt_resource_editor.render_button')}
                    </glass-button>
                    ${preview ? html`
                        <div class="field" style="margin-top: var(--space-2)">
                            <label>${this.t('prompt_resource_editor.render_preview')}</label>
                            <div class="preview">${preview}</div>
                        </div>
                    ` : ''}
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-prompt-resource-editor', FlowsPromptResourceEditor);

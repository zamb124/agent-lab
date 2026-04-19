/**
 * flows-code-resource-editor — ресурс code.
 *
 * Поля точно по `CodeResourceConfig`:
 *   - language (CodeLanguage: python | javascript)
 *   - code (str)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-code-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';

const LANGUAGES = Object.freeze(['python', 'javascript']);

export class FlowsCodeResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .body { padding: 0 var(--space-3); }
            .field { display: flex; flex-direction: column; gap: var(--space-1); margin-bottom: var(--space-2); }
            label { font-size: var(--text-sm); color: var(--text-secondary); }
            .row { display: flex; align-items: center; gap: var(--space-2); }
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
        this.resourceId = '';
        this.resource = null;
    }

    _emitConfig(patch) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    _openDocs(language) {
        this.openModal('flows.code_docs', { language });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const language = LANGUAGES.includes(cfg.language) ? cfg.language : 'python';
        const code = typeof cfg.code === 'string' ? cfg.code : '';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'code'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <div class="row">
                        <div class="field" style="flex:1">
                            <label>${this.t('code_resource_editor.language')}</label>
                            <select .value=${language}
                                @change=${(e) => this._emitConfig({ language: e.target.value })}>
                                ${LANGUAGES.map((l) => html`<option value=${l} ?selected=${l === language}>${l}</option>`)}
                            </select>
                        </div>
                        <glass-button size="sm" variant="ghost" @click=${() => this._openDocs(language)}>
                            <platform-icon name="info"></platform-icon>
                            ${this.t('code_resource_editor.docs')}
                        </glass-button>
                    </div>
                    <div class="field">
                        <label>${this.t('code_resource_editor.code')}</label>
                        <flows-code-editor
                            language=${language}
                            .value=${code}
                            @change=${(e) => this._emitConfig({ code: e.detail?.value || '' })}
                        ></flows-code-editor>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-code-resource-editor', FlowsCodeResourceEditor);

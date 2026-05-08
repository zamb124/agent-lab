/**
 * flows-code-resource-editor — ресурс code.
 *
 * Поля точно по `CodeResourceConfig`:
 *   - language (CodeLanguage: python | javascript)
 *   - code (str)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-resource-editor.js';
import '../editors/flows-code-editor.js';
import '@platform/lib/components/glass-button.js';
import '@platform/lib/components/platform-icon.js';
import { asString } from '../../_helpers/flows-resolvers.js';

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
            .row platform-field { flex: 1; min-width: 0; }
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

    _onLanguageChange(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-code-resource-editor: language change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-code-resource-editor: language detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-code-resource-editor: language string required');
        }
        if (!LANGUAGES.includes(v)) {
            throw new Error('flows-code-resource-editor: language unknown');
        }
        this._emitConfig({ language: v });
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const language = LANGUAGES.includes(cfg.language) ? cfg.language : 'python';
        const code = typeof cfg.code === 'string' ? cfg.code : '';
        const langValues = LANGUAGES.map((l) => ({ value: l, label: l }));
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'code'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <div class="row">
                        <platform-field
                            mode="edit"
                            type="enum"
                            .label=${this.t('code_resource_editor.language')}
                            .value=${language}
                            .config=${{ values: langValues }}
                            @change=${this._onLanguageChange}
                        ></platform-field>
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
                            @change=${(e) => this._emitConfig({ code: asString(e.detail?.value) })}
                        ></flows-code-editor>
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-code-resource-editor', FlowsCodeResourceEditor);

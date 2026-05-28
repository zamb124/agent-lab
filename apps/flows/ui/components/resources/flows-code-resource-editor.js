/**
 * flows-code-resource-editor — ресурс code.
 *
 * Поля точно по `CodeResourceConfig`:
 *   - language (CodeLanguage: python | javascript | typescript | go | csharp)
 *   - code (str)
 *
 * UI — `flows-code-workbench` в режиме resource (та же оболочка, что у code-ноды).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';
import '../editors/flows-code-workbench.js';
import { asString } from '../../_helpers/flows-resolvers.js';
import { normalizeFlowCodeLanguage } from '../../_helpers/flows-code-languages.js';

export class FlowsCodeResourceEditor extends PlatformElement {
    static properties = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            .body {
                padding: 0 var(--space-3);
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

    _onWorkbenchChange(e) {
        const d = e.detail;
        if (!d || typeof d !== 'object' || !('type' in d)) {
            throw new Error('flows-code-resource-editor: code-workbench-change detail');
        }
        if (d.type === 'code') {
            this._emitConfig({ code: asString(d.value) });
            return;
        }
        if (d.type === 'language') {
            if (typeof d.language !== 'string' || d.language.length === 0) {
                throw new Error('flows-code-resource-editor: language required');
            }
            const patch = { language: normalizeFlowCodeLanguage(d.language) };
            if (typeof d.code === 'string') {
                patch.code = d.code;
            }
            this._emitConfig(patch);
            return;
        }
        if (d.type === 'parameters_schema') {
            throw new Error('flows-code-resource-editor: parameters_schema not supported for code resource');
        }
        throw new Error('flows-code-resource-editor: unknown code-workbench-change type');
    }

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const language = normalizeFlowCodeLanguage(cfg.language);
        const code = typeof cfg.code === 'string' ? cfg.code : '';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'code'}
                .compactHeader=${this.compactHeader}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <flows-code-workbench
                        variant="resource"
                        .scopeKey=${this.resourceId}
                        documentation-perspective="editor"
                        .code=${code}
                        .language=${language}
                        @code-workbench-change=${this._onWorkbenchChange}
                    ></flows-code-workbench>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-code-resource-editor', FlowsCodeResourceEditor);

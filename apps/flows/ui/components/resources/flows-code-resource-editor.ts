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
import { asString, isPlainObject } from '../../_helpers/flows-resolvers.js';
import { normalizeFlowCodeLanguage } from '../../_helpers/flows-code-languages.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsCodeResourceEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    }
    declare resourceId: string;
    declare resource: Record<string, any> | null;
    declare compactHeader: boolean;
;

    static override styles: CSSResultGroup = [
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

    _emitConfig(patch: any) {
        const base = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        this.emit('change', { resourceId: this.resourceId, patch: { config: { ...base, ...patch } } });
    }

    _onWorkbenchChange(e: CustomEvent) {
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
            const patch: any = { language: normalizeFlowCodeLanguage(d.language) };
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

    override render(): TemplateResult {
        const config: Record<string, unknown> = this.resource && isPlainObject(this.resource.config)
            ? this.resource.config
            : {};
        const language = normalizeFlowCodeLanguage(config.language);
        const codeValue = config.code;
        const code = typeof codeValue === 'string' ? codeValue : '';
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'code'}
                .compactHeader=${this.compactHeader}
                @change=${(e: CustomEvent) => this.emit('change', e.detail)}
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

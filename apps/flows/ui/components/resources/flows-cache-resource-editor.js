/**
 * flows-cache-resource-editor — ресурс cache.
 *
 * Поля точно по `CacheResourceConfig`:
 *   - namespace (str, required)
 *   - ttl (int, default 3600 сек)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-base-resource-editor.js';

export class FlowsCacheResourceEditor extends PlatformElement {
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
            input {
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-primary); font: inherit;
                width: 100%; box-sizing: border-box;
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

    render() {
        const cfg = this.resource && typeof this.resource.config === 'object' ? this.resource.config : {};
        const namespace = typeof cfg.namespace === 'string' ? cfg.namespace : '';
        const ttl = typeof cfg.ttl === 'number' ? cfg.ttl : 3600;
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'cache'}
                @change=${(e) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <div class="field">
                        <label>${this.t('cache_resource_editor.namespace')}</label>
                        <input type="text" .value=${namespace}
                            @input=${(e) => this._emitConfig({ namespace: e.target.value })} />
                    </div>
                    <div class="field">
                        <label>${this.t('cache_resource_editor.ttl')}</label>
                        <input type="number" min="0" step="1" .value=${String(ttl)}
                            @input=${(e) => {
                                const v = parseInt(e.target.value, 10);
                                this._emitConfig({ ttl: Number.isFinite(v) && v >= 0 ? v : 0 });
                            }} />
                    </div>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-cache-resource-editor', FlowsCacheResourceEditor);

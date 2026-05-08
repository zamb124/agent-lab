/**
 * flows-cache-resource-editor — ресурс cache.
 *
 * Поля точно по `CacheResourceConfig`:
 *   - namespace (str, required)
 *   - ttl (int, default 3600 сек)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
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

    _emitConfigFromNamespace(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-cache-resource-editor: namespace change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-cache-resource-editor: namespace detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-cache-resource-editor: namespace string required');
        }
        this._emitConfig({ namespace: v });
    }

    _emitConfigFromTtl(e) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-cache-resource-editor: ttl change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-cache-resource-editor: ttl detail.value');
        }
        const v = d.value;
        if (v === null) {
            this._emitConfig({ ttl: 0 });
            return;
        }
        if (typeof v !== 'number' || !Number.isFinite(v)) {
            throw new Error('flows-cache-resource-editor: ttl number required');
        }
        const rounded = Math.floor(v);
        this._emitConfig({ ttl: rounded >= 0 ? rounded : 0 });
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
                    <platform-field
                        mode="edit"
                        type="string"
                        .label=${this.t('cache_resource_editor.namespace')}
                        .value=${namespace}
                        @change=${this._emitConfigFromNamespace}
                    ></platform-field>
                    <platform-field
                        mode="edit"
                        type="integer"
                        .label=${this.t('cache_resource_editor.ttl')}
                        .value=${ttl}
                        @change=${this._emitConfigFromTtl}
                    ></platform-field>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-cache-resource-editor', FlowsCacheResourceEditor);

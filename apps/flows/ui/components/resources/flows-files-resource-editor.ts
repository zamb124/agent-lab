/**
 * flows-files-resource-editor — ресурс files (S3 хранилище).
 *
 * Поля точно по `FilesResourceConfig`:
 *   - bucket (str, обязательный)
 *   - prefix (str)
 *   - endpoint_url (str)
 *   - access_key_id (str)
 *   - secret_access_key (str, через variable-input)
 *   - region (str, по умолчанию 'us-east-1')
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import './flows-base-resource-editor.js';
import '@platform/lib/components/platform-variable-input.js';
import { isPlainObject } from '../../_helpers/flows-resolvers.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

function configRecord(resource: Record<string, unknown> | null): Record<string, unknown> {
    if (resource === null || !isPlainObject(resource.config)) {
        return {};
    }
    const row: Record<string, unknown> = {};
    for (const [key, field] of Object.entries(resource.config)) {
        row[key] = field;
    }
    return row;
}

function stringField(record: Record<string, unknown>, key: string, fallback: string): string {
    const value = record[key];
    return typeof value === 'string' ? value : fallback;
}

export class FlowsFilesResourceEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        resourceId: { type: String },
        resource: { type: Object },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    }
    declare resourceId: string;
    declare resource: Record<string, unknown> | null;
    declare compactHeader: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            .body {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                padding: var(--space-3) var(--space-3);
                box-sizing: border-box;
            }
            .usage-hint {
                margin: 0;
                font-size: var(--text-sm);
                line-height: 1.45;
                color: var(--text-secondary);
            }
            .field {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .field label {
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            .grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: var(--space-3);
                align-items: start;
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

    _strDetail(e: CustomEvent, ctx: any) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error(`flows-files-resource-editor: ${ctx} change detail`);
        }
        if (!('value' in d)) {
            throw new Error(`flows-files-resource-editor: ${ctx} detail.value`);
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error(`flows-files-resource-editor: ${ctx} string required`);
        }
        return v;
    }

    override render(): TemplateResult {
        const cfg = configRecord(this.resource);
        const bucket = stringField(cfg, 'bucket', '');
        const prefix = stringField(cfg, 'prefix', '');
        const endpoint = stringField(cfg, 'endpoint_url', '');
        const accessKey = stringField(cfg, 'access_key_id', '');
        const secretKey = stringField(cfg, 'secret_access_key', '');
        const region = stringField(cfg, 'region', 'us-east-1');
        return html`
            <flows-base-resource-editor
                .resourceId=${this.resourceId}
                .resource=${this.resource}
                .resourceType=${'files'}
                .compactHeader=${this.compactHeader}
                @change=${(e: CustomEvent) => this.emit('change', e.detail)}
            >
                <div slot="settings" class="body">
                    <p class="usage-hint">${this.t('files_resource_editor.usage_hint')}</p>
                    <div class="grid">
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.bucket')}
                            .value=${bucket}
                            @change=${(e: CustomEvent) => this._emitConfig({ bucket: this._strDetail(e, 'bucket') })}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.prefix')}
                            .value=${prefix}
                            @change=${(e: CustomEvent) => this._emitConfig({ prefix: this._strDetail(e, 'prefix') })}
                        ></platform-field>
                    </div>
                    <platform-field
                        mode="edit"
                        type="string"
                        input-type="url"
                        .label=${this.t('files_resource_editor.endpoint_url')}
                        .placeholder=${'https://s3.amazonaws.com'}
                        .value=${endpoint}
                        @change=${(e: CustomEvent) => {
                            const v = this._strDetail(e, 'endpoint_url');
                            this._emitConfig({ endpoint_url: v.length > 0 ? v : null });
                        }}
                    ></platform-field>
                    <div class="grid">
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.access_key_id')}
                            .value=${accessKey}
                            @change=${(e: CustomEvent) => {
                                const v = this._strDetail(e, 'access_key_id');
                                this._emitConfig({ access_key_id: v.length > 0 ? v : null });
                            }}
                        ></platform-field>
                        <platform-field
                            mode="edit"
                            type="string"
                            .label=${this.t('files_resource_editor.region')}
                            .value=${region}
                            @change=${(e: CustomEvent) => {
                                const v = this._strDetail(e, 'region');
                                this._emitConfig({ region: v.length > 0 ? v : 'us-east-1' });
                            }}
                        ></platform-field>
                    </div>
                    <platform-variable-input
                        .label=${this.t('files_resource_editor.secret_access_key')}
                        .value=${secretKey}
                        @change=${(e: CustomEvent) => { const v = e.detail?.value; this._emitConfig({ secret_access_key: typeof v === 'string' && v.length > 0 ? v : null }); }}
                    ></platform-variable-input>
                </div>
            </flows-base-resource-editor>
        `;
    }
}

customElements.define('flows-files-resource-editor', FlowsFilesResourceEditor);

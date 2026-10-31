/**
 * flows-base-resource-editor — общая обёртка для редакторов ресурсов.
 *
 * Поля точно по `ResourceDefinition` (apps/flows/src/models/resource.py):
 *   - resource_id (только для чтения)
 *   - type (badge)
 *   - name
 *   - description
 *   - tags (platform-field type=array)
 *   - permission (группы; пусто = всем)
 *
 * Slot 'settings' — поля, специфичные для типа (`config: dict`).
 *
 * `compactHeader` — карточка закреплённого ресурса на resource-ноде: без шапки
 * (id / имя / описание / теги); только `slot settings`. Метаданные ресурса — в каталоге
 * или в панели ресурса.
 *
 * Эмитит наружу `change { resourceId, patch }` — patch содержит изменённые
 * top-level поля ресурса (name, description, tags, permission) или config (от слота).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsBaseResourceEditor extends PlatformElement {
    static override properties: PropertyDeclarations = {
        resourceId: { type: String },
        resource: { type: Object },
        resourceType: { type: String },
        compactHeader: { type: Boolean, reflect: true, attribute: 'compact-header' },
    }
    declare resourceId: string;
    declare resource: Record<string, unknown> | null;
    declare resourceType: string;
    declare compactHeader: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; padding: var(--space-3); color: var(--text-primary); }
            :host([compact-header]) {
                padding: 0;
            }
            .header {
                display: flex; flex-direction: column; gap: var(--space-2);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                margin-bottom: var(--space-3);
            }
            .row {
                display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap;
            }
            platform-field.name-field {
                flex: 1;
                min-width: 0;
            }
            .badge {
                padding: 2px 8px; font-size: var(--text-xs);
                border-radius: var(--radius-full);
                background: var(--accent-subtle); color: var(--accent);
                white-space: nowrap;
            }
            .id {
                padding: 2px 8px; font-size: var(--text-xs);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-sm);
                color: var(--text-secondary);
                font-family: var(--font-mono);
            }
            .field { display: flex; flex-direction: column; gap: var(--space-1); }
            .field label { font-size: var(--text-sm); color: var(--text-secondary); }
            .permission-hint {
                font-size: var(--text-xs);
                color: var(--text-secondary);
                margin: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.resourceId = '';
        this.resource = null;
        this.resourceType = '';
        this.compactHeader = false;
    }

    _emitPatch(patch: any) {
        this.emit('change', { resourceId: this.resourceId, patch });
    }

    _onName(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-base-resource-editor: name change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-base-resource-editor: name detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-base-resource-editor: name detail.value string');
        }
        this._emitPatch({ name: v });
    }

    _onDescription(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-base-resource-editor: description change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-base-resource-editor: description detail.value');
        }
        const v = d.value;
        if (typeof v !== 'string') {
            throw new Error('flows-base-resource-editor: description detail.value string');
        }
        this._emitPatch({ description: v });
    }

    _onTags(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-base-resource-editor: tags change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-base-resource-editor: tags detail.value');
        }
        const tags = d.value;
        if (!Array.isArray(tags)) {
            throw new Error('flows-base-resource-editor: tags must be array');
        }
        this._emitPatch({ tags });
    }

    _onPermission(e: CustomEvent) {
        const d = e.detail;
        if (d === null || typeof d !== 'object') {
            throw new Error('flows-base-resource-editor: permission change detail');
        }
        if (!('value' in d)) {
            throw new Error('flows-base-resource-editor: permission detail.value');
        }
        const permission = d.value;
        if (!Array.isArray(permission)) {
            throw new Error('flows-base-resource-editor: permission must be array');
        }
        for (const item of permission) {
            if (typeof item !== 'string') {
                throw new Error('flows-base-resource-editor: permission items must be strings');
            }
        }
        this._emitPatch({ permission });
    }

    override render(): TemplateResult {
        if (!this.resource) return html`<div>${this.t('property_panel.select_resource')}</div>`;
        if (this.compactHeader) {
            return html`<slot name="settings"></slot>`;
        }
        const name = typeof this.resource.name === 'string' ? this.resource.name : this.resourceId;
        const description = typeof this.resource.description === 'string' ? this.resource.description : '';
        const tags = Array.isArray(this.resource.tags) ? this.resource.tags : [];
        const permission = Array.isArray(this.resource.permission) ? this.resource.permission : [];
        let type;
        if (typeof this.resourceType === 'string' && this.resourceType.length > 0) {
            type = this.resourceType;
        } else if (this.resource && typeof this.resource.type === 'string') {
            type = this.resource.type;
        } else {
            type = '';
        }
        return html`
            <div class="header">
                <div class="row">
                    <platform-field
                        class="name-field"
                        mode="edit"
                        type="string"
                        .value=${name}
                        @change=${this._onName}
                    ></platform-field>
                    <span class="badge">${type}</span>
                </div>
                <div class="row">
                    <span class="id">${this.resourceId}</span>
                </div>
                <platform-field
                    mode="edit"
                    type="text"
                    .label=${this.t('base_resource_editor.field_description')}
                    .value=${description}
                    @change=${this._onDescription}
                ></platform-field>
                <platform-field
                    type="array"
                    mode="edit"
                    .label=${this.t('base_resource_editor.tags')}
                    .placeholder=${this.t('tag_input.placeholder')}
                    .value=${tags}
                    .config=${{ preserve_case: true }}
                    @change=${this._onTags}
                ></platform-field>
                <platform-field
                    type="array"
                    mode="edit"
                    .label=${this.t('base_resource_editor.permission')}
                    .placeholder=${this.t('base_resource_editor.permission_placeholder')}
                    .value=${permission}
                    .config=${{ preserve_case: true }}
                    @change=${this._onPermission}
                ></platform-field>
                <p class="permission-hint">${this.t('base_resource_editor.permission_hint')}</p>
            </div>
            <slot name="settings"></slot>
        `;
    }
}

customElements.define('flows-base-resource-editor', FlowsBaseResourceEditor);

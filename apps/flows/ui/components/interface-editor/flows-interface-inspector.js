/**
 * Inspector: schema-driven property form from the catalog manifest,
 * layout/placement, bindings and actions for the selected component.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FLOW_UI_CATALOG_MANIFEST } from '@platform/lib/flow-ui/catalog/manifest.js';
import { FLOW_UI_VALIDATION_INPUT_TYPES } from '@platform/lib/flow-ui/editor/component-quick-props.js';
import { buildFlowAssetFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { buildPlatformFileDownloadUrl } from '@platform/lib/utils/platform-files-url.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/components/platform-icon.js';
import './flows-interface-layout-inspector.js';
import './flows-interface-binding-editor.js';
import './flows-interface-action-editor.js';

export class FlowsInterfaceInspector extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        component: { attribute: false },
        dataModel: { attribute: false },
        pages: { attribute: false },
        band: { type: String },
        rootId: { type: String },
        selectionCount: { type: Number },
        flowId: { type: String },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: block; padding: 14px 16px; overflow: auto; }
        .eyebrow {
            font-size: 10px;
            text-transform: uppercase;
            letter-spacing: .07em;
            color: var(--text-tertiary);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        h3 { font-size: 15px; margin: 4px 0 14px; color: var(--text-primary); }
        .id-input {
            width: 100%;
            box-sizing: border-box;
            height: 26px;
            border: 1px solid transparent;
            border-radius: 6px;
            background: transparent;
            color: var(--text-tertiary);
            font: inherit;
            font-size: 11px;
            padding: 0 4px;
            margin-bottom: 10px;
        }
        .id-input:hover, .id-input:focus {
            border-color: var(--border-subtle);
            background: var(--bg-elevated);
            outline: none;
        }
        .fields { display: grid; gap: 8px; }
        .section {
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: .06em;
            color: var(--text-tertiary);
            margin: 14px 0 6px;
        }
        platform-button.danger-action { display: block; margin-top: 16px; }
        .multi { color: var(--text-tertiary); font-size: 12px; padding: 8px 0; }
        .image-field {
            display: grid;
            gap: 8px;
            padding: 10px;
            border: 1px solid var(--border-subtle);
            border-radius: var(--radius-md);
            background: var(--bg-elevated);
        }
        .image-field .label {
            font-size: 12px;
            font-weight: 650;
            color: var(--text-secondary);
        }
        .image-field .preview {
            display: grid;
            place-items: center;
            min-height: 88px;
            border-radius: var(--radius-sm);
            border: 1px dashed var(--border-subtle);
            overflow: hidden;
            background: color-mix(in srgb, var(--bg-primary) 80%, transparent);
        }
        .image-field .preview img {
            display: block;
            max-width: 100%;
            max-height: 160px;
            object-fit: contain;
        }
        .image-field .preview-empty {
            font-size: 12px;
            color: var(--text-tertiary);
            padding: 12px;
            text-align: center;
        }
        .image-field .actions {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .image-field .file-id-value {
            font: 650 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
            color: var(--text-secondary);
            word-break: break-all;
            padding: 8px;
        }
        .contract {
            display: grid; gap: 6px; padding: 10px;
            border: 1px solid color-mix(in srgb, var(--accent) 40%, var(--border-subtle));
            border-radius: var(--radius-md);
            background: color-mix(in srgb, var(--accent) 8%, transparent);
            margin-bottom: 8px;
        }
        .contract .ref {
            font: 650 12px/1.4 ui-monospace, SFMono-Regular, Menlo, monospace;
            color: var(--accent); word-break: break-all;
        }
        .contract .hint { font-size: 11px; color: var(--text-secondary); line-height: 1.4; }
        .contract[data-scope='submit'] {
            border-color: color-mix(in srgb, var(--success) 50%, var(--border-subtle));
            background: color-mix(in srgb, var(--success) 10%, transparent);
        }
        .contract[data-scope='submit'] .ref { color: var(--success); }
        .contract[data-scope='content'] {
            border-color: color-mix(in srgb, var(--info) 50%, var(--border-subtle));
            background: color-mix(in srgb, var(--info) 10%, transparent);
        }
        .contract[data-scope='content'] .ref { color: var(--info); }
        .contract[data-scope='system'] {
            border-color: color-mix(in srgb, var(--warning) 50%, var(--border-subtle));
            background: color-mix(in srgb, var(--warning) 10%, transparent);
        }
        .contract[data-scope='system'] .ref { color: var(--warning); }
    `];

    constructor() {
        super();
        this.component = null;
        this.dataModel = null;
        this.pages = [];
        this.band = 'wide';
        this.rootId = 'root';
        this.selectionCount = 1;
        this.flowId = '';
    }

    _entry() {
        return this.component ? FLOW_UI_CATALOG_MANIFEST.components[this.component.type] : null;
    }

    _locale() {
        return this.select((state) => state.i18n.locale).value === 'ru' ? 'ru' : 'en';
    }

    _openImagePicker(fieldName, field) {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            throw new Error('flows-interface-inspector: flowId required for image upload');
        }
        if (!field || typeof field !== 'object') {
            throw new Error('flows-interface-inspector: image field required');
        }
        const publicAsset = field.publicAsset === true;
        this.openModal('platform.file_picker', {
            acceptMimePrefix: 'image/',
            uploadOpName: 'platform/file_create',
            uploadSpec: buildFlowAssetFileCreateSpecJson({
                flowId: this.flowId,
                isPublic: publicAsset,
            }),
            catalogsOpName: 'flows/catalogs',
            documentsOpName: 'flows/documents',
            searchOpName: 'flows/documents_search',
            onSelect: (file) => {
                if (!file || typeof file.file_id !== 'string' || file.file_id.length === 0) {
                    throw new Error('flows-interface-inspector: image file_id required');
                }
                if (publicAsset && file.is_public !== true) {
                    throw new Error('flows-interface-inspector: public image requires is_public file');
                }
                this.emit('property-change', {
                    name: fieldName,
                    value: buildPlatformFileDownloadUrl(file.file_id),
                });
            },
        });
    }

    _clearImage(fieldName) {
        this.emit('property-change', { name: fieldName, value: '' });
    }

    _openFileIdPicker(fieldName) {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            throw new Error('flows-interface-inspector: flowId required for file_id picker');
        }
        this.openModal('platform.file_picker', {
            acceptMimePrefix: 'application/vnd.sqlite3',
            uploadOpName: 'platform/file_create',
            uploadSpec: buildFlowAssetFileCreateSpecJson({ flowId: this.flowId }),
            catalogsOpName: 'flows/catalogs',
            documentsOpName: 'flows/documents',
            searchOpName: 'flows/documents_search',
            onSelect: (file) => {
                if (!file || typeof file.file_id !== 'string' || file.file_id.length === 0) {
                    throw new Error('flows-interface-inspector: file_id required');
                }
                this.emit('property-change', {
                    name: fieldName,
                    value: file.file_id,
                });
            },
        });
    }

    _clearFileId(fieldName) {
        this.emit('property-change', { name: fieldName, value: '' });
    }

    _fileIdField(field) {
        const locale = this._locale();
        const label = field.label[locale];
        const raw = this.component?.properties?.[field.name];
        const fileId = typeof raw === 'string' ? raw.trim() : '';
        const hasFileId = fileId.length > 0;
        return html`<div class="image-field">
            <div class="label">${label}</div>
            <div class="preview">
                ${hasFileId
                    ? html`<div class="file-id-value">${fileId}</div>`
                    : html`<div class="preview-empty">${this.t('interface_editor.inspector_file_id_empty')}</div>`}
            </div>
            <div class="actions">
                <platform-button
                    variant="secondary"
                    density="compact"
                    @click=${() => this._openFileIdPicker(field.name)}
                >${this.t(hasFileId ? 'interface_editor.inspector_file_id_replace' : 'interface_editor.inspector_file_id_pick')}</platform-button>
                ${hasFileId ? html`<platform-button
                    variant="ghost"
                    density="compact"
                    @click=${() => this._clearFileId(field.name)}
                >${this.t('interface_editor.inspector_file_id_clear')}</platform-button>` : nothing}
            </div>
        </div>`;
    }

    _imageField(field) {
        const locale = this._locale();
        const label = field.label[locale];
        const raw = this.component?.properties?.[field.name];
        const src = typeof raw === 'string' ? raw.trim() : '';
        const hasSrc = src.length > 0;
        return html`<div class="image-field">
            <div class="label">${label}</div>
            <div class="preview">
                ${hasSrc
                    ? html`<img src=${src} alt="">`
                    : html`<div class="preview-empty">${this.t('interface_editor.inspector_image_empty')}</div>`}
            </div>
            <div class="actions">
                <platform-button
                    variant="secondary"
                    density="compact"
                    @click=${() => this._openImagePicker(field.name, field)}
                >${this.t(hasSrc ? 'interface_editor.inspector_image_replace' : 'interface_editor.inspector_image_pick')}</platform-button>
                ${hasSrc ? html`<platform-button
                    variant="ghost"
                    density="compact"
                    @click=${() => this._clearImage(field.name)}
                >${this.t('interface_editor.inspector_image_clear')}</platform-button>` : nothing}
            </div>
        </div>`;
    }

    _schemaField(field) {
        const locale = this._locale();
        const label = field.label[locale];
        const raw = this.component?.properties?.[field.name];
        const emitChange = (value) => this.emit('property-change', { name: field.name, value });
        if (field.kind === 'image') {
            return this._imageField(field);
        }
        if (field.kind === 'file_id') {
            return this._fileIdField(field);
        }
        if (field.kind === 'boolean') {
            return html`<platform-field
                type="boolean"
                .label=${label}
                .value=${raw === true}
                mode="edit"
                @change=${(event) => emitChange(event.detail.value === true)}
            ></platform-field>`;
        }
        if (field.kind === 'number') {
            return html`<platform-field
                type="number"
                .label=${label}
                .value=${raw == null ? null : Number(raw)}
                mode="edit"
                @change=${(event) => emitChange(Number(event.detail.value))}
            ></platform-field>`;
        }
        if (field.kind === 'enum') {
            const rawOptions = field.options || [];
            const numeric = rawOptions.every((option) => {
                const optionValue = typeof option === 'object' && option !== null
                    ? option.value
                    : option;
                return typeof optionValue === 'number';
            });
            const values = rawOptions.map((option) => {
                if (typeof option !== 'object' || option === null) {
                    return { value: String(option), label: String(option) };
                }
                const optionLabel = option.label;
                const resolved = optionLabel && typeof optionLabel === 'object'
                    ? (optionLabel[locale] || optionLabel.en || String(option.value))
                    : (optionLabel == null ? String(option.value) : String(optionLabel));
                return { value: String(option.value), label: resolved };
            });
            return html`<platform-field
                type="enum"
                .label=${label}
                .value=${raw == null ? '' : String(raw)}
                .config=${{ values }}
                mode="edit"
                @change=${(event) => {
                    const value = event.detail.value;
                    emitChange(numeric ? Number(value) : value);
                }}
            ></platform-field>`;
        }
        return html`<platform-field
            type=${field.kind === 'text' ? 'text' : 'string'}
            .label=${label}
            .value=${raw == null ? '' : String(raw)}
            mode="edit"
            @change=${(event) => emitChange(event.detail.value)}
        ></platform-field>`;
    }

    _valuePointer() {
        const bindings = this.component?.bindings;
        if (!bindings || typeof bindings !== 'object') return null;
        for (const name of ['value', 'values', 'files']) {
            const pointer = bindings[name];
            if (typeof pointer === 'string' && (pointer === '/values' || pointer.startsWith('/values/'))) {
                return pointer;
            }
        }
        return null;
    }

    _stateRef() {
        const pointer = this._valuePointer();
        if (!pointer) return null;
        const override = this.component?.properties?.fieldName;
        if (typeof override === 'string' && override.trim() !== '') {
            return `@state:ui_values.${override.trim()}`;
        }
        if (pointer === '/values') return '@state:ui_values';
        const segment = pointer.slice('/values/'.length).replace(/\//g, '_');
        return segment ? `@state:ui_values.${segment}` : '@state:ui_values';
    }

    _isSubmit() {
        const press = this.component?.actions?.press;
        return Boolean(
            press
            && typeof press === 'object'
            && press.kind === 'event'
            && press.name === 'platform.ui.submit',
        );
    }

    _contentPointers() {
        const bindings = this.component?.bindings;
        if (!bindings || typeof bindings !== 'object') return [];
        return Object.values(bindings).filter((pointer) => (
            typeof pointer === 'string'
            && (pointer === '/content' || pointer.startsWith('/content/')
                || pointer === '/system' || pointer.startsWith('/system/'))
        ));
    }

    _requiredCheck() {
        const checks = Array.isArray(this.component?.checks) ? this.component.checks : [];
        return checks.find((check) => check && check.function === 'required') || null;
    }

    _supportsValidation() {
        return FLOW_UI_VALIDATION_INPUT_TYPES.has(this.component?.type);
    }

    _setRequired(enabled) {
        const checks = Array.isArray(this.component?.checks) ? [...this.component.checks] : [];
        const index = checks.findIndex((check) => check && check.function === 'required');
        if (enabled) {
            if (index >= 0) return;
            checks.push({ function: 'required', message: '' });
        } else if (index >= 0) {
            checks.splice(index, 1);
        } else {
            return;
        }
        this.emit('checks-change', { checks });
    }

    _setRequiredMessage(message) {
        const checks = Array.isArray(this.component?.checks) ? [...this.component.checks] : [];
        const index = checks.findIndex((check) => check && check.function === 'required');
        if (index < 0) {
            checks.push({ function: 'required', message });
        } else {
            checks[index] = { ...checks[index], function: 'required', message };
        }
        this.emit('checks-change', { checks });
    }

    _renderValidation() {
        if (!this._supportsValidation()) return nothing;
        const required = this._requiredCheck();
        return html`
            <div class="section">${this.t('interface_editor.inspector_validation')}</div>
            <div class="fields">
                <platform-field
                    type="boolean"
                    .label=${this.t('interface_editor.inspector_required')}
                    .value=${required != null}
                    mode="edit"
                    @change=${(event) => this._setRequired(event.detail.value === true)}
                ></platform-field>
                ${required != null ? html`<platform-field
                    type="string"
                    .label=${this.t('interface_editor.inspector_required_message')}
                    .value=${typeof required.message === 'string' ? required.message : ''}
                    mode="edit"
                    @change=${(event) => this._setRequiredMessage(String(event.detail.value ?? ''))}
                ></platform-field>` : nothing}
            </div>
        `;
    }

    _renderContractCard() {
        if (this._isSubmit()) {
            return html`<div class="contract" data-scope="submit">
                <div class="ref">platform.ui.submit</div>
                <div class="hint">${this.t('interface_editor.inspector_contract_submit')}</div>
            </div>`;
        }
        const stateRef = this._stateRef();
        if (stateRef) {
            return html`<div class="contract" data-scope="input">
                <div class="ref">${stateRef}</div>
                <div class="hint">${this.t('interface_editor.inspector_contract_input')}</div>
            </div>`;
        }
        const contentPointers = this._contentPointers();
        if (contentPointers.length > 0) {
            const pointer = contentPointers[0];
            const scope = pointer.startsWith('/system') ? 'system' : 'content';
            return html`<div class="contract" data-scope=${scope}>
                <div class="ref">${pointer}</div>
                <div class="hint">${this.t(
                    scope === 'system'
                        ? 'interface_editor.inspector_contract_system'
                        : 'interface_editor.inspector_contract_content',
                )}</div>
            </div>`;
        }
        return nothing;
    }

    render() {
        const component = this.component;
        if (this.selectionCount > 1) {
            return html`<div class="multi">${this.t('interface_editor.inspector_multi', { count: String(this.selectionCount) })}</div>`;
        }
        if (!component) {
            return html`<div class="eyebrow">${this.t('interface_editor.inspector_empty')}</div>`;
        }
        const entry = this._entry();
        const schema = entry?.editor?.schema || [];
        const isRoot = component.component_id === this.rootId;
        return html`
            <div class="eyebrow">
                <platform-icon name=${entry?.editor?.icon || 'box'} size="12"></platform-icon>
                ${component.kind}
            </div>
            <h3>${component.type}</h3>
            ${this._renderContractCard()}
            <input
                class="id-input"
                data-canon="inline-edit"
                .value=${component.component_id}
                title=${this.t('interface_editor.inspector_id_hint')}
                ?readonly=${isRoot}
                @keydown=${(event) => { if (event.key === 'Enter') event.target.blur(); }}
                @blur=${(event) => {
                    const nextId = String(event.target.value).trim();
                    if (nextId && nextId !== component.component_id) {
                        this.emit('component-rename', { componentId: component.component_id, nextId });
                    }
                }}
            >
            ${schema.length ? html`
                <div class="section">${this.t('interface_editor.inspector_content')}</div>
                <div class="fields">${schema.map((field) => this._schemaField(field))}</div>
            ` : nothing}
            ${this._renderValidation()}
            <div class="section">${this.t('interface_editor.inspector_layout')}</div>
            <flows-interface-layout-inspector
                .component=${component}
                .band=${this.band}
                @band-change=${(event) => this.emit('band-change', event.detail)}
                @placement-patch=${(event) => this.emit('placement-patch', event.detail)}
                @placement-reset=${(event) => this.emit('placement-reset', event.detail)}
                @layout-patch=${(event) => this.emit('layout-patch', event.detail)}
            ></flows-interface-layout-inspector>
            <flows-interface-binding-editor
                .bindings=${component.bindings || {}}
                .dataModel=${this.dataModel}
                @binding-change=${(event) => this.emit('binding-change', event.detail)}
                @binding-remove=${(event) => this.emit('binding-remove', event.detail)}
            ></flows-interface-binding-editor>
            <flows-interface-action-editor
                .actions=${component.actions || {}}
                .pages=${this.pages}
                @action-change=${(event) => this.emit('action-change', event.detail)}
            ></flows-interface-action-editor>
            ${!isRoot ? html`<platform-button
                class="danger-action"
                variant="danger"
                density="compact"
                block
                @click=${() => this.emit('component-delete', { componentId: component.component_id })}
            >${this.t('interface_editor.inspector_delete')}</platform-button>` : nothing}
        `;
    }
}

if (!customElements.get('flows-interface-inspector')) {
    customElements.define('flows-interface-inspector', FlowsInterfaceInspector);
}

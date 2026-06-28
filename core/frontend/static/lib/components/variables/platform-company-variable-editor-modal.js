/**
 * Create/edit modal for PlatformVariable (company scope).
 */

import { html, css } from 'lit';
import { PlatformFormModal } from '../glass-form-modal.js';
import { registerModalKind } from '../../utils/modal-registry.js';
import '../fields/platform-field.js';
import './platform-variable-value-editor.js';
import './platform-variable-scopes-editor.js';
import './platform-variable-secret-policy.js';
import './platform-variable-resolve-preview.js';

function _defaultPayload() {
    return {
        base: { value_kind: 'static', value: '', expression: '' },
        scopes: [],
    };
}

function _payloadFromItem(item) {
    if (!item || !item.payload) {
        return _defaultPayload();
    }
    const base = item.payload.base || {};
    const scopes = Array.isArray(item.payload.scopes) ? item.payload.scopes.map((scope) => ({
        value_kind: scope.value_kind === 'expression' ? 'expression' : 'static',
        value: scope.value ?? '',
        expression: scope.expression ?? '',
        priority: typeof scope.priority === 'number' ? scope.priority : 0,
        match: Array.isArray(scope.match) ? scope.match.map((entry) => ({
            field: entry.field,
            op: entry.op ?? 'eq',
            ref_key: entry.ref_key ?? null,
            value: entry.value ?? '',
        })) : [],
    })) : [];
    return {
        base: {
            value_kind: base.value_kind === 'expression' ? 'expression' : 'static',
            value: base.value === null || base.value === undefined ? '' : String(base.value),
            expression: base.expression ?? '',
        },
        scopes,
    };
}

export class PlatformCompanyVariableEditorModal extends PlatformFormModal {
    static modalKind = 'platform.company_variable_editor';
    static i18nNamespace = 'company_variables';

    static properties = {
        ...PlatformFormModal.properties,
        variableKey: { type: String, attribute: 'variable-key' },
        _key: { state: true },
        _title: { state: true },
        _description: { state: true },
        _order: { state: true },
        _groups: { state: true },
        _public: { state: true },
        _secret: { state: true },
        _sharedForExecution: { state: true },
        _payload: { state: true },
    };

    static styles = [
        ...(PlatformFormModal.styles ? [PlatformFormModal.styles] : []),
        css`
            .section {
                margin-bottom: var(--space-4);
                padding-bottom: var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
            }
            .section:last-child { border-bottom: none; }
            .section-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin: 0 0 var(--space-3) 0;
            }
            .field { margin-bottom: var(--space-3); }
        `,
    ];

    constructor() {
        super();
        this.variableKey = '';
        this._key = '';
        this._title = '';
        this._description = '';
        this._order = '';
        this._groups = '';
        this._public = false;
        this._secret = false;
        this._sharedForExecution = false;
        this._payload = _defaultPayload();
        this._variables = this.useResource('secrets/variables');
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('variableKey') && this.variableKey) {
            this._loadExisting(this.variableKey);
        }
    }

    async _loadExisting(variableKey) {
        const item = await this._variables.get(variableKey);
        if (!item) {
            throw new Error(`platform-company-variable-editor-modal: variable "${variableKey}" not found`);
        }
        this._key = item.variable_key;
        this._title = item.title ?? '';
        this._description = item.description ?? '';
        this._order = item.order === null || item.order === undefined ? '' : String(item.order);
        this._groups = Array.isArray(item.groups) ? item.groups.join(', ') : '';
        this._public = Boolean(item.public);
        this._secret = Boolean(item.secret);
        this._sharedForExecution = Boolean(item.shared_for_execution);
        this._payload = _payloadFromItem(item);
    }

    renderHeader() {
        return html`<h3>${this.t(this.variableKey ? 'editor.title_edit' : 'editor.title_create')}</h3>`;
    }

    _buildWritePayload() {
        const key = this.variableKey || this._key.trim();
        if (!key) {
            throw new Error('platform-company-variable-editor-modal: variable_key required');
        }
        const orderRaw = this._order.trim();
        let order = null;
        if (orderRaw !== '') {
            order = Number(orderRaw);
            if (Number.isNaN(order)) {
                throw new Error('platform-company-variable-editor-modal: order must be number');
            }
        }
        const groups = this._groups
            .split(',')
            .map((group) => group.trim())
            .filter((group) => group.length > 0);
        const base = this._payload.base;
        const payload = {
            base: {
                value_kind: base.value_kind,
                value: base.value_kind === 'static' ? base.value : null,
                expression: base.value_kind === 'expression' ? base.expression : null,
            },
            scopes: this._payload.scopes.map((scope) => ({
                value_kind: scope.value_kind,
                value: scope.value_kind === 'static' ? scope.value : null,
                expression: scope.value_kind === 'expression' ? scope.expression : null,
                priority: scope.priority,
                match: scope.match,
            })),
        };
        return {
            variable_key: key,
            payload,
            secret: this._secret,
            shared_for_execution: this._sharedForExecution,
            public: this._public,
            title: this._title.trim() === '' ? null : this._title.trim(),
            description: this._description,
            order,
            groups,
        };
    }

    async handleSubmit() {
        const body = this._buildWritePayload();
        await this._variables.create(body);
        this.closeAfterSave();
    }

    renderBody() {
        const editing = Boolean(this.variableKey);
        return html`
            <section class="section">
                <h4 class="section-title">${this.t('editor.section_basic')}</h4>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('editor.field_key')}
                        .value=${this._key}
                        ?disabled=${editing}
                        @change=${(e) => {
                            if (!editing) {
                                this._key = typeof e.detail.value === 'string' ? e.detail.value : '';
                                this.isDirty = true;
                            }
                        }}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('editor.field_title')}
                        .value=${this._title}
                        @change=${(e) => { this._title = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('editor.field_description')}
                        .value=${this._description}
                        @change=${(e) => { this._description = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('editor.field_order')}
                        .value=${this._order}
                        @change=${(e) => { this._order = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('editor.field_groups')}
                        .value=${this._groups}
                        @change=${(e) => { this._groups = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
            </section>

            <section class="section">
                <h4 class="section-title">${this.t('editor.section_value')}</h4>
                <platform-variable-value-editor
                    .valueKind=${this._payload.base.value_kind}
                    .value=${this._payload.base.value}
                    .expression=${this._payload.base.expression}
                    @change=${(e) => {
                        this._payload = { ...this._payload, base: { ...this._payload.base, ...e.detail } };
                        this.isDirty = true;
                    }}
                ></platform-variable-value-editor>
            </section>

            <section class="section">
                <h4 class="section-title">${this.t('editor.section_scopes')}</h4>
                <platform-variable-scopes-editor
                    .scopes=${this._payload.scopes}
                    @change=${(e) => {
                        this._payload = { ...this._payload, scopes: e.detail.scopes };
                        this.isDirty = true;
                    }}
                ></platform-variable-scopes-editor>
            </section>

            <section class="section">
                <h4 class="section-title">${this.t('editor.section_access')}</h4>
                <platform-variable-secret-policy
                    .secret=${this._secret}
                    .sharedForExecution=${this._sharedForExecution}
                    @change=${(e) => {
                        this._secret = Boolean(e.detail.secret);
                        this._sharedForExecution = Boolean(e.detail.shared_for_execution);
                        this.isDirty = true;
                    }}
                ></platform-variable-secret-policy>
                <div class="field">
                    <platform-field
                        type="boolean"
                        mode="edit"
                        .label=${this.t('editor.field_public')}
                        .value=${this._public}
                        @change=${(e) => { this._public = Boolean(e.detail.value); this.isDirty = true; }}
                    ></platform-field>
                </div>
            </section>

            <section class="section">
                <h4 class="section-title">${this.t('editor.section_preview')}</h4>
                <platform-variable-resolve-preview
                    .variableKey=${this.variableKey || this._key}
                ></platform-variable-resolve-preview>
            </section>
        `;
    }
}

customElements.define('platform-company-variable-editor-modal', PlatformCompanyVariableEditorModal);
registerModalKind(PlatformCompanyVariableEditorModal.modalKind, 'platform-company-variable-editor-modal');

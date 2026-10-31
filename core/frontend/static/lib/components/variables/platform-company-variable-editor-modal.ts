/**
 * Create/edit modal for PlatformVariable (company scope).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { isPlainRecord } from '../../events/payload.js';
import { PlatformFormModal } from '../glass-form-modal.js';
import { registerModalKind } from '../../utils/modal-registry.js';
import type { ResourceItem } from '../../events/factories/resource-collection.js';
import type { ResourceController } from '../../base/use-resource.js';
import '../fields/platform-field.js';
import './platform-variable-value-editor.js';
import './platform-variable-scopes-editor.js';
import './platform-variable-secret-policy.js';
import './platform-variable-resolve-preview.js';

interface VariableMatchEntry {
    field?: string | undefined;
    op?: string;
    ref_key?: string | null;
    value?: unknown;
}

interface VariableScope {
    value_kind: 'static' | 'expression';
    value: string;
    expression: string;
    priority: number;
    match: VariableMatchEntry[];
}

interface VariablePayload {
    base: { value_kind: 'static' | 'expression'; value: string; expression: string };
    scopes: VariableScope[];
}

function _defaultPayload(): VariablePayload {
    return {
        base: { value_kind: 'static', value: '', expression: '' },
        scopes: [],
    };
}

function textValue(value: unknown): string {
    if (typeof value === 'string') return value;
    if (value === undefined || value === null) return '';
    return String(value);
}

function matchEntry(value: unknown): VariableMatchEntry {
    if (!isPlainRecord(value)) {
        throw new Error('company variable editor: scope match entry must be an object');
    }
    const op = value.op;
    return {
        field: typeof value.field === 'string' ? value.field : undefined,
        op: typeof op === 'string' && op.length > 0 ? op : 'eq',
        ref_key: typeof value.ref_key === 'string' ? value.ref_key : null,
        value: textValue(value.value),
    };
}

function variableScope(value: unknown): VariableScope {
    if (!isPlainRecord(value)) {
        throw new Error('company variable editor: scope must be an object');
    }
    return {
        value_kind: value.value_kind === 'expression' ? 'expression' : 'static',
        value: textValue(value.value),
        expression: typeof value.expression === 'string' ? value.expression : '',
        priority: typeof value.priority === 'number' ? value.priority : 0,
        match: Array.isArray(value.match) ? value.match.map(matchEntry) : [],
    };
}

function valueChange(detail: unknown): VariablePayload['base'] {
    if (!isPlainRecord(detail)) {
        throw new Error('company variable editor: value change must be an object');
    }
    const kind = detail.value_kind;
    if (kind !== 'static' && kind !== 'expression') {
        throw new Error('company variable editor: value_kind must be static or expression');
    }
    return {
        value_kind: kind,
        value: textValue(detail.value),
        expression: typeof detail.expression === 'string' ? detail.expression : '',
    };
}

function scopesChange(detail: unknown): VariableScope[] {
    if (!isPlainRecord(detail) || !Array.isArray(detail.scopes)) {
        throw new Error('company variable editor: scopes change must include scopes');
    }
    return detail.scopes.map(variableScope);
}

function _payloadFromItem(item: ResourceItem | null | undefined): VariablePayload {
    const rawPayload = item === null || item === undefined ? undefined : item.payload;
    if (!isPlainRecord(rawPayload)) {
        return _defaultPayload();
    }
    const base = isPlainRecord(rawPayload.base) ? rawPayload.base : {};
    const scopes = Array.isArray(rawPayload.scopes) ? rawPayload.scopes.map(variableScope) : [];
    return {
        base: {
            value_kind: base.value_kind === 'expression' ? 'expression' : 'static',
            value: base.value === null || base.value === undefined ? '' : String(base.value),
            expression: typeof base.expression === 'string' ? base.expression : '',
        },
        scopes,
    };
}

export class PlatformCompanyVariableEditorModal extends PlatformFormModal {
    static modalKind = 'platform.company_variable_editor';
    static i18nNamespace = 'company_variables';

    static override properties: PropertyDeclarations = {
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
    declare variableKey: string;
    declare _key: string;
    declare _title: string;
    declare _description: string;
    declare _order: string;
    declare _groups: string;
    declare _public: boolean;
    declare _secret: boolean;
    declare _sharedForExecution: boolean;
    declare _payload: VariablePayload;

    private _loadSeq: number;
    private _variables: ResourceController;

    static override styles: CSSResultGroup = [
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
        this._loadSeq = 0;
        this._variables = this.useResource('secrets/variables');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('variableKey')) {
            if (this.variableKey) {
                void this._loadExisting(this.variableKey);
            } else {
                this._resetCreateForm();
            }
        }
    }

    _resetCreateForm() {
        this._loadSeq += 1;
        this._key = '';
        this._title = '';
        this._description = '';
        this._order = '';
        this._groups = '';
        this._public = false;
        this._secret = false;
        this._sharedForExecution = false;
        this._payload = _defaultPayload();
    }

    _applyItem(item: ResourceItem): void {
        this._key = typeof item.variable_key === 'string' ? item.variable_key : '';
        this._title = typeof item.title === 'string' ? item.title : '';
        this._description = typeof item.description === 'string' ? item.description : '';
        this._order = item.order === null || item.order === undefined ? '' : String(item.order);
        this._groups = Array.isArray(item.groups) ? item.groups.map((group) => textValue(group)).join(', ') : '';
        this._public = Boolean(item.public);
        this._secret = Boolean(item.secret);
        this._sharedForExecution = Boolean(item.shared_for_execution);
        this._payload = _payloadFromItem(item);
    }

    async _loadExisting(variableKey: string): Promise<void> {
        const seq = ++this._loadSeq;
        const cached = this._variables.byId[variableKey];
        if (cached) {
            this._applyItem(cached);
        }
        const item = await this._variables.fetchItem(variableKey);
        if (seq !== this._loadSeq) {
            return;
        }
        this._applyItem(item);
    }

    override renderHeader() {
        return html`<h3>${this.t(this.variableKey ? 'editor.title_edit' : 'editor.title_create')}</h3>`;
    }

    _buildWritePayload(): Record<string, unknown> {
        const key = this.variableKey || this._key.trim();
        if (!key) {
            throw new Error('platform-company-variable-editor-modal: variable_key required');
        }
        const orderRaw = this._order.trim();
        let order: number | null = null;
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
            scopes: this._payload.scopes.map((scope: VariableScope) => ({
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

    override async handleSubmit(): Promise<void> {
        const body = this._buildWritePayload();
        await this._variables.create(body);
        this.closeAfterSave();
    }

    override renderBody() {
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
                        @change=${(e: CustomEvent) => {
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
                        @change=${(e: CustomEvent) => { this._title = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="text"
                        mode="edit"
                        .label=${this.t('editor.field_description')}
                        .value=${this._description}
                        @change=${(e: CustomEvent) => { this._description = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('editor.field_order')}
                        .value=${this._order}
                        @change=${(e: CustomEvent) => { this._order = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
                <div class="field">
                    <platform-field
                        type="string"
                        mode="edit"
                        .label=${this.t('editor.field_groups')}
                        .value=${this._groups}
                        @change=${(e: CustomEvent) => { this._groups = typeof e.detail.value === 'string' ? e.detail.value : ''; this.isDirty = true; }}
                    ></platform-field>
                </div>
            </section>

            <section class="section">
                <h4 class="section-title">${this.t('editor.section_value')}</h4>
                <platform-variable-value-editor
                    .valueKind=${this._payload.base.value_kind}
                    .value=${this._payload.base.value}
                    .expression=${this._payload.base.expression}
                    @change=${(e: CustomEvent) => {
                        this._payload = { ...this._payload, base: valueChange(e.detail) };
                        this.isDirty = true;
                    }}
                ></platform-variable-value-editor>
            </section>

            <section class="section">
                <h4 class="section-title">${this.t('editor.section_scopes')}</h4>
                <platform-variable-scopes-editor
                    .scopes=${this._payload.scopes}
                    @change=${(e: CustomEvent) => {
                        this._payload = { ...this._payload, scopes: scopesChange(e.detail) };
                        this.isDirty = true;
                    }}
                ></platform-variable-scopes-editor>
            </section>

            <section class="section">
                <h4 class="section-title">${this.t('editor.section_access')}</h4>
                <platform-variable-secret-policy
                    .secret=${this._secret}
                    .sharedForExecution=${this._sharedForExecution}
                    @change=${(e: CustomEvent) => {
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
                        @change=${(e: CustomEvent) => { this._public = Boolean(e.detail.value); this.isDirty = true; }}
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

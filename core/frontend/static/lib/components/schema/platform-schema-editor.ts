/**
 * platform-schema-editor — dual-mode JSON Schema object editor (Form cards / JSON).
 * Presentational: value object in, schema-change { value, valid, error? } out.
 */

import { html, css, nothing } from '../../lit-shim.js';
import { PlatformElement } from '../../platform-element/index.js';
import '../platform-segmented-control.js';
import '../platform-button.js';
import '../platform-icon.js';
import '../platform-json-editor.js';
import './platform-schema-parameter-card.js';
import { formatJsonPretty } from '../../utils/json-format.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from '../../lit-shim.js';
import {
    createEmptyParameterRow,
    detectAdvancedSchemaFeatures,
    normalizeParametersSchema,
    parameterRowsToSchema,
    parseSchemaForEditor,
    validateParameterRows,
} from './schema-model.js';
import type { ParameterRow } from './schema-model.js';

export class PlatformSchemaEditor extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        /** JSON Schema object | null */
        value: { type: Object },
        /** Controlled mode: 'form' | 'json'. Empty = internal defaultMode. */
        mode: { type: String },
        defaultMode: { type: String, attribute: 'default-mode' },
        readonly: { type: Boolean, reflect: true },
        fillParent: { type: Boolean, reflect: true, attribute: 'fill-parent' },
        showPreview: { type: Boolean, attribute: 'show-preview' },
        minHeight: { type: Number, attribute: 'min-height' },
        _internalMode: { state: true },
        _rows: { state: true },
        _rest: { state: true },
        _advanced: { state: true },
        _advancedReasons: { state: true },
        _jsonText: { state: true },
        _jsonInvalid: { state: true },
        _jsonError: { state: true },
        _formError: { state: true },
        _syncToken: { state: true },
    }
    declare value: Record<string, unknown> | null;
    declare mode: string;
    declare defaultMode: string;
    declare readonly: boolean;
    declare fillParent: boolean;
    declare showPreview: boolean;
    declare minHeight: number;
    declare _internalMode: 'form' | 'json';
    declare _rows: ParameterRow[];
    declare _rest: Record<string, unknown>;
    declare _advanced: boolean;
    declare _advancedReasons: string[];
    declare _jsonText: string;
    declare _jsonInvalid: boolean;
    declare _jsonError: string;
    declare _formError: string;
    declare _syncToken: number;

    private _suppressValueSync: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-width: 0;
                gap: var(--space-2);
            }
            :host([fill-parent]) {
                flex: 1 1 auto;
                min-height: 0;
                height: 100%;
            }
            .toolbar {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .toolbar-end {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
            }
            .banner {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--warning-border, var(--glass-border-subtle));
                background: var(--warning-bg, var(--glass-solid-subtle));
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: 1.4;
            }
            .banner platform-icon {
                flex-shrink: 0;
                margin-top: 2px;
                color: var(--warning, var(--accent));
            }
            .form-body {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                min-height: 0;
            }
            :host([fill-parent]) .form-body {
                flex: 1 1 auto;
                overflow: auto;
            }
            .cards {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .empty {
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: var(--space-2);
                padding: var(--space-4);
                border: 1px dashed var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
            }
            .empty-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .empty-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
                max-width: 42rem;
            }
            .error {
                color: var(--error);
                font-size: var(--text-xs);
            }
            .preview {
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
            }
            .preview-title {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                color: var(--text-tertiary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .preview-list {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
            }
            .preview-chip {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 8px;
                border-radius: var(--radius-full, 999px);
                border: 1px solid var(--glass-border-subtle);
                background: var(--bg-elevated, var(--glass-solid-medium));
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-family: var(--font-mono);
            }
            .preview-chip[data-required] {
                border-color: var(--accent);
                color: var(--text-primary);
            }
            .preview-empty {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .json-wrap {
                min-height: var(--schema-editor-min-height, 220px);
            }
            :host([fill-parent]) .json-wrap {
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            :host([fill-parent]) platform-json-editor {
                flex: 1 1 auto;
                min-height: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.mode = '';
        this.defaultMode = 'form';
        this.readonly = false;
        this.fillParent = false;
        this.showPreview = true;
        this.minHeight = 220;
        this._internalMode = 'form';
        this._rows = [];
        this._rest = {};
        this._advanced = false;
        this._advancedReasons = [];
        this._jsonText = formatJsonPretty({ type: 'object', properties: {} });
        this._jsonInvalid = false;
        this._jsonError = '';
        this._formError = '';
        this._syncToken = 0;
        this._suppressValueSync = false;
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this._hydrateFromValue(this.value, { forceMode: true });
    }

    override updated(changed: PropertyValues): void {
        super.updated?.(changed);
        if (changed.has('minHeight')) {
            const value = Number.isFinite(this.minHeight) ? this.minHeight : 220;
            this.style.setProperty('--schema-editor-min-height', `${value}px`);
        }
        if (changed.has('value') && !this._suppressValueSync) {
            this._hydrateFromValue(this.value, { forceMode: false });
        }
        if (changed.has('mode') && typeof this.mode === 'string' && this.mode.length > 0) {
            this._internalMode = this.mode === 'json' ? 'json' : 'form';
        }
    }

    _effectiveMode(): 'form' | 'json' {
        if (typeof this.mode === 'string' && this.mode.length > 0) {
            return this.mode === 'json' ? 'json' : 'form';
        }
        return this._internalMode === 'json' ? 'json' : 'form';
    }

    _hydrateFromValue(raw: unknown, opts: { forceMode: boolean }): void {
        let parsed;
        try {
            parsed = parseSchemaForEditor(raw);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this._advanced = true;
            this._advancedReasons = ['parse_error'];
            this._rows = [];
            this._rest = {};
            this._jsonText = typeof raw === 'string' ? raw : formatJsonPretty(raw ?? { type: 'object', properties: {} });
            this._jsonInvalid = true;
            this._jsonError = message;
            this._formError = message;
            if (opts.forceMode || this._effectiveMode() === 'form') {
                this._setMode('json');
            }
            return;
        }
        this._rows = parsed.rows;
        this._rest = parsed.rest;
        this._advanced = parsed.advanced;
        this._advancedReasons = parsed.reasons;
        this._jsonText = formatJsonPretty(parsed.schema);
        this._jsonInvalid = false;
        this._jsonError = '';
        this._formError = '';
        if (parsed.advanced && this._effectiveMode() === 'form') {
            this._setMode('json');
        } else if (opts.forceMode && !parsed.advanced) {
            const preferred =
                typeof this.defaultMode === 'string' && this.defaultMode === 'json' ? 'json' : 'form';
            this._setMode(preferred);
        }
    }

    _setMode(next: 'form' | 'json'): void {
        if (typeof this.mode === 'string' && this.mode.length > 0) {
            this.emit('mode-change', { mode: next });
            return;
        }
        this._internalMode = next;
    }

    _emitSchemaChange(schema: Record<string, unknown> | null, valid: boolean, error?: string): void {
        this._suppressValueSync = true;
        this.value = schema;
        this.emit('schema-change', {
            value: schema,
            valid,
            ...(typeof error === 'string' && error.length > 0 ? { error } : {}),
        });
        queueMicrotask(() => {
            this._suppressValueSync = false;
        });
    }

    _emitFromRows(): void {
        if (this._advanced) {
            return;
        }
        const validation = validateParameterRows(this._rows);
        if (!validation.valid) {
            this._formError = validation.error;
            this._emitSchemaChange(this.value, false, validation.valid ? undefined : validation.error);
            return;
        }
        this._formError = '';
        const schema = parameterRowsToSchema(this._rows, this._rest);
        this._jsonText = formatJsonPretty(schema);
        this._emitSchemaChange(schema, true);
    }

    _onModeChange(e: CustomEvent<{ value?: unknown }>): void {
        e.stopPropagation();
        const next = e.detail?.value === 'json' ? 'json' : 'form';
        if (next === 'form' && this._advanced) {
            this._setMode('json');
            return;
        }
        if (next === 'form' && this._jsonInvalid) {
            return;
        }
        if (next === 'form' && !this._advanced) {
            try {
                const normalized = normalizeParametersSchema(
                    this._jsonInvalid ? this.value : JSON.parse(this._jsonText),
                );
                this._rows = parseSchemaForEditor({
                    type: 'object',
                    properties: normalized.properties,
                    required: normalized.required,
                    ...normalized.rest,
                }).rows;
                this._rest = normalized.rest;
            } catch (err) {
                this._jsonInvalid = true;
                this._jsonError = err instanceof Error ? err.message : String(err);
                return;
            }
        }
        if (next === 'json' && !this._advanced) {
            const validation = validateParameterRows(this._rows);
            if (validation.valid) {
                this._jsonText = formatJsonPretty(parameterRowsToSchema(this._rows, this._rest));
                this._jsonInvalid = false;
                this._jsonError = '';
            }
        }
        this._setMode(next);
    }

    _onJsonChange(e: CustomEvent<{ value?: unknown; parsed?: unknown }>): void {
        e.stopPropagation();
        const detail = e.detail;
        if (!detail || typeof detail !== 'object') {
            return;
        }
        if (!('parsed' in detail)) {
            if (typeof detail.value === 'string') {
                this._jsonText = detail.value;
                this._jsonInvalid = true;
                this._jsonError = this.t('schema_editor.json_invalid');
            }
            return;
        }
        const parsed = detail.parsed;
        this._jsonText = typeof detail.value === 'string' ? detail.value : formatJsonPretty(parsed);
        if (parsed === null) {
            const empty = { type: 'object', properties: {} };
            this._jsonInvalid = false;
            this._jsonError = '';
            const detection = detectAdvancedSchemaFeatures(empty);
            this._advanced = detection.advanced;
            this._advancedReasons = detection.reasons;
            this._rows = [];
            this._rest = {};
            this._emitSchemaChange(empty, true);
            return;
        }
        try {
            const editorState = parseSchemaForEditor(parsed);
            this._jsonInvalid = false;
            this._jsonError = '';
            this._advanced = editorState.advanced;
            this._advancedReasons = editorState.reasons;
            this._rows = editorState.rows;
            this._rest = editorState.rest;
            this._emitSchemaChange(editorState.schema, true);
        } catch (err) {
            this._jsonInvalid = true;
            this._jsonError = err instanceof Error ? err.message : String(err);
            this._emitSchemaChange(this.value, false, this._jsonError);
        }
    }

    _addParameter(): void {
        if (this.readonly || this._advanced) {
            return;
        }
        this._rows = [...this._rows, createEmptyParameterRow()];
        this._emitFromRows();
    }

    _onRowChange(e: CustomEvent<{ index?: unknown; row?: unknown }>): void {
        e.stopPropagation();
        if (this.readonly || this._advanced) {
            return;
        }
        const index = e.detail?.index;
        const row = e.detail?.row;
        if (typeof index !== 'number' || !row || typeof row !== 'object') {
            throw new Error('platform-schema-editor: row-change detail');
        }
        const nextRow = row as ParameterRow;
        this._rows = this._rows.map((item, i) => (i === index ? nextRow : item));
        this._emitFromRows();
    }

    _onRowRemove(e: CustomEvent<{ index?: unknown }>): void {
        e.stopPropagation();
        if (this.readonly || this._advanced) {
            return;
        }
        const index = e.detail?.index;
        if (typeof index !== 'number') {
            throw new Error('platform-schema-editor: row-remove detail');
        }
        this._rows = this._rows.filter((_, i) => i !== index);
        this._emitFromRows();
    }

    _onRowMove(e: CustomEvent<{ index?: unknown; direction?: unknown }>): void {
        e.stopPropagation();
        if (this.readonly || this._advanced) {
            return;
        }
        const index = e.detail?.index;
        const direction = e.detail?.direction;
        if (typeof index !== 'number' || (direction !== 1 && direction !== -1)) {
            throw new Error('platform-schema-editor: row-move detail');
        }
        const target = index + direction;
        if (target < 0 || target >= this._rows.length) {
            return;
        }
        const next = [...this._rows];
        const [item] = next.splice(index, 1);
        if (item) {
            next.splice(target, 0, item);
        }
        this._rows = next;
        this._emitFromRows();
    }

    _previewChips(): { key: string; uiType: string; required: boolean }[] {
        return this._rows
            .map((row) => {
                const key = typeof row.key === 'string' ? row.key.trim() : '';
                if (key.length === 0) {
                    return null;
                }
                return {
                    key,
                    uiType: row.uiType,
                    required: Boolean(row.required),
                };
            })
            .filter((item) => item !== null);
    }

    _renderPreview(): TemplateResult | typeof nothing {
        if (!this.showPreview || this._effectiveMode() !== 'form' || this._advanced) {
            return nothing;
        }
        const chips = this._previewChips();
        return html`
            <div class="preview" aria-label=${this.t('schema_editor.preview_aria')}>
                <div class="preview-title">${this.t('schema_editor.preview_title')}</div>
                ${chips.length === 0
                    ? html`<div class="preview-empty">${this.t('schema_editor.preview_empty')}</div>`
                    : html`
                        <div class="preview-list">
                            ${chips.map(
                                (chip) => html`
                                    <span class="preview-chip" ?data-required=${chip.required}>
                                        ${chip.key}: ${this.t(`schema_editor.type_${chip.uiType}`)}
                                        ${chip.required ? html`*` : nothing}
                                    </span>
                                `,
                            )}
                        </div>
                    `}
            </div>
        `;
    }

    _renderAdvancedBanner(): TemplateResult | typeof nothing {
        if (!this._advanced) {
            return nothing;
        }
        return html`
            <div class="banner" role="status">
                <platform-icon name="alert-triangle" size="16"></platform-icon>
                <div>${this.t('schema_editor.advanced_banner')}</div>
            </div>
        `;
    }

    _renderForm(): TemplateResult | typeof nothing {
        if (this._advanced) {
            return nothing;
        }
        const rows = this._rows;
        return html`
            <div class="form-body">
                ${rows.length === 0
                    ? html`
                        <div class="empty">
                            <div class="empty-title">${this.t('schema_editor.empty_title')}</div>
                            <div class="empty-hint">${this.t('schema_editor.empty_hint')}</div>
                            ${this.readonly
                                ? nothing
                                : html`
                                    <platform-button variant="primary" density="compact" @click=${this._addParameter}>
                                        <platform-icon name="plus" size="14"></platform-icon>
                                        ${this.t('schema_editor.add_parameter')}
                                    </platform-button>
                                `}
                        </div>
                    `
                    : html`
                        <div
                            class="cards"
                            @row-change=${this._onRowChange}
                            @row-remove=${this._onRowRemove}
                            @row-move=${this._onRowMove}
                        >
                            ${rows.map(
                                (row, index) => html`
                                    <platform-schema-parameter-card
                                        .row=${row}
                                        .index=${index}
                                        ?readonly=${this.readonly}
                                        ?canMoveUp=${index > 0}
                                        ?canMoveDown=${index < rows.length - 1}
                                    ></platform-schema-parameter-card>
                                `,
                            )}
                        </div>
                        ${this.readonly
                            ? nothing
                            : html`
                                <platform-button variant="secondary" density="compact" @click=${this._addParameter}>
                                    <platform-icon name="plus" size="14"></platform-icon>
                                    ${this.t('schema_editor.add_parameter')}
                                </platform-button>
                            `}
                    `}
                ${this._formError
                    ? html`<div class="error">${this._formError}</div>`
                    : nothing}
                ${this._renderPreview()}
            </div>
        `;
    }

    _renderJson(): TemplateResult {
        return html`
            <div class="json-wrap">
                <platform-json-editor
                    validate-json
                    show-toolbar="false"
                    ?fill-parent=${this.fillParent}
                    ?readonly=${this.readonly}
                    .minHeight=${this.minHeight}
                    .value=${this._jsonText}
                    @change=${this._onJsonChange}
                ></platform-json-editor>
                ${this._jsonInvalid && this._jsonError
                    ? html`<div class="error">${this._jsonError}</div>`
                    : nothing}
            </div>
        `;
    }

    override render(): TemplateResult {
        const mode = this._effectiveMode();
        const formDisabled = this._advanced || this._jsonInvalid;
        const modeItems = [
            {
                value: 'form',
                label: this.t('schema_editor.mode_form'),
                disabled: formDisabled,
            },
            {
                value: 'json',
                label: this.t('schema_editor.mode_json'),
            },
        ];
        return html`
            <div class="toolbar">
                <platform-segmented-control
                    density="compact"
                    .value=${mode}
                    .items=${modeItems}
                    aria-label=${this.t('schema_editor.mode_aria')}
                    @change=${this._onModeChange}
                ></platform-segmented-control>
                <div class="toolbar-end">
                    ${mode === 'form' && !this._advanced && !this.readonly
                        ? html`
                            <platform-button variant="ghost" density="compact" @click=${this._addParameter}>
                                <platform-icon name="plus" size="14"></platform-icon>
                                ${this.t('schema_editor.add_parameter')}
                            </platform-button>
                        `
                        : nothing}
                </div>
            </div>
            ${this._renderAdvancedBanner()}
            ${mode === 'json' ? this._renderJson() : this._renderForm()}
        `;
    }
}

customElements.define('platform-schema-editor', PlatformSchemaEditor);

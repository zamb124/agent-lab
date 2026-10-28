/**
 * CRMKnowledgeImportModal — мастер импорта знаний в выбранный namespace.
 *
 * 5-шаговый мастер поверх PlatformModal:
 *   0. mode      — graph (полный граф сущностей и связей) | notes_only (только заметки).
 *   1. types     — какие типы сущностей извлекать; пусто = все типы из namespace.
 *   2. source    — файлы (через platform/file_create) и/или вставленный текст.
 *   3. settings  — split_by_headings, chunk_max_chars (2000..500000).
 *   4. summary   — финальный обзор и запуск crm/task_knowledge_import_start.
 *
 * Шаг source:
 *   - upload файла идёт через chunked `/{segment}/api/v1/files/uploads*` (platform/file_create),
 *     id-шники накапливаются в this._files и подставляются в payload как
 *     source_file_ids.
 *   - paste-area — обычный textarea, отдаётся в payload как source_text.
 *   - хотя бы один источник (файл ИЛИ текст) обязателен.
 *
 * Состояние пространства:
 *   - целевой namespace — `selectCrmApiNamespace` (тот же срез, что у страниц CRM);
 *     при режиме «все пространства» wizard блокирует запуск; список типов перезагружается
 *     при смене пространства и при открытии модалки.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { CoreEvents } from '@platform/lib/events/index.js';
import { selectCrmApiNamespace } from '../_helpers/crm-namespace-select.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import { buildPlatformAuxiliaryFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/fields/platform-field.js';
import type {
    TemplateResult,
    CSSResultGroup,
    PropertyDeclarations,
    PropertyValues,
} from 'lit';
import type {
    OpController,
    ResourceController,
} from '@platform/lib/base/use-resource.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

function anyRecord(value: unknown): Record<string, any> | null {
    if (!isPlainRecord(value)) return null;
    const row: Record<string, any> = {};
    for (const [key, field] of Object.entries(value)) row[key] = field;
    return row;
}

function dragEvent(event: Event): DragEvent {
    if (!(event instanceof DragEvent)) {
        throw new Error('knowledge-import-modal: drag event required');
    }
    return event;
}

const MAX_INLINE_TEXT = 100000;
const CHUNK_MIN = 2000;
const CHUNK_MAX = 500000;
const CHUNK_DEFAULT = 50000;

const MODES = Object.freeze([
    { id: 'graph', icon: 'graph', titleKey: 'mode_graph_title', descKey: 'mode_graph_desc' },
    { id: 'notes_only', icon: 'doc-detail', titleKey: 'mode_notes_title', descKey: 'mode_notes_desc' },
]);

const STEP_KEYS = Object.freeze([
    'step_mode', 'step_types', 'step_source', 'step_settings', 'step_summary',
]);

export class CRMKnowledgeImportModal extends PlatformModal {
    static modalKind = 'crm.knowledge_import';
    static i18nNamespace = 'crm';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        _step: { state: true },
        _mode: { state: true },
        _selectedTypeIds: { state: true },
        _files: { state: true },
        _pasteText: { state: true },
        _splitByHeadings: { state: true },
        _chunkMaxChars: { state: true },
        _uploading: { state: true },
        _starting: { state: true },
        _dropzoneActive: { state: true },
    };
    declare _step: number;
    declare _mode: string;
    declare _selectedTypeIds: string[];
    declare _files: { file_id: string; original_name: string; content_type: string }[];
    declare _pasteText: string;
    declare _splitByHeadings: boolean;
    declare _chunkMaxChars: number;
    declare _uploading: boolean;
    declare _starting: boolean;
    declare _dropzoneActive: boolean;

    static override styles: CSSResultGroup = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .ki-steps {
                display: flex; flex-wrap: wrap; gap: var(--space-2);
                padding: 0 0 var(--space-3) 0;
                border-bottom: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
                margin-bottom: var(--space-3);
            }
            .ki-step-pill {
                display: inline-flex; align-items: center; gap: 6px;
                padding: 4px 10px; font-size: var(--text-xs);
                color: var(--text-tertiary);
                border-radius: var(--radius-full, 999px);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
            }
            .ki-step-pill.active {
                color: var(--text-primary);
                border-color: var(--accent, #6366f1);
                background: rgba(99,102,241,0.1);
            }
            .ki-step-pill.done { color: var(--text-secondary); }
            .ki-step-num {
                display: inline-flex; align-items: center; justify-content: center;
                width: 18px; height: 18px; font-weight: 700;
                border-radius: 50%;
                background: rgba(255,255,255,0.06);
                color: inherit;
            }
            .ki-step-body { display: flex; flex-direction: column; gap: var(--space-4); }
            .ki-step-desc { color: var(--text-secondary); font-size: var(--text-sm); margin: 0; }
            .ki-empty { color: var(--text-tertiary); padding: var(--space-4); text-align: center; }

            .ki-mode-grid {
                display: grid; gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            }
            .ki-mode-card {
                display: flex; flex-direction: column; gap: 6px;
                padding: var(--space-4);
                border-radius: var(--radius-lg);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
                color: var(--text-primary);
                text-align: left; cursor: pointer;
            }
            .ki-mode-card:hover { border-color: var(--accent, #6366f1); }
            .ki-mode-card.active {
                border-color: var(--accent, #6366f1);
                background: rgba(99,102,241,0.1);
            }
            .ki-mode-title { font-weight: 600; font-size: var(--text-sm); }
            .ki-mode-desc { color: var(--text-tertiary); font-size: var(--text-xs); }

            .ki-types-grid {
                display: grid; gap: var(--space-2);
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            }
            .ki-type-card {
                display: inline-flex; align-items: center; gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
                color: var(--text-primary);
                cursor: pointer; text-align: left;
            }
            .ki-type-card.selected {
                border-color: var(--accent, #6366f1);
                background: rgba(99,102,241,0.1);
            }
            .ki-type-check {
                display: inline-flex; align-items: center; justify-content: center;
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid var(--glass-border-medium, rgba(255,255,255,0.1));
                color: var(--accent, #6366f1);
            }
            .ki-type-name { font-size: var(--text-sm); }

            .ki-dropzone {
                display: flex; flex-direction: column; align-items: center; gap: 6px;
                padding: var(--space-6);
                border-radius: var(--radius-lg);
                border: 2px dashed var(--glass-border-medium, rgba(255,255,255,0.1));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
                color: var(--text-secondary);
                cursor: pointer; position: relative;
            }
            .ki-dropzone.active { border-color: var(--accent, #6366f1); background: rgba(99,102,241,0.08); }
            .ki-dropzone:hover { border-color: var(--accent, #6366f1); }
            .ki-file-input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
            .ki-dropzone-label { font-weight: 600; color: var(--text-primary); }
            .ki-dropzone-hint { font-size: var(--text-xs); color: var(--text-tertiary); }

            .ki-uploading {
                font-size: var(--text-xs); color: var(--text-tertiary);
                text-align: center;
            }
            .ki-files-list { display: flex; flex-direction: column; gap: 6px; }
            .ki-file-row {
                display: flex; align-items: center; gap: var(--space-2);
                padding: 6px var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
                color: var(--text-primary);
            }
            .ki-file-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--text-sm); }
            .ki-file-remove {
                display: inline-flex; align-items: center; justify-content: center;
                width: 24px; height: 24px;
                background: transparent; color: var(--text-tertiary);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
                border-radius: var(--radius-sm);
                cursor: pointer;
            }
            .ki-file-remove:hover { color: var(--text-primary); }

            .ki-label { font-weight: 600; font-size: var(--text-sm); color: var(--text-primary); }
            .ki-textarea {
                resize: vertical;
                width: 100%;
                font: inherit;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium, rgba(255,255,255,0.1));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
                color: var(--text-primary);
                box-sizing: border-box;
            }
            .ki-input {
                font: inherit;
                padding: 6px var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium, rgba(255,255,255,0.1));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
                color: var(--text-primary);
            }
            .ki-input--num { width: 120px; text-align: right; font-variant-numeric: tabular-nums; }
            .ki-hint { font-size: var(--text-xs); color: var(--text-tertiary); }
            .ki-hint--err { color: #fda4af; }

            .ki-row {
                display: flex; align-items: center; justify-content: space-between;
                gap: var(--space-3);
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
            }
            .ki-row-text { display: flex; flex-direction: column; gap: 2px; }
            .ki-row-title { font-weight: 600; font-size: var(--text-sm); color: var(--text-primary); }
            .ki-row-desc { font-size: var(--text-xs); color: var(--text-tertiary); }

            .ki-summary-grid {
                display: grid; gap: var(--space-3);
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            }
            .ki-summary-card {
                padding: var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
                background: var(--glass-solid-subtle, rgba(255,255,255,0.02));
                display: flex; flex-direction: column; gap: 4px;
            }
            .ki-summary-card--wide { grid-column: 1 / -1; }
            .ki-summary-label { font-size: var(--text-xs); color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; }
            .ki-summary-value { font-size: var(--text-sm); color: var(--text-primary); word-break: break-word; }

            .ki-footer-row {
                display: flex; align-items: center; gap: var(--space-3);
                width: 100%;
            }
            .ki-footer-spacer { flex: 1; }
            .ki-btn {
                display: inline-flex; align-items: center; gap: 6px;
                font: inherit; font-weight: 600; font-size: var(--text-sm);
                padding: 8px var(--space-4);
                border-radius: var(--radius-md);
                cursor: pointer;
            }
            .ki-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .ki-btn--ghost {
                background: transparent;
                color: var(--text-secondary);
                border: 1px solid var(--glass-border-subtle, rgba(255,255,255,0.06));
            }
            .ki-btn--ghost:hover:not(:disabled) { color: var(--text-primary); }
            .ki-btn--primary {
                background: var(--accent, #6366f1);
                color: var(--platform-btn-primary-text, #fff);
                border: 1px solid var(--accent, #6366f1);
            }
            .ki-btn--primary:hover:not(:disabled) { filter: brightness(1.05); }
        `,
    ];

    private _entityTypes: ResourceController;
    private _fileUpload: OpController;
    private _startImport: OpController;
    private _crmNamespaceSel: SelectController<string | null>;

    constructor() {
        super();
        this.size = 'xl';
        this._step = 0;
        this._mode = 'graph';
        this._selectedTypeIds = [];
        this._files = [];
        this._pasteText = '';
        this._splitByHeadings = false;
        this._chunkMaxChars = CHUNK_DEFAULT;
        this._uploading = false;
        this._starting = false;
        this._dropzoneActive = false;

        this._entityTypes = this.useResource('crm/entity_types', { autoload: false });
        this._fileUpload = this.useOp('platform/file_create');
        this._startImport = this.useOp('crm/task_knowledge_import_start');

        this._crmNamespaceSel = this.select(selectCrmApiNamespace);
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('open') && this.open) {
            this._selectedTypeIds = [];
            this._reloadEntityTypesForImport();
        }
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.useEvent(this._startImport.op.events.SUCCEEDED, () => this.close());
        this.useEvent(CoreEvents.UI_NAMESPACE_CHANGED, () => {
            this._selectedTypeIds = [];
            this._reloadEntityTypesForImport();
        });
        this._reloadEntityTypesForImport();
    }

    _reloadEntityTypesForImport() {
        const ns = this._currentNamespace();
        if (typeof ns === 'string' && ns.length > 0) {
            this._entityTypes.load({ namespace: ns });
            return;
        }
        this._entityTypes.load(null);
    }

    _currentNamespace(): string | null | undefined {
        return this._crmNamespaceSel.value;
    }

    _hasNamespace(): boolean {
        const ns = this._currentNamespace();
        return typeof ns === 'string' && ns.length > 0;
    }

    _allowedTypes(): Record<string, any>[] {
        const items: Record<string, any>[] = [];
        for (const item of this._entityTypes.items) {
            const row = anyRecord(item);
            if (row === null) {
                throw new Error('knowledge-import-modal: entity type must be an object');
            }
            items.push(row);
        }
        return items;
    }

    _toggleType(typeId: unknown): void {
        if (typeof typeId !== 'string' || typeId.length === 0) {
            throw new Error('CRMKnowledgeImportModal._toggleType: typeId required');
        }
        const next = [...this._selectedTypeIds];
        const idx = next.indexOf(typeId);
        if (idx >= 0) {
            next.splice(idx, 1);
        } else {
            next.push(typeId);
        }
        this._selectedTypeIds = next;
    }

    _setMode(mode: string): void {
        if (mode !== 'graph' && mode !== 'notes_only') {
            throw new Error(`CRMKnowledgeImportModal._setMode: bad mode ${mode}`);
        }
        this._mode = mode;
    }

    async _onFileInputChange(ev: Event): Promise<void> {
        const input = ev.target;
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('knowledge-import-modal: file input required');
        }
        const files = input.files === null ? [] : Array.from(input.files);
        input.value = '';
        await this._uploadFilesArray(files);
    }

    async _uploadFilesArray(rawFiles: unknown): Promise<void> {
        if (!Array.isArray(rawFiles) || rawFiles.length === 0) {
            return;
        }
        this._uploading = true;
        const next = [...this._files];
        for (const file of rawFiles) {
            if (!(file instanceof File)) {
                throw new Error('knowledge-import-modal: file required');
            }
            const spec = buildPlatformAuxiliaryFileCreateSpecJson({
                retentionKind: 'crm_knowledge_import',
            });
            const result = anyRecord(await this._fileUpload.run({ file, spec }));
            if (!result || typeof result.file_id !== 'string') {
                this._uploading = false;
                throw new Error('CRMKnowledgeImportModal: upload returned no file_id');
            }
            next.push({
                file_id: result.file_id,
                original_name: typeof result.original_name === 'string' && result.original_name.length > 0
                    ? result.original_name
                    : (typeof file.name === 'string' && file.name.length > 0 ? file.name : result.file_id),
                content_type: typeof result.content_type === 'string'
                    ? result.content_type
                    : (typeof file.type === 'string' ? file.type : ''),
            });
        }
        this._files = next;
        this._uploading = false;
    }

    _removeFile(index: number): void {
        const next = [...this._files];
        next.splice(index, 1);
        this._files = next;
    }

    _onDragEnter(ev: Event) {
        ev.preventDefault();
        this._dropzoneActive = true;
    }

    _onDragOver(ev: Event) {
        ev.preventDefault();
        const dt = dragEvent(ev).dataTransfer;
        if (dt !== null) {
            dt.dropEffect = 'copy';
        }
    }

    _onDragLeave(ev: Event) {
        ev.preventDefault();
        const zone = ev.currentTarget;
        const rel = dragEvent(ev).relatedTarget;
        if (rel instanceof Node && zone instanceof HTMLElement && zone.contains(rel)) return;
        this._dropzoneActive = false;
    }

    async _onDrop(ev: Event): Promise<void> {
        ev.preventDefault();
        this._dropzoneActive = false;
        const dt = dragEvent(ev).dataTransfer;
        const raw = dt === null ? [] : Array.from(dt.files);
        await this._uploadFilesArray(raw);
    }

    _openFilePicker() {
        const input = this.shadowRoot?.querySelector('input.ki-file-input');
        if (input instanceof HTMLInputElement) {
            input.click();
        }
    }

    _onPasteTextFieldChange(e: CustomEvent) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('CRMKnowledgeImportModal: paste field expects change detail.value string');
        }
        this._pasteText = e.detail.value;
    }

    _onChunkMaxCharsFieldChange(e: CustomEvent) {
        if (!e.detail || e.detail.value === null || typeof e.detail.value !== 'number') {
            throw new Error('CRMKnowledgeImportModal: chunk field expects numeric change detail.value');
        }
        this._setChunkMaxChars(String(e.detail.value));
    }

    _setSplitByHeadings(value: unknown): void {
        this._splitByHeadings = Boolean(value);
    }

    _setChunkMaxChars(raw: unknown): void {
        const n = Number(raw);
        if (!Number.isFinite(n)) {
            throw new Error('CRMKnowledgeImportModal._setChunkMaxChars: NaN');
        }
        const clamped = Math.max(CHUNK_MIN, Math.min(CHUNK_MAX, Math.trunc(n)));
        this._chunkMaxChars = clamped;
    }

    _hasSource(): boolean {
        const text = this._pasteText.trim();
        return this._files.length > 0 || text.length > 0;
    }

    _canProceed(): boolean {
        if (this._step === 0) return this._mode === 'graph' || this._mode === 'notes_only';
        if (this._step === 1) return true;
        if (this._step === 2) {
            if (this._uploading) return false;
            if (!this._hasSource()) return false;
            if (this._pasteText.length > MAX_INLINE_TEXT) return false;
            return true;
        }
        if (this._step === 3) {
            return this._chunkMaxChars >= CHUNK_MIN && this._chunkMaxChars <= CHUNK_MAX;
        }
        return true;
    }

    _stepNext() {
        if (!this._canProceed()) return;
        if (this._step < STEP_KEYS.length - 1) {
            this._step += 1;
        }
    }

    _stepBack() {
        if (this._step > 0) this._step -= 1;
    }

    _buildSourcePart(): Record<string, unknown> {
        const part: Record<string, unknown> = {};
        const text = this._pasteText.trim();
        if (text.length > 0) {
            part.source_text = this._pasteText;
        }
        if (this._files.length > 0) {
            part.source_file_ids = this._files.map((f) => f.file_id);
        }
        return part;
    }

    async _start() {
        const namespace = this._currentNamespace();
        if (typeof namespace !== 'string' || namespace.length === 0) {
            throw new Error('CRMKnowledgeImportModal._start: namespace must be selected');
        }
        if (!this._hasSource()) {
            throw new Error('CRMKnowledgeImportModal._start: source required');
        }
        this._starting = true;
        const payload = {
            namespace,
            mode: this._mode,
            extract_entity_types: this._selectedTypeIds.length > 0 ? this._selectedTypeIds : null,
            split_by_headings: this._splitByHeadings,
            chunk_max_chars: this._chunkMaxChars,
            ...this._buildSourcePart(),
        };
        this._startImport.run(payload);
        this._starting = false;
    }

    _renderStepMode(): TemplateResult {
        return html`
            <div class="ki-step-body">
                <p class="ki-step-desc">${this.t('knowledge_import_modal.step_mode_desc')}</p>
                <div class="ki-mode-grid">
                    ${MODES.map((m) => html`
                        <button
                            type="button"
                            class="ki-mode-card ${this._mode === m.id ? 'active' : ''}"
                            @click=${() => this._setMode(m.id)}
                        >
                            <platform-icon name=${m.icon} size="22"></platform-icon>
                            <div class="ki-mode-title">${this.t(`knowledge_import_modal.${m.titleKey}`)}</div>
                            <div class="ki-mode-desc">${this.t(`knowledge_import_modal.${m.descKey}`)}</div>
                        </button>
                    `)}
                </div>
            </div>
        `;
    }

    _renderStepTypes(): TemplateResult {
        const types = this._allowedTypes();
        return html`
            <div class="ki-step-body">
                <p class="ki-step-desc">${this.t('knowledge_import_modal.step_types_desc')}</p>
                ${types.length === 0
                    ? html`<div class="ki-empty">${this.t('knowledge_import_modal.types_empty')}</div>`
                    : html`
                        <div class="ki-types-grid">
                            ${types.map((t: Record<string, any>) => {
                                const selected = this._selectedTypeIds.includes(t.type_id);
                                return html`
                                    <button
                                        type="button"
                                        class="ki-type-card ${selected ? 'selected' : ''}"
                                        aria-pressed=${selected ? 'true' : 'false'}
                                        @click=${() => this._toggleType(t.type_id)}
                                    >
                                        <span class="ki-type-check">
                                            ${selected ? html`<platform-icon name="check" size="12"></platform-icon>` : ''}
                                        </span>
                                        <platform-icon name=${typeof t.icon === 'string' && t.icon.length > 0 ? t.icon : 'box'} size="20"></platform-icon>
                                        <span class="ki-type-name">${t.name}</span>
                                    </button>
                                `;
                            })}
                        </div>
                    `}
                <div class="ki-hint">${this.t('knowledge_import_modal.types_hint_all')}</div>
            </div>
        `;
    }

    _renderStepSource(): TemplateResult {
        const textOver = this._pasteText.length > MAX_INLINE_TEXT;
        return html`
            <div class="ki-step-body">
                <p class="ki-step-desc">${this.t('knowledge_import_modal.step_source_desc')}</p>
                <div
                    class="ki-dropzone ${this._dropzoneActive ? 'active' : ''}"
                    @click=${() => this._openFilePicker()}
                    @dragenter=${this._onDragEnter}
                    @dragover=${this._onDragOver}
                    @dragleave=${this._onDragLeave}
                    @drop=${this._onDrop}
                >
                    <input
                        type="file"
                        class="ki-file-input"
                        multiple
                        @change=${this._onFileInputChange}
                    />
                    <platform-icon name="cloud" size="28"></platform-icon>
                    <div class="ki-dropzone-label">${this.t('knowledge_import_modal.dropzone_label')}</div>
                    <div class="ki-dropzone-hint">${this.t('knowledge_import_modal.dropzone_hint')}</div>
                </div>

                ${this._uploading
                    ? html`<div class="ki-uploading">${this.t('knowledge_import_modal.uploading')}</div>`
                    : ''}

                ${this._files.length > 0
                    ? html`
                        <div class="ki-files-list">
                            ${this._files.map((f: { file_id: string; original_name: string; content_type: string }, idx: number) => html`
                                <div class="ki-file-row">
                                    <platform-icon
                                        file-icon
                                        name=${resolveFileIconKey(f.original_name, f.content_type)}
                                        size="24"
                                    ></platform-icon>
                                    <span class="ki-file-name">${f.original_name}</span>
                                    <button
                                        type="button"
                                        class="ki-file-remove"
                                        title=${this.t('knowledge_import_modal.remove_file')}
                                        @click=${() => this._removeFile(idx)}
                                    >
                                        <platform-icon name="x" size="14"></platform-icon>
                                    </button>
                                </div>
                            `)}
                        </div>
                    `
                    : ''}

                <platform-field
                    type="text"
                    mode="edit"
                    label=${this.t('knowledge_import_modal.paste_label')}
                    placeholder=${this.t('knowledge_import_modal.paste_placeholder')}
                    .value=${this._pasteText}
                    @change=${this._onPasteTextFieldChange}
                ></platform-field>
                <div class="ki-hint ${textOver ? 'ki-hint--err' : ''}">
                    ${this.t('knowledge_import_modal.paste_count', {
                        len: String(this._pasteText.length),
                        max: String(MAX_INLINE_TEXT),
                    })}
                </div>
            </div>
        `;
    }

    _renderStepSettings(): TemplateResult {
        return html`
            <div class="ki-step-body">
                <p class="ki-step-desc">${this.t('knowledge_import_modal.step_settings_desc')}</p>
                <div class="ki-row">
                    <div class="ki-row-text">
                        <div class="ki-row-title">${this.t('knowledge_import_modal.split_title')}</div>
                        <div class="ki-row-desc">${this.t('knowledge_import_modal.split_desc')}</div>
                    </div>
                    <platform-switch
                        .checked=${this._splitByHeadings}
                        @change=${(e: Event) => {
                            if (!(e instanceof CustomEvent) || !isPlainRecord(e.detail) || typeof e.detail.value !== 'boolean') {
                                throw new Error('knowledge-import-modal: split switch expects detail.value boolean');
                            }
                            this._setSplitByHeadings(e.detail.value);
                        }}
                    ></platform-switch>
                </div>
                <div class="ki-row">
                    <div class="ki-row-text">
                        <div class="ki-row-title">${this.t('knowledge_import_modal.chunk_title')}</div>
                        <div class="ki-row-desc">${this.t('knowledge_import_modal.chunk_desc', {
                            min: String(CHUNK_MIN),
                            max: String(CHUNK_MAX),
                        })}</div>
                    </div>
                    <platform-field
                        type="integer"
                        mode="edit"
                        label=""
                        placeholder=""
                        .value=${this._chunkMaxChars}
                        @change=${this._onChunkMaxCharsFieldChange}
                    ></platform-field>
                </div>
            </div>
        `;
    }

    _renderStepSummary(): TemplateResult {
        const namespace = this._currentNamespace();
        const types = this._allowedTypes();
        const typeLabels = this._selectedTypeIds.length === 0
            ? this.t('knowledge_import_modal.all_types')
            : this._selectedTypeIds.map((id: string) => {
                const t = types.find((x: Record<string, any>) => x.type_id === id);
                return t ? t.name : id;
            }).join(', ');
        const modeLabel = this._mode === 'graph'
            ? this.t('knowledge_import_modal.mode_graph_title')
            : this.t('knowledge_import_modal.mode_notes_title');
        return html`
            <div class="ki-step-body">
                <div class="ki-summary-grid">
                    <div class="ki-summary-card">
                        <div class="ki-summary-label">${this.t('knowledge_import_modal.summary_namespace')}</div>
                        <div class="ki-summary-value">${namespace}</div>
                    </div>
                    <div class="ki-summary-card">
                        <div class="ki-summary-label">${this.t('knowledge_import_modal.summary_mode')}</div>
                        <div class="ki-summary-value">${modeLabel}</div>
                    </div>
                    <div class="ki-summary-card ki-summary-card--wide">
                        <div class="ki-summary-label">${this.t('knowledge_import_modal.summary_types')}</div>
                        <div class="ki-summary-value">${typeLabels}</div>
                    </div>
                    <div class="ki-summary-card">
                        <div class="ki-summary-label">${this.t('knowledge_import_modal.summary_files')}</div>
                        <div class="ki-summary-value">${this._files.length}</div>
                    </div>
                    <div class="ki-summary-card">
                        <div class="ki-summary-label">${this.t('knowledge_import_modal.summary_text')}</div>
                        <div class="ki-summary-value">${this._pasteText.trim().length > 0 ? this.t('knowledge_import_modal.yes') : this.t('knowledge_import_modal.no')}</div>
                    </div>
                    <div class="ki-summary-card">
                        <div class="ki-summary-label">${this.t('knowledge_import_modal.summary_split')}</div>
                        <div class="ki-summary-value">${this._splitByHeadings ? this.t('knowledge_import_modal.yes') : this.t('knowledge_import_modal.no')}</div>
                    </div>
                    <div class="ki-summary-card">
                        <div class="ki-summary-label">${this.t('knowledge_import_modal.summary_chunk')}</div>
                        <div class="ki-summary-value">${this._chunkMaxChars}</div>
                    </div>
                </div>
            </div>
        `;
    }

    _renderStepBody(): TemplateResult {
        switch (this._step) {
            case 0: return this._renderStepMode();
            case 1: return this._renderStepTypes();
            case 2: return this._renderStepSource();
            case 3: return this._renderStepSettings();
            case 4: return this._renderStepSummary();
            default: throw new Error(`CRMKnowledgeImportModal: unknown step ${this._step}`);
        }
    }

    override renderHeader() {
        const titleKey = `knowledge_import_modal.${STEP_KEYS[this._step]}_title`;
        return `${this.t('knowledge_import_modal.header')} — ${this.t(titleKey)}`;
    }

    override renderBody() {
        if (!this._hasNamespace()) {
            return html`
                <div class="ki-empty">${this.t('knowledge_import_modal.no_namespace_warning')}</div>
            `;
        }
        return html`
            <div class="ki-steps">
                ${STEP_KEYS.map((key, idx) => html`
                    <div class="ki-step-pill ${idx === this._step ? 'active' : ''} ${idx < this._step ? 'done' : ''}">
                        <span class="ki-step-num">${idx + 1}</span>
                        <span>${this.t(`knowledge_import_modal.${key}_title`)}</span>
                    </div>
                `)}
            </div>
            ${this._renderStepBody()}
        `;
    }

    override renderFooter() {
        if (!this._hasNamespace()) {
            return html`
                <div class="ki-footer-row">
                    <div class="ki-footer-spacer"></div>
                    <button type="button" class="ki-btn ki-btn--ghost" @click=${() => this.close()}>
                        ${this.t('knowledge_import_modal.close')}
                    </button>
                </div>
            `;
        }
        const isLast = this._step === STEP_KEYS.length - 1;
        const canProceed = this._canProceed();
        return html`
            <div class="ki-footer-row">
                <button
                    type="button"
                    class="ki-btn ki-btn--ghost"
                    ?disabled=${this._step === 0}
                    @click=${() => this._stepBack()}
                >
                    <platform-icon name="arrow-left" size="14"></platform-icon>
                    ${this.t('knowledge_import_modal.back')}
                </button>
                <div class="ki-footer-spacer"></div>
                ${isLast
                    ? html`
                        <button
                            type="button"
                            class="ki-btn ki-btn--primary"
                            ?disabled=${this._starting || this._startImport.busy || !this._hasNamespace()}
                            @click=${() => this._start()}
                        >
                            <platform-icon name="play" size="14"></platform-icon>
                            ${this._starting || this._startImport.busy
                                ? this.t('knowledge_import_modal.starting')
                                : this.t('knowledge_import_modal.start')}
                        </button>
                    `
                    : html`
                        <button
                            type="button"
                            class="ki-btn ki-btn--primary"
                            ?disabled=${!canProceed}
                            @click=${() => this._stepNext()}
                        >
                            ${this.t('knowledge_import_modal.next')}
                            <platform-icon name="arrow-right" size="14"></platform-icon>
                        </button>
                    `}
            </div>
        `;
    }
}

customElements.define('crm-knowledge-import-modal', CRMKnowledgeImportModal);
registerModalKind(CRMKnowledgeImportModal.modalKind, 'crm-knowledge-import-modal');

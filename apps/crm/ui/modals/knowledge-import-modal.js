/**
 * CRMKnowledgeImportModal — мастер импорта знаний в выбранный namespace.
 *
 * 5-шаговый wizard поверх PlatformModal:
 *   0. mode      — graph (полный граф сущностей и связей) | notes_only (только заметки).
 *   1. types     — какие типы сущностей извлекать; пусто = все типы из namespace.
 *   2. source    — файлы (через crm/file_upload, multipart) и/или вставленный текст.
 *   3. settings  — split_by_headings, chunk_max_chars (2000..500000).
 *   4. summary   — финальный обзор и запуск crm/task_knowledge_import_start.
 *
 * Source-step:
 *   - upload файла идёт через POST /crm/api/v1/files/, который возвращает file_id;
 *     id-шники накапливаются в this._files и подставляются в payload как
 *     source_file_id (если ровно один) или source_file_ids (если несколько).
 *   - paste-area — обычный textarea, отдаётся в payload как source_text.
 *   - хотя бы один источник (файл ИЛИ текст) обязателен.
 *
 * Состояние пространства:
 *   - текущий namespace берётся из state.ui.namespace.selectionByCompany[companyId];
 *     если выбрано 'all', wizard выводит блокирующее предупреждение и не даёт
 *     запустить импорт (не понятно, в какой namespace писать).
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { resolveFileIconKey } from '@platform/lib/utils/file-icons.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-switch.js';

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

    static properties = {
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

    static styles = [
        ...PlatformModal.styles,
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

        this._entityTypes = this.useResource('crm/entity_types', { autoload: true });
        this._fileUpload = this.useOp('crm/file_upload');
        this._startImport = this.useOp('crm/task_knowledge_import_start');

        this._namespaceSel = this.select((s) => {
            const user = s.auth.user;
            if (!user || typeof user.company_id !== 'string') return null;
            const cid = user.company_id;
            const map = s.ui.namespace.selectionByCompany;
            const sel = map[cid];
            if (sel === 'all' || sel === undefined || sel === null) return null;
            return sel;
        });
    }

    connectedCallback() {
        super.connectedCallback();
        this.useEvent(this._startImport.op.events.SUCCEEDED, () => this.close());
    }

    _currentNamespace() {
        return this._namespaceSel.value;
    }

    _hasNamespace() {
        const ns = this._currentNamespace();
        return typeof ns === 'string' && ns.length > 0;
    }

    _allowedTypes() {
        return this._entityTypes.items;
    }

    _toggleType(typeId) {
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

    _setMode(mode) {
        if (mode !== 'graph' && mode !== 'notes_only') {
            throw new Error(`CRMKnowledgeImportModal._setMode: bad mode ${mode}`);
        }
        this._mode = mode;
    }

    async _onFileInputChange(ev) {
        const input = ev.target;
        const files = input.files ? Array.from(input.files) : [];
        input.value = '';
        await this._uploadFilesArray(files);
    }

    async _uploadFilesArray(rawFiles) {
        if (!Array.isArray(rawFiles) || rawFiles.length === 0) {
            return;
        }
        this._uploading = true;
        const next = [...this._files];
        for (const file of rawFiles) {
            const result = await this._awaitOp(this._fileUpload, { file });
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

    /**
     * Подписывается на SUCCEEDED/FAILED конкретной операции, выполняет run()
     * и резолвит промис результатом первого SUCCEEDED с подходящим
     * causation_id (id REQUESTED-события). FAILED → reject(Error).
     */
    _awaitOp(controller, payload) {
        return new Promise((resolve, reject) => {
            const op = controller.op;
            const requested = controller.run(payload);
            if (!requested || typeof requested.id !== 'string') {
                throw new Error('CRMKnowledgeImportModal._awaitOp: REQUESTED event missing id');
            }
            const requestedId = requested.id;
            let unsubOk = null;
            let unsubFail = null;
            unsubOk = this.bus.subscribeType(op.events.SUCCEEDED, (event) => {
                if (event.meta.causation_id !== requestedId) return;
                unsubOk();
                unsubFail();
                resolve(event.payload.result);
            });
            unsubFail = this.bus.subscribeType(op.events.FAILED, (event) => {
                if (event.meta.causation_id !== requestedId) return;
                unsubOk();
                unsubFail();
                reject(new Error(event.payload.message));
            });
        });
    }

    _removeFile(index) {
        const next = [...this._files];
        next.splice(index, 1);
        this._files = next;
    }

    _onDragEnter(ev) {
        ev.preventDefault();
        this._dropzoneActive = true;
    }

    _onDragOver(ev) {
        ev.preventDefault();
        if (ev.dataTransfer) {
            ev.dataTransfer.dropEffect = 'copy';
        }
    }

    _onDragLeave(ev) {
        ev.preventDefault();
        const zone = ev.currentTarget;
        const rel = ev.relatedTarget;
        if (rel instanceof Node && zone.contains(rel)) return;
        this._dropzoneActive = false;
    }

    async _onDrop(ev) {
        ev.preventDefault();
        this._dropzoneActive = false;
        const dt = ev.dataTransfer;
        const raw = dt && dt.files ? Array.from(dt.files) : [];
        await this._uploadFilesArray(raw);
    }

    _openFilePicker() {
        const input = this.shadowRoot?.querySelector('input.ki-file-input');
        if (input instanceof HTMLInputElement) {
            input.click();
        }
    }

    _setSplitByHeadings(value) {
        this._splitByHeadings = Boolean(value);
    }

    _setChunkMaxChars(raw) {
        const n = Number(raw);
        if (!Number.isFinite(n)) {
            throw new Error('CRMKnowledgeImportModal._setChunkMaxChars: NaN');
        }
        const clamped = Math.max(CHUNK_MIN, Math.min(CHUNK_MAX, Math.trunc(n)));
        this._chunkMaxChars = clamped;
    }

    _hasSource() {
        const text = this._pasteText.trim();
        return this._files.length > 0 || text.length > 0;
    }

    _canProceed() {
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

    _buildSourcePart() {
        const part = {};
        const text = this._pasteText.trim();
        if (text.length > 0) {
            part.source_text = this._pasteText;
        }
        if (this._files.length === 1) {
            part.source_file_id = this._files[0].file_id;
        } else if (this._files.length > 1) {
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

    _renderStepMode() {
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

    _renderStepTypes() {
        const types = this._allowedTypes();
        return html`
            <div class="ki-step-body">
                <p class="ki-step-desc">${this.t('knowledge_import_modal.step_types_desc')}</p>
                ${types.length === 0
                    ? html`<div class="ki-empty">${this.t('knowledge_import_modal.types_empty')}</div>`
                    : html`
                        <div class="ki-types-grid">
                            ${types.map((t) => {
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

    _renderStepSource() {
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
                            ${this._files.map((f, idx) => html`
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

                <label class="ki-label">${this.t('knowledge_import_modal.paste_label')}</label>
                <textarea
                    class="ki-textarea"
                    rows="6"
                    placeholder=${this.t('knowledge_import_modal.paste_placeholder')}
                    .value=${this._pasteText}
                    @input=${(e) => { this._pasteText = e.target.value; }}
                ></textarea>
                <div class="ki-hint ${textOver ? 'ki-hint--err' : ''}">
                    ${this.t('knowledge_import_modal.paste_count', {
                        len: String(this._pasteText.length),
                        max: String(MAX_INLINE_TEXT),
                    })}
                </div>
            </div>
        `;
    }

    _renderStepSettings() {
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
                        @change=${(e) => this._setSplitByHeadings(e.target.checked)}
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
                    <input
                        type="number"
                        class="ki-input ki-input--num"
                        min=${CHUNK_MIN}
                        max=${CHUNK_MAX}
                        step="1000"
                        .value=${String(this._chunkMaxChars)}
                        @change=${(e) => this._setChunkMaxChars(e.target.value)}
                    />
                </div>
            </div>
        `;
    }

    _renderStepSummary() {
        const namespace = this._currentNamespace();
        const types = this._allowedTypes();
        const typeLabels = this._selectedTypeIds.length === 0
            ? this.t('knowledge_import_modal.all_types')
            : this._selectedTypeIds.map((id) => {
                const t = types.find((x) => x.type_id === id);
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

    _renderStepBody() {
        switch (this._step) {
            case 0: return this._renderStepMode();
            case 1: return this._renderStepTypes();
            case 2: return this._renderStepSource();
            case 3: return this._renderStepSettings();
            case 4: return this._renderStepSummary();
            default: throw new Error(`CRMKnowledgeImportModal: unknown step ${this._step}`);
        }
    }

    renderHeader() {
        const titleKey = `knowledge_import_modal.${STEP_KEYS[this._step]}_title`;
        return `${this.t('knowledge_import_modal.header')} — ${this.t(titleKey)}`;
    }

    renderBody() {
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

    renderFooter() {
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

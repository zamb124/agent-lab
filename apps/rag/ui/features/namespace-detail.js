/**
 * Namespace Detail - просмотр и управление документами в namespace
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles, iconButtonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/page-header.js';

/** Значения ``IndexProfileSplitStrategy`` (``core/rag_indexing_schema``). */
const RAG_SPLIT_STRATEGIES = [
    { value: 'fixed_tokens', label: 'Фиксированные токены' },
    { value: 'semantic', label: 'Семантический' },
    { value: 'structure', label: 'По структуре' },
    { value: 'token', label: 'Токены (legacy)' },
    { value: 'sentence', label: 'По предложениям' },
    { value: 'code', label: 'Код' },
    { value: 'table', label: 'Таблицы' },
    { value: 'fast', label: 'Fast' },
];

export class NamespaceDetail extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        buttonStyles,
        iconButtonStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: var(--space-8);
            }
            
            .header-left {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .menu-btn {
                display: none;
            }
            
            @media (max-width: 767px) {
                .menu-btn {
                    display: flex;
                    width: 36px;
                    height: 36px;
                    align-items: center;
                    justify-content: center;
                    border-radius: var(--radius-lg);
                    background: var(--glass-solid-strong);
                    border: 1px solid var(--glass-border-medium);
                    color: var(--text-primary);
                    cursor: pointer;
                    flex-shrink: 0;
                }
            }
            
            .title {
                font-size: var(--text-3xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                letter-spacing: var(--tracking-tight);
            }
            
            .subtitle {
                font-size: var(--text-base);
                color: var(--text-secondary);
                margin-top: var(--space-1);
            }
            
            .actions {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }

            .split-select {
                min-width: 200px;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .split-select-label {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-right: var(--space-2);
            }

            .upload-settings {
                margin-bottom: var(--space-6);
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }

            .upload-settings-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }

            .upload-settings-hint {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-4);
                line-height: 1.5;
            }

            .upload-settings-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-3);
                align-items: end;
            }

            .upload-field label {
                display: block;
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-1);
            }

            .upload-field input,
            .upload-field select {
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-medium);
                color: var(--text-primary);
                font-size: var(--text-sm);
            }

            .upload-settings-actions {
                margin-top: var(--space-4);
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
            }
            
            .documents-list {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            
            .document-card {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: all var(--duration-fast);
            }
            
            .document-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }
            
            .document-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: var(--space-2);
            }
            
            .document-name {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .document-meta {
                display: flex;
                gap: var(--space-4);
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .document-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .empty {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: var(--space-12);
                text-align: center;
            }
            
            .empty-icon {
                width: 80px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: var(--space-4);
                opacity: 0.3;
                color: var(--text-tertiary);
            }
            
            .empty-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }
            
            .empty-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            input[type="file"] {
                display: none;
            }
            
            .drop-zone {
                margin-top: var(--space-6);
                padding: var(--space-12);
                border: 2px dashed var(--glass-border-medium);
                border-radius: var(--radius-xl);
                background: var(--glass-solid-subtle);
                text-align: center;
                transition: all var(--duration-fast);
                cursor: pointer;
            }
            
            .drop-zone:hover,
            .drop-zone.drag-over {
                border-color: var(--accent);
                background: var(--glass-solid-medium);
            }
            
            .drop-zone-content {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: var(--space-3);
            }
            
            .drop-zone-icon {
                width: 64px;
                height: 64px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-full);
                background: var(--glass-solid-medium);
                color: var(--accent);
            }
            
            .drop-zone-icon platform-icon {
                transition: transform var(--duration-fast);
            }
            
            .drop-zone:hover .drop-zone-icon platform-icon {
                transform: scale(1.1);
            }
            
            .drop-zone-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            
            .drop-zone-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            
            .loading-spinner {
                width: 48px;
                height: 48px;
                border: 4px solid var(--glass-border-subtle);
                border-top: 4px solid var(--accent);
                border-radius: 50%;
                animation: spin 1s linear infinite;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            .doc-status-badge {
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                padding: 2px var(--space-2);
                border-radius: var(--radius-md);
                text-transform: uppercase;
                letter-spacing: 0.02em;
            }

            .doc-status-badge--completed {
                background: color-mix(in srgb, var(--success) 18%, transparent);
                color: var(--success);
            }

            .doc-status-badge--processing,
            .doc-status-badge--pending {
                background: color-mix(in srgb, var(--warning) 18%, transparent);
                color: var(--warning);
            }

            .doc-status-badge--failed {
                background: color-mix(in srgb, var(--danger) 18%, transparent);
                color: var(--danger);
            }

            .doc-status-badge--pending {
                background: color-mix(in srgb, var(--warning) 18%, transparent);
                color: var(--warning);
            }

            .stats-bar {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-4);
                font-size: var(--text-sm);
                color: var(--text-secondary);
                margin-bottom: var(--space-4);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
            }

            .stats-bar strong {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
            }

            .status-legend {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-4);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-bottom: var(--space-4);
            }

            .status-legend span {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }

            .legend-dot {
                width: 8px;
                height: 8px;
                border-radius: var(--radius-full);
                display: inline-block;
            }

            .legend-dot--completed { background: var(--success); }
            .legend-dot--processing { background: var(--warning); }
            .legend-dot--pending { background: var(--warning); opacity: 0.7; }
            .legend-dot--failed { background: var(--danger); }

            .doc-detail-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
                gap: var(--space-2);
                margin-top: var(--space-3);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }

            .doc-detail-grid dt {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin: 0;
            }

            .doc-detail-grid dd {
                margin: 0;
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }

            .doc-error {
                margin-top: var(--space-2);
                font-size: var(--text-sm);
                color: var(--danger);
            }

        `
    ];
    
    constructor() {
        super();
        this.state = this.use((s) => ({
            currentNamespaceId: s.namespaces.currentId,
            namespaces: s.namespaces.list,
            documents: s.namespaces.documents,
            documentSummaries: s.namespaces.documentSummaries,
            loading: s.loading,
            uploading: s.uploading,
            uploadIdx: s.uploadIndexProfileDefaults,
        }));
        this._dragOver = false;
    }
    
    connectedCallback() {
        super.connectedCallback();
        this._loadDocuments();
    }
    
    async _loadDocuments() {
        const { currentNamespaceId } = this.state.value;
        if (!currentNamespaceId) return;
        
        const ragApi = this.services.get('ragApi');
        await RagStore.loadDocuments(ragApi, currentNamespaceId);
    }
    
    _goBack() {
        RagStore.setCurrentView('namespaces');
    }
    
    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }
    
    _getCurrentNamespace() {
        const { currentNamespaceId, namespaces } = this.state.value;
        return namespaces.find(
            (ns) => (ns.namespace_id ?? ns.name) === currentNamespaceId,
        );
    }

    _namespaceDocumentsSubtitle(namespace, docCount) {
        const c = namespace?.document_status_counts;
        const bits = [];
        if (c && typeof c === 'object') {
            if (c.completed > 0) bits.push(`готово ${c.completed}`);
            if (c.processing > 0) bits.push(`в работе ${c.processing}`);
            if (c.pending > 0) bits.push(`ожидают ${c.pending}`);
            if (c.failed > 0) bits.push(`ошибки ${c.failed}`);
        }
        const tail = bits.length ? ` · ${bits.join(', ')}` : '';
        return `${docCount} документов${tail}`;
    }

    _docCreatedLabel(doc) {
        const raw = doc.created_at || doc.metadata?.created_at;
        if (!raw) return '';
        try {
            return new Date(raw).toLocaleDateString();
        } catch {
            return '';
        }
    }

    _docStatusBadgeClass(status) {
        const s = String(status || 'processing').toLowerCase();
        if (s === 'completed') return 'doc-status-badge doc-status-badge--completed';
        if (s === 'failed') return 'doc-status-badge doc-status-badge--failed';
        if (s === 'pending') return 'doc-status-badge doc-status-badge--pending';
        return 'doc-status-badge doc-status-badge--processing';
    }

    _statusLabelRu(status) {
        const s = String(status || '').toLowerCase();
        const map = {
            completed: 'готово',
            processing: 'обработка',
            pending: 'в очереди',
            failed: 'ошибка',
        };
        return map[s] || s;
    }

    _formatSplit(split) {
        if (!split || typeof split !== 'object') return '—';
        const strategy = split.strategy != null ? String(split.strategy) : '';
        const parts = [strategy];
        if (split.chunk_size != null) parts.push(`размер ${split.chunk_size}`);
        if (split.chunk_overlap != null) parts.push(`перекрытие ${split.chunk_overlap}`);
        return parts.filter(Boolean).join(' · ') || '—';
    }

    _numberOrDash(value) {
        if (value === null || value === undefined) return '—';
        const n = Number(value);
        if (Number.isNaN(n)) return '—';
        return String(n);
    }

    _handleFileSelect(e) {
        const file = e.target.files[0];
        if (!file) return;
        
        this._uploadFile(file);
    }
    
    _uploadMetadata() {
        const d = this.state.value.uploadIdx;
        if (!d || typeof d !== 'object') {
            throw new Error('Нет сохранённых параметров индексации');
        }

        const chunkSize = Number(d.split.chunk_size);
        const chunkOverlap = Number(d.split.chunk_overlap);
        if (!Number.isInteger(chunkSize) || chunkSize < 1) {
            throw new Error('Размер чанка (chunk_size) должен быть целым числом не меньше 1');
        }
        if (!Number.isInteger(chunkOverlap) || chunkOverlap < 0) {
            throw new Error('Перекрытие (chunk_overlap) должно быть целым числом не меньше 0');
        }

        const langParts = String(d.parsing.languages || '')
            .split(/[,;\s]+/)
            .map((x) => x.trim())
            .filter(Boolean);
        if (langParts.length === 0) {
            throw new Error('Укажите хотя бы один язык парсинга (поле «Языки парсинга»)');
        }

        const split = {
            strategy: d.split.strategy,
            chunk_size: chunkSize,
            chunk_overlap: chunkOverlap,
            chonkie_code_language: String(d.split.chonkie_code_language || 'auto').trim() || 'auto',
        };
        const delim = String(d.split.chonkie_fast_delimiters || '').trim();
        if (delim) {
            split.chonkie_fast_delimiters = delim;
        }

        const parsing = {
            engine: d.parsing.engine,
            languages: langParts,
        };

        return {
            index_profile_config: { split, parsing },
        };
    }

    _patchUploadSplit(field, value) {
        RagStore.patchUploadIndexProfileDefaults({ split: { [field]: value } });
    }

    _onUploadStrategyChange(e) {
        this._patchUploadSplit('strategy', e.target.value);
    }

    _onUploadChunkSizeInput(e) {
        const v = parseInt(e.target.value, 10);
        if (e.target.value.trim() === '' || Number.isNaN(v)) {
            return;
        }
        this._patchUploadSplit('chunk_size', v);
    }

    _onUploadChunkOverlapInput(e) {
        const v = parseInt(e.target.value, 10);
        if (e.target.value.trim() === '' || Number.isNaN(v)) {
            return;
        }
        this._patchUploadSplit('chunk_overlap', v);
    }

    _onUploadChonkieLangInput(e) {
        this._patchUploadSplit('chonkie_code_language', e.target.value);
    }

    _onUploadFastDelimInput(e) {
        this._patchUploadSplit('chonkie_fast_delimiters', e.target.value);
    }

    _onUploadParsingEngineChange(e) {
        RagStore.patchUploadIndexProfileDefaults({ parsing: { engine: e.target.value } });
    }

    _onUploadLanguagesInput(e) {
        RagStore.patchUploadIndexProfileDefaults({ parsing: { languages: e.target.value } });
    }

    _resetUploadDefaults() {
        RagStore.resetUploadIndexProfileDefaults();
    }

    _renderUploadSettings(uploading) {
        const { uploadIdx } = this.state.value;
        const split = uploadIdx?.split;
        const parsing = uploadIdx?.parsing;
        if (!split || !parsing) {
            return html``;
        }

        return html`
            <section class="upload-settings" aria-label="Параметры индексации при загрузке">
                <div class="upload-settings-title">Параметры индексации</div>
                <p class="upload-settings-hint">
                    Значения сохраняются в браузере и уходят в
                    <code>metadata.index_profile_config</code> при каждой загрузке. Сервер мержит их с
                    <code>rag.document_indexing</code>.
                </p>
                <div class="upload-settings-grid">
                    <div class="upload-field">
                        <label for="rag-upload-strategy">Стратегия нарезки</label>
                        <select
                            id="rag-upload-strategy"
                            class="split-select"
                            style="width:100%;min-width:0;"
                            .value=${split.strategy}
                            @change=${this._onUploadStrategyChange}
                            ?disabled=${uploading}
                        >
                            ${RAG_SPLIT_STRATEGIES.map(
                                (o) => html`<option value=${o.value}>${o.label}</option>`,
                            )}
                        </select>
                    </div>
                    <div class="upload-field">
                        <label for="rag-chunk-size">Размер чанка (токены)</label>
                        <input
                            id="rag-chunk-size"
                            type="number"
                            min="1"
                            step="1"
                            .value=${String(split.chunk_size)}
                            @change=${this._onUploadChunkSizeInput}
                            ?disabled=${uploading}
                        />
                    </div>
                    <div class="upload-field">
                        <label for="rag-chunk-overlap">Перекрытие</label>
                        <input
                            id="rag-chunk-overlap"
                            type="number"
                            min="0"
                            step="1"
                            .value=${String(split.chunk_overlap)}
                            @change=${this._onUploadChunkOverlapInput}
                            ?disabled=${uploading}
                        />
                    </div>
                    <div class="upload-field">
                        <label for="rag-chonkie-lang">Язык для CodeChunker</label>
                        <input
                            id="rag-chonkie-lang"
                            type="text"
                            autocomplete="off"
                            placeholder="auto"
                            .value=${split.chonkie_code_language ?? 'auto'}
                            @input=${this._onUploadChonkieLangInput}
                            ?disabled=${uploading}
                        />
                    </div>
                    <div class="upload-field">
                        <label for="rag-fast-delim">Разделители FastChunker (опционально)</label>
                        <input
                            id="rag-fast-delim"
                            type="text"
                            autocomplete="off"
                            placeholder="пусто — дефолт Chonkie"
                            .value=${split.chonkie_fast_delimiters ?? ''}
                            @input=${this._onUploadFastDelimInput}
                            ?disabled=${uploading}
                        />
                    </div>
                    <div class="upload-field">
                        <label for="rag-parse-engine">Движок парсинга</label>
                        <select
                            id="rag-parse-engine"
                            .value=${parsing.engine}
                            @change=${this._onUploadParsingEngineChange}
                            ?disabled=${uploading}
                        >
                            <option value="unstructured">unstructured</option>
                            <option value="marker">marker</option>
                        </select>
                    </div>
                    <div class="upload-field" style="grid-column: 1 / -1;">
                        <label for="rag-parse-langs">Языки парсинга</label>
                        <input
                            id="rag-parse-langs"
                            type="text"
                            autocomplete="off"
                            placeholder="rus, eng"
                            .value=${parsing.languages ?? ''}
                            @input=${this._onUploadLanguagesInput}
                            ?disabled=${uploading}
                        />
                    </div>
                </div>
                <div class="upload-settings-actions">
                    <button
                        type="button"
                        class="btn btn-secondary"
                        @click=${this._resetUploadDefaults}
                        ?disabled=${uploading}
                    >
                        Сбросить к умолчанию
                    </button>
                </div>
            </section>
        `;
    }

    async _uploadFile(file) {
        const { currentNamespaceId } = this.state.value;
        const ragApi = this.services.get('ragApi');
        if (!currentNamespaceId) {
            this.error('Namespace не выбран');
            return;
        }
        let metadata;
        try {
            metadata = this._uploadMetadata();
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.error(message);
            return;
        }
        try {
            await RagStore.uploadDocument(
                ragApi,
                currentNamespaceId,
                file,
                metadata,
            );
            this.success(`Файл «${file.name}» принят, идёт индексация`);
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.error(message);
        }
    }
    
    async _deleteDocument(documentId) {
        const { currentNamespaceId } = this.state.value;
        const ragApi = this.services.get('ragApi');
        
        if (!confirm('Удалить этот документ?')) return;
        
        await RagStore.deleteDocument(ragApi, currentNamespaceId, documentId);
        this.success('Документ удален');
    }
    
    _triggerFileInput() {
        const input = this.shadowRoot.querySelector('input[type="file"]');
        input?.click();
    }
    
    _handleDragOver(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = true;
        this.requestUpdate();
    }
    
    _handleDragLeave(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
        this.requestUpdate();
    }
    
    _handleDrop(e) {
        e.preventDefault();
        e.stopPropagation();
        this._dragOver = false;
        this.requestUpdate();
        
        const files = Array.from(e.dataTransfer?.files || []);
        if (files.length > 0) {
            this._uploadFile(files[0]);
        }
    }
    
    _handleDropZoneClick() {
        this._triggerFileInput();
    }
    
    render() {
        const { currentNamespaceId, documents, documentSummaries, loading, uploading } =
            this.state.value;
        const namespace = this._getCurrentNamespace();
        const namespaceDocuments = documents[currentNamespaceId] || [];
        const summary = documentSummaries[currentNamespaceId] || null;
        
        if (!namespace) {
            return html`
                <div class="empty">
                    <div class="empty-text">Namespace не найден</div>
                </div>
            `;
        }
        
        return html`
            <div class="header">
                <div class="header-left">
                    <button class="menu-btn" @click=${this._openSidebar} title="Открыть меню">
                        <platform-icon name="menu" size="20"></platform-icon>
                    </button>
                    <button class="btn-icon" @click=${this._goBack}>
                        <platform-icon name="chevron-left" size="20"></platform-icon>
                    </button>
                    <div>
                        <h1 class="title">${namespace.name}</h1>
                        <p class="subtitle">${this._namespaceDocumentsSubtitle(namespace, namespaceDocuments.length)}</p>
                    </div>
                </div>
                <div class="actions">
                    <button class="btn btn-primary" @click=${this._triggerFileInput} ?disabled=${uploading}>
                        <platform-icon name="plus" size="18"></platform-icon>
                        <span>${uploading ? 'Загрузка...' : 'Загрузить документ'}</span>
                    </button>
                </div>
            </div>

            ${this._renderUploadSettings(uploading)}
            
            <input 
                type="file" 
                @change=${this._handleFileSelect} 
                accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.ppt,.html,.htm,.txt,.md,.rst,.rtf,.odt,.csv,.tsv,.eml,.msg,.epub,.jpg,.jpeg,.png,.tiff,.bmp"
            />

            ${summary && !loading
                ? html`
                    <div class="stats-bar">
                        <span>Всего документов: <strong>${this._numberOrDash(summary.total_documents)}</strong></span>
                        <span>Всего чанков: <strong>${this._numberOrDash(summary.total_chunks)}</strong></span>
                        ${summary.status_counts
                            ? html`
                                <span>
                                    По статусам:
                                    ${Object.entries(summary.status_counts)
                                        .map(([k, v]) => `${this._statusLabelRu(k)} ${v}`)
                                        .join(' · ')}
                                </span>
                              `
                            : ''}
                    </div>
                    <div class="status-legend" aria-label="Расшифровка статусов">
                        <span><i class="legend-dot legend-dot--completed"></i> готово — в индексе</span>
                        <span><i class="legend-dot legend-dot--pending"></i> в очереди — ждёт воркер</span>
                        <span><i class="legend-dot legend-dot--processing"></i> обработка — парсинг и эмбеддинги</span>
                        <span><i class="legend-dot legend-dot--failed"></i> ошибка — см. текст ниже</span>
                    </div>
                `
                : ''}
            
            ${loading ? html`
                <div class="empty">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">Загрузка документов...</div>
                </div>
            ` : html`
                ${namespaceDocuments.length === 0 ? html`
                    <div 
                        class="drop-zone ${this._dragOver ? 'drag-over' : ''}"
                        @click=${this._handleDropZoneClick}
                        @dragover=${this._handleDragOver}
                        @dragleave=${this._handleDragLeave}
                        @drop=${this._handleDrop}
                    >
                        <div class="drop-zone-content">
                            <div class="drop-zone-icon">
                                <platform-icon name="${uploading ? 'refresh' : 'cloud'}" size="32"></platform-icon>
                            </div>
                            <div class="drop-zone-text">
                                ${uploading ? 'Загрузка документа...' : 'Перетащите файл сюда'}
                            </div>
                            <div class="drop-zone-hint">
                                или нажмите для выбора файла<br>
                                Поддерживаемые форматы: PDF, DOCX, DOC, XLSX, PPTX, HTML, TXT, MD, RTF, CSV, изображения
                            </div>
                        </div>
                    </div>
                ` : html`
                    <div class="documents-list">
                        ${namespaceDocuments.map(doc => html`
                            <div class="document-card">
                                <div class="document-header">
                                    <div>
                                        <div class="document-name">
                                            <platform-icon name="file" size="16"></platform-icon>
                                            ${doc.name || doc.document_id}
                                            <span class=${this._docStatusBadgeClass(doc.status)} title=${doc.status}
                                                >${this._statusLabelRu(doc.status)}</span
                                            >
                                        </div>
                                        <div class="document-meta">
                                            ${this._docCreatedLabel(doc)
                                                ? html`<span>Создан: ${this._docCreatedLabel(doc)}</span>`
                                                : ''}
                                            ${doc.pages ? html`<span>${doc.pages} страниц</span>` : ''}
                                        </div>
                                        <dl class="doc-detail-grid">
                                            <div>
                                                <dt>Документовых фрагментов (чанков)</dt>
                                                <dd>${this._numberOrDash(doc.chunks_count)}</dd>
                                            </div>
                                            <div>
                                                <dt>Повторных индексаций</dt>
                                                <dd>${this._numberOrDash(doc.reindex_count)}</dd>
                                            </div>
                                            <div>
                                                <dt>Успешных индексаций всего</dt>
                                                <dd>${this._numberOrDash(doc.indexing_runs)}</dd>
                                            </div>
                                            <div>
                                                <dt>Нарезка (split)</dt>
                                                <dd>${this._formatSplit(doc.split)}</dd>
                                            </div>
                                        </dl>
                                        ${doc.status === 'failed' && doc.metadata?.error_message
                                            ? html`<div class="doc-error">${doc.metadata.error_message}</div>`
                                            : ''}
                                    </div>
                                    <div class="document-actions">
                                        <button class="btn-icon danger" @click=${() => this._deleteDocument(doc.document_id)} title="Удалить">
                                            <platform-icon name="trash" size="16"></platform-icon>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        `)}
                    </div>
                `}
            `}
        `;
    }
}

customElements.define('namespace-detail', NamespaceDetail);

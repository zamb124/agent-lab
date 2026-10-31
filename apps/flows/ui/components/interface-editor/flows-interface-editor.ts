/**
 * Редактор интерфейса flow (модель Odoo Studio): слева «Добавить» / «Свойства», в центре холст
 * ``<platform-flow-ui editing>`` на реальном рендере, сверху вкладки страниц.
 *
 * Хост-контракт: ``.interfaceConfig`` (FlowUIDocument ветки), ``.flowId``, ``.branchId``;
 * ``interface-change {config}`` — коммит валидного черновика в flowConfig (без PUT).
 * ``interface-save-request`` — страница сохраняет flow после коммита Preview.
 * Черновик и история живут в slice ``flows/interface_editor``; структура меняется только командами домена.
 * Глобальные Publish/статус — в ``flows-editor-header``, не здесь.
 */

import type { OpController, SliceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buildFlowAssetFileCreateSpecJson } from '@platform/lib/utils/file-create-spec.js';
import { flowUIEditorChromeTokens } from '@platform/lib/flow-ui/editor/editor-chrome.styles.js';
import { blockElement, blockFrame, blockIdFromEvent } from '@platform/lib/flow-ui/editor/selection.js';
import { renderAlignButtons, renderSpanHandle } from '@platform/lib/flow-ui/editor/layout-handles.js';
import { BLOCK_ID_MIME, dropTargetFromEvent, hasFlowUiDrag, readDragPayload } from '@platform/lib/flow-ui/editor/drop-zones.js';
import { inlineEditKeyAction, inlineTextIsMultiline, inlineTextProperty } from '@platform/lib/flow-ui/editor/inline-text-edit.js';
import { PlatformFlowUI } from '@platform/lib/flow-ui/components/platform-flow-ui.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-empty-state.js';
import {
    CONTAINER_TYPES,
    type CatalogEntry,
    type DocumentProblem,
    type FlowUiDocument,
    blockCatalog,
    catalogEntry,
    defaultBlock,
    documentProblems,
    duplicateBlock,
    findPage,
    frozenStateFields,
    hasBlockingProblems,
    insertBlock,
    insertPage,
    locateBlock,
    moveBlock,
    paletteInsertTarget,
    removeBlock,
    removePage,
    replacePageBlocks,
    setBlockProperty,
    setPageProperty,
    statePathCatalog,
    uniqueBlockId,
    uniquePageId,
    withColumns,
    wrapInSection,
} from '../../_helpers/interface-editor-domain.js';
import { readDrafts, stableStringify, writeDraft } from './interface-editor-drafts.js';
import { interfaceEditorStyles } from './flows-interface-editor.styles.js';
import { HOST_EDITOR_EVENTS, editorFrameWidth, inlineTextControl, type InlineEdit } from '../../_helpers/interface-editor-helpers.js';
import './flows-interface-pages-tabs.js';
import './flows-interface-add-panel.js';
import './flows-interface-properties-panel.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

export class FlowsInterfaceEditor extends PlatformElement {
    private _onHostEditorEvent: (event: Event) => void;
    private _onKeyDown: (event: Event) => void;
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        interfaceConfig: { attribute: false },
        flowId: { type: String },
        branchId: { type: String },
        _schema: { state: true },
        _frame: { state: true },
        _drop: { state: true },
        _inlineEdit: { state: true },
        _menuOpen: { state: true },
    }
    declare interfaceConfig: unknown;
    declare flowId: string;
    declare branchId: string;
    declare _schema: unknown;
    declare _frame: ReturnType<typeof blockFrame>;
    declare _drop: ReturnType<typeof dropTargetFromEvent>;
    declare _inlineEdit: InlineEdit | null;
    declare _menuOpen: boolean;
;

    static override styles: CSSResultGroup = [PlatformElement.styles, flowUIEditorChromeTokens, interfaceEditorStyles];
    private _ui: ControllerFor<'flows/interface_editor'>;
    private _editor: ControllerFor<'flows/editor'>;
    private _schemaOp: OpController;
    private _assistOp: OpController;
    private _fileUpload: OpController;
    private _catalog: readonly CatalogEntry[];
    private _frozen: Set<string>;
    private _frameRaf: number;
    private _resizeObserver: ResizeObserver | null;

    constructor() {
        super();
        this.interfaceConfig = null;
        this.flowId = '';
        this.branchId = 'default';
        this._schema = null;
        this._catalog = [];
        this._frozen = new Set<string>();
        this._frame = null;
        this._drop = null;
        this._inlineEdit = null;
        this._menuOpen = false;
        this._ui = this.useSlice('flows/interface_editor');
        this._editor = this.useOp('flows/editor');
        this._schemaOp = this.useOp('flows/flow_ui_schema');
        this._assistOp = this.useOp('flows/flow_ui_assist');
        this._fileUpload = this.useOp('platform/file_create');
        this._frameRaf = 0;
        this._resizeObserver = null;
        this._onKeyDown = (event: Event) => {
            if (!(event instanceof KeyboardEvent)) {
                throw new Error('flows-interface-editor: keydown must be a KeyboardEvent');
            }
            this._handleKeydown(event);
        };
        this._onHostEditorEvent = (event: Event) => {
            if (!(event instanceof CustomEvent)) {
                throw new Error('flows-interface-editor: host editor event must be a CustomEvent');
            }
            this._handleHostEditorEvent(event);
        };
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.tabIndex = 0;
        this.addEventListener('keydown', this._onKeyDown);
        for (const name of HOST_EDITOR_EVENTS) this.addEventListener(name, this._onHostEditorEvent);
        void this._loadSchema();
    }

    override disconnectedCallback(): void {
        this.removeEventListener('keydown', this._onKeyDown);
        for (const name of HOST_EDITOR_EVENTS) this.removeEventListener(name, this._onHostEditorEvent);
        if (this._resizeObserver) this._resizeObserver.disconnect();
        cancelAnimationFrame(this._frameRaf);
        super.disconnectedCallback();
    }

    async _loadSchema() {
        const schema = await this._schemaOp.run(null);
        if (schema === null) return;
        this._catalog = blockCatalog(schema);
        this._frozen = frozenStateFields(schema);
        this._schema = schema;
    }

    override firstUpdated() {
        this._resizeObserver = new ResizeObserver(() => this._scheduleFrame());
        const canvas = this.renderRoot.querySelector('.canvas');
        if (canvas) this._resizeObserver.observe(canvas);
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('interfaceConfig') || changed.has('flowId') || changed.has('branchId')) this._openDocument();
        this._syncCanvasPage();
        this._scheduleFrame();
        this._syncProblems();
    }

    /** Активная вкладка страницы — источник правды для страницы холста. */
    _syncCanvasPage() {
        const flowUi = this._flowUi();
        const pageId = (this._ui).value.pageId;
        if (flowUi === null || this._ui.value.preview || typeof pageId !== 'string' || pageId === '' || this._page === null) return;
        if (flowUi.store.document === null || flowUi.store.pageId === pageId || !flowUi.store.page(pageId)) return;
        flowUi.navigate(pageId);
    }

    // --- Документ ---------------------------------------------------------------------------

    get _documentKey() {
        return `${this.flowId}:${this.branchId}`;
    }

    get _draft(): FlowUiDocument | null {
        const ui = this._ui.value;
        const history = ui.history;
        if (history == null || ui.documentKey !== this._documentKey) return null;
        return history.present;
    }

    _requireDraft(): FlowUiDocument {
        const draft = this._draft;
        if (draft === null) throw new Error('flows-interface-editor: draft required');
        return draft;
    }

    get _page() {
        const draft = this._draft;
        const pageId = this._ui.value.pageId;
        if (draft === null || typeof pageId !== 'string' || pageId === '') return null;
        return findPage(draft, pageId);
    }

    _requirePage() {
        const page = this._page;
        if (page === null) throw new Error('flows-interface-editor: page required');
        return page;
    }

    _requirePageId() {
        const pageId = this._ui.value.pageId;
        if (typeof pageId !== 'string' || pageId === '') throw new Error('flows-interface-editor: pageId required');
        return pageId;
    }

    get _sampleState() {
        const preview = this._editor.state.previewExecutionState;
        return preview && typeof preview === 'object' ? preview : {};
    }

    _openDocument() {
        if (this.flowId === '' || this.interfaceConfig === null) return;
        if ((this._ui).value.documentKey === this._documentKey) return;
        const drafts = readDrafts();
        const stored = Object.hasOwn(drafts, this._documentKey) ? drafts[this._documentKey] : null;
        (this._ui.openDocument)({ documentKey: this._documentKey, document: stored ?? structuredClone(this.interfaceConfig) });
    }

    _commit(document: unknown, coalesceKey: string | null = null) {
        (this._ui.commitDocument({ document, coalesceKey }));
        writeDraft(this._documentKey, document);
    }

    get _dirty() {
        const draft = this._draft;
        return draft !== null && this.interfaceConfig !== null && stableStringify(draft) !== stableStringify(this.interfaceConfig);
    }

    get _problems() {
        const draft = this._draft;
        return draft === null || this._schema === null ? [] : documentProblems(draft, this._catalog, this._frozen);
    }

    _syncProblems() {
        const problems = this._problems;
        const current = (this._ui).value.problems;
        if (stableStringify(current) === stableStringify(problems)) return;
        (this._ui.setProblems({ problems }));
    }

    _handleHostEditorEvent(event: CustomEvent) {
        const type = event.type;
        if (type === 'editor-undo') this.undo();
        else if (type === 'editor-redo') this.redo();
        else if (type === 'editor-viewport') this.setViewport(event.detail && event.detail.viewport);
        else if (type === 'editor-preview') void this.setCanvasPreview(Boolean(event.detail && event.detail.preview));
        else if (type === 'editor-templates') this.openTemplates();
        else if (type === 'editor-assist') {
            const instruction = event.detail && event.detail.instruction;
            const scope = event.detail && event.detail.scope;
            void this.assist(instruction, scope);
        }
        else throw new Error(`interface editor: unknown host event ${type}`);
    }

    undo() {
        if ((this._ui).value.history === null) return;
        (this._ui.undo(null));
    }

    redo() {
        if ((this._ui).value.history === null) return;
        (this._ui.redo(null));
    }

    setViewport(viewport: unknown) {
        if ((this._ui).value.history === null) return;
        if (typeof viewport !== 'string') return;
        (this._ui.setViewport({ viewport }));
    }

    openTemplates() {
        this.openModal('flows.interface_template', { onApply: (document: unknown) => this._applyTemplate(document) });
    }

    focusProblem(problem: DocumentProblem) {
        this._focusProblem(problem);
    }

    _labels() {
        return {
            tab: this.t('interface_editor.default_tab'),
            option: this.t('interface_editor.default_option'),
            text: (type: string, name: string) => this.t(`interface_editor.default_text_${type}_${name}`),
        };
    }

    // --- Команды ------------------------------------------------------------------------------

    _insert(type: string, containerKey: string, index: number, columns: number | null = null) {
        const page = this._requirePage();
        const entry = catalogEntry(this._catalog, type);
        const blockId = uniqueBlockId(page, type);
        const block = columns === null ? defaultBlock(entry, blockId, this._labels()) : withColumns(entry, blockId, columns, this._labels());
        this._commit(insertBlock(this._requireDraft(), page.page_id, containerKey, index, block));
        (this._ui.selectBlock({ blockId }));
        if (CONTAINER_TYPES.includes(type)) (this._ui.setSidebarTab({ tab: 'add' }));
    }

    _setProperty(blockId: string, property: string, value: unknown) {
        const pageId = this._requirePageId();
        this._commit(setBlockProperty(this._requireDraft(), pageId, blockId, property, value), `${blockId}:${property}`);
        if (property === 'block_id') (this._ui.selectBlock({ blockId: value }));
    }

    async _uploadBlockImage(detail: unknown) {
        if (!isPlainRecord(detail)) throw new Error('flows-interface-editor: image-upload detail required');
        const { blockId, property, file } = detail;
        if (typeof blockId !== 'string' || blockId === '') throw new Error('flows-interface-editor: image-upload blockId required');
        if (typeof property !== 'string' || property === '') throw new Error('flows-interface-editor: image-upload property required');
        if (!(file instanceof File)) throw new Error('flows-interface-editor: image-upload file required');
        if (typeof this.flowId !== 'string' || this.flowId === '') throw new Error('flows-interface-editor: flowId required for image upload');
        const spec = buildFlowAssetFileCreateSpecJson({ flowId: this.flowId, isPublic: true });
        const result = await this._fileUpload.run({ file, spec });
        if (!isPlainRecord(result) || typeof result.url !== 'string' || result.url === '') {
            this.toast('interface_editor.image_upload_failed', { type: 'error' });
            return;
        }
        this._setProperty(blockId, property, result.url);
    }

    _remove(blockId: string) {
        this._commit(removeBlock(this._requireDraft(), this._requirePageId(), blockId));
        (this._ui.selectBlock({ blockId: '' }));
    }

    _moveWithin(blockId: string, delta: number) {
        const page = this._requirePage();
        const { containerKey, index } = locateBlock(page, blockId);
        const target = index + delta;
        if (target < 0) return;
        this._commit(moveBlock(this._requireDraft(), page.page_id, blockId, containerKey, delta > 0 ? target + 1 : target));
    }

    _blockMenuAction(blockId: string, action: string) {
        this._menuOpen = false;
        const pageId = this._requirePageId();
        if (action === 'edit_html') { this._openHtmlEditor(blockId); return; }
        if (action === 'duplicate') this._commit(duplicateBlock(this._requireDraft(), pageId, blockId));
        else if (action === 'wrap') this._commit(wrapInSection(this._requireDraft(), pageId, blockId));
        else if (action === 'remove') this._remove(blockId);
        else throw new Error(`interface editor: unknown block action ${action}`);
    }

    _openHtmlEditor(blockId: string) {
        const { block } = locateBlock(this._requirePage(), blockId);
        if (block.type !== 'html') throw new Error('interface editor: edit_html requires html block');
        const statePaths = statePathCatalog({ dataflow: this._editor.state.dataflow, sampleState: this._sampleState, document: this._requireDraft() })
            .filter((entry) => !entry.protected).map((entry) => entry.path);
        this.openModal('flows.interface_html_editor', {
            source: typeof block.source === 'string' ? block.source : '',
            block,
            sampleState: this._sampleState,
            statePaths,
            onApply: (source: unknown) => this._setProperty(block.block_id, 'source', source),
        });
    }

    _pageCommand(event: CustomEvent) {
        const { command, pageId, property, value } = event.detail;
        const draft = this._requireDraft();
        if (command === 'add') {
            const page = { page_id: uniquePageId(draft), title: this.t('interface_editor.page_default_title'), show_title: false, blocks: [] };
            this._commit(insertPage(draft, page));
            (this._ui.selectPage({ pageId: page.page_id }));
        } else if (command === 'remove') {
            this._commit(removePage(draft, pageId));
            (this._ui.selectPage({ pageId: this._requireDraft().start_page_id }));
        } else if (command === 'set') {
            this._commit(setPageProperty(draft, pageId, property, value), `page:${pageId}:${property}`);
            if (property === 'page_id') (this._ui.selectPage({ pageId: value }));
        } else if (command === 'start') {
            this._commit({ ...structuredClone(draft), start_page_id: pageId });
        } else {
            throw new Error(`interface editor: unknown page command ${String(command)}`);
        }
    }

    _applyTemplate(document: unknown) {
        if (!isPlainRecord(document) || typeof document.start_page_id !== 'string' || document.start_page_id === '') {
            throw new Error('flows-interface-editor: template document requires start_page_id');
        }
        this._commit(structuredClone(document));
        this._ui.selectPage({ pageId: document.start_page_id });
    }

    async assist(instruction: unknown, scope: unknown) {
        const draft = this._requireDraft();
        const pageId = this._requirePageId();
        const blockId = scope === 'block' ? this._ui.value.selectedBlockId : null;
        if (scope === 'block' && blockId === '') throw new Error('interface editor: assist for block requires selection');
        const result = await this._assistOp.run({ flow_id: this.flowId, branch_id: this.branchId, instruction, document: draft, page_id: pageId, block_id: blockId });
        if (!isPlainRecord(result)) return;
        if (result.scope === 'page') {
            const page = result.page;
            if (!isPlainRecord(page) || !Array.isArray(page.blocks)) {
                throw new Error('flows-interface-editor: assist page blocks required');
            }
            this._commit(replacePageBlocks(this._requireDraft(), pageId, page.blocks));
            return;
        }
        if (!Array.isArray(result.blocks) || result.blocks.length === 0) {
            throw new Error('flows-interface-editor: assist blocks required');
        }
        if (typeof blockId !== 'string' || blockId === '') throw new Error('flows-interface-editor: assist blockId required');
        const { containerKey, index } = locateBlock(findPage(this._requireDraft(), pageId), blockId);
        let next = removeBlock(this._requireDraft(), pageId, blockId);
        result.blocks.forEach((block, offset) => { next = insertBlock(next, pageId, containerKey, index + offset, block); });
        this._commit(next);
        const first = result.blocks[0];
        if (!isPlainRecord(first) || typeof first.block_id !== 'string') {
            throw new Error('flows-interface-editor: assist block_id required');
        }
        (this._ui.selectBlock)({ blockId: first.block_id });
    }

    /**
     * Коммит UI-черновика в flowConfig. PUT делает страница / Preview.
     * @returns {boolean} можно продолжать save; при blocking problems — false.
     */
    commitDraft() {
        const draft = this._draft;
        if (draft === null) return true;
        if (!this._dirty) return true;
        if (this._schema === null) return false;
        const problems = this._problems;
        if (hasBlockingProblems(problems)) {
            const first = problems.find((problem) => problem.severity === 'error');
            if (first) this._focusProblem(first);
            this.toast('interface_editor.publish_blocked', { type: 'error' });
            return false;
        }
        this.emit('interface-change', { config: structuredClone(draft) });
        writeDraft(this._documentKey, null);
        return true;
    }

    /**
     * Предпросмотр холста — живой Task на том же документе, что проверяет сервер:
     * несохранённый черновик коммитится и сохраняется перед запуском.
     */
    async setCanvasPreview(preview: boolean) {
        if (preview && this._dirty) {
            if (!this.commitDraft()) return;
            this.emit('interface-save-request');
            await this._flowSaved();
            if (this._editor.state.isDirty) return;
        }
        (this._ui.setPreview({ preview }));
    }

    /** Страница сохраняет flow по ``interface-save-request``; ждём завершения этого сохранения. */
    _flowSaved() {
        if (!this._editor.state.isSaving) return Promise.resolve();
        return new Promise<void>((resolve) => {
            const setSaving = this._editor.op.actions.setSaving;
            if (typeof setSaving !== 'string' || setSaving.length === 0) {
                throw new Error('flows-interface-editor: setSaving event required');
            }
            const unsubscribe = this.useEvent(setSaving, (event) => {
                if (!isPlainRecord(event.payload)) {
                    throw new Error('flows-interface-editor: saving payload required');
                }
                if (event.payload.saving === true) return;
                unsubscribe();
                resolve();
            });
        });
    }

    _focusProblem(problem: DocumentProblem) {
        if (problem.pageId !== null && problem.pageId !== (this._ui).value.pageId) (this._ui.selectPage({ pageId: problem.pageId }));
        if (problem.blockId !== null) (this._ui.selectBlock({ blockId: problem.blockId }));
    }

    // --- Холст: выделение, DnD, inline ------------------------------------------------------

    _flowUi(): PlatformFlowUI | null {
        const flowUi = this.renderRoot.querySelector('platform-flow-ui');
        if (flowUi === null) return null;
        if (!(flowUi instanceof PlatformFlowUI)) {
            throw new Error('flows-interface-editor: platform-flow-ui is not registered');
        }
        return flowUi;
    }

    _scheduleFrame() {
        cancelAnimationFrame(this._frameRaf);
        this._frameRaf = requestAnimationFrame(() => {
            const frameHost = this.renderRoot.querySelector('.frame');
            const blockId = (this._ui).value.selectedBlockId;
            const next = frameHost && blockId !== '' && !(this._ui).value.preview ? blockFrame(this._flowUi(), blockId, frameHost) : null;
            if (stableStringify(next) !== stableStringify(this._frame)) this._frame = next;
        });
    }

    _onCanvasClick(event: Event) {
        if (this._inlineEdit !== null || (this._ui).value.preview) return;
        const blockId = blockIdFromEvent(event);
        (this._ui.selectBlock({ blockId: blockId === null ? '' : blockId }));
        this.focus();
    }

    _onCanvasDblClick(event: Event) {
        if ((this._ui).value.preview) return;
        const blockId = blockIdFromEvent(event);
        if (blockId === null) return;
        const { block } = locateBlock(this._requirePage(), blockId);
        const property = inlineTextProperty(block.type);
        if (property === null) return;
        const frameHost = this.renderRoot.querySelector('.frame');
        if (!(frameHost instanceof Element)) return;
        const frame = blockFrame(this._flowUi(), blockId, frameHost);
        if (frame === null) return;
        this._inlineEdit = { blockId, property, value: block[property], frame, multiline: inlineTextIsMultiline(block.type) };
        this.updateComplete.then(() => {
            const field = inlineTextControl(this.renderRoot);
            if (field === null) return;
            field.focus();
            field.select();
        });
    }

    _finishInlineEdit(commit: boolean) {
        const edit = this._inlineEdit;
        if (edit === null) return;
        this._inlineEdit = null;
        if (commit) {
            const field = inlineTextControl(this.renderRoot);
            if (field === null) {
                throw new Error('flows-interface-editor: inline edit control required');
            }
            const value = field.value;
            if (value !== edit.value) this._setProperty(edit.blockId, edit.property, value);
        }
        this.focus();
    }

    _onDragOver(event: Event) {
        if (!(event instanceof DragEvent) || event.dataTransfer === null || !hasFlowUiDrag(event.dataTransfer)) return;
        event.preventDefault();
        const frameHost = this.renderRoot.querySelector('.frame');
        if (!(frameHost instanceof Element)) return;
        const dragTypes = Array.from(event.dataTransfer.types);
        const movingId = dragTypes.includes(BLOCK_ID_MIME)
            ? (this._ui).value.selectedBlockId
            : null;
        const target = dropTargetFromEvent(event, frameHost, movingId);
        if (stableStringify(target) !== stableStringify(this._drop)) this._drop = target;
    }

    _onDrop(event: Event) {
        if (!(event instanceof DragEvent) || event.dataTransfer === null || !hasFlowUiDrag(event.dataTransfer)) return;
        event.preventDefault();
        const target = this._drop;
        this._drop = null;
        if (target === null) return;
        const payload = readDragPayload(event.dataTransfer);
        if (payload === null) return;
        if (payload.kind === 'insert') {
            this._insert(payload.type, target.containerKey, target.index, payload.columns);
            return;
        }
        this._commit(moveBlock(this._requireDraft(), this._requirePageId(), payload.blockId, target.containerKey, target.index));
    }

    _onHandleDragStart(event: DragEvent, blockId: string) {
        const transfer = event.dataTransfer;
        if (transfer === null) {
            throw new Error('flows-interface-editor: dataTransfer required');
        }
        transfer.setData(BLOCK_ID_MIME, blockId);
        transfer.effectAllowed = 'move';
    }

    _handleKeydown(event: KeyboardEvent) {
        if (this._inlineEdit !== null || (this._ui).value.preview) return;
        const path = event.composedPath();
        if (path.some((node) => node instanceof HTMLElement && (node.matches('input, textarea, select, [contenteditable="true"]') || node.classList.contains('cm-content')))) return;
        const meta = event.metaKey || event.ctrlKey;
        const blockId = (this._ui).value.selectedBlockId;
        if (meta && event.key.toLowerCase() === 'z') {
            event.preventDefault();
            if (event.shiftKey) (this._ui.redo(null)); else (this._ui.undo(null));
            return;
        }
        if (typeof blockId !== 'string' || blockId === '') return;
        if (meta && event.key.toLowerCase() === 'd') { event.preventDefault(); this._blockMenuAction(blockId, 'duplicate'); return; }
        if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); this._remove(blockId); return; }
        if (event.key === 'ArrowUp') { event.preventDefault(); this._moveWithin(blockId, -1); return; }
        if (event.key === 'ArrowDown') { event.preventDefault(); this._moveWithin(blockId, 1); return; }
        if (event.key === 'Escape') (this._ui.selectBlock({ blockId: '' }));
    }

    // --- Рендер -------------------------------------------------------------------------------

    _renderSelection() {
        const frame = this._frame;
        const blockId = this._ui.value.selectedBlockId;
        const page = this._page;
        if (frame === null || typeof blockId !== 'string' || blockId === '' || page === null) return '';
        const { block } = locateBlock(page, blockId);
        const items = [
            ...(block.type === 'html' ? [{ id: 'edit_html', label: this.t('interface_editor.html_open_editor'), icon: 'code' }] : []),
            { id: 'duplicate', label: this.t('interface_editor.block_duplicate'), icon: 'copy', hint: '⌘D' },
            { id: 'wrap', label: this.t('interface_editor.block_wrap_section'), icon: 'square' },
            { id: 'remove', label: this.t('interface_editor.block_remove'), icon: 'trash', hint: '⌫', danger: true },
        ];
        return html`<div class="selection" style=${`top:${frame.top}px;left:${frame.left}px;width:${frame.width}px;height:${frame.height}px`}>
            <div class="label">
                <span class="handle" draggable="true" title=${this.t('interface_editor.drag_hint')} @dragstart=${(event: DragEvent) => this._onHandleDragStart(event, blockId)}><platform-icon name="drag-handle" size="12"></platform-icon></span>
                <span>${this.t(`interface_editor.block_${block.type}`)}</span>
                ${renderAlignButtons({ block, t: (key) => this.t(key), setProperty: (id, name, value) => {
                    if (typeof id !== 'string' || id === '') throw new Error('flows-interface-editor: block id required');
                    this._setProperty(id, name, value);
                } })}
                <platform-button ghost density="dense" icon-only class="kebab" aria-label=${this.t('interface_editor.block_menu')} @click=${(event: CustomEvent) => { event.stopPropagation(); this._menuOpen = !this._menuOpen; }}><platform-icon name="more-vert" size="12"></platform-icon></platform-button>
                <platform-popover trigger="manual" .anchor=${this.renderRoot.querySelector('.kebab')} ?open=${this._menuOpen} role="menu" dismiss-on-outside @popover-dismiss=${() => { this._menuOpen = false; }}>
                    <platform-menu compact .items=${items} @menu-select=${(event: CustomEvent) => {
                        const actionId = event.detail.id;
                        if (typeof actionId !== 'string' || actionId === '') throw new Error('flows-interface-editor: block action required');
                        this._blockMenuAction(blockId, actionId);
                    }}></platform-menu>
                </platform-popover>
            </div>
            ${renderSpanHandle({ block, t: (key) => this.t(key), setProperty: (id, name, value) => {
                if (typeof id !== 'string' || id === '') throw new Error('flows-interface-editor: block id required');
                this._setProperty(id, name, value);
            }, blockEl: blockElement(this._flowUi(), blockId) })}
        </div>`;
    }

    override render(): TemplateResult {
        const draft = this._draft;
        if (draft === null || this._schema === null) return html`<platform-empty-state loading></platform-empty-state>`;
        const ui = this._ui.value;
        const page = this._page;
        if (page === null) throw new Error('flows-interface-editor: page required');
        const problems = this._problems;
        const catalogPaths = statePathCatalog({ dataflow: this._editor.state.dataflow, sampleState: this._sampleState, document: draft });
        const selectedBlockId = ui.selectedBlockId;
        const selected = typeof selectedBlockId === 'string' && selectedBlockId !== '' ? locateBlock(page, selectedBlockId).block : null;
        const drop = this._drop;
        const inlineEdit = this._inlineEdit;
        return html`
            <flows-interface-pages-tabs .document=${draft} .pageId=${ui.pageId!}
                @page-select=${(event: CustomEvent) => (this._ui.selectPage({ pageId: event.detail.pageId }))}
                @page-command=${(event: CustomEvent) => this._pageCommand(event)}
            ></flows-interface-pages-tabs>
            <div class="body">
                <aside class="sidebar">
                    <platform-segmented-control class="sidebar-tabs" density="compact" .value=${ui.sidebarTab!}
                        .items=${[{ value: 'add', label: this.t('interface_editor.tab_add') }, { value: 'properties', label: this.t('interface_editor.tab_properties') }]}
                        @change=${(event: CustomEvent) => (this._ui.setSidebarTab({ tab: event.detail.value }))}></platform-segmented-control>
                    ${ui.sidebarTab! === 'add'
                        ? html`<flows-interface-add-panel .catalog=${this._catalog}
                            @block-add=${(event: CustomEvent) => { const target = paletteInsertTarget(page, typeof selectedBlockId === 'string' ? selectedBlockId : null); this._insert(event.detail.type, target.containerKey, target.index, event.detail.columns); }}></flows-interface-add-panel>`
                        : html`<flows-interface-properties-panel .block=${selected} .page=${page} .document=${draft}
                            .catalog=${this._catalog} .schema=${this._schema} .frozen=${this._frozen} .statePaths=${catalogPaths} .sampleState=${this._sampleState}
                            .problems=${problems.filter((problem) => selected !== null && problem.blockId === selected.block_id)}
                            @property-change=${(event: CustomEvent) => this._setProperty(event.detail.blockId, event.detail.property, event.detail.value)}
                            @page-property-change=${(event: CustomEvent) => {
                                const pageId = ui.pageId;
                                if (typeof pageId !== 'string' || pageId.length === 0) {
                                    throw new Error('flows-interface-editor: pageId required');
                                }
                                this._commit(setPageProperty(this._requireDraft(), pageId, event.detail.property, event.detail.value), `page:${pageId}:${event.detail.property}`);
                            }}
                            @image-upload=${(event: CustomEvent) => void this._uploadBlockImage(event.detail)}
                            @block-action=${(event: CustomEvent) => this._blockMenuAction(event.detail.blockId, event.detail.action)}
                        ></flows-interface-properties-panel>`}
                </aside>
                <div class="canvas" @click=${this._onCanvasClick} @dblclick=${this._onCanvasDblClick}
                    @dragover=${this._onDragOver} @drop=${this._onDrop} @dragleave=${() => { this._drop = null; }}
                    @scroll=${() => this._scheduleFrame()}>
                    <div class="frame" data-preview=${ui.preview! ? 'true' : 'false'} style=${`width:min(100%, ${editorFrameWidth(ui.viewport)}px)`}>
                        ${ui.preview!
                            ? html`<platform-flow-ui profile="editor_test" display="panel" theme="auto" flow-id=${this.flowId} branch-id=${this.branchId} page-id=${ui.pageId!} base-url="/flows" .initialDocument=${draft}></platform-flow-ui>`
                            : html`<platform-flow-ui editing theme="auto" flow-id=${this.flowId} page-id=${ui.pageId!} .initialDocument=${draft} .sampleState=${this._sampleState}
                                selected-block-id=${ui.selectedBlockId!}
                                @flow-ui-navigation=${(event: CustomEvent) => { if (event.detail.pageId !== ui.pageId) (this._ui.selectPage({ pageId: event.detail.pageId })); }}></platform-flow-ui>`}
                        ${this._renderSelection()}
                        ${drop !== null ? html`<div class="drop-line" style=${`top:${drop.indicator.top}px;left:${drop.indicator.left}px;width:${drop.indicator.width}px`}></div>` : nothing}
                        ${inlineEdit !== null ? html`<textarea class="inline-edit" data-canon="inline-edit" .value=${inlineEdit.value}
                            style=${`top:${inlineEdit.frame.top}px;left:${inlineEdit.frame.left}px;width:${inlineEdit.frame.width}px;min-height:${Math.max(inlineEdit.frame.height, 36)}px`}
                            @blur=${() => this._finishInlineEdit(true)}
                            @keydown=${(event: KeyboardEvent) => { const action = inlineEditKeyAction(event, inlineEdit.multiline); if (action !== null) { event.preventDefault(); this._finishInlineEdit(action === 'commit'); } }}></textarea>` : nothing}
                    </div>
                </div>
            </div>
        `;
    }
}

if (!customElements.get('flows-interface-editor')) customElements.define('flows-interface-editor', FlowsInterfaceEditor);

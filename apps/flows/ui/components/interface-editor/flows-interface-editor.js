/**
 * Редактор интерфейса flow (модель Odoo Studio): слева «Добавить» / «Свойства», в центре холст
 * ``<platform-flow-ui editing>`` на реальном рендере, сверху вкладки страниц и панель инструментов.
 *
 * Хост-контракт: ``.interfaceConfig`` (FlowUIDocument ветки), ``.flowId``, ``.branchId``;
 * ``interface-change {config}`` — публикация валидного черновика. Черновик и история живут
 * в slice ``flows/interface_editor``; структура меняется только командами домена.
 */

import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { flowUIEditorChromeTokens } from '@platform/lib/flow-ui/editor/editor-chrome.styles.js';
import { blockFrame, blockIdFromEvent } from '@platform/lib/flow-ui/editor/selection.js';
import { BLOCK_ID_MIME, dropTargetFromEvent, hasFlowUiDrag, readDragPayload } from '@platform/lib/flow-ui/editor/drop-zones.js';
import { inlineEditKeyAction, inlineTextIsMultiline, inlineTextProperty } from '@platform/lib/flow-ui/editor/inline-text-edit.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-button.js';
import {
    EDITOR_VIEWPORTS,
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
} from './interface-editor-domain.js';
import './flows-interface-toolbar.js';
import './flows-interface-pages-tabs.js';
import './flows-interface-add-panel.js';
import './flows-interface-properties-panel.js';

const DRAFTS_STORAGE_KEY = platformStorageKey('flows', 'interface_drafts');

function stableStringify(value) {
    if (value === null || typeof value !== 'object') return JSON.stringify(value);
    if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
}

function readDrafts() {
    const raw = globalThis.localStorage.getItem(DRAFTS_STORAGE_KEY);
    return raw === null ? {} : JSON.parse(raw);
}

function writeDraft(documentKey, document) {
    const drafts = readDrafts();
    if (document === null) delete drafts[documentKey];
    else drafts[documentKey] = document;
    globalThis.localStorage.setItem(DRAFTS_STORAGE_KEY, JSON.stringify(drafts));
}

export class FlowsInterfaceEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        interfaceConfig: { attribute: false },
        flowId: { type: String },
        branchId: { type: String },
        _schema: { state: true },
        _frame: { state: true },
        _drop: { state: true },
        _inlineEdit: { state: true },
        _menuOpen: { state: true },
    };

    static styles = [PlatformElement.styles, flowUIEditorChromeTokens, css`
        :host { display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; min-width: 0; min-height: 0; height: 100%; background: var(--bg-elevated); outline: none; }
        .body { display: grid; grid-template-columns: minmax(280px, 320px) minmax(0, 1fr); min-height: 0; }
        .sidebar { min-height: 0; overflow: auto; border-right: 1px solid var(--border-subtle); background: var(--glass-solid-medium); display: grid; grid-template-rows: auto minmax(0, 1fr); }
        .sidebar-tabs { display: block; margin: 8px 10px 0; }
        .canvas { position: relative; min-width: 0; min-height: 0; overflow: auto; padding: 28px 24px 120px; background:
            radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--text-tertiary) 22%, transparent) 1px, transparent 0) 0 0 / 22px 22px; }
        .frame { position: relative; margin: 0 auto; min-height: 480px; border-radius: 16px; border: 1px solid var(--border-subtle); background: var(--bg-primary); box-shadow: var(--shadow-lg); transition: width 180ms ease; }
        .frame platform-flow-ui { display: block; border-radius: inherit; overflow: hidden; }
        .frame[data-preview='true'] platform-flow-ui { height: 720px; }
        .selection { position: absolute; pointer-events: none; border: 2px solid var(--flow-ui-editor-select); border-radius: 8px; z-index: 3; }
        .selection .label { position: absolute; top: -26px; left: -2px; display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px; border-radius: 6px 6px 6px 0; background: var(--flow-ui-editor-select); color: var(--flow-ui-editor-label-fg); font-size: 11px; font-weight: 650; white-space: nowrap; pointer-events: auto; }
        .selection .label .handle { cursor: grab; display: inline-grid; place-items: center; }
        .selection .label .kebab { color: inherit; }
        .drop-line { position: absolute; height: 3px; margin-top: -1px; border-radius: 3px; background: var(--flow-ui-editor-insert); box-shadow: 0 0 0 3px var(--flow-ui-editor-insert-fill); pointer-events: none; z-index: 4; }
        .inline-edit { position: absolute; z-index: 5; box-sizing: border-box; padding: 6px 8px; border: 2px solid var(--flow-ui-editor-select); border-radius: 8px; background: var(--bg-primary); color: var(--text-primary); font: inherit; font-size: 14px; line-height: 1.4; resize: none; outline: none; box-shadow: var(--shadow-lg); }
        .problems { display: flex; align-items: center; gap: 10px; min-height: 34px; padding: 4px 12px; border-top: 1px solid var(--border-subtle); background: var(--glass-solid-medium); font-size: 12px; color: var(--text-secondary); overflow-x: auto; white-space: nowrap; }
        .problems .problem { display: inline-flex; align-items: center; gap: 6px; margin: 0; padding: 3px 8px; border-radius: 6px; background: var(--glass-solid-subtle); color: var(--text-primary); font-size: 12px; cursor: pointer; }
        .problems .problem:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .problems .problem[data-severity='error'] { color: var(--error); }
        .problems .problem[data-severity='warning'] { color: var(--warning); }
        .problems .ok { color: var(--success); display: inline-flex; align-items: center; gap: 6px; }
        .loading { display: grid; place-items: center; height: 100%; color: var(--text-tertiary); font-size: 13px; }
        @media (max-width: 1000px) { .body { grid-template-columns: 240px minmax(0, 1fr); } }
    `];

    constructor() {
        super();
        this.interfaceConfig = null;
        this.flowId = '';
        this.branchId = 'default';
        this._schema = null;
        this._catalog = [];
        this._frozen = new Set();
        this._frame = null;
        this._drop = null;
        this._inlineEdit = null;
        this._menuOpen = false;
        this._ui = this.useSlice('flows/interface_editor');
        this._editor = this.useOp('flows/editor');
        this._schemaOp = this.useOp('flows/flow_ui_schema');
        this._assistOp = this.useOp('flows/flow_ui_assist');
        this._frameRaf = 0;
        this._resizeObserver = null;
        this._onKeyDown = (event) => this._handleKeydown(event);
    }

    connectedCallback() {
        super.connectedCallback();
        this.tabIndex = 0;
        this.addEventListener('keydown', this._onKeyDown);
        void this._loadSchema();
    }

    disconnectedCallback() {
        this.removeEventListener('keydown', this._onKeyDown);
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

    firstUpdated() {
        this._resizeObserver = new ResizeObserver(() => this._scheduleFrame());
        const canvas = this.renderRoot.querySelector('.canvas');
        if (canvas) this._resizeObserver.observe(canvas);
    }

    updated(changed) {
        if (changed.has('interfaceConfig') || changed.has('flowId') || changed.has('branchId')) this._openDocument();
        this._syncCanvasPage();
        this._scheduleFrame();
    }

    /** Активная вкладка страницы — источник правды для страницы холста. */
    _syncCanvasPage() {
        const flowUi = this._flowUi();
        const pageId = this._ui.value.pageId;
        if (flowUi === null || this._ui.value.preview || pageId === '' || this._page === null) return;
        if (flowUi.store.document !== null && flowUi.store.pageId !== pageId) flowUi.navigate(pageId);
    }

    // --- Документ ---------------------------------------------------------------------------

    get _documentKey() {
        return `${this.flowId}:${this.branchId}`;
    }

    get _draft() {
        const ui = this._ui.value;
        return ui.history !== null && ui.documentKey === this._documentKey ? ui.history.present : null;
    }

    get _page() {
        const draft = this._draft;
        return draft === null ? null : findPage(draft, this._ui.value.pageId);
    }

    get _sampleState() {
        const preview = this._editor.state.previewExecutionState;
        return preview && typeof preview === 'object' ? preview : {};
    }

    _openDocument() {
        if (this.flowId === '' || this.interfaceConfig === null) return;
        if (this._ui.value.documentKey === this._documentKey) return;
        const drafts = readDrafts();
        const stored = Object.hasOwn(drafts, this._documentKey) ? drafts[this._documentKey] : null;
        this._ui.openDocument({ documentKey: this._documentKey, document: stored ?? structuredClone(this.interfaceConfig) });
    }

    _commit(document, coalesceKey = null) {
        this._ui.commitDocument({ document, coalesceKey });
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

    _labels() {
        return {
            tab: this.t('interface_editor.default_tab'),
            option: this.t('interface_editor.default_option'),
            text: (type, name) => this.t(`interface_editor.default_text_${type}_${name}`),
        };
    }

    // --- Команды ------------------------------------------------------------------------------

    _insert(type, containerKey, index, columns = null) {
        const page = this._page;
        const entry = catalogEntry(this._catalog, type);
        const blockId = uniqueBlockId(page, type);
        const block = columns === null ? defaultBlock(entry, blockId, this._labels()) : withColumns(entry, blockId, columns, this._labels());
        this._commit(insertBlock(this._draft, page.page_id, containerKey, index, block));
        this._ui.selectBlock({ blockId });
    }

    _setProperty(blockId, property, value) {
        const pageId = this._ui.value.pageId;
        this._commit(setBlockProperty(this._draft, pageId, blockId, property, value), `${blockId}:${property}`);
        if (property === 'block_id') this._ui.selectBlock({ blockId: value });
    }

    _remove(blockId) {
        this._commit(removeBlock(this._draft, this._ui.value.pageId, blockId));
        this._ui.selectBlock({ blockId: '' });
    }

    _moveWithin(blockId, delta) {
        const page = this._page;
        const { containerKey, index } = locateBlock(page, blockId);
        const target = index + delta;
        if (target < 0) return;
        this._commit(moveBlock(this._draft, page.page_id, blockId, containerKey, delta > 0 ? target + 1 : target));
    }

    _blockMenuAction(blockId, action) {
        this._menuOpen = false;
        const pageId = this._ui.value.pageId;
        if (action === 'duplicate') this._commit(duplicateBlock(this._draft, pageId, blockId));
        else if (action === 'wrap') this._commit(wrapInSection(this._draft, pageId, blockId));
        else if (action === 'remove') this._remove(blockId);
        else throw new Error(`interface editor: unknown block action ${action}`);
    }

    _pageCommand(event) {
        const { command, pageId, property, value } = event.detail;
        const draft = this._draft;
        if (command === 'add') {
            const page = { page_id: uniquePageId(draft), title: this.t('interface_editor.page_default_title'), blocks: [] };
            this._commit(insertPage(draft, page));
            this._ui.selectPage({ pageId: page.page_id });
        } else if (command === 'remove') {
            this._commit(removePage(draft, pageId));
            this._ui.selectPage({ pageId: this._draft.start_page_id });
        } else if (command === 'set') {
            this._commit(setPageProperty(draft, pageId, property, value), `page:${pageId}:${property}`);
            if (property === 'page_id') this._ui.selectPage({ pageId: value });
        } else if (command === 'start') {
            this._commit({ ...structuredClone(draft), start_page_id: pageId });
        } else {
            throw new Error(`interface editor: unknown page command ${String(command)}`);
        }
    }

    _applyTemplate(document) {
        this._commit(structuredClone(document));
        this._ui.selectPage({ pageId: document.start_page_id });
    }

    async _assist(instruction, scope) {
        const draft = this._draft;
        const pageId = this._ui.value.pageId;
        const blockId = scope === 'block' ? this._ui.value.selectedBlockId : null;
        if (scope === 'block' && blockId === '') throw new Error('interface editor: assist for block requires selection');
        const result = await this._assistOp.run({ flow_id: this.flowId, branch_id: this.branchId, instruction, document: draft, page_id: pageId, block_id: blockId });
        if (result === null) return;
        if (result.scope === 'page') {
            this._commit(replacePageBlocks(this._draft, pageId, result.page.blocks));
            return;
        }
        const { containerKey, index } = locateBlock(findPage(this._draft, pageId), blockId);
        let next = removeBlock(this._draft, pageId, blockId);
        result.blocks.forEach((block, offset) => { next = insertBlock(next, pageId, containerKey, index + offset, block); });
        this._commit(next);
        this._ui.selectBlock({ blockId: result.blocks[0].block_id });
    }

    /** @returns {boolean} опубликовано ли; при блокирующих проблемах фокусирует первую. */
    _publish() {
        const problems = this._problems;
        if (hasBlockingProblems(problems)) {
            const first = problems.find((problem) => problem.severity === 'error');
            this._focusProblem(first);
            this.toast('interface_editor.publish_blocked', { type: 'error' });
            return false;
        }
        this.emit('interface-change', { config: structuredClone(this._draft) });
        writeDraft(this._documentKey, null);
        return true;
    }

    /**
     * Тест — реальный Task на том же документе, что проверяет сервер: несохранённый черновик
     * публикуется перед запуском, иначе поля черновика отклонит ingress ui-action.
     */
    async _setPreview(preview) {
        if (preview && this._dirty) {
            if (!this._publish()) return;
            await this._flowSaved();
            if (this._editor.state.isDirty) return;
        }
        this._ui.setPreview({ preview });
    }

    /** Страница сохраняет flow по ``interface-change``; ждём завершения этого сохранения. */
    _flowSaved() {
        if (!this._editor.state.isSaving) return Promise.resolve();
        return new Promise((resolve) => {
            const unsubscribe = this.useEvent(this._editor.op.actions.setSaving, (event) => {
                if (event.payload.saving) return;
                unsubscribe();
                resolve();
            });
        });
    }

    _focusProblem(problem) {
        if (problem.pageId !== null && problem.pageId !== this._ui.value.pageId) this._ui.selectPage({ pageId: problem.pageId });
        if (problem.blockId !== null) this._ui.selectBlock({ blockId: problem.blockId });
    }

    // --- Холст: выделение, DnD, inline ------------------------------------------------------

    _flowUi() {
        return this.renderRoot.querySelector('platform-flow-ui');
    }

    _scheduleFrame() {
        cancelAnimationFrame(this._frameRaf);
        this._frameRaf = requestAnimationFrame(() => {
            const frameHost = this.renderRoot.querySelector('.frame');
            const blockId = this._ui.value.selectedBlockId;
            const next = frameHost && blockId !== '' && !this._ui.value.preview ? blockFrame(this._flowUi(), blockId, frameHost) : null;
            if (stableStringify(next) !== stableStringify(this._frame)) this._frame = next;
        });
    }

    _onCanvasClick(event) {
        if (this._inlineEdit !== null || this._ui.value.preview) return;
        const blockId = blockIdFromEvent(event);
        this._ui.selectBlock({ blockId: blockId === null ? '' : blockId });
        this.focus();
    }

    _onCanvasDblClick(event) {
        if (this._ui.value.preview) return;
        const blockId = blockIdFromEvent(event);
        if (blockId === null) return;
        const { block } = locateBlock(this._page, blockId);
        const property = inlineTextProperty(block.type);
        if (property === null) return;
        const frameHost = this.renderRoot.querySelector('.frame');
        const frame = blockFrame(this._flowUi(), blockId, frameHost);
        if (frame === null) return;
        this._inlineEdit = { blockId, property, value: block[property], frame, multiline: inlineTextIsMultiline(block.type) };
        this.updateComplete.then(() => { const field = this.renderRoot.querySelector('.inline-edit'); if (field) { field.focus(); field.select(); } });
    }

    _finishInlineEdit(commit) {
        const edit = this._inlineEdit;
        if (edit === null) return;
        this._inlineEdit = null;
        if (commit) {
            const value = this.renderRoot.querySelector('.inline-edit').value;
            if (value !== edit.value) this._setProperty(edit.blockId, edit.property, value);
        }
        this.focus();
    }

    _onDragOver(event) {
        if (!hasFlowUiDrag(event.dataTransfer)) return;
        event.preventDefault();
        const frameHost = this.renderRoot.querySelector('.frame');
        const movingId = event.dataTransfer.types.includes(BLOCK_ID_MIME) ? this._ui.value.selectedBlockId : null;
        const target = dropTargetFromEvent(event, frameHost, movingId);
        if (stableStringify(target) !== stableStringify(this._drop)) this._drop = target;
    }

    _onDrop(event) {
        if (!hasFlowUiDrag(event.dataTransfer)) return;
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
        this._commit(moveBlock(this._draft, this._ui.value.pageId, payload.blockId, target.containerKey, target.index));
    }

    _onHandleDragStart(event, blockId) {
        event.dataTransfer.setData(BLOCK_ID_MIME, blockId);
        event.dataTransfer.effectAllowed = 'move';
    }

    _handleKeydown(event) {
        if (this._inlineEdit !== null || this._ui.value.preview) return;
        const path = event.composedPath();
        if (path.some((node) => node instanceof HTMLElement && (node.matches('input, textarea, select, [contenteditable="true"]') || node.classList.contains('cm-content')))) return;
        const meta = event.metaKey || event.ctrlKey;
        const blockId = this._ui.value.selectedBlockId;
        if (meta && event.key.toLowerCase() === 'z') {
            event.preventDefault();
            if (event.shiftKey) this._ui.redo(null); else this._ui.undo(null);
            return;
        }
        if (blockId === '') return;
        if (meta && event.key.toLowerCase() === 'd') { event.preventDefault(); this._blockMenuAction(blockId, 'duplicate'); return; }
        if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); this._remove(blockId); return; }
        if (event.key === 'ArrowUp') { event.preventDefault(); this._moveWithin(blockId, -1); return; }
        if (event.key === 'ArrowDown') { event.preventDefault(); this._moveWithin(blockId, 1); return; }
        if (event.key === 'Escape') this._ui.selectBlock({ blockId: '' });
    }

    // --- Рендер -------------------------------------------------------------------------------

    _renderSelection() {
        const frame = this._frame;
        const blockId = this._ui.value.selectedBlockId;
        if (frame === null || blockId === '' || this._page === null) return nothing;
        const { block } = locateBlock(this._page, blockId);
        const items = [
            { id: 'duplicate', label: this.t('interface_editor.block_duplicate'), icon: 'copy', hint: '⌘D' },
            { id: 'wrap', label: this.t('interface_editor.block_wrap_section'), icon: 'square' },
            { id: 'remove', label: this.t('interface_editor.block_remove'), icon: 'trash', hint: '⌫', danger: true },
        ];
        return html`<div class="selection" style=${`top:${frame.top}px;left:${frame.left}px;width:${frame.width}px;height:${frame.height}px`}>
            <div class="label">
                <span class="handle" draggable="true" title=${this.t('interface_editor.drag_hint')} @dragstart=${(event) => this._onHandleDragStart(event, blockId)}><platform-icon name="drag-handle" size="12"></platform-icon></span>
                <span>${this.t(`interface_editor.block_${block.type}`)}</span>
                <platform-button ghost density="dense" icon-only class="kebab" aria-label=${this.t('interface_editor.block_menu')} @click=${(event) => { event.stopPropagation(); this._menuOpen = !this._menuOpen; }}><platform-icon name="more-vert" size="12"></platform-icon></platform-button>
                <platform-popover trigger="manual" .anchor=${this.renderRoot.querySelector('.kebab')} ?open=${this._menuOpen} role="menu" dismiss-on-outside @popover-dismiss=${() => { this._menuOpen = false; }}>
                    <platform-menu compact .items=${items} @menu-select=${(event) => this._blockMenuAction(blockId, event.detail.id)}></platform-menu>
                </platform-popover>
            </div>
        </div>`;
    }

    _renderProblems(problems) {
        if (problems.length === 0) return html`<div class="problems"><span class="ok"><platform-icon name="check" size="13"></platform-icon>${this.t('interface_editor.problems_none')}</span></div>`;
        return html`<div class="problems">
            ${problems.map((problem) => html`<article role="button" tabindex="0" class="problem" data-severity=${problem.severity}
                @click=${() => this._focusProblem(problem)}
                @keydown=${(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); this._focusProblem(problem); } }}>
                <platform-icon name=${problem.severity === 'error' ? 'notification-error' : 'alert-triangle'} size="12"></platform-icon>
                ${problem.blockId !== null ? html`<code>${problem.blockId}</code>` : nothing}
                ${this.t(`interface_editor.problem_${problem.code}`, problem.params)}
            </article>`)}
        </div>`;
    }

    render() {
        const draft = this._draft;
        if (draft === null || this._schema === null) return html`<div class="loading">${this.t('interface_editor.loading')}</div>`;
        const ui = this._ui.value;
        const page = this._page;
        const problems = this._problems;
        const catalogPaths = statePathCatalog({ dataflow: this._editor.state.dataflow, sampleState: this._sampleState, document: draft });
        const selected = ui.selectedBlockId !== '' ? locateBlock(page, ui.selectedBlockId).block : null;
        return html`
            <flows-interface-toolbar
                .canUndo=${ui.history.past.length > 0} .canRedo=${ui.history.future.length > 0}
                .viewport=${ui.viewport} .preview=${ui.preview} .dirty=${this._dirty}
                .problemCount=${problems.filter((problem) => problem.severity === 'error').length}
                .hasSelection=${selected !== null} .assistBusy=${this._assistOp.busy}
                @editor-undo=${() => this._ui.undo(null)} @editor-redo=${() => this._ui.redo(null)}
                @editor-viewport=${(event) => this._ui.setViewport({ viewport: event.detail.viewport })}
                @editor-preview=${(event) => this._setPreview(event.detail.preview)}
                @editor-templates=${() => this.openModal('flows.interface_template', { onApply: (document) => this._applyTemplate(document) })}
                @editor-publish=${() => this._publish()}
                @editor-assist=${(event) => this._assist(event.detail.instruction, event.detail.scope)}
            ></flows-interface-toolbar>
            <flows-interface-pages-tabs .document=${draft} .pageId=${ui.pageId}
                @page-select=${(event) => this._ui.selectPage({ pageId: event.detail.pageId })}
                @page-command=${(event) => this._pageCommand(event)}
            ></flows-interface-pages-tabs>
            <div class="body">
                <aside class="sidebar">
                    <platform-segmented-control class="sidebar-tabs" density="compact" .value=${ui.sidebarTab}
                        .items=${[{ value: 'add', label: this.t('interface_editor.tab_add') }, { value: 'properties', label: this.t('interface_editor.tab_properties') }]}
                        @change=${(event) => this._ui.setSidebarTab({ tab: event.detail.value })}></platform-segmented-control>
                    ${ui.sidebarTab === 'add'
                        ? html`<flows-interface-add-panel .catalog=${this._catalog}
                            @block-add=${(event) => this._insert(event.detail.type, 'page', page.blocks.length, event.detail.columns)}></flows-interface-add-panel>`
                        : html`<flows-interface-properties-panel .block=${selected} .page=${page} .document=${draft}
                            .catalog=${this._catalog} .schema=${this._schema} .frozen=${this._frozen} .statePaths=${catalogPaths} .sampleState=${this._sampleState}
                            .problems=${problems.filter((problem) => selected !== null && problem.blockId === selected.block_id)}
                            @property-change=${(event) => this._setProperty(event.detail.blockId, event.detail.property, event.detail.value)}
                            @block-action=${(event) => this._blockMenuAction(event.detail.blockId, event.detail.action)}
                        ></flows-interface-properties-panel>`}
                </aside>
                <div class="canvas" @click=${this._onCanvasClick} @dblclick=${this._onCanvasDblClick}
                    @dragover=${this._onDragOver} @drop=${this._onDrop} @dragleave=${() => { this._drop = null; }}
                    @scroll=${() => this._scheduleFrame()}>
                    <div class="frame" data-preview=${ui.preview ? 'true' : 'false'} style=${`width:min(100%, ${EDITOR_VIEWPORTS[ui.viewport]}px)`}>
                        ${ui.preview
                            ? html`<platform-flow-ui profile="editor_test" display="panel" theme="auto" flow-id=${this.flowId} branch-id=${this.branchId} .initialDocument=${draft}></platform-flow-ui>`
                            : html`<platform-flow-ui editing theme="auto" flow-id=${this.flowId} .initialDocument=${draft} .sampleState=${this._sampleState}
                                selected-block-id=${ui.selectedBlockId}
                                @flow-ui-navigation=${(event) => { if (event.detail.pageId !== ui.pageId) this._ui.selectPage({ pageId: event.detail.pageId }); }}></platform-flow-ui>`}
                        ${this._renderSelection()}
                        ${this._drop !== null ? html`<div class="drop-line" style=${`top:${this._drop.indicator.top}px;left:${this._drop.indicator.left}px;width:${this._drop.indicator.width}px`}></div>` : nothing}
                        ${this._inlineEdit !== null ? html`<textarea class="inline-edit" data-canon="inline-edit" .value=${this._inlineEdit.value}
                            style=${`top:${this._inlineEdit.frame.top}px;left:${this._inlineEdit.frame.left}px;width:${this._inlineEdit.frame.width}px;min-height:${Math.max(this._inlineEdit.frame.height, 36)}px`}
                            @blur=${() => this._finishInlineEdit(true)}
                            @keydown=${(event) => { const action = inlineEditKeyAction(event, this._inlineEdit.multiline); if (action !== null) { event.preventDefault(); this._finishInlineEdit(action === 'commit'); } }}></textarea>` : nothing}
                    </div>
                </div>
            </div>
            ${this._renderProblems(problems)}
        `;
    }
}

if (!customElements.get('flows-interface-editor')) customElements.define('flows-interface-editor', FlowsInterfaceEditor);

/**
 * Блочный редактор документов платформы.
 *
 * Область редактирования живёт в light DOM компонента, а не в shadow root:
 * в shadow DOM ломается IME-ввод (открытый баг ProseMirror #1449 на iOS), а
 * у платформы есть локали zh-CN / ja / ko. Поэтому стили редактора —
 * глобальный `prosemirror.css`, подключаемый рядом с `tokens.css`.
 *
 * Значение — документ ProseMirror (`.value`), тот же формат, что хранит
 * сервер. Markdown здесь не строится: он производный и считается на бэкенде.
 *
 * Плавающие слои (панель форматирования, меню команд, упоминания, меню блока)
 * держит `platform-popover`: он живёт в top layer, поэтому не обрезается
 * прокруткой страницы и не конфликтует с модалками.
 */

import { html, nothing } from '../lit-shim.js';

import { PlatformElement } from '../platform-element/index.js';
import {
    SLASH_MENU_ITEMS,
    buildBlockCommands,
    buildInputRules,
    buildKeymap,
    insertMentionCommand,
    insertPlatformFileCommand,
} from '../editor/wiki-editor-plugins.js';
import { loadWikiEditorRuntime } from '../editor/wiki-schema-builder.js';
import './platform-icon.js';
import './platform-menu.js';
import './platform-popover.js';

const EMPTY_DOCUMENT = Object.freeze({
    type: 'doc',
    content: [{ type: 'paragraph' }],
});

/** Ширина полосы слева от блока, в которой показывается ручка перетаскивания. */
const HANDLE_GUTTER_PX = 44;

const BLOCK_MENU_ACTIONS = Object.freeze([
    { id: 'duplicate', icon: 'copy' },
    { id: 'delete', icon: 'trash', danger: true },
    { id: 'sep', kind: 'separator' },
    { id: 'turn_paragraph', icon: 'text' },
    { id: 'turn_heading_1', icon: 'heading-1' },
    { id: 'turn_heading_2', icon: 'heading-2' },
    { id: 'turn_bullet_list', icon: 'list' },
    { id: 'turn_blockquote', icon: 'quote' },
    { id: 'turn_code_block', icon: 'code' },
]);

const TABLE_ACTIONS = Object.freeze([
    { id: 'addRowBefore', icon: 'arrow-up' },
    { id: 'addRowAfter', icon: 'arrow-down' },
    { id: 'deleteRow', icon: 'minus' },
    { id: 'addColumnBefore', icon: 'arrow-left' },
    { id: 'addColumnAfter', icon: 'arrow-right' },
    { id: 'deleteColumn', icon: 'minus' },
    { id: 'deleteTable', icon: 'trash' },
]);

export class PlatformRichEditor extends PlatformElement {
    static properties = {
        value: { type: Object },
        readonly: { type: Boolean, reflect: true },
        placeholder: { type: String },
        autofocus: { type: Boolean },
        /** `(query: string) => Promise<MentionItem[]>` для меню по `@`. */
        mentionProvider: { attribute: false },
        _ready: { state: true },
        _slashOpen: { state: true },
        _slashQuery: { state: true },
        _slashAnchor: { state: true },
        _bubble: { state: true },
        _bubbleAnchor: { state: true },
        _mentionOpen: { state: true },
        _mentionItems: { state: true },
        _mentionAnchor: { state: true },
        _handleTop: { state: true },
        _handleBlockPos: { state: true },
        _blockMenuAnchor: { state: true },
        _inTable: { state: true },
        _tableAnchor: { state: true },
        _error: { state: true },
    };

    // Редактор управляет своим DOM сам, поэтому Lit не должен его перерисовывать.
    createRenderRoot() {
        return this;
    }

    constructor() {
        super();
        this.value = EMPTY_DOCUMENT;
        this.readonly = false;
        this.placeholder = '';
        this.autofocus = false;
        this.mentionProvider = null;
        this._ready = false;
        this._slashOpen = false;
        this._slashQuery = '';
        this._slashAnchor = null;
        this._bubble = null;
        this._bubbleAnchor = null;
        this._mentionOpen = false;
        this._mentionItems = [];
        this._mentionAnchor = null;
        this._mentionQuery = '';
        this._mentionSeq = 0;
        this._handleTop = -1;
        this._handleBlockPos = -1;
        this._blockMenuAnchor = null;
        this._inTable = false;
        this._tableAnchor = null;
        this._error = '';
        this._view = null;
        this._pm = null;
        this._schema = null;
        this._commands = null;
        this._applyingExternalValue = false;
        this._onHostPointerMove = this._onHostPointerMove.bind(this);
        this._onHostPointerLeave = this._onHostPointerLeave.bind(this);
    }

    async firstUpdated() {
        await this._initEditor();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._view) {
            this._view.destroy();
            this._view = null;
        }
    }

    updated(changed) {
        if (changed.has('value') && this._view && !this._applyingExternalValue) {
            this._applyExternalValue();
        }
        if (changed.has('readonly') && this._view) {
            this._view.setProps({ editable: () => !this.readonly });
        }
    }

    async _initEditor() {
        const host = this.querySelector('.pm-host');
        if (!host) return;

        let runtime;
        try {
            runtime = await loadWikiEditorRuntime();
        } catch (error) {
            this._error = String(error);
            return;
        }

        const { pm, schema } = runtime;
        this._pm = pm;
        this._schema = schema;
        this._commands = buildBlockCommands(pm, schema);

        const plugins = [
            buildInputRules(pm, schema),
            buildKeymap(pm, schema),
            pm.keymap(pm.baseKeymap),
            pm.history(),
            pm.dropCursor(),
            pm.gapCursor(),
            pm.tableEditing(),
            pm.columnResizing(),
            this._slashPlugin(pm),
            this._mentionPlugin(pm),
        ];

        const state = pm.EditorState.create({
            doc: schema.nodeFromJSON(this.value || EMPTY_DOCUMENT),
            plugins,
        });

        this._view = new pm.EditorView(host, {
            state,
            editable: () => !this.readonly,
            attributes: {
                class: 'pm-editor',
                'data-placeholder': this.placeholder || '',
            },
            dispatchTransaction: (transaction) => this._onTransaction(transaction),
        });

        host.addEventListener('pointermove', this._onHostPointerMove);
        host.addEventListener('pointerleave', this._onHostPointerLeave);

        this._ready = true;
        if (this.autofocus && !this.readonly) {
            this._view.focus();
        }
    }

    // --- плагины ---

    _slashPlugin(pm) {
        return new pm.Plugin({
            key: new pm.PluginKey('wiki-slash-menu'),
            props: {
                handleTextInput: (view, from, to, text) => {
                    if (text !== '/') return false;
                    const before = view.state.doc.textBetween(Math.max(0, from - 1), from, '\n', '\n');
                    // Меню открывается только в начале блока или после пробела:
                    // иначе слэш в пути вида /api/v1 превращался бы в меню.
                    if (before && before !== ' ' && before !== '\n') return false;
                    this._slashOpen = true;
                    this._slashQuery = '';
                    return false;
                },
                handleKeyDown: (view, event) => {
                    if (!this._slashOpen) return false;
                    if (event.key === 'Escape') {
                        this._slashOpen = false;
                        return true;
                    }
                    if (event.key === 'Enter') {
                        const items = this._filteredSlashItems();
                        if (items.length > 0) {
                            this._runSlashCommand(items[0].command);
                            return true;
                        }
                    }
                    return false;
                },
            },
        });
    }

    _mentionPlugin(pm) {
        return new pm.Plugin({
            key: new pm.PluginKey('wiki-mention-menu'),
            props: {
                handleTextInput: (view, from, to, text) => {
                    if (text !== '@' || typeof this.mentionProvider !== 'function') return false;
                    const before = view.state.doc.textBetween(Math.max(0, from - 1), from, '\n', '\n');
                    if (before && before !== ' ' && before !== '\n') return false;
                    this._mentionOpen = true;
                    this._mentionQuery = '';
                    void this._loadMentions('');
                    return false;
                },
                handleKeyDown: (view, event) => {
                    if (!this._mentionOpen) return false;
                    if (event.key === 'Escape') {
                        this._mentionOpen = false;
                        return true;
                    }
                    if (event.key === 'Enter' && this._mentionItems.length > 0) {
                        this._pickMention(this._mentionItems[0]);
                        return true;
                    }
                    return false;
                },
            },
        });
    }

    // --- транзакции и состояние слоёв ---

    _onTransaction(transaction) {
        if (!this._view) return;
        const nextState = this._view.state.apply(transaction);
        this._view.updateState(nextState);

        if (this._slashOpen) {
            this._slashQuery = this._queryBefore(nextState, '/');
            if (this._slashQuery === null) {
                this._slashOpen = false;
                this._slashQuery = '';
            } else {
                this._slashAnchor = this._selectionAnchor(nextState);
            }
        }

        if (this._mentionOpen) {
            const query = this._queryBefore(nextState, '@');
            if (query === null) {
                this._mentionOpen = false;
                this._mentionQuery = '';
            } else {
                this._mentionAnchor = this._selectionAnchor(nextState);
                if (query !== this._mentionQuery) {
                    this._mentionQuery = query;
                    void this._loadMentions(query);
                }
            }
        }

        this._bubble = this._bubbleState(nextState);
        this._bubbleAnchor = this._bubble === null ? null : this._selectionAnchor(nextState);
        // Контролы таблицы нужны при курсоре в ячейке, а не только при выделении.
        this._inTable = this._isInTable(nextState);
        this._tableAnchor = this._inTable ? this._selectionAnchor(nextState) : null;

        if (!transaction.docChanged) return;
        this._applyingExternalValue = true;
        this.value = nextState.doc.toJSON();
        this._applyingExternalValue = false;
        this.emit('change', { content: this.value });
    }

    /** Прямоугольник текущего выделения в координатах viewport — якорь для popover. */
    _selectionAnchor(state) {
        if (!this._view) return null;
        const { from, to } = state.selection;
        const start = this._view.coordsAtPos(from);
        const end = this._view.coordsAtPos(to);
        const left = Math.min(start.left, end.left);
        const right = Math.max(start.right, end.right);
        const top = Math.min(start.top, end.top);
        const bottom = Math.max(start.bottom, end.bottom);
        return { top, left, width: Math.max(right - left, 1), height: bottom - top };
    }

    _queryBefore(state, trigger) {
        const { $from } = state.selection;
        const textBefore = $from.parent.textBetween(0, $from.parentOffset, '\n', '\n');
        const pattern = trigger === '/' ? /\/([\p{L}\w-]*)$/u : /@([\p{L}\w-]*)$/u;
        const match = pattern.exec(textBefore);
        return match ? match[1] : null;
    }

    _bubbleState(state) {
        if (this.readonly || state.selection.empty) return null;
        const marks = this._schema ? this._schema.marks : {};
        const isActive = (markType) => {
            if (!markType) return false;
            const { from, $from, to, empty } = state.selection;
            return empty
                ? Boolean(markType.isInSet(state.storedMarks || $from.marks()))
                : state.doc.rangeHasMark(from, to, markType);
        };
        return {
            strong: isActive(marks.strong),
            em: isActive(marks.em),
            code: isActive(marks.code),
            strike: isActive(marks.strike),
            highlight: isActive(marks.highlight),
        };
    }

    _isInTable(state) {
        const { $from } = state.selection;
        for (let depth = $from.depth; depth > 0; depth -= 1) {
            if ($from.node(depth).type.name === 'table') {
                return true;
            }
        }
        return false;
    }

    _applyExternalValue() {
        const nextDoc = this._schema.nodeFromJSON(this.value || EMPTY_DOCUMENT);
        if (nextDoc.eq(this._view.state.doc)) return;
        const state = this._pm.EditorState.create({
            doc: nextDoc,
            plugins: this._view.state.plugins,
        });
        this._view.updateState(state);
    }

    // --- команды по слэшу ---

    _filteredSlashItems() {
        const query = (this._slashQuery || '').toLowerCase();
        const items = SLASH_MENU_ITEMS.map((item) => ({
            ...item,
            label: this.t(item.labelKey),
        }));
        if (!query) return items;
        // Имя команды тоже участвует в поиске: при русском интерфейсе привычно
        // набирать /table, а не /таблица.
        return items.filter(
            (item) =>
                item.label.toLowerCase().includes(query)
                || item.command.toLowerCase().includes(query),
        );
    }

    _runSlashCommand(commandName) {
        const command = this._commands[commandName];
        if (!command || !this._view) return;

        // Слэш и набранный после него фильтр — часть команды, а не текста.
        this._dropTriggerText('/');
        command(this._view.state, this._view.dispatch);
        this._slashOpen = false;
        this._slashQuery = '';
        this._view.focus();
    }

    /** Убрать из документа текст-триггер вместе с набранным фильтром. */
    _dropTriggerText(trigger) {
        const { state } = this._view;
        const { $from } = state.selection;
        const textBefore = $from.parent.textBetween(0, $from.parentOffset, '\n', '\n');
        const pattern = trigger === '/' ? /\/([\p{L}\w-]*)$/u : /@([\p{L}\w-]*)$/u;
        const match = pattern.exec(textBefore);
        if (!match) return;
        const from = state.selection.from - match[0].length;
        this._view.dispatch(state.tr.delete(from, state.selection.from));
    }

    // --- упоминания ---

    async _loadMentions(query) {
        if (typeof this.mentionProvider !== 'function') {
            return;
        }
        this._mentionSeq += 1;
        const seq = this._mentionSeq;
        const items = await this.mentionProvider(query);
        // Ответ на устаревший префикс не должен подменять текущую выдачу.
        if (seq !== this._mentionSeq) return;
        this._mentionItems = Array.isArray(items) ? items : [];
    }

    _pickMention(item) {
        if (!this._view || !this._schema) return;
        this._dropTriggerText('@');
        // Провайдер отдаёт UI-форму (id/kind/label); схема хранит свою.
        const mention = { mentionKind: item.kind, targetId: item.id, label: item.label };
        insertMentionCommand(this._schema, mention)(this._view.state, this._view.dispatch);
        this._mentionOpen = false;
        this._mentionQuery = '';
        this._mentionItems = [];
        this._view.focus();
    }

    _toggleMark(markName) {
        if (!this._view || !this._schema) return;
        const markType = this._schema.marks[markName];
        if (!markType) return;
        this._pm.toggleMark(markType)(this._view.state, this._view.dispatch);
        this._view.focus();
    }

    // --- ручка блока ---

    _onHostPointerMove(event) {
        if (!this._view || this.readonly) return;
        const host = this.querySelector('.pm-host');
        if (!host) return;
        const hostRect = host.getBoundingClientRect();
        const found = this._view.posAtCoords({ left: hostRect.left + HANDLE_GUTTER_PX, top: event.clientY });
        if (!found) {
            this._handleTop = -1;
            this._handleBlockPos = -1;
            return;
        }
        const resolved = this._view.state.doc.resolve(found.pos);
        const blockPos = resolved.depth === 0 ? found.pos : resolved.before(1);
        const dom = this._view.nodeDOM(blockPos);
        const element = dom instanceof Element ? dom : null;
        if (!element) {
            this._handleTop = -1;
            return;
        }
        const rect = element.getBoundingClientRect();
        this._handleTop = rect.top - hostRect.top;
        this._handleBlockPos = blockPos;
    }

    _onHostPointerLeave() {
        if (this._blockMenuAnchor !== null) return;
        this._handleTop = -1;
    }

    _openBlockMenu(event) {
        event.preventDefault();
        this._blockMenuAnchor = event.currentTarget;
    }

    _blockMenuItems() {
        return BLOCK_MENU_ACTIONS.map((action) => (
            action.kind === 'separator'
                ? action
                : { ...action, label: this.t(`editor.block_menu.${action.id}`) }
        ));
    }

    _onBlockMenuSelect(event) {
        const actionId = event.detail.id;
        this._blockMenuAnchor = null;
        if (!this._view || this._handleBlockPos < 0) return;

        const { state } = this._view;
        const node = state.doc.nodeAt(this._handleBlockPos);
        if (!node) return;

        if (actionId === 'delete') {
            this._view.dispatch(state.tr.delete(this._handleBlockPos, this._handleBlockPos + node.nodeSize));
            this._view.focus();
            return;
        }
        if (actionId === 'duplicate') {
            const insertAt = this._handleBlockPos + node.nodeSize;
            this._view.dispatch(state.tr.insert(insertAt, node.copy(node.content)));
            this._view.focus();
            return;
        }

        const commandName = actionId.replace(/^turn_/, '');
        const command = this._commands[commandName];
        if (!command) {
            throw new Error(`platform-rich-editor: нет команды блока ${commandName}`);
        }
        // Команда работает от выделения, поэтому курсор сначала переносится в блок.
        const selection = this._pm.TextSelection.create(state.doc, this._handleBlockPos + 1);
        this._view.dispatch(state.tr.setSelection(selection));
        command(this._view.state, this._view.dispatch);
        this._view.focus();
    }

    _onHandleDragStart(event) {
        if (!this._view || this._handleBlockPos < 0) return;
        const node = this._view.state.doc.nodeAt(this._handleBlockPos);
        if (!node) return;
        // NodeSelection даёт ProseMirror переместить блок целиком его же
        // механикой drag-and-drop, вместе с дочерним содержимым.
        const selection = this._pm.NodeSelection.create(this._view.state.doc, this._handleBlockPos);
        this._view.dispatch(this._view.state.tr.setSelection(selection));
        event.dataTransfer.effectAllowed = 'move';
    }

    // --- таблицы ---

    _runTableCommand(actionId) {
        const command = this._pm[actionId];
        if (typeof command !== 'function') {
            throw new Error(`platform-rich-editor: нет табличной команды ${actionId}`);
        }
        command(this._view.state, this._view.dispatch);
        this._view.focus();
    }

    // --- публичный API ---

    /** Вставить упоминание пользователя, сущности, страницы или документа. */
    insertMention(mention) {
        if (!this._view || !this._schema) return;
        insertMentionCommand(this._schema, mention)(this._view.state, this._view.dispatch);
        this._view.focus();
    }

    /** Вставить карточку документа платформы. */
    insertPlatformFile(file) {
        if (!this._view || !this._schema) return;
        insertPlatformFileCommand(this._schema, file)(this._view.state, this._view.dispatch);
        this._view.focus();
    }

    /** Оглавление страницы: заголовки в порядке документа. */
    getOutline() {
        if (!this._view) return [];
        const outline = [];
        this._view.state.doc.descendants((node, pos) => {
            if (node.type.name === 'heading') {
                outline.push({ level: node.attrs.level, text: node.textContent, pos });
            }
            return true;
        });
        return outline;
    }

    /** Прокрутить к заголовку из оглавления. */
    scrollToPosition(pos) {
        if (!this._view) return;
        const { node } = this._view.domAtPos(pos);
        const element = node instanceof Element ? node : node.parentElement;
        if (element) element.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    render() {
        return html`
            <div class="pm-shell" data-ready=${this._ready ? 'true' : 'false'}>
                ${this._error
                    ? html`<div class="pm-error">${this.t('editor.load_failed')}</div>`
                    : ''}
                ${this._renderBlockHandle()}
                <div class="pm-host"></div>
                ${this._renderBubblePopover()}
                ${this._renderTablePopover()}
                ${this._renderSlashPopover()}
                ${this._renderMentionPopover()}
                ${this._renderBlockMenuPopover()}
            </div>
        `;
    }

    _renderBlockHandle() {
        if (this.readonly || this._handleTop < 0) {
            return nothing;
        }
        return html`
            <div class="pm-block-handle" style=${`top:${this._handleTop}px`}>
                <button
                    type="button"
                    class="pm-block-handle-btn"
                    draggable="true"
                    aria-label=${this.t('editor.block_menu.aria')}
                    @dragstart=${this._onHandleDragStart}
                    @click=${this._openBlockMenu}
                >
                    <platform-icon name="grip-vertical" size="14"></platform-icon>
                </button>
            </div>
        `;
    }

    _renderBlockMenuPopover() {
        return html`
            <platform-popover
                trigger="manual"
                role="menu"
                placement="bottom-start"
                offset="4"
                .anchor=${this._blockMenuAnchor}
                ?open=${this._blockMenuAnchor !== null}
                @popover-dismiss=${() => { this._blockMenuAnchor = null; }}
            >
                ${this._blockMenuAnchor !== null
                    ? html`<platform-menu
                          compact
                          .items=${this._blockMenuItems()}
                          @menu-select=${this._onBlockMenuSelect}
                      ></platform-menu>`
                    : nothing}
            </platform-popover>
        `;
    }

    _renderBubblePopover() {
        const marks = [
            { name: 'strong', icon: 'bold' },
            { name: 'em', icon: 'italic' },
            { name: 'strike', icon: 'strikethrough' },
            { name: 'code', icon: 'code' },
            { name: 'highlight', icon: 'highlighter' },
        ];
        return html`
            <platform-popover
                trigger="manual"
                role="dialog"
                placement="top"
                offset="8"
                dismiss-on-outside="false"
                .anchor=${this._bubbleAnchor}
                ?open=${this._bubble !== null}
            >
                ${this._bubble !== null
                    ? html`
                        <div class="pm-bubble" role="toolbar" aria-label=${this.t('editor.format_toolbar')}>
                            ${marks.map(
                                (mark) => html`
                                    <button
                                        type="button"
                                        class="pm-bubble-btn ${this._bubble[mark.name] ? 'is-active' : ''}"
                                        aria-pressed=${this._bubble[mark.name] ? 'true' : 'false'}
                                        title=${this.t(`editor.mark.${mark.name}`)}
                                        @mousedown=${(event) => event.preventDefault()}
                                        @click=${() => this._toggleMark(mark.name)}
                                    >
                                        <platform-icon name=${mark.icon} size="16"></platform-icon>
                                    </button>
                                `,
                            )}
                        </div>
                    `
                    : nothing}
            </platform-popover>
        `;
    }

    _renderTablePopover() {
        return html`
            <platform-popover
                trigger="manual"
                role="toolbar"
                placement="bottom-start"
                offset="8"
                dismiss-on-outside="false"
                .anchor=${this._tableAnchor}
                ?open=${this._inTable && !this.readonly}
            >
                ${this._inTable
                    ? html`<div class="pm-bubble" role="toolbar" aria-label=${this.t('editor.table.toolbar')}>
                          ${this._renderTableControls()}
                      </div>`
                    : nothing}
            </platform-popover>
        `;
    }

    _renderTableControls() {
        return html`
            ${TABLE_ACTIONS.map(
                (action) => html`
                    <button
                        type="button"
                        class="pm-bubble-btn"
                        data-table-action=${action.id}
                        title=${this.t(`editor.table.${action.id}`)}
                        @mousedown=${(event) => event.preventDefault()}
                        @click=${() => this._runTableCommand(action.id)}
                    >
                        <platform-icon name=${action.icon} size="14"></platform-icon>
                    </button>
                `,
            )}
        `;
    }

    _renderSlashPopover() {
        const items = this._slashOpen ? this._filteredSlashItems() : [];
        return html`
            <platform-popover
                trigger="manual"
                role="listbox"
                placement="bottom-start"
                offset="6"
                .anchor=${this._slashAnchor}
                ?open=${this._slashOpen}
                @popover-dismiss=${() => { this._slashOpen = false; }}
            >
                ${this._slashOpen
                    ? html`
                        <div class="pm-slash" role="listbox" aria-label=${this.t('editor.slash.title')}>
                            ${items.length === 0
                                ? html`<div class="pm-slash-empty">${this.t('editor.slash.empty')}</div>`
                                : items.map(
                                    (item) => html`
                                        <button
                                            type="button"
                                            class="pm-slash-item"
                                            role="option"
                                            data-slash-command=${item.command}
                                            @mousedown=${(event) => event.preventDefault()}
                                            @click=${() => this._runSlashCommand(item.command)}
                                        >
                                            <platform-icon name=${item.icon} size="16"></platform-icon>
                                            <span>${item.label}</span>
                                        </button>
                                    `,
                                )}
                        </div>
                    `
                    : nothing}
            </platform-popover>
        `;
    }

    _renderMentionPopover() {
        return html`
            <platform-popover
                trigger="manual"
                role="listbox"
                placement="bottom-start"
                offset="6"
                .anchor=${this._mentionAnchor}
                ?open=${this._mentionOpen}
                @popover-dismiss=${() => { this._mentionOpen = false; }}
            >
                ${this._mentionOpen
                    ? html`
                        <div class="pm-mention" role="listbox" aria-label=${this.t('editor.mention.title')}>
                            ${this._mentionItems.length === 0
                                ? html`<div class="pm-slash-empty">${this.t('editor.mention.empty')}</div>`
                                : this._mentionItems.map(
                                    (item) => html`
                                        <button
                                            type="button"
                                            class="pm-slash-item"
                                            role="option"
                                            data-mention-id=${item.id}
                                            @mousedown=${(event) => event.preventDefault()}
                                            @click=${() => this._pickMention(item)}
                                        >
                                            <span class="pm-mention-kind">${this.t(`editor.mention.kind.${item.kind}`)}</span>
                                            <span>${item.label}</span>
                                        </button>
                                    `,
                                )}
                        </div>
                    `
                    : nothing}
            </platform-popover>
        `;
    }
}

customElements.define('platform-rich-editor', PlatformRichEditor);

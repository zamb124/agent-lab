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
import type { PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';

import { PlatformElement } from '../platform-element/index.js';
import { StyleCache } from '../utils/style-cache.js';
import {
    resolveDefaultFileUrlBase,
    buildWikiNodeViews,
    loadCodeMirrorBundle,
} from '../editor/wiki-editor-nodeviews.js';
import {
    HIGHLIGHT_COLORS,
    SLASH_MENU_ITEMS,
    buildBlockCommands,
    buildInputRules,
    buildKeymap,
    insertImageCommand,
    insertMentionCommand,
    insertPlatformFileCommand,
    setHighlightColorCommand,
    setLinkCommand,
} from '../editor/wiki-editor-plugins.js';
import { loadWikiEditorRuntime } from '../editor/wiki-schema-builder.js';
import type {
    ImagePayload,
    MentionPayload,
    PlatformFilePayload,
} from '../editor/wiki-editor-plugins.js';
import type {
    PmBundleLike,
    PmCommand,
    PmDispatch,
    PmMarkTypeLike,
    PmNodeLike,
    PmSchemaLike,
    PmStateLike,
    PmTransactionLike,
    PmViewLike,
} from '../editor/pm-types.js';
import type { CmModule } from '../codemirror/variable-extensions.js';
import type { PopoverAnchor } from './platform-popover.js';
import { isPlainRecord } from '../events/payload.js';
import './fields/platform-field.js';
import './platform-icon.js';
import './platform-menu.js';
import './platform-popover.js';

const EMPTY_DOCUMENT: Record<string, unknown> = Object.freeze({
    type: 'doc',
    content: [{ type: 'paragraph' }],
});

interface MentionItem {
    id: string;
    kind: string;
    label: string;
}

interface BubbleState {
    strong: boolean;
    em: boolean;
    code: boolean;
    strike: boolean;
    highlight: boolean;
    highlightColor: string;
    link: boolean;
    linkHref: string;
}

interface SlashItem {
    command: string;
    icon: string;
    labelKey: string;
    label: string;
}

interface BlockMenuAction {
    id: string;
    icon?: string;
    danger?: boolean;
    kind?: string;
    label?: string;
}

/** Стили области правки: light DOM не покрывается стилями самого компонента. */
const EDITOR_STYLESHEET_URL = '/static/core/assets/css/prosemirror.css';

/** Отступ от левого края, по которому ищется блок под курсором мыши. */
const BLOCK_PROBE_INSET_PX = 24;

const BLOCK_MENU_ACTIONS: readonly BlockMenuAction[] = Object.freeze([
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

function eventRecord(event: Event, label: string): Record<string, unknown> {
    if (!(event instanceof CustomEvent) || !isPlainRecord(event.detail)) {
        throw new Error(`platform-rich-editor: ${label} detail must be an object`);
    }
    return event.detail;
}

function isPmCommand(value: unknown): value is PmCommand {
    return typeof value === 'function';
}

function dragBlockFrom(dragging: unknown): number | null {
    if (dragging === null) return null;
    if (!isPlainRecord(dragging)) {
        throw new Error('platform-rich-editor: dragging must be an object');
    }
    const node = dragging.node;
    if (node === undefined || node === null) return null;
    if (!isPlainRecord(node)) {
        throw new Error('platform-rich-editor: dragging.node must be an object');
    }
    const from = node.from;
    if (typeof from !== 'number') {
        throw new Error('platform-rich-editor: dragging.node.from must be a number');
    }
    return from;
}

export class PlatformRichEditor extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        value: { type: Object },
        readonly: { type: Boolean, reflect: true },
        placeholder: { type: String },
        autofocus: { type: Boolean },
        /**
         * База URL для чипа `platform_file`. На публичном сайте — роут с
         * токеном; внутри приложения — обычный download Files API.
         */
        fileUrlBase: { type: String, attribute: 'file-url-base' },
        /** `(query: string) => Promise<MentionItem[]>` для меню по `@`. */
        mentionProvider: { attribute: false },
        /**
         * `(markdown: string) => Promise<object>` — документ ProseMirror из
         * markdown. Разбор живёт на сервере, поэтому редактор о нём ничего не
         * знает и берёт функцию у хозяина: второй реализации диалекта в
         * браузере быть не должно.
         */
        markdownParser: { attribute: false },
        _ready: { state: true },
        _slashOpen: { state: true },
        _slashQuery: { state: true },
        _slashAnchor: { state: true },
        _bubble: { state: true },
        _bubbleAnchor: { state: true },
        _linkOpen: { state: true },
        _linkHref: { state: true },
        _highlightOpen: { state: true },
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
    override createRenderRoot(): this {
        return this;
    }
    declare value: Record<string, unknown>;
    declare readonly: boolean;
    declare placeholder: string;
    declare autofocus: boolean;
    declare fileUrlBase: string;
    declare mentionProvider: ((query: string) => Promise<MentionItem[]>) | null;
    declare markdownParser: ((markdown: string) => Promise<Record<string, unknown>>) | null;
    declare _ready: boolean;
    declare _slashOpen: boolean;
    declare _slashQuery: string;
    declare _slashAnchor: PopoverAnchor;
    declare _bubble: BubbleState | null;
    declare _bubbleAnchor: PopoverAnchor;
    declare _linkOpen: boolean;
    declare _linkHref: string;
    declare _highlightOpen: boolean;
    declare _mentionOpen: boolean;
    declare _mentionItems: MentionItem[];
    declare _mentionAnchor: PopoverAnchor;
    declare _handleTop: number;
    declare _handleBlockPos: number;
    declare _blockMenuAnchor: PopoverAnchor;
    declare _inTable: boolean;
    declare _tableAnchor: PopoverAnchor;
    declare _error: string;
    _mentionQuery = '';
    _mentionSeq = 0;
    _suppressBlockMenuClick = false;
    _view: PmViewLike | null = null;
    _pm: PmBundleLike | null = null;
    _schema: PmSchemaLike | null = null;
    _commands: Record<string, PmCommand> | null = null;
    _cm: CmModule | null = null;
    _emittedValue: Record<string, unknown> | null = null;



    constructor() {
        super();
        this.value = EMPTY_DOCUMENT;
        this.readonly = false;
        this.placeholder = '';
        this.autofocus = false;
        this.fileUrlBase = '';
        this.mentionProvider = null;
        this.markdownParser = null;
        this._ready = false;
        this._slashOpen = false;
        this._slashQuery = '';
        this._slashAnchor = null;
        this._bubble = null;
        this._bubbleAnchor = null;
        this._linkOpen = false;
        this._linkHref = '';
        this._highlightOpen = false;
        this._mentionOpen = false;
        this._mentionItems = [];
        this._mentionAnchor = null;
        this._mentionQuery = '';
        this._mentionSeq = 0;
        this._handleTop = -1;
        this._handleBlockPos = -1;
        this._blockMenuAnchor = null;
        this._suppressBlockMenuClick = false;
        this._inTable = false;
        this._tableAnchor = null;
        this._error = '';
        this._view = null;
        this._pm = null;
        this._schema = null;
        this._commands = null;
        /**
         * Документ, который редактор сам отдал наружу последним изменением.
         *
         * Хозяин обычно связывает `.value` со своим состоянием и перерисовывается
         * по другим причинам — индикатор сохранения, оглавление. Если он при этом
         * пришлёт то же значение, применять его нельзя: `updated()` у Lit
         * асинхронный, к его вызову набранный символ уже в документе, и повторная
         * установка состояния стёрла бы ввод.
         */
        this._emittedValue = null;
        this._onHostPointerMove = this._onHostPointerMove.bind(this);
        this._onShellPointerLeave = this._onShellPointerLeave.bind(this);
    }

    override async firstUpdated(): Promise<void> {
        await this._adoptEditorStyles();
        await this._initEditor();
    }

    /**
     * Область правки живёт в light DOM, поэтому её стили — глобальный
     * `prosemirror.css` из index.html. Внутри shadow root страницы глобальный
     * лист не действует, и тот же файл подключается в этот корень.
     */
    async _adoptEditorStyles(): Promise<void> {
        const root = this.getRootNode();
        if (!(root instanceof ShadowRoot)) {
            return;
        }
        const sheet = await StyleCache.load(EDITOR_STYLESHEET_URL);
        if (root.adoptedStyleSheets.includes(sheet)) {
            return;
        }
        root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        if (this._view) {
            this._view.destroy();
            this._view = null;
        }
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('value') && this._view && this.value !== this._emittedValue) {
            this._applyExternalValue();
        }
        if ((changed.has('readonly') || changed.has('fileUrlBase')) && this._view) {
            this._view.setProps({
                editable: () => !this.readonly,
                nodeViews: this._nodeViews(),
            });
            this._view.dispatch(this._view.state.tr);
        }
        // Подсказка живёт в decoration, а не в атрибуте: пустая транзакция
        // пересчитывает её при смене локали.
        if (changed.has('placeholder') && this._view) {
            this._view.dispatch(this._view.state.tr);
        }
    }

    async _initEditor(): Promise<void> {
        const host = this.querySelector('.pm-host');
        if (!host) return;

        let runtime: Awaited<ReturnType<typeof loadWikiEditorRuntime>>;
        let cm: CmModule;
        try {
            [runtime, cm] = await Promise.all([loadWikiEditorRuntime(), loadCodeMirrorBundle()]);
        } catch (error) {
            this._error = String(error);
            return;
        }

        const { pm, schema } = runtime;
        this._pm = pm;
        this._schema = schema;
        this._cm = cm;
        this._commands = buildBlockCommands(pm, schema);

        const plugins = [
            buildInputRules(pm, schema),
            buildKeymap(pm, schema, {
                onPasteMarkdown: () => {
                    void this._pasteAsMarkdown();
                },
                onLink: () => {
                    this._openLinkEditor();
                },
            }),
            pm.keymap(pm.baseKeymap),
            pm.history(),
            pm.dropCursor({ color: 'var(--accent)', width: 2, class: 'pm-dropcursor' }),
            pm.gapCursor(),
            pm.tableEditing(),
            pm.columnResizing(),
            this._slashPlugin(),
            this._mentionPlugin(),
            this._placeholderPlugin(),
        ];

        const state = pm.EditorState.create({
            doc: schema.nodeFromJSON(this.value || EMPTY_DOCUMENT),
            plugins,
        });

        this._view = new pm.EditorView(host, {
            state,
            editable: () => !this.readonly,
            attributes: { class: 'pm-editor' },
            nodeViews: this._nodeViews(),
            // Клик по уже стоящей каретке транзакции не даёт, поэтому кнопки
            // блока подтягиваются к строке ещё и на фокусе.
            handleDOMEvents: {
                focus: () => {
                    this._syncHandleToSelection();
                    return false;
                },
                drop: (_view: PmViewLike, event: DragEvent) => this._onEditorDrop(event),
            },
            dispatchTransaction: (transaction: PmTransactionLike) => this._onTransaction(transaction),
        });

        host.addEventListener('pointermove', this._onHostPointerMove);
        // Уход отслеживает вся оболочка: кнопки блока лежат в полосе слева, вне
        // области правки, и на пути мыши к ним не должны пропадать.
        this.querySelector('.pm-shell')?.addEventListener('pointerleave', this._onShellPointerLeave);

        this._ready = true;
        if (this.autofocus && !this.readonly) {
            this._view.focus();
            this._syncHandleToSelection();
        }
    }

    _nodeViews(): Record<string, unknown> {
        return buildWikiNodeViews({
            cm: this._cm,
            getFileUrlBase: () => {
                if (typeof this.fileUrlBase === 'string' && this.fileUrlBase.length > 0) {
                    return this.fileUrlBase;
                }
                return resolveDefaultFileUrlBase();
            },
            isEditable: () => !this.readonly,
            onOpenFile: this.readonly
                ? undefined
                : (fileId: string) => {
                    if (typeof fileId !== 'string' || fileId.length === 0) {
                        throw new Error('platform-rich-editor: onOpenFile fileId required');
                    }
                    this.openFile(fileId, { source: 'wiki_editor' });
                },
        });
    }

    // --- плагины ---

    _slashPlugin(): unknown {
        const pm = this._pm;
        if (!pm) return null;
        return new pm.Plugin({
            key: new pm.PluginKey('wiki-slash-menu'),
            props: {
                handleTextInput: (view: PmViewLike, from: number, _to: number, text: string) => {
                    if (text !== '/') return false;
                    const before = view.state.doc.textBetween(Math.max(0, from - 1), from, '\n', '\n');
                    // Меню открывается только в начале блока или после пробела:
                    // иначе слэш в пути вида /api/v1 превращался бы в меню.
                    if (before && before !== ' ' && before !== '\n') return false;
                    this._slashOpen = true;
                    this._slashQuery = '';
                    return false;
                },
                handleKeyDown: (_view: PmViewLike, event: KeyboardEvent) => {
                    if (!this._slashOpen) return false;
                    if (event.key === 'Escape') {
                        this._slashOpen = false;
                        return true;
                    }
                    if (event.key === 'Enter') {
                        const items = this._filteredSlashItems();
                        const first = items[0];
                        if (first !== undefined) {
                            this._runSlashCommand(first.command);
                            return true;
                        }
                    }
                    return false;
                },
            },
        });
    }

    _mentionPlugin(): unknown {
        const pm = this._pm;
        if (!pm) return null;
        return new pm.Plugin({
            key: new pm.PluginKey('wiki-mention-menu'),
            props: {
                handleTextInput: (view: PmViewLike, from: number, _to: number, text: string) => {
                    if (text !== '@' || typeof this.mentionProvider !== 'function') return false;
                    const before = view.state.doc.textBetween(Math.max(0, from - 1), from, '\n', '\n');
                    if (before && before !== ' ' && before !== '\n') return false;
                    this._mentionOpen = true;
                    this._mentionQuery = '';
                    void this._loadMentions('');
                    return false;
                },
                handleKeyDown: (_view: PmViewLike, event: KeyboardEvent) => {
                    if (!this._mentionOpen) return false;
                    if (event.key === 'Escape') {
                        this._mentionOpen = false;
                        return true;
                    }
                    const first = this._mentionItems[0];
                    if (event.key === 'Enter' && first !== undefined) {
                        this._pickMention(first);
                        return true;
                    }
                    return false;
                },
            },
        });
    }

    /**
     * Подсказка на пустом абзаце.
     *
     * ProseMirror держит в пустом абзаце `<br>`, поэтому CSS-селектор `:empty`
     * на нём не срабатывает — пустоту определяет схема документа, а не разметка.
     */
    _placeholderPlugin(): unknown {
        const pm = this._pm;
        if (!pm) return null;
        return new pm.Plugin({
            key: new pm.PluginKey('wiki-placeholder'),
            props: {
                decorations: (state: PmStateLike) => {
                    if (this.placeholder === '') return null;
                    const target = this._placeholderBlock(state);
                    if (target === null) return null;
                    return pm.DecorationSet.create(state.doc, [
                        pm.Decoration.node(target.pos, target.pos + target.node.nodeSize, {
                            class: 'is-empty',
                            'data-placeholder': this.placeholder,
                        }),
                    ]);
                },
            },
        });
    }

    /**
     * Где показывать подсказку: на пустом абзаце под курсором, а в нетронутом
     * документе — на единственном абзаце, чтобы её было видно до первого клика.
     */
    _placeholderBlock(state: PmStateLike): { pos: number; node: PmNodeLike } | null {
        const { doc, selection } = state;
        const isEmptyParagraph = (node: PmNodeLike | null): node is PmNodeLike =>
            node !== null && node.type.name === 'paragraph' && node.content.size === 0;
        const { $from } = selection;
        if (selection.empty && $from.depth === 1 && isEmptyParagraph($from.parent)) {
            return { pos: $from.before(1), node: $from.parent };
        }
        if (doc.childCount === 1 && isEmptyParagraph(doc.firstChild)) {
            return { pos: 0, node: doc.firstChild };
        }
        return null;
    }

    // --- транзакции и состояние слоёв ---

    _onTransaction(transaction: PmTransactionLike): void {
        if (!this._view) return;
        const nextState = this._view.state.apply(transaction);
        this._view.updateState(nextState);

        if (this._slashOpen) {
            const slashQuery = this._queryBefore(nextState, '/');
            if (slashQuery === null) {
                this._slashOpen = false;
                this._slashQuery = '';
            } else {
                this._slashQuery = slashQuery;
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

        this._syncHandleToSelection();
        this._bubble = this._bubbleState(nextState);
        this._bubbleAnchor = this._bubble === null ? null : this._selectionAnchor(nextState);
        // Контролы таблицы нужны при курсоре в ячейке, а не только при выделении.
        this._inTable = this._isInTable(nextState);
        this._tableAnchor = this._inTable ? this._selectionAnchor(nextState) : null;

        if (!transaction.docChanged) return;
        this._emittedValue = nextState.doc.toJSON();
        this.value = this._emittedValue;
        this.emit('change', { content: this._emittedValue });
    }

    /** Прямоугольник текущего выделения в координатах viewport — якорь для popover. */
    _selectionAnchor(state: PmStateLike): PopoverAnchor {
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

    _queryBefore(state: PmStateLike, trigger: '/' | '@'): string | null {
        const { $from } = state.selection;
        const textBefore = $from.parent.textBetween(0, $from.parentOffset, '\n', '\n');
        const pattern = trigger === '/' ? /\/([\p{L}\w-]*)$/u : /@([\p{L}\w-]*)$/u;
        const match = pattern.exec(textBefore);
        if (match === null) return null;
        const query = match[1];
        return query === undefined ? null : query;
    }

    _bubbleState(state: PmStateLike): BubbleState | null {
        if (this.readonly || state.selection.empty) return null;
        const marks: Record<string, PmMarkTypeLike | undefined> = this._schema ? this._schema.marks : {};
        const isActive = (markType: PmMarkTypeLike | undefined): boolean => {
            if (!markType) return false;
            const { from, $from, to, empty } = state.selection;
            return empty
                ? Boolean(markType.isInSet(state.storedMarks || $from.marks()))
                : state.doc.rangeHasMark(from, to, markType);
        };
        let highlightColor = '';
        if (marks.highlight && isActive(marks.highlight)) {
            const { from, to } = state.selection;
            state.doc.nodesBetween(from, to, (node: PmNodeLike) => {
                if (highlightColor !== '') return false;
                for (const mark of node.marks) {
                    if (mark.type === marks.highlight) {
                        highlightColor = String(mark.attrs.color || 'yellow');
                        return false;
                    }
                }
                return true;
            });
        }
        let linkHref = '';
        if (marks.link && isActive(marks.link)) {
            const { from, to } = state.selection;
            state.doc.nodesBetween(from, to, (node: PmNodeLike) => {
                if (linkHref !== '') return false;
                for (const mark of node.marks) {
                    if (mark.type === marks.link) {
                        const href = mark.attrs.href;
                        linkHref = typeof href === 'string' ? href : '';
                        return false;
                    }
                }
                return true;
            });
        }
        return {
            strong: isActive(marks.strong),
            em: isActive(marks.em),
            code: isActive(marks.code),
            strike: isActive(marks.strike),
            highlight: isActive(marks.highlight),
            highlightColor,
            link: isActive(marks.link),
            linkHref,
        };
    }

    _isInTable(state: PmStateLike): boolean {
        const { $from } = state.selection;
        for (let depth = $from.depth; depth > 0; depth -= 1) {
            if ($from.node(depth).type.name === 'table') {
                return true;
            }
        }
        return false;
    }

    _applyExternalValue(): void {
        if (!this._view || !this._schema || !this._pm) return;
        const nextDoc = this._schema.nodeFromJSON(this.value || EMPTY_DOCUMENT);
        if (nextDoc.eq(this._view.state.doc)) return;
        const state = this._pm.EditorState.create({
            doc: nextDoc,
            plugins: this._view.state.plugins,
        });
        this._view.updateState(state);
    }

    // --- команды по слэшу ---

    _filteredSlashItems(): SlashItem[] {
        const query = this._slashQuery.toLowerCase();
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

    _runSlashCommand(commandName: string): void {
        if (!this._view) return;

        // Слэш и набранный после него фильтр — часть команды, а не текста.
        this._dropTriggerText('/');
        this._slashOpen = false;
        this._slashQuery = '';

        if (commandName === 'image') {
            this._requestFilePick('image');
            return;
        }
        if (commandName === 'platform_file') {
            this._requestFilePick('file');
            return;
        }

        const command = this._commands?.[commandName];
        if (!command) {
            throw new Error(`platform-rich-editor: unknown slash command ${commandName}`);
        }
        command(this._view.state, this._view.dispatch.bind(this._view));
        this._view.focus();
    }

    /**
     * Загрузка/выбор файла — доменный шаг (wiki → Documents). Редактор только
     * просит наружу; insertImage / insertPlatformFile вызываются после выбора.
     */
    _requestFilePick(kind: string): void {
        if (kind !== 'image' && kind !== 'file') {
            throw new Error(`platform-rich-editor: unknown file pick kind ${kind}`);
        }
        this.emit('file-pick-requested', { kind });
    }

    /** Убрать из документа текст-триггер вместе с набранным фильтром. */
    _dropTriggerText(trigger: '/' | '@'): void {
        if (!this._view) return;
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

    async _loadMentions(query: string): Promise<void> {
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

    _pickMention(item: MentionItem): void {
        if (!this._view || !this._schema) return;
        this._dropTriggerText('@');
        // Провайдер отдаёт UI-форму (id/kind/label); схема хранит свою.
        const mention: MentionPayload = { mentionKind: item.kind, targetId: item.id, label: item.label };
        const view = this._view;
        insertMentionCommand(this._schema, mention)(view.state, view.dispatch.bind(view));
        this._mentionOpen = false;
        this._mentionQuery = '';
        this._mentionItems = [];
        this._view.focus();
    }

    _toggleMark(markName: string): void {
        if (!this._view || !this._schema) return;
        const markType = this._schema.marks[markName];
        if (!markType) return;
        if (!this._pm) return;
        const view = this._view;
        this._pm.toggleMark(markType)(view.state, view.dispatch.bind(view));
        this._view.focus();
    }

    _openLinkEditor(): void {
        if (this.readonly || this._view === null) {
            return;
        }
        if (this._view.state.selection.empty) {
            return;
        }
        const bubble = this._bubbleState(this._view.state);
        this._linkHref = bubble && typeof bubble.linkHref === 'string' ? bubble.linkHref : '';
        this._linkOpen = true;
        this._highlightOpen = false;
    }

    _applyLink(): void {
        if (!this._view || !this._schema) {
            return;
        }
        const href = typeof this._linkHref === 'string' ? this._linkHref.trim() : '';
        const view = this._view;
        setLinkCommand(this._schema, href)(view.state, view.dispatch.bind(view));
        this._linkOpen = false;
        this._view.focus();
    }

    _removeLink(): void {
        if (!this._view || !this._schema) {
            return;
        }
        const view = this._view;
        setLinkCommand(this._schema, '')(view.state, view.dispatch.bind(view));
        this._linkOpen = false;
        this._linkHref = '';
        this._view.focus();
    }

    _applyHighlightColor(color: string): void {
        if (!this._view || !this._schema) {
            return;
        }
        const view = this._view;
        setHighlightColorCommand(this._schema, color)(view.state, view.dispatch.bind(view));
        this._highlightOpen = false;
        this._view.focus();
    }

    // --- ручка блока ---

    _onHostPointerMove(event: Event): void {
        if (!this._view || this.readonly) return;
        const host = this.querySelector('.pm-host');
        if (!host) return;
        const found = this._view.posAtCoords({
            left: host.getBoundingClientRect().left + BLOCK_PROBE_INSET_PX,
            top: event instanceof MouseEvent ? event.clientY : 0,
        });
        if (!found) {
            this._handleTop = -1;
            this._handleBlockPos = -1;
            return;
        }
        this._showHandleForBlock(this._blockPosAt(this._view.state, found.pos));
    }

    _onShellPointerLeave(): void {
        if (this._blockMenuAnchor !== null) return;
        // Курсор в тексте — кнопки остаются у своей строки: иначе после ухода
        // мыши единственный способ добавить блок снова пришлось бы искать.
        if (this._view !== null && this._view.hasFocus()) {
            this._syncHandleToSelection();
            return;
        }
        this._handleTop = -1;
    }

    /** Позиция блока верхнего уровня, внутри которого лежит позиция документа. */
    _blockPosAt(state: PmStateLike, pos: number): number {
        const resolved = state.doc.resolve(pos);
        return resolved.depth === 0 ? pos : resolved.before(1);
    }

    _syncHandleToSelection(): void {
        if (this.readonly || this._view === null) return;
        const { state } = this._view;
        this._showHandleForBlock(this._blockPosAt(state, state.selection.from));
    }

    _showHandleForBlock(blockPos: number): void {
        const host = this.querySelector('.pm-host');
        const dom = this._view === null ? null : this._view.nodeDOM(blockPos);
        const element = dom instanceof Element ? dom : null;
        if (host === null || element === null) {
            this._handleTop = -1;
            return;
        }
        this._handleTop = element.getBoundingClientRect().top - host.getBoundingClientRect().top;
        this._handleBlockPos = blockPos;
    }

    _openBlockMenu(event: Event): void {
        // После drag браузер иногда шлёт click на ту же кнопку — меню не открываем.
        if (this._suppressBlockMenuClick) {
            this._suppressBlockMenuClick = false;
            event.preventDefault();
            return;
        }
        event.preventDefault();
        this._blockMenuAnchor = event.currentTarget instanceof Element ? event.currentTarget : null;
    }

    _blockMenuItems(): BlockMenuAction[] {
        return BLOCK_MENU_ACTIONS.map((action) => (
            action.kind === 'separator'
                ? action
                : { ...action, label: this.t(`editor.block_menu.${action.id}`) }
        ));
    }

    _onBlockMenuSelect(event: Event): void {
        const detail = eventRecord(event, 'menu-select');
        if (typeof detail.id !== 'string' || detail.id.length === 0) {
            throw new Error('platform-rich-editor: menu-select id must be a non-empty string');
        }
        const actionId = detail.id;
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
        const command = this._commands?.[commandName];
        if (!command) {
            throw new Error(`platform-rich-editor: нет команды блока ${commandName}`);
        }
        // Команда работает от выделения, поэтому курсор сначала переносится в блок.
        if (!this._pm) return;
        const view = this._view;
        const selection = this._pm.TextSelection.create(state.doc, this._handleBlockPos + 1);
        view.dispatch(state.tr.setSelection(selection));
        command(view.state, view.dispatch.bind(view));
        view.focus();
    }

    /**
     * Кнопка «плюс» у блока: курсор уходит в пустой абзац и открывается то же
     * меню команд, что по слэшу. Слэш вставляется в текст, поэтому дальнейшая
     * фильтрация набором работает как при обычном вводе.
     */
    _onHandleAdd(): void {
        if (!this._view || !this._schema || !this._pm || this._handleBlockPos < 0) return;
        const { state } = this._view;
        const node = state.doc.nodeAt(this._handleBlockPos);
        if (!node) return;

        const paragraph = this._schema.nodes.paragraph;
        if (!paragraph) return;
        if (node.type === paragraph && node.content.size === 0) {
            const selection = this._pm.TextSelection.create(state.doc, this._handleBlockPos + 1);
            this._view.dispatch(state.tr.setSelection(selection));
        } else {
            const insertAt = this._handleBlockPos + node.nodeSize;
            const transaction = state.tr.insert(insertAt, paragraph.create());
            transaction.setSelection(this._pm.TextSelection.create(transaction.doc, insertAt + 1));
            this._view.dispatch(transaction);
        }

        this._slashOpen = true;
        this._slashQuery = '';
        this._view.focus();
        this._view.dispatch(this._view.state.tr.insertText('/'));
    }

    _onHandleDragStart(event: Event): void {
        if (!this._view || !this._pm || this._handleBlockPos < 0) return;
        if (!(event instanceof DragEvent) || !(event.dataTransfer instanceof DataTransfer)) {
            throw new Error('platform-rich-editor: dragstart without dataTransfer');
        }
        const node = this._view.state.doc.nodeAt(this._handleBlockPos);
        if (!node) return;
        // Ручка лежит вне contenteditable, поэтому встроенный dragstart ProseMirror
        // не срабатывает. Собираем тот же контракт: NodeSelection + clipboard slice
        // + view.dragging — drop и dropcursor подхватят его сами.
        // Selection в документ не пишем: иначе bubble/handle обновят Lit-state и
        // кнопка пересоздастся — браузер оборвёт drag.
        const selection = this._pm.NodeSelection.create(this._view.state.doc, this._handleBlockPos);
        const { dom, text, slice } = this._view.serializeForClipboard(selection.content());
        event.dataTransfer.clearData();
        event.dataTransfer.setData('text/html', dom.innerHTML);
        event.dataTransfer.setData('text/plain', text);
        event.dataTransfer.effectAllowed = 'copyMove';
        this._view.dragging = { slice, move: true, node: selection };

        const blockDom = this._view.nodeDOM(this._handleBlockPos);
        if (blockDom instanceof HTMLElement) {
            blockDom.classList.add('ProseMirror-selectednode');
            event.dataTransfer.setDragImage(blockDom, 0, 0);
        }
    }

    _onHandleDragEnd(): void {
        // После drag браузер иногда шлёт click на ту же кнопку — меню глушим
        // только на этот тик; иначе следующий осознанный клик тоже пропадёт.
        this._suppressBlockMenuClick = true;
        const view = this._view;
        const dragging = view === null ? null : view.dragging;
        const from = dragBlockFrom(dragging);
        if (view !== null && from !== null) {
            const blockDom = view.nodeDOM(from);
            if (blockDom instanceof HTMLElement) {
                blockDom.classList.remove('ProseMirror-selectednode');
            }
        }
        window.setTimeout(() => {
            this._suppressBlockMenuClick = false;
            if (view !== null && view.dragging === dragging) {
                view.dragging = null;
            }
        }, 50);
    }

    // --- таблицы ---

    _runTableCommand(actionId: string): void {
        if (!this._pm || !this._view) return;
        const command = this._pm[actionId];
        if (!isPmCommand(command)) {
            throw new Error(`platform-rich-editor: нет табличной команды ${actionId}`);
        }
        const view = this._view;
        command(view.state, view.dispatch.bind(view));
        view.focus();
    }

    // --- markdown ---

    /**
     * Перетащенный `.md` уходит наверх событием, а не разбирается здесь:
     * решение «заменить страницу или вставить в текст» доменное, и принимать его
     * редактору не по чину.
     */
    _onEditorDrop(event: DragEvent): boolean {
        const file = this._markdownFileFrom(event.dataTransfer);
        if (file === null) {
            return false;
        }
        event.preventDefault();
        this.emit('markdown-file-drop', { file });
        return true;
    }

    _markdownFileFrom(transfer: DataTransfer | null): File | null {
        if (!transfer || !transfer.files || transfer.files.length !== 1) {
            return null;
        }
        const file = transfer.files[0];
        if (file === undefined) {
            return null;
        }
        const name = typeof file.name === 'string' ? file.name.toLowerCase() : '';
        const isMarkdown = name.endsWith('.md')
            || name.endsWith('.markdown')
            || file.type === 'text/markdown';
        return isMarkdown ? file : null;
    }

    /** Вставить содержимое буфера как markdown, а не как обычный текст. */
    async _pasteAsMarkdown(): Promise<void> {
        if (typeof this.markdownParser !== 'function' || this._view === null) {
            return;
        }
        const text = await navigator.clipboard.readText();
        if (text.trim() === '') {
            return;
        }
        await this.insertMarkdown(text);
    }

    /**
     * Вставить markdown в позицию курсора.
     * @param {string} markdown
     */
    async insertMarkdown(markdown: string): Promise<void> {
        if (typeof this.markdownParser !== 'function') {
            throw new Error('platform-rich-editor: markdownParser required to insert markdown');
        }
        const document = await this.markdownParser(markdown);
        if (this._view === null || !document || typeof document !== 'object') {
            return;
        }
        // Разбор отдаёт целый `doc`; вставляется его содержимое, иначе документ
        // оказался бы вложен в документ.
        if (!this._schema || !this._pm) return;
        const parsed = this._schema.nodeFromJSON(document);
        const slice = new this._pm.Slice(parsed.content, 0, 0);
        const { state } = this._view;
        this._view.dispatch(state.tr.replaceSelection(slice).scrollIntoView());
        this._view.focus();
    }

    // --- публичный API ---

    /** Вставить упоминание пользователя, сущности, страницы или документа. */
    insertMention(mention: MentionPayload): void {
        if (!this._view || !this._schema) return;
        const view = this._view;
        insertMentionCommand(this._schema, mention)(view.state, view.dispatch.bind(view));
        view.focus();
    }

    /** Вставить карточку документа платформы. */
    insertPlatformFile(file: PlatformFilePayload): void {
        if (!this._view || !this._schema) return;
        const view = this._view;
        insertPlatformFileCommand(this._schema, file)(view.state, view.dispatch.bind(view));
        view.focus();
    }

    /** Вставить картинку с платформенным `file_id`. */
    insertImage(image: ImagePayload): void {
        if (!this._view || !this._schema) return;
        const view = this._view;
        insertImageCommand(this._schema, image)(view.state, view.dispatch.bind(view));
        view.focus();
    }

    /** Оглавление страницы: заголовки в порядке документа. */
    getOutline(): Array<{ level: number; text: string; pos: number }> {
        if (!this._view) return [];
        const outline: Array<{ level: number; text: string; pos: number }> = [];
        this._view.state.doc.descendants((node: PmNodeLike, pos: number) => {
            if (node.type.name === 'heading') {
                outline.push({ level: Number(node.attrs.level), text: node.textContent, pos });
            }
            return true;
        });
        return outline;
    }

    get isReady(): boolean {
        return this._view !== null;
    }

    /** Прокрутить к заголовку из оглавления. */
    scrollToPosition(pos: number): void {
        if (!this._view) {
            throw new Error('platform-rich-editor: editor not ready');
        }
        if (typeof pos !== 'number' || !Number.isFinite(pos)) {
            throw new Error(`platform-rich-editor: outline position must be a number, got ${String(pos)}`);
        }
        const { doc } = this._view.state;
        if (pos < 0 || pos > doc.content.size) {
            throw new Error(
                `platform-rich-editor: outline position ${pos} out of range 0..${doc.content.size}`,
            );
        }
        const heading = doc.resolve(pos).nodeAfter;
        if (!heading || heading.type.name !== 'heading') {
            throw new Error(`platform-rich-editor: outline position ${pos} is not a heading`);
        }
        // Outline отдаёт позицию перед узлом — outer DOM heading через nodeDOM.
        // Если DOM ещё не привязан (смена doc после save) — берём через domAtPos.
        const posDom = this._view.nodeDOM(pos);
        let element: Element | null = posDom instanceof Element ? posDom : null;
        if (!(element instanceof Element)) {
            const inside = Math.min(pos + 1, doc.content.size);
            const domAt = this._view.domAtPos(inside);
            const start = domAt.node instanceof Element ? domAt.node : domAt.node.parentElement;
            if (!(start instanceof Element)) {
                throw new Error(`platform-rich-editor: no DOM node at outline position ${pos}`);
            }
            const closestHeading = start.closest('h1, h2, h3, h4, h5, h6');
            element = closestHeading instanceof Element ? closestHeading : start;
        }
        const scroller = this.closest('[data-wiki-page-scroll]');
        if (scroller instanceof HTMLElement) {
            const topbar = scroller.querySelector('.topbar');
            const stickyOffset = topbar instanceof HTMLElement ? topbar.getBoundingClientRect().height : 0;
            const scrollerRect = scroller.getBoundingClientRect();
            const targetRect = element.getBoundingClientRect();
            scroller.scrollTop = scroller.scrollTop
                + (targetRect.top - scrollerRect.top)
                - stickyOffset
                - 8;
            return;
        }
        element.scrollIntoView({ behavior: 'auto', block: 'start' });
    }

    override render(): TemplateResult {
        return html`
            <div class="pm-shell" data-ready=${this._ready ? 'true' : 'false'}>
                ${this._error
                    ? html`<div class="pm-error">${this.t('editor.load_failed')}</div>`
                    : ''}
                ${this._renderBlockHandle()}
                <div class="pm-host"></div>
                ${this._renderBubblePopover()}
                ${this._renderLinkPopover()}
                ${this._renderHighlightPopover()}
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
                    class="pm-block-add-btn"
                    aria-label=${this.t('editor.add_block')}
                    title=${this.t('editor.add_block')}
                    @click=${this._onHandleAdd}
                >
                    <platform-icon name="plus" size="18"></platform-icon>
                </button>
                <button
                    type="button"
                    class="pm-block-handle-btn"
                    draggable="true"
                    aria-label=${this.t('editor.block_menu.aria')}
                    @dragstart=${this._onHandleDragStart}
                    @dragend=${this._onHandleDragEnd}
                    @click=${this._openBlockMenu}
                >
                    <platform-icon name="drag-handle" size="18"></platform-icon>
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
        const bubble = this._bubble;
        const marks: Array<{ name: 'strong' | 'em' | 'strike' | 'code'; icon: string }> = [
            { name: 'strong', icon: 'bold' },
            { name: 'em', icon: 'italic' },
            { name: 'strike', icon: 'strikethrough' },
            { name: 'code', icon: 'code' },
        ];
        return html`
            <platform-popover
                trigger="manual"
                role="dialog"
                placement="top"
                offset="8"
                dismiss-on-outside="false"
                .anchor=${this._bubbleAnchor}
                ?open=${this._bubble !== null && !this._linkOpen && !this._highlightOpen}
            >
                ${bubble !== null
                    ? html`
                        <div class="pm-bubble" role="toolbar" aria-label=${this.t('editor.format_toolbar')}>
                            ${marks.map(
                                (mark) => html`
                                    <button
                                        type="button"
                                        class="pm-bubble-btn ${bubble[mark.name] ? 'is-active' : ''}"
                                        aria-pressed=${bubble[mark.name] ? 'true' : 'false'}
                                        title=${this.t(`editor.mark.${mark.name}`)}
                                        @mousedown=${(event: MouseEvent) => event.preventDefault()}
                                        @click=${() => this._toggleMark(mark.name)}
                                    >
                                        <platform-icon name=${mark.icon} size="16"></platform-icon>
                                    </button>
                                `,
                            )}
                            <span class="pm-bubble-sep"></span>
                            <button
                                type="button"
                                class="pm-bubble-btn ${bubble.link ? 'is-active' : ''}"
                                data-editor-link
                                aria-pressed=${bubble.link ? 'true' : 'false'}
                                title=${this.t('editor.mark.link')}
                                @mousedown=${(event: MouseEvent) => event.preventDefault()}
                                @click=${() => this._openLinkEditor()}
                            >
                                <platform-icon name="link" size="16"></platform-icon>
                            </button>
                            <button
                                type="button"
                                class="pm-bubble-btn ${bubble.highlight ? 'is-active' : ''}"
                                data-editor-highlight
                                aria-pressed=${bubble.highlight ? 'true' : 'false'}
                                title=${this.t('editor.mark.highlight')}
                                @mousedown=${(event: MouseEvent) => event.preventDefault()}
                                @click=${() => { this._highlightOpen = true; this._linkOpen = false; }}
                            >
                                <platform-icon name="highlighter" size="16"></platform-icon>
                            </button>
                        </div>
                    `
                    : nothing}
            </platform-popover>
        `;
    }

    _renderLinkPopover() {
        return html`
            <platform-popover
                trigger="manual"
                role="dialog"
                placement="top"
                offset="8"
                .anchor=${this._bubbleAnchor}
                ?open=${this._linkOpen}
                @popover-dismiss=${() => { this._linkOpen = false; }}
            >
                ${this._linkOpen
                    ? html`
                        <div class="pm-link-editor" data-editor-link-form>
                            <platform-field
                                input-type="url"
                                label=${this.t('editor.link.href')}
                                .value=${this._linkHref}
                                @change=${(event: Event) => {
                                    const value = eventRecord(event, 'link change').value;
                                    this._linkHref = value === undefined || value === null ? '' : String(value);
                                }}
                            ></platform-field>
                            <div class="pm-link-actions">
                                <button
                                    type="button"
                                    class="pm-bubble-btn"
                                    data-editor-link-apply
                                    @mousedown=${(event: MouseEvent) => event.preventDefault()}
                                    @click=${() => this._applyLink()}
                                >
                                    ${this.t('editor.link.apply')}
                                </button>
                                <button
                                    type="button"
                                    class="pm-bubble-btn"
                                    data-editor-link-remove
                                    @mousedown=${(event: MouseEvent) => event.preventDefault()}
                                    @click=${() => this._removeLink()}
                                >
                                    ${this.t('editor.link.remove')}
                                </button>
                            </div>
                        </div>
                    `
                    : nothing}
            </platform-popover>
        `;
    }

    _renderHighlightPopover() {
        return html`
            <platform-popover
                trigger="manual"
                role="dialog"
                placement="top"
                offset="8"
                .anchor=${this._bubbleAnchor}
                ?open=${this._highlightOpen}
                @popover-dismiss=${() => { this._highlightOpen = false; }}
            >
                ${this._highlightOpen
                    ? html`
                        <div class="pm-highlight-swatches" role="listbox" aria-label=${this.t('editor.mark.highlight')}>
                            ${HIGHLIGHT_COLORS.map(
                                (color) => html`
                                    <button
                                        type="button"
                                        class="pm-highlight-swatch ${this._bubble?.highlightColor === color ? 'is-active' : ''}"
                                        data-highlight-color=${color}
                                        title=${this.t(`editor.highlight.${color}`)}
                                        style=${`--swatch: var(--wiki-highlight-${color})`}
                                        @mousedown=${(event: MouseEvent) => event.preventDefault()}
                                        @click=${() => this._applyHighlightColor(color)}
                                    ></button>
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
                        @mousedown=${(event: MouseEvent) => event.preventDefault()}
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
                                            @mousedown=${(event: MouseEvent) => event.preventDefault()}
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
                                            @mousedown=${(event: MouseEvent) => event.preventDefault()}
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

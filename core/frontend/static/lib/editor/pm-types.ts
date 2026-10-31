/**
 * Структурные типы поверхности lazy prosemirror-чанка.
 *
 * Бандл грузится по URL и не имеет деклараций — здесь описан только тот
 * минимум, который реально используют wiki-редактор и его nodeviews. Это не
 * обёртка вокруг API, а точное описание существующего контракта.
 */

export interface PmAttrs {
    attrs: Record<string, unknown>;
}

export interface PmNodeTypeLike {
    name: string;
    create(attrs?: Record<string, unknown> | null, content?: unknown): PmNodeLike;
    [key: string]: unknown;
}

export interface PmMarkTypeLike {
    name?: string;
    create(attrs?: Record<string, unknown>): PmMarkLike;
    isInSet(marks: readonly PmMarkLike[] | null): PmMarkLike | undefined;
}

export interface PmMarkLike {
    type: PmMarkTypeLike;
    attrs: Record<string, unknown>;
}

export interface PmResolvedPosLike {
    pos: number;
    depth: number;
    parent: PmNodeLike;
    parentOffset: number;
    nodeAfter: PmNodeLike | null;
    node(depth?: number): PmNodeLike;
    index(depth?: number): number;
    before(depth?: number): number;
    marks(): PmMarkLike[];
    [key: string]: unknown;
}

export interface PmSliceLike {
    content: unknown;
    openStart: number;
    openEnd: number;
    [key: string]: unknown;
}

export interface PmSelectionLike {
    from: number;
    to: number;
    empty: boolean;
    $from: PmResolvedPosLike;
    content(): PmSliceLike;
    [key: string]: unknown;
}

export interface PmNodeLike extends PmAttrs {
    type: PmNodeTypeLike;
    childCount: number;
    content: { size: number };
    firstChild: PmNodeLike | null;
    marks: readonly PmMarkLike[];
    isAtom: boolean;
    nodeSize: number;
    textContent: string;
    descendants(callback: (node: PmNodeLike, pos: number) => boolean | void): void;
    nodesBetween(from: number, to: number, callback: (node: PmNodeLike) => boolean | void): void;
    textBetween(from: number, to: number, blockSeparator?: string, leafText?: string): string;
    nodeAt(pos: number): PmNodeLike | null;
    resolve(pos: number): PmResolvedPosLike;
    rangeHasMark(from: number, to: number, markType: PmMarkTypeLike): boolean;
    copy(content?: unknown): PmNodeLike;
    eq(other: PmNodeLike): boolean;
    toJSON(): Record<string, unknown>;
    [key: string]: unknown;
}

export interface PmTransactionLike {
    doc: PmNodeLike;
    docChanged: boolean;
    replaceRangeWith(start: number, end: number, node: PmNodeLike): PmTransactionLike;
    replaceSelectionWith(node: PmNodeLike, inheritMarks?: boolean): PmTransactionLike;
    replaceSelection(slice: PmSliceLike): PmTransactionLike;
    replaceWith(from: number, to: number, content: unknown): PmTransactionLike;
    insert(pos: number, node: PmNodeLike): PmTransactionLike;
    insertText(text: string): PmTransactionLike;
    delete(from: number, to: number): PmTransactionLike;
    setNodeMarkup(pos: number, type: unknown, attrs?: Record<string, unknown>): PmTransactionLike;
    setSelection(selection: PmSelectionLike): PmTransactionLike;
    removeMark(from: number, to: number, markType: PmMarkTypeLike): PmTransactionLike;
    addMark(from: number, to: number, mark: PmMarkLike): PmTransactionLike;
    scrollIntoView(): PmTransactionLike;
    [key: string]: unknown;
}

export interface PmStateLike {
    tr: PmTransactionLike;
    doc: PmNodeLike;
    selection: PmSelectionLike;
    schema: PmSchemaLike;
    plugins: unknown[];
    storedMarks: readonly PmMarkLike[] | null;
    apply(tr: PmTransactionLike): PmStateLike;
    [key: string]: unknown;
}

export type PmDispatch = (tr: PmTransactionLike) => void;

export type PmCommand = (state: PmStateLike, dispatch?: PmDispatch, view?: PmViewLike) => boolean;

export interface PmViewLike {
    state: PmStateLike;
    dom: HTMLElement;
    dragging: unknown;
    dispatch(tr: PmTransactionLike): void;
    updateState(state: PmStateLike): void;
    setProps(props: Record<string, unknown>): void;
    posAtDOM(dom: Node, offset?: number): number;
    posAtCoords(coords: { left: number; top: number }): { pos: number; inside: number } | null;
    coordsAtPos(pos: number): { left: number; right: number; top: number; bottom: number };
    nodeDOM(pos: number): Node | null;
    domAtPos(pos: number): { node: Node; offset: number };
    serializeForClipboard(slice: PmSliceLike): { dom: HTMLElement; text: string; slice: PmSliceLike };
    hasFocus(): boolean;
    focus(): void;
    destroy(): void;
    [key: string]: unknown;
}

export interface PmSchemaLike {
    nodes: Record<string, PmNodeTypeLike>;
    marks: Record<string, PmMarkTypeLike | undefined>;
    text(text: string): PmNodeLike;
    nodeFromJSON(json: unknown): PmNodeLike;
    [key: string]: unknown;
}

export interface PmPluginApiLike {
    textblockTypeInputRule(
        pattern: RegExp,
        nodeType: PmNodeTypeLike,
        getAttrs?: (match: RegExpMatchArray) => Record<string, unknown>,
    ): unknown;
    wrappingInputRule(
        pattern: RegExp,
        nodeType: PmNodeTypeLike,
        getAttrs?: ((match: RegExpMatchArray) => Record<string, unknown>) | null,
        joinPredicate?: (match: RegExpMatchArray, node: PmNodeLike) => boolean,
    ): unknown;
    InputRule: new (
        pattern: RegExp,
        handler: (state: PmStateLike, match: RegExpMatchArray, start: number, end: number) => PmTransactionLike | null,
    ) => unknown;
    inputRules(opts: { rules: unknown[] }): unknown;
    toggleMark(markType: PmMarkTypeLike | undefined): PmCommand;
    undo: PmCommand;
    redo: PmCommand;
    exitCode: PmCommand;
    chainCommands(...commands: PmCommand[]): PmCommand;
    splitListItem(nodeType: PmNodeTypeLike): PmCommand;
    sinkListItem(nodeType: PmNodeTypeLike): PmCommand;
    liftListItem(nodeType: PmNodeTypeLike): PmCommand;
    setBlockType(nodeType: PmNodeTypeLike, attrs?: Record<string, unknown>): PmCommand;
    wrapInList(nodeType: PmNodeTypeLike): PmCommand;
    wrapIn(nodeType: PmNodeTypeLike, attrs?: Record<string, unknown>): PmCommand;
    keymap(keys: Record<string, PmCommand>): unknown;
}

/**
 * Весь lazy prosemirror-чанк: plugin API + конструкторы редактора,
 * selection, decorations, table-команды (доступ по имени — табличные хелперы
 * лежат прямо на объекте бандла).
 */
export interface PmBundleLike extends PmPluginApiLike {
    Schema: new (spec: { nodes: unknown; marks: unknown }) => PmSchemaLike;
    tableNodes(opts: Record<string, unknown>): Record<string, unknown>;
    EditorState: {
        create(config: { doc?: PmNodeLike; plugins?: unknown[]; schema?: PmSchemaLike }): PmStateLike;
    };
    EditorView: new (host: Element, props: Record<string, unknown>) => PmViewLike;
    Plugin: new (spec: { key?: unknown; props?: Record<string, unknown> }) => unknown;
    PluginKey: new (name: string) => unknown;
    Decoration: {
        node(from: number, to: number, attrs: Record<string, unknown>): unknown;
    };
    DecorationSet: {
        create(doc: PmNodeLike, decorations: unknown[]): unknown;
    };
    TextSelection: {
        create(doc: PmNodeLike, pos: number): PmSelectionLike;
    };
    NodeSelection: {
        create(doc: PmNodeLike, pos: number): PmSelectionLike;
    };
    Slice: new (content: unknown, openStart: number, openEnd: number) => PmSliceLike;
    baseKeymap: Record<string, PmCommand>;
    history(): unknown;
    dropCursor(options?: Record<string, unknown>): unknown;
    gapCursor(): unknown;
    tableEditing(): unknown;
    columnResizing(): unknown;
    [key: string]: unknown;
}

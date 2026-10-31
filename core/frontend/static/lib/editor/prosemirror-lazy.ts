/**
 * prosemirror-lazy — lazy-чанк ProseMirror для всех платформенных редакторов.
 * Динамический import этого модуля резолвится esbuild в отдельный чанк.
 *
 * Один модуль на всю платформу — собирать ProseMirror несколькими входами
 * нельзя: разные копии prosemirror-model ломают instanceof между схемой и
 * документом, а диагностируется это только по странному поведению редактора.
 */
export { EditorState, Plugin, PluginKey, NodeSelection, TextSelection, Selection } from 'prosemirror-state';
export { EditorView, Decoration, DecorationSet } from 'prosemirror-view';
export { DOMParser, DOMSerializer, Fragment, Mark, Node, Schema, Slice } from 'prosemirror-model';
export { ReplaceStep, Step, Transform, liftTarget, findWrapping } from 'prosemirror-transform';
export {
    baseKeymap,
    chainCommands,
    exitCode,
    joinDown,
    joinUp,
    lift,
    selectParentNode,
    setBlockType,
    toggleMark,
    wrapIn,
} from 'prosemirror-commands';
export { keymap } from 'prosemirror-keymap';
export { history, redo, undo } from 'prosemirror-history';
export {
    InputRule,
    inputRules,
    smartQuotes,
    textblockTypeInputRule,
    wrappingInputRule,
} from 'prosemirror-inputrules';
export {
    liftListItem,
    sinkListItem,
    splitListItem,
    wrapInList,
} from 'prosemirror-schema-list';
export { dropCursor } from 'prosemirror-dropcursor';
export { gapCursor } from 'prosemirror-gapcursor';
export {
    addColumnAfter,
    addColumnBefore,
    addRowAfter,
    addRowBefore,
    columnResizing,
    deleteColumn,
    deleteRow,
    deleteTable,
    goToNextCell,
    mergeCells,
    splitCell,
    tableEditing,
    tableNodes,
} from 'prosemirror-tables';

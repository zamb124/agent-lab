import { build } from 'esbuild';

// Один бандл на всю платформу. Собирать ProseMirror несколькими входами нельзя:
// разные копии prosemirror-model ломают instanceof между схемой и документом,
// а диагностируется это только по странному поведению редактора.
const ENTRY = `
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
`;

await build({
    stdin: {
        contents: ENTRY,
        resolveDir: process.cwd(),
        sourcefile: 'prosemirror-bundle-entry.js',
        loader: 'js',
    },
    outfile: 'core/frontend/static/assets/prosemirror/prosemirror-bundle.js',
    bundle: true,
    format: 'esm',
    target: 'es2022',
    minify: true,
    sourcemap: false,
    legalComments: 'none',
});

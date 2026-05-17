import { build } from 'esbuild';

const ENTRY = `
export { Compartment, EditorState, RangeSetBuilder, StateEffect, StateField } from '@codemirror/state';
export {
    Decoration,
    EditorView,
    MatchDecorator,
    ViewPlugin,
    WidgetType,
    highlightActiveLine,
    highlightActiveLineGutter,
    hoverTooltip,
    keymap,
    lineNumbers,
    showTooltip,
    tooltips,
} from '@codemirror/view';
export {
    defaultKeymap,
    history,
    historyKeymap,
    indentLess,
    indentMore,
    indentWithTab,
} from '@codemirror/commands';
export { autocompletion } from '@codemirror/autocomplete';
export {
    StreamLanguage,
    bracketMatching,
    defaultHighlightStyle,
    foldGutter,
    indentOnInput,
    syntaxHighlighting,
} from '@codemirror/language';
export { oneDark } from '@codemirror/theme-one-dark';
export { python } from '@codemirror/lang-python';
export { json } from '@codemirror/lang-json';
export { javascript } from '@codemirror/lang-javascript';
export { go } from '@codemirror/lang-go';

import { StreamLanguage } from '@codemirror/language';
import { csharp as csharpMode } from '@codemirror/legacy-modes/mode/clike';

export function csharp() {
    return StreamLanguage.define(csharpMode);
}
`;

await build({
    stdin: {
        contents: ENTRY,
        resolveDir: process.cwd(),
        sourcefile: 'codemirror-bundle-entry.js',
        loader: 'js',
    },
    outfile: 'core/frontend/static/assets/codemirror/codemirror-bundle.js',
    bundle: true,
    format: 'esm',
    target: 'es2020',
    minify: true,
    sourcemap: false,
    legalComments: 'none',
});

/**
 * codemirror-lazy — lazy-чанк CodeMirror для всех платформенных редакторов.
 * Динамический import этого модуля резолвится esbuild в отдельный чанк:
 * тяжёлый CodeMirror не грузится до первого редактора.
 *
 * Один модуль на всю платформу — так же, как prosemirror-lazy: несколько
 * копий @codemirror/state ломают StateField/ViewPlugin между редакторами.
 */
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
export { autocompletion, startCompletion } from '@codemirror/autocomplete';
export { LSPClient, languageServerExtensions } from '@codemirror/lsp-client';
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
export { html } from '@codemirror/lang-html';

import { StreamLanguage } from '@codemirror/language';
import { csharp as csharpMode } from '@codemirror/legacy-modes/mode/clike';

export function csharp() {
    return StreamLanguage.define(csharpMode);
}

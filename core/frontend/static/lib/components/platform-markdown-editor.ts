/**
 * platform-markdown-editor — единый платформенный markdown-редактор (UI Kit).
 * L0 document (CodeMirror source + preview/split/fullscreen),
 * L1/L2 wysiwyg compose (mail), L3 variables, L4 mentions, L5 file-drop.
 * Канон: value = markdown; change detail = { value, htmlValue, textValue }.
 */
import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';
import { PlatformElement } from '../platform-element/index.js';
import { markdownToHtml } from '../utils/markdown.js';
import './platform-help-hint.js';
import './platform-icon.js';
import './platform-button.js';
import { platformPrompt } from './platform-confirm-modal.js';
import './platform-voice-dictation.js';
import { formatFileSize } from '../utils/format-file-size.js';
import {
    sanitizeMarkdownEditorHtml,
    htmlToMarkdown,
    htmlToPlainText,
    MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES,
} from '../utils/markdown-html.js';
import { createVariableExtensions, refreshVariableDecorations } from '../codemirror/variable-extensions.js';
import type { CmCompartmentLike, CmEditorViewLike, CmModule, CmViewUpdateLike } from '../codemirror/variable-extensions.js';
import { isPlainRecord } from '../events/payload.js';

const CM_EXPORTS = [
    'EditorState',
    'EditorView',
    'Compartment',
    'keymap',
    'history',
    'autocompletion',
    'oneDark',
    'syntaxHighlighting',
    'defaultHighlightStyle',
    'lineNumbers',
    'highlightActiveLine',
    'highlightActiveLineGutter',
    'defaultKeymap',
    'historyKeymap',
] as const;

function isCmModule(value: unknown): value is CmModule {
    if (!isPlainRecord(value)) return false;
    return CM_EXPORTS.every((name) => value[name] !== undefined && value[name] !== null);
}

interface VariableCatalogEntry {
    name: string;
    type?: string;
    source?: string;
    hasValue?: boolean;
    kind?: string;
}

function isVariableCatalogEntry(value: unknown): value is VariableCatalogEntry {
    if (!isPlainRecord(value) || typeof value.name !== 'string' || value.name.length === 0) return false;
    if (value.type !== undefined && typeof value.type !== 'string') return false;
    if (value.source !== undefined && typeof value.source !== 'string') return false;
    if (value.hasValue !== undefined && typeof value.hasValue !== 'boolean') return false;
    if (value.kind !== undefined && typeof value.kind !== 'string') return false;
    return true;
}

function variableCatalogEntries(value: unknown): VariableCatalogEntry[] {
    if (!Array.isArray(value)) return [];
    return value.filter(isVariableCatalogEntry);
}

function stringList(value: unknown, label: string): string[] {
    if (!Array.isArray(value)) return [];
    return value.map((item, index) => {
        if (typeof item !== 'string') {
            throw new Error(`platform-markdown-editor: ${label}[${index}] must be a string`);
        }
        return item;
    });
}

function iconCache(icon: unknown): { uiCache: Record<string, string> } | undefined {
    if (!isPlainRecord(icon) || !isPlainRecord(icon.uiCache)) return undefined;
    const uiCache: Record<string, string> = {};
    for (const [key, value] of Object.entries(icon.uiCache)) {
        if (typeof value !== 'string') {
            throw new Error(`platform-markdown-editor: icon cache ${key} must be a string`);
        }
        uiCache[key] = value;
    }
    return { uiCache };
}

function attachmentChip(value: unknown): { filename?: string; size?: number } {
    if (!isPlainRecord(value)) {
        throw new Error('platform-markdown-editor: attachment must be an object');
    }
    const chip: { filename?: string; size?: number } = {};
    if (typeof value.filename === 'string') chip.filename = value.filename;
    if (typeof value.size === 'number') chip.size = value.size;
    return chip;
}
import type { SelectController } from '../events/select-controller.js';
import { lookupPreviewValue } from '../variables/variable-refs.js';
import { variableRefsStyles } from '../styles/shared/variable-refs.styles.js';
import { uploadPlatformFile } from '../utils/platform-file-upload.js';
import { buildPlatformAuxiliaryFileCreateSpecJson } from '../utils/file-create-spec.js';

export { sanitizeMarkdownEditorHtml, htmlToMarkdown, MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES } from '../utils/markdown-html.js';

export class PlatformMarkdownEditor extends PlatformElement {
    static i18nNamespace = 'platform';
    declare value: string;
    declare htmlValue: string;
    declare variables: Record<string, unknown>;
    declare variableCatalog: unknown[];
    declare label: string;
    declare hint: string;
    declare placeholder: string;
    declare primaryLabel: string;
    declare readonly: boolean;
    declare variant: string;
    declare viewMode: string;
    declare showHeader: boolean;
    declare showPreview: boolean;
    declare showHint: boolean;
    declare showPrimary: boolean;
    declare showAttach: boolean;
    declare showDiscard: boolean;
    declare showFormatToggle: boolean;
    declare showFormatToolbar: boolean;
    declare enableVoiceDictation: boolean;
    declare primaryDisabled: boolean;
    declare enableVariables: boolean;
    declare variableSyntax: string;
    declare statePreview: Record<string, unknown>;
    declare statePaths: unknown[];
    declare enableMentions: boolean;
    declare minHeight: number;
    declare compact: boolean;
    declare previewMode: boolean;
    declare splitMode: boolean;
    declare fullscreenMode: boolean;
    declare acceptFileDrop: boolean;
    declare attachments: unknown[];
    declare _formatOpen: boolean;
    _editorView: CmEditorViewLike | null = null;
    _editorEl: HTMLElement | null = null;
    _skipNextHtmlSync = false;
    _iconCacheSelect: SelectController<{ uiCache: Record<string, string> } | undefined>;
    _cmModules: Pick<
        CmModule,
        | 'EditorState'
        | 'Compartment'
        | 'EditorView'
        | 'keymap'
        | 'history'
        | 'defaultKeymap'
        | 'historyKeymap'
        | 'autocompletion'
        | 'oneDark'
        | 'syntaxHighlighting'
        | 'defaultHighlightStyle'
        | 'lineNumbers'
        | 'highlightActiveLine'
        | 'highlightActiveLineGutter'
    > | null = null;
    _cmBundle: CmModule | null = null;
    _readonlyCompartment: CmCompartmentLike | null = null;
    _fileDropCleanup: (() => void) | null = null;
    _variablesFingerprint = '';
    _variablesRefreshInProgress = false;
    _boundEscapeHandler: (event: Event) => void = () => {};

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        variableRefsStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                box-sizing: border-box;
                min-width: 0;
                min-height: 0;
                /* По умолчанию занимает свободную высоту родителя (flex/grid/height). */
                flex: 1 1 auto;
                align-self: stretch;
                height: 100%;
            }

            :host([compact]) {
                flex: 0 1 auto;
                align-self: auto;
                height: auto;
            }

            /*
             * embed — вложенный в field-pill / detail panel: без собственной «карточки»,
             * иначе box-in-box. Chrome: showHeader/showPreview; палитра — showFormatToolbar.
             */
            :host([variant="embed"]) .editor-wrapper {
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                min-height: 0;
                border: none;
                border-radius: 0;
                background: transparent;
                box-shadow: none;
                overflow: visible;
            }

            :host([variant="embed"]) .editor-wrapper:focus-within {
                border: none;
                background: transparent;
                box-shadow: none;
            }

            :host([variant="embed"]) .editor-header {
                background: transparent;
                border-bottom: 1px solid var(--glass-border-subtle);
                padding: var(--space-1) 0 var(--space-2);
                min-height: 0;
            }

            :host([variant="embed"]) .format-toolbar {
                border: none;
                border-bottom: 1px solid var(--glass-border-subtle);
                background: transparent;
                padding: var(--space-1) 0;
                margin: 0;
            }

            :host([variant="embed"]) #codemirror-container {
                flex: 1 1 auto;
                min-height: var(--editor-min-height, 150px);
            }

            :host([variant="embed"]) #codemirror-container .cm-editor {
                background: transparent;
            }

            :host([variant="embed"]) #codemirror-container .cm-scroller {
                padding: var(--space-1) 0;
            }

            :host([variant="embed"]) .preview-container {
                flex: 1 1 auto;
                padding: var(--space-1) 0;
                background: transparent;
            }

            :host([variant="embed"]) .editor-label {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            :host([variant="embed"]) .syntax-footer {
                border-top: 1px solid var(--glass-border-subtle);
                background: transparent;
                padding: var(--space-2) 0 0;
            }
            
            .editor-wrapper {
                position: relative;
                flex: 1 1 auto;
                display: flex;
                flex-direction: column;
                min-height: 0;
                height: 100%;
                border-radius: var(--radius-md);
                overflow: hidden;
                border: 1px solid var(--border-default);
                background: var(--glass-solid-subtle);
            }

            :host([compact]) .editor-wrapper {
                height: auto;
                flex: 0 1 auto;
            }
            
            .editor-wrapper:focus-within {
                border-color: var(--accent);
                box-shadow: var(--focus-ring);
            }
            
            .editor-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-shrink: 0;
                padding: var(--space-2) var(--space-3);
                background: var(--glass-tint-medium);
                border-bottom: 1px solid var(--border-subtle);
            }

            .editor-header.actions-only {
                justify-content: flex-end;
            }
            
            .editor-label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }

            .editor-label-wrap {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                min-width: 0;
            }
            
            .editor-actions {
                display: flex;
                gap: var(--space-2);
            }
            
            .editor-btn {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-secondary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            
            .editor-btn:hover {
                color: var(--text-primary);
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            
            .editor-btn.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            
            /*
             * Растягиваем .cm-editor на всю высоту контейнера: иначе клики
             * ниже последней строки попадают в «пустоту» и курсор не ставится.
             */
            #codemirror-container {
                box-sizing: border-box;
                flex: 1 1 auto;
                min-height: var(--editor-min-height, 150px);
                height: 100%;
                display: flex;
                flex-direction: column;
            }
            
            #codemirror-container.hidden {
                display: none;
            }
            
            #codemirror-container .cm-editor {
                flex: 1 1 auto;
                align-self: stretch;
                height: 100%;
                min-height: var(--editor-min-height, 150px);
                font-size: 14px;
                line-height: 1.6;
            }
            
            #codemirror-container .cm-scroller {
                flex: 1 1 auto;
                min-height: 0;
                padding: var(--space-3);
            }
            
            #codemirror-container .cm-content {
                font-family: var(--font-sans);
            }
            
            .preview-container {
                flex: 1 1 auto;
                min-height: var(--editor-min-height, 150px);
                padding: var(--space-4);
                font-size: var(--text-base);
                line-height: var(--leading-relaxed);
                color: var(--text-primary);
                overflow-y: auto;
            }
            
            .preview-container p {
                margin: 0 0 var(--space-3);
            }
            
            .preview-container p:last-child {
                margin-bottom: 0;
            }
            
            .preview-container code {
                font-family: var(--font-mono);
                font-size: 0.875em;
                padding: 2px 6px;
                background: var(--glass-tint-medium);
                border-radius: var(--radius-sm);
            }
            
            .preview-container pre {
                margin: var(--space-3) 0;
                padding: var(--space-3);
                background: var(--bg-primary);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                overflow-x: auto;
            }
            
            .preview-container pre code {
                padding: 0;
                background: none;
            }
            
            .hint {
                padding: var(--space-2) var(--space-3);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                border-top: 1px solid var(--border-subtle);
            }
            
            /* Split mode */
            .split-container {
                display: flex;
                flex: 1 1 auto;
                gap: 1px;
                min-height: max(var(--editor-min-height, 150px), 320px);
                height: 100%;
                background: var(--border-subtle);
            }

            :host([compact]) .split-container {
                height: auto;
                flex: 0 1 auto;
            }
            
            .split-container .split-pane {
                flex: 1;
                min-width: 0;
                background: var(--glass-solid-subtle);
                display: flex;
                flex-direction: column;
                overflow: hidden;
            }
            
            .split-container .split-pane-label {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                background: var(--glass-tint-subtle);
                border-bottom: 1px solid var(--border-subtle);
                text-transform: uppercase;
                letter-spacing: 0.05em;
                flex-shrink: 0;
            }
            
            .split-container #codemirror-container {
                border-radius: 0;
                flex: 1;
                min-height: 0;
                overflow: hidden;
            }
            
            .split-container #codemirror-container .cm-editor,
            .split-container #codemirror-container .cm-scroller {
                height: 100%;
                min-height: unset;
            }
            
            .split-container .preview-container {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
            }
            
            /* Fullscreen mode */
            :host([fullscreen]) {
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                right: 0 !important;
                bottom: 0 !important;
                z-index: 9999 !important;
                padding: var(--space-4);
                background: var(--bg-primary);
            }
            
            :host([fullscreen]) .editor-wrapper {
                height: 100%;
                display: flex;
                flex-direction: column;
            }
            
            :host([fullscreen]) #codemirror-container,
            :host([fullscreen]) .split-container {
                flex: 1;
                min-height: 0;
            }
            
            :host([fullscreen]) #codemirror-container .cm-editor,
            :host([fullscreen]) #codemirror-container .cm-scroller {
                height: 100%;
                min-height: unset;
            }
            
            :host([fullscreen]) .preview-container {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
            }
            
            /* Иконки-кнопки */
            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 28px;
                height: 28px;
                padding: 0;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-sm);
                background: var(--glass-tint-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            
            .icon-btn:hover {
                color: var(--text-primary);
                border-color: var(--accent);
                background: var(--accent-subtle);
            }
            
            .icon-btn.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            
            .icon-btn svg {
                width: 16px;
                height: 16px;
                fill: currentColor;
            }

            /* Prompt workspace */
            .editor-wrapper {
                border-radius: var(--radius-xl);
                border-color: var(--border-subtle);
                background: color-mix(in srgb, var(--glass-solid-subtle) 94%, transparent);
                box-shadow: var(--glass-shadow-subtle);
                transition: border-color var(--duration-fast) ease, box-shadow var(--duration-fast) ease;
            }

            .editor-wrapper:focus-within {
                border-color: color-mix(in srgb, var(--accent) 72%, transparent);
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 12%, transparent), var(--glass-shadow-medium);
            }

            .editor-header {
                min-height: 48px;
                padding: var(--space-2) var(--space-3) var(--space-2) var(--space-4);
                gap: var(--space-3);
                background: color-mix(in srgb, var(--glass-tint-medium) 72%, transparent);
            }

            .editor-label-wrap {
                gap: var(--space-2);
            }

            .editor-label {
                font-weight: var(--font-semibold);
                letter-spacing: -0.01em;
            }

            .document-meta {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                white-space: nowrap;
            }

            .document-meta::before {
                content: '';
                width: 4px;
                height: 4px;
                border-radius: 50%;
                background: var(--border-strong);
            }

            .editor-actions {
                align-items: center;
                gap: var(--space-1);
            }

            .mode-switch {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                padding: 3px;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-tint-subtle);
            }

            .mode-tab {
                min-height: 28px;
                padding: 0 var(--space-2);
                border: 0;
                border-radius: calc(var(--radius-md) - 3px);
                background: transparent;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .mode-tab:hover {
                color: var(--text-primary);
                background: var(--glass-tint-medium);
            }

            .mode-tab.active {
                color: var(--text-primary);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-subtle);
            }

            .format-toolbar {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                flex-shrink: 0;
                min-height: 38px;
                padding: var(--space-1) var(--space-3);
                border-bottom: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--glass-tint-subtle) 68%, transparent);
                overflow-x: auto;
            }

            .tool-group {
                display: inline-flex;
                align-items: center;
                gap: 2px;
                padding-right: var(--space-2);
                margin-right: var(--space-1);
                border-right: 1px solid var(--border-subtle);
            }

            .tool-group:last-child {
                padding-right: 0;
                margin-right: 0;
                border-right: 0;
            }

            .tool-group.voice-dictation-group {
                margin-left: auto;
                border-right: 0;
                padding-right: 0;
                margin-right: 0;
            }

            .tool-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 28px;
                height: 28px;
                padding: 0 var(--space-2);
                border: 0;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                cursor: pointer;
                white-space: nowrap;
            }

            .tool-btn:hover {
                color: var(--text-primary);
                background: var(--accent-subtle);
            }

            .tool-btn:disabled {
                opacity: 0.45;
                cursor: default;
            }

            .tool-btn.mono {
                font-family: var(--font-mono);
                color: var(--accent);
            }

            #codemirror-container .cm-editor {
                font-size: 14px;
                line-height: 1.72;
                background: transparent;
            }

            #codemirror-container .cm-content {
                padding-block: var(--space-3);
                font-family: var(--font-mono);
                caret-color: var(--accent);
            }

            #codemirror-container .cm-scroller {
                padding: 0;
            }

            #codemirror-container .cm-gutters {
                min-width: 42px;
                padding-top: var(--space-3);
                border-right: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--glass-tint-subtle) 45%, transparent);
                color: var(--text-disabled);
            }

            #codemirror-container .cm-lineNumbers .cm-gutterElement {
                padding: 0 var(--space-3) 0 var(--space-2);
                font-family: var(--font-mono);
                font-size: var(--text-xs);
            }

            #codemirror-container .cm-activeLine,
            #codemirror-container .cm-activeLineGutter {
                background: color-mix(in srgb, var(--accent) 6%, transparent);
            }

            .syntax-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                flex-shrink: 0;
                min-height: 38px;
                padding: var(--space-1) var(--space-3);
                border-top: 1px solid var(--border-subtle);
                background: color-mix(in srgb, var(--glass-tint-subtle) 62%, transparent);
            }

            .syntax-list {
                display: flex;
                align-items: center;
                gap: var(--space-1);
                min-width: 0;
                overflow-x: auto;
            }

            .syntax-list-label {
                flex: 0 0 auto;
                margin-right: var(--space-1);
                color: var(--text-tertiary);
                font-size: 11px;
                font-weight: var(--font-medium);
            }

            .syntax-chip {
                padding: 3px 7px;
                border: 1px solid transparent;
                border-radius: var(--radius-full);
                background: transparent;
                color: var(--text-tertiary);
                font-family: var(--font-mono);
                font-size: 11px;
                cursor: pointer;
                white-space: nowrap;
            }

            .syntax-chip[data-source="local"] { color: var(--accent); }
            .syntax-chip[data-source="input"] { color: var(--success); }
            .syntax-chip[data-source="upstream"],
            .syntax-chip[data-source="preview"],
            .syntax-chip[data-source="interface"] { color: var(--info); }

            .syntax-chip:hover {
                color: var(--accent);
                border-color: color-mix(in srgb, var(--accent) 24%, transparent);
                background: var(--accent-subtle);
            }

            .syntax-chip:disabled {
                cursor: default;
            }

            .editor-status {
                flex: 0 0 auto;
                color: var(--text-tertiary);
                font-size: 11px;
                white-space: nowrap;
            }

            .preview-container {
                background: color-mix(in srgb, var(--glass-solid-subtle) 88%, transparent);
            }

            @media (max-width: 720px) {
                .document-meta,
                .mode-tab-label,
                .syntax-list {
                    display: none;
                }

                .editor-header {
                    padding-inline: var(--space-3);
                }

                .mode-tab {
                    min-width: 30px;
                    padding-inline: var(--space-1);
                }
            }

            /* compose / wysiwyg surface */
            .compose-shell {
                display: flex;
                flex-direction: column;
                flex: 1 1 auto;
                min-height: var(--markdown-editor-min-height, 160px);
                height: 100%;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-lg);
                background: var(--bg-surface);
                overflow: hidden;
            }
            :host([compact]) .compose-shell {
                height: auto;
                flex: 0 1 auto;
            }
            :host([readonly]) .compose-shell {
                border: none;
                border-radius: 0;
                background: transparent;
            }
            .body-wrap {
                position: relative;
                flex: 1 1 auto;
                min-height: 0;
                display: flex;
                flex-direction: column;
            }
            .editor-body {
                flex: 1 1 auto;
                min-height: var(--markdown-editor-body-min-height, 120px);
                max-height: var(--markdown-editor-body-max-height, none);
                overflow: auto;
                padding: var(--space-4) var(--space-4) var(--space-3);
                outline: none;
                line-height: 1.55;
                font-size: 0.9375rem;
                color: var(--text-primary);
                white-space: pre-wrap;
                word-break: break-word;
            }
            .editor-body:empty::before {
                content: attr(data-placeholder);
                color: var(--text-tertiary);
                pointer-events: none;
            }
            .compose-fmt.fmt-btn, .compose-fmt .fmt-btn, .fmt-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 32px;
                height: 32px;
                padding: 0 var(--space-2);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font: inherit;
                font-weight: 650;
                font-size: 0.8125rem;
            }
            .fmt-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            .attachments {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3) 0;
                flex-shrink: 0;
            }
            .att-chip {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                max-width: 100%;
                padding: var(--space-1) var(--space-2);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                background: var(--bg-elevated);
                font-size: 0.75rem;
            }
            .att-chip-name {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 180px;
            }
            .att-chip-remove {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                cursor: pointer;
                padding: 0;
                display: inline-flex;
            }
            .action-bar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-height: var(--markdown-editor-action-bar-height, 48px);
                padding: var(--space-2) var(--space-3);
                border-top: 1px solid var(--border-subtle);
                background: var(--bg-surface);
                flex-shrink: 0;
            }
            .action-bar-end {
                margin-left: auto;
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
            }
            .file-input { display: none; }
        `
    ];

    static override properties: PropertyDeclarations = {
        value: { type: String },
        htmlValue: { type: String, attribute: false },
        variables: { type: Object },
        variableCatalog: { type: Array },
        label: { type: String },
        hint: { type: String },
        placeholder: { type: String },
        primaryLabel: { type: String, attribute: 'primary-label' },
        readonly: { type: Boolean, reflect: true },
        variant: { type: String, reflect: true },
        viewMode: { type: String, attribute: 'view-mode', reflect: true },
        showHeader: { type: Boolean, attribute: 'show-header' },
        showPreview: { type: Boolean, attribute: 'show-preview' },
        showHint: { type: Boolean, attribute: 'show-hint' },
        showPrimary: { type: Boolean, attribute: 'show-primary' },
        showAttach: { type: Boolean, attribute: 'show-attach' },
        showDiscard: { type: Boolean, attribute: 'show-discard' },
        showFormatToggle: { type: Boolean, attribute: 'show-format-toggle' },
        /** Document H2/B/list/code (+ variable inserts). Независимо от showHeader. */
        showFormatToolbar: { type: Boolean, attribute: 'show-format-toolbar' },
        /** Встроенный <platform-voice-dictation> (STT-only WS). Независимо от showHeader. */
        enableVoiceDictation: { type: Boolean, attribute: 'enable-voice-dictation' },
        primaryDisabled: { type: Boolean, attribute: 'primary-disabled' },
        enableVariables: { type: Boolean, attribute: 'enable-variables' },
        /**
         * Синтаксис вставок при enableVariables:
         * - brace — LLM-промпты ({var}, циклы);
         * - at-ref — поля flows (@state: / @var:), как platform-variable-input.
         */
        variableSyntax: { type: String, attribute: 'variable-syntax' },
        /** Preview map for `@state:` hover (from previewExecutionState). */
        statePreview: { type: Object, attribute: false },
        /** Known `@state:` paths for autocomplete (dataflow incoming_state). */
        statePaths: { type: Array, attribute: false },
        enableMentions: { type: Boolean, attribute: 'enable-mentions' },
        minHeight: { type: Number, attribute: 'min-height' },
        /** Не растягиваться на свободную высоту родителя (короткие поля в форме). */
        compact: { type: Boolean, reflect: true },
        previewMode: { type: Boolean },
        splitMode: { type: Boolean },
        fullscreenMode: { type: Boolean },
        acceptFileDrop: { type: Boolean, attribute: 'accept-file-drop' },
        attachments: { type: Array, attribute: false },
        _formatOpen: { state: true },
    };

    constructor() {
        super();
        this.value = '';
        this.htmlValue = '';
        this.variables = {};
        this.variableCatalog = [];
        this.label = '';
        this.hint = '';
        this.placeholder = '';
        this.primaryLabel = '';
        this.readonly = false;
        this.variant = 'default';
        this.viewMode = 'source';
        this.showHeader = true;
        this.showPreview = true;
        this.showHint = true;
        this.showPrimary = false;
        this.showAttach = false;
        this.showDiscard = false;
        this.showFormatToggle = false;
        this.showFormatToolbar = true;
        this.enableVoiceDictation = true;
        this.primaryDisabled = false;
        this.enableVariables = false;
        this.variableSyntax = 'brace';
        this.statePreview = {};
        this.statePaths = [];
        this.enableMentions = false;
        this.minHeight = 150;
        this.compact = false;
        this.previewMode = false;
        this.splitMode = false;
        this.fullscreenMode = false;
        this.acceptFileDrop = false;
        this.attachments = [];
        this._formatOpen = false;
        this._editorEl = null;
        this._skipNextHtmlSync = false;
        this._iconCacheSelect = this.select(
            (s) => iconCache(s.icon),
        );
        this._cmModules = null;
        this._readonlyCompartment = null;
        this._fileDropCleanup = null;
        this._variablesFingerprint = '';
        this._variablesRefreshInProgress = false;
    }

    _isComposeSurface(): boolean {
        return this.variant === 'compose' || this.viewMode === 'wysiwyg';
    }

    _isPreviewOnly(): boolean {
        return this.viewMode === 'preview' || (this.readonly && this._isComposeSurface() === false && this.previewMode);
    }

    _changeDetailFromMarkdown(markdown: unknown): { value: string; htmlValue: string; textValue: string } {
        const value = typeof markdown === 'string' ? markdown : '';
        const htmlValue = markdownToHtml(value);
        const tmp = document.createElement('div');
        tmp.innerHTML = sanitizeMarkdownEditorHtml(htmlValue);
        const textValue = tmp.innerText;
        return { value, htmlValue, textValue };
    }

    _changeDetailFromHtml(html: unknown): { value: string; htmlValue: string; textValue: string } {
        const htmlValue = sanitizeMarkdownEditorHtml(typeof html === 'string' ? html : '');
        const textValue = htmlToPlainText(htmlValue);
        const value = htmlToMarkdown(htmlValue);
        return { value, htmlValue, textValue };
    }

    _emitUnifiedChange(detail: { value: string; htmlValue: string; textValue: string }): void {
        this.value = detail.value;
        this.htmlValue = detail.htmlValue;
        this.emit('change', detail);
    }

    override async firstUpdated(): Promise<void> {
        this._loadIcons();
        this._boundEscapeHandler = this._handleEscape.bind(this);
        document.addEventListener('keydown', this._boundEscapeHandler);
        if (this._isComposeSurface()) {
            this._editorEl = this.renderRoot.querySelector('.editor-body');
            this._syncWysiwygFromProp();
            return;
        }
        if (this.viewMode === 'preview' && this.readonly) {
            return;
        }
        await this._initCodeMirror();
    }
    
    _handleEscape(e: Event): void {
        if (e instanceof KeyboardEvent && e.key === 'Escape' && this.fullscreenMode) {
            this._toggleFullscreen();
        }
    }
    
    _loadIcons(): void {
        const iconNames = ['fullscreen', 'minimize', 'list'];
        for (const name of iconNames) {
            this.dispatch('icon/ui_asset/load_requested', { name });
        }
    }

    _icon(name: string): string {
        const cache = this._iconCacheSelect.value;
        if (!cache) return '';
        const icon = cache.uiCache[name];
        return icon === undefined ? '' : icon;
    }

    _variablesFingerprintValue(variables: unknown): string {
        if (!variables || typeof variables !== 'object' || Array.isArray(variables)) {
            return '';
        }
        return JSON.stringify(variables);
    }

    _refreshVariableHighlighting(): void {
        if (!this._editorView) {
            return;
        }
        this._variablesRefreshInProgress = true;
        try {
            refreshVariableDecorations(this._editorView);
        } finally {
            this._variablesRefreshInProgress = false;
        }
    }

    override updated(changed: PropertyValues<this>): void {
        if (this._isComposeSurface()) {
            if (changed.has('htmlValue') && !this._skipNextHtmlSync) {
                const focused = this._editorEl !== null && this.renderRoot instanceof ShadowRoot && this.renderRoot.activeElement === this._editorEl;
                if (!focused) {
                    this._syncWysiwygFromProp();
                }
            }
            this._skipNextHtmlSync = false;
            return;
        }

        if (changed.has('value') && this._editorView) {
            const currentValue = this._editorView.state.doc.toString();
            if (this.value !== currentValue) {
                this._editorView.dispatch({
                    changes: { from: 0, to: currentValue.length, insert: this.value }
                });
            }
        }
        
        if (changed.has('readonly') && this._editorView && this._readonlyCompartment && this._cmModules) {
            this._editorView.dispatch({
                effects: this._readonlyCompartment.reconfigure(
                    this._cmModules.EditorState.readOnly.of(this.readonly)
                )
            });
        }
        
        if (
            this.enableVariables
            && (
                changed.has('variables')
                || changed.has('variableCatalog')
                || changed.has('statePreview')
                || changed.has('statePaths')
            )
            && this._editorView
        ) {
            const nextFingerprint = this._variablesFingerprintValue(this.variables);
            const nextCatalogFingerprint = JSON.stringify(this.variableCatalog);
            const nextStateFingerprint = JSON.stringify(this.statePreview);
            const nextPathsFingerprint = JSON.stringify(this.statePaths);
            const combinedFingerprint = `${nextFingerprint}|${nextCatalogFingerprint}|${nextStateFingerprint}|${nextPathsFingerprint}`;
            if (combinedFingerprint !== this._variablesFingerprint) {
                this._variablesFingerprint = combinedFingerprint;
                this._refreshVariableHighlighting();
            }
        }
        
        if (changed.has('splitMode') && this._cmModules) {
            this._recreateEditor();
        }

        if (changed.has('acceptFileDrop') && this._editorView) {
            this._syncFileDropListeners();
        }
    }
    
    async _recreateEditor(): Promise<void> {
        await this.updateComplete;
        
        const currentValue = this._editorView ? this._editorView.state.doc.toString() : this.value;
        
        if (this._editorView) {
            this._teardownFileDropListeners();
            this._editorView.destroy();
            this._editorView = null;
        }
        
        this.value = currentValue;
        this._createEditor();
    }

    async _initCodeMirror(): Promise<void> {
        const loaded: unknown = await import('/static/core/assets/codemirror/codemirror-bundle.js');
        if (!isCmModule(loaded)) {
            throw new Error('platform-markdown-editor: CodeMirror bundle is incomplete');
        }
        const cm = loaded;
        
        this._cmBundle = cm;
        this._cmModules = {
            EditorState: cm.EditorState,
            Compartment: cm.Compartment,
            EditorView: cm.EditorView,
            keymap: cm.keymap,
            history: cm.history,
            defaultKeymap: cm.defaultKeymap,
            historyKeymap: cm.historyKeymap,
            autocompletion: cm.autocompletion,
            oneDark: cm.oneDark,
            syntaxHighlighting: cm.syntaxHighlighting,
            defaultHighlightStyle: cm.defaultHighlightStyle,
            lineNumbers: cm.lineNumbers,
            highlightActiveLine: cm.highlightActiveLine,
            highlightActiveLineGutter: cm.highlightActiveLineGutter,
        };

        this._createEditor();
    }

    _requireCmBundle(): CmModule {
        const bundle = this._cmBundle;
        if (bundle === null) {
            throw new Error('platform-markdown-editor: CodeMirror bundle required');
        }
        return bundle;
    }

    _createEditor(): void {
        const container = this.renderRoot.querySelector('#codemirror-container');
        if (!container) return;

        const cm = this._cmModules;
        if (!cm) return;
        const isDarkTheme = document.documentElement.getAttribute('data-theme') !== 'light';
        
        this._readonlyCompartment = new cm.Compartment();
        
        const variableExtensions = this.enableVariables
            ? createVariableExtensions(this._requireCmBundle(), {
                syntax: this.variableSyntax === 'at-ref' ? 'at-ref' : 'both',
                getValues: () => (this.variables && typeof this.variables === 'object' ? this.variables : {}),
                getStatePreview: () => (this.statePreview && typeof this.statePreview === 'object' ? this.statePreview : {}),
                getCatalog: () => variableCatalogEntries(this.variableCatalog),
                getStatePaths: () => stringList(this.statePaths, 'statePaths'),
                t: (key: string) => {
                    if (key === 'undefined') return this.t('markdown_editor.var_undefined');
                    if (key === 'runtime_value') return this.t('markdown_editor.runtime_value');
                    throw new Error(`platform-markdown-editor: unknown variable tooltip key ${key}`);
                },
            })
            : [];

        const themeExtensions = isDarkTheme 
            ? [cm.oneDark]
            : [
                cm.syntaxHighlighting(cm.defaultHighlightStyle, { fallback: true }),
                cm.EditorView.theme({
                    "&": { backgroundColor: "transparent", color: "#383a42" },
                    ".cm-content": { caretColor: "#7c8af4" },
                    ".cm-cursor": { borderLeftColor: "#7c8af4" },
                }, { dark: false })
            ];

        const extensions = [
            cm.history(),
            cm.lineNumbers(),
            cm.highlightActiveLine(),
            cm.highlightActiveLineGutter(),
            cm.EditorView.lineWrapping,
            this._readonlyCompartment.of(cm.EditorState.readOnly.of(this.readonly)),
            cm.keymap.of([
                ...cm.defaultKeymap,
                ...cm.historyKeymap,
            ]),
            ...variableExtensions,
            ...themeExtensions,
            cm.EditorView.updateListener.of((update: CmViewUpdateLike) => {
                if (update.docChanged && !this._variablesRefreshInProgress) {
                    const markdown = update.state.doc.toString();
                    this._emitUnifiedChange(this._changeDetailFromMarkdown(markdown));
                    if (this.enableMentions) {
                        this._maybeEmitMentionQuery(update);
                    }
                }
                if (update.focusChanged && !update.view.hasFocus) {
                    this.emit('blur', null);
                }
            }),
            cm.EditorView.theme({
                "&.cm-focused": { outline: "none" },
                ".cm-line": { padding: "0 4px" },
            }),
        ];

        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: this.value,
                extensions
            }),
            parent: container
        });
        this._variablesFingerprint = `${this._variablesFingerprintValue(this.variables)}|${JSON.stringify(this.variableCatalog)}|${JSON.stringify(this.statePreview)}|${JSON.stringify(this.statePaths)}`;
        this._syncFileDropListeners();
    }

    _teardownFileDropListeners(): void {
        if (this._fileDropCleanup) {
            this._fileDropCleanup();
            this._fileDropCleanup = null;
        }
    }

    _syncFileDropListeners(): void {
        this._teardownFileDropListeners();
        if (!this.acceptFileDrop || !this._editorView) {
            return;
        }
        const dom = this._editorView.dom;
        const asDropEvent = (e: Event): Event & { dataTransfer?: DataTransfer | null } => e;
        const onDragOver = (e: Event) => {
            e.preventDefault();
            e.stopPropagation();
            const dt = asDropEvent(e).dataTransfer;
            if (!dt) {
                return;
            }
            const types = dt.types ? Array.from(dt.types) : [];
            if (types.includes('text/plain')) {
                dt.dropEffect = 'copy';
            }
        };
        const onDrop = (e: Event) => {
            e.preventDefault();
            e.stopPropagation();
            const transfer = asDropEvent(e).dataTransfer;
            if (transfer === undefined || transfer === null) {
                return;
            }
            const text = transfer.getData('text/plain');
            if (text !== '') {
                this.insertTextAtCursor(text);
            }
        };
        dom.addEventListener('dragover', onDragOver);
        dom.addEventListener('drop', onDrop);
        this._fileDropCleanup = () => {
            dom.removeEventListener('dragover', onDragOver);
            dom.removeEventListener('drop', onDrop);
        };
    }

    _getVariableValue(path: string, type: string): unknown {
        const kind = type === 'state_ref' ? 'state' : type === 'var_ref' ? 'var' : 'brace';
        const preview = lookupPreviewValue(path, {
            kind,
            values: this.variables,
            statePreview: this.statePreview,
            catalog: this.variableCatalog,
        });
        if (preview.status === 'resolved') {
            return preview.value;
        }
        return undefined;
    }

    _togglePreview(): void {
        if (this.splitMode) {
            this.splitMode = false;
        }
        this.previewMode = !this.previewMode;
    }
    
    _toggleSplit(): void {
        if (this.previewMode) {
            this.previewMode = false;
        }
        this.splitMode = !this.splitMode;
    }
    
    _toggleFullscreen(): void {
        this.fullscreenMode = !this.fullscreenMode;
        if (this.fullscreenMode) {
            this.setAttribute('fullscreen', '');
            document.body.style.overflow = 'hidden';
        } else {
            this.removeAttribute('fullscreen');
            document.body.style.overflow = '';
        }
    }

    _renderPreview(): TemplateResult {
        if (!this.value) {
            return html`<div class="preview-container" style="color: var(--text-tertiary);">${this.t('markdown_editor.empty_preview')}</div>`;
        }

        const rendered = this._resolveTemplate(this.value);
        const htmlContent = markdownToHtml(rendered);
        return html`<div class="preview-container">${unsafeHTML(htmlContent)}</div>`;
    }
    
    _resolveTemplate(template: string): string {
        let result = template;
        
        result = this._resolveForLoops(result);
        
        result = result.replace(/\{\?([\w.]+)\|([^}]+)\}/g, (_match: string, varName: string, _defaultVal: string) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : '';
        });
        
        result = result.replace(/\{\?([\w.]+)\}/g, (_match: string, varName: string) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : '';
        });
        
        result = result.replace(/\{([\w.]+)\|([^}]+)\}/g, (_match: string, varName: string, defaultVal: string) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : defaultVal;
        });
        
        result = result.replace(/\{([\w.]+)\}/g, (match: string, varName: string) => {
            const value = this._getVariableValue(varName, 'variable');
            if (value !== undefined) {
                return this._formatValue(value);
            }
            return this._missingPreviewValue(match, varName);
        });
        
        result = result.replace(/@var:([\w.]+)/g, (match: string, varName: string) => {
            const value = this._getVariableValue(varName, 'variable');
            return value !== undefined ? this._formatValue(value) : this._missingPreviewValue(match, varName);
        });
        
        result = result.replace(/@state:([\w.]+)/g, (match: string, varName: string) => {
            const value = this._getVariableValue(varName, 'state_ref');
            return value !== undefined ? this._formatValue(value) : `📍${match}`;
        });
        
        return result;
    }

    _missingPreviewValue(original: string, varName: string): string {
        const catalog = Array.isArray(this.variableCatalog) ? this.variableCatalog : [];
        const root = typeof varName === 'string' ? varName.split('.')[0] : '';
        const entry = catalog.find((item: unknown) => {
            const name = isPlainRecord(item) ? item.name : undefined;
            if (typeof name !== 'string' || name.length === 0) return false;
            if (name === varName || name === root) return true;
            return typeof root === 'string' && root.length > 0 && name.startsWith(`${root}.`);
        });
        if (entry) return `‹${varName}: ${this.t('markdown_editor.runtime_value')}›`;
        return `⚠️${original}`;
    }
    
    _resolveForLoops(template: string): string {
        const forPattern = /\{for\s+(\w+)\s+in\s+([\w.]+)\}([\s\S]*?)\{endfor\}/g;

        return template.replace(forPattern, (_match: string, itemVar: string, listVar: string, body: string) => {
            const listValue = this._getVariableValue(listVar, 'variable');
            
            if (!Array.isArray(listValue)) {
                return `⚠️ ${this.t('markdown_editor.for_not_array', { name: listVar })}`;
            }
            
            const results = listValue.map((item: unknown) => {
                let itemBody = body;
                
                itemBody = itemBody.replace(new RegExp(`\\{${itemVar}\\}`, 'g'), this._formatValue(item));
                
                itemBody = itemBody.replace(new RegExp(`\\{${itemVar}\\.(\\w+)\\}`, 'g'), (_m: string, prop: string) => {
                    if (isPlainRecord(item) && prop in item) {
                        return this._formatValue(item[prop]);
                    }
                    return `⚠️{${itemVar}.${prop}}`;
                });
                
                return itemBody;
            });
            
            return results.join('');
        });
    }
    
    _formatValue(value: unknown): string {
        if (value === null || value === undefined) return '';
        if (typeof value === 'object') return JSON.stringify(value);
        return String(value);
    }

    _setMode(mode: string): void {
        if (mode !== 'edit' && mode !== 'preview' && mode !== 'split') {
            throw new Error(`platform-markdown-editor: unsupported mode "${mode}"`);
        }
        this.previewMode = mode === 'preview';
        this.splitMode = mode === 'split';
    }

    _wrapSelection(prefix: string, suffix: string, placeholder: string): void {
        if (this.readonly || !this._editorView) return;
        const { from, to } = this._editorView.state.selection.main;
        const selected = this._editorView.state.sliceDoc(from, to);
        const content = selected || placeholder;
        const insert = `${prefix}${content}${suffix}`;
        this._editorView.dispatch({
            changes: { from, to, insert },
            selection: {
                anchor: from + prefix.length,
                head: from + prefix.length + content.length,
            },
        });
        this._editorView.focus();
    }

    _prefixSelectedLines(prefix: string): void {
        if (this.readonly || !this._editorView) return;
        const { state } = this._editorView;
        const { from, to } = state.selection.main;
        const start = state.doc.lineAt(from).from;
        const endLine = state.doc.lineAt(to);
        const end = endLine.to;
        const source = state.sliceDoc(start, end);
        const insert = source.split('\n').map((line) => `${prefix}${line}`).join('\n');
        this._editorView.dispatch({
            changes: { from: start, to: end, insert },
            selection: { anchor: start + prefix.length, head: start + insert.length },
        });
        this._editorView.focus();
    }

    _documentStats(): { words: number; characters: number } {
        const text = typeof this.value === 'string' ? this.value : '';
        const words = text.trim() === '' ? 0 : text.trim().split(/\s+/u).length;
        return { words, characters: text.length };
    }

    _availableVariableEntries(): Array<{ name: string; source?: string; hasValue?: boolean; type?: string }> {
        if (!Array.isArray(this.variableCatalog)) return [];
        return this.variableCatalog.filter(isVariableCatalogEntry);
    }

    _variableChipTitle(entry: { name?: string; type?: string; source?: string; hasValue?: boolean }): string {
        const source = this.t(`markdown_editor.source_${entry.source || 'system'}`);
        const availability = entry.hasValue
            ? this.t('markdown_editor.preview_value_available')
            : this.t('markdown_editor.preview_value_runtime');
        return `${entry.name} · ${entry.type || 'any'} · ${source} · ${availability}`;
    }

    _maybeEmitMentionQuery(update: CmViewUpdateLike): void {
        const pos = update.state.selection.main.head;
        const text = update.state.doc.toString();
        const before = text.slice(0, pos);
        const match = before.match(/(^|[\s([{])@([^\s@]*)$/);
        const mentionQuery = match === null ? undefined : match[2];
        if (match === null || mentionQuery === undefined) {
            return;
        }
        this.emit('mention-query', {
            query: mentionQuery,
            from: pos - mentionQuery.length - 1,
            to: pos,
        });
    }

    _syncWysiwygFromProp(): void {
        if (!this._editorEl) {
            this._editorEl = this.renderRoot.querySelector('.editor-body');
        }
        if (!this._editorEl) return;
        let html = typeof this.htmlValue === 'string' ? this.htmlValue : '';
        if (html.length === 0 && typeof this.value === 'string' && this.value.length > 0) {
            html = markdownToHtml(this.value);
        }
        const next = sanitizeMarkdownEditorHtml(html);
        if (this._editorEl.innerHTML !== next) {
            this._editorEl.innerHTML = next;
        }
    }

    _onWysiwygInput(): void {
        if (this.readonly) return;
        if (!this._editorEl) return;
        const detail = this._changeDetailFromHtml(this._editorEl.innerHTML);
        this._skipNextHtmlSync = true;
        this._emitUnifiedChange(detail);
    }

    _wysiwygFormat(command: string, value?: string): void {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: format unavailable in readonly mode');
        }
        this._editorEl?.focus();
        const ok = document.execCommand(command, false, value);
        if (!ok) {
            throw new Error(`platform-markdown-editor: execCommand failed for ${command}`);
        }
        this._onWysiwygInput();
    }

    async _insertLink(): Promise<void> {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: link unavailable in readonly mode');
        }
        const href = await platformPrompt(this.t('markdown_editor.link_prompt'), {
            inputLabel: this.t('markdown_editor.link_prompt'),
            inputPlaceholder: 'https://',
        });
        if (href === undefined) return;
        const trimmed = href.trim();
        if (!trimmed) {
            throw new Error('platform-markdown-editor: link href required');
        }
        if (!trimmed.startsWith('http://') && !trimmed.startsWith('https://') && !trimmed.startsWith('mailto:')) {
            throw new Error('platform-markdown-editor: link must be http(s) or mailto');
        }
        if (this._isComposeSurface()) {
            this._wysiwygFormat('createLink', trimmed);
            return;
        }
        this.insertTextAtCursor(`[link](${trimmed})`);
    }

    _toggleFormat(): void {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: format toggle unavailable in readonly mode');
        }
        this._formatOpen = !this._formatOpen;
    }

    _onPrimary(): void {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: primary unavailable in readonly mode');
        }
        const detail = this._isComposeSurface() && this._editorEl
            ? this._changeDetailFromHtml(this._editorEl.innerHTML)
            : this._changeDetailFromMarkdown(this.getValue());
        this.emit('primary', {
            ...detail,
            attachments: Array.isArray(this.attachments) ? this.attachments : [],
        });
    }

    _onDiscard(): void {
        if (this.readonly) {
            throw new Error('platform-markdown-editor: discard unavailable in readonly mode');
        }
        this.emit('discard', null);
    }

    _openFilePicker(): void {
        const input = this.renderRoot.querySelector('.file-input');
        if (!(input instanceof HTMLInputElement)) {
            throw new Error('platform-markdown-editor: file input missing');
        }
        input.click();
    }

    async _onFilesSelected(event: Event): Promise<void> {
        const input = event.target;
        if (!(input instanceof HTMLInputElement) || !input.files) {
            return;
        }
        const files = Array.from(input.files);
        input.value = '';
        const current = Array.isArray(this.attachments) ? [...this.attachments] : [];
        for (const file of files) {
            if (file.size > MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES) {
                this.toast('markdown_editor.attach_too_large', {
                    type: 'error',
                    vars: { filename: file.name, max_mb: 10 },
                    namespace: 'platform',
                });
                continue;
            }
            if (file.size <= 0) {
                throw new Error(`platform-markdown-editor: empty file ${file.name}`);
            }
            const uploaded = await uploadPlatformFile({
                file,
                spec: buildPlatformAuxiliaryFileCreateSpecJson({
                    metadata: { mail_compose_attachment: true },
                }),
                maxUploadBytes: MARKDOWN_EDITOR_MAX_ATTACHMENT_BYTES,
            });
            if (typeof uploaded.file_id !== 'string' || uploaded.file_id.trim() === '') {
                throw new Error('platform-markdown-editor: uploaded.file_id required');
            }
            if (typeof uploaded.url !== 'string' || uploaded.url.trim() === '') {
                throw new Error('platform-markdown-editor: uploaded.url required');
            }
            const contentType =
                typeof uploaded.content_type === 'string' && uploaded.content_type.trim() !== ''
                    ? uploaded.content_type
                    : file.type && file.type.length > 0
                      ? file.type
                      : 'application/octet-stream';
            current.push({
                filename:
                    typeof uploaded.original_name === 'string' && uploaded.original_name.trim() !== ''
                        ? uploaded.original_name
                        : file.name,
                content_type: contentType,
                file_id: uploaded.file_id,
                url: uploaded.url,
                size: typeof uploaded.file_size === 'number' ? uploaded.file_size : file.size,
            });
        }
        this.attachments = current;
        this.emit('attachments-change', { attachments: current });
    }

    _removeAttachment(index: number): void {
        if (!Array.isArray(this.attachments) || index < 0 || index >= this.attachments.length) {
            throw new Error('platform-markdown-editor: invalid attachment index');
        }
        const next = this.attachments.filter((_att: unknown, i: number) => i !== index);
        this.attachments = next;
        this.emit('attachments-change', { attachments: next });
    }


    getValue(): string {
        if (this._editorView) {
            return this._editorView.state.doc.toString();
        }
        return this.value;
    }

    /**
     * @param {CustomEvent<{ text: string, provider: string }>} event
     */
    _onVoiceDictationTranscribed(event: Event) {
        const detail = event instanceof CustomEvent && isPlainRecord(event.detail) ? event.detail : null;
        if (detail === null || typeof detail.text !== 'string' || detail.text.length === 0) {
            throw new Error('platform-markdown-editor: transcribed detail.text required');
        }
        const current = this.getValue();
        const next = typeof current === 'string' && current.length > 0
            ? `${current}\n\n${detail.text}`
            : detail.text;
        if (this._isComposeSurface()) {
            this.value = next;
            this.htmlValue = '';
            if (this._editorEl) {
                this._editorEl.textContent = next;
            }
            this._emitUnifiedChange(this._changeDetailFromMarkdown(next));
            return;
        }
        if (this._editorView) {
            const docLen = this._editorView.state.doc.length;
            this._editorView.dispatch({
                selection: { anchor: docLen, head: docLen },
            });
        }
        this.insertTextAtCursor(
            typeof current === 'string' && current.length > 0
                ? `\n\n${detail.text}`
                : detail.text,
        );
    }

    insertTextAtCursor(text: string): void {
        if (typeof text !== 'string' || text.length === 0) {
            throw new Error('platform-markdown-editor: insertTextAtCursor text required');
        }
        if (this._isComposeSurface()) {
            if (!this._editorEl) {
                throw new Error('platform-markdown-editor: compose editor is not ready');
            }
            this._editorEl.focus();
            const ok = document.execCommand('insertText', false, text);
            if (!ok) {
                throw new Error('platform-markdown-editor: insertText failed');
            }
            this._onWysiwygInput();
            return;
        }
        if (!this._editorView) {
            throw new Error('platform-markdown-editor: editor view is not ready');
        }
        const { from, to } = this._editorView.state.selection.main;
        this._editorView.dispatch({
            changes: { from, to, insert: text },
            selection: { anchor: from + text.length, head: from + text.length },
        });
        const markdown = this._editorView.state.doc.toString();
        this._emitUnifiedChange(this._changeDetailFromMarkdown(markdown));
    }

    insertMention({ name, entityId }: { name: unknown; entityId: unknown }): void {
        if (typeof name !== 'string' || name.length === 0) {
            throw new Error('platform-markdown-editor: mention name required');
        }
        if (typeof entityId !== 'string' || entityId.length === 0) {
            throw new Error('platform-markdown-editor: mention entityId required');
        }
        const token = `[@${name}](entity:${entityId})`;
        this.insertTextAtCursor(token);
    }

    setValue(text: string): void {
        this.value = text;
        if (this._editorView) {
            this._editorView.dispatch({
                changes: { from: 0, to: this._editorView.state.doc.length, insert: text }
            });
        }
    }

    override focus(): void {
        if (this._editorView) {
            this._editorView.focus();
        }
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        this._teardownFileDropListeners();
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
        if (this._boundEscapeHandler) {
            document.removeEventListener('keydown', this._boundEscapeHandler);
        }
        if (this.fullscreenMode) {
            document.body.style.overflow = '';
        }
    }

    _hasLabelRow(): boolean {
        const labelText = typeof this.label === 'string' && this.label.length > 0
            ? this.label
            : '';
        const hasHint = typeof this.hint === 'string' && this.hint.length > 0;
        return labelText.length > 0 || hasHint;
    }

    _labelText(): string {
        if (typeof this.label === 'string' && this.label.length > 0) {
            return this.label;
        }
        return this.t('markdown_editor.label_default');
    }

    _placeholderText(): string {
        if (typeof this.placeholder === 'string' && this.placeholder.length > 0) {
            return this.placeholder;
        }
        return this.t('markdown_editor.placeholder_default');
    }

    _renderCompose(): TemplateResult {
        const placeholder = this.placeholder.length > 0
            ? this.placeholder
            : this.t('markdown_editor.placeholder');
        const primaryLabel = this.primaryLabel.length > 0
            ? this.primaryLabel
            : this.t('markdown_editor.primary');
        const atts = Array.isArray(this.attachments) ? this.attachments : [];
        const editable = !this.readonly;
        return html`
            <div class="compose-shell">
                <div class="body-wrap">
                    <div
                        class="editor-body"
                        contenteditable=${editable ? 'true' : 'false'}
                        data-canon="composer"
                        data-placeholder=${placeholder}
                        @input=${() => this._onWysiwygInput()}
                    ></div>
                </div>
                ${!this.readonly && atts.length > 0 ? html`
                    <div class="attachments">
                        ${atts.map((att, index: number) => {
                            const chip = attachmentChip(att);
                            return html`
                            <div class="att-chip">
                                <platform-icon name="attach" size="12"></platform-icon>
                                <span class="att-chip-name">${chip.filename}</span>
                                <span>${formatFileSize(typeof chip.size === 'number' && Number.isFinite(chip.size) ? chip.size : 0)}</span>
                                <button type="button" class="att-chip-remove"
                                    .ariaLabel=${this.t('markdown_editor.attach_remove')}
                                    @click=${() => this._removeAttachment(index)}>
                                    <platform-icon name="close" size="12"></platform-icon>
                                </button>
                            </div>
                        `;
                        })}
                    </div>
                ` : nothing}
                ${!this.readonly && this.showFormatToggle && this._formatOpen ? html`
                    <div class="format-toolbar compose-fmt" role="toolbar" aria-label=${this.t('markdown_editor.format_toolbar')}>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.bold')} @click=${() => this._wysiwygFormat('bold')}>B</button>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.italic')} @click=${() => this._wysiwygFormat('italic')}><em>I</em></button>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.underline')} @click=${() => this._wysiwygFormat('underline')}><u>U</u></button>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.strikethrough')} @click=${() => this._wysiwygFormat('strikeThrough')}><s>S</s></button>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.ul')} @click=${() => this._wysiwygFormat('insertUnorderedList')}>
                            <platform-icon name="list" size="14"></platform-icon>
                        </button>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.ol')} @click=${() => this._wysiwygFormat('insertOrderedList')}>1.</button>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.quote')} @click=${() => this._wysiwygFormat('formatBlock', 'blockquote')}>"</button>
                        <button type="button" class="fmt-btn" title=${this.t('markdown_editor.link')} @click=${() => this._insertLink()}>
                            <platform-icon name="link" size="14"></platform-icon>
                        </button>
                    </div>
                ` : nothing}
                ${this.readonly ? nothing : html`
                    <div class="action-bar">
                        ${this.showPrimary ? html`
                            <platform-button variant="primary" density="compact"
                                ?disabled=${this.primaryDisabled} @click=${() => this._onPrimary()}>
                                <platform-icon name="send" size="16"></platform-icon>
                                ${primaryLabel}
                            </platform-button>
                        ` : nothing}
                        <div class="action-bar-end">
                            ${this.showFormatToggle ? html`
                                <platform-button variant="ghost" icon-only density="dense"
                                    .ariaLabel=${this.t('markdown_editor.format_toggle')}
                                    @click=${() => this._toggleFormat()}>
                                    <span style="font-weight:700;font-size:0.75rem;">Aa</span>
                                </platform-button>
                            ` : nothing}
                            ${this.showAttach ? html`
                                <platform-button variant="ghost" icon-only density="dense"
                                    .ariaLabel=${this.t('markdown_editor.attach')}
                                    @click=${() => this._openFilePicker()}>
                                    <platform-icon name="attach" size="16"></platform-icon>
                                </platform-button>
                                <input class="file-input" type="file" multiple @change=${(e: Event) => this._onFilesSelected(e)} />
                            ` : nothing}
                            <platform-button variant="ghost" icon-only density="dense"
                                .ariaLabel=${this.t('markdown_editor.link')}
                                @click=${() => this._insertLink()}>
                                <platform-icon name="link" size="16"></platform-icon>
                            </platform-button>
                            ${this.showDiscard ? html`
                                <platform-button variant="ghost" icon-only density="dense"
                                    .ariaLabel=${this.t('markdown_editor.discard')}
                                    @click=${() => this._onDiscard()}>
                                    <platform-icon name="trash" size="16"></platform-icon>
                                </platform-button>
                            ` : nothing}
                        </div>
                    </div>
                `}
            </div>
        `;
    }

    override render(): TemplateResult {
        if (this._isComposeSurface()) {
            return this._renderCompose();
        }
        if (this.viewMode === 'preview' && this.readonly) {
            return this._renderPreview();
        }
        const style = `--editor-min-height: ${this.minHeight}px`;
        const hasLabelRow = this._hasLabelRow();
        const headerClass = hasLabelRow ? 'editor-header' : 'editor-header actions-only';
        const fullscreenTitle = this.fullscreenMode
            ? this.t('markdown_editor.fullscreen_exit')
            : this.t('markdown_editor.fullscreen_enter');
        const mode = this.splitMode ? 'split' : (this.previewMode ? 'preview' : 'edit');
        const stats = this._documentStats();
        const availableVariables = this.enableVariables ? this._availableVariableEntries() : [];

        return html`
            <div class="editor-wrapper" style=${style}>
                ${this.showHeader ? html`
                    <div class=${headerClass}>
                        ${hasLabelRow ? html`
                            <span class="editor-label-wrap">
                                <span class="editor-label">${this._labelText()}</span>
                                ${typeof this.hint === 'string' && this.hint !== ''
                                    ? html`<platform-help-hint .text=${this.hint}></platform-help-hint>`
                                    : ''}
                                <span class="document-meta">
                                    ${this.t('markdown_editor.markdown_label')}
                                </span>
                            </span>
                        ` : nothing}
                        <div class="editor-actions">
                            ${this.showPreview ? html`
                                <div class="mode-switch" role="tablist" aria-label=${this.t('markdown_editor.view_modes')}>
                                    <button type="button" class="mode-tab ${mode === 'edit' ? 'active' : ''}"
                                        role="tab" aria-selected=${mode === 'edit'} @click=${() => this._setMode('edit')}
                                        title=${this.t('markdown_editor.mode_edit')}>
                                        <platform-icon name="edit" size="14"></platform-icon>
                                        <span class="mode-tab-label">${this.t('markdown_editor.mode_edit')}</span>
                                    </button>
                                    <button type="button" class="mode-tab ${mode === 'preview' ? 'active' : ''}"
                                        role="tab" aria-selected=${mode === 'preview'} @click=${() => this._setMode('preview')}
                                        title=${this.t('markdown_editor.mode_preview')}>
                                        <platform-icon name="eye" size="14"></platform-icon>
                                        <span class="mode-tab-label">${this.t('markdown_editor.mode_preview')}</span>
                                    </button>
                                    <button type="button" class="mode-tab ${mode === 'split' ? 'active' : ''}"
                                        role="tab" aria-selected=${mode === 'split'} @click=${() => this._setMode('split')}
                                        title=${this.t('markdown_editor.split')}>
                                        <platform-icon name="list" size="14"></platform-icon>
                                        <span class="mode-tab-label">${this.t('markdown_editor.split_short')}</span>
                                    </button>
                                </div>
                            ` : nothing}
                            ${this.variant === 'embed' && !this.showPreview ? nothing : html`
                            <button
                                type="button"
                                class="icon-btn ${this.fullscreenMode ? 'active' : ''}"
                                @click=${this._toggleFullscreen}
                                title=${fullscreenTitle}
                            >
                                ${this.fullscreenMode
                                    ? (this._icon('minimize') ? unsafeHTML(this._icon('minimize')) : '⊠')
                                    : (this._icon('fullscreen') ? unsafeHTML(this._icon('fullscreen')) : '⊡')
                                }
                            </button>
                            `}
                        </div>
                    </div>
                ` : nothing}

                ${!this.previewMode && (this.showFormatToolbar || this.enableVoiceDictation) ? html`
                    <div class="format-toolbar" role="toolbar" aria-label=${this.t('markdown_editor.format_toolbar')}>
                        ${this.showFormatToolbar ? html`
                        <div class="tool-group">
                            <button type="button" class="tool-btn" ?disabled=${this.readonly}
                                @click=${() => this._prefixSelectedLines('## ')} title=${this.t('markdown_editor.format_heading')}>H2</button>
                            <button type="button" class="tool-btn" ?disabled=${this.readonly}
                                @click=${() => this._wrapSelection('**', '**', this.t('markdown_editor.placeholder_text'))}
                                title=${this.t('markdown_editor.format_bold')}><strong>B</strong></button>
                            <button type="button" class="tool-btn" ?disabled=${this.readonly}
                                @click=${() => this._prefixSelectedLines('- ')} title=${this.t('markdown_editor.format_list')}>☷</button>
                            <button type="button" class="tool-btn" ?disabled=${this.readonly}
                                @click=${() => this._wrapSelection('`', '`', 'code')} title=${this.t('markdown_editor.format_code')}>&lt;/&gt;</button>
                        </div>
                        ${this.enableVariables ? html`
                        <div class="tool-group">
                            ${this.variableSyntax === 'at-ref' ? html`
                            <button type="button" class="tool-btn mono" ?disabled=${this.readonly}
                                @click=${() => this.insertTextAtCursor('@state:path')}
                                title=${this.t('markdown_editor.insert_state_ref')}>${'@state:path'}</button>
                            <button type="button" class="tool-btn mono" ?disabled=${this.readonly}
                                @click=${() => this.insertTextAtCursor('@var:name')}
                                title=${this.t('markdown_editor.insert_var_ref')}>${'@var:name'}</button>
                            ` : html`
                            <button type="button" class="tool-btn mono" ?disabled=${this.readonly}
                                @click=${() => this.insertTextAtCursor('{variable}')}>${'{variable}'}</button>
                            <button type="button" class="tool-btn mono" ?disabled=${this.readonly}
                                @click=${() => this.insertTextAtCursor('{?optional}')}>${'{?optional}'}</button>
                            <button type="button" class="tool-btn mono" ?disabled=${this.readonly}
                                @click=${() => this.insertTextAtCursor('{for item in list}\n{item}\n{endfor}')}>${this.t('markdown_editor.insert_loop')}</button>
                            `}
                        </div>
                        ` : nothing}
                        ` : nothing}
                        ${this.enableVoiceDictation && !this.readonly ? html`
                        <div class="tool-group voice-dictation-group">
                            <platform-voice-dictation
                                density="dense"
                                @transcribed=${this._onVoiceDictationTranscribed}
                            ></platform-voice-dictation>
                        </div>
                        ` : nothing}
                    </div>
                ` : nothing}

                ${this.splitMode ? html`
                    <div class="split-container">
                        <div class="split-pane">
                            <div class="split-pane-label">${this.t('markdown_editor.split_pane_edit')}</div>
                            <div id="codemirror-container"></div>
                        </div>
                        <div class="split-pane">
                            <div class="split-pane-label">${this.t('markdown_editor.split_pane_preview')}</div>
                            ${this._renderPreview()}
                        </div>
                    </div>
                ` : html`
                    <div id="codemirror-container" class="${this.previewMode ? 'hidden' : ''}"></div>
                    ${this.previewMode ? this._renderPreview() : ''}
                `}

                ${this.showHint && !this.fullscreenMode ? html`
                    <div class="syntax-footer">
                        ${this.enableVariables ? html`
                        <div class="syntax-list" aria-label=${this.t('markdown_editor.syntax_help')}>
                            <span class="syntax-list-label">${this.t('markdown_editor.available_variables')}</span>
                            ${availableVariables.length > 0
                                ? availableVariables.map((entry) => html`
                                    <button
                                        type="button"
                                        class="syntax-chip"
                                        data-source=${entry.source || 'system'}
                                        title=${this._variableChipTitle(entry)}
                                        ?disabled=${this.readonly}
                                        @click=${() => this.insertTextAtCursor(
                                            this.variableSyntax === 'at-ref'
                                                ? `@var:${entry.name}`
                                                : `{${entry.name}}`
                                        )}
                                    >${this.variableSyntax === 'at-ref'
                                        ? `@var:${entry.name}`
                                        : `{${entry.name}}`}</button>
                                `)
                                : html`<span class="editor-status">${this.t('markdown_editor.no_available_variables')}</span>`}
                        </div>
                        ` : nothing}
                        <span class="editor-status">
                            ${this.t('markdown_editor.document_stats', { words: stats.words, characters: stats.characters })}
                        </span>
                    </div>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('platform-markdown-editor', PlatformMarkdownEditor);

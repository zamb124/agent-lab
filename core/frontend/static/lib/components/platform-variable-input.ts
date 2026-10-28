/**
 * platform-variable-input — field-pill with single-line CodeMirror:
 * highlight / hover / autocomplete for `@var:` and `@state:`.
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import { variableRefsStyles } from '../styles/shared/variable-refs.styles.js';
import './fields/platform-field-shell.js';
import { listSystemVariableKeys } from './variables/platform-system-variables-catalog.js';
import { createVariableExtensions, refreshVariableDecorations } from '../codemirror/variable-extensions.js';
import type {
    CmEditorViewLike,
    CmModule,
    CmTransactionLike,
    VariableSyntaxMode,
} from '../codemirror/variable-extensions.js';
import type { ResourceController } from '../base/use-resource.js';
import { isPlainRecord } from '../events/payload.js';

function _asString(value: unknown): string {
    if (typeof value === 'string') {
        return value;
    }
    if (value === null || value === undefined) {
        return '';
    }
    return String(value);
}

function _asArray(value: unknown): unknown[] {
    if (!Array.isArray(value)) {
        throw new TypeError('platform-variable-input: expected array');
    }
    const items: unknown[] = [];
    for (const item of value) items.push(item);
    return items;
}

function isExpressionPayload(payload: unknown): boolean {
    if (payload === undefined || payload === null) return false;
    if (!isPlainRecord(payload)) {
        throw new Error('platform-variable-input: variable payload must be an object');
    }
    const base = payload.base;
    if (base === undefined || base === null) return false;
    if (!isPlainRecord(base)) {
        throw new Error('platform-variable-input: variable payload.base must be an object');
    }
    return base.value_kind === 'expression';
}

function companyCatalogEntry(rawItem: unknown): { name: string; type: string; source: string; hasValue: boolean } {
    if (!isPlainRecord(rawItem)) {
        throw new Error('platform-variable-input: catalog item must be an object');
    }
    const key = rawItem.variable_key;
    if (typeof key !== 'string' || key.length === 0) {
        throw new Error('platform-variable-input: variable_key must be a non-empty string');
    }
    return {
        name: key,
        type: isExpressionPayload(rawItem.payload) ? 'expression' : 'string',
        source: 'company',
        hasValue: true,
    };
}

export class PlatformVariableInput extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        value: { type: String },
        label: { type: String },
        placeholder: { type: String },
        /** Live `@var:` / brace preview map from parent (flow variables). */
        previewValues: { type: Object, attribute: false },
        /** Live `@state:` preview map from previewExecutionState. */
        statePreview: { type: Object, attribute: false },
        /** Catalog entries `{ name, type?, source?, hasValue? }`. */
        variableCatalog: { type: Array, attribute: false },
        /** Known `@state:` paths for autocomplete. */
        statePaths: { type: Array, attribute: false },
        /** `at-ref` (`@var:`/`@state:`), `brace` (`{path}` шаблонов Flow UI) или `both`. */
        syntax: { type: String },
        _focused: { type: Boolean, state: true },
    };
    declare value: string;
    declare label: string;
    declare placeholder: string;
    declare previewValues: Record<string, unknown>;
    declare statePreview: Record<string, unknown>;
    declare variableCatalog: Array<{ name?: unknown; type?: string; source?: string; hasValue?: boolean }>;
    declare statePaths: string[];
    declare syntax: VariableSyntaxMode;
    declare _focused: boolean;

    private _focusOutTimer: ReturnType<typeof setTimeout> | null;
    private _onFocusIn: () => void;
    private _onFocusOut: () => void;
    private _cmBundle: CmModule | null;
    private _editorView: CmEditorViewLike | null;
    private _variablesRefreshInProgress: boolean;
    private _previewFingerprint: string;
    private _variables: ResourceController;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        variableRefsStyles,
        css`
            :host {
                display: block;
                position: relative;
                min-width: 0;
            }

            #cm-host {
                width: 100%;
                min-width: 0;
                position: relative;
            }

            .cm-wrap {
                position: relative;
                width: 100%;
                min-width: 0;
            }

            #cm-host .cm-editor {
                background: transparent;
                font-family: inherit;
                font-size: var(--field-pill-input-size);
                font-weight: var(--field-pill-input-weight);
                line-height: var(--field-pill-input-line);
                color: var(--field-pill-input-color);
            }

            #cm-host .cm-scroller {
                font-family: inherit;
                overflow-x: auto;
                overflow-y: hidden;
            }

            #cm-host .cm-content {
                padding: 0;
                caret-color: var(--accent);
                min-height: var(--field-pill-input-line);
            }

            #cm-host .cm-line {
                padding: 0;
            }

            #cm-host .cm-focused {
                outline: none;
            }

            #cm-host .cm-gutters {
                display: none;
            }

            .cm-placeholder-overlay {
                position: absolute;
                inset: 0;
                pointer-events: none;
                color: var(--text-disabled);
                font-size: var(--field-pill-input-size);
                font-weight: var(--font-normal);
                line-height: var(--field-pill-input-line);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this.label = '';
        this.placeholder = '';
        this.previewValues = {};
        this.statePreview = {};
        this.variableCatalog = [];
        this.statePaths = [];
        this.syntax = 'at-ref';
        this._focused = false;
        this._focusOutTimer = null;
        this._onFocusIn = () => {
            this._focused = true;
        };
        this._onFocusOut = () => {
            if (this._focusOutTimer !== null) clearTimeout(this._focusOutTimer);
            this._focusOutTimer = setTimeout(() => {
                this._focused = this.matches(':focus-within');
            }, 0);
        };
        this._cmBundle = null;
        this._editorView = null;
        this._variablesRefreshInProgress = false;
        this._previewFingerprint = '';
        this._variables = this.useResource('secrets/variables', { autoload: true });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        this.addEventListener('focusin', this._onFocusIn);
        this.addEventListener('focusout', this._onFocusOut);
    }

    override disconnectedCallback(): void {
        this.removeEventListener('focusin', this._onFocusIn);
        this.removeEventListener('focusout', this._onFocusOut);
        if (this._focusOutTimer !== null) clearTimeout(this._focusOutTimer);
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }
        super.disconnectedCallback();
    }

    override firstUpdated(changed: PropertyValues<this>): void {
        void this._initCodeMirror();
    }

    override updated(changed: PropertyValues<this>): void {
        if (this._editorView && changed.has('value')) {
            const current = this._editorView.state.doc.toString();
            if (this.value !== current) {
                this._editorView.dispatch({
                    changes: { from: 0, to: current.length, insert: this.value },
                });
            }
        }

        if (this._editorView) {
            const next = this._fingerprint();
            if (next !== this._previewFingerprint) {
                this._previewFingerprint = next;
                this._variablesRefreshInProgress = true;
                try {
                    refreshVariableDecorations(this._editorView);
                } finally {
                    this._variablesRefreshInProgress = false;
                }
            }
        }
    }

    _fingerprint() {
        return [
            JSON.stringify(this.previewValues),
            JSON.stringify(this.statePreview),
            JSON.stringify(this.variableCatalog),
            JSON.stringify(this.statePaths),
            JSON.stringify(this._companyCatalogEntries().map((e) => e.name)),
        ].join('|');
    }

    _companyCatalogEntries(): Array<{ name: string; type: string; source: string; hasValue: boolean }> {
        const companyItems = _asArray(this._variables.items).map((rawItem) => companyCatalogEntry(rawItem));
        const systemItems = listSystemVariableKeys().map((key) => ({
            name: key,
            type: 'string',
            source: 'system',
            hasValue: false,
        }));
        return [...companyItems, ...systemItems];
    }

    _mergedCatalog(): Array<{ name: string; type?: string; source?: string; hasValue?: boolean; kind?: string }> {
        const byName = new Map<string, { name: string; type?: string; source?: string; hasValue?: boolean; kind?: string }>();
        for (const entry of this._companyCatalogEntries()) {
            byName.set(entry.name, entry);
        }
        for (const entry of Array.isArray(this.variableCatalog) ? this.variableCatalog : []) {
            if (!entry || typeof entry.name !== 'string') continue;
            byName.set(entry.name, { ...entry, name: entry.name });
        }
        return [...byName.values()];
    }

    _mergedValues(): Record<string, unknown> {
        const values = this.previewValues && typeof this.previewValues === 'object' && !Array.isArray(this.previewValues)
            ? { ...this.previewValues }
            : {};
        return values;
    }

    async _initCodeMirror(): Promise<void> {
        const cm = await import('/static/core/assets/codemirror/codemirror-bundle.js');
        this._cmBundle = cm;
        this._createEditor();
    }

    _createEditor() {
        const host = this.shadowRoot?.querySelector('#cm-host');
        if (!host || !this._cmBundle) {
            return;
        }
        if (this._editorView) {
            this._editorView.destroy();
            this._editorView = null;
        }

        const cm = this._cmBundle;
        const self = this;
        const variableExtensions = createVariableExtensions(cm, {
            syntax: this.syntax,
            getValues: () => self._mergedValues(),
            getStatePreview: () => (
                self.statePreview && typeof self.statePreview === 'object' && !Array.isArray(self.statePreview)
                    ? self.statePreview
                    : {}
            ),
            getCatalog: () => self._mergedCatalog(),
            getStatePaths: () => (Array.isArray(self.statePaths) ? self.statePaths : []),
            t: (key) => {
                if (key === 'undefined') return self.t('markdown_editor.var_undefined');
                if (key === 'runtime_value') return self.t('markdown_editor.runtime_value');
                throw new Error(`platform-variable-input: unknown variable tooltip key ${key}`);
            },
        });

        const singleLineFilter = cm.EditorState.transactionFilter.of((tr: CmTransactionLike) => {
            if (!tr.docChanged) {
                return tr;
            }
            let hasNewline = false;
            tr.changes.iterChanges((_fromA: number, _toA: number, _fromB: number, _toB: number, inserted: { toString(): string }) => {
                if (inserted.toString().includes('\n')) {
                    hasNewline = true;
                }
            });
            if (!hasNewline && tr.newDoc.lines === 1) {
                return tr;
            }
            return [{
                changes: {
                    from: 0,
                    to: tr.startState.doc.length,
                    insert: tr.newDoc.toString().replace(/\n/g, ' '),
                },
                selection: tr.newSelection,
                filter: false,
            }];
        });

        this._editorView = new cm.EditorView({
            state: cm.EditorState.create({
                doc: this.value,
                extensions: [
                    cm.history(),
                    singleLineFilter,
                    cm.keymap.of([
                        ...cm.defaultKeymap,
                        ...cm.historyKeymap,
                        {
                            key: 'Enter',
                            run: () => true,
                        },
                    ]),
                    ...variableExtensions,
                    cm.EditorView.theme({
                        '&': { backgroundColor: 'transparent' },
                        '&.cm-focused': { outline: 'none' },
                        '.cm-content': { fontFamily: 'inherit' },
                    }),
                    cm.EditorView.updateListener.of((update: { docChanged: boolean; state: { doc: { toString(): string } } }) => {
                        if (update.docChanged && !self._variablesRefreshInProgress) {
                            const next = update.state.doc.toString();
                            self.value = next;
                            self.emit('change', { value: next });
                        }
                    }),
                ],
            }),
            parent: host,
        });
        this._previewFingerprint = this._fingerprint();
    }

    override render(): TemplateResult {
        const hasLabel = typeof this.label === 'string' && this.label.length > 0;
        const floated = (typeof this.value === 'string' && this.value.length > 0) || this._focused;
        const showPlaceholder = (typeof this.value !== 'string' || this.value.length === 0)
            && typeof this.placeholder === 'string'
            && this.placeholder.length > 0
            && (!hasLabel || floated);
        return html`
            <platform-field-shell .label=${this.label} ?floated=${floated} editable>
                <div class="cm-wrap">
                    ${showPlaceholder
                        ? html`<div class="cm-placeholder-overlay">${this.placeholder}</div>`
                        : nothing}
                    <div id="cm-host" data-canon="search-as-you-type"></div>
                </div>
            </platform-field-shell>
        `;
    }
}

customElements.define('platform-variable-input', PlatformVariableInput);

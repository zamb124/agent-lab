/**
 * Редактор блока ``html``: preview-first (кадр холста + исходник), inspector State/Events/Help,
 * сниппеты в курсор. Apply отдаёт ``source``; test-state в документ не пишется.
 */

import { css, html, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { platformStorageKey } from '@platform/lib/utils/storage-keys.js';
import { htmlBlockState, htmlBoundPaths } from '@platform/lib/flow-ui/runtime/html-sandbox.js';
import {
    FLOW_UI_API,
    HTML_EDITOR_LIVE_MS,
    HTML_EDITOR_SNIPPETS,
    HTML_EDITOR_VIEWPORTS,
    mergeTestState,
    parseTestState,
    previewBlock,
    setValueAtPath,
} from '@platform/lib/flow-ui/editor/html-editor-api.js';
import { htmlEditorStageStyles, renderHtmlEditorStage } from '@platform/lib/flow-ui/editor/html-editor-stage.js';
import { htmlEditorInspectorStyles, renderHtmlEditorInspector } from '@platform/lib/flow-ui/editor/html-editor-inspector.js';
import '@platform/lib/components/platform-code-editor.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/fields/platform-field.js';
import '@platform/lib/flow-ui/blocks/html.js';

const LAYOUT_KEY = platformStorageKey('flows', 'html_editor_layout');

export class FlowsInterfaceHtmlEditorModal extends PlatformModal {
    static modalKind = 'flows.interface_html_editor';
    static i18nNamespace = 'flows';

    static properties = {
        source: { type: String },
        block: { attribute: false },
        sampleState: { attribute: false },
        statePaths: { attribute: false },
        onApply: { attribute: false },
        _draft: { type: String, state: true },
        _liveSource: { type: String, state: true },
        _stateText: { type: String, state: true },
        _stateError: { type: String, state: true },
        _log: { attribute: false, state: true },
        _viewport: { type: String, state: true },
        _previewTheme: { type: String, state: true },
        _tab: { type: String, state: true },
        _stateMode: { type: String, state: true },
        _layout: { type: String, state: true },
        _snippetsOpen: { type: Boolean, state: true },
        _replaceConfirm: { type: Boolean, state: true },
    };

    static styles = [PlatformModal.styles, htmlEditorStageStyles, htmlEditorInspectorStyles, css`
        .workspace { display: grid; grid-template-rows: minmax(0, 1fr) minmax(160px, 280px); gap: var(--space-3); height: 100%; min-height: 60vh; min-width: 0; }
        .panes { display: grid; gap: var(--space-3); min-height: 0; }
        .workspace[data-layout='preview'] .panes { grid-template-columns: minmax(0, 1.4fr) minmax(280px, 1fr); }
        .workspace[data-layout='split'] .panes { grid-template-columns: 1fr 1fr; }
        .pane { display: grid; min-height: 0; min-width: 0; }
        platform-code-editor { min-height: 0; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; }
        .header-buttons { flex-wrap: wrap; }
        .tools { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
        .pane .hint { font-size: 11px; color: var(--text-tertiary); }
        .snippets { display: grid; gap: 4px; width: min(280px, 90vw); padding: 8px; }
        .snippets platform-button { width: 100%; }
        .snippets .confirm { font-size: 11px; color: var(--text-secondary); padding: 4px 10px; }
        .dirty { margin-right: 6px; color: var(--warning); }
        @media (max-width: 1200px) { .workspace { grid-template-rows: minmax(0, 1fr) auto; } }
        @media (max-width: 900px) { .panes, .workspace[data-layout='preview'] .panes, .workspace[data-layout='split'] .panes { grid-template-columns: 1fr; } }
    `];

    constructor() {
        super();
        this.size = 'full';
        this.source = '';
        this.block = null;
        this.sampleState = {};
        this.statePaths = [];
        this.onApply = null;
        this._draft = '';
        this._liveSource = '';
        this._stateText = '';
        this._stateError = '';
        this._log = [];
        this._viewport = 'desktop';
        this._previewTheme = 'dark';
        this._tab = 'state';
        this._stateMode = 'fields';
        this._layout = 'preview';
        this._snippetsOpen = false;
        this._replaceConfirm = false;
        this._lastGoodState = {};
        this._cachedPreview = null;
        this._liveTimer = 0;
        this._snippetsAnchor = null;
    }

    connectedCallback() {
        super.connectedCallback();
        this._draft = this.source;
        this._liveSource = this.source;
        const stored = localStorage.getItem(LAYOUT_KEY);
        if (stored === 'split' || stored === 'preview') this._layout = stored;
        this._setStateText(JSON.stringify(this._initialTestState(), null, 2));
    }

    disconnectedCallback() {
        if (this._liveTimer) window.clearTimeout(this._liveTimer);
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated?.(changed);
        if (changed.has('_previewTheme')) {
            this.updateComplete.then(() => this.renderRoot.querySelector('flow-ui-html-block')?.pushHost());
        }
    }

    _initialTestState() {
        const projection = htmlBlockState({ ...this.block, source: this._draft }, this.sampleState);
        for (const path of this._readMeta().paths) {
            if (path.includes('.') || path in projection) continue;
            projection[path] = null;
        }
        return projection;
    }

    _readMeta() {
        try {
            const bound = htmlBoundPaths(this._draft);
            const fields = Array.isArray(this.block.fields) ? this.block.fields : [];
            return { paths: [...fields.filter((path) => !bound.includes(path)), ...bound], error: '' };
        } catch (error) {
            return { paths: [], error: error.message };
        }
    }

    _setDraft(value, immediate) {
        this._draft = value;
        if (this._liveTimer) window.clearTimeout(this._liveTimer);
        if (immediate === true) {
            this._liveSource = value;
            this._liveTimer = 0;
            return;
        }
        this._liveTimer = window.setTimeout(() => {
            this._liveSource = this._draft;
            this._liveTimer = 0;
        }, HTML_EDITOR_LIVE_MS);
    }

    _setStateText(text) {
        this._stateText = text;
        const parsed = parseTestState(text);
        this._stateError = parsed.ok ? '' : parsed.error;
        if (parsed.ok) this._lastGoodState = parsed.value;
    }

    _previewBlock() {
        this._cachedPreview = previewBlock(this.block, this._liveSource, this._cachedPreview);
        return this._cachedPreview;
    }

    _extensions(cm) {
        const paths = this.statePaths;
        const source = (context) => {
            const attribute = context.matchBefore(/data-(bind|show)="[A-Za-z0-9_.]*/);
            if (attribute !== null) {
                const from = attribute.from + attribute.text.indexOf('"') + 1;
                return { from, options: paths.map((path) => ({ label: path, type: 'variable' })) };
            }
            const word = context.matchBefore(/[\w.]*/);
            if (word === null || (word.from === word.to && !context.explicit)) return null;
            return { from: word.from, options: FLOW_UI_API.map((entry) => ({ label: entry.label, detail: entry.detail, info: this.t(`interface_editor.html_api_${entry.key}`), type: 'function' })) };
        };
        return [cm.autocompletion({ override: [source] })];
    }

    _apply() {
        if (typeof this.onApply !== 'function') throw new Error('flows.interface_html_editor: onApply callback is required');
        if (this._draft.trim() === '') return;
        this.onApply(this._draft);
        this.close();
    }

    _onBridgeEvent(event) {
        const entry = event.kind === 'error'
            ? { kind: 'error', text: event.stack !== '' ? `${event.message}\n${event.stack}` : event.message }
            : event.kind === 'action' ? { kind: 'action', text: `send(${JSON.stringify(event.name)}, ${JSON.stringify(event.payload)})` }
                : event.kind === 'value' ? { kind: 'value', text: `setValue(${JSON.stringify(event.value)})` }
                    : { kind: 'open_url', text: `openUrl(${JSON.stringify(event.url)})` };
        this._log = [...this._log.slice(-49), entry];
    }

    _snippetSource(id) {
        const spec = HTML_EDITOR_SNIPPETS.find((item) => item.id === id);
        return spec?.kitchen === true
            ? this.t('interface_editor.default_text_html_source')
            : this.t(`interface_editor.html_snippet_${id}_source`);
    }

    _snippetState(id) {
        const spec = HTML_EDITOR_SNIPPETS.find((item) => item.id === id);
        const raw = spec?.kitchen === true
            ? this.t('interface_editor.html_example_state')
            : this.t(`interface_editor.html_snippet_${id}_state`);
        return JSON.parse(raw);
    }

    _insertAtSource(chunk) {
        const editor = this.renderRoot.querySelector('platform-code-editor[data-html-source]');
        if (editor && typeof editor.insertAtCursor === 'function') {
            editor.insertAtCursor(chunk);
            this._setDraft(editor.value, true);
            return;
        }
        this._setDraft(`${this._draft}${chunk}`, true);
    }

    _insertSnippet(id) {
        this._insertAtSource(this._snippetSource(id));
        this._setStateText(JSON.stringify(mergeTestState(this._lastGoodState, this._snippetState(id)), null, 2));
        this._snippetsOpen = false;
        this._replaceConfirm = false;
    }

    _replaceSource() {
        if (this._draft.trim() !== '' && this._draft !== this.source && this._replaceConfirm !== true) {
            this._replaceConfirm = true;
            return;
        }
        this._replaceConfirm = false;
        this._snippetsOpen = false;
        this._setDraft(this.t('interface_editor.default_text_html_source'), true);
        this._setStateText(JSON.stringify(JSON.parse(this.t('interface_editor.html_example_state')), null, 2));
        this._log = [];
    }

    _onField(path, value, error) {
        if (error) return;
        const next = setValueAtPath(JSON.parse(JSON.stringify(this._lastGoodState)), path, value);
        this._setStateText(JSON.stringify(next, null, 2));
    }

    _insertToken(token) {
        this._insertAtSource(`var(${token})`);
    }

    _setLayout(layout) {
        this._layout = layout;
        localStorage.setItem(LAYOUT_KEY, layout);
    }

    renderHeader() {
        return this.t('interface_editor.html_editor_title', { block_id: this.block.block_id });
    }

    renderHeaderActions() {
        const t = (key) => this.t(key);
        return html`<div class="tools">
            <platform-segmented-control density="compact" icon-only .value=${this._viewport}
                .items=${Object.keys(HTML_EDITOR_VIEWPORTS).map((value) => ({ value, icon: value === 'desktop' ? 'monitor' : (value === 'tablet' ? 'tablet' : 'smartphone'), title: t(`interface_editor.viewport_${value}`) }))}
                aria-label=${t('interface_editor.viewport')}
                @change=${(event) => { this._viewport = event.detail.value; }}></platform-segmented-control>
            <platform-segmented-control density="compact" .value=${this._previewTheme}
                .items=${[{ value: 'dark', label: t('interface_editor.html_theme_dark') }, { value: 'light', label: t('interface_editor.html_theme_light') }]}
                @change=${(event) => { this._previewTheme = event.detail.value; }}></platform-segmented-control>
            <platform-button ghost density="compact" class="snippets-trigger" @click=${(event) => {
                this._snippetsAnchor = event.currentTarget;
                this._snippetsOpen = !this._snippetsOpen;
                this._replaceConfirm = false;
            }}>
                <platform-icon name="sparkle" size="13"></platform-icon>${t('interface_editor.html_snippets')}
            </platform-button>
            <platform-popover trigger="manual" .anchor=${this._snippetsAnchor} ?open=${this._snippetsOpen}
                placement="bottom-end" dismiss-on-outside @popover-dismiss=${() => { this._snippetsOpen = false; this._replaceConfirm = false; }}>
                <div class="snippets">
                    ${HTML_EDITOR_SNIPPETS.map((item) => html`<platform-button ghost density="compact" block data-snippet=${item.id} @click=${() => this._insertSnippet(item.id)}>${t(`interface_editor.html_snippet_${item.id}`)}</platform-button>`)}
                    ${this._replaceConfirm
                        ? html`<div class="confirm">${t('interface_editor.html_replace_confirm')}</div>
                            <platform-button ghost density="compact" block data-replace-yes @click=${() => this._replaceSource()}>${t('interface_editor.html_replace_source')}</platform-button>
                            <platform-button ghost density="compact" block @click=${() => { this._replaceConfirm = false; }}>${t('interface_editor.cancel')}</platform-button>`
                        : html`<platform-button ghost density="compact" block data-replace @click=${() => this._replaceSource()}>${t('interface_editor.html_replace_source')}</platform-button>`}
                    <platform-button ghost density="compact" block data-layout @click=${() => this._setLayout(this._layout === 'split' ? 'preview' : 'split')}>${t(`interface_editor.html_layout_${this._layout === 'split' ? 'preview' : 'split'}`)}</platform-button>
                </div>
            </platform-popover>
            <platform-button ghost density="compact" @click=${() => this.renderRoot.querySelector('flow-ui-html-block')?.reload()}>
                <platform-icon name="refresh" size="13"></platform-icon>${t('interface_editor.html_reload')}
            </platform-button>
        </div>`;
    }

    renderBody() {
        const parsed = parseTestState(this._stateText);
        const previewState = parsed.ok ? parsed.value : this._lastGoodState;
        const meta = this._readMeta();
        const empty = this._liveSource.trim() === '';
        const t = (key) => this.t(key);
        return html`<div class="workspace" data-layout=${this._layout}>
            <div class="panes">
                ${renderHtmlEditorStage({
                    viewport: this._viewport, theme: this._previewTheme, empty, error: meta.error, t,
                    onSnippet: (id) => this._insertSnippet(id),
                    canvas: html`<flow-ui-html-block .block=${this._previewBlock()} .state=${previewState} .readonly=${true}
                        .onBridgeEvent=${(event) => this._onBridgeEvent(event)}></flow-ui-html-block>`,
                })}
                <div class="pane">
                    <platform-code-editor data-html-source language="html" fill-parent line-wrapping .readonly=${false} .value=${this._draft}
                        .extensionsFactory=${(cm) => this._extensions(cm)}
                        @change=${(event) => this._setDraft(event.detail.value, false)}></platform-code-editor>
                    <div class="hint">${t('interface_editor.html_api_hint')}</div>
                </div>
            </div>
            ${renderHtmlEditorInspector({
                tab: this._tab, stateMode: this._stateMode, paths: meta.paths, bindError: meta.error,
                state: this._lastGoodState, stateText: this._stateText, stateError: this._stateError, log: this._log,
                writes: this.block.field, t,
                onTab: (tab) => { this._tab = tab; },
                onStateMode: (mode) => { this._stateMode = mode; },
                onStateText: (text) => this._setStateText(text),
                onField: (path, value, error) => this._onField(path, value, error),
                onClear: () => { this._log = []; },
                onToken: (token) => this._insertToken(token),
            })}
        </div>`;
    }

    renderFooter() {
        const empty = this._draft.trim() === '';
        return html`
            <platform-button ghost @click=${() => this.close()}>${this.t('interface_editor.cancel')}</platform-button>
            <platform-button primary ?disabled=${empty} title=${empty ? this.t('interface_editor.html_apply_empty') : ''} @click=${() => this._apply()}>
                ${this._draft !== this.source ? html`<span class="dirty">●</span>` : nothing}${this.t('interface_editor.html_apply')}
            </platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-html-editor-modal')) customElements.define('flows-interface-html-editor-modal', FlowsInterfaceHtmlEditorModal);
registerModalKind(FlowsInterfaceHtmlEditorModal.modalKind, 'flows-interface-html-editor-modal');

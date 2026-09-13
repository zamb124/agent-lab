/**
 * Редактор блока ``html``: preview-first (кадр холста + исходник), inspector State/Events/Help.
 * Viewport/theme/Reload — тулбар превью; сниппеты/replace/layout — тулбар исходника.
 * Apply отдаёт ``source``; test-state в документ не пишется.
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
const PANELS_KEY = platformStorageKey('flows', 'html_editor_panels');
const PANEL_NAMES = Object.freeze(['preview', 'source', 'inspector']);
const DEFAULT_PANELS = Object.freeze({ preview: true, source: true, inspector: true });

function readStoredPanels() {
    try {
        const raw = JSON.parse(localStorage.getItem(PANELS_KEY));
        if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return { ...DEFAULT_PANELS };
        const next = { ...DEFAULT_PANELS };
        for (const name of PANEL_NAMES) {
            if (typeof raw[name] === 'boolean') next[name] = raw[name];
        }
        if (!next.preview && !next.source && !next.inspector) return { ...DEFAULT_PANELS };
        return next;
    } catch {
        return { ...DEFAULT_PANELS };
    }
}

export class FlowsInterfaceHtmlEditorModal extends PlatformModal {
    static modalKind = 'flows.interface_html_editor';
    static i18nNamespace = 'flows';

    static properties = {
        source: { type: String, attribute: false },
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
        _panels: { attribute: false, state: true },
    };

    static styles = [PlatformModal.styles, htmlEditorStageStyles, htmlEditorInspectorStyles, css`
        .modal-content { overflow: hidden; display: flex; flex-direction: column; }
        .workspace {
            display: grid; grid-template-rows: auto minmax(0, 1fr) minmax(160px, 280px); gap: var(--space-3);
            flex: 1 1 auto; height: 100%; min-height: 60vh; min-width: 0; overflow: hidden; isolation: isolate;
        }
        .workspace[data-inspector='off'] { grid-template-rows: auto minmax(0, 1fr); }
        .workspace[data-preview='off'][data-source='off'] { grid-template-rows: auto minmax(0, 1fr); }
        .panel-switch { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; min-width: 0; }
        .panel-switch .panel-toggle.is-on {
            background: color-mix(in srgb, var(--accent) 18%, transparent);
            color: var(--accent);
        }
        .panes { display: grid; gap: var(--space-3); min-height: 0; overflow: hidden; max-height: 100%; }
        .workspace[data-layout='preview'] .panes { grid-template-columns: minmax(0, 1.4fr) minmax(280px, 1fr); }
        .workspace[data-layout='split'] .panes { grid-template-columns: 1fr 1fr; }
        .workspace[data-preview='off'] .panes,
        .workspace[data-source='off'] .panes,
        .workspace[data-preview='off'][data-layout='preview'] .panes,
        .workspace[data-source='off'][data-layout='preview'] .panes,
        .workspace[data-preview='off'][data-layout='split'] .panes,
        .workspace[data-source='off'][data-layout='split'] .panes { grid-template-columns: minmax(0, 1fr); }
        .workspace[data-preview='off'] .preview-pane { display: none; }
        .workspace[data-source='off'] .pane { display: none; }
        .workspace[data-inspector='off'] .inspector { display: none; }
        .workspace[data-preview='off'][data-source='off'] .panes { display: none; }
        .pane {
            display: grid; grid-template-rows: auto minmax(0, 1fr) auto;
            min-height: 0; min-width: 0; overflow: hidden;
        }
        .source-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-width: 0; padding-bottom: 6px; }
        .source-toolbar .confirm { font-size: 11px; color: var(--text-secondary); }
        .source-toolbar .collapse { margin-left: auto; }
        platform-code-editor { min-height: 0; border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; }
        .pane .hint { font-size: 11px; color: var(--text-tertiary); }
        .snippets { display: grid; gap: 4px; width: min(280px, 90vw); padding: 8px; }
        .snippets platform-button { width: 100%; }
        .dirty { margin-right: 6px; color: var(--warning); }
        @media (max-width: 1200px) {
            .workspace { grid-template-rows: auto minmax(0, 1fr) auto; }
            .workspace[data-inspector='off'], .workspace[data-preview='off'][data-source='off'] { grid-template-rows: auto minmax(0, 1fr); }
        }
        @media (max-width: 900px) {
            .panes, .workspace[data-layout='preview'] .panes, .workspace[data-layout='split'] .panes { grid-template-columns: 1fr; }
        }
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
        this._panels = { ...DEFAULT_PANELS };
        this._lastGoodState = {};
        this._cachedPreview = null;
        this._liveTimer = 0;
        this._snippetsAnchor = null;
        this._hydrated = false;
        this._originalSource = '';
    }

    connectedCallback() {
        super.connectedCallback();
        this._hydrateDraft();
    }

    willUpdate(changed) {
        super.willUpdate?.(changed);
        if (!this._hydrated && (changed.has('source') || changed.has('block'))) this._hydrateDraft();
    }

    _resolvedSource() {
        if (typeof this.source === 'string' && this.source !== '') return this.source;
        return typeof this.block?.source === 'string' ? this.block.source : '';
    }

    _hydrateDraft() {
        if (this._hydrated || this.block === null) return;
        const next = this._resolvedSource();
        this._draft = next;
        this._liveSource = next;
        this._originalSource = next;
        this._hydrated = true;
        const stored = localStorage.getItem(LAYOUT_KEY);
        if (stored === 'split' || stored === 'preview') this._layout = stored;
        this._panels = readStoredPanels();
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
        if (this._draft.trim() !== '' && this._draft !== this._originalSource && this._replaceConfirm !== true) {
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

    _visiblePanelCount() {
        return PANEL_NAMES.filter((name) => this._panels[name]).length;
    }

    _setPanel(name, visible) {
        if (!PANEL_NAMES.includes(name)) return;
        if (visible !== true && this._visiblePanelCount() <= 1 && this._panels[name]) return;
        const next = { ...this._panels, [name]: visible === true };
        this._panels = next;
        localStorage.setItem(PANELS_KEY, JSON.stringify(next));
        if (visible === true && name === 'preview') {
            this.updateComplete.then(() => this.renderRoot.querySelector('flow-ui-html-block')?.pushHost());
        }
    }

    _togglePanel(name) {
        this._setPanel(name, this._panels[name] !== true);
    }

    _reloadPreview() {
        this.renderRoot.querySelector('flow-ui-html-block')?.reload();
    }

    _renderPanelSwitch(t) {
        const last = this._visiblePanelCount() <= 1;
        return html`<div class="panel-switch" role="group" aria-label=${t('interface_editor.html_panels')}>
            ${PANEL_NAMES.map((name) => {
                const on = this._panels[name] === true;
                const label = t(`interface_editor.html_panel_${name}`);
                return html`<platform-button ghost density="compact"
                    class="panel-toggle ${on ? 'is-on' : ''}"
                    data-panel=${name} data-on=${on ? 'true' : 'false'}
                    ?disabled=${last && on}
                    title=${t(on ? 'interface_editor.html_panel_hide' : 'interface_editor.html_panel_show', { name: label })}
                    @click=${() => this._togglePanel(name)}>${label}</platform-button>`;
            })}
        </div>`;
    }

    _renderSourceToolbar(t) {
        return html`<div class="source-toolbar">
            <platform-button ghost density="compact" class="snippets-trigger" @click=${(event) => {
                this._snippetsAnchor = event.currentTarget;
                this._snippetsOpen = !this._snippetsOpen;
                this._replaceConfirm = false;
            }}>
                <platform-icon name="sparkle" size="13"></platform-icon>${t('interface_editor.html_snippets')}
            </platform-button>
            <platform-popover class="snippets-popover" trigger="manual" .anchor=${this._snippetsAnchor} ?open=${this._snippetsOpen}
                placement="bottom-start" dismiss-on-outside @popover-dismiss=${() => { this._snippetsOpen = false; }}>
                <div class="snippets">
                    ${HTML_EDITOR_SNIPPETS.map((item) => html`<platform-button ghost density="compact" block data-snippet=${item.id} @click=${() => this._insertSnippet(item.id)}>${t(`interface_editor.html_snippet_${item.id}`)}</platform-button>`)}
                </div>
            </platform-popover>
            ${this._replaceConfirm
                ? html`<span class="confirm">${t('interface_editor.html_replace_confirm')}</span>
                    <platform-button ghost density="compact" data-replace-yes @click=${() => this._replaceSource()}>${t('interface_editor.html_replace_source')}</platform-button>
                    <platform-button ghost density="compact" data-replace-cancel @click=${() => { this._replaceConfirm = false; }}>${t('interface_editor.cancel')}</platform-button>`
                : html`<platform-button ghost density="compact" data-replace @click=${() => this._replaceSource()}>${t('interface_editor.html_replace_source')}</platform-button>`}
            ${this._panels.preview && this._panels.source ? html`<platform-segmented-control class="layout-control" density="compact" .value=${this._layout}
                .items=${[
                    { value: 'preview', label: t('interface_editor.html_layout_preview') },
                    { value: 'split', label: t('interface_editor.html_layout_split') },
                ]}
                @change=${(event) => this._setLayout(event.detail.value)}></platform-segmented-control>` : nothing}
            <platform-button ghost density="compact" class="collapse" data-collapse="source"
                ?disabled=${this._visiblePanelCount() <= 1}
                title=${t('interface_editor.html_panel_hide', { name: t('interface_editor.html_panel_source') })}
                @click=${() => this._setPanel('source', false)}>
                <platform-icon name="minimize" size="13"></platform-icon>
            </platform-button>
        </div>`;
    }

    renderHeader() {
        return this.t('interface_editor.html_editor_title', { block_id: this.block?.block_id ?? '' });
    }

    renderBody() {
        if (this.block === null) return nothing;
        const parsed = parseTestState(this._stateText);
        const previewState = parsed.ok ? parsed.value : this._lastGoodState;
        const meta = this._readMeta();
        const empty = this._liveSource.trim() === '';
        const t = (key, vars) => this.t(key, vars);
        return html`<div class="workspace" data-layout=${this._layout}
            data-preview=${this._panels.preview ? 'on' : 'off'}
            data-source=${this._panels.source ? 'on' : 'off'}
            data-inspector=${this._panels.inspector ? 'on' : 'off'}>
            ${this._renderPanelSwitch(t)}
            <div class="panes">
                ${renderHtmlEditorStage({
                    viewport: this._viewport, theme: this._previewTheme, empty, error: meta.error, t,
                    onSnippet: (id) => this._insertSnippet(id),
                    onViewport: (value) => { this._viewport = value; },
                    onTheme: (value) => { this._previewTheme = value; },
                    onReload: () => this._reloadPreview(),
                    onCollapse: () => this._setPanel('preview', false),
                    collapseDisabled: this._visiblePanelCount() <= 1,
                    canvas: this._panels.preview
                        ? html`<flow-ui-html-block .block=${this._previewBlock()} .state=${previewState} .readonly=${true}
                            .onBridgeEvent=${(event) => this._onBridgeEvent(event)}></flow-ui-html-block>`
                        : nothing,
                })}
                <div class="pane">
                    ${this._panels.source ? html`
                        ${this._renderSourceToolbar(t)}
                        <platform-code-editor data-html-source language="html" fill-parent line-wrapping .readonly=${false} .value=${this._draft}
                            .extensionsFactory=${(cm) => this._extensions(cm)}
                            @change=${(event) => this._setDraft(event.detail.value, false)}></platform-code-editor>
                        <div class="hint">${t('interface_editor.html_api_hint')}</div>
                    ` : nothing}
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
                onCollapse: () => this._setPanel('inspector', false),
                collapseDisabled: this._visiblePanelCount() <= 1,
            })}
        </div>`;
    }

    renderFooter() {
        const empty = this._draft.trim() === '';
        return html`
            <platform-button ghost @click=${() => this.close()}>${this.t('interface_editor.cancel')}</platform-button>
            <platform-button primary ?disabled=${empty} title=${empty ? this.t('interface_editor.html_apply_empty') : ''} @click=${() => this._apply()}>
                ${this._draft !== this._originalSource ? html`<span class="dirty">●</span>` : nothing}${this.t('interface_editor.html_apply')}
            </platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-html-editor-modal')) customElements.define('flows-interface-html-editor-modal', FlowsInterfaceHtmlEditorModal);
registerModalKind(FlowsInterfaceHtmlEditorModal.modalKind, 'flows-interface-html-editor-modal');

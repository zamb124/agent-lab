/**
 * Полноэкранный редактор блока ``html``: слева CodeMirror (HTML + автодополнение ``flowUi.*``,
 * ``data-bind``/``data-show`` с путями state), в центре живой sandbox-предпросмотр с тестовым state
 * (JSON) и журналом моста (действия, значения, ошибки), справа шпаргалка: что блок читает и пишет,
 * API ``flowUi``, токены темы. «Применить» отдаёт ``source`` через ``onApply``.
 */

import { css, html, nothing } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { FLOW_UI_HTML_THEME_TOKENS, htmlBlockState, htmlBoundPaths } from '@platform/lib/flow-ui/runtime/html-sandbox.js';
import '@platform/lib/components/platform-code-editor.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/flow-ui/blocks/html.js';

/**
 * Публичный API sandbox (``html-sandbox.js`` BOOTSTRAP): ``label``/``detail`` — для автодополнения,
 * ``signature`` — для шпаргалки; описания — ``interface_editor.html_api_<key>``.
 */
const FLOW_UI_API = Object.freeze([
    { label: 'flowUi.state', detail: 'object', signature: 'flowUi.state', key: 'state' },
    { label: 'flowUi.onChange(', detail: '(state) => void', signature: 'flowUi.onChange((state) => { ... })', key: 'on_change' },
    { label: 'flowUi.send(', detail: '(action, payload?)', signature: "flowUi.send('action', { ... })", key: 'send' },
    { label: 'flowUi.setValue(', detail: '(value)', signature: 'flowUi.setValue(value)', key: 'set_value' },
    { label: 'flowUi.resize()', detail: '()', signature: 'flowUi.resize()', key: 'resize' },
    { label: 'flowUi.openUrl(', detail: '(url)', signature: "flowUi.openUrl('https://...')", key: 'open_url' },
    { label: 'data-bind=""', detail: 'attr', signature: 'data-bind="path"', key: 'data_bind' },
    { label: 'data-show=""', detail: 'attr', signature: 'data-show="path"', key: 'data_show' },
]);

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
        _stateText: { type: String, state: true },
        _log: { attribute: false, state: true },
    };

    static styles = [PlatformModal.styles, css`
        .split { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(300px, 0.9fr) 260px; gap: var(--space-3); height: 100%; min-height: 60vh; }
        .pane { display: grid; grid-template-rows: auto minmax(0, 1fr); gap: var(--space-2); min-height: 0; }
        .pane-title { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); font-size: 12px; font-weight: 650; color: var(--text-secondary); }
        platform-code-editor { border: 1px solid var(--border-subtle); border-radius: var(--radius-md); overflow: hidden; min-height: 0; }
        .preview { display: grid; grid-template-rows: minmax(220px, 1fr) auto minmax(120px, 200px) auto auto; gap: var(--space-2); min-height: 0; }
        .stage { overflow: auto; padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--bg-primary); }
        .label { font-size: 11px; font-weight: 600; color: var(--text-secondary); }
        .log { max-height: 140px; overflow: auto; padding: var(--space-2); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--glass-solid-subtle); font-family: var(--font-mono); font-size: 11.5px; color: var(--text-secondary); white-space: pre-wrap; }
        .log .entry[data-kind='error'] { color: var(--error); }
        .log .entry[data-kind='action'] { color: var(--accent); }
        .log .empty { color: var(--text-tertiary); }
        .hint { font-size: 11px; color: var(--text-tertiary); }
        .sheet { overflow: auto; display: grid; gap: var(--space-3); align-content: start; padding: var(--space-3); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); background: var(--glass-solid-subtle); font-size: 12px; }
        .sheet h4 { margin: 0 0 var(--space-1); font-size: 11px; font-weight: 650; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-tertiary); }
        .sheet code { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-primary); }
        .sheet .api { display: grid; gap: var(--space-2); }
        .sheet .api div { display: grid; gap: 2px; color: var(--text-secondary); }
        .chips { display: flex; flex-wrap: wrap; gap: 4px; }
        .chips code { padding: 1px 7px; border-radius: 999px; border: 1px solid var(--border-subtle); background: var(--bg-primary); }
        .chips .none { color: var(--text-tertiary); }
        .chips .problem { color: var(--error); }
        @media (max-width: 1200px) { .split { grid-template-columns: minmax(0, 1fr) minmax(300px, 0.8fr); } .sheet { grid-column: 1 / -1; } }
        @media (max-width: 900px) { .split { grid-template-columns: 1fr; } }
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
        this._stateText = '';
        this._log = [];
    }

    connectedCallback() {
        super.connectedCallback();
        this._draft = this.source;
        this._stateText = JSON.stringify(this._initialTestState(), null, 2);
    }

    /** Тестовый state открывается как проекция блока: только его пути; отсутствующие в sampleState — ``null``, чтобы форма была видна сразу. */
    _initialTestState() {
        const projection = htmlBlockState(this.block, this.sampleState);
        for (const path of this._readPaths()) {
            if (path.includes('.') || path in projection) continue;
            projection[path] = null;
        }
        return projection;
    }

    /** Стартовый пример: исходник и подходящий к нему тестовый state из i18n. */
    _insertExample() {
        this._draft = this.t('interface_editor.default_text_html_source');
        this._stateText = JSON.stringify(JSON.parse(this.t('interface_editor.html_example_state')), null, 2);
        this._log = [];
    }

    /** Блок для предпросмотра: исходник из редактора, остальное — из выбранного блока. */
    _previewBlock() {
        return { ...this.block, source: this._draft };
    }

    _previewState() {
        return JSON.parse(this._stateText);
    }

    /** Пути, которые блок читает из state: ``fields`` блока плюс ``data-bind``/``data-show`` из черновика. */
    _readPaths() {
        const bound = htmlBoundPaths(this._draft);
        return [...this.block.fields.filter((path) => !bound.includes(path)), ...bound];
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
        if (this._draft.trim() === '') throw new Error('flows.interface_html_editor: source is empty');
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

    renderHeader() {
        return this.t('interface_editor.html_editor_title', { block_id: this.block.block_id });
    }

    _renderSheet() {
        let reads;
        try {
            reads = this._readPaths().map((path) => html`<code>${path}</code>`);
        } catch (error) {
            reads = html`<span class="problem">${error.message}</span>`;
        }
        return html`<aside class="sheet">
            <section>
                <h4>${this.t('interface_editor.html_reads')}</h4>
                <div class="chips">${Array.isArray(reads) && reads.length === 0 ? html`<span class="none">${this.t('interface_editor.html_reads_none')}</span>` : reads}</div>
            </section>
            <section>
                <h4>${this.t('interface_editor.html_writes')}</h4>
                <div class="chips">${this.block.field === null ? html`<span class="none">${this.t('interface_editor.html_writes_none')}</span>` : html`<code>${this.block.field}</code>`}</div>
            </section>
            <section class="api">
                <h4>${this.t('interface_editor.html_api_title')}</h4>
                ${FLOW_UI_API.map((entry) => html`<div><code>${entry.signature}</code><span>${this.t(`interface_editor.html_api_${entry.key}`)}</span></div>`)}
            </section>
            <section>
                <h4>${this.t('interface_editor.html_theme_tokens')}</h4>
                <div class="chips">${FLOW_UI_HTML_THEME_TOKENS.map((token) => html`<code>${token}</code>`)}</div>
                <div class="hint">${this.t('interface_editor.html_theme_tokens_hint')}</div>
            </section>
        </aside>`;
    }

    renderBody() {
        let stateError = '';
        let previewState = {};
        try {
            previewState = this._previewState();
        } catch (error) {
            stateError = error.message;
        }
        return html`<div class="split">
            <div class="pane">
                <div class="pane-title"><span>${this.t('interface_editor.html_source')}</span>
                    <span class="hint">${this.t('interface_editor.html_api_hint')}</span>
                    <platform-button ghost density="compact" @click=${() => this._insertExample()}>
                        <platform-icon name="sparkle" size="13"></platform-icon>${this.t('interface_editor.html_insert_example')}
                    </platform-button>
                </div>
                <platform-code-editor language="html" fill-parent line-wrapping .value=${this._draft} .extensionsFactory=${(cm) => this._extensions(cm)}
                    @change=${(event) => { this._draft = event.detail.value; }}></platform-code-editor>
            </div>
            <div class="pane">
                <div class="pane-title"><span>${this.t('interface_editor.html_preview')}</span></div>
                <div class="preview">
                    <div class="stage">
                        ${stateError === '' ? html`<flow-ui-html-block .block=${this._previewBlock()} .state=${previewState} .readonly=${true}
                            .onBridgeEvent=${(event) => this._onBridgeEvent(event)}></flow-ui-html-block>` : nothing}
                    </div>
                    <div class="label">${this.t('interface_editor.html_test_state')}</div>
                    <platform-code-editor language="json" fill-parent .value=${this._stateText} @change=${(event) => { this._stateText = event.detail.value; }}></platform-code-editor>
                    <div class="hint">${this.t('interface_editor.html_test_state_hint')}</div>
                    ${stateError !== '' ? html`<div class="log"><div class="entry" data-kind="error">${stateError}</div></div>` : html`<div class="log">
                        ${this._log.length === 0 ? html`<div class="empty">${this.t('interface_editor.html_log_empty')}</div>` : this._log.map((entry) => html`<div class="entry" data-kind=${entry.kind}>${entry.text}</div>`)}
                    </div>`}
                </div>
            </div>
            ${this._renderSheet()}
        </div>`;
    }

    renderFooter() {
        return html`
            <platform-button ghost @click=${() => this.close()}>${this.t('interface_editor.cancel')}</platform-button>
            <platform-button primary @click=${() => this._apply()}>${this.t('interface_editor.html_apply')}</platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-html-editor-modal')) customElements.define('flows-interface-html-editor-modal', FlowsInterfaceHtmlEditorModal);
registerModalKind(FlowsInterfaceHtmlEditorModal.modalKind, 'flows-interface-html-editor-modal');

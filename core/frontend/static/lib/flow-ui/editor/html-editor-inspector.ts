/**
 * Inspector HTML-редактора: вкладки State / Events / Help (шпаргалка API и токенов).
 */

import { css, html, nothing } from 'lit';
import { FLOW_UI_HTML_THEME_TOKENS } from '../runtime/html-sandbox.js';
import type { FlowUiRecord } from '../runtime/flow-ui-store.js';
import { FLOW_UI_API, fieldControlKind, fieldEditorValue, parseFieldEditorValue, valueAtSimplePath } from './html-editor-api.js';

export type HtmlEditorT = (key: string, params?: Record<string, string>) => string;

interface HtmlInspectorLogEntry {
    kind: string;
    text: string;
}

export interface HtmlEditorInspectorRenderArgs {
    tab: string;
    stateMode: string;
    paths: string[];
    bindError: string;
    state: FlowUiRecord;
    stateText: string;
    stateError: string;
    log: HtmlInspectorLogEntry[];
    writes: string | null;
    t: HtmlEditorT;
    onTab: (tab: unknown) => void;
    onStateMode: (mode: unknown) => void;
    onStateText: (text: unknown) => void;
    onField: (path: string, value: unknown, error?: string) => void;
    onClear: () => void;
    onToken: (token: string) => void;
    onCollapse: () => void;
    collapseDisabled?: boolean;
}

// static i18nNamespace = 'flows'; host modal passes t()

export const htmlEditorInspectorStyles = css`
    .inspector {
        display: grid; grid-template-rows: auto minmax(0, 1fr); min-height: 0;
        position: relative; z-index: 1; isolation: isolate; overflow: hidden;
        background: var(--bg-elevated);
        border-top: 1px solid var(--border-subtle);
        border-radius: 0 0 var(--radius-md) var(--radius-md);
        padding: 0 var(--space-2) var(--space-2);
        box-sizing: border-box;
    }
    .inspector .tabs { padding: 6px 0 8px; display: flex; align-items: center; gap: 8px; min-width: 0; }
    .inspector .tabs .inspector-tabs { flex: 1; min-width: 0; }
    .inspector .tabs .collapse { flex-shrink: 0; }
    .inspector .body { min-height: 0; overflow: auto; display: grid; gap: 8px; }
    .inspector .fields { display: grid; gap: 8px; }
    .inspector .hint { font-size: 11px; color: var(--text-tertiary); }
    .inspector .log { display: grid; gap: 4px; font-family: var(--font-mono); font-size: 11.5px; color: var(--text-secondary); white-space: pre-wrap; }
    .inspector .log .entry[data-kind='error'] { color: var(--error); }
    .inspector .log .entry[data-kind='action'] { color: var(--accent); }
    .inspector .toolbar { display: flex; justify-content: flex-end; }
    .inspector .sheet { display: grid; gap: var(--space-3); align-content: start; font-size: 12px; }
    .inspector .sheet h4 { margin: 0 0 var(--space-1); font-size: 11px; font-weight: 650; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-tertiary); }
    .inspector .sheet code { font-family: var(--font-mono); font-size: 11.5px; color: var(--text-primary); }
    .inspector .sheet .api { display: grid; gap: var(--space-2); }
    .inspector .sheet .api div { display: grid; gap: 2px; color: var(--text-secondary); }
    .inspector .chips { display: flex; flex-wrap: wrap; gap: 4px; }
    .inspector .chips code, .inspector .chips button {
        padding: 1px 7px; border-radius: 999px; border: 1px solid var(--border-subtle);
        background: var(--bg-primary); color: var(--text-primary); font: inherit; font-family: var(--font-mono); font-size: 11.5px;
    }
    .inspector .chips button { cursor: pointer; }
    .inspector .chips .none { color: var(--text-tertiary); }
    .inspector .chips .problem { color: var(--error); }
    .inspector .badge { color: var(--error); font-size: 11px; }
    .inspector platform-code-editor { min-height: 140px; }
`;

function renderStateFields({ paths, state, t, onField }: {
    paths: string[];
    state: FlowUiRecord;
    t: HtmlEditorT;
    onField: (path: string, value: unknown, error?: string) => void;
}) {
    if (paths.length === 0) return html`<div class="hint">${t('interface_editor.html_reads_none')}</div>`;
    return html`<div class="fields">${paths.map((path) => {
        const value = valueAtSimplePath(state, path);
        const kind = fieldControlKind(value);
        const type = kind === 'json' ? 'text' : kind;
        return html`<platform-field mode="edit" type=${type} .label=${path} .value=${fieldEditorValue(value)}
            @change=${(event: CustomEvent<{ value: unknown }>) => {
                try {
                    onField(path, parseFieldEditorValue(kind, event.detail.value));
                } catch (error) {
                    onField(path, value, error instanceof Error ? error.message : String(error));
                }
            }}></platform-field>`;
    })}</div>`;
}

export function renderHtmlEditorInspector({
    tab, stateMode, paths, bindError, state, stateText, stateError, log, writes,
    t, onTab, onStateMode, onStateText, onField, onClear, onToken, onCollapse, collapseDisabled,
}: HtmlEditorInspectorRenderArgs) {
    const items = [
        { value: 'state', label: t('interface_editor.html_inspector_state'), indicator: stateError !== '' },
        { value: 'events', label: t('interface_editor.html_inspector_events'), indicator: log.some((entry) => entry.kind === 'error') },
        { value: 'help', label: t('interface_editor.html_inspector_help') },
    ];
    return html`<section class="inspector">
        <div class="tabs">
            <platform-segmented-control class="inspector-tabs" density="compact" .value=${tab} .items=${items} aria-label=${t('interface_editor.html_inspector')}
                @change=${(event: CustomEvent<{ value: unknown }>) => onTab(event.detail.value)}></platform-segmented-control>
            <platform-button ghost density="compact" class="collapse" data-collapse="inspector"
                ?disabled=${collapseDisabled === true}
                title=${t('interface_editor.html_panel_hide', { name: t('interface_editor.html_panel_inspector') })}
                @click=${onCollapse}>
                <platform-icon name="minimize" size="13"></platform-icon>
            </platform-button>
        </div>
        <div class="body">
            ${tab === 'state' ? html`
                <platform-segmented-control class="state-mode" density="compact" .value=${stateMode}
                    .items=${[{ value: 'fields', label: t('interface_editor.html_state_fields') }, { value: 'json', label: t('interface_editor.html_state_json') }]}
                    @change=${(event: CustomEvent<{ value: unknown }>) => onStateMode(event.detail.value)}></platform-segmented-control>
                ${stateError !== '' ? html`<div class="badge">${t('interface_editor.html_state_invalid')}: ${stateError}</div>` : nothing}
                ${stateMode === 'fields'
                    ? renderStateFields({ paths, state, t, onField })
                    : html`<platform-code-editor language="json" fill-parent .readonly=${false} .value=${stateText} @change=${(event: CustomEvent<{ value: unknown }>) => onStateText(event.detail.value)}></platform-code-editor>`}
                <div class="hint">${t('interface_editor.html_test_state_hint')}</div>
            ` : nothing}
            ${tab === 'events' ? html`
                <div class="hint">${t('interface_editor.html_log_readonly_hint')}</div>
                <div class="toolbar"><platform-button ghost density="dense" data-log-clear ?disabled=${log.length === 0} @click=${onClear}>${t('interface_editor.html_log_clear')}</platform-button></div>
                <div class="log">
                    ${log.length === 0 ? html`<div class="empty">${t('interface_editor.html_log_empty')}</div>`
                        : log.map((entry) => html`<div class="entry" data-kind=${entry.kind}>${entry.text}</div>`)}
                </div>
            ` : nothing}
            ${tab === 'help' ? html`<aside class="sheet">
                <section>
                    <h4>${t('interface_editor.html_reads')}</h4>
                    <div class="chips">${bindError !== '' ? html`<span class="problem">${bindError}</span>`
                        : (paths.length === 0 ? html`<span class="none">${t('interface_editor.html_reads_none')}</span>`
                            : paths.map((path) => html`<code>${path}</code>`))}</div>
                </section>
                <section>
                    <h4>${t('interface_editor.html_writes')}</h4>
                    <div class="chips">${writes === null || writes === '' ? html`<span class="none">${t('interface_editor.html_writes_none')}</span>` : html`<code>${writes}</code>`}</div>
                </section>
                <section class="api">
                    <h4>${t('interface_editor.html_api_title')}</h4>
                    ${FLOW_UI_API.map((entry) => html`<div><code>${entry.signature}</code><span>${t(`interface_editor.html_api_${entry.key}`)}</span></div>`)}
                </section>
                <section>
                    <h4>${t('interface_editor.html_theme_tokens')}</h4>
                    <div class="chips">${FLOW_UI_HTML_THEME_TOKENS.map((token) => html`<button type="button" data-token=${token} @click=${() => onToken(token)}>${token}</button>`)}</div>
                    <div class="hint">${t('interface_editor.html_theme_tokens_hint')}</div>
                </section>
            </aside>` : nothing}
        </div>
    </section>`;
}

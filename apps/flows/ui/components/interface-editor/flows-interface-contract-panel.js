/**
 * Flow contract panel: what the flow receives from this screen.
 *
 * Server projector (`/interface/contract-preview`) is the only source —
 * editor preview equals runtime `@state:ui_values.*` and `state.content`.
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsInterfaceContractPanel extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        flowId: { type: String },
        document: { attribute: false },
        surfaceId: { type: String },
        _preview: { state: true },
        _error: { state: true },
        _loading: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: grid; gap: 10px; padding: 10px; }
        .title {
            font-size: 11px; font-weight: 700; text-transform: uppercase;
            letter-spacing: .06em; color: var(--text-tertiary);
            display: flex; align-items: center; gap: 6px;
        }
        .hint { font-size: 11px; color: var(--text-tertiary); line-height: 1.4; }
        .legend {
            display: grid; gap: 4px; font-size: 11px; color: var(--text-secondary);
        }
        .legend-row { display: flex; align-items: center; gap: 6px; }
        .swatch {
            width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0;
            border: 1.5px solid var(--accent);
            background: color-mix(in srgb, var(--accent) 30%, transparent);
        }
        .swatch[data-scope='content'] {
            border-color: var(--info);
            background: color-mix(in srgb, var(--info) 30%, transparent);
        }
        .swatch[data-scope='system'] {
            border-color: var(--warning);
            background: color-mix(in srgb, var(--warning) 30%, transparent);
            border-style: dashed;
        }
        .swatch[data-scope='submit'] {
            border-color: var(--success);
            background: color-mix(in srgb, var(--success) 30%, transparent);
        }
        .mode {
            display: inline-flex; align-items: center; gap: 6px;
            padding: 4px 8px; border-radius: 999px;
            background: var(--accent-subtle); color: var(--accent);
            font-size: 11px; font-weight: 650; width: fit-content;
        }
        .fields { display: grid; gap: 6px; }
        .field {
            display: grid; gap: 2px; padding: 8px;
            border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
            background: var(--bg-elevated); cursor: pointer;
        }
        .field:hover { border-color: var(--accent); }
        .field:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
        .field .ref {
            font: 650 11px/1.35 ui-monospace, SFMono-Regular, Menlo, monospace;
            color: var(--accent); word-break: break-all;
        }
        .field .meta {
            font-size: 10px; color: var(--text-tertiary);
            display: flex; flex-wrap: wrap; gap: 6px;
        }
        .pill {
            padding: 1px 5px; border-radius: 4px;
            background: var(--glass-solid-medium);
        }
        .pill[data-on='true'] {
            background: color-mix(in srgb, var(--success) 18%, transparent);
            color: var(--success);
        }
        .content-box {
            margin: 0; padding: 10px; border-radius: var(--radius-md);
            border: 1px solid var(--border-subtle); background: var(--bg-elevated);
            font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
            white-space: pre-wrap; word-break: break-word; color: var(--text-secondary);
            max-height: 220px; overflow: auto;
        }
        .empty { color: var(--text-tertiary); font-size: 11px; font-style: italic; }
        .error { color: var(--error); font-size: 11px; }
        .actions { display: flex; gap: 6px; }
    `];

    constructor() {
        super();
        this.flowId = '';
        this.document = null;
        this.surfaceId = '';
        this._preview = null;
        this._error = '';
        this._loading = false;
        this._contractOp = this.useOp('flows/interface_contract_preview');
        this._refreshTimer = 0;
        this._lastKey = '';
    }

    willUpdate(changed) {
        if (changed.has('document') || changed.has('surfaceId') || changed.has('flowId')) {
            this._scheduleRefresh();
        }
    }

    disconnectedCallback() {
        if (this._refreshTimer) {
            window.clearTimeout(this._refreshTimer);
            this._refreshTimer = 0;
        }
        super.disconnectedCallback();
    }

    _scheduleRefresh() {
        if (this._refreshTimer) {
            window.clearTimeout(this._refreshTimer);
        }
        this._refreshTimer = window.setTimeout(() => {
            this._refreshTimer = 0;
            void this._refresh();
        }, 280);
    }

    _documentKey() {
        if (!this.document || typeof this.document !== 'object') return '';
        return JSON.stringify({
            revision: this.document.revision,
            active_page_id: this.document.active_page_id,
            surface_id: this.surfaceId,
            surfaces: this.document.surfaces,
        });
    }

    async _refresh() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            this._error = this.t('interface_editor.contract_no_flow');
            this._preview = null;
            return;
        }
        if (!this.document || typeof this.document !== 'object') {
            this._preview = null;
            return;
        }
        const key = this._documentKey();
        if (key === this._lastKey && this._preview) return;
        this._lastKey = key;
        this._loading = true;
        this._error = '';
        try {
            const payload = { flow_id: this.flowId, document: this.document };
            if (typeof this.surfaceId === 'string' && this.surfaceId.length > 0) {
                payload.surface_id = this.surfaceId;
            }
            const preview = await this._contractOp.run(payload);
            this._preview = preview && typeof preview === 'object' ? preview : null;
        } catch (error) {
            this._error = error instanceof Error ? error.message : String(error);
            this._preview = null;
        } finally {
            this._loading = false;
        }
    }

    _selectField(componentId) {
        if (typeof componentId !== 'string' || componentId.length === 0) return;
        this.emit('component-select', { componentId, additive: false });
    }

    _renderFields(fields) {
        if (!Array.isArray(fields) || fields.length === 0) {
            return html`<div class="empty">${this.t('interface_editor.contract_fields_empty')}</div>`;
        }
        return html`<div class="fields">${fields.map((field) => html`
            <div
                class="field"
                role="button"
                tabindex="0"
                @click=${() => this._selectField(field.component_id)}
                @keydown=${(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        this._selectField(field.component_id);
                    }
                }}
            >
                <div class="ref">${field.state_ref}</div>
                <div class="meta">
                    <span class="pill">${field.component_type}</span>
                    <span class="pill">${field.label || field.field}</span>
                    <span class="pill" data-on=${field.included_in_content === true ? 'true' : 'false'}>
                        ${field.included_in_content === true
                            ? this.t('interface_editor.contract_in_content')
                            : this.t('interface_editor.contract_not_in_content')}
                    </span>
                </div>
            </div>
        `)}</div>`;
    }

    render() {
        const preview = this._preview;
        return html`
            <div class="title">
                <platform-icon name="zap" size="12"></platform-icon>
                ${this.t('interface_editor.contract_title')}
            </div>
            <div class="hint">${this.t('interface_editor.contract_hint')}</div>
            <div class="legend">
                <div class="legend-row">
                    <span class="swatch" data-scope="input"></span>
                    ${this.t('interface_editor.data_flow_legend_input')}
                </div>
                <div class="legend-row">
                    <span class="swatch" data-scope="content"></span>
                    ${this.t('interface_editor.data_flow_legend_content')}
                </div>
                <div class="legend-row">
                    <span class="swatch" data-scope="system"></span>
                    ${this.t('interface_editor.data_flow_legend_system')}
                </div>
                <div class="legend-row">
                    <span class="swatch" data-scope="submit"></span>
                    ${this.t('interface_editor.data_flow_legend_submit')}
                </div>
            </div>
            <div class="actions">
                <platform-button
                    density="compact"
                    variant="secondary"
                    ?disabled=${this._loading}
                    @click=${() => { this._lastKey = ''; void this._refresh(); }}
                >${this.t('interface_editor.contract_refresh')}</platform-button>
            </div>
            ${this._error ? html`<div class="error">${this._error}</div>` : nothing}
            ${this._loading && !preview
                ? html`<div class="empty">${this.t('interface_editor.contract_loading')}</div>`
                : nothing}
            ${preview ? html`
                <div class="mode">${this.t('interface_editor.contract_mode')}: ${preview.content_mode}</div>
                <div class="title">${this.t('interface_editor.contract_fields')}</div>
                ${this._renderFields(preview.fields)}
                <div class="title">${this.t('interface_editor.contract_content')}</div>
                ${preview.content
                    ? html`<pre class="content-box">${preview.content}</pre>`
                    : html`<div class="empty">${this.t('interface_editor.contract_content_empty')}</div>`}
            ` : nothing}
        `;
    }
}

if (!customElements.get('flows-interface-contract-panel')) {
    customElements.define('flows-interface-contract-panel', FlowsInterfaceContractPanel);
}

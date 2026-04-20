/**
 * flows-tool-picker-modal — выбор tool из реестра.
 *
 * Источник — useResource('flows/tools'). После выбора вызывает props.onPick(toolId)
 * (передаётся вызывающим компонентом) и закрывается.
 */

import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import { asArray } from '../_helpers/flows-resolvers.js';

export class FlowsToolPickerModal extends PlatformModal {
    static modalKind = 'flows.tool_picker';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformModal.properties,
        onPick: { type: Object, attribute: false },
    };

    static styles = [
        ...PlatformModal.styles,
        css`
            .picker-row {
                display: flex; gap: var(--space-2); align-items: center;
                padding: var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                cursor: pointer; margin-bottom: var(--space-1);
            }
            .picker-row:hover { background: var(--glass-solid-medium); }
            .picker-name { font-weight: var(--font-medium); }
            .picker-id { font-size: var(--text-xs); color: var(--text-tertiary); }
            .picker-empty { padding: var(--space-4); text-align: center; color: var(--text-tertiary); }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.onPick = null;
        this._tools = this.useResource('flows/tools', { autoload: true });
    }

    _pick(tool) {
        if (typeof this.onPick === 'function') this.onPick(tool.tool_id);
        this.close();
    }

    renderHeader() {
        return this.t('tool_picker_modal.title');
    }

    renderBody() {
        const items = asArray(this._tools.items);
        if (this._tools.loading && items.length === 0) {
            return html`<glass-spinner></glass-spinner>`;
        }
        if (items.length === 0) {
            return html`<div class="picker-empty">${this.t('tool_picker_modal.empty')}</div>`;
        }
        return html`
            ${items.map((t) => html`
                <div class="picker-row" @click=${() => this._pick(t)}>
                    <div>
                        <div class="picker-name">${typeof t.name === 'string' && t.name.length > 0 ? t.name : t.tool_id}</div>
                        <div class="picker-id">${t.tool_id}</div>
                    </div>
                </div>
            `)}
        `;
    }
}

customElements.define('flows-tool-picker-modal', FlowsToolPickerModal);
registerModalKind(FlowsToolPickerModal.modalKind, 'flows-tool-picker-modal');

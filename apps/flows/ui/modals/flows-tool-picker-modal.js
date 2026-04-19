/**
 * flows-tool-picker-modal — выбор tool из реестра.
 *
 * Источник — useResource('flows/tools'). После выбора вызывает props.onPick(toolId)
 * (передаётся вызывающим компонентом) и закрывается.
 */

import { html, css } from 'lit';
import { PlatformLightModal } from '@platform/lib/components/glass-light-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';

export class FlowsToolPickerModal extends PlatformLightModal {
    static modalKind = 'flows.tool_picker';
    static i18nNamespace = 'flows';

    static properties = {
        ...PlatformLightModal.properties,
        onPick: { type: Object, attribute: false },
    };

    constructor() {
        super();
        this.onPick = null;
        this._tools = this.useResource('flows/tools', { autoload: true });
    }

    _pick(tool) {
        if (typeof this.onPick === 'function') this.onPick(tool.tool_id);
        this.close();
    }

    render() {
        const items = this._tools.items || [];
        return html`
            <div class="light-modal-backdrop" @click=${this._onBackdropClick}></div>
            <div class="light-modal-container picker-shell">
                <style>
                    .picker-shell { padding: var(--space-4); gap: var(--space-3); }
                    .picker-header { display: flex; align-items: center; justify-content: space-between; }
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
                </style>
                <div class="picker-header">
                    <h2>${this.t('tool_picker_modal.title')}</h2>
                    <platform-button @click=${() => this.close()}>
                        <platform-icon name="close" size="14"></platform-icon>
                    </platform-button>
                </div>
                ${this._tools.loading && items.length === 0
                    ? html`<glass-spinner></glass-spinner>`
                    : items.length === 0
                        ? html`<div>${this.t('tool_picker_modal.empty')}</div>`
                        : items.map((t) => html`
                            <div class="picker-row" @click=${() => this._pick(t)}>
                                <div>
                                    <div class="picker-name">${t.name || t.tool_id}</div>
                                    <div class="picker-id">${t.tool_id}</div>
                                </div>
                            </div>
                        `)}
            </div>
        `;
    }
}

customElements.define('flows-tool-picker-modal', FlowsToolPickerModal);
registerModalKind(FlowsToolPickerModal.modalKind, 'flows-tool-picker-modal');

/**
 * Панель инструментов редактора интерфейса: Undo/Redo, режим холста Desktop/Tablet/Mobile,
 * Тест (живой прогон черновика), Шаблоны, AI-помощник и Опубликовать.
 *
 * События: ``editor-undo``, ``editor-redo``, ``editor-viewport {viewport}``, ``editor-preview {preview}``,
 * ``editor-templates``, ``editor-publish``, ``editor-assist {instruction, scope}``.
 */

import { css, html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/fields/platform-field.js';

export class FlowsInterfaceToolbar extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        canUndo: { type: Boolean },
        canRedo: { type: Boolean },
        viewport: { type: String },
        preview: { type: Boolean },
        dirty: { type: Boolean },
        problemCount: { type: Number },
        hasSelection: { type: Boolean },
        assistBusy: { type: Boolean },
        _assistOpen: { state: true },
        _instruction: { state: true },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-bottom: 1px solid var(--border-subtle); background: var(--glass-solid-medium); min-width: 0; }
        .group { display: inline-flex; align-items: center; gap: 4px; }
        .spacer { flex: 1; }
        .status { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-tertiary); white-space: nowrap; }
        .status[data-dirty='true'] { color: var(--warning); }
        .status[data-errors='true'] { color: var(--error); }
        .assist { display: grid; gap: 10px; width: min(420px, 90vw); padding: 12px; }
        .assist-actions { display: flex; gap: 8px; justify-content: flex-end; }
        .assist-hint { font-size: 12px; color: var(--text-tertiary); }
    `];

    constructor() {
        super();
        this.canUndo = false;
        this.canRedo = false;
        this.viewport = 'desktop';
        this.preview = false;
        this.dirty = false;
        this.problemCount = 0;
        this.hasSelection = false;
        this.assistBusy = false;
        this._assistOpen = false;
        this._instruction = '';
    }

    _viewportItems() {
        return [
            { value: 'desktop', icon: 'monitor', title: this.t('interface_editor.viewport_desktop') },
            { value: 'tablet', icon: 'tablet', title: this.t('interface_editor.viewport_tablet') },
            { value: 'mobile', icon: 'smartphone', title: this.t('interface_editor.viewport_mobile') },
        ];
    }

    _submitAssist(scope) {
        const instruction = this._instruction.trim();
        if (instruction === '') return;
        this.emit('editor-assist', { instruction, scope });
        this._assistOpen = false;
        this._instruction = '';
    }

    _renderAssist() {
        const anchor = this.renderRoot.querySelector('.assist-trigger');
        return html`<platform-popover trigger="manual" .anchor=${anchor} ?open=${this._assistOpen} placement="bottom-end" dismiss-on-outside
            @popover-dismiss=${() => { this._assistOpen = false; }}>
            <div class="assist">
                <platform-field mode="edit" type="text" .value=${this._instruction} .label=${this.t('interface_editor.assist_label')}
                    .placeholder=${this.t('interface_editor.assist_placeholder')}
                    @change=${(event) => { this._instruction = event.detail.value; }}></platform-field>
                <div class="assist-hint">${this.t('interface_editor.assist_hint')}</div>
                <div class="assist-actions">
                    <platform-button secondary density="compact" ?disabled=${!this.hasSelection || this.assistBusy} @click=${() => this._submitAssist('block')}>${this.t('interface_editor.assist_block')}</platform-button>
                    <platform-button primary density="compact" ?disabled=${this.assistBusy} @click=${() => this._submitAssist('page')}>${this.t('interface_editor.assist_page')}</platform-button>
                </div>
            </div>
        </platform-popover>`;
    }

    render() {
        const statusKey = this.problemCount > 0 ? 'interface_editor.status_problems' : (this.dirty ? 'interface_editor.status_draft' : 'interface_editor.status_published');
        return html`
            <div class="group">
                <platform-button ghost icon-only density="compact" aria-label=${this.t('interface_editor.undo')} title="⌘Z" ?disabled=${!this.canUndo} @click=${() => this.emit('editor-undo')}><platform-icon name="undo" size="16"></platform-icon></platform-button>
                <platform-button ghost icon-only density="compact" aria-label=${this.t('interface_editor.redo')} title="⇧⌘Z" ?disabled=${!this.canRedo} @click=${() => this.emit('editor-redo')}><platform-icon name="redo" size="16"></platform-icon></platform-button>
            </div>
            <platform-segmented-control density="compact" icon-only .value=${this.viewport} .items=${this._viewportItems()} aria-label=${this.t('interface_editor.viewport')}
                @change=${(event) => this.emit('editor-viewport', { viewport: event.detail.value })}></platform-segmented-control>
            <platform-button ?accent=${this.preview} ?secondary=${!this.preview} density="compact" @click=${() => this.emit('editor-preview', { preview: !this.preview })}>
                <platform-icon name=${this.preview ? 'edit' : 'play'} size="14"></platform-icon>${this.t(this.preview ? 'interface_editor.back_to_editing' : 'interface_editor.test')}
            </platform-button>
            <span class="spacer"></span>
            <span class="status" data-dirty=${this.dirty ? 'true' : 'false'} data-errors=${this.problemCount > 0 ? 'true' : 'false'}>
                <platform-icon name=${this.problemCount > 0 ? 'notification-error' : (this.dirty ? 'fiber-manual-record' : 'done-all')} size="13"></platform-icon>
                ${this.t(statusKey, { count: this.problemCount })}
            </span>
            <platform-button secondary density="compact" @click=${() => this.emit('editor-templates')}><platform-icon name="layers" size="14"></platform-icon>${this.t('interface_editor.templates')}</platform-button>
            <platform-button class="assist-trigger" secondary density="compact" ?loading=${this.assistBusy} @click=${() => { this._assistOpen = !this._assistOpen; }}>
                <platform-icon name="sparkle" size="14"></platform-icon>${this.t('interface_editor.assist')}
            </platform-button>
            ${this._renderAssist()}
            <platform-button primary density="compact" ?disabled=${!this.dirty} @click=${() => this.emit('editor-publish')}>${this.t('interface_editor.publish')}</platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-toolbar')) customElements.define('flows-interface-toolbar', FlowsInterfaceToolbar);

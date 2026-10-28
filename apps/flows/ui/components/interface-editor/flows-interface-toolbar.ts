/**
 * Контекстные инструменты Interface в единой chrome-bar: Undo/Redo, viewport,
 * предпросмотр холста, шаблоны и AI-помощник страницы.
 *
 * Publish, статус и Lara здесь не живут — они общие в ``flows-editor-header``.
 *
 * События: ``editor-undo``, ``editor-redo``, ``editor-viewport {viewport}``,
 * ``editor-preview {preview}``, ``editor-templates``, ``editor-assist {instruction, scope}``.
 */

import { css, html } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsInterfaceToolbar extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        canUndo: { type: Boolean },
        canRedo: { type: Boolean },
        viewport: { type: String },
        preview: { type: Boolean },
        hasSelection: { type: Boolean },
        assistBusy: { type: Boolean },
        _assistOpen: { state: true },
        _instruction: { state: true },
    }
    declare canUndo: boolean;
    declare canRedo: boolean;
    declare viewport: string;
    declare preview: boolean;
    declare hasSelection: boolean;
    declare assistBusy: boolean;
    declare _assistOpen: boolean;
    declare _instruction: string;
;

    static override styles: CSSResultGroup = [PlatformElement.styles, css`
        :host {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            min-width: 0;
            padding: 0;
            background: transparent;
            border: none;
        }
        .group { display: inline-flex; align-items: center; gap: 2px; }
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

    _submitAssist(scope: any) {
        const instruction = (this._instruction.trim() as any);
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
                    @change=${(event: CustomEvent) => { this._instruction = event.detail.value; }}></platform-field>
                <div class="assist-hint">${this.t('interface_editor.assist_hint')}</div>
                <div class="assist-actions">
                    <platform-button secondary density="compact" ?disabled=${!this.hasSelection || this.assistBusy} @click=${() => this._submitAssist('block')}>${this.t('interface_editor.assist_block')}</platform-button>
                    <platform-button primary density="compact" ?disabled=${this.assistBusy} @click=${() => this._submitAssist('page')}>${this.t('interface_editor.assist_page')}</platform-button>
                </div>
            </div>
        </platform-popover>`;
    }

    override render(): TemplateResult {
        const previewLabel = this.t(this.preview ? 'interface_editor.back_to_editing' : 'interface_editor.preview');
        return html`
            <div class="group">
                <platform-button variant="ghost" icon-only density="dense" aria-label=${this.t('interface_editor.undo')} title="⌘Z" ?disabled=${!this.canUndo} @click=${() => this.emit('editor-undo')}><platform-icon name="undo" size="16"></platform-icon></platform-button>
                <platform-button variant="ghost" icon-only density="dense" aria-label=${this.t('interface_editor.redo')} title="⇧⌘Z" ?disabled=${!this.canRedo} @click=${() => this.emit('editor-redo')}><platform-icon name="redo" size="16"></platform-icon></platform-button>
            </div>
            <platform-segmented-control density="dense" icon-only .value=${this.viewport} .items=${this._viewportItems()} aria-label=${this.t('interface_editor.viewport')}
                @change=${(event: CustomEvent) => this.emit('editor-viewport', { viewport: event.detail.value })}></platform-segmented-control>
            <platform-button variant="ghost" density="dense" ?accent=${this.preview} aria-label=${previewLabel} title=${previewLabel} @click=${() => this.emit('editor-preview', { preview: !this.preview })}>
                <platform-icon name=${this.preview ? 'edit' : 'play'} size="14"></platform-icon>${previewLabel}
            </platform-button>
            <platform-button variant="ghost" icon-only density="dense" aria-label=${this.t('interface_editor.templates')} title=${this.t('interface_editor.templates')} @click=${() => this.emit('editor-templates')}>
                <platform-icon name="layers" size="14"></platform-icon>
            </platform-button>
            <platform-button class="assist-trigger" variant="ghost" icon-only density="dense" ?loading=${this.assistBusy} aria-label=${this.t('interface_editor.assist')} title=${this.t('interface_editor.assist')} @click=${() => { this._assistOpen = !this._assistOpen; }}>
                <platform-icon name="sparkle" size="14"></platform-icon>
            </platform-button>
            ${this._renderAssist()}
        `;
    }
}

if (!customElements.get('flows-interface-toolbar')) customElements.define('flows-interface-toolbar', FlowsInterfaceToolbar);

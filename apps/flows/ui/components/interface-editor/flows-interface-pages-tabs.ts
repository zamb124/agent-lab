/**
 * Вкладки страниц документа Flow UI: переключение, добавление, переименование (двойной клик),
 * стартовая страница и удаление через меню вкладки.
 *
 * События: ``page-select {pageId}``, ``page-command {command: 'add'|'remove'|'start'|'set', pageId, property, value}``.
 */

import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-button.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class FlowsInterfacePagesTabs extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        document: { attribute: false },
        pageId: { type: String },
        _menuPageId: { state: true },
        _renamePageId: { state: true },
    }
    declare document: any;
    declare pageId: string;
    declare _menuPageId: string;
    declare _renamePageId: string;
;

    static override styles: CSSResultGroup = [PlatformElement.styles, css`
        :host { display: flex; align-items: center; gap: 4px; padding: 6px 12px 0; border-bottom: 1px solid var(--border-subtle); background: var(--glass-solid-medium); overflow-x: auto; min-width: 0; }
        .tab { display: inline-flex; align-items: center; gap: 6px; padding: 7px 10px; border: 0; border-radius: 8px 8px 0 0; background: transparent; color: var(--text-secondary); font: inherit; font-size: 12.5px; cursor: pointer; white-space: nowrap; }
        .tab[aria-selected='true'] { color: var(--text-primary); background: var(--bg-primary); box-shadow: inset 0 -2px var(--accent); }
        .tab .start { color: var(--accent); }
        .tab .kebab { color: var(--text-tertiary); opacity: 0; }
        .tab:hover .kebab, .tab[aria-selected='true'] .kebab { opacity: 1; }
        .tab input { font: inherit; font-size: 12.5px; border: 0; outline: none; background: transparent; color: var(--text-primary); width: 14ch; padding: 0; border-bottom: 1px solid var(--accent); }
        .add { color: var(--text-tertiary); }
    `];

    constructor() {
        super();
        this.document = null;
        this.pageId = '';
        this._menuPageId = '';
        this._renamePageId = '';
    }

    _command(command: any, pageId: any, property: any = null, value: any = null) {
        this._menuPageId = '';
        this.emit('page-command', { command, pageId, property, value });
    }

    _menuItems(page: any) {
        return [
            { id: 'rename', label: this.t('interface_editor.page_rename'), icon: 'edit' },
            { id: 'show_title', label: this.t(page.show_title === false ? 'interface_editor.page_show_title' : 'interface_editor.page_hide_title'), icon: 'eye' },
            { id: 'start', label: this.t('interface_editor.page_make_start'), icon: 'star', disabled: (this.document.start_page_id as any) === page.page_id },
            { id: 'remove', label: this.t('interface_editor.page_remove'), icon: 'trash', danger: true, disabled: (this.document.pages.length as any) === 1 },
        ];
    }

    _onMenuSelect(page: any, id: string) {
        if (id === 'rename') {
            this._menuPageId = '';
            this._renamePageId = page.page_id;
            this.updateComplete.then(() => { const field = this.renderRoot.querySelector('.tab input'); if (field) { (field as Record<string, any>).focus(); (field as Record<string, any>).select(); } });
            return;
        }
        if (id === 'show_title') {
            this._command('set', page.page_id, 'show_title', page.show_title === false);
            return;
        }
        this._command(id, page.page_id);
    }

    _finishRename(page: any, commit: any) {
        const field = this.renderRoot.querySelector('.tab input');
        const value = field === null ? page.title : (field as Record<string, any>).value.trim();
        this._renamePageId = '';
        if (commit && value !== page.title) this._command('set', page.page_id, 'title', value);
    }

    _renderTab(page: any) {
        const selected = page.page_id === this.pageId;
        const renaming = page.page_id === this._renamePageId;
        return html`<div class="tab" role="tab" aria-selected=${selected ? 'true' : 'false'} tabindex="0"
            @click=${() => { if (!selected) this.emit('page-select', { pageId: page.page_id }); }}
            @dblclick=${() => this._onMenuSelect(page, 'rename')}
            @keydown=${(event: CustomEvent) => { if (!renaming && ((event as Record<string, any>).key === 'Enter' || (event as Record<string, any>).key === ' ')) { event.preventDefault(); this.emit('page-select', { pageId: page.page_id }); } }}>
            ${(this.document.start_page_id as any) === page.page_id ? html`<platform-icon class="start" name="star" size="11" title=${this.t('interface_editor.page_start')}></platform-icon>` : nothing}
            ${renaming
                ? html`<input type="text" data-canon="inline-edit" .value=${page.title} aria-label=${this.t('interface_editor.page_title')}
                    @blur=${() => this._finishRename(page, true)}
                    @keydown=${(event: CustomEvent) => { if ((event as Record<string, any>).key === 'Enter') { event.preventDefault(); this._finishRename(page, true); } if ((event as Record<string, any>).key === 'Escape') { event.preventDefault(); this._finishRename(page, false); } }} />`
                : html`<span>${page.title === '' ? page.page_id : page.title}</span>`}
            <platform-button ghost density="dense" icon-only class="kebab" data-page-id=${page.page_id} aria-label=${this.t('interface_editor.page_menu')}
                @click=${(event: CustomEvent) => { event.stopPropagation(); this._menuPageId = this._menuPageId === page.page_id ? '' : page.page_id; }}>
                <platform-icon name="more-vert" size="12"></platform-icon>
            </platform-button>
            <platform-popover trigger="manual" .anchor=${this.renderRoot.querySelector(`.kebab[data-page-id="${page.page_id}"]`)} ?open=${this._menuPageId === page.page_id} role="menu" dismiss-on-outside
                @popover-dismiss=${() => { this._menuPageId = ''; }}>
                <platform-menu compact .items=${this._menuItems(page)} @menu-select=${(event: CustomEvent) => this._onMenuSelect(page, event.detail.id)}></platform-menu>
            </platform-popover>
        </div>`;
    }

    override render(): TemplateResult | typeof nothing {
        if (this.document === null) return nothing;
        return html`
            <div role="tablist" style="display: contents">${(this.document as Record<string, any>).pages.map((page: any) => this._renderTab(page))}</div>
            <platform-button ghost density="dense" icon-only class="add" aria-label=${this.t('interface_editor.page_add')} @click=${() => this._command('add', null)}>
                <platform-icon name="plus" size="14"></platform-icon>
            </platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-pages-tabs')) customElements.define('flows-interface-pages-tabs', FlowsInterfacePagesTabs);

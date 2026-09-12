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

export class FlowsInterfacePagesTabs extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        document: { attribute: false },
        pageId: { type: String },
        _menuPageId: { state: true },
        _renamePageId: { state: true },
    };

    static styles = [PlatformElement.styles, css`
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

    _command(command, pageId, property = null, value = null) {
        this._menuPageId = '';
        this.emit('page-command', { command, pageId, property, value });
    }

    _menuItems(page) {
        return [
            { id: 'rename', label: this.t('interface_editor.page_rename'), icon: 'edit' },
            { id: 'show_title', label: this.t(page.show_title === false ? 'interface_editor.page_show_title' : 'interface_editor.page_hide_title'), icon: 'eye' },
            { id: 'start', label: this.t('interface_editor.page_make_start'), icon: 'star', disabled: this.document.start_page_id === page.page_id },
            { id: 'remove', label: this.t('interface_editor.page_remove'), icon: 'trash', danger: true, disabled: this.document.pages.length === 1 },
        ];
    }

    _onMenuSelect(page, id) {
        if (id === 'rename') {
            this._menuPageId = '';
            this._renamePageId = page.page_id;
            this.updateComplete.then(() => { const field = this.renderRoot.querySelector('.tab input'); if (field) { field.focus(); field.select(); } });
            return;
        }
        if (id === 'show_title') {
            this._command('set', page.page_id, 'show_title', page.show_title === false);
            return;
        }
        this._command(id, page.page_id);
    }

    _finishRename(page, commit) {
        const field = this.renderRoot.querySelector('.tab input');
        const value = field === null ? page.title : field.value.trim();
        this._renamePageId = '';
        if (commit && value !== page.title) this._command('set', page.page_id, 'title', value);
    }

    _renderTab(page) {
        const selected = page.page_id === this.pageId;
        const renaming = page.page_id === this._renamePageId;
        return html`<div class="tab" role="tab" aria-selected=${selected ? 'true' : 'false'} tabindex="0"
            @click=${() => { if (!selected) this.emit('page-select', { pageId: page.page_id }); }}
            @dblclick=${() => this._onMenuSelect(page, 'rename')}
            @keydown=${(event) => { if (!renaming && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); this.emit('page-select', { pageId: page.page_id }); } }}>
            ${this.document.start_page_id === page.page_id ? html`<platform-icon class="start" name="star" size="11" title=${this.t('interface_editor.page_start')}></platform-icon>` : nothing}
            ${renaming
                ? html`<input type="text" data-canon="inline-edit" .value=${page.title} aria-label=${this.t('interface_editor.page_title')}
                    @blur=${() => this._finishRename(page, true)}
                    @keydown=${(event) => { if (event.key === 'Enter') { event.preventDefault(); this._finishRename(page, true); } if (event.key === 'Escape') { event.preventDefault(); this._finishRename(page, false); } }} />`
                : html`<span>${page.title === '' ? page.page_id : page.title}</span>`}
            <platform-button ghost density="dense" icon-only class="kebab" data-page-id=${page.page_id} aria-label=${this.t('interface_editor.page_menu')}
                @click=${(event) => { event.stopPropagation(); this._menuPageId = this._menuPageId === page.page_id ? '' : page.page_id; }}>
                <platform-icon name="more-vert" size="12"></platform-icon>
            </platform-button>
            <platform-popover trigger="manual" .anchor=${this.renderRoot.querySelector(`.kebab[data-page-id="${page.page_id}"]`)} ?open=${this._menuPageId === page.page_id} role="menu" dismiss-on-outside
                @popover-dismiss=${() => { this._menuPageId = ''; }}>
                <platform-menu compact .items=${this._menuItems(page)} @menu-select=${(event) => this._onMenuSelect(page, event.detail.id)}></platform-menu>
            </platform-popover>
        </div>`;
    }

    render() {
        if (this.document === null) return nothing;
        return html`
            <div role="tablist" style="display: contents">${this.document.pages.map((page) => this._renderTab(page))}</div>
            <platform-button ghost density="dense" icon-only class="add" aria-label=${this.t('interface_editor.page_add')} @click=${() => this._command('add', null)}>
                <platform-icon name="plus" size="14"></platform-icon>
            </platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-pages-tabs')) customElements.define('flows-interface-pages-tabs', FlowsInterfacePagesTabs);

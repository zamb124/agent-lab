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
import type { FlowUiDocument, FlowUiPage } from '../../_helpers/interface-editor-domain.js';

function tabInput(root: ParentNode): HTMLInputElement | null {
    const field = root.querySelector('.tab input');
    if (field === null) {
        return null;
    }
    if (!(field instanceof HTMLInputElement)) {
        throw new Error('flows-interface-pages-tabs: rename field must be an input');
    }
    return field;
}

export class FlowsInterfacePagesTabs extends PlatformElement {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        document: { attribute: false },
        pageId: { type: String },
        _menuPageId: { state: true },
        _renamePageId: { state: true },
    }
    declare document: FlowUiDocument | null;
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

    _requireDocument(): FlowUiDocument {
        if (this.document === null) {
            throw new Error('flows-interface-pages-tabs: document required');
        }
        return this.document;
    }

    _command(command: string, pageId: string | null, property: string | null = null, value: unknown = null) {
        this._menuPageId = '';
        this.emit('page-command', { command, pageId, property, value });
    }

    _menuItems(page: FlowUiPage) {
        const document = this._requireDocument();
        return [
            { id: 'rename', label: this.t('interface_editor.page_rename'), icon: 'edit' },
            { id: 'show_title', label: this.t(page.show_title === false ? 'interface_editor.page_show_title' : 'interface_editor.page_hide_title'), icon: 'eye' },
            { id: 'start', label: this.t('interface_editor.page_make_start'), icon: 'star', disabled: document.start_page_id === page.page_id },
            { id: 'remove', label: this.t('interface_editor.page_remove'), icon: 'trash', danger: true, disabled: document.pages.length === 1 },
        ];
    }

    _onMenuSelect(page: FlowUiPage, id: string) {
        if (id === 'rename') {
            this._menuPageId = '';
            this._renamePageId = page.page_id;
            this.updateComplete.then(() => {
                const field = tabInput(this.renderRoot);
                if (field === null) {
                    return;
                }
                field.focus();
                field.select();
            });
            return;
        }
        if (id === 'show_title') {
            this._command('set', page.page_id, 'show_title', page.show_title === false);
            return;
        }
        this._command(id, page.page_id);
    }

    _finishRename(page: FlowUiPage, commit: boolean) {
        const field = tabInput(this.renderRoot);
        const title = typeof page.title === 'string' ? page.title : '';
        const value = field === null ? title : field.value.trim();
        this._renamePageId = '';
        if (commit && value !== title) this._command('set', page.page_id, 'title', value);
    }

    _renderTab(page: FlowUiPage) {
        const document = this._requireDocument();
        const selected = page.page_id === this.pageId;
        const renaming = page.page_id === this._renamePageId;
        const title = typeof page.title === 'string' ? page.title : '';
        return html`<div class="tab" role="tab" aria-selected=${selected ? 'true' : 'false'} tabindex="0"
            @click=${() => { if (!selected) this.emit('page-select', { pageId: page.page_id }); }}
            @dblclick=${() => this._onMenuSelect(page, 'rename')}
            @keydown=${(event: Event) => {
                if (!(event instanceof KeyboardEvent) || renaming) return;
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    this.emit('page-select', { pageId: page.page_id });
                }
            }}>
            ${document.start_page_id === page.page_id ? html`<platform-icon class="start" name="star" size="11" title=${this.t('interface_editor.page_start')}></platform-icon>` : nothing}
            ${renaming
                ? html`<input type="text" data-canon="inline-edit" .value=${title} aria-label=${this.t('interface_editor.page_title')}
                    @blur=${() => this._finishRename(page, true)}
                    @keydown=${(event: Event) => {
                        if (!(event instanceof KeyboardEvent)) return;
                        if (event.key === 'Enter') {
                            event.preventDefault();
                            this._finishRename(page, true);
                        }
                        if (event.key === 'Escape') {
                            event.preventDefault();
                            this._finishRename(page, false);
                        }
                    }} />`
                : html`<span>${title === '' ? page.page_id : title}</span>`}
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
        const document = this.document;
        return html`
            <div role="tablist" style="display: contents">${document.pages.map((page) => this._renderTab(page))}</div>
            <platform-button ghost density="dense" icon-only class="add" aria-label=${this.t('interface_editor.page_add')} @click=${() => this._command('add', null)}>
                <platform-icon name="plus" size="14"></platform-icon>
            </platform-button>
        `;
    }
}

if (!customElements.get('flows-interface-pages-tabs')) customElements.define('flows-interface-pages-tabs', FlowsInterfacePagesTabs);

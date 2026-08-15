/**
 * office-catalog-context-menu — контекстное меню каталога в explorer tree.
 *
 * Пункты и клавиатура — платформенный `platform-menu`, слой — `platform-popover`
 * с якорем по координатам курсора, поэтому меню не обрезается деревом и не
 * уезжает за край экрана.
 *
 * Шлёт DOM-событие `ctx-action` с detail = { action, catalog }.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-menu.js';
import '@platform/lib/components/platform-popover.js';

export class OfficeCatalogContextMenu extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        x: { type: Number },
        y: { type: Number },
        catalog: { type: Object, attribute: false },
        hasChildCatalogs: { type: Boolean, attribute: 'has-child-catalogs' },
        visible: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: contents;
            }
        `,
    ];

    constructor() {
        super();
        this.x = 0;
        this.y = 0;
        this.catalog = null;
        this.hasChildCatalogs = false;
        this.visible = false;
    }

    _onSelect(event) {
        if (!this.catalog || typeof this.catalog !== 'object') {
            return;
        }
        this.emit('ctx-action', { action: event.detail.id, catalog: this.catalog });
    }

    _canDelete() {
        const catalog = this.catalog;
        if (!catalog || catalog.is_owner !== true) {
            return false;
        }
        const fileCount = typeof catalog.file_count === 'number' ? catalog.file_count : 0;
        return fileCount === 0 && this.hasChildCatalogs !== true;
    }

    _items() {
        const catalog = this.catalog;
        if (!catalog || typeof catalog !== 'object' || catalog.is_owner !== true) {
            return [];
        }
        const items = [
            { id: 'edit', label: this.t('catalog_context_menu.edit'), icon: 'edit' },
            { id: 'access', label: this.t('catalog_context_menu.access'), icon: 'link' },
        ];
        if (catalog.company_visible !== true) {
            items.push({ id: 'members', label: this.t('catalog_context_menu.members'), icon: 'users' });
        }
        items.push(
            { id: 'rag', label: this.t('catalog_context_menu.rag'), icon: 'search' },
            { id: 'sep', kind: 'separator' },
            {
                id: 'delete',
                label: this.t('catalog_context_menu.delete'),
                icon: 'trash',
                danger: true,
                disabled: !this._canDelete(),
            },
        );
        return items;
    }

    render() {
        const items = this._items();
        return html`
            <platform-popover
                trigger="manual"
                role="menu"
                placement="bottom-start"
                offset="2"
                .anchor=${{ x: this.x, y: this.y }}
                ?open=${this.visible && items.length > 0}
                @popover-dismiss=${() => this.emit('ctx-dismiss')}
            >
                <platform-menu compact .items=${items} @menu-select=${this._onSelect}></platform-menu>
            </platform-popover>
        `;
    }
}

customElements.define('office-catalog-context-menu', OfficeCatalogContextMenu);

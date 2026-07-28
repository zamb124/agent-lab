/**
 * Дерево страниц на узком экране.
 *
 * kind: 'wiki.tree'
 *
 * Перетаскивание здесь выключено: на телефоне оно конфликтует с прокруткой
 * списка, а перемещать страницы удобнее через контекстное меню.
 */

import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import '@platform/lib/components/platform-tree.js';

export class WikiTreeSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'wiki.tree';
    static i18nNamespace = 'wiki';

    static properties = {
        ...PlatformBottomSheet.properties,
        activePageId: { type: String, attribute: 'active-page-id' },
    };

    static styles = [
        PlatformBottomSheet.styles,
        css`
            platform-tree {
                display: block;
                width: 100%;
            }

            .empty {
                padding: var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.activePageId = '';
        this.snap = 'full';
        this._pages = this.useResource('wiki/pages');
        this._treeMenuItems = this._treeMenuItems.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('sidebar.pages');
    }

    _nodes() {
        return this._pages.items.map((page) => ({
            id: page.wiki_page_id,
            parent_id: page.parent_page_id,
            label: page.title === '' ? this.t('page.untitled') : page.title,
            emoji: page.icon === '' ? undefined : page.icon,
            icon: 'file',
            has_children: page.has_children,
        }));
    }

    _treeMenuItems() {
        return [
            { id: 'open', label: this.t('tree_menu.open'), icon: 'external-link' },
            { id: 'move', label: this.t('tree_menu.move'), icon: 'swap-horiz' },
            { id: 'access', label: this.t('tree_menu.access'), icon: 'lock' },
        ];
    }

    _onSelect(event) {
        this.navigate('wiki_page', { pageId: event.detail.id });
        this.close();
    }

    _onAction(event) {
        const { action, id } = event.detail;
        if (action === 'open') {
            this.navigate('wiki_page', { pageId: id });
            this.close();
            return;
        }
        if (action === 'move') {
            this.close();
            this.openModal('wiki.move_page', { pageId: id });
            return;
        }
        if (action === 'access') {
            this.close();
            this.openModal('wiki.page_access', { pageId: id });
            return;
        }
        throw new Error(`wiki-tree-sheet: неизвестное действие ${action}`);
    }

    renderBody() {
        const nodes = this._nodes();
        if (nodes.length === 0) {
            return html`<div class="empty">${this.t('sidebar.empty')}</div>`;
        }
        return html`
            <platform-tree
                .nodes=${nodes}
                selected-id=${this.activePageId}
                aria-label=${this.t('sidebar.pages')}
                .menuItems=${this._treeMenuItems}
                @tree-select=${this._onSelect}
                @tree-action=${this._onAction}
            ></platform-tree>
        `;
    }
}

customElements.define('wiki-tree-sheet', WikiTreeSheet);
registerBottomSheetKind(WikiTreeSheet.bottomSheetKind, 'wiki-tree-sheet');

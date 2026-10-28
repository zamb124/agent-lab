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
import type { ResourceController } from '@platform/lib/base/use-resource.js';
import type { ResourceItem } from '@platform/lib/events/factories/resource-collection.js';

interface WikiTreeNode {
    id: unknown;
    parent_id: unknown;
    label: unknown;
    emoji: unknown;
    icon: string;
    has_children: unknown;
}

interface WikiTreeMenuItem {
    id: string;
    label: string;
    icon: string;
}
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import '@platform/lib/components/platform-tree.js';

function missingAsEmpty(value: unknown): string {
    if (value === undefined || value === null) return '';
    return String(value);
}


export class WikiTreeSheet extends PlatformBottomSheet {
    static bottomSheetKind = 'wiki.tree';
    static i18nNamespace = 'wiki';

    declare activePageId: string;
    private _pages: ResourceController;

    static override properties = {
        ...PlatformBottomSheet.properties,
        activePageId: { type: String, attribute: 'active-page-id' },
    };

    static override styles = [
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

    override connectedCallback() {
        super.connectedCallback();
        this.heading = this.t('sidebar.pages');
    }

    private _nodes(): WikiTreeNode[] {
        return this._pages.items.map((page: ResourceItem) => ({
            id: page.wiki_page_id,
            parent_id: page.parent_page_id,
            label: page.title === '' ? this.t('page.untitled') : page.title,
            emoji: page.icon === '' ? undefined : page.icon,
            icon: 'file',
            has_children: page.has_children,
        }));
    }

    private _treeMenuItems(): WikiTreeMenuItem[] {
        return [
            { id: 'open', label: this.t('tree_menu.open'), icon: 'external-link' },
            { id: 'move', label: this.t('tree_menu.move'), icon: 'swap-horiz' },
            { id: 'access', label: this.t('tree_menu.access'), icon: 'lock' },
        ];
    }

    private _onSelect(event: CustomEvent<{ id?: unknown }>) {
        this.navigate('wiki_page', { pageId: missingAsEmpty(event.detail.id) });
        this._requestClose();
    }

    private _onAction(event: CustomEvent<{ action?: string; id?: unknown }>) {
        const { action, id } = event.detail;
        const pageId = missingAsEmpty(id);
        if (action === 'open') {
            this.navigate('wiki_page', { pageId });
            this._requestClose();
            return;
        }
        if (action === 'move') {
            this._requestClose();
            this.openModal('wiki.move_page', { pageId });
            return;
        }
        if (action === 'access') {
            this._requestClose();
            this.openModal('wiki.page_access', { pageId });
            return;
        }
        throw new Error(`wiki-tree-sheet: неизвестное действие ${action}`);
    }

    override renderBody() {
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
                @tree-select=${(event: CustomEvent<{ id?: unknown }>) => this._onSelect(event)}
                @tree-action=${(event: CustomEvent<{ action?: string; id?: unknown }>) => this._onAction(event)}
            ></platform-tree>
        `;
    }
}

customElements.define('wiki-tree-sheet', WikiTreeSheet);
registerBottomSheetKind(WikiTreeSheet.bottomSheetKind, 'wiki-tree-sheet');

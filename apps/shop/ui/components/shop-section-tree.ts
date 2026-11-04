/**
 * shop-section-tree — дерево разделов меню поверх core `<platform-tree>`.
 *
 * Строка «Все позиции» снимает фильтр; меню строки — подраздел,
 * переименование, удаление; перетаскивание меняет порядок и вложенность.
 * Компонент не ходит в сеть: намерения уходят событиями
 *   section-select  { id: string | null }
 *   section-create  { parentId: string | null, name }
 *   section-rename  { id, name }
 *   section-remove  { id }
 *   section-reorder { items: ShopMenuSectionReorderItem[] } — все разделы меню
 *                   в порядке обхода в глубину (контракт `shop/menu_sections_reorder`).
 */

import { html, css } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { PlatformTreeNode } from '@platform/lib/components/platform-tree.js';
import type { PlatformMenuItem } from '@platform/lib/components/platform-menu.js';
import type { ShopMenuSection, ShopMenuSectionReorderItem } from '@platform/lib/events/wire/shop.gen.js';
import { platformConfirm, platformPrompt } from '@platform/lib/components/platform-confirm-modal.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-tree.js';

interface TreeMoveDetail {
    id: string;
    target_id: string;
    position: string;
    parent_id: string | null;
}

function sectionParent(section: ShopMenuSection): string | null {
    return section.parent_id === undefined ? null : section.parent_id;
}

/** Новый порядок после перетаскивания: дети каждого родителя в порядке `sections`. */
function reorderedItems(sections: readonly ShopMenuSection[], move: TreeMoveDetail): ShopMenuSectionReorderItem[] {
    const children = new Map<string | null, string[]>();
    const childrenOf = (parentId: string | null): string[] => {
        const list = children.get(parentId);
        if (list !== undefined) return list;
        const created: string[] = [];
        children.set(parentId, created);
        return created;
    };
    for (const section of sections) {
        if (section.shop_menu_section_id !== move.id) {
            childrenOf(sectionParent(section)).push(section.shop_menu_section_id);
        }
    }
    const siblings = childrenOf(move.parent_id);
    if (move.position === 'inside') {
        siblings.push(move.id);
    } else {
        const targetIndex = siblings.indexOf(move.target_id);
        if (targetIndex < 0) {
            throw new Error('shop-section-tree: drop target missing among siblings');
        }
        siblings.splice(move.position === 'before' ? targetIndex : targetIndex + 1, 0, move.id);
    }
    const items: ShopMenuSectionReorderItem[] = [];
    const walk = (parentId: string | null): void => {
        for (const id of childrenOf(parentId)) {
            items.push({ shop_menu_section_id: id, parent_id: parentId });
            walk(id);
        }
    };
    walk(null);
    if (items.length !== sections.length) {
        throw new Error('shop-section-tree: reorder lost sections');
    }
    return items;
}

function isTreeMoveDetail(value: unknown): value is TreeMoveDetail {
    if (value === null || typeof value !== 'object') return false;
    const detail = value as Record<string, unknown>;
    return typeof detail.id === 'string'
        && typeof detail.target_id === 'string'
        && typeof detail.position === 'string'
        && (detail.parent_id === null || typeof detail.parent_id === 'string');
}

export class ShopSectionTree extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        sections: { attribute: false },
        counts: { attribute: false },
        allCount: { type: Number, attribute: 'all-count' },
        selectedId: { attribute: false },
    };
    declare sections: ShopMenuSection[];
    declare counts: Record<string, number>;
    declare allCount: number;
    declare selectedId: string | null;

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: flex; flex-direction: column; gap: var(--space-1); min-width: 0; }
            .all {
                display: flex; align-items: center; gap: var(--space-2);
                min-height: 30px; padding: 0 var(--space-2);
                border: none; border-radius: var(--radius-sm); background: transparent;
                color: var(--text-secondary); font: inherit; font-size: var(--text-sm);
                cursor: pointer; text-align: left;
            }
            .all:hover { background: var(--glass-tint-subtle); color: var(--text-primary); }
            .all.on { background: var(--glass-tint-medium); color: var(--text-primary); font-weight: var(--font-medium); }
            .all .count { margin-left: auto; color: var(--text-tertiary); font-size: var(--text-xs); font-variant-numeric: tabular-nums; }
            .add { margin-top: var(--space-2); }
        `,
    ];

    constructor() {
        super();
        this.sections = [];
        this.counts = {};
        this.allCount = 0;
        this.selectedId = null;
    }

    private _nodes(): PlatformTreeNode[] {
        return this.sections.map((section) => {
            const node: PlatformTreeNode = {
                id: section.shop_menu_section_id,
                label: section.name,
                parent_id: sectionParent(section),
                icon: 'folder',
            };
            const count = this.counts[section.shop_menu_section_id];
            if (count !== undefined) node.count = count;
            return node;
        });
    }

    private _menuItems(): PlatformMenuItem[] {
        return [
            { id: 'add_child', label: this.t('menu_editor.section_add_child'), icon: 'plus' },
            { id: 'rename', label: this.t('menu_editor.section_rename'), icon: 'edit' },
            { id: 'remove', label: this.t('menu_editor.section_remove'), icon: 'trash', danger: true },
        ];
    }

    private async _promptName(title: string, value: string): Promise<string | null> {
        const name = await platformPrompt(this.t('menu_editor.section_name_message'), {
            title,
            inputLabel: this.t('menu_editor.section_name'),
            inputValue: value,
            confirmText: this.t('menus.save'),
        });
        if (name === undefined || name.trim() === '') return null;
        return name.trim();
    }

    private async _create(parentId: string | null): Promise<void> {
        const name = await this._promptName(this.t('menu_editor.section_new'), '');
        if (name !== null) this.emit('section-create', { parentId, name });
    }

    private async _onAction(event: CustomEvent<{ action?: unknown; id?: unknown }>): Promise<void> {
        const { action, id } = event.detail;
        if (typeof id !== 'string') return;
        const section = this.sections.find((row) => row.shop_menu_section_id === id);
        if (section === undefined) return;
        if (action === 'add_child') {
            await this._create(id);
            return;
        }
        if (action === 'rename') {
            const name = await this._promptName(this.t('menu_editor.section_rename'), section.name);
            if (name !== null && name !== section.name) this.emit('section-rename', { id, name });
            return;
        }
        if (action === 'remove') {
            const confirmed = await platformConfirm(this.t('menu_editor.section_remove_confirm', { name: section.name }), {
                title: this.t('menu_editor.section_remove'),
                variant: 'warning',
                confirmText: this.t('menu_editor.section_remove'),
                cancelText: this.t('product.cancel'),
            });
            if (confirmed === true) this.emit('section-remove', { id });
        }
    }

    private _onMove(event: CustomEvent<unknown>): void {
        if (!isTreeMoveDetail(event.detail)) {
            throw new Error('shop-section-tree: invalid tree-move detail');
        }
        this.emit('section-reorder', { items: reorderedItems(this.sections, event.detail) });
    }

    override render(): TemplateResult {
        return html`
            <button type="button" class="all ${this.selectedId === null ? 'on' : ''}"
                @click=${() => this.emit('section-select', { id: null })}>
                <platform-icon name="list" size="14"></platform-icon>
                ${this.t('menu_editor.all_sections')}
                <span class="count">${this.allCount}</span>
            </button>
            <platform-tree
                .nodes=${this._nodes()}
                selected-id=${this.selectedId === null ? '' : this.selectedId}
                draggable-nodes
                aria-label=${this.t('menu_editor.sections')}
                empty-label=${this.t('menu_editor.sections_empty')}
                .menuItems=${() => this._menuItems()}
                @tree-select=${(event: CustomEvent<{ id?: unknown }>) => {
                    if (typeof event.detail.id === 'string') this.emit('section-select', { id: event.detail.id });
                }}
                @tree-action=${(event: CustomEvent<{ action?: unknown; id?: unknown }>) => this._onAction(event)}
                @tree-move=${(event: CustomEvent<unknown>) => this._onMove(event)}
            ></platform-tree>
            <platform-button class="add" size="sm" variant="ghost" @click=${() => this._create(null)}>
                <platform-icon name="plus" size="14"></platform-icon> ${this.t('menu_editor.section_add')}
            </platform-button>
        `;
    }
}

customElements.define('shop-section-tree', ShopSectionTree);

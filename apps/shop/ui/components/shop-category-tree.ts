/**
 * shop-category-tree — дерево категорий меню магазина: раскрытие веток,
 * inline-создание и переименование, drag&drop порядка и вложенности,
 * приём перетаскиваемых товаров из списка.
 *
 * Изменения дерева уходят событием `tree-change` с полным depth-first
 * списком `items` — sort внутри siblings назначает сервер.
 */

import { html, css, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

export interface ShopTreeCategory {
    shop_category_id: string;
    parent_id: string | null;
    name: string;
    sort: number;
    is_active: boolean;
}

export interface ShopTreeReorderItem {
    category_id: string;
    parent_id: string | null;
}

const CATEGORY_MIME = 'application/x-shop-category-id';
const PRODUCT_MIME = 'application/x-shop-product-id';
const ALL_ROW = '__all__';
const ROOT_CREATE = '__root__';

type DropZone = 'before' | 'after' | 'nest';

interface DropHint {
    id: string;
    zone: DropZone;
}

export class ShopCategoryTree extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        categories: { attribute: false },
        counts: { attribute: false },
        allCount: { attribute: false },
        activeId: { attribute: false },
        expandedIds: { attribute: false },
        _draggingId: { state: true },
        _dropHint: { state: true },
        _creatingUnder: { state: true },
        _editingId: { state: true },
        _editValue: { state: true },
    };

    declare categories: ShopTreeCategory[];
    declare counts: Record<string, number>;
    declare allCount: number;
    declare activeId: string | null;
    declare expandedIds: string[];
    declare _draggingId: string;
    declare _dropHint: DropHint | null;
    /** id родителя, под которым открыта inline-строка создания; ROOT_CREATE — корень. */
    declare _creatingUnder: string;
    declare _editingId: string;
    declare _editValue: string;

    constructor() {
        super();
        this.categories = [];
        this.counts = {};
        this.allCount = 0;
        this.activeId = null;
        this.expandedIds = [];
        this._draggingId = '';
        this._dropHint = null;
        this._creatingUnder = '';
        this._editingId = '';
        this._editValue = '';
    }

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; min-width: 0; }

            .head {
                display: flex; align-items: center; justify-content: space-between;
                padding: var(--space-2) var(--space-2) var(--space-1);
            }
            .head-title {
                font-size: var(--text-xs); font-weight: var(--font-semibold);
                color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em;
            }

            .row {
                display: flex; align-items: center; gap: 2px;
            }
            .toggle {
                display: inline-flex; align-items: center; justify-content: center;
                width: 18px; height: 26px; border: 0; background: transparent;
                color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; padding: 0;
            }
            .toggle:disabled { visibility: hidden; }
            .toggle platform-icon { transition: transform 0.15s ease; }
            .toggle.expanded platform-icon { transform: rotate(90deg); }

            .treeitem {
                display: flex; align-items: center; gap: var(--space-1);
                flex: 1; min-width: 0; height: 34px;
                padding: 0 var(--space-2) 0 var(--space-1);
                border: 1px solid transparent; border-radius: var(--radius-md);
                background: transparent; color: var(--text-secondary);
                font-size: var(--text-sm); transition: background 0.12s ease, border-color 0.12s ease;
            }
            .treeitem:hover { background: color-mix(in srgb, var(--text-primary) 5%, transparent); }
            .treeitem.off { opacity: 0.5; }
            .treeitem.active {
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent);
            }
            .treeitem.dragging { opacity: 0.4; }
            .treeitem.drop-nest { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }
            .treeitem.drop-before { box-shadow: inset 0 2px 0 0 var(--accent); }
            .treeitem.drop-after { box-shadow: inset 0 -2px 0 0 var(--accent); }

            .item-main {
                display: flex; align-items: center; gap: var(--space-1);
                flex: 1; min-width: 0; height: 100%;
                border: 0; background: transparent; padding: 0;
                color: inherit; font: inherit; text-align: left; cursor: pointer;
            }
            .grip { color: var(--text-tertiary); opacity: 0; flex-shrink: 0; cursor: grab; }
            .treeitem:hover .grip, .treeitem.dragging .grip { opacity: 1; }
            .item-label {
                flex: 1; min-width: 0; overflow: hidden;
                text-overflow: ellipsis; white-space: nowrap;
            }
            .treeitem.active .item-label { font-weight: var(--font-semibold); }
            .count {
                font-size: var(--text-xs); color: var(--text-tertiary);
                font-variant-numeric: tabular-nums; flex-shrink: 0;
            }
            .treeitem.active .count { color: var(--accent); }
            .row:hover .count, .row:focus-within .count { display: none; }
            .ops {
                display: none; align-items: center; flex-shrink: 0;
            }
            .treeitem:hover .ops, .treeitem:focus-within .ops { display: inline-flex; }
            .ops platform-button { --platform-button-padding: 3px; }

            .movebar {
                display: flex; align-items: center; gap: 2px;
                padding: 2px var(--space-2) 4px 22px;
            }
            .movebar platform-button { --platform-button-padding: 3px; }

            .edit-row {
                display: flex; align-items: end; gap: 2px;
                padding: 2px var(--space-2) 4px;
            }
            .edit-row platform-field { flex: 1; min-width: 0; }
            .edit-row platform-button { margin-bottom: 3px; }

            .empty {
                padding: var(--space-3) var(--space-2); color: var(--text-tertiary);
                font-size: var(--text-xs); line-height: 1.5;
            }
        `,
    ];

    private _childrenMap(): Map<string | null, ShopTreeCategory[]> {
        const ids = new Set(this.categories.map((c) => c.shop_category_id));
        const map = new Map<string | null, ShopTreeCategory[]>();
        for (const c of this.categories) {
            const parent = c.parent_id !== null && ids.has(c.parent_id) ? c.parent_id : null;
            const list = map.get(parent);
            if (list === undefined) map.set(parent, [c]);
            else list.push(c);
        }
        for (const list of map.values()) {
            list.sort((a, b) => a.sort - b.sort);
        }
        return map;
    }

    private _idChildrenMap(): Map<string | null, string[]> {
        const map = new Map<string | null, string[]>();
        for (const [parent, list] of this._childrenMap()) {
            map.set(parent, list.map((c) => c.shop_category_id));
        }
        return map;
    }

    private _descendantIds(id: string): Set<string> {
        const children = this._idChildrenMap();
        const out = new Set<string>();
        const queue = [...(children.get(id) ?? [])];
        while (queue.length > 0) {
            const next = queue.shift();
            if (next === undefined || out.has(next)) continue;
            out.add(next);
            queue.push(...(children.get(next) ?? []));
        }
        return out;
    }

    /** Сериализует карту children в depth-first items для categories_reorder. */
    private _flatten(children: Map<string | null, string[]>): ShopTreeReorderItem[] {
        const items: ShopTreeReorderItem[] = [];
        const walk = (parentId: string | null) => {
            for (const id of children.get(parentId) ?? []) {
                items.push({ category_id: id, parent_id: parentId });
                walk(id);
            }
        };
        walk(null);
        return items;
    }

    private _emitTree(children: Map<string | null, string[]>): void {
        this.emit('tree-change', { items: this._flatten(children) });
    }

    /** Перемещает узел под нового родителя: якорь — sibling, рядом с которым
     * вставить (null — в конец списка). Индекс ищется после удаления dragged,
     * поэтому перестановка внутри одного списка корректна. */
    private _moveTo(draggedId: string, parentId: string | null, anchorId: string | null, after: boolean): void {
        const children = this._idChildrenMap();
        const byId = new Map(this.categories.map((c) => [c.shop_category_id, c]));
        const dragged = byId.get(draggedId);
        if (dragged === undefined) return;
        const oldParent = dragged.parent_id !== null && byId.has(dragged.parent_id)
            ? dragged.parent_id
            : null;
        const source = children.get(oldParent) ?? [];
        const from = source.indexOf(draggedId);
        if (from === -1) return;
        source.splice(from, 1);
        const target = children.get(parentId) ?? [];
        let at = target.length;
        if (anchorId !== null) {
            const anchorAt = target.indexOf(anchorId);
            at = anchorAt === -1 ? target.length : anchorAt + (after ? 1 : 0);
        }
        target.splice(at, 0, draggedId);
        children.set(parentId, target);
        this._emitTree(children);
    }

    private _siblingIndex(id: string): { siblings: string[]; index: number } {
        const cat = this.categories.find((c) => c.shop_category_id === id);
        if (cat === undefined) return { siblings: [], index: -1 };
        const byId = new Map(this.categories.map((c) => [c.shop_category_id, c]));
        const parent = cat.parent_id !== null && byId.has(cat.parent_id) ? cat.parent_id : null;
        const children = this._idChildrenMap();
        const siblings = children.get(parent) ?? [];
        return { siblings, index: siblings.indexOf(id) };
    }

    private _moveSibling(id: string, dir: -1 | 1): void {
        const { siblings, index } = this._siblingIndex(id);
        const swap = siblings[index + dir];
        if (index === -1 || swap === undefined) return;
        const cat = this.categories.find((c) => c.shop_category_id === id);
        if (cat === undefined) return;
        const children = this._idChildrenMap();
        const byId = new Map(this.categories.map((c) => [c.shop_category_id, c]));
        const parent = cat.parent_id !== null && byId.has(cat.parent_id) ? cat.parent_id : null;
        const list = children.get(parent) ?? [];
        list[index] = swap;
        list[index + dir] = id;
        this._emitTree(children);
    }

    /** Вложить в предыдущего sibling'а (становится его последним ребёнком). */
    private _indent(id: string): void {
        const { siblings, index } = this._siblingIndex(id);
        const prev = siblings[index - 1];
        if (index <= 0 || prev === undefined) return;
        this._moveTo(id, prev, null, false);
        this.emit('tree-toggle', { id: prev, expanded: true });
    }

    /** Поднять на уровень родителя — сразу после него в списке siblings. */
    private _outdent(id: string): void {
        const cat = this.categories.find((c) => c.shop_category_id === id);
        if (cat === undefined || cat.parent_id === null) return;
        const byId = new Map(this.categories.map((c) => [c.shop_category_id, c]));
        const parent = cat.parent_id;
        if (!byId.has(parent)) return;
        const grand = byId.get(parent)?.parent_id ?? null;
        const resolved = grand !== null && byId.has(grand) ? grand : null;
        this._moveTo(id, resolved, parent, true);
    }

    // --- DnD ---

    private _onDragStart(e: DragEvent, id: string): void {
        e.stopPropagation();
        e.dataTransfer?.setData(CATEGORY_MIME, id);
        if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
        this._draggingId = id;
    }

    private _onDragEnd(): void {
        this._draggingId = '';
        this._dropHint = null;
    }

    private _zoneFromOffset(e: DragEvent, el: HTMLElement): DropZone {
        const rect = el.getBoundingClientRect();
        const ratio = (e.clientY - rect.top) / Math.max(rect.height, 1);
        if (ratio < 0.28) return 'before';
        if (ratio > 0.72) return 'after';
        return 'nest';
    }

    /** Допустимый родитель для drop-зоны; null — дроп запрещён. */
    private _dropCandidate(targetId: string, zone: DropZone): string | null | 'forbidden' {
        const byId = new Map(this.categories.map((c) => [c.shop_category_id, c]));
        const target = byId.get(targetId);
        const dragged = byId.get(this._draggingId);
        if (target === undefined || dragged === undefined) return 'forbidden';
        if (zone === 'nest') {
            if (targetId === this._draggingId) return 'forbidden';
            return targetId;
        }
        if (targetId === this._draggingId) return 'forbidden';
        const parent = target.parent_id !== null && byId.has(target.parent_id)
            ? target.parent_id
            : null;
        return parent;
    }

    private _onRowDragOver(e: DragEvent, cat: ShopTreeCategory, el: HTMLElement): void {
        if (!e.dataTransfer) return;
        if (e.dataTransfer.types.includes(PRODUCT_MIME)) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            this._setHint({ id: cat.shop_category_id, zone: 'nest' });
            return;
        }
        if (!e.dataTransfer.types.includes(CATEGORY_MIME)) return;
        const zone = this._zoneFromOffset(e, el);
        const candidate = this._dropCandidate(cat.shop_category_id, zone);
        if (candidate === 'forbidden'
            || (candidate !== null && this._descendantIds(this._draggingId).has(candidate))) {
            if (this._dropHint !== null) this._dropHint = null;
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'move';
        this._setHint({ id: cat.shop_category_id, zone });
    }

    private _setHint(hint: DropHint | null): void {
        const cur = this._dropHint;
        if (hint === null || cur === null || cur.id !== hint.id || cur.zone !== hint.zone) {
            this._dropHint = hint;
        }
    }

    private _onRowDragLeave(e: DragEvent, cat: ShopTreeCategory): void {
        const related = e.relatedTarget;
        const row = e.currentTarget;
        if (row instanceof HTMLElement && related instanceof Node && row.contains(related)) return;
        if (this._dropHint?.id === cat.shop_category_id) this._dropHint = null;
    }

    private _onRowDrop(e: DragEvent, cat: ShopTreeCategory, el: HTMLElement): void {
        e.preventDefault();
        e.stopPropagation();
        this._dropHint = null;
        const productId = e.dataTransfer?.getData(PRODUCT_MIME);
        if (typeof productId === 'string' && productId !== '') {
            this.emit('product-drop', { productId, categoryId: cat.shop_category_id });
            return;
        }
        const draggedId = e.dataTransfer?.getData(CATEGORY_MIME);
        if (typeof draggedId !== 'string' || draggedId === '') return;
        const zone = this._zoneFromOffset(e, el);
        const candidate = this._dropCandidate(cat.shop_category_id, zone);
        if (candidate === 'forbidden'
            || (candidate !== null && this._descendantIds(draggedId).has(candidate))) return;
        if (zone === 'nest') {
            this._moveTo(draggedId, cat.shop_category_id, null, false);
            this.emit('tree-toggle', { id: cat.shop_category_id, expanded: true });
            return;
        }
        this._moveTo(draggedId, candidate, cat.shop_category_id, zone === 'after');
    }

    private _onAllDragOver(e: DragEvent): void {
        if (!e.dataTransfer) return;
        if (e.dataTransfer.types.includes(PRODUCT_MIME) || e.dataTransfer.types.includes(CATEGORY_MIME)) {
            e.preventDefault();
            e.stopPropagation();
            e.dataTransfer.dropEffect = 'move';
            this._setHint({ id: ALL_ROW, zone: 'nest' });
        }
    }

    private _onAllDrop(e: DragEvent): void {
        e.preventDefault();
        e.stopPropagation();
        this._dropHint = null;
        const productId = e.dataTransfer?.getData(PRODUCT_MIME);
        if (typeof productId === 'string' && productId !== '') {
            this.emit('product-drop', { productId, categoryId: null });
            return;
        }
        const draggedId = e.dataTransfer?.getData(CATEGORY_MIME);
        if (typeof draggedId === 'string' && draggedId !== '') {
            this._moveTo(draggedId, null, null, false);
        }
    }

    private _onListDrop(e: DragEvent): void {
        const draggedId = e.dataTransfer?.getData(CATEGORY_MIME);
        if (typeof draggedId !== 'string' || draggedId === '') return;
        e.preventDefault();
        this._dropHint = null;
        this._moveTo(draggedId, null, null, false);
    }

    private _onListDragOver(e: DragEvent): void {
        const el = e.target;
        if (el instanceof HTMLElement && el.closest('.treeitem')) return;
        if (e.dataTransfer?.types.includes(CATEGORY_MIME)) {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
        }
    }

    // --- Inline создание и переименование ---

    private _focusPending = false;

    private _beginCreate(parentId: string): void {
        this._creatingUnder = parentId;
        this._editingId = '';
        this._editValue = '';
        this._focusPending = true;
        if (parentId !== ROOT_CREATE) {
            this.emit('tree-toggle', { id: parentId, expanded: true });
        }
    }

    private _beginRename(cat: ShopTreeCategory): void {
        this._editingId = cat.shop_category_id;
        this._creatingUnder = '';
        this._editValue = cat.name;
        this._focusPending = true;
    }

    private _commitEdit(): void {
        const name = this._editValue.trim();
        if (name === '') return;
        if (this._creatingUnder !== '') {
            this.emit('tree-create', {
                parentId: this._creatingUnder === ROOT_CREATE ? null : this._creatingUnder,
                name,
            });
            this._creatingUnder = '';
        } else if (this._editingId !== '') {
            const id = this._editingId;
            const cat = this.categories.find((c) => c.shop_category_id === id);
            if (cat !== undefined && cat.name !== name) {
                this.emit('tree-rename', { id, name });
            }
            this._editingId = '';
        }
        this._editValue = '';
    }

    private _cancelEdit(): void {
        this._creatingUnder = '';
        this._editingId = '';
        this._editValue = '';
    }

    override updated(): void {
        if (!this._focusPending) return;
        this._focusPending = false;
        const field = this.renderRoot.querySelector<HTMLElement>('.edit-row platform-field');
        field?.focus();
    }

    private _renderEditRow(depth: number): TemplateResult {
        return html`
            <div class="edit-row" style="padding-left: ${depth * 14 + 22}px">
                <platform-field
                    type="string"
                    mode="edit"
                    label=${this.t('menu.new_category')}
                    .value=${this._editValue}
                    @change=${(event: CustomEvent<{ value?: unknown }>) => {
                        this._editValue = typeof event.detail.value === 'string' ? event.detail.value : '';
                    }}
                    @keydown=${(event: KeyboardEvent) => {
                        if (event.key === 'Enter') { event.preventDefault(); this._commitEdit(); }
                        if (event.key === 'Escape') { event.preventDefault(); this._cancelEdit(); }
                    }}
                ></platform-field>
                <platform-button icon-only density="compact" variant="primary"
                    title=${this.t('menu.save')} ?disabled=${this._editValue.trim() === ''}
                    @click=${() => this._commitEdit()}
                ><platform-icon name="check" size="12"></platform-icon></platform-button>
                <platform-button icon-only density="compact" variant="ghost"
                    title=${this.t('menu.cancel')}
                    @click=${() => this._cancelEdit()}
                ><platform-icon name="close" size="12"></platform-icon></platform-button>
            </div>`;
    }

    private _renderNode(cat: ShopTreeCategory, childrenMap: Map<string | null, ShopTreeCategory[]>, depth: number): TemplateResult {
        const children = childrenMap.get(cat.shop_category_id) ?? [];
        const hasChildren = children.length > 0;
        const expanded = this.expandedIds.includes(cat.shop_category_id);
        const active = this.activeId === cat.shop_category_id;
        const hint = this._dropHint !== null && this._dropHint.id === cat.shop_category_id ? this._dropHint.zone : '';
        const count = this.counts[cat.shop_category_id] ?? 0;
        const { siblings, index } = this._siblingIndex(cat.shop_category_id);
        const isRoot = cat.parent_id === null;
        return html`
            <div class="row" style="padding-left: ${depth * 14}px">
                <button class="toggle ${expanded ? 'expanded' : ''}" type="button"
                    ?disabled=${!hasChildren}
                    title=${expanded ? this.t('menu.cat_collapse') : this.t('menu.cat_expand')}
                    @click=${(e: Event) => { e.stopPropagation(); this.emit('tree-toggle', { id: cat.shop_category_id, expanded: !expanded }); }}
                ><platform-icon name="chevron-right" size="12"></platform-icon></button>
                ${this._editingId === cat.shop_category_id
                    ? this._renderEditRow(depth)
                    : html`
                <div class="treeitem ${active ? 'active' : ''} ${cat.is_active ? '' : 'off'} ${this._draggingId === cat.shop_category_id ? 'dragging' : ''} ${hint !== '' ? `drop-${hint}` : ''}"
                    role="treeitem"
                    draggable="true"
                    @dragstart=${(e: DragEvent) => this._onDragStart(e, cat.shop_category_id)}
                    @dragend=${() => this._onDragEnd()}
                    @dragover=${(e: DragEvent) => this._onRowDragOver(e, cat, e.currentTarget as HTMLElement)}
                    @dragleave=${(e: DragEvent) => this._onRowDragLeave(e, cat)}
                    @drop=${(e: DragEvent) => this._onRowDrop(e, cat, e.currentTarget as HTMLElement)}
                >
                    <button class="item-main" type="button" @click=${() => this.emit('tree-select', { id: cat.shop_category_id })}>
                        <platform-icon class="grip" name="drag-handle" size="12"></platform-icon>
                        <span class="item-label" title=${cat.name}>${cat.name}</span>
                        <span class="count">${count}</span>
                    </button>
                    <span class="ops">
                        <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_add_child')}
                            @click=${(e: Event) => { e.stopPropagation(); this._beginCreate(cat.shop_category_id); }}
                        ><platform-icon name="plus" size="12"></platform-icon></platform-button>
                        <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_rename')}
                            @click=${(e: Event) => { e.stopPropagation(); this._beginRename(cat); }}
                        ><platform-icon name="edit" size="12"></platform-icon></platform-button>
                        <platform-button icon-only density="dense" variant="ghost-danger" title=${this.t('menu.category_remove')}
                            @click=${(e: Event) => { e.stopPropagation(); this.emit('tree-remove', { id: cat.shop_category_id }); }}
                        ><platform-icon name="trash" size="12"></platform-icon></platform-button>
                    </span>
                </div>`}
            </div>
            ${active && this._editingId === '' ? html`
                <div class="movebar" style="padding-left: ${depth * 14 + 22}px">
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.move_up')}
                        ?disabled=${index <= 0}
                        @click=${() => this._moveSibling(cat.shop_category_id, -1)}
                    ><platform-icon name="chevron-up" size="12"></platform-icon></platform-button>
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.move_down')}
                        ?disabled=${index === -1 || index >= siblings.length - 1}
                        @click=${() => this._moveSibling(cat.shop_category_id, 1)}
                    ><platform-icon name="chevron-down" size="12"></platform-icon></platform-button>
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_indent')}
                        ?disabled=${index <= 0}
                        @click=${() => this._indent(cat.shop_category_id)}
                    ><platform-icon name="chevron-right" size="12"></platform-icon></platform-button>
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_outdent')}
                        ?disabled=${isRoot}
                        @click=${() => this._outdent(cat.shop_category_id)}
                    ><platform-icon name="chevron-left" size="12"></platform-icon></platform-button>
                </div>` : nothing}
            ${hasChildren && expanded ? html`
                <div class="children">
                    ${this._creatingUnder === cat.shop_category_id ? this._renderEditRow(depth + 1) : nothing}
                    ${children.map((child) => this._renderNode(child, childrenMap, depth + 1))}
                </div>` : nothing}
            ${!hasChildren && this._creatingUnder === cat.shop_category_id ? html`
                <div class="children">${this._renderEditRow(depth + 1)}</div>` : nothing}
        `;
    }

    override render(): TemplateResult {
        const childrenMap = this._childrenMap();
        const roots = childrenMap.get(null) ?? [];
        const allActive = this.activeId === null;
        const allHint = this._dropHint !== null && this._dropHint.id === ALL_ROW;
        return html`
            <div class="head">
                <span class="head-title">${this.t('menu.categories_title')}</span>
                <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.new_category')}
                    @click=${() => this._beginCreate(ROOT_CREATE)}
                ><platform-icon name="plus" size="12"></platform-icon></platform-button>
            </div>
            <div class="list" role="tree"
                @dragover=${(e: DragEvent) => this._onListDragOver(e)}
                @drop=${(e: DragEvent) => this._onListDrop(e)}
            >
                <div class="treeitem ${allActive ? 'active' : ''} ${allHint ? 'drop-nest' : ''}"
                    @dragover=${(e: DragEvent) => this._onAllDragOver(e)}
                    @dragleave=${(e: DragEvent) => { if (this._dropHint?.id === ALL_ROW) this._dropHint = null; }}
                    @drop=${(e: DragEvent) => this._onAllDrop(e)}
                >
                    <button class="item-main" type="button" @click=${() => this.emit('tree-select', { id: null })}>
                        <platform-icon name="list" size="13"></platform-icon>
                        <span class="item-label">${this.t('menu.all_products')}</span>
                        <span class="count">${this.allCount}</span>
                    </button>
                </div>
                ${this._creatingUnder === ROOT_CREATE ? this._renderEditRow(0) : nothing}
                ${roots.length === 0 && this._creatingUnder === ''
                    ? html`<div class="empty">${this.t('menu.cat_empty_hint')}</div>`
                    : roots.map((cat) => this._renderNode(cat, childrenMap, 0))}
            </div>
        `;
    }
}

customElements.define('shop-category-tree', ShopCategoryTree);

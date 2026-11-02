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
const AUTO_EXPAND_MS = 550;

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
                padding: var(--space-1) var(--space-2) var(--space-1);
            }
            .head-title {
                font-size: var(--text-xs); font-weight: var(--font-semibold);
                color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em;
            }

            .list { display: flex; flex-direction: column; gap: 1px; padding: 0 var(--space-1) var(--space-1); }

            .row {
                display: flex; align-items: center; position: relative;
            }
            .toggle {
                display: inline-flex; align-items: center; justify-content: center;
                width: 20px; height: 32px; border: 0; background: transparent;
                color: var(--text-tertiary); cursor: pointer; flex-shrink: 0; padding: 0;
                border-radius: var(--radius-sm);
            }
            .toggle:hover { color: var(--text-primary); }
            .toggle:disabled { visibility: hidden; }
            .toggle platform-icon { transition: transform 0.18s ease; }
            .toggle.expanded platform-icon { transform: rotate(90deg); }

            .treeitem {
                display: flex; align-items: center; gap: 2px;
                flex: 1; min-width: 0; height: 32px;
                padding: 0 var(--space-1) 0 0;
                border: 1px solid transparent; border-radius: var(--radius-md);
                background: transparent; color: var(--text-secondary);
                font-size: var(--text-sm);
                transition: background 0.12s ease, border-color 0.12s ease, box-shadow 0.12s ease;
            }
            .treeitem:hover { background: color-mix(in srgb, var(--text-primary) 5%, transparent); }
            .treeitem.off { opacity: 0.5; }
            .treeitem.active {
                background: color-mix(in srgb, var(--accent) 12%, transparent);
                color: var(--accent);
            }
            .treeitem.dragging { opacity: 0.35; }
            :host([data-dragging]) .treeitem { cursor: grabbing; }

            .treeitem.drop-nest {
                border-color: var(--accent);
                background: color-mix(in srgb, var(--accent) 14%, transparent);
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 12%, transparent);
            }
            .treeitem.drop-before::before, .treeitem.drop-after::after {
                content: ''; position: absolute; left: 2px; right: 4px; height: 2px;
                border-radius: 2px; background: var(--accent);
                box-shadow: 0 0 6px color-mix(in srgb, var(--accent) 60%, transparent);
                pointer-events: none; z-index: 1;
            }
            .treeitem.drop-before::before { top: -2px; }
            .treeitem.drop-after::after { bottom: -2px; }
            .treeitem.drop-before::after, .treeitem.drop-after::before {
                content: ''; position: absolute; width: 6px; height: 6px; border-radius: 50%;
                background: var(--accent); pointer-events: none; z-index: 1;
            }
            .treeitem.drop-before::after { top: -4px; left: -1px; }
            .treeitem.drop-after::before { bottom: -4px; left: -1px; }

            .item-main {
                display: flex; align-items: center; gap: 6px;
                flex: 1; min-width: 0; height: 100%;
                border: 0; background: transparent; padding: 0;
                color: inherit; font: inherit; text-align: left; cursor: pointer;
            }
            .item-main .lead { color: var(--text-tertiary); flex-shrink: 0; display: inline-flex; }
            .treeitem.active .item-main .lead { color: var(--accent); }
            .grip {
                color: var(--text-tertiary); opacity: 0; flex-shrink: 0; cursor: grab;
                display: inline-flex; transition: opacity 0.12s ease;
            }
            .treeitem:hover .grip, .treeitem.dragging .grip { opacity: 0.7; }
            .item-label {
                flex: 1; min-width: 0; overflow: hidden;
                text-overflow: ellipsis; white-space: nowrap;
            }
            .treeitem.active .item-label { font-weight: var(--font-semibold); }
            .count {
                font-size: var(--text-xs); color: var(--text-tertiary);
                font-variant-numeric: tabular-nums; flex-shrink: 0;
                padding: 0 var(--space-1);
            }
            .treeitem.active .count { color: var(--accent); }
            .row:hover .count, .row:focus-within .count { opacity: 0; }

            .ops {
                display: none; align-items: center; flex-shrink: 0; padding-right: 2px;
            }
            .treeitem:hover .ops, .treeitem:focus-within .ops { display: inline-flex; }
            @media (hover: none) { .ops { display: inline-flex; } }

            .add-row {
                display: flex; align-items: center; gap: 6px;
                height: 32px; margin: 2px 0 0; padding: 0 var(--space-2) 0 26px;
                border: 1px dashed color-mix(in srgb, var(--text-tertiary) 35%, transparent);
                border-radius: var(--radius-md); background: transparent;
                color: var(--text-tertiary); font: inherit; font-size: var(--text-sm);
                cursor: pointer; width: 100%; text-align: left;
                transition: border-color 0.12s ease, color 0.12s ease, background 0.12s ease;
            }
            .add-row:hover {
                border-color: var(--accent); color: var(--accent);
                background: color-mix(in srgb, var(--accent) 6%, transparent);
            }

            .children { position: relative; animation: treeSlide 0.16s ease; }
            .children .guide {
                position: absolute; top: 0; bottom: 0; width: 1px;
                background: color-mix(in srgb, var(--text-tertiary) 18%, transparent);
                pointer-events: none;
            }
            @keyframes treeSlide {
                from { opacity: 0; transform: translateY(-4px); }
                to { opacity: 1; transform: translateY(0); }
            }

            .movebar {
                display: inline-flex; align-items: center; margin: 2px 0 4px 26px;
                border: 1px solid var(--glass-border-subtle); border-radius: var(--radius-md);
                background: var(--bg-surface); overflow: hidden;
            }
            .movebar platform-button { --platform-button-padding: 4px 7px; border-radius: 0; }
            .movebar platform-button + platform-button { margin-left: 1px; }

            .edit-row {
                display: flex; align-items: center; height: 32px; gap: 6px;
                padding-right: var(--space-1);
            }
            .edit-row .toggle-space { width: 20px; flex-shrink: 0; }
            .edit-input {
                flex: 1; min-width: 0; height: 26px; padding: 0 var(--space-2);
                border: 1px solid var(--accent); border-radius: var(--radius-md);
                background: var(--bg-surface); color: var(--text-primary);
                font: inherit; font-size: var(--text-sm); outline: none;
                box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 14%, transparent);
            }
            .edit-input::placeholder { color: var(--text-tertiary); }

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

    private _dragGhost: HTMLElement | null = null;
    private _autoExpandTimer: number | undefined;
    private _autoExpandId = '';

    private _onDragStart(e: DragEvent, cat: ShopTreeCategory): void {
        e.stopPropagation();
        e.dataTransfer?.setData(CATEGORY_MIME, cat.shop_category_id);
        if (e.dataTransfer) {
            e.dataTransfer.effectAllowed = 'move';
            this._setDragImage(e.dataTransfer, cat);
        }
        this._draggingId = cat.shop_category_id;
        this.setAttribute('data-dragging', '');
    }

    private _setDragImage(dt: DataTransfer, cat: ShopTreeCategory): void {
        const ghost = document.createElement('div');
        const accent = getComputedStyle(this).getPropertyValue('--accent').trim();
        Object.assign(ghost.style, {
            position: 'fixed', top: '-1000px', left: '-1000px',
            display: 'inline-flex', alignItems: 'center', gap: '6px',
            padding: '5px 12px', borderRadius: '8px',
            background: 'rgba(24, 24, 28, 0.92)', color: '#fff',
            border: `1px solid ${accent !== '' ? accent : '#7c6cf8'}`,
            boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
            font: '500 13px/1.2 system-ui, sans-serif',
            pointerEvents: 'none', zIndex: '2147483647',
        });
        ghost.textContent = cat.name;
        document.body.append(ghost);
        this._dragGhost = ghost;
        dt.setDragImage(ghost, -8, 14);
    }

    private _onDragEnd(): void {
        this._draggingId = '';
        this._dropHint = null;
        this.removeAttribute('data-dragging');
        this._dragGhost?.remove();
        this._dragGhost = null;
        this._clearAutoExpand();
    }

    private _zoneFromOffset(e: DragEvent, el: HTMLElement): DropZone {
        const rect = el.getBoundingClientRect();
        const ratio = (e.clientY - rect.top) / Math.max(rect.height, 1);
        if (ratio < 0.28) return 'before';
        if (ratio > 0.72) return 'after';
        return 'nest';
    }

    /** Допустимый родитель для drop-зоны; 'forbidden' — дроп запрещён. */
    private _dropCandidate(targetId: string, zone: DropZone): string | null | 'forbidden' {
        const byId = new Map(this.categories.map((c) => [c.shop_category_id, c]));
        const target = byId.get(targetId);
        const dragged = byId.get(this._draggingId);
        if (target === undefined || dragged === undefined) return 'forbidden';
        if (targetId === this._draggingId) return 'forbidden';
        if (zone === 'nest') {
            return targetId;
        }
        const parent = target.parent_id !== null && byId.has(target.parent_id)
            ? target.parent_id
            : null;
        return parent;
    }

    private _onRowDragOver(e: DragEvent, cat: ShopTreeCategory, el: HTMLElement): void {
        if (!e.dataTransfer) return;
        if (e.dataTransfer.types.includes(PRODUCT_MIME)) {
            e.preventDefault();
            e.stopPropagation();
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
            this._clearAutoExpand();
            return;
        }
        e.preventDefault();
        e.stopPropagation();
        e.dataTransfer.dropEffect = 'move';
        this._setHint({ id: cat.shop_category_id, zone });
        if (zone === 'nest') this._scheduleAutoExpand(cat);
        else this._clearAutoExpand();
    }

    /** При удержании курсора над свёрнутой категорией раскрывает её. */
    private _scheduleAutoExpand(cat: ShopTreeCategory): void {
        if (this.expandedIds.includes(cat.shop_category_id)) return;
        if (this._autoExpandId === cat.shop_category_id && this._autoExpandTimer !== undefined) return;
        this._clearAutoExpand();
        this._autoExpandId = cat.shop_category_id;
        this._autoExpandTimer = window.setTimeout(() => {
            this._autoExpandTimer = undefined;
            const children = this._idChildrenMap().get(cat.shop_category_id) ?? [];
            if (children.length > 0 && !this.expandedIds.includes(cat.shop_category_id)) {
                this.emit('tree-toggle', { id: cat.shop_category_id, expanded: true });
            }
        }, AUTO_EXPAND_MS);
    }

    private _clearAutoExpand(): void {
        if (this._autoExpandTimer !== undefined) {
            window.clearTimeout(this._autoExpandTimer);
            this._autoExpandTimer = undefined;
        }
        this._autoExpandId = '';
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
        this._clearAutoExpand();
    }

    private _onRowDrop(e: DragEvent, cat: ShopTreeCategory, el: HTMLElement): void {
        e.preventDefault();
        e.stopPropagation();
        this._dropHint = null;
        this._clearAutoExpand();
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
        if (this._creatingUnder !== '') {
            const parentId = this._creatingUnder;
            this._creatingUnder = '';
            this._editValue = '';
            if (name !== '') {
                this.emit('tree-create', {
                    parentId: parentId === ROOT_CREATE ? null : parentId,
                    name,
                });
            }
            return;
        }
        if (this._editingId !== '') {
            const id = this._editingId;
            const cat = this.categories.find((c) => c.shop_category_id === id);
            this._editingId = '';
            this._editValue = '';
            if (name !== '' && cat !== undefined && cat.name !== name) {
                this.emit('tree-rename', { id, name });
            }
        }
    }

    private _cancelEdit(): void {
        this._creatingUnder = '';
        this._editingId = '';
        this._editValue = '';
    }

    override updated(): void {
        if (!this._focusPending) return;
        this._focusPending = false;
        const input = this.renderRoot.querySelector<HTMLInputElement>('.edit-input');
        input?.focus();
        input?.select();
    }

    private _renderEditRow(depth: number): TemplateResult {
        return html`
            <div class="edit-row" style="padding-left: ${depth * 14}px">
                <span class="toggle-space"></span>
                <input class="edit-input" data-canon="inline-edit"
                    type="text"
                    placeholder=${this.t('menu.new_category')}
                    .value=${this._editValue}
                    @input=${(e: Event) => { this._editValue = (e.target as HTMLInputElement).value; }}
                    @keydown=${(e: KeyboardEvent) => {
                        if (e.key === 'Enter') { e.preventDefault(); this._commitEdit(); }
                        if (e.key === 'Escape') { e.preventDefault(); this._cancelEdit(); }
                    }}
                    @blur=${() => this._commitEdit()}
                >
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
                ><platform-icon name="chevron-right" size="13"></platform-icon></button>
                ${this._editingId === cat.shop_category_id
                    ? html`
                        <input class="edit-input" data-canon="inline-edit"
                            type="text"
                            placeholder=${this.t('menu.new_category')}
                            .value=${this._editValue}
                            @input=${(e: Event) => { this._editValue = (e.target as HTMLInputElement).value; }}
                            @keydown=${(e: KeyboardEvent) => {
                                if (e.key === 'Enter') { e.preventDefault(); this._commitEdit(); }
                                if (e.key === 'Escape') { e.preventDefault(); this._cancelEdit(); }
                            }}
                            @blur=${() => this._commitEdit()}
                        >`
                    : html`
                <div class="treeitem ${active ? 'active' : ''} ${cat.is_active ? '' : 'off'} ${this._draggingId === cat.shop_category_id ? 'dragging' : ''} ${hint !== '' ? `drop-${hint}` : ''}"
                    role="treeitem"
                    aria-expanded=${hasChildren ? String(expanded) : nothing}
                    aria-selected=${String(active)}
                    aria-level=${String(depth + 1)}
                    draggable="true"
                    @dragstart=${(e: DragEvent) => this._onDragStart(e, cat)}
                    @dragend=${() => this._onDragEnd()}
                    @dragover=${(e: DragEvent) => this._onRowDragOver(e, cat, e.currentTarget as HTMLElement)}
                    @dragleave=${(e: DragEvent) => this._onRowDragLeave(e, cat)}
                    @drop=${(e: DragEvent) => this._onRowDrop(e, cat, e.currentTarget as HTMLElement)}
                >
                    <button class="item-main" type="button" @click=${() => this.emit('tree-select', { id: cat.shop_category_id })}>
                        <platform-icon class="grip" name="drag-handle" size="13"></platform-icon>
                        <span class="item-label" title=${cat.name}>${cat.name}</span>
                        <span class="count">${count}</span>
                    </button>
                    <span class="ops">
                        <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_add_child')}
                            @click=${(e: Event) => { e.stopPropagation(); this._beginCreate(cat.shop_category_id); }}
                        ><platform-icon name="plus" size="13"></platform-icon></platform-button>
                        <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_rename')}
                            @click=${(e: Event) => { e.stopPropagation(); this._beginRename(cat); }}
                        ><platform-icon name="edit" size="13"></platform-icon></platform-button>
                        <platform-button icon-only density="dense" variant="ghost-danger" title=${this.t('menu.category_remove')}
                            @click=${(e: Event) => { e.stopPropagation(); this.emit('tree-remove', { id: cat.shop_category_id }); }}
                        ><platform-icon name="trash" size="13"></platform-icon></platform-button>
                    </span>
                </div>`}
            </div>
            ${active && this._editingId === '' ? html`
                <div class="movebar" style="margin-left: ${depth * 14 + 26}px">
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.move_up')}
                        ?disabled=${index <= 0}
                        @click=${() => this._moveSibling(cat.shop_category_id, -1)}
                    ><platform-icon name="chevron-up" size="13"></platform-icon></platform-button>
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.move_down')}
                        ?disabled=${index === -1 || index >= siblings.length - 1}
                        @click=${() => this._moveSibling(cat.shop_category_id, 1)}
                    ><platform-icon name="chevron-down" size="13"></platform-icon></platform-button>
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_indent')}
                        ?disabled=${index <= 0}
                        @click=${() => this._indent(cat.shop_category_id)}
                    ><platform-icon name="chevron-right" size="13"></platform-icon></platform-button>
                    <platform-button icon-only density="dense" variant="ghost" title=${this.t('menu.cat_outdent')}
                        ?disabled=${isRoot}
                        @click=${() => this._outdent(cat.shop_category_id)}
                    ><platform-icon name="chevron-left" size="13"></platform-icon></platform-button>
                </div>` : nothing}
            ${hasChildren && expanded ? html`
                <div class="children">
                    <div class="guide" style="left: ${depth * 14 + 9}px"></div>
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
                ><platform-icon name="plus" size="13"></platform-icon></platform-button>
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
                        <span class="lead"><platform-icon name="list" size="14"></platform-icon></span>
                        <span class="item-label">${this.t('menu.all_products')}</span>
                        <span class="count">${this.allCount}</span>
                    </button>
                </div>
                ${this._creatingUnder === ROOT_CREATE ? this._renderEditRow(0) : nothing}
                ${roots.map((cat) => this._renderNode(cat, childrenMap, 0))}
                ${roots.length === 0 && this._creatingUnder === '' ? html`
                    <div class="empty">${this.t('menu.cat_empty_hint')}</div>` : nothing}
                <button class="add-row" type="button"
                    @click=${() => this._beginCreate(ROOT_CREATE)}
                ><platform-icon name="plus" size="13"></platform-icon>${this.t('menu.new_category')}</button>
            </div>
        `;
    }
}

customElements.define('shop-category-tree', ShopCategoryTree);

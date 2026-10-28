/**
 * Дерево с раскрытием, перетаскиванием и контекстным меню.
 *
 * Узлы описываются плоским списком с `parent_id`: так их отдают и wiki, и
 * каталоги документов, и не нужно перестраивать вложенные структуры на каждое
 * изменение. Компонент не ходит в сеть и не знает про домен — он сообщает о
 * действиях событиями, а состояние раскрытия хранит у себя.
 *
 * При перетаскивании различаются два намерения: положить **внутрь** узла и
 * вставить **между** узлами. От этого зависит и подсветка, и payload события.
 *
 * @example
 * <platform-tree
 *     .nodes=${nodes}
 *     selected-id=${pageId}
 *     draggable-nodes
 *     .menuItems=${(node) => this._menuFor(node)}
 *     @tree-select=${(e) => this._open(e.detail.id)}
 *     @tree-move=${(e) => this._move(e.detail)}
 * ></platform-tree>
 */

import { css, html, nothing } from '../lit-shim.js';
import { repeat } from 'lit/directives/repeat.js';

import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';
import './platform-menu.js';
import './platform-popover.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from '../lit-shim.js';
import type { PopoverAnchor } from './platform-popover.js';

export interface PlatformTreeNode {
    id: string;
    label: string;
    parent_id?: string | null;
    /** имя platform-icon */
    icon?: string;
    /** эмодзи вместо иконки */
    emoji?: string;
    /** показать раскрывающий шеврон до загрузки детей */
    has_children?: boolean;
    /** число справа (например, количество файлов) */
    count?: number;
    [key: string]: unknown;
}

/** Куда попадёт узел при отпускании. */
const DROP_INSIDE = 'inside';
const DROP_BEFORE = 'before';
const DROP_AFTER = 'after';

/** Доля высоты строки сверху и снизу, попадание в которую значит «между». */
const EDGE_RATIO = 0.28;

function visibleAt(
    rows: readonly { node: PlatformTreeNode; depth: number }[],
    index: number,
): { node: PlatformTreeNode; depth: number } {
    const row = rows[index];
    if (row === undefined) {
        throw new Error('platform-tree: visible row missing');
    }
    return row;
}

function eventElement(event: Event, label: string): Element {
    const target = event.currentTarget;
    if (!(target instanceof Element)) {
        throw new Error(`platform-tree: ${label} target must be an element`);
    }
    return target;
}

export class PlatformTree extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        nodes: { type: Array },
        selectedId: { type: String, attribute: 'selected-id' },
        draggableNodes: { type: Boolean, attribute: 'draggable-nodes' },
        emptyLabel: { type: String, attribute: 'empty-label' },
        ariaLabel: { type: String, attribute: 'aria-label' },
        /** Функция узла → пункты `platform-menu`; без неё меню не открывается. */
        menuItems: { attribute: false },
        _expanded: { state: true },
        _dragId: { state: true },
        _dropTarget: { state: true },
        _menuNode: { state: true },
        _menuAnchor: { state: true },
        _focusedId: { state: true },
    }
    declare nodes: PlatformTreeNode[];
    declare selectedId: string;
    declare draggableNodes: boolean;
    declare emptyLabel: string;
    declare ariaLabel: string;
    declare menuItems: ((node: PlatformTreeNode) => unknown) | null;
    declare _expanded: Set<string>;
    declare _dragId: string;
    declare _dropTarget: { id: string; position: string } | null;
    declare _menuNode: PlatformTreeNode | null;
    declare _menuAnchor: PopoverAnchor;
    declare _focusedId: string;

    private _revealedSelectedId: string;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }

            .row {
                position: relative;
                display: flex;
                align-items: center;
                gap: var(--space-1, 4px);
                min-height: 30px;
                padding-right: var(--space-2, 8px);
                border-radius: var(--radius-sm, 8px);
                color: var(--text-secondary);
                cursor: pointer;
                user-select: none;
                transition: var(--motion-transition-interactive, background-color 120ms ease);
            }

            .row:hover {
                background: var(--glass-tint-subtle, rgba(120, 120, 140, 0.08));
                color: var(--text-primary);
            }

            .row.is-selected {
                background: var(--glass-tint-medium, rgba(120, 120, 140, 0.16));
                color: var(--text-primary);
                font-weight: var(--font-medium, 500);
            }

            .row.is-focused {
                outline: 2px solid var(--accent);
                outline-offset: -2px;
            }

            .row.is-dragging {
                opacity: 0.45;
            }

            .row.drop-inside {
                background: var(--accent-subtle, rgba(99, 102, 241, 0.18));
                box-shadow: inset 0 0 0 1px var(--accent);
            }

            /* Линия вставки рисуется на строке, а не отдельным узлом:
               иначе она сдвигает соседей и дерево дёргается при перетаскивании. */
            .row.drop-before::before,
            .row.drop-after::after {
                content: '';
                position: absolute;
                left: 0;
                right: 0;
                height: 2px;
                background: var(--accent);
                border-radius: 2px;
            }

            .row.drop-before::before {
                top: -1px;
            }

            .row.drop-after::after {
                bottom: -1px;
            }

            .twisty {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 22px;
                height: 22px;
                border: none;
                border-radius: var(--radius-xs, 4px);
                background: transparent;
                color: var(--text-secondary, #5f6368);
                cursor: pointer;
                transition:
                    transform 120ms ease,
                    background 120ms ease,
                    color 120ms ease;
            }

            .twisty:hover {
                background: var(--glass-tint-subtle, rgba(0, 0, 0, 0.06));
                color: var(--text-primary, #202124);
            }

            .row.is-selected .twisty {
                color: var(--text-primary, #202124);
            }

            .twisty[hidden] {
                visibility: hidden;
            }

            .twisty.is-open {
                transform: rotate(90deg);
            }

            .icon {
                flex-shrink: 0;
                display: inline-flex;
                width: 18px;
                justify-content: center;
                font-size: 14px;
                line-height: 1;
            }

            .label {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: var(--text-sm, 0.8125rem);
            }

            .count {
                flex-shrink: 0;
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-xs, 0.75rem);
                font-variant-numeric: tabular-nums;
            }

            /* Меню строки: правая кнопка мыши есть не у всех (тач, трекпад),
               поэтому те же действия открывает видимая кнопка. */
            .row-menu {
                flex-shrink: 0;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 20px;
                height: 20px;
                border: none;
                border-radius: var(--radius-xs, 4px);
                background: transparent;
                color: var(--text-tertiary, #9aa0a6);
                opacity: 0.55;
                cursor: pointer;
                transition: var(--motion-transition-interactive, opacity 120ms ease);
            }

            .row:hover .row-menu,
            .row.is-selected .row-menu,
            .row-menu:hover,
            .row-menu:focus-visible {
                opacity: 1;
            }

            .row-menu:hover {
                background: var(--glass-tint-medium, rgba(120, 120, 140, 0.16));
                color: var(--text-primary);
            }

            .row-menu:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 1px;
            }

            .empty {
                padding: var(--space-3, 12px);
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-sm, 0.8125rem);
            }
        `,
    ];

    constructor() {
        super();
        this.nodes = [];
        this.selectedId = '';
        this.draggableNodes = false;
        this.emptyLabel = '';
        this.ariaLabel = '';
        this.menuItems = null;
        /** @type {Set<string>} */
        this._expanded = new Set();
        this._dragId = '';
        this._dropTarget = null;
        this._menuNode = null;
        this._menuAnchor = null;
        this._focusedId = '';
        this._revealedSelectedId = '';
    }

    override updated(changed: PropertyValues): void {
        super.updated(changed);
        this._revealSelected();
    }

    /**
     * Выбранный узел всегда виден: переход по ссылке или создание вложенного
     * узла не должны оставлять его за свёрнутым родителем.
     *
     * Раскрываем один раз на выбранный id и только когда узел уже есть в
     * `nodes` (дерево может прийти позже маршрута). Свёрнутую вручную ветку
     * повторно не разворачиваем.
     */
    _revealSelected() {
        if (this.selectedId === '' || this._revealedSelectedId === this.selectedId) {
            return;
        }
        if (!this.nodes.some((node) => node.id === this.selectedId)) {
            return;
        }
        this.revealNode(this.selectedId);
        this._revealedSelectedId = this.selectedId;
    }

    /** Раскрыть узел и всех его предков — используется при переходе по ссылке. */
    revealNode(nodeId: string): void {
        const byId = this._byId();
        let current = byId.get(nodeId);
        const next = new Set(this._expanded);
        while (current && current.parent_id) {
            next.add(current.parent_id);
            current = byId.get(current.parent_id);
        }
        this._expanded = next;
    }

    isExpanded(nodeId: string): boolean {
        return this._expanded.has(nodeId);
    }

    setExpanded(nodeId: string, expanded: boolean): void {
        const next = new Set(this._expanded);
        if (expanded) {
            next.add(nodeId);
        } else {
            next.delete(nodeId);
        }
        this._expanded = next;
    }

    _byId(): Map<string, PlatformTreeNode> {
        const map = new Map<string, PlatformTreeNode>();
        for (const node of this.nodes) {
            map.set(node.id, node);
        }
        return map;
    }

    _childrenOf(parentId: string | null): PlatformTreeNode[] {
        return this.nodes.filter((node) => {
            const nodeParent = node.parent_id === undefined ? null : node.parent_id;
            return nodeParent === parentId;
        });
    }

    _hasChildren(node: PlatformTreeNode): boolean {
        if (node.has_children === true) {
            return true;
        }
        return this._childrenOf(node.id).length > 0;
    }

    /** Плоский список видимых узлов — по нему ходит клавиатура. */
    _visibleNodes(
        parentId: string | null = null,
        depth = 0,
        acc: { node: PlatformTreeNode; depth: number }[] = [],
    ): { node: PlatformTreeNode; depth: number }[] {
        for (const node of this._childrenOf(parentId)) {
            acc.push({ node, depth });
            if (this._expanded.has(node.id)) {
                this._visibleNodes(node.id, depth + 1, acc);
            }
        }
        return acc;
    }

    _toggle(node: PlatformTreeNode, event: Event): void {
        event.stopPropagation();
        this.setExpanded(node.id, !this._expanded.has(node.id));
        this.emit('tree-toggle', { id: node.id, expanded: this._expanded.has(node.id) });
    }

    _select(node: PlatformTreeNode): void {
        this._focusedId = node.id;
        this.emit('tree-select', { id: node.id, node });
    }

    _onContextMenu(node: PlatformTreeNode, event: MouseEvent): void {
        if (typeof this.menuItems !== 'function') {
            return;
        }
        event.preventDefault();
        event.stopPropagation();
        this._menuNode = node;
        this._menuAnchor = { x: event.clientX, y: event.clientY };
    }

    /** Кнопка меню строки: якорь — сама кнопка, выбор узла не срабатывает. */
    _openRowMenu(node: PlatformTreeNode, event: MouseEvent): void {
        event.preventDefault();
        event.stopPropagation();
        if (this._menuNode !== null && this._menuNode.id === node.id) {
            this._menuNode = null;
            return;
        }
        this._menuNode = node;
        this._menuAnchor = eventElement(event, 'row menu');
    }

    _onMenuSelect(event: CustomEvent<{ id?: unknown }>): void {
        const node = this._menuNode;
        this._menuNode = null;
        if (node === null) {
            return;
        }
        this.emit('tree-action', { action: event.detail.id, id: node.id, node });
    }

    // --- перетаскивание ---

    _onDragStart(node: PlatformTreeNode, event: DragEvent): void {
        if (!this.draggableNodes) {
            return;
        }
        this._dragId = node.id;
        const transfer = event.dataTransfer;
        if (transfer === null) {
            throw new Error('platform-tree: dataTransfer missing');
        }
        transfer.effectAllowed = 'move';
        transfer.setData('text/plain', node.id);
    }

    _onDragEnd(): void {
        this._dragId = '';
        this._dropTarget = null;
    }

    /** Верх строки — «до», низ — «после», середина — «внутрь». */
    _dropPositionFor(event: DragEvent, row: Element): string {
        const rect = row.getBoundingClientRect();
        const offset = (event.clientY - rect.top) / rect.height;
        if (offset < EDGE_RATIO) {
            return DROP_BEFORE;
        }
        if (offset > 1 - EDGE_RATIO) {
            return DROP_AFTER;
        }
        return DROP_INSIDE;
    }

    _isOwnDescendant(candidateId: string, draggedId: string): boolean {
        const byId = this._byId();
        let current = byId.get(candidateId);
        while (current) {
            if (current.id === draggedId) {
                return true;
            }
            const parentId = current.parent_id;
            current = parentId ? byId.get(parentId) : undefined;
        }
        return false;
    }

    _onDragOver(node: PlatformTreeNode, event: DragEvent): void {
        if (!this.draggableNodes || this._dragId === '') {
            return;
        }
        // Узел нельзя перенести внутрь собственного поддерева — дерево бы распалось.
        if (this._isOwnDescendant(node.id, this._dragId)) {
            return;
        }
        event.preventDefault();
        const transfer = event.dataTransfer;
        if (transfer === null) {
            throw new Error('platform-tree: dataTransfer missing');
        }
        transfer.dropEffect = 'move';
        const position = this._dropPositionFor(event, eventElement(event, 'drop'));
        if (this._dropTarget === null
            || this._dropTarget.id !== node.id
            || this._dropTarget.position !== position) {
            this._dropTarget = { id: node.id, position };
        }
    }

    _onDragLeave(node: PlatformTreeNode): void {
        if (this._dropTarget !== null && this._dropTarget.id === node.id) {
            this._dropTarget = null;
        }
    }

    _onDrop(node: PlatformTreeNode, event: DragEvent): void {
        if (!this.draggableNodes || this._dragId === '' || this._dropTarget === null) {
            return;
        }
        event.preventDefault();
        const dragId = this._dragId;
        const { position } = this._dropTarget;
        this._dragId = '';
        this._dropTarget = null;
        if (dragId === node.id) {
            return;
        }
        if (position === DROP_INSIDE) {
            // Иначе перенесённый узел пропадает внутри свёрнутого родителя.
            this.setExpanded(node.id, true);
        }
        this.emit('tree-move', {
            id: dragId,
            target_id: node.id,
            position,
            parent_id: position === DROP_INSIDE
                ? node.id
                : (node.parent_id === undefined ? null : node.parent_id),
        });
    }

    // --- клавиатура ---

    _onKeyDown(event: KeyboardEvent): void {
        const visible = this._visibleNodes();
        if (visible.length === 0) {
            return;
        }
        const currentIndex = visible.findIndex((entry) => entry.node.id === this._focusedId);
        const currentEntry = currentIndex === -1 ? null : visible[currentIndex];
        if (currentIndex !== -1 && currentEntry === undefined) {
            throw new Error('platform-tree: focused row missing');
        }
        const current = currentEntry === null || currentEntry === undefined ? null : currentEntry.node;

        if (event.key === 'ArrowDown') {
            event.preventDefault();
            const next = visibleAt(visible, Math.min(currentIndex + 1, visible.length - 1));
            const target = currentIndex === -1 ? visibleAt(visible, 0) : next;
            this._focusedId = target.node.id;
            return;
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault();
            const prev = visibleAt(visible, Math.max(currentIndex - 1, 0));
            const target = currentIndex === -1 ? visibleAt(visible, 0) : prev;
            this._focusedId = target.node.id;
            return;
        }
        if (event.key === 'ArrowRight' && current) {
            event.preventDefault();
            if (this._hasChildren(current) && !this._expanded.has(current.id)) {
                this.setExpanded(current.id, true);
            } else {
                const children = this._childrenOf(current.id);
                if (children.length > 0) {
                    const firstChild = children[0];
                    if (firstChild === undefined) {
                        throw new Error('platform-tree: first child missing');
                    }
                    this._focusedId = firstChild.id;
                }
            }
            return;
        }
        if (event.key === 'ArrowLeft' && current) {
            event.preventDefault();
            if (this._expanded.has(current.id)) {
                this.setExpanded(current.id, false);
            } else if (current.parent_id) {
                this._focusedId = current.parent_id;
            }
            return;
        }
        if ((event.key === 'Enter' || event.key === ' ') && current) {
            event.preventDefault();
            this._select(current);
        }
    }

    override render(): TemplateResult {
        const roots = this._childrenOf(null);
        if (roots.length === 0) {
            return html`<div class="empty">${this.emptyLabel}<slot name="empty"></slot></div>`;
        }

        return html`
            <div
                role="tree"
                aria-label=${this.ariaLabel || nothing}
                tabindex="0"
                @keydown=${this._onKeyDown}
            >
                ${roots.map((node) => this._renderNode(node, 0))}
            </div>
            <platform-popover
                trigger="manual"
                role="menu"
                placement="bottom-start"
                offset="2"
                .anchor=${this._menuAnchor}
                ?open=${this._menuNode !== null}
                @popover-dismiss=${() => { this._menuNode = null; }}
            >
                ${this._menuNode !== null && typeof this.menuItems === 'function'
                    ? html`<platform-menu
                          compact
                          .items=${this.menuItems(this._menuNode)}
                          @menu-select=${this._onMenuSelect}
                      ></platform-menu>`
                    : nothing}
            </platform-popover>
        `;
    }

    _renderNode(node: PlatformTreeNode, depth: number): TemplateResult {
        const expanded = this._expanded.has(node.id);
        const hasChildren = this._hasChildren(node);
        const drop = this._dropTarget !== null && this._dropTarget.id === node.id
            ? this._dropTarget.position
            : '';
        const classes = [
            'row',
            node.id === this.selectedId ? 'is-selected' : '',
            node.id === this._focusedId ? 'is-focused' : '',
            node.id === this._dragId ? 'is-dragging' : '',
            drop === DROP_INSIDE ? 'drop-inside' : '',
            drop === DROP_BEFORE ? 'drop-before' : '',
            drop === DROP_AFTER ? 'drop-after' : '',
        ]
            .filter(Boolean)
            .join(' ');

        return html`
            <div
                class=${classes}
                role="treeitem"
                data-node-id=${node.id}
                aria-level=${depth + 1}
                aria-selected=${node.id === this.selectedId ? 'true' : 'false'}
                aria-expanded=${hasChildren ? String(expanded) : nothing}
                style=${`padding-left:${depth * 14 + 4}px`}
                draggable=${this.draggableNodes ? 'true' : 'false'}
                @click=${() => this._select(node)}
                @contextmenu=${(event: MouseEvent) => this._onContextMenu(node, event)}
                @dragstart=${(event: DragEvent) => this._onDragStart(node, event)}
                @dragend=${this._onDragEnd}
                @dragover=${(event: DragEvent) => this._onDragOver(node, event)}
                @dragleave=${() => this._onDragLeave(node)}
                @drop=${(event: DragEvent) => this._onDrop(node, event)}
            >
                <button
                    class=${expanded ? 'twisty is-open' : 'twisty'}
                    type="button"
                    tabindex="-1"
                    ?hidden=${!hasChildren}
                    aria-hidden=${hasChildren ? 'false' : 'true'}
                    aria-label=${hasChildren ? this.t('tree.expand') : nothing}
                    title=${hasChildren ? this.t('tree.expand') : nothing}
                    data-twisty=${node.id}
                    @click=${(event: Event) => this._toggle(node, event)}
                >
                    <platform-icon name="chevron-right" size="16"></platform-icon>
                </button>
                <span class="icon">
                    ${node.emoji
                        ? node.emoji
                        : html`<platform-icon name=${node.icon ?? 'file'} size="14"></platform-icon>`}
                </span>
                <span class="label" title=${node.label}>${node.label}</span>
                ${typeof node.count === 'number'
                    ? html`<span class="count">${node.count}</span>`
                    : nothing}
                ${typeof this.menuItems === 'function'
                    ? html`<button
                          class="row-menu"
                          type="button"
                          tabindex="-1"
                          data-row-menu=${node.id}
                          aria-haspopup="menu"
                          aria-label=${this.t('tree.row_menu')}
                          title=${this.t('tree.row_menu')}
                          @click=${(event: MouseEvent) => this._openRowMenu(node, event)}
                      >
                          <platform-icon name="more-vert" size="14"></platform-icon>
                      </button>`
                    : nothing}
            </div>
            ${expanded
                ? repeat(
                    this._childrenOf(node.id),
                    (child) => child.id,
                    (child) => this._renderNode(child, depth + 1),
                )
                : nothing}
        `;
    }
}

customElements.define('platform-tree', PlatformTree);

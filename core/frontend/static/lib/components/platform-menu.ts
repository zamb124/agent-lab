/**
 * Меню действий: список пунктов с клавиатурой и доступностью.
 *
 * Отвечает только за навигацию и выбор; за положение на экране отвечает
 * `platform-popover`, внутрь которого меню кладут. Пункты описываются данными,
 * а не разметкой, — так одно и то же меню собирают контекстное меню дерева,
 * slash-команды редактора и меню блока.
 *
 * @example
 * <platform-popover trigger="manual" .anchor=${el} ?open=${open} role="menu">
 *     <platform-menu .items=${items} @menu-select=${onSelect}></platform-menu>
 * </platform-popover>
 */

import { css, html, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { repeat } from 'lit/directives/repeat.js';

import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

export interface PlatformMenuItem {
    id: string;
    /** подпись; для `kind: 'separator'` не нужна */
    label?: string;
    /** имя иконки platform-icon */
    icon?: string;
    /** подпись справа (горячая клавиша или пояснение) */
    hint?: string;
    kind?: 'action' | 'separator' | 'section';
    disabled?: boolean;
    /** красный акцент для разрушающих действий */
    danger?: boolean;
    /** отметка текущего значения */
    selected?: boolean;
}

function menuItemAt(items: readonly PlatformMenuItem[], index: number): PlatformMenuItem {
    const item = items[index];
    if (item === undefined) {
        throw new Error('platform-menu: item missing');
    }
    return item;
}

function selectableAt(indexes: readonly number[], index: number): number {
    const value = indexes[index];
    if (value === undefined) {
        throw new Error('platform-menu: selectable index missing');
    }
    return value;
}

export class PlatformMenu extends PlatformElement {
    static override properties: PropertyDeclarations = {
        items: { type: Array },
        ariaLabel: { type: String, attribute: 'aria-label' },
        compact: { type: Boolean, reflect: true },
        _activeIndex: { state: true },
    };

    declare items: PlatformMenuItem[];
    declare ariaLabel: string;
    declare compact: boolean;
    declare _activeIndex: number;

    _typeahead: string;
    _typeaheadTimer: number | null;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 200px;
                padding: var(--space-1);
            }

            :host([compact]) {
                min-width: 160px;
            }

            .item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            :host([compact]) .item {
                padding: 6px var(--space-2);
            }

            .item:hover:not([disabled]),
            .item.is-active:not([disabled]) {
                background: var(--glass-tint-medium);
            }

            .item[disabled] {
                opacity: 0.45;
                cursor: not-allowed;
            }

            .item.is-danger {
                color: var(--error);
            }

            .item:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: -2px;
            }

            .label {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .hint {
                flex-shrink: 0;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-variant-numeric: tabular-nums;
            }

            .check {
                flex-shrink: 0;
                color: var(--accent);
            }

            .separator {
                height: 1px;
                margin: var(--space-1) var(--space-2);
                background: var(--glass-border-subtle);
            }

            .section {
                padding: var(--space-2) var(--space-3) var(--space-1);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: var(--tracking-wide);
                text-transform: uppercase;
            }

            .empty {
                padding: var(--space-3);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.items = [];
        this.ariaLabel = '';
        this.compact = false;
        this._activeIndex = -1;
        this._typeahead = '';
        this._typeaheadTimer = null;
    }

    /** Индексы пунктов, на которые можно встать: без разделителей и отключённых. */
    get _selectableIndexes(): number[] {
        const indexes: number[] = [];
        for (let index = 0; index < this.items.length; index += 1) {
            const item = menuItemAt(this.items, index);
            const kind = item.kind ?? 'action';
            if (kind === 'action' && item.disabled !== true) {
                indexes.push(index);
            }
        }
        return indexes;
    }

    /** Поставить фокус на первый доступный пункт — вызывается при открытии меню. */
    focusFirstItem(): void {
        const selectable = this._selectableIndexes;
        this._activeIndex = selectable.length > 0 ? selectableAt(selectable, 0) : -1;
        this._focusActive();
    }

    _focusActive(): void {
        void this.updateComplete.then(() => {
            const node = this.renderRoot?.querySelector('.item.is-active');
            if (node instanceof HTMLElement) {
                node.focus();
                node.scrollIntoView({ block: 'nearest' });
            }
        });
    }

    _moveActive(step: number): void {
        const selectable = this._selectableIndexes;
        if (selectable.length === 0) {
            return;
        }
        const current = selectable.indexOf(this._activeIndex);
        const next = current === -1
            ? (step > 0 ? 0 : selectable.length - 1)
            : (current + step + selectable.length) % selectable.length;
        this._activeIndex = selectableAt(selectable, next);
        this._focusActive();
    }

    _onKeyDown(event: KeyboardEvent): void {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            this._moveActive(1);
            return;
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault();
            this._moveActive(-1);
            return;
        }
        if (event.key === 'Home') {
            event.preventDefault();
            const selectable = this._selectableIndexes;
            if (selectable.length > 0) {
                this._activeIndex = selectableAt(selectable, 0);
                this._focusActive();
            }
            return;
        }
        if (event.key === 'End') {
            event.preventDefault();
            const selectable = this._selectableIndexes;
            if (selectable.length > 0) {
                this._activeIndex = selectableAt(selectable, selectable.length - 1);
                this._focusActive();
            }
            return;
        }
        if (event.key === 'Enter' || event.key === ' ') {
            const item = this.items[this._activeIndex];
            if (item) {
                event.preventDefault();
                this._select(item);
            }
            return;
        }
        if (event.key.length === 1 && !event.metaKey && !event.ctrlKey && !event.altKey) {
            this._handleTypeahead(event.key);
        }
    }

    /** Переход к пункту по первым набранным буквам — привычно для меню. */
    _handleTypeahead(char: string): void {
        this._typeahead += char.toLowerCase();
        if (this._typeaheadTimer !== null) {
            clearTimeout(this._typeaheadTimer);
        }
        this._typeaheadTimer = window.setTimeout(() => {
            this._typeahead = '';
            this._typeaheadTimer = null;
        }, 600);

        const match = this._selectableIndexes.find((index) => {
            const itemLabel = menuItemAt(this.items, index).label;
            const label = (itemLabel === undefined ? '' : itemLabel).toLowerCase();
            return label.startsWith(this._typeahead);
        });
        if (match !== undefined) {
            this._activeIndex = match;
            this._focusActive();
        }
    }

    _select(item: PlatformMenuItem): void {
        if (item.disabled === true) {
            return;
        }
        this.emit('menu-select', { id: item.id, item });
    }

    override render(): TemplateResult {
        if (this.items.length === 0) {
            return html`<div class="empty" role="presentation"><slot name="empty"></slot></div>`;
        }

        return html`
            <div
                role="menu"
                aria-label=${this.ariaLabel || nothing}
                @keydown=${this._onKeyDown}
            >
                ${repeat(
                    this.items,
                    (item: PlatformMenuItem, index: number) => item.id ?? `idx-${index}`,
                    (item: PlatformMenuItem, index: number) => this._renderItem(item, index),
                )}
            </div>
        `;
    }

    _renderItem(item: PlatformMenuItem, index: number): TemplateResult {
        const kind = item.kind ?? 'action';
        if (kind === 'separator') {
            return html`<div class="separator" role="separator"></div>`;
        }
        if (kind === 'section') {
            return html`<div class="section" role="presentation">${item.label}</div>`;
        }

        const classes = [
            'item',
            index === this._activeIndex ? 'is-active' : '',
            item.danger === true ? 'is-danger' : '',
        ]
            .filter(Boolean)
            .join(' ');

        return html`
            <button
                type="button"
                class=${classes}
                role="menuitem"
                tabindex=${index === this._activeIndex ? '0' : '-1'}
                ?disabled=${item.disabled === true}
                aria-disabled=${item.disabled === true ? 'true' : 'false'}
                data-menu-item=${item.id}
                @click=${() => this._select(item)}
                @pointerenter=${() => {
                    this._activeIndex = index;
                }}
            >
                ${item.icon
                    ? html`<platform-icon name=${item.icon} size="16"></platform-icon>`
                    : nothing}
                <span class="label">${item.label}</span>
                ${item.hint ? html`<span class="hint">${item.hint}</span>` : nothing}
                ${item.selected === true
                    ? html`<platform-icon class="check" name="check" size="14"></platform-icon>`
                    : nothing}
            </button>
        `;
    }
}

customElements.define('platform-menu', PlatformMenu);

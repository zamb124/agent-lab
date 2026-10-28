/**
 * Командная палитра: поиск и быстрые действия по Cmd/Ctrl+K.
 *
 * Источник результатов задаёт сервис через `provider` — асинхронную функцию
 * запроса. Палитра сама гасит устаревшие ответы: при быстром наборе приходит
 * несколько ответов вразнобой, и без этого список «прыгал» бы назад.
 *
 * @example
 * <platform-command-palette
 *     .provider=${(query) => this._search(query)}
 *     @palette-select=${(e) => this._open(e.detail.item)}
 * ></platform-command-palette>
 */

import { css, html, nothing } from '../lit-shim.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { repeat } from 'lit/directives/repeat.js';

import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

function queryText(event: Event): string {
    const target = event.composedPath()[0];
    if (!(target instanceof HTMLInputElement)) {
        throw new Error('platform-command-palette: query target must be an input');
    }
    return target.value;
}

export interface PaletteItem {
    id: string;
    label: string;
    /** подпись справа */
    hint?: string;
    /** вторая строка */
    description?: string;
    icon?: string;
    /** заголовок секции */
    group?: string;
}

export type PaletteProvider = (query: string) => Promise<PaletteItem[]>;

const SEARCH_DEBOUNCE_MS = 120;

export class PlatformCommandPalette extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        open: { type: Boolean, reflect: true },
        placeholder: { type: String },
        /** `(query: string) => Promise<PaletteItem[]>`; пустой запрос — недавнее. */
        provider: { attribute: false },
        _query: { state: true },
        _items: { state: true },
        _activeIndex: { state: true },
        _loading: { state: true },
    };
    declare open: boolean;
    declare placeholder: string;
    declare provider: PaletteProvider | null;
    declare _query: string;
    declare _items: PaletteItem[];
    declare _activeIndex: number;
    declare _loading: boolean;

    private _searchTimer: number | null;
    private _requestSeq: number;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: none;
            }

            :host([open]) {
                display: block;
                position: fixed;
                inset: 0;
                z-index: var(--z-modal, 1000);
            }

            .scrim {
                position: absolute;
                inset: 0;
                background: var(--glass-scrim, rgba(0, 0, 0, 0.4));
                backdrop-filter: blur(2px);
            }

            .panel {
                position: relative;
                width: min(640px, calc(100vw - 32px));
                max-height: min(60vh, 520px);
                margin: 12vh auto 0;
                display: flex;
                flex-direction: column;
                border-radius: var(--radius-xl, 16px);
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-strong);
                box-shadow: var(--glass-shadow-strong);
                overflow: hidden;
            }

            .search {
                display: flex;
                align-items: center;
                gap: var(--space-2, 8px);
                padding: var(--space-3, 12px) var(--space-4, 16px);
                border-bottom: 1px solid var(--glass-border-subtle);
                color: var(--text-tertiary, #9aa0a6);
            }

            .search input {
                flex: 1;
                min-width: 0;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-base, 1rem);
                outline: none;
            }

            .results {
                flex: 1;
                overflow-y: auto;
                padding: var(--space-1, 4px);
            }

            .group {
                padding: var(--space-2, 8px) var(--space-3, 12px) var(--space-1, 4px);
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-xs, 0.75rem);
                font-weight: var(--font-semibold, 600);
                text-transform: uppercase;
                letter-spacing: var(--tracking-wide, 0.04em);
            }

            .item {
                display: flex;
                align-items: center;
                gap: var(--space-3, 12px);
                width: 100%;
                box-sizing: border-box;
                padding: var(--space-2, 8px) var(--space-3, 12px);
                border: none;
                border-radius: var(--radius-sm, 8px);
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm, 0.8125rem);
                text-align: left;
                cursor: pointer;
            }

            .item.is-active {
                background: var(--glass-tint-medium, rgba(120, 120, 140, 0.16));
            }

            .item-body {
                flex: 1;
                min-width: 0;
            }

            .item-label {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .item-description {
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-xs, 0.75rem);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .item-hint {
                flex-shrink: 0;
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-xs, 0.75rem);
            }

            .status {
                padding: var(--space-5, 20px);
                text-align: center;
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-sm, 0.8125rem);
            }
        `,
    ];

    constructor() {
        super();
        this.open = false;
        this.placeholder = '';
        this.provider = null;
        this._query = '';
        this._items = [];
        this._activeIndex = 0;
        this._loading = false;
        this._searchTimer = null;
        this._requestSeq = 0;
        this._onGlobalKeyDown = this._onGlobalKeyDown.bind(this);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        document.addEventListener('keydown', this._onGlobalKeyDown);
    }

    override disconnectedCallback(): void {
        super.disconnectedCallback();
        document.removeEventListener('keydown', this._onGlobalKeyDown);
        this._clearSearchTimer();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (changed.has('open') && this.open) {
            this._query = '';
            this._activeIndex = 0;
            void this._runSearch('');
            void this.updateComplete.then(() => {
                this.renderRoot?.querySelector('input')?.focus();
            });
        }
    }

    show() {
        this.open = true;
    }

    hide() {
        this.open = false;
        this.emit('palette-close');
    }

    _onGlobalKeyDown(event: KeyboardEvent) {
        const isPaletteShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
        if (isPaletteShortcut) {
            event.preventDefault();
            if (this.open) {
                this.hide();
            } else {
                this.show();
            }
            return;
        }
        if (event.key === 'Escape' && this.open) {
            event.preventDefault();
            this.hide();
        }
    }

    _clearSearchTimer() {
        if (this._searchTimer !== null) {
            clearTimeout(this._searchTimer);
            this._searchTimer = null;
        }
    }

    async _runSearch(query: string): Promise<void> {
        if (typeof this.provider !== 'function') {
            throw new Error('platform-command-palette: не задан provider');
        }
        this._requestSeq += 1;
        const seq = this._requestSeq;
        this._loading = true;
        const items = await this.provider(query);
        // Ответ на устаревший запрос игнорируется: иначе поздний ответ на
        // короткий префикс затрёт результаты уже набранного запроса.
        if (seq !== this._requestSeq) {
            return;
        }
        this._items = Array.isArray(items) ? items : [];
        this._activeIndex = 0;
        this._loading = false;
    }

    _onInput(event: Event) {
        this._query = queryText(event);
        this._clearSearchTimer();
        this._searchTimer = window.setTimeout(() => {
            this._searchTimer = null;
            void this._runSearch(this._query);
        }, SEARCH_DEBOUNCE_MS);
    }

    _onKeyDown(event: KeyboardEvent) {
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            this._activeIndex = this._items.length === 0
                ? 0
                : (this._activeIndex + 1) % this._items.length;
            this._scrollActiveIntoView();
            return;
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault();
            this._activeIndex = this._items.length === 0
                ? 0
                : (this._activeIndex - 1 + this._items.length) % this._items.length;
            this._scrollActiveIntoView();
            return;
        }
        if (event.key === 'Enter') {
            event.preventDefault();
            const item = this._items[this._activeIndex];
            if (item) {
                this._select(item);
            }
        }
    }

    _scrollActiveIntoView() {
        void this.updateComplete.then(() => {
            const active = this.renderRoot.querySelector('.item.is-active');
            if (active instanceof HTMLElement) {
                active.scrollIntoView({ block: 'nearest' });
            }
        });
    }

    _select(item: PaletteItem): void {
        this.emit('palette-select', { id: item.id, item });
        this.hide();
    }

    _onScrimClick() {
        this.hide();
    }

    override render(): TemplateResult | typeof nothing {
        if (!this.open) {
            return nothing;
        }
        return html`
            <div class="scrim" @click=${this._onScrimClick}></div>
            <div class="panel" role="dialog" aria-modal="true">
                <div class="search">
                    <platform-icon name="search" size="16"></platform-icon>
                    <input
                        type="text"
                        data-canon="search-as-you-type"
                        spellcheck="false"
                        autocomplete="off"
                        role="combobox"
                        aria-expanded="true"
                        aria-controls="palette-results"
                        placeholder=${this.placeholder || this.t('command_palette.placeholder')}
                        .value=${this._query}
                        @input=${this._onInput}
                        @keydown=${this._onKeyDown}
                    />
                </div>
                <div class="results" id="palette-results" role="listbox">
                    ${this._renderResults()}
                </div>
            </div>
        `;
    }

    _renderResults() {
        if (this._items.length === 0) {
            return html`<div class="status">
                ${this._loading
                    ? this.t('command_palette.loading')
                    : this.t('command_palette.empty')}
            </div>`;
        }

        let lastGroup: string | null = null;
        return repeat(
            this._items,
            (item: PaletteItem) => item.id,
            (item: PaletteItem, index: number) => {
                const group = typeof item.group === 'string' ? item.group : null;
                const showGroup = group !== null && group !== lastGroup;
                lastGroup = group;
                return html`
                    ${showGroup ? html`<div class="group">${group}</div>` : nothing}
                    <button
                        type="button"
                        class=${index === this._activeIndex ? 'item is-active' : 'item'}
                        role="option"
                        aria-selected=${index === this._activeIndex ? 'true' : 'false'}
                        data-palette-item=${item.id}
                        @click=${() => this._select(item)}
                        @pointerenter=${() => { this._activeIndex = index; }}
                    >
                        ${item.icon
                            ? html`<platform-icon name=${item.icon} size="16"></platform-icon>`
                            : nothing}
                        <span class="item-body">
                            <span class="item-label">${item.label}</span>
                            ${item.description
                                ? html`<span class="item-description">${item.description}</span>`
                                : nothing}
                        </span>
                        ${item.hint ? html`<span class="item-hint">${item.hint}</span>` : nothing}
                    </button>
                `;
            },
        );
    }
}

customElements.define('platform-command-palette', PlatformCommandPalette);

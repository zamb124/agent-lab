/**
 * Поиск по базе знаний: по тексту страниц или по смыслу.
 *
 * Два канала разведены явным переключателем, а не «умным» режимом: текстовый
 * поиск находит точные формулировки, смысловой — близкие по значению
 * страницы, и пользователь сам выбирает, что ему нужно сейчас.
 */

import { html, css } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import type { OpController } from '@platform/lib/base/use-resource.js';

interface WikiSearchHit {
    wiki_page_id?: unknown;
    title?: unknown;
    snippet?: unknown;
    [key: string]: unknown;
}
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-segmented-control.js';

const MODE_LEXICAL = 'lexical';
const MODE_SEMANTIC = 'semantic';
const SEARCH_DEBOUNCE_MS = 250;
const RESULT_LIMIT = 30;

export class WikiSearchPage extends PlatformPage {
    static i18nNamespace = 'wiki';

    declare _query: string;
    declare _mode: string;
    declare _items: WikiSearchHit[];
    private _timer: number | null;
    private _seq: number;
    private _search: OpController;

    static override properties = {
        _query: { state: true },
        _mode: { state: true },
        _items: { state: true },
    };

    static override styles = [
        PlatformPage.styles,
        css`
            :host {
                display: block;
                height: 100%;
                overflow-y: auto;
            }

            .wrap {
                max-width: var(--wiki-page-max-width);
                margin: 0 auto;
                padding: var(--space-8) var(--space-6);
            }

            .title {
                margin: 0 0 var(--space-4);
                font-size: var(--text-2xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
            }

            .search-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--wiki-surface-muted);
                color: var(--text-tertiary);
            }

            .search-row input {
                flex: 1;
                min-width: 0;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-base);
                outline: none;
            }

            platform-segmented-control {
                margin: var(--space-3) 0 var(--space-4);
            }

            .count {
                margin-bottom: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }

            .hit {
                display: block;
                width: 100%;
                padding: var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                text-align: left;
                cursor: pointer;
            }

            .hit:hover {
                background: var(--wiki-surface-muted);
            }

            .hit-title {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
            }

            .hit-snippet {
                margin-top: 2px;
                color: var(--text-secondary);
                font-size: var(--text-xs);
                overflow-wrap: anywhere;
            }

            .state {
                padding: var(--space-8);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this._query = '';
        this._mode = MODE_LEXICAL;
        this._items = [];
        this._timer = null;
        this._seq = 0;
        this._search = this.useOp('wiki/search');
    }

    override disconnectedCallback() {
        super.disconnectedCallback();
        if (this._timer !== null) {
            clearTimeout(this._timer);
            this._timer = null;
        }
    }

    private _onInput(event: Event) {
        this._query = (event.target as HTMLInputElement).value;
        this._schedule();
    }

    private _onModeChange(event: CustomEvent<{ value?: unknown }>) {
        this._mode = String(event.detail.value ?? '');
        this._schedule();
    }

    private _schedule() {
        if (this._timer !== null) {
            clearTimeout(this._timer);
        }
        this._timer = window.setTimeout(() => {
            this._timer = null;
            void this._run();
        }, SEARCH_DEBOUNCE_MS);
    }

    private async _run(): Promise<void> {
        const query = this._query.trim();
        if (query === '') {
            this._items = [];
            return;
        }
        this._seq += 1;
        const seq = this._seq;
        const result = await this._search.run({ query, mode: this._mode, limit: RESULT_LIMIT }) as { items?: unknown } | null;
        // Ответ на прошлый префикс не должен подменять текущую выдачу.
        if (seq !== this._seq) {
            return;
        }
        if (result === null) {
            this._items = [];
            return;
        }
        if (typeof result !== 'object' || !Array.isArray(result.items)) {
            throw new Error('wiki search: result.items required');
        }
        this._items = result.items as WikiSearchHit[];
    }

    private _modeOptions() {
        return [
            { value: MODE_LEXICAL, label: this.t('search.mode_lexical') },
            { value: MODE_SEMANTIC, label: this.t('search.mode_semantic') },
        ];
    }

    override render() {
        return html`
            <div class="wrap">
                <h1 class="title">${this.t('search.title')}</h1>
                <div class="search-row">
                    <platform-icon name="search" size="18"></platform-icon>
                    <input
                        type="text"
                        data-canon="search-as-you-type"
                        data-wiki-search-input
                        spellcheck="false"
                        autocomplete="off"
                        aria-label=${this.t('search.placeholder')}
                        placeholder=${this.t('search.placeholder')}
                        .value=${this._query}
                        @input=${(event: Event) => this._onInput(event)}
                    />
                </div>
                <platform-segmented-control
                    density="compact"
                    .value=${this._mode}
                    .options=${this._modeOptions()}
                    @change=${(event: CustomEvent<{ value?: unknown }>) => this._onModeChange(event)}
                ></platform-segmented-control>

                ${this._renderResults()}
            </div>
        `;
    }

    private _renderResults() {
        if (this._query.trim() === '') {
            return html`<div class="state">${this.t('search.hint')}</div>`;
        }
        if (this._search.busy && this._items.length === 0) {
            return html`<div class="state"><glass-spinner size="sm"></glass-spinner></div>`;
        }
        if (this._items.length === 0) {
            return html`<div class="state">${this.t('search.empty')}</div>`;
        }
        return html`
            <div class="count">${this.t('search.results_count', { count: this._items.length })}</div>
            ${this._items.map((hit) => html`
                <button
                    class="hit"
                    type="button"
                    data-wiki-hit=${hit.wiki_page_id}
                    @click=${() => this.navigate('wiki_page', { pageId: String(hit.wiki_page_id ?? '') })}
                >
                    <div class="hit-title">${hit.title === '' ? this.t('page.untitled') : hit.title}</div>
                    ${hit.snippet === '' ? '' : html`<div class="hit-snippet">${hit.snippet}</div>`}
                </button>
            `)}
        `;
    }
}

customElements.define('wiki-search-page', WikiSearchPage);

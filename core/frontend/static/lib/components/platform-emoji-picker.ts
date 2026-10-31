/**
 * Выбор эмодзи для иконки страницы или сущности.
 *
 * Набор — не полный Unicode: он раздул бы бандл и утомил бы выбором. Здесь
 * подобраны категории, которыми реально помечают рабочие документы, с поиском
 * по ключевым словам на русском и английском.
 *
 * @example
 * <platform-emoji-picker value="📄"
 *     @emoji-select=${(e) => this._setIcon(e.detail.emoji)}
 *     @emoji-clear=${() => this._setIcon('')}
 * ></platform-emoji-picker>
 */

import { css, html, nothing } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';

import { PlatformElement } from '../platform-element/index.js';
import './platform-icon.js';

/**
 * @typedef {object} EmojiEntry
 * @property {string} emoji
 * @property {string[]} keywords ключевые слова для поиска (ru + en)
 */

/** @type {ReadonlyArray<{ id: string, items: EmojiEntry[] }>} */
export const EMOJI_CATEGORIES = Object.freeze([
    {
        id: 'documents',
        items: [
            { emoji: '📄', keywords: ['документ', 'страница', 'page', 'doc'] },
            { emoji: '📝', keywords: ['заметка', 'note', 'написать', 'write'] },
            { emoji: '📋', keywords: ['список', 'буфер', 'clipboard', 'list'] },
            { emoji: '📊', keywords: ['график', 'отчёт', 'chart', 'report'] },
            { emoji: '📈', keywords: ['рост', 'метрика', 'growth', 'metrics'] },
            { emoji: '📚', keywords: ['книги', 'база знаний', 'books', 'knowledge'] },
            { emoji: '🗂', keywords: ['каталог', 'папка', 'folder', 'archive'] },
            { emoji: '📎', keywords: ['вложение', 'скрепка', 'attachment', 'clip'] },
        ],
    },
    {
        id: 'work',
        items: [
            { emoji: '🚀', keywords: ['запуск', 'релиз', 'launch', 'release'] },
            { emoji: '🎯', keywords: ['цель', 'задача', 'goal', 'target'] },
            { emoji: '🛠', keywords: ['инструменты', 'настройка', 'tools', 'setup'] },
            { emoji: '⚙️', keywords: ['настройки', 'система', 'settings', 'system'] },
            { emoji: '🧩', keywords: ['модуль', 'интеграция', 'module', 'plugin'] },
            { emoji: '🔐', keywords: ['доступ', 'безопасность', 'security', 'access'] },
            { emoji: '🐞', keywords: ['баг', 'ошибка', 'bug', 'issue'] },
            { emoji: '✅', keywords: ['готово', 'сделано', 'done', 'ok'] },
        ],
    },
    {
        id: 'people',
        items: [
            { emoji: '👥', keywords: ['команда', 'люди', 'team', 'people'] },
            { emoji: '🧑‍💻', keywords: ['разработчик', 'инженер', 'developer', 'engineer'] },
            { emoji: '🤝', keywords: ['встреча', 'договор', 'meeting', 'deal'] },
            { emoji: '💬', keywords: ['обсуждение', 'чат', 'discussion', 'chat'] },
            { emoji: '📣', keywords: ['анонс', 'объявление', 'announcement', 'news'] },
            { emoji: '🎓', keywords: ['обучение', 'онбординг', 'learning', 'onboarding'] },
        ],
    },
    {
        id: 'signals',
        items: [
            { emoji: '⭐️', keywords: ['избранное', 'важное', 'favorite', 'star'] },
            { emoji: '🔥', keywords: ['срочно', 'горячее', 'urgent', 'hot'] },
            { emoji: '💡', keywords: ['идея', 'предложение', 'idea', 'proposal'] },
            { emoji: '⚠️', keywords: ['внимание', 'риск', 'warning', 'risk'] },
            { emoji: '🧪', keywords: ['эксперимент', 'тест', 'experiment', 'test'] },
            { emoji: '🕒', keywords: ['время', 'история', 'time', 'history'] },
            { emoji: '🌍', keywords: ['публичное', 'мир', 'public', 'global'] },
            { emoji: '🏷', keywords: ['метка', 'тег', 'tag', 'label'] },
        ],
    },
]);

export class PlatformEmojiPicker extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        value: { type: String },
        _query: { state: true },
    };
    declare value: string;
    declare _query: string;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: min(320px, 90vw);
            }

            .search {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                border-bottom: 1px solid var(--glass-border-subtle);
                color: var(--text-tertiary);
            }

            .search input {
                flex: 1;
                min-width: 0;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-family: inherit;
                font-size: var(--text-sm);
                outline: none;
            }

            .clear {
                border: none;
                background: transparent;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                cursor: pointer;
            }

            .clear:hover {
                color: var(--text-primary);
            }

            .body {
                max-height: 260px;
                overflow-y: auto;
                padding: var(--space-2);
            }

            .group-title {
                padding: var(--space-1) var(--space-1) var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: var(--tracking-wide);
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(8, 1fr);
                gap: 2px;
                margin-bottom: var(--space-2);
            }

            .cell {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                aspect-ratio: 1;
                border: none;
                border-radius: var(--radius-sm);
                background: transparent;
                font-size: 18px;
                line-height: 1;
                cursor: pointer;
            }

            .cell:hover {
                background: var(--glass-tint-medium);
            }

            .cell.is-selected {
                background: var(--accent-subtle);
                box-shadow: inset 0 0 0 1px var(--accent);
            }

            .empty {
                padding: var(--space-4);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this._query = '';
    }

    _onInput(event: Event) {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) {
            throw new Error('platform-emoji-picker: input target must be an input');
        }
        this._query = target.value;
    }

    _select(emoji: string): void {
        this.value = emoji;
        this.emit('emoji-select', { emoji });
    }

    _clear() {
        this.value = '';
        this.emit('emoji-clear');
    }

    /** Отфильтрованные категории; пустые из выдачи убираются. */
    _visibleCategories() {
        const query = this._query.trim().toLowerCase();
        if (query === '') {
            return EMOJI_CATEGORIES.map((category) => ({ id: category.id, items: category.items }));
        }
        const result = [];
        for (const category of EMOJI_CATEGORIES) {
            const items = category.items.filter(
                (entry) =>
                    entry.emoji === query
                    || entry.keywords.some((keyword) => keyword.includes(query)),
            );
            if (items.length > 0) {
                result.push({ id: category.id, items });
            }
        }
        return result;
    }

    override render(): TemplateResult {
        const categories = this._visibleCategories();
        return html`
            <div class="search">
                <platform-icon name="search" size="14"></platform-icon>
                <input
                    type="text"
                    data-canon="search-as-you-type"
                    spellcheck="false"
                    autocomplete="off"
                    aria-label=${this.t('emoji_picker.search_aria')}
                    placeholder=${this.t('emoji_picker.search_placeholder')}
                    .value=${this._query}
                    @input=${this._onInput}
                />
                ${this.value !== ''
                    ? html`<button type="button" class="clear" data-emoji-clear @click=${this._clear}>
                          ${this.t('emoji_picker.clear')}
                      </button>`
                    : nothing}
            </div>
            <div class="body">
                ${categories.length === 0
                    ? html`<div class="empty">${this.t('emoji_picker.empty')}</div>`
                    : categories.map((category) => html`
                          <div class="group-title">${this.t(`emoji_picker.category.${category.id}`)}</div>
                          <div class="grid" role="listbox">
                              ${category.items.map((entry) => html`
                                  <button
                                      type="button"
                                      class=${entry.emoji === this.value ? 'cell is-selected' : 'cell'}
                                      role="option"
                                      aria-selected=${entry.emoji === this.value ? 'true' : 'false'}
                                      data-emoji=${entry.emoji}
                                      title=${entry.keywords[0]}
                                      @click=${() => this._select(entry.emoji)}
                                  >${entry.emoji}</button>
                              `)}
                          </div>
                      `)}
            </div>
        `;
    }
}

customElements.define('platform-emoji-picker', PlatformEmojiPicker);

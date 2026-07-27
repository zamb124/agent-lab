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

import { css, html, nothing } from '../lit-shim.js';

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

    static properties = {
        value: { type: String },
        _query: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: min(320px, 90vw);
            }

            .search {
                display: flex;
                align-items: center;
                gap: var(--space-2, 8px);
                padding: var(--space-2, 8px) var(--space-3, 12px);
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
                font-size: var(--text-sm, 0.8125rem);
                outline: none;
            }

            .clear {
                border: none;
                background: transparent;
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-xs, 0.75rem);
                cursor: pointer;
            }

            .clear:hover {
                color: var(--text-primary);
            }

            .body {
                max-height: 260px;
                overflow-y: auto;
                padding: var(--space-2, 8px);
            }

            .group-title {
                padding: var(--space-1, 4px) var(--space-1, 4px) var(--space-2, 8px);
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-xs, 0.75rem);
                font-weight: var(--font-semibold, 600);
                text-transform: uppercase;
                letter-spacing: var(--tracking-wide, 0.04em);
            }

            .grid {
                display: grid;
                grid-template-columns: repeat(8, 1fr);
                gap: 2px;
                margin-bottom: var(--space-2, 8px);
            }

            .cell {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                aspect-ratio: 1;
                border: none;
                border-radius: var(--radius-sm, 8px);
                background: transparent;
                font-size: 18px;
                line-height: 1;
                cursor: pointer;
            }

            .cell:hover {
                background: var(--glass-tint-medium, rgba(120, 120, 140, 0.16));
            }

            .cell.is-selected {
                background: var(--accent-subtle, rgba(99, 102, 241, 0.18));
                box-shadow: inset 0 0 0 1px var(--accent);
            }

            .empty {
                padding: var(--space-4, 16px);
                text-align: center;
                color: var(--text-tertiary, #9aa0a6);
                font-size: var(--text-sm, 0.8125rem);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '';
        this._query = '';
    }

    _onInput(event) {
        this._query = event.target.value;
    }

    _select(emoji) {
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

    render() {
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

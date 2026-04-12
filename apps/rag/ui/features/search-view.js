/**
 * Search View - поиск по документам
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { RagStore } from '../store/rag.store.js';
import '@platform/lib/components/layout/page-header.js';

export class SearchView extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        buttonStyles,
        formStyles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
            }

            .search-form {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
                margin-bottom: var(--space-6);
            }

            .form-row {
                display: flex;
                gap: var(--space-3);
                flex-wrap: wrap;
            }

            .search-input-wrapper {
                position: relative;
            }

            .search-input {
                width: 100%;
                padding-right: 100px;
            }

            .search-btn {
                position: absolute;
                right: 4px;
                top: 4px;
                bottom: 4px;
            }

            .param-help {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: var(--space-1);
                line-height: 1.45;
            }

            details.search-advanced {
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                padding: var(--space-3) var(--space-4);
                background: var(--glass-solid-subtle);
            }

            details.search-advanced summary {
                cursor: pointer;
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }

            .results {
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }

            .result-card {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: all var(--duration-fast);
            }

            .result-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }

            .result-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                margin-bottom: var(--space-3);
            }

            .result-title {
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-1);
            }

            .result-meta {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }

            .result-score {
                padding: var(--space-1) var(--space-2);
                background: var(--accent-subtle);
                color: var(--accent);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }

            .result-content {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.6;
            }

            .empty {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                padding: var(--space-12);
                text-align: center;
            }

            .empty-icon {
                width: 80px;
                height: 80px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: var(--space-4);
                opacity: 0.3;
                color: var(--text-tertiary);
            }

            .empty-text {
                font-size: var(--text-lg);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                margin-bottom: var(--space-2);
            }

            .empty-hint {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }

            textarea.form-input {
                min-height: 4.5rem;
                font-family: var(--font-mono, ui-monospace, monospace);
                font-size: var(--text-xs);
            }

            .loading-spinner {
                width: 48px;
                height: 48px;
                border: 4px solid var(--glass-border-subtle);
                border-top: 4px solid var(--accent);
                border-radius: 50%;
                animation: rag-search-spin 1s linear infinite;
            }

            .namespace-picker {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                max-height: 12rem;
                overflow-y: auto;
                padding: var(--space-2);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
            }

            .namespace-picker-actions {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-2);
                margin-bottom: var(--space-1);
            }

            .namespace-picker .form-check {
                margin: 0;
            }

            @keyframes rag-search-spin {
                0% {
                    transform: rotate(0deg);
                }
                100% {
                    transform: rotate(360deg);
                }
            }
        `,
    ];

    constructor() {
        super();
        this._query = '';
        /** @type {string[]} */
        this._selectedNamespaceIds = [];
        this._limit = 10;
        this._chSemantic = true;
        this._chLexical = true;
        this._rerank = true;
        this._rrfK = '';
        this._perChannelTopK = '';
        this._filtersJson = '';

        this.state = this.use((s) => ({
            namespaces: s.namespaces.list,
            searchResults: s.search.results,
            loading: s.loading,
        }));
    }

    _buildSearchOptions() {
        const opts = {
            channels: {
                semantic: Boolean(this._chSemantic),
                lexical: Boolean(this._chLexical),
            },
            rerank: Boolean(this._rerank),
        };
        const rrf = parseInt(String(this._rrfK).trim(), 10);
        if (!Number.isNaN(rrf) && rrf > 0) {
            opts.rrf_k = rrf;
        }
        const pct = parseInt(String(this._perChannelTopK).trim(), 10);
        if (!Number.isNaN(pct) && pct > 0) {
            opts.per_channel_top_k = pct;
        }
        const raw = String(this._filtersJson || '').trim();
        if (raw) {
            opts.filters = JSON.parse(raw);
        }
        return opts;
    }

    async _handleSearch(e) {
        e.preventDefault();

        if (!this._query || this._selectedNamespaceIds.length === 0) {
            this.warning('Выберите хотя бы один namespace и введите запрос');
            return;
        }
        if (!this._chSemantic && !this._chLexical) {
            this.warning('Включите хотя бы один канал: semantic или lexical');
            return;
        }

        let options;
        try {
            options = this._buildSearchOptions();
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.error(`Фильтры JSON: ${message}`);
            return;
        }

        const ragApi = this.services.get('ragApi');
        await RagStore.searchInNamespaces(
            ragApi,
            this._selectedNamespaceIds,
            this._query,
            this._limit,
            options,
        );
    }

    _handleQueryChange(e) {
        this._query = e.target.value;
        this.requestUpdate();
    }

    _namespaceId(ns) {
        return String(ns.namespace_id ?? ns.name ?? '');
    }

    _handleNamespaceToggle(e, nsId) {
        const checked = Boolean(e.target.checked);
        const set = new Set(this._selectedNamespaceIds);
        if (checked) {
            set.add(nsId);
        } else {
            set.delete(nsId);
        }
        this._selectedNamespaceIds = [...set];
        this.requestUpdate();
    }

    _selectAllNamespaces() {
        const { namespaces } = this.state.value;
        this._selectedNamespaceIds = namespaces.map((ns) => this._namespaceId(ns)).filter(Boolean);
        this.requestUpdate();
    }

    _clearNamespaceSelection() {
        this._selectedNamespaceIds = [];
        this.requestUpdate();
    }

    _handleLimitChange(e) {
        this._limit = parseInt(e.target.value, 10);
        this.requestUpdate();
    }

    _handleChSemanticChange(e) {
        this._chSemantic = Boolean(e.target.checked);
        this.requestUpdate();
    }

    _handleChLexicalChange(e) {
        this._chLexical = Boolean(e.target.checked);
        this.requestUpdate();
    }

    _handleRerankChange(e) {
        this._rerank = Boolean(e.target.checked);
        this.requestUpdate();
    }

    _handleRrfKChange(e) {
        this._rrfK = e.target.value;
        this.requestUpdate();
    }

    _handlePerChannelTopKChange(e) {
        this._perChannelTopK = e.target.value;
        this.requestUpdate();
    }

    _handleFiltersJsonChange(e) {
        this._filtersJson = e.target.value;
        this.requestUpdate();
    }

    async connectedCallback() {
        super.connectedCallback();
        const ragApi = this.services.get('ragApi');
        if (!ragApi) {
            return;
        }
        try {
            await RagStore.loadNamespaces(ragApi, { silent: true });
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.error(message);
        }
    }

    render() {
        const { namespaces, searchResults, loading } = this.state.value;

        return html`
            <page-header
                title="Поиск"
                subtitle="Каналы semantic и lexical задают режим: оба включены — RRF по рангам; только semantic — вектор; только lexical — полнотекст. Реранк по умолчанию включён."
            ></page-header>

            <form class="search-form" @submit=${this._handleSearch}>
                <div class="form-row">
                    <div class="form-group" style="flex: 1; min-width: 220px;">
                        <label class="form-label">Namespaces</label>
                        <div class="namespace-picker-actions">
                            <button
                                type="button"
                                class="btn btn-secondary"
                                style="padding: var(--space-2) var(--space-4); font-size: var(--text-sm);"
                                @click=${this._selectAllNamespaces}
                            >
                                Все
                            </button>
                            <button
                                type="button"
                                class="btn btn-secondary"
                                style="padding: var(--space-2) var(--space-4); font-size: var(--text-sm);"
                                @click=${this._clearNamespaceSelection}
                            >
                                Снять
                            </button>
                        </div>
                        <div class="namespace-picker" role="group" aria-label="Выбор namespace">
                            ${namespaces.length === 0
                                ? html`<span class="param-help">Нет доступных namespace</span>`
                                : namespaces.map((ns) => {
                                      const id = this._namespaceId(ns);
                                      if (!id) {
                                          return null;
                                      }
                                      const checked = this._selectedNamespaceIds.includes(id);
                                      return html`
                                          <label class="form-check">
                                              <input
                                                  type="checkbox"
                                                  .checked=${checked}
                                                  @change=${(e) => this._handleNamespaceToggle(e, id)}
                                              />
                                              <span>${ns.name}</span>
                                          </label>
                                      `;
                                  })}
                        </div>
                        <p class="param-help">
                            Поиск по выбранным областям индекса. Несколько — объединение результатов
                            (реранк по всем кандидатам), итог обрезается до limit.
                        </p>
                    </div>
                    <div class="form-group" style="max-width: 160px;">
                        <label class="form-label">limit</label>
                        <select
                            class="form-select"
                            @change=${this._handleLimitChange}
                            .value=${String(this._limit)}
                        >
                            <option value="3">3</option>
                            <option value="5">5</option>
                            <option value="10">10</option>
                            <option value="20">20</option>
                            <option value="50">50</option>
                        </select>
                        <p class="param-help">Сколько чанков вернуть после слияния каналов и реранка.</p>
                    </div>
                </div>

                <div class="form-row" style="max-width: 36rem;">
                    <label class="form-check" style="display: flex; align-items: flex-start; gap: var(--space-2);">
                        <input
                            type="checkbox"
                            .checked=${this._chSemantic}
                            @change=${this._handleChSemanticChange}
                        />
                        <span>
                            Канал <strong>semantic</strong> (векторный поиск)
                            <span class="param-help" style="display: block; margin-top: var(--space-1);"
                                >Поиск по embedding. Вместе с lexical даёт слияние рангов (RRF).</span
                            >
                        </span>
                    </label>
                    <label class="form-check" style="display: flex; align-items: flex-start; gap: var(--space-2);">
                        <input
                            type="checkbox"
                            .checked=${this._chLexical}
                            @change=${this._handleChLexicalChange}
                        />
                        <span>
                            Канал <strong>lexical</strong> (полнотекст / BM25 по чанкам)
                            <span class="param-help" style="display: block; margin-top: var(--space-1);"
                                >Совпадения по словам; вместе с semantic — RRF между каналами.</span
                            >
                        </span>
                    </label>
                </div>

                <div class="form-group" style="max-width: 36rem;">
                    <label class="form-check" style="display: flex; align-items: flex-start; gap: var(--space-2);">
                        <input type="checkbox" .checked=${this._rerank} @change=${this._handleRerankChange} />
                        <span>
                            <strong>rerank</strong> — второй проход HTTP-реранкером по кандидатам
                            <span class="param-help" style="display: block; margin-top: var(--space-1);"
                                >По умолчанию включено. Требует настроенный URL реранкера (rag.reranker /
                                provider_litserve). Только для провайдера pgvector.</span
                            >
                        </span>
                    </label>
                </div>

                <details class="search-advanced">
                    <summary>Дополнительные параметры RRF и фильтры</summary>
                    <div style="margin-top: var(--space-4); display: flex; flex-direction: column; gap: var(--space-4);">
                        <div class="form-group" style="max-width: 16rem;">
                            <label class="form-label">rrf_k</label>
                            <input
                                class="form-input"
                                type="text"
                                inputmode="numeric"
                                placeholder="пусто = из rag.document_indexing"
                                .value=${this._rrfK}
                                @input=${this._handleRrfKChange}
                            />
                            <p class="param-help">
                                Константа k в формуле RRF: 1 / (k + rank). Чем больше k, тем ровнее веса
                                нижних позиций. Пустое поле — дефолт из профиля индексации.
                            </p>
                        </div>
                        <div class="form-group" style="max-width: 16rem;">
                            <label class="form-label">per_channel_top_k</label>
                            <input
                                class="form-input"
                                type="text"
                                inputmode="numeric"
                                placeholder="пусто = из профиля"
                                .value=${this._perChannelTopK}
                                @input=${this._handlePerChannelTopKChange}
                            />
                            <p class="param-help">
                                Сколько кандидатов брать из каждого канала до слияния RRF. Пустое — из
                                rag.document_indexing.search_defaults.
                            </p>
                        </div>
                        <div class="form-group">
                            <label class="form-label">filters (JSON)</label>
                            <textarea
                                class="form-input"
                                placeholder='{}'
                                .value=${this._filtersJson}
                                @input=${this._handleFiltersJsonChange}
                            ></textarea>
                            <p class="param-help">
                                Произвольные фильтры по метаданным чанков (формат зависит от провайдера).
                                Оставьте пустым, если фильтры не нужны.
                            </p>
                        </div>
                    </div>
                </details>

                <div class="form-group">
                    <label class="form-label">Запрос</label>
                    <div class="search-input-wrapper">
                        <input
                            class="form-input search-input"
                            type="text"
                            placeholder="Текст запроса..."
                            .value=${this._query}
                            @input=${this._handleQueryChange}
                        />
                        <button type="submit" class="btn btn-primary search-btn" ?disabled=${loading}>
                            ${loading ? 'Поиск...' : 'Найти'}
                        </button>
                    </div>
                </div>
            </form>

            ${searchResults.length > 0
                ? html`
                      <div class="results">
                          ${searchResults.map(
                              (result) => html`
                                  <div class="result-card">
                                      <div class="result-header">
                                          <div>
                                              <div class="result-title">
                                                  ${result.document_name || 'Документ'}
                                              </div>
                                              <div class="result-meta">
                                                  ${result.namespace
                                                      ? html`<span>${result.namespace}</span>`
                                                      : ''}
                                                  ${result.chunk_id
                                                      ? html`<span>chunk: ${result.chunk_id}</span>`
                                                      : ''}
                                                  ${result.metadata?.page != null
                                                      ? html`<span>стр. ${result.metadata.page}</span>`
                                                      : ''}
                                              </div>
                                          </div>
                                          <div class="result-score">
                                              ${(Number(result.score) * 100).toFixed(1)}%
                                          </div>
                                      </div>
                                      <div class="result-content">${result.content}</div>
                                  </div>
                              `,
                          )}
                      </div>
                  `
                : !loading
                  ? html`
                        <div class="empty">
                            <div class="empty-icon">
                                <platform-icon name="eye" size="64"></platform-icon>
                            </div>
                            <div class="empty-text">Нет результатов</div>
                            <div class="empty-hint">Введите запрос и нажмите «Найти»</div>
                        </div>
                    `
                  : html`
                        <div class="empty">
                            <div class="loading-spinner"></div>
                            <div class="loading-text">Поиск...</div>
                        </div>
                    `}
        `;
    }
}

customElements.define('search-view', SearchView);

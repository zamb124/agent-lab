/**
 * office-catalog-semantic-search-results — Google-like SERP for catalog semantic search.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class OfficeCatalogSemanticSearchResults extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        items: { type: Array },
        loading: { type: Boolean },
        query: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        buttonStyles,
        css`
            :host {
                display: block;
            }
            .results {
                display: flex;
                flex-direction: column;
                gap: var(--space-4);
            }
            .result-card {
                padding: var(--space-4);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-lg);
                transition: var(--motion-transition-interactive);
            }
            .result-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }
            .result-header {
                display: flex;
                justify-content: space-between;
                align-items: start;
                gap: var(--space-3);
                margin-bottom: var(--space-2);
            }
            .result-title {
                border: none;
                background: transparent;
                padding: 0;
                text-align: left;
                cursor: pointer;
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                color: var(--accent);
            }
            .result-title:hover {
                text-decoration: underline;
            }
            .result-meta {
                font-size: var(--text-sm);
                color: var(--text-tertiary);
            }
            .result-score {
                flex-shrink: 0;
                padding: var(--space-1) var(--space-2);
                background: var(--accent-subtle);
                color: var(--accent);
                border-radius: var(--radius-sm);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
            }
            .result-snippet {
                font-size: var(--text-sm);
                color: var(--text-secondary);
                line-height: 1.6;
            }
            .empty,
            .loading {
                padding: var(--space-8);
                text-align: center;
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.items = [];
        this.loading = false;
        this.query = '';
    }

    _openResult(item) {
        if (!item || typeof item !== 'object') {
            return;
        }
        const bindingId = typeof item.binding_id === 'string' ? item.binding_id : '';
        if (bindingId.length === 0) {
            throw new Error('office-catalog-semantic-search-results: binding_id required');
        }
        this.emit('result-open', { bindingId });
    }

    _formatScore(score) {
        if (typeof score !== 'number') {
            return '';
        }
        return score.toFixed(3);
    }

    render() {
        if (this.loading) {
            return html`<div class="loading">${this.t('semantic_search.loading')}</div>`;
        }
        const items = Array.isArray(this.items) ? this.items : [];
        const query = typeof this.query === 'string' ? this.query.trim() : '';
        if (query.length === 0) {
            return html`<div class="empty">${this.t('semantic_search.empty_query')}</div>`;
        }
        if (items.length === 0) {
            return html`<div class="empty">${this.t('semantic_search.no_results')}</div>`;
        }
        return html`
            <div class="results">
                ${items.map((item) => html`
                    <article class="result-card">
                        <div class="result-header">
                            <div>
                                <button
                                    type="button"
                                    class="result-title"
                                    @click=${() => this._openResult(item)}
                                >
                                    ${item.title}
                                </button>
                                <div class="result-meta">
                                    ${item.catalog_title}
                                </div>
                            </div>
                            <span class="result-score">${this._formatScore(item.score)}</span>
                        </div>
                        <div class="result-snippet">${item.snippet}</div>
                    </article>
                `)}
            </div>
        `;
    }
}

customElements.define('office-catalog-semantic-search-results', OfficeCatalogSemanticSearchResults);

/**
 * office-catalog-semantic-search-results — Google-like SERP for catalog semantic search.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/platform-empty-state.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

export class OfficeCatalogSemanticSearchResults extends PlatformElement {
    static i18nNamespace = 'documents';

    static override properties: PropertyDeclarations = {
        items: { type: Array },
        loading: { type: Boolean },
        query: { type: String },
    }
    declare items: Record<string, unknown>[];
    declare loading: boolean;
    declare query: string;
;

    static override styles: CSSResultGroup = [
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
        `,
    ];

    constructor() {
        super();
        this.items = [];
        this.loading = false;
        this.query = '';
    }

    private _openResult(item: Record<string, unknown>) {
        if (!item || typeof item !== 'object') {
            return;
        }
        const fileId = typeof item.file_id === 'string' ? item.file_id : '';
        if (fileId.length === 0) {
            throw new Error('office-catalog-semantic-search-results: file_id required');
        }
        this.emit('result-open', { fileId });
    }

    private _formatScore(score: unknown) {
        if (typeof score !== 'number') {
            return '';
        }
        return score.toFixed(3);
    }

    override render(): TemplateResult {
        if (this.loading) {
            return html`<platform-empty-state loading></platform-empty-state>`;
        }
        const items = Array.isArray(this.items) ? this.items : [];
        const query = typeof this.query === 'string' ? this.query.trim() : '';
        if (query.length === 0) {
            return html`<platform-empty-state icon="search" title=${this.t('semantic_search.empty_query')}></platform-empty-state>`;
        }
        if (items.length === 0) {
            return html`<platform-empty-state icon="search" title=${this.t('semantic_search.no_results')}></platform-empty-state>`;
        }
        return html`
            <div class="results">
                ${items.map((item: Record<string, unknown>) => html`
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

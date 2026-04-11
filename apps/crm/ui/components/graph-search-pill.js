import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class GraphSearchPill extends PlatformElement {
    static properties = {
        query: { type: String },
        viewMode: { type: String, attribute: 'view-mode' },
        modes: { type: Array },
        searchMode: { type: String, attribute: 'search-mode' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                align-items: center;
                gap: 8px;
                pointer-events: none;
            }

            .pill {
                display: flex;
                align-items: center;
                gap: 0;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: 999px;
                overflow: hidden;
                pointer-events: auto;
                backdrop-filter: blur(6px);
            }

            .pill input {
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: 13px;
                padding: 8px 14px;
                width: 180px;
                outline: none;
            }

            .pill input::placeholder {
                color: var(--text-tertiary);
            }

            .pill-icon-btn {
                width: 32px;
                height: 32px;
                border: none;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }

            .pill-icon-btn:hover {
                color: var(--text-primary);
            }

            .pill-icon-btn svg {
                width: 14px;
                height: 14px;
                fill: none;
                stroke: currentColor;
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            .mode-pills {
                display: flex;
                align-items: center;
                gap: 4px;
                pointer-events: auto;
            }

            .mode-pill {
                display: inline-flex;
                align-items: center;
                padding: 5px 10px;
                border-radius: 999px;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                backdrop-filter: blur(6px);
                color: var(--text-secondary);
                font-size: 12px;
                cursor: pointer;
                transition: background 0.14s, color 0.14s;
            }

            .mode-pill:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .mode-pill.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--text-primary);
            }

            .search-mode-toggle {
                display: flex;
                align-items: center;
                gap: 2px;
                pointer-events: auto;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: 999px;
                padding: 2px;
                backdrop-filter: blur(6px);
            }

            .search-mode-btn {
                display: inline-flex;
                align-items: center;
                padding: 4px 9px;
                border-radius: 999px;
                border: none;
                background: transparent;
                color: var(--text-secondary);
                font-size: 11px;
                cursor: pointer;
                transition: background 0.14s, color 0.14s;
            }

            .search-mode-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }

            .search-mode-btn.active {
                background: var(--accent-subtle);
                color: var(--text-primary);
            }

            @media (max-width: 1199px) {
                .pill input {
                    width: 140px;
                }
            }

            @media (max-width: 767px) {
                :host {
                    flex-wrap: wrap;
                }

                .pill input {
                    width: 100px;
                }

                .mode-pills {
                    gap: 3px;
                }

                .mode-pill {
                    font-size: 11px;
                    padding: 4px 8px;
                }
            }
        `,
    ];

    constructor() {
        super();
        this.query = '';
        this.viewMode = 'influence';
        this.modes = ['influence', 'related', 'path'];
        this.searchMode = 'hybrid';
    }

    _onInput(e) {
        this.emit('search-input', { query: e.target.value });
    }

    _onKeydown(e) {
        if (e.key === 'Escape') {
            this.emit('search-clear');
        }
        if (e.key === 'Enter') {
            this.emit('search-submit');
        }
    }

    _onSearchModeChange(mode) {
        this.emit('search-mode-change', { mode });
    }

    _onClear() {
        this.emit('search-clear');
    }

    _onRefresh() {
        this.emit('refresh');
    }

    _onModeChange(mode) {
        this.emit('mode-change', { mode });
    }

    render() {
        const hasQuery = this.query.trim().length > 0;

        return html`
            <div class="pill">
                <input
                    type="text"
                    .value=${this.query}
                    placeholder=${this.i18n.t('graph.search_placeholder_short')}
                    @input=${this._onInput}
                    @keydown=${this._onKeydown}
                />
                ${hasQuery
                    ? html`<button class="pill-icon-btn" type="button" title=${this.i18n.t('graph.search_clear')} @click=${this._onClear}>
                        <platform-icon name="close" size="16"></platform-icon>
                    </button>`
                    : html`<button class="pill-icon-btn" type="button" title=${this.i18n.t('graph.search_refresh_graph')} @click=${this._onRefresh}>
                        <platform-icon name="refresh" size="16"></platform-icon>
                    </button>`
                }
            </div>
            <div class="search-mode-toggle">
                ${['text', 'semantic', 'hybrid'].map((mode) => html`
                    <button
                        class="search-mode-btn ${this.searchMode === mode ? 'active' : ''}"
                        type="button"
                        title=${this.i18n.t(`graph.search_mode_${mode}`)}
                        @click=${() => this._onSearchModeChange(mode)}
                    >${this.i18n.t(`entities.search_modes.${mode}`)}</button>
                `)}
            </div>
            <div class="mode-pills">
                ${this.modes.map((mode) => html`
                    <button
                        class="mode-pill ${this.viewMode === mode ? 'active' : ''}"
                        type="button"
                        @click=${() => this._onModeChange(mode)}
                    >${mode}</button>
                `)}
            </div>
        `;
    }
}

customElements.define('graph-search-pill', GraphSearchPill);

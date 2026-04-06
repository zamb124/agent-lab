import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

/**
 * Единая строка мобильного хедера CRM: заголовок или поле поиска (иконка + input) в одной линии.
 */
export class CrmMobileAppHeader extends PlatformElement {
    static properties = {
        headerTitle: { type: String },
        searchable: { type: Boolean },
        searchOpen: { type: Boolean },
        searchValue: { type: String },
        extraIcon: { type: String },
        extraTitle: { type: String },
        actionIcon: { type: String },
        actionTitle: { type: String },
        assistantIcon: { type: String, attribute: 'assistant-icon' },
        assistantTitle: { type: String },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                width: 100%;
            }

            .bar {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: max(var(--space-2), env(safe-area-inset-top, 0px)) var(--space-3) var(--space-2);
                background: var(--crm-surface-muted);
                border-bottom: 1px solid var(--crm-stroke);
                box-sizing: border-box;
            }

            .menu-btn,
            .icon-btn {
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: transparent;
                border: 1px solid var(--crm-stroke);
                color: var(--text-primary);
                cursor: pointer;
                flex-shrink: 0;
                padding: 0;
            }

            .menu-btn:hover,
            .icon-btn:hover {
                background: var(--crm-surface);
            }

            .title {
                flex: 1;
                min-width: 0;
                font-size: var(--text-lg);
                font-weight: 700;
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .inline-search {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: 0 var(--space-3);
                border-radius: var(--radius-full);
                border: 1px solid var(--crm-stroke);
                background: var(--crm-surface-muted);
                min-height: 36px;
                box-sizing: border-box;
            }

            .inline-search-input {
                width: 100%;
                min-width: 0;
                border: none;
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                outline: none;
            }

            .inline-search-input:focus {
                outline: none;
            }

            .inline-search:focus-within {
                border-color: var(--accent);
            }

            .action-btn {
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: var(--crm-daily-notes-cta-bg);
                border: none;
                color: var(--text-inverse);
                cursor: pointer;
                flex-shrink: 0;
                padding: 0;
                transition: background var(--duration-fast);
            }

            .action-btn:hover {
                background: var(--crm-daily-notes-cta-hover);
            }
        `,
    ];

    constructor() {
        super();
        this.headerTitle = '';
        this.searchable = false;
        this.searchOpen = false;
        this.searchValue = '';
        this.extraIcon = '';
        this.extraTitle = '';
        this.actionIcon = '';
        this.actionTitle = '';
        this.assistantIcon = '';
        this.assistantTitle = '';
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('searchOpen') && this.searchOpen && this.searchable) {
            requestAnimationFrame(() => {
                const input = this.renderRoot?.querySelector('.inline-search-input');
                if (input instanceof HTMLInputElement) {
                    input.focus();
                }
            });
        }
    }

    render() {
        const showInlineSearch = this.searchable && this.searchOpen;
        const showTitle = !showInlineSearch;

        return html`
            <div class="bar">
                <button
                    class="menu-btn"
                    type="button"
                    title=${this.i18n.t('app_shell.mobile_menu')}
                    @click=${() => this.emit('header-menu')}
                >
                    <platform-icon name="menu" size="18"></platform-icon>
                </button>

                ${showInlineSearch ? html`
                    <label class="inline-search">
                        <platform-icon name="search" size="14"></platform-icon>
                        <input
                            class="inline-search-input"
                            type="text"
                            placeholder=${this.i18n.t('search.placeholder')}
                            .value=${this.searchValue}
                            @input=${(e) => this.emit('header-search-input', { value: e.target.value })}
                        />
                    </label>
                    <button
                        class="icon-btn"
                        type="button"
                        title=${this.i18n.t('app_shell.mobile_close_search')}
                        @click=${() => this.emit('header-search-close')}
                    >
                        <platform-icon name="close" size="16"></platform-icon>
                    </button>
                ` : html`
                    ${showTitle ? html`<span class="title">${this.headerTitle}</span>` : ''}
                    ${this.searchable ? html`
                        <button
                            class="icon-btn"
                            type="button"
                            title=${this.i18n.t('app_shell.mobile_search')}
                            @click=${() => this.emit('header-toggle-search')}
                        >
                            <platform-icon name="search" size="16"></platform-icon>
                        </button>
                    ` : ''}
                `}

                ${this.assistantIcon ? html`
                    <button
                        class="icon-btn"
                        type="button"
                        title=${this.assistantTitle || ''}
                        @click=${() => this.emit('header-assistant')}
                    >
                        <platform-icon name=${this.assistantIcon} size="16" filled></platform-icon>
                    </button>
                ` : ''}

                ${this.extraIcon ? html`
                    <button
                        class="icon-btn"
                        type="button"
                        title=${this.extraTitle || ''}
                        @click=${() => this.emit('header-extra')}
                    >
                        <platform-icon name=${this.extraIcon} size="16"></platform-icon>
                    </button>
                ` : ''}

                ${this.actionIcon ? html`
                    <button
                        class="action-btn"
                        type="button"
                        title=${this.actionTitle || ''}
                        @click=${() => this.emit('header-action')}
                    >
                        <platform-icon name=${this.actionIcon} size="18"></platform-icon>
                    </button>
                ` : ''}
            </div>
        `;
    }
}

customElements.define('crm-mobile-app-header', CrmMobileAppHeader);

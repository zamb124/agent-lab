/**
 * PageHeader - унифицированный хедер страницы с бургер-меню на мобильных
 *
 * Использование:
 * <page-header title="Заголовок" subtitle="Подзаголовок">
 *     <button slot="actions">Кнопка</button>
 * </page-header>
 *
 * На узких экранах: одна строка, заголовок без переноса (ellipsis). Режим
 * mobileToolbarMode="search" заменяет блок заголовка на слот toolbar-search
 * (поле поиска и т.п. между бургером и actions).
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { CoreEvents } from '../../events/contract.js';
import '../platform-icon.js';

export class PageHeader extends PlatformElement {
    static properties = {
        title: { type: String },
        subtitle: { type: String },
        /** На mobile: "title" — заголовок и subtitle; "search" — слот toolbar-search */
        mobileToolbarMode: { type: String },
        _isMobile: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                margin-bottom: var(--space-6);
            }

            .header {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: var(--space-4);
            }

            .header-left {
                display: flex;
                align-items: flex-start;
                gap: var(--space-3);
                flex: 1;
                min-width: 0;
            }

            .menu-btn {
                display: none;
            }

            .title-section {
                flex: 1;
                min-width: 0;
            }

            .toolbar-search-host {
                flex: 1;
                min-width: 0;
                display: flex;
                align-items: center;
            }

            .title {
                font-size: var(--text-3xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                margin: 0;
                letter-spacing: var(--tracking-tight);
            }

            .subtitle {
                font-size: var(--text-base);
                color: var(--text-secondary);
                margin-top: var(--space-1);
            }

            .actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }

            @media (max-width: 767px) {
                :host {
                    margin-bottom: var(--space-2);
                }

                .header-wrap {
                    position: sticky;
                    top: 0;
                    z-index: 30;
                    margin: 0 0 var(--space-2);
                    padding: max(var(--space-1), var(--platform-safe-top))
                        max(var(--space-1), env(safe-area-inset-right, 0px))
                        var(--space-2)
                        max(var(--space-1), env(safe-area-inset-left, 0px));
                    background: var(--glass-solid-strong);
                    backdrop-filter: blur(var(--glass-blur-medium));
                    -webkit-backdrop-filter: blur(var(--glass-blur-medium));
                    border-bottom: 1px solid var(--glass-border-subtle);
                    box-sizing: border-box;
                }

                .header {
                    align-items: center;
                    flex-wrap: nowrap;
                    min-height: 44px;
                    gap: var(--space-1);
                }

                .header-left {
                    align-items: center;
                    min-width: 0;
                }

                .menu-btn {
                    display: flex;
                    width: 36px;
                    height: 36px;
                    margin-left: 0;
                    align-items: center;
                    justify-content: center;
                    border-radius: var(--radius-lg);
                    background: var(--glass-solid-strong);
                    backdrop-filter: blur(var(--glass-blur-medium));
                    border: 1px solid var(--glass-border-medium);
                    color: var(--text-primary);
                    cursor: pointer;
                    flex-shrink: 0;
                    transition: all var(--duration-fast) var(--easing-default);
                    box-shadow: var(--glass-shadow-subtle);
                }

                .menu-btn.hidden {
                    display: none;
                }

                .menu-btn:hover {
                    background: var(--glass-solid-medium);
                }

                .menu-btn:active {
                    transform: scale(0.95);
                }

                .title {
                    font-size: var(--text-xl);
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }

                .actions {
                    gap: var(--space-1);
                    overflow-x: auto;
                    flex-shrink: 0;
                    -webkit-overflow-scrolling: touch;
                    scrollbar-width: none;
                }

                .actions::-webkit-scrollbar {
                    display: none;
                }

                /* Слот между бургером и actions: без display:contents у <slot> flex-элемент
                   часто получает нулевую ширину — поле поиска не видно. */
                .toolbar-search-host slot {
                    display: contents;
                }

                .toolbar-search-host ::slotted(*) {
                    flex: 1 1 0%;
                    min-width: 0;
                    display: flex;
                    align-items: center;
                    gap: var(--space-2);
                    box-sizing: border-box;
                }
            }

            /* Light theme */
            :host-context([data-theme="light"]) .header-wrap {
                background: rgba(255, 255, 255, 0.92);
                border-bottom-color: rgba(15, 23, 42, 0.08);
            }

            :host-context([data-theme="light"]) .menu-btn {
                background: rgba(255, 255, 255, 0.95);
                border-color: rgba(0, 0, 0, 0.1);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }
        `,
    ];

    constructor() {
        super();
        this.title = '';
        this.subtitle = '';
        this.mobileToolbarMode = 'title';
        this._isMobile = false;
        this._resizeObserver = null;
        this._sidebarOpenSel = this.select((s) => s.ui.sidebar.mobileOpen);
    }

    connectedCallback() {
        super.connectedCallback();
        this._checkMobile();
        this._resizeObserver = new ResizeObserver(() => this._checkMobile());
        this._resizeObserver.observe(document.body);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
    }

    _checkMobile() {
        this._isMobile = window.innerWidth <= 767;
    }

    _openSidebar() {
        this.dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
    }

    _renderTitleBlock() {
        if (this._isMobile && this.mobileToolbarMode === 'search') {
            return html`
                <div class="toolbar-search-host">
                    <slot name="toolbar-search"></slot>
                </div>
            `;
        }
        return html`
            <div class="title-section">
                <h1 class="title">${this.title}</h1>
                ${this.subtitle ? html`<p class="subtitle">${this.subtitle}</p>` : ''}
            </div>
        `;
    }

    render() {
        const sidebarOpen = !!(this._sidebarOpenSel && this._sidebarOpenSel.value);
        const showMenu = this._isMobile && !sidebarOpen;

        return html`
            <div class="header-wrap">
            <div class="header">
                <div class="header-left">
                    <button
                        class="menu-btn ${showMenu ? '' : 'hidden'}"
                        @click=${this._openSidebar}
                        title="Открыть меню"
                    >
                        <platform-icon name="menu" size="20"></platform-icon>
                    </button>
                    ${this._renderTitleBlock()}
                </div>
                <div class="actions">
                    <slot name="actions"></slot>
                </div>
            </div>
            </div>
        `;
    }
}

customElements.define('page-header', PageHeader);

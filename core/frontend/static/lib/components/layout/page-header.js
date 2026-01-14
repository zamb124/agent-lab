/**
 * PageHeader - унифицированный хедер страницы с бургер-меню на мобильных
 * 
 * Использование:
 * <page-header title="Заголовок" subtitle="Подзаголовок">
 *     <button slot="actions">Кнопка</button>
 * </page-header>
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../platform-icon.js';

export class PageHeader extends PlatformElement {
    static properties = {
        title: { type: String },
        subtitle: { type: String },
        _isMobile: { state: true },
        _sidebarOpen: { state: true },
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
                .header {
                    flex-wrap: wrap;
                }

                .menu-btn {
                    display: flex;
                    width: 36px;
                    height: 36px;
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
                    margin-top: 2px;
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
                    font-size: var(--text-2xl);
                }

                .actions {
                    width: 100%;
                    margin-top: var(--space-3);
                }
            }

            /* Light theme */
            :host-context([data-theme="light"]) .menu-btn {
                background: rgba(255, 255, 255, 0.95);
                border-color: rgba(0, 0, 0, 0.1);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }
        `
    ];

    constructor() {
        super();
        this.title = '';
        this.subtitle = '';
        this._isMobile = false;
        this._sidebarOpen = false;
        this._resizeObserver = null;
        this._boundMobileChangeHandler = this._onSidebarMobileChange.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        this._checkMobile();
        this._resizeObserver = new ResizeObserver(() => this._checkMobile());
        this._resizeObserver.observe(document.body);
        window.addEventListener('platform-sidebar-mobile-change', this._boundMobileChangeHandler);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        window.removeEventListener('platform-sidebar-mobile-change', this._boundMobileChangeHandler);
    }

    _checkMobile() {
        this._isMobile = window.innerWidth <= 767;
    }

    _onSidebarMobileChange(e) {
        this._sidebarOpen = e.detail?.open || false;
    }

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }

    render() {
        const showMenu = this._isMobile && !this._sidebarOpen;

        return html`
            <div class="header">
                <div class="header-left">
                    <button 
                        class="menu-btn ${showMenu ? '' : 'hidden'}" 
                        @click=${this._openSidebar} 
                        title="Открыть меню"
                    >
                        <platform-icon name="menu" size="20"></platform-icon>
                    </button>
                    <div class="title-section">
                        <h1 class="title">${this.title}</h1>
                        ${this.subtitle ? html`<p class="subtitle">${this.subtitle}</p>` : ''}
                    </div>
                </div>
                <div class="actions">
                    <slot name="actions"></slot>
                </div>
            </div>
        `;
    }
}

customElements.define('page-header', PageHeader);

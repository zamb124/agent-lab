/**
 * PageHeader — in-flow заголовок страницы.
 *
 * Использование:
 * <page-header title="Заголовок" subtitle="Подзаголовок">
 *     <button type="button" slot="leading" class="page-header-leading-btn"></button>
 *     <button slot="actions">Кнопка</button>
 * </page-header>
 *
 * На узких экранах: одна строка в липкой полосе — только заголовок (ellipsis),
 * без subtitle (длинный текст выносится в тело страницы). Режим
 * mobileToolbarMode="search" заменяет блок заголовка на слот toolbar-search.
 *
 * Mobile shell 2026: гамбургер удалён, первичная навигация — `platform-bottom-nav`,
 * глобальная шапка — `platform-top-bar`. `page-header` остаётся как in-flow
 * заголовок страницы для контекстных actions и подписей. Атрибут `hide-mobile-menu`
 * сохранён как no-op для обратной совместимости и будет удалён позже.
 */
import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { mobileStickyHeaderPageHeaderShellStyles } from '../../styles/shared/mobile-sticky-header.styles.js';
import '../platform-icon.js';

export class PageHeader extends PlatformElement {
    static properties = {
        title: { type: String },
        subtitle: { type: String },
        /** Компактный отступ снизу и чуть меньший заголовок (строчка с actions). */
        dense: { type: Boolean, reflect: true },
        /** На mobile: "title" — только заголовок; "search" — слот toolbar-search */
        mobileToolbarMode: { type: String },
        /**
         * На mobile у `.actions` по умолчанию `overflow-x: auto` (много кнопок).
         * `visible` — не обрезать по вертикали/вне контейнера (выпадающие меню в slot actions).
         */
        actionsOverflow: { type: String, attribute: 'actions-overflow' },
        /**
         * @deprecated Mobile shell 2026: гамбургер удалён, атрибут оставлен как no-op
         * для постепенной миграции pages/modals. Используйте `platform-top-bar`.
         */
        hideMobileMenu: { type: Boolean, attribute: 'hide-mobile-menu' },
        _isMobile: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        mobileStickyHeaderPageHeaderShellStyles,
        css`
            :host {
                display: block;
                margin-bottom: var(--space-6);
            }

            :host([dense]) {
                margin-bottom: var(--space-2);
            }

            :host([dense]) .title {
                font-size: var(--text-2xl);
            }

            :host([dense]) .subtitle {
                font-size: var(--text-sm);
                margin-top: 2px;
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

            ::slotted(.page-header-leading-btn) {
                flex-shrink: 0;
                width: 40px;
                height: 40px;
                margin-top: 2px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                box-sizing: border-box;
                padding: 0;
            }
            ::slotted(.page-header-leading-btn):hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
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

                .header,
                .header-left {
                    align-items: center;
                }

                ::slotted(.page-header-leading-btn) {
                    margin-top: 0;
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

                .actions[data-overflow='visible'] {
                    overflow: visible;
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
                    min-height: var(--platform-mobile-sticky-header-row-min-height);
                    display: grid;
                    grid-template-columns: auto minmax(0, 1fr);
                    align-items: center;
                    gap: var(--space-2);
                    box-sizing: border-box;
                }
            }

            /* Светлая тема */
            :host-context([data-theme="light"]) .header-wrap {
                background: rgba(255, 255, 255, 0.92);
                border-bottom-color: rgba(15, 23, 42, 0.08);
            }
        `,
    ];

    constructor() {
        super();
        this.title = '';
        this.subtitle = '';
        this.dense = false;
        this.mobileToolbarMode = 'title';
        this.actionsOverflow = 'auto';
        this.hideMobileMenu = false;
        this._isMobile = false;
        this._resizeObserver = null;
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

    _renderTitleBlock() {
        if (this._isMobile && this.mobileToolbarMode === 'search') {
            return html`
                <div class="toolbar-search-host">
                    <slot name="toolbar-search"></slot>
                </div>
            `;
        }
        const showSubtitle = Boolean(this.subtitle) && !(this._isMobile && this.mobileToolbarMode === 'title');
        return html`
            <div class="title-section">
                <h1 class="title">${this.title}</h1>
                ${showSubtitle ? html`<p class="subtitle">${this.subtitle}</p>` : ''}
            </div>
        `;
    }

    render() {
        return html`
            <div class="header-wrap">
            <div class="header">
                <div class="header-left">
                    <slot name="leading"></slot>
                    ${this._renderTitleBlock()}
                </div>
                <div
                    class="actions"
                    data-overflow=${this.actionsOverflow === 'visible' ? 'visible' : 'auto'}
                >
                    <slot name="actions"></slot>
                </div>
            </div>
            </div>
        `;
    }
}

customElements.define('page-header', PageHeader);

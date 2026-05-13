/**
 * Shared Sidebar Styles
 * Стили для элементов sidebar - классы, без :host
 * :host стили находятся в platform-sidebar.js
 */
import { css } from 'lit';

/**
 * Стили для platform-sidebar компонента (с :host)
 * Используется ТОЛЬКО в platform-sidebar.js
 */
export const sidebarHostStyles = css`
    :host {
        display: flex;
        flex-direction: column;
        width: var(--sidebar-width, 280px);
        min-width: var(--sidebar-width, 280px);
        height: 100%;
        background: transparent;
        transition: width var(--duration-normal, 0.25s) ease,
                    min-width var(--duration-normal, 0.25s) ease;
        /* iOS Safe Area - учитываем notch и статус-бар */
        padding-top: env(safe-area-inset-top, 0);
    }

    /* ========== COLLAPSED MODE ========== */

    :host([collapsed]) {
        width: var(--sidebar-collapsed-width, 72px);
        min-width: var(--sidebar-collapsed-width, 72px);
    }

    :host([collapsed]) .sidebar-content {
        padding: var(--space-3) var(--space-2);
        padding-bottom: 0;
    }

    /*
     * В expanded отрицательный margin даёт полноширинные nav-item без «ступеньки»;
     * при collapsed узкая колонка + overflow:hidden обрезают содержимое слева.
     */
    :host([collapsed]) .sidebar-nav {
        margin-inline: 0;
        padding-inline: 0;
    }

    :host([collapsed]) .sidebar-logo {
        flex-direction: row;
        justify-content: center;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-3) var(--space-2);
    }

    :host([collapsed]) .sidebar-logo-hit {
        flex: 0 1 auto;
    }

    :host([collapsed]) .sidebar-collapse-row {
        justify-content: center;
    }

    :host(:not([collapsed])) .sidebar-logo {
        margin-bottom: var(--space-6);
    }

    :host([collapsed]) .sidebar-logo-text,
    :host([collapsed]) .sidebar-section-title,
    :host([collapsed]) .sidebar-text,
    :host([collapsed]) ::slotted([data-hide-collapsed]) {
        display: none;
    }

    :host([collapsed]) .sidebar-header {
        flex-direction: column;
        padding: 0;
    }

    :host([collapsed]) .sidebar-footer {
        padding: var(--space-3) 0;
        display: flex;
        flex-direction: column;
        align-items: center;
    }

    /* ========== MOBILE MODE ========== */

    .mobile-backdrop {
        display: none;
    }

    /*
     * Mobile shell 2026: сайдбар-drawer удалён на мобиле. Первичная навигация —
     * <platform-bottom-nav> + <platform-top-bar> + <platform-bottom-sheet>.
     * Сайдбар-сервиса полностью скрыт на ширине <= 767px; обёртка
     * platform-service-sidebar не рендерит мобильное переключение.
     */
    @media (max-width: 767px) {
        :host {
            display: none !important;
        }
    }

    /* ========== LIGHT THEME ========== */

    :host-context([data-theme="light"]) .sidebar-footer {
        border-top-color: rgba(15, 23, 42, 0.08);
    }
`;

/**
 * Стили для внутренних элементов sidebar (классы)
 * Можно использовать в любом компоненте
 */
export const sidebarStyles = css`
    .sidebar-content {
        flex: 1;
        min-height: 0;
        display: flex;
        flex-direction: column;
        padding: var(--space-4);
        padding-bottom: 0;
        overflow-y: auto;
        overflow-x: visible;
    }

    .sidebar-logo {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: var(--space-4) var(--space-3);
        margin-bottom: var(--space-2);
    }

    .sidebar-logo-hit {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        flex: 1;
        min-width: 0;
        margin: 0;
        padding: 0;
        border: none;
        background: transparent;
        font: inherit;
        color: inherit;
        text-align: left;
        cursor: pointer;
        border-radius: var(--radius-lg);
        transition: background var(--duration-fast);
    }

    .sidebar-logo-hit:hover {
        background: var(--glass-solid-subtle);
    }

    .sidebar-logo-hit:focus-visible {
        outline: 2px solid var(--accent);
        outline-offset: 2px;
    }

    .sidebar-logo > .collapse-btn {
        margin-left: auto;
        flex-shrink: 0;
    }

    .sidebar-logo--slot {
        flex-wrap: wrap;
    }

    .sidebar-logo--slot slot[name='logo']::slotted(*) {
        flex: 1 1 auto;
        min-width: 0;
    }

    .sidebar-collapse-row {
        display: flex;
        align-items: center;
        justify-content: flex-end;
        flex-shrink: 0;
        width: 100%;
        min-width: 0;
        padding: 0 var(--space-3);
        margin-bottom: var(--space-3);
        box-sizing: border-box;
    }

    @media (max-width: 767px) {
        .sidebar-collapse-row {
            display: none;
        }
    }

    .sidebar-logo-icon {
        width: var(--sidebar-logo-width, 36px);
        height: var(--sidebar-logo-height, 36px);
        flex-shrink: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-lg);
        transition: all var(--duration-fast);
    }

    .sidebar-logo-icon.clickable {
        cursor: pointer;
    }

    .sidebar-logo-icon.clickable:hover {
        background: var(--glass-solid-medium);
        transform: scale(1.05);
    }

    .sidebar-logo-icon img {
        width: 100%;
        height: 100%;
        object-fit: contain;
    }

    .sidebar-logo-text {
        font-size: var(--text-xl);
        font-weight: var(--sidebar-logo-text-weight, var(--font-bold));
        color: var(--sidebar-logo-text-color, var(--text-primary));
        background: var(--sidebar-logo-text-gradient, none);
        -webkit-background-clip: var(--sidebar-logo-text-clip, border-box);
        background-clip: var(--sidebar-logo-text-clip, border-box);
        -webkit-text-fill-color: var(--sidebar-logo-text-fill, currentColor);
        letter-spacing: var(--tracking-tight);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .sidebar-header {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: 0;
        margin-bottom: var(--space-4);
        width: 100%;
        min-width: 0;
        box-sizing: border-box;
    }

    .sidebar-header slot[name="header"]::slotted(*) {
        flex: 1 1 100%;
        min-width: 0;
        max-width: 100%;
        box-sizing: border-box;
    }

    .sidebar-nav {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
        overflow-y: auto;
        overflow-x: hidden;
        min-height: 0;
        padding: 0 var(--sidebar-nav-inline, var(--space-2));
        margin: 0 calc(-1 * var(--sidebar-nav-inline, var(--space-2)));
    }

    .sidebar-section {
        margin-bottom: var(--space-6);
    }

    .sidebar-section-title {
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-tertiary);
        padding: var(--space-2) var(--space-3);
        margin-bottom: var(--space-2);
        white-space: nowrap;
        overflow: hidden;
    }

    .sidebar-footer {
        flex-shrink: 0;
        padding: var(--space-4);
        border-top: 1px solid var(--glass-border-subtle);
        overflow: visible;
    }

    .collapse-btn {
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-lg);
        color: var(--text-secondary);
        background: transparent;
        border: 1px solid transparent;
        cursor: pointer;
        transition: all var(--duration-normal) var(--easing-default);
    }

    .collapse-btn:hover {
        background: var(--glass-solid-medium);
        border-color: var(--glass-border-subtle);
        color: var(--text-primary);
    }
`;

export const sidebarNavItemStyles = css`
    .nav-item {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: var(--space-3) var(--space-4);
        border-radius: var(--radius-xl);
        cursor: pointer;
        background: transparent;
        border: 1px solid transparent;
        color: var(--text-secondary);
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        text-decoration: none;
        transition: all var(--duration-normal) var(--easing-default);
        width: 100%;
        text-align: left;
    }

    .nav-item:hover {
        background: var(--glass-solid-medium);
        border-color: var(--glass-border-subtle);
        box-shadow: var(--glass-shadow-subtle);
        color: var(--text-primary);
        transform: translateX(4px);
    }

    .nav-item.active {
        background: var(--accent-subtle);
        border-color: var(--accent);
        color: var(--accent);
        font-weight: var(--font-semibold);
        box-shadow: var(--accent-glow);
    }

    /* Ведущая иконка в одной вертикали: фиксированная полоса, SVG центрируем (разный viewBox у иконок). */
    .nav-item > platform-icon:first-child {
        flex: 0 0 var(--sidebar-nav-icon-slot, 32px);
        width: var(--sidebar-nav-icon-slot, 32px);
        min-width: var(--sidebar-nav-icon-slot, 32px);
        margin: 0;
        box-sizing: border-box;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .nav-item-icon {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-md);
        flex-shrink: 0;
        transition: transform var(--duration-fast);
    }

    .nav-item:hover .nav-item-icon {
        transform: scale(1.05);
    }

    .nav-item-label {
        flex: 1;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .nav-item-badge {
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
        color: var(--text-secondary);
        padding: 3px 8px;
        background: var(--glass-solid-medium);
        border-radius: var(--radius-full);
        flex-shrink: 0;
    }

    .nav-item-actions {
        display: flex;
        gap: var(--space-1);
        opacity: 0;
        transition: opacity var(--duration-fast);
    }

    .nav-item:hover .nav-item-actions {
        opacity: 1;
    }

    .nav-item-expand {
        width: 20px;
        height: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--text-tertiary);
        transition: transform var(--duration-fast);
        flex-shrink: 0;
    }

    .nav-item-expand.expanded {
        transform: rotate(90deg);
    }

    .nav-item-icon.gradient-emerald {
        background: var(--accent-gradient);
        color: var(--text-inverse);
        box-shadow: var(--crm-nav-entities-shadow);
    }

    .nav-item-icon.gradient-blue {
        background: var(--crm-nav-entities-gradient);
        color: var(--text-inverse);
        box-shadow: var(--crm-nav-entities-shadow);
    }

    .nav-item-icon.gradient-purple {
        background: var(--crm-nav-graph-gradient);
        color: var(--text-inverse);
        box-shadow: var(--crm-nav-graph-shadow);
    }

    .nav-item-icon.gradient-orange {
        background: var(--crm-nav-notes-gradient);
        color: var(--text-inverse);
        box-shadow: var(--crm-nav-notes-shadow);
    }

    .nav-item-icon.gradient-green {
        background: var(--crm-nav-tasks-gradient);
        color: var(--text-inverse);
        box-shadow: var(--crm-nav-tasks-shadow);
    }

    .nav-item-icon.gradient-red {
        background: var(--crm-nav-calendar-gradient);
        color: var(--text-inverse);
        box-shadow: var(--crm-nav-calendar-shadow);
    }

    :host-context([data-theme="light"]) .nav-item.active {
        background: var(--accent-subtle);
        box-shadow: var(--accent-glow);
    }

    :host-context([data-theme="light"]) .nav-item-badge {
        background: var(--crm-surface-tint-strong);
    }
`;

export const sidebarSectionStyles = css`
    .section {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-height: 0;
        margin-bottom: var(--space-4);
    }

    .section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--space-2) var(--space-3);
        margin-bottom: var(--space-2);
        flex-shrink: 0;
    }

    .section-title {
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--text-tertiary);
        display: flex;
        align-items: center;
        gap: var(--space-2);
    }

    .section-actions {
        display: flex;
        gap: var(--space-1);
    }

    .section-action-btn {
        width: 22px;
        height: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-sm);
        color: var(--text-tertiary);
        background: var(--glass-solid-subtle);
        border: none;
        cursor: pointer;
        transition: all var(--duration-fast);
    }

    .section-action-btn:hover {
        background: var(--accent-subtle);
        color: var(--accent);
    }

    .section-content {
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        overflow-x: hidden;
    }
`;

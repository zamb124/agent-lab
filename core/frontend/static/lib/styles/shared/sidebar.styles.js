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
        padding: var(--space-3);
    }

    :host([collapsed]) .sidebar-logo {
        justify-content: center;
        padding: var(--space-3);
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
        padding: var(--space-3);
    }

    /* ========== MOBILE MODE ========== */

    .mobile-backdrop {
        display: none;
    }

    @media (max-width: 767px) {
        :host {
            position: fixed;
            left: -100%;
            top: 0;
            bottom: 0;
            height: auto;
            min-height: var(--app-vh, 100vh);
            min-height: -webkit-fill-available;
            z-index: var(--z-modal, 1000);
            width: 75%;
            min-width: 0;
            max-width: 320px;
            background: var(--glass-solid-strong);
            backdrop-filter: blur(var(--glass-blur-strong));
            -webkit-backdrop-filter: blur(var(--glass-blur-strong));
            border-right: 1px solid var(--glass-border-subtle);
            transition: left var(--duration-normal) ease;
            padding-bottom: env(safe-area-inset-bottom, 0px);
        }

        :host([mobile-open]) {
            left: 0;
        }

        :host([mobile-open]) .mobile-backdrop {
            display: block;
            position: fixed;
            top: 0;
            bottom: 0;
            left: 100%;
            width: 100vw;
            width: var(--app-vw, 100vw);
            height: auto;
            min-height: var(--app-vh, 100vh);
            min-height: -webkit-fill-available;
            background: rgba(0, 0, 0, 0.5);
            z-index: -1;
        }

        :host([collapsed]) {
            width: 75%;
            min-width: 0;
            max-width: 320px;
        }

        :host([collapsed]) .sidebar-logo-text,
        :host([collapsed]) .sidebar-section-title,
        :host([collapsed]) .sidebar-text,
        :host([collapsed]) ::slotted([data-hide-collapsed]) {
            display: block;
        }

        :host([collapsed]) .sidebar-logo {
            justify-content: flex-start;
        }

        :host([collapsed]) .sidebar-header {
            flex-direction: row;
        }
    }

    /* ========== LIGHT THEME ========== */

    :host-context([data-theme="light"]) .sidebar-footer {
        border-top-color: rgba(15, 23, 42, 0.08);
    }

    @media (max-width: 767px) {
        :host-context([data-theme="light"]) {
            background: rgba(255, 255, 255, 0.95);
            border-right-color: rgba(15, 23, 42, 0.08);
        }

        :host-context([data-theme="light"]) .mobile-backdrop {
            background: rgba(15, 23, 42, 0.3);
        }
    }
`;

/**
 * Стили для внутренних элементов sidebar (классы)
 * Можно использовать в любом компоненте
 */
export const sidebarStyles = css`
    .sidebar-content {
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: var(--space-4);
        overflow-y: auto;
        overflow-x: hidden;
    }

    .sidebar-logo {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: var(--space-4) var(--space-3);
        margin-bottom: var(--space-6);
    }

    .sidebar-logo .collapse-btn {
        margin-left: auto;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-lg);
        color: var(--text-secondary);
        background: transparent;
        border: 1px solid transparent;
        cursor: pointer;
        flex-shrink: 0;
        transition: all var(--duration-normal) var(--easing-default);
    }

    .sidebar-logo .collapse-btn:hover {
        background: var(--glass-solid-medium);
        border-color: var(--glass-border-subtle);
        color: var(--text-primary);
    }

    @media (max-width: 767px) {
        /* Скрыть collapse кнопку на мобильных */
        .sidebar-logo .collapse-btn {
            display: none;
        }
    }

    .sidebar-logo-icon {
        width: 36px;
        height: 36px;
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
        font-weight: var(--font-bold);
        color: var(--text-primary);
        letter-spacing: var(--tracking-tight);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .sidebar-header {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: 0 var(--space-3);
        margin-bottom: var(--space-4);
    }

    .sidebar-nav {
        flex: 1;
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
        overflow-y: auto;
        overflow-x: hidden;
        min-height: 0;
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
        margin-top: auto;
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

/**
 * Shared Island & Panel Styles
 * Стили для glass-контейнеров контента и сворачиваемых панелей
 */
import { css } from 'lit';

/**
 * Host стили для platform-island компонента
 */
export const islandHostStyles = css`
    :host {
        display: block;
        width: 100%;
        height: 100%;
    }

    :host([variant="subtle"]) {
        --island-bg: var(--glass-solid-subtle);
        --island-border: var(--glass-border-subtle);
        --island-shadow: var(--glass-shadow-subtle);
        --island-blur: var(--glass-blur-subtle);
    }

    :host([variant="elevated"]) {
        --island-bg: var(--glass-solid-strong);
        --island-border: var(--glass-border-strong);
        --island-shadow: var(--glass-shadow-strong);
        --island-blur: var(--glass-blur-strong);
    }
`;

/**
 * Внутренние стили для island контейнера
 */
export const islandStyles = css`
    .island {
        position: relative;
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        background: var(--island-bg, var(--glass-solid-medium));
        backdrop-filter: blur(var(--island-blur, var(--glass-blur-strong)));
        -webkit-backdrop-filter: blur(var(--island-blur, var(--glass-blur-strong)));
        border: 1px solid var(--island-border, var(--glass-border-medium));
        border-radius: var(--island-radius, var(--radius-2xl));
        box-shadow: var(--island-shadow, var(--glass-shadow-medium)), var(--glass-inner-glow-subtle);
        overflow: hidden;
        isolation: isolate;
        background-clip: padding-box;
        -webkit-mask-image: -webkit-radial-gradient(white, black);
    }

    .island-header-glow {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        height: 120px;
        border-radius: var(--island-radius, var(--radius-2xl)) var(--island-radius, var(--radius-2xl)) 0 0;
        background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.08) 0%,
            rgba(255, 255, 255, 0.02) 50%,
            transparent 100%
        );
        pointer-events: none;
        z-index: 0;
    }

    .island-content {
        position: relative;
        z-index: 1;
        padding: var(--island-padding, var(--space-6));
        flex: 1;
        min-height: 0;
        box-sizing: border-box;
        overflow-y: auto;
        overflow-x: hidden;
        overscroll-behavior: contain;
    }

    :host([padding="none"]) .island-content {
        padding: 0;
    }

    :host([padding="sm"]) .island-content {
        padding: var(--space-3);
    }

    :host([padding="md"]) .island-content {
        padding: var(--space-4);
    }

    :host([padding="lg"]) .island-content {
        padding: var(--space-8);
    }

    /* Light theme */
    :host-context([data-theme="light"]) .island {
        background: rgba(255, 255, 255, 0.9);
        border-color: rgba(15, 23, 42, 0.08);
    }

    :host-context([data-theme="light"]) .island-header-glow {
        background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.8) 0%,
            transparent 100%
        );
    }

    /* ========== MOBILE FULLSCREEN ========== */
    @media (max-width: 767px) {
        .island {
            border-radius: 0;
            border: none;
            box-shadow: none;
        }

        .island-header-glow {
            border-radius: 0;
        }

        .island-content {
            padding: var(--space-2);
            padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
            padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
            padding-bottom: max(var(--space-2), var(--platform-safe-bottom));
            display: flex;
            flex-direction: column;
        }

        :host([padding="none"]) .island-content {
            padding: 0;
        }

        :host([padding="none"][safe-bottom]) .island-content {
            padding-bottom: var(--platform-safe-bottom);
        }

        :host([padding="sm"]) .island-content {
            padding: var(--space-1);
            padding-left: max(var(--space-1), env(safe-area-inset-left, 0px));
            padding-right: max(var(--space-1), env(safe-area-inset-right, 0px));
            padding-bottom: max(var(--space-1), var(--platform-safe-bottom));
        }

        :host([padding="md"]) .island-content {
            padding: var(--space-2);
            padding-left: max(var(--space-2), env(safe-area-inset-left, 0px));
            padding-right: max(var(--space-2), env(safe-area-inset-right, 0px));
            padding-bottom: max(var(--space-2), var(--platform-safe-bottom));
        }

        :host([padding="lg"]) .island-content {
            padding: var(--space-4);
            padding-left: max(var(--space-4), env(safe-area-inset-left, 0px));
            padding-right: max(var(--space-4), env(safe-area-inset-right, 0px));
            padding-bottom: max(var(--space-4), var(--platform-safe-bottom));
        }
    }

    :host([content-no-scroll]) .island-content {
        overflow: hidden;
        overflow-y: hidden;
        display: flex;
        flex-direction: column;
    }

    :host([content-no-scroll]) .island-content ::slotted(*) {
        flex: 1;
        min-height: 0;
        min-width: 0;
    }

    /* ========== LOADING STATE ========== */

    .island-loading-overlay {
        position: absolute;
        inset: 0;
        z-index: 10;
        display: flex;
        align-items: center;
        justify-content: center;
        pointer-events: none;
        animation: island-loading-in 0.15s ease;
    }

    .island-content.busy {
        opacity: 0.5;
        pointer-events: none;
        transition: opacity 0.15s ease;
    }

    @keyframes island-loading-in {
        from { opacity: 0; }
        to { opacity: 1; }
    }
`;

/**
 * Host стили для platform-panel компонента
 */
export const panelHostStyles = css`
    :host {
        display: flex;
        flex-direction: column;
        height: 100%;
        width: var(--panel-width, 320px);
        min-width: var(--panel-width, 320px);
        background: var(--glass-solid-medium);
        backdrop-filter: blur(var(--glass-blur-strong));
        -webkit-backdrop-filter: blur(var(--glass-blur-strong));
        border: 1px solid var(--glass-border-medium);
        border-radius: var(--radius-2xl);
        overflow: hidden;
        transition: width var(--duration-normal) ease,
                    min-width var(--duration-normal) ease,
                    flex var(--duration-normal) ease;
    }

    :host([collapsed]) {
        width: var(--panel-collapsed-width, 48px) !important;
        min-width: var(--panel-collapsed-width, 48px) !important;
        flex: 0 0 var(--panel-collapsed-width, 48px) !important;
    }

    /* Light theme */
    :host-context([data-theme="light"]) {
        background: rgba(255, 255, 255, 0.9);
        border-color: rgba(15, 23, 42, 0.08);
    }

    /* Mobile fullscreen */
    @media (max-width: 767px) {
        :host {
            border-radius: 0;
            border: none;
            width: 100% !important;
            min-width: 100% !important;
        }
    }
`;

/**
 * Внутренние стили для panel компонента
 */
export const panelStyles = css`
    .panel-header {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: var(--space-4);
        border-bottom: 1px solid var(--glass-border-subtle);
        background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.08) 0%,
            transparent 100%
        );
        flex-shrink: 0;
    }

    :host([collapsed]) .panel-header {
        display: none;
    }

    .panel-collapse-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        background: var(--glass-solid-subtle);
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-md);
        cursor: pointer;
        transition: var(--motion-transition-interactive);
        color: var(--text-secondary);
        flex-shrink: 0;
    }

    .panel-collapse-btn:hover {
        background: var(--glass-solid-medium);
        color: var(--text-primary);
        border-color: var(--accent-subtle);
    }

    .panel-title {
        flex: 1;
        font-size: var(--text-lg);
        font-weight: 600;
        color: var(--text-primary);
        margin: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .panel-header-actions {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        flex-shrink: 0;
    }

    .panel-content {
        flex: 1;
        overflow-y: auto;
        overflow-x: hidden;
    }

    :host([collapsed]) .panel-content {
        display: none;
    }

    .panel-collapsed-view {
        display: none;
        flex-direction: column;
        align-items: center;
        flex: 1;
        padding: var(--space-3) 0;
        cursor: pointer;
    }

    :host([collapsed]) .panel-collapsed-view {
        display: flex;
    }

    .panel-collapsed-view:hover {
        background: var(--glass-solid-subtle);
    }

    .panel-expand-btn {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 28px;
        height: 28px;
        background: var(--glass-solid-subtle);
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-md);
        cursor: pointer;
        transition: var(--motion-transition-interactive);
        color: var(--text-secondary);
        margin: var(--space-2);
    }

    .panel-expand-btn:hover {
        background: var(--glass-solid-medium);
        color: var(--text-primary);
    }

    .panel-collapsed-title {
        writing-mode: vertical-rl;
        text-orientation: mixed;
        transform: rotate(180deg);
        font-size: var(--text-sm);
        font-weight: 500;
        color: var(--text-secondary);
        margin-top: var(--space-3);
        flex: 1;
    }

    .panel-collapsed-icon {
        margin-top: var(--space-2);
        color: var(--text-tertiary);
    }

    /* Light theme */
    :host-context([data-theme="light"]) .panel-header {
        background: linear-gradient(
            180deg,
            rgba(255, 255, 255, 0.8) 0%,
            transparent 100%
        );
    }
`;

/**
 * Стили для floating panel (agent-editor и подобные)
 */
export const floatingPanelStyles = css`
    .floating-panel {
        position: absolute;
        top: var(--space-4);
        right: var(--space-4);
        width: 340px;
        max-height: calc(100% - var(--space-8));
        background: var(--glass-solid-strong);
        border: 1px solid var(--border-default);
        border-radius: var(--radius-xl);
        box-shadow: var(--glass-shadow-strong);
        overflow: hidden;
        z-index: 20;
        display: flex;
        flex-direction: column;
        transition: 
            top var(--duration-slow) var(--easing-default),
            right var(--duration-slow) var(--easing-default),
            left var(--duration-slow) var(--easing-default),
            width var(--duration-slow) var(--easing-default),
            height var(--duration-slow) var(--easing-default),
            max-height var(--duration-slow) var(--easing-default),
            transform var(--duration-slow) var(--easing-default),
            box-shadow var(--duration-slow) var(--easing-default);
    }

    .floating-panel.entering {
        animation: floatingPanelSlideIn var(--duration-normal) ease-out;
    }

    @keyframes floatingPanelSlideIn {
        from {
            opacity: 0;
            transform: translateX(40px) scale(0.95);
        }
        to {
            opacity: 1;
            transform: translateX(0) scale(1);
        }
    }

    .floating-panel.expanded {
        position: fixed;
        top: 5vh !important;
        left: 50% !important;
        right: auto !important;
        transform: translateX(-50%);
        width: min(900px, 90vw);
        height: 90vh;
        max-height: 90vh;
        z-index: 100;
        box-shadow: 0 32px 100px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(255, 255, 255, 0.1);
    }

    .floating-panel-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(0, 0, 0, 0);
        z-index: 99;
        pointer-events: none;
        transition: background var(--duration-slow) var(--easing-default);
    }

    .floating-panel-backdrop.visible {
        background: rgba(0, 0, 0, 0.6);
        pointer-events: auto;
        backdrop-filter: blur(4px);
    }

    .floating-panel-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 12px 16px;
        border-bottom: 1px solid var(--border-subtle);
        flex-shrink: 0;
    }

    .floating-panel.expanded .floating-panel-header {
        padding: 16px 24px;
    }

    .floating-panel-title {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .floating-panel-icon {
        width: 28px;
        height: 28px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .floating-panel.expanded .floating-panel-icon {
        width: 36px;
        height: 36px;
        border-radius: 10px;
    }

    .floating-panel-name {
        font-size: 14px;
        font-weight: 600;
        color: var(--text-primary);
    }

    .floating-panel.expanded .floating-panel-name {
        font-size: 18px;
    }

    .floating-panel-actions {
        display: flex;
        align-items: center;
        gap: 4px;
    }

    .floating-panel-btn {
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: transparent;
        border: none;
        border-radius: 8px;
        color: var(--text-tertiary);
        cursor: pointer;
        transition: var(--motion-transition-interactive);
    }

    .floating-panel-btn:hover {
        background: rgba(255, 255, 255, 0.08);
        color: var(--text-primary);
    }

    .floating-panel-btn.expand-btn:hover {
        color: var(--accent);
    }

    .floating-panel-body {
        position: relative;
        flex: 1;
        min-height: 0;
        overflow-y: auto;
        padding: var(--space-4);
    }

    @media (max-width: 480px) {
        .floating-panel-body {
            padding: var(--space-2);
        }
    }
`;

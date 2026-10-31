/**
 * Общие стили модалок
 * Дизайн Apple Liquid Glass (iOS 26 / WWDC 2025)
 * Поддержка темной и светлой темы
 */
import { css } from 'lit';

export const modalStyles = css`
    :host {
        display: none;
        position: fixed;
        inset: 0;
        z-index: var(--platform-modal-layer-z, var(--z-modal));
    }
    
    :host([open]) {
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    /* Scrim без backdrop-filter — nested blur с panel даёт GPU flicker при scroll */
    .modal-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(0, 0, 0, 0.45);
        z-index: -1;
        animation: backdropFadeIn var(--modal-overlay-duration) var(--easing-smooth);
    }
    
    @keyframes backdropFadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    
    /* Контейнер Liquid Glass */
    .modal-container {
        position: relative;
        width: 90%;
        max-width: var(--modal-max-width, 500px);
        max-height: 90vh;
        display: flex;
        flex-direction: column;
        border-radius: var(--radius-3xl);
        overflow: visible;
        
        /* Solid glass surface — без backdrop-filter (flicker-safe) */
        background: var(--glass-solid-strong);
        border: 1px solid var(--glass-border-medium);
        
        /* Multi-layer shadows для глубины стекла */
        box-shadow: var(--glass-shadow-strong);
        
        animation: modalEnter var(--modal-panel-duration) var(--modal-panel-easing);
    }
    
    /* Псевдоэлемент liquid-блеска */
    .modal-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        border-radius: var(--radius-3xl);
        background: linear-gradient(
            160deg,
            rgba(255, 255, 255, 0.15) 0%,
            rgba(255, 255, 255, 0.05) 30%,
            transparent 60%
        );
        pointer-events: none;
        z-index: 1;
    }
    
    /* Верхний блик для liquid-эффекта */
    .modal-container::after {
        content: '';
        position: absolute;
        top: 0;
        left: var(--space-5);
        right: var(--space-5);
        height: 1px;
        background: linear-gradient(
            90deg,
            transparent 0%,
            rgba(255, 255, 255, 0.35) 20%,
            rgba(255, 255, 255, 0.35) 80%,
            transparent 100%
        );
        border-radius: var(--radius-3xl) var(--radius-3xl) 0 0;
        z-index: 2;
    }
    
    @keyframes modalEnter {
        from {
            opacity: 0;
            transform: scale(0.96) translateY(12px);
        }
        to {
            opacity: 1;
            transform: scale(1) translateY(0);
        }
    }
    
    /* Sizes */
    :host([size="sm"]) .modal-container { max-width: 400px; }
    :host([size="md"]) .modal-container { max-width: 500px; }
    :host([size="lg"]) .modal-container { max-width: 640px; }
    :host([size="xl"]) .modal-container { max-width: 800px; }
    
    :host([fullscreen]) .modal-container {
        width: 100%;
        height: 100%;
        max-width: none;
        max-height: none;
        border-radius: 0;
    }
    
    /* Header */
    .modal-header {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--space-4) var(--space-4) 0 var(--space-4);
        flex-shrink: 0;
        z-index: 3;
    }
    
    .modal-title {
        font-size: var(--text-xl);
        font-weight: var(--font-semibold);
        color: var(--text-primary);
        margin: 0;
        letter-spacing: var(--tracking-tight);
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    }
    
    .modal-actions {
        display: flex;
        align-items: center;
        gap: var(--space-2);
    }
    
    .modal-action-btn {
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-full);
        color: var(--text-secondary);
        background: var(--glass-tint-medium);
        border: none;
        cursor: pointer;
        transition: var(--motion-transition-interactive);
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
    }
    
    .modal-action-btn:hover {
        background: var(--glass-tint-strong);
        color: var(--text-primary);
        transform: scale(1.08);
    }
    
    /* Body */
    .modal-body {
        position: relative;
        flex: 1;
        overflow-y: auto;
        padding: var(--space-4);
        color: var(--text-primary);
        z-index: 3;
    }
    
    /* Footer */
    .modal-footer {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: var(--space-3);
        padding: 0 var(--space-4) var(--space-4) var(--space-4);
        flex-shrink: 0;
        z-index: 3;
    }
    
    /* Responsive */
    @media (max-width: 768px) {
        .modal-container {
            width: 95%;
            max-height: 95vh;
            border-radius: var(--radius-2xl);
        }
        
        .modal-header,
        .modal-body,
        .modal-footer {
            padding-left: var(--space-3);
            padding-right: var(--space-3);
        }
    }

    @media (max-width: 480px) {
        .modal-header,
        .modal-body,
        .modal-footer {
            padding-left: var(--space-2);
            padding-right: var(--space-2);
        }
    }

    /* Light Theme */
    :host-context([data-theme="light"]) .modal-backdrop {
        background: rgba(100, 100, 120, 0.4);
    }

    :host-context([data-theme="light"]) .modal-container {
        background: linear-gradient(
            145deg,
            rgba(255, 255, 255, 0.95) 0%,
            rgba(248, 250, 252, 0.98) 100%
        );
        border: 1px solid rgba(0, 0, 0, 0.06);
        box-shadow: 
            0 25px 60px rgba(0, 0, 0, 0.15),
            0 10px 25px rgba(0, 0, 0, 0.08),
            inset 0 1px 0 rgba(255, 255, 255, 1),
            inset 0 -1px 0 rgba(0, 0, 0, 0.03);
    }

    :host-context([data-theme="light"]) .modal-container::before {
        background: linear-gradient(
            135deg,
            rgba(255, 255, 255, 0.8) 0%,
            rgba(255, 255, 255, 0.2) 50%,
            transparent 100%
        );
    }

    :host-context([data-theme="light"]) .modal-container::after {
        background: linear-gradient(
            90deg,
            transparent 0%,
            rgba(255, 255, 255, 1) 20%,
            rgba(255, 255, 255, 1) 80%,
            transparent 100%
        );
    }

    :host-context([data-theme="light"]) .modal-title {
        text-shadow: none;
    }

    :host-context([data-theme="light"]) .modal-action-btn {
        background: rgba(15, 23, 42, 0.06);
        color: rgba(15, 23, 42, 0.5);
    }

    :host-context([data-theme="light"]) .modal-action-btn:hover {
        background: rgba(15, 23, 42, 0.12);
        color: rgba(15, 23, 42, 0.9);
    }
`;

export const modalUtilityStyles = css`
    /* Status Icons */
    .modal-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 64px;
        height: 64px;
        border-radius: var(--radius-full);
        flex-shrink: 0;
        font-size: var(--text-2xl);
        margin: 0 auto var(--space-4);
    }
    
    .modal-icon.warning {
        background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
        color: white;
        box-shadow: 
            0 8px 24px rgba(251, 191, 36, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .modal-icon.danger {
        background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%);
        color: white;
        box-shadow: 
            0 8px 24px rgba(244, 63, 94, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .modal-icon.info {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white;
        box-shadow: 
            0 8px 24px rgba(59, 130, 246, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .modal-icon.success {
        background: var(--accent-gradient);
        color: white;
        box-shadow: 
            0 8px 24px rgba(153, 166, 249, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .modal-subtitle {
        font-size: var(--text-sm);
        color: var(--text-tertiary);
        margin-top: var(--space-1);
    }
    
    .modal-message {
        font-size: var(--text-base);
        line-height: var(--leading-relaxed);
        color: var(--text-secondary);
        text-align: center;
    }
`;

/**
 * Кастомные модалки (Lit): классы .backdrop + .modal / .modal-box / .drawer / .panel.
 * Длительности и easing — через CSS-переменные из tokens.css.
 */
export const modalShellStyles = css`
    @keyframes platformModalBackdropIn {
        from {
            opacity: 0;
        }
        to {
            opacity: 1;
        }
    }

    @keyframes platformModalPanelIn {
        from {
            opacity: 0;
            transform: scale(0.96) translateY(12px);
        }
        to {
            opacity: 1;
            transform: scale(1) translateY(0);
        }
    }

    @keyframes platformDrawerIn {
        from {
            opacity: 0;
            transform: translateX(14px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }

    .backdrop:not(.modal-backdrop-no-animate) {
        animation: platformModalBackdropIn var(--modal-overlay-duration) var(--easing-smooth) both;
    }

    .modal,
    .modal-box {
        animation: platformModalPanelIn var(--modal-panel-duration) var(--modal-panel-easing) both;
    }

    .drawer {
        animation: platformDrawerIn var(--modal-panel-duration) var(--modal-panel-easing) both;
    }

    .panel {
        animation: platformModalPanelIn var(--modal-popover-duration) var(--modal-panel-easing) both;
    }

    @media (prefers-reduced-motion: reduce) {
        .backdrop:not(.modal-backdrop-no-animate),
        .modal,
        .modal-box,
        .drawer,
        .panel {
            animation-duration: 1ms !important;
        }
    }
`;

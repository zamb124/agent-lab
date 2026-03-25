/**
 * Shared Modal Styles
 * Apple Liquid Glass Design (iOS 26 / WWDC 2025)
 * Поддержка темной и светлой темы
 */
import { css } from 'lit';

export const modalStyles = css`
    :host {
        display: none;
        position: fixed;
        inset: 0;
        z-index: var(--platform-modal-layer-z, var(--z-modal, 1000));
    }
    
    :host([open]) {
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    /* Backdrop с размытием фона */
    .modal-backdrop {
        position: absolute;
        inset: 0;
        background: rgba(0, 0, 0, 0.2);
        backdrop-filter: blur(30px) saturate(200%);
        -webkit-backdrop-filter: blur(30px) saturate(200%);
        z-index: -1;
        animation: backdropFadeIn var(--modal-overlay-duration, var(--duration-normal)) var(--easing-smooth, ease-out);
    }
    
    @keyframes backdropFadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
    
    /* Liquid Glass Container */
    .modal-container {
        position: relative;
        width: 90%;
        max-width: var(--modal-max-width, 500px);
        max-height: 90vh;
        display: flex;
        flex-direction: column;
        border-radius: var(--radius-3xl, 28px);
        overflow: visible;
        
        /* Liquid Glass Effect - темная тема */
        background: var(--glass-solid-strong, rgba(40, 40, 64, 0.92));
        backdrop-filter: blur(var(--glass-blur-medium, 40px)) saturate(180%);
        -webkit-backdrop-filter: blur(var(--glass-blur-medium, 40px)) saturate(180%);
        border: 1px solid var(--glass-border-medium, rgba(255, 255, 255, 0.12));
        
        /* Multi-layer shadows для глубины стекла */
        box-shadow: var(--glass-shadow-strong,
            0 16px 48px rgba(0, 0, 0, 0.4),
            0 4px 16px rgba(0, 0, 0, 0.25));
        
        animation: modalEnter var(--modal-panel-duration, var(--duration-slow)) var(--modal-panel-easing, var(--easing-smooth));
    }
    
    /* Liquid shine pseudo-element */
    .modal-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        border-radius: var(--radius-3xl, 28px);
        background: linear-gradient(
            160deg,
            rgba(255, 255, 255, 0.15) 0%,
            rgba(255, 255, 255, 0.05) 30%,
            transparent 60%
        );
        pointer-events: none;
        z-index: 1;
    }
    
    /* Top highlight for liquid effect */
    .modal-container::after {
        content: '';
        position: absolute;
        top: 0;
        left: var(--space-5, 20px);
        right: var(--space-5, 20px);
        height: 1px;
        background: linear-gradient(
            90deg,
            transparent 0%,
            rgba(255, 255, 255, 0.35) 20%,
            rgba(255, 255, 255, 0.35) 80%,
            transparent 100%
        );
        border-radius: var(--radius-3xl, 28px) var(--radius-3xl, 28px) 0 0;
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
        padding: var(--space-4, 16px) var(--space-4, 16px) 0 var(--space-4, 16px);
        flex-shrink: 0;
        z-index: 3;
    }
    
    .modal-title {
        font-size: var(--text-xl, 22px);
        font-weight: var(--font-semibold, 600);
        color: var(--text-primary, rgba(255, 255, 255, 0.95));
        margin: 0;
        letter-spacing: var(--tracking-tight, -0.02em);
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    }
    
    .modal-actions {
        display: flex;
        align-items: center;
        gap: var(--space-2, 8px);
    }
    
    .modal-action-btn {
        width: 28px;
        height: 28px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: var(--radius-full, 50%);
        color: var(--text-secondary, rgba(255, 255, 255, 0.6));
        background: var(--glass-tint-medium, rgba(255, 255, 255, 0.08));
        border: none;
        cursor: pointer;
        transition: all var(--duration-fast, 0.2s) ease;
        font-size: var(--text-xs, 12px);
        font-weight: var(--font-semibold, 600);
        backdrop-filter: blur(10px);
    }
    
    .modal-action-btn:hover {
        background: var(--glass-tint-strong, rgba(255, 255, 255, 0.15));
        color: var(--text-primary, rgba(255, 255, 255, 0.9));
        transform: scale(1.08);
    }
    
    /* Body */
    .modal-body {
        position: relative;
        flex: 1;
        overflow-y: auto;
        padding: var(--space-4, 16px);
        color: var(--text-primary, rgba(255, 255, 255, 0.85));
        z-index: 3;
    }
    
    /* Footer */
    .modal-footer {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: flex-end;
        gap: var(--space-3, 12px);
        padding: 0 var(--space-4, 16px) var(--space-4, 16px) var(--space-4, 16px);
        flex-shrink: 0;
        z-index: 3;
    }
    
    /* Responsive */
    @media (max-width: 768px) {
        .modal-container {
            width: 95%;
            max-height: 95vh;
            border-radius: var(--radius-2xl, 24px);
        }
        
        .modal-header,
        .modal-body,
        .modal-footer {
            padding-left: var(--space-3, 12px);
            padding-right: var(--space-3, 12px);
        }
    }

    @media (max-width: 480px) {
        .modal-header,
        .modal-body,
        .modal-footer {
            padding-left: var(--space-2, 8px);
            padding-right: var(--space-2, 8px);
        }
    }

    /* Light Theme */
    :host-context([data-theme="light"]) .modal-backdrop {
        background: rgba(100, 100, 120, 0.25);
        backdrop-filter: blur(20px) saturate(120%);
        -webkit-backdrop-filter: blur(20px) saturate(120%);
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
        border-radius: var(--radius-full, 50%);
        flex-shrink: 0;
        font-size: var(--text-2xl, 28px);
        margin: 0 auto var(--space-4, 16px);
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
        background: linear-gradient(135deg, #10b981 0%, #059669 100%);
        color: white;
        box-shadow: 
            0 8px 24px rgba(16, 185, 129, 0.35),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .modal-subtitle {
        font-size: var(--text-sm, 14px);
        color: var(--text-tertiary, rgba(255, 255, 255, 0.5));
        margin-top: var(--space-1, 4px);
    }
    
    .modal-message {
        font-size: var(--text-base, 15px);
        line-height: var(--leading-relaxed, 1.6);
        color: var(--text-secondary, rgba(255, 255, 255, 0.65));
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
        animation: platformModalBackdropIn var(--modal-overlay-duration, var(--duration-normal)) var(--easing-smooth, ease-out) both;
    }

    .modal,
    .modal-box {
        animation: platformModalPanelIn var(--modal-panel-duration, var(--duration-slow)) var(--modal-panel-easing, var(--easing-smooth)) both;
    }

    .drawer {
        animation: platformDrawerIn var(--modal-panel-duration, var(--duration-slow)) var(--modal-panel-easing, var(--easing-smooth)) both;
    }

    .panel {
        animation: platformModalPanelIn var(--modal-popover-duration, var(--duration-fast)) var(--modal-panel-easing, var(--easing-smooth)) both;
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

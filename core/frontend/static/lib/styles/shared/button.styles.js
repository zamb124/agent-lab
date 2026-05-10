/**
 * Shared Button Styles
 * Humanitec UI Kit — violet primary, orange accent, pill shape
 * Поддержка темной и светлой темы
 */
import { css } from '../../../assets/js/lit/lit.min.js';

export const buttonStyles = css`
    .btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-2, 8px);
        padding: var(--btn-padding, 8px 24px);
        font-size: var(--btn-font-size, 16px);
        font-weight: var(--btn-font-weight, 400);
        font-family: inherit;
        line-height: var(--btn-line-height, 20px);
        border-radius: var(--btn-radius, 22px);
        border: none;
        cursor: pointer;
        transition: all var(--duration-fast, 0.15s) ease;
        text-decoration: none;
        user-select: none;
        white-space: nowrap;
    }
    
    .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
        pointer-events: none;
    }
    
    /* Primary Button — violet */
    .btn-primary,
    .btn.primary {
        color: var(--platform-btn-primary-text, #ffffff);
        background: var(--platform-btn-primary-bg, #99A6F9);
        box-shadow: var(--platform-btn-primary-shadow, none);
    }
    
    .btn-primary:hover:not(:disabled),
    .btn.primary:hover:not(:disabled) {
        background: var(--platform-btn-primary-bg-hover, #8794F0);
        box-shadow: var(--platform-btn-primary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.6));
    }

    .btn-primary:active:not(:disabled),
    .btn.primary:active:not(:disabled) {
        transform: translateY(0);
    }

    /* Accent Button — orange */
    .btn-accent,
    .btn.accent {
        color: var(--platform-btn-accent-text, #ffffff);
        background: var(--platform-btn-accent-bg, #FF885C);
        box-shadow: var(--platform-btn-accent-shadow, none);
    }

    .btn-accent:hover:not(:disabled),
    .btn.accent:hover:not(:disabled) {
        background: var(--platform-btn-accent-bg-hover, #F2784A);
        box-shadow: var(--platform-btn-accent-shadow-hover, 0 0 10px rgba(255, 136, 92, 0.6));
    }

    .btn-accent:active:not(:disabled),
    .btn.accent:active:not(:disabled) {
        transform: translateY(0);
    }
    
    /* Secondary Button — violet text, transparent bg */
    .btn-secondary,
    .btn.secondary {
        color: var(--platform-btn-secondary-text, #99A6F9);
        background: var(--platform-btn-secondary-bg, rgba(153, 166, 249, 0.15));
        border: none;
    }
    
    .btn-secondary:hover:not(:disabled),
    .btn.secondary:hover:not(:disabled) {
        background: var(--platform-btn-secondary-bg-hover, rgba(153, 166, 249, 0.1));
        box-shadow: var(--platform-btn-secondary-shadow-hover, 0 0 10px rgba(153, 166, 249, 0.2));
    }

    /* Accent Secondary — orange text, transparent bg */
    .btn-accent-secondary,
    .btn.accent-secondary {
        color: var(--platform-btn-accent-secondary-text, #FF9A76);
        background: var(--platform-btn-accent-secondary-bg, rgba(255, 136, 92, 0.15));
        border: none;
    }

    .btn-accent-secondary:hover:not(:disabled),
    .btn.accent-secondary:hover:not(:disabled) {
        background: var(--platform-btn-accent-secondary-bg-hover, rgba(255, 136, 92, 0.1));
        box-shadow: var(--platform-btn-accent-secondary-shadow-hover, 0 0 10px rgba(255, 136, 92, 0.2));
    }
    
    /* Danger Button */
    .btn-danger,
    .btn.danger {
        color: white;
        background: var(--error, #f43f5e);
        box-shadow: 0 4px 12px rgba(244, 63, 94, 0.25);
    }
    
    .btn-danger:hover:not(:disabled),
    .btn.danger:hover:not(:disabled) {
        background: #e11d48;
        box-shadow: 0 0 10px rgba(244, 63, 94, 0.4);
    }
    
    /* Ghost Button */
    .btn-ghost,
    .btn.ghost {
        color: var(--text-secondary, rgba(255, 255, 255, 0.65));
        background: transparent;
        padding: var(--space-3, 12px) var(--space-4, 16px);
    }
    
    .btn-ghost:hover:not(:disabled),
    .btn.ghost:hover:not(:disabled) {
        color: var(--text-primary, rgba(255, 255, 255, 0.95));
        background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
    }
    
    /* Sizes */
    .btn.sm {
        padding: 6px 16px;
        font-size: var(--text-sm, 14px);
    }
    
    .btn.md {
        padding: var(--btn-padding, 8px 24px);
        font-size: var(--btn-font-size, 16px);
    }
    
    .btn.lg {
        padding: 10px 32px;
        font-size: var(--text-lg, 18px);
    }
    
    .btn.icon-only {
        padding: var(--space-3, 12px);
        aspect-ratio: 1;
    }
    
    /* Loading state */
    .btn.loading {
        position: relative;
        color: transparent;
        pointer-events: none;
    }
    
    .btn.loading::after {
        content: '';
        position: absolute;
        width: 18px;
        height: 18px;
        border: 2px solid currentColor;
        border-right-color: transparent;
        border-radius: var(--radius-full, 50%);
        animation: spin 0.6s linear infinite;
    }

    .btn-primary.loading::after,
    .btn.primary.loading::after,
    .btn-accent.loading::after,
    .btn.accent.loading::after,
    .btn-danger.loading::after,
    .btn.danger.loading::after {
        border-color: white;
        border-right-color: transparent;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .btn-group {
        display: flex;
        gap: var(--space-3, 12px);
    }
    
    .btn-group.vertical {
        flex-direction: column;
    }
    
    /* Responsive - Mobile */
    @media (max-width: 480px) {
        .btn {
            padding: 6px 16px;
            font-size: var(--text-sm, 14px);
        }
        
        .btn.lg {
            padding: var(--btn-padding, 8px 24px);
            font-size: var(--btn-font-size, 16px);
        }
    }

    /* Light Theme */
    :host-context([data-theme="light"]) .btn-secondary,
    :host-context([data-theme="light"]) .btn.secondary {
        color: var(--platform-btn-secondary-text, #8794F0);
        background: var(--platform-btn-secondary-bg, rgba(135, 148, 240, 0.12));
    }

    :host-context([data-theme="light"]) .btn-secondary:hover:not(:disabled),
    :host-context([data-theme="light"]) .btn.secondary:hover:not(:disabled) {
        background: var(--platform-btn-secondary-bg-hover, rgba(135, 148, 240, 0.08));
    }

    :host-context([data-theme="light"]) .btn-ghost,
    :host-context([data-theme="light"]) .btn.ghost {
        color: rgba(15, 23, 42, 0.6);
    }

    :host-context([data-theme="light"]) .btn-ghost:hover:not(:disabled),
    :host-context([data-theme="light"]) .btn.ghost:hover:not(:disabled) {
        color: rgba(15, 23, 42, 0.9);
        background: rgba(15, 23, 42, 0.05);
    }
`;

export const iconButtonStyles = css`
    .btn-icon {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        padding: 0;
        border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
        border-radius: var(--radius-sm, 10px);
        color: var(--text-secondary, rgba(255, 255, 255, 0.65));
        background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
        cursor: pointer;
        transition: all var(--duration-fast, 0.15s) ease;
    }
    
    .btn-icon:hover:not(:disabled) {
        color: var(--text-primary, rgba(255, 255, 255, 0.95));
        background: var(--glass-tint-medium, rgba(255, 255, 255, 0.05));
        border-color: var(--border-strong, rgba(255, 255, 255, 0.15));
    }
    
    .btn-icon:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    
    .btn-icon.sm {
        width: 28px;
        height: 28px;
        border-radius: var(--radius-sm, 8px);
    }
    
    .btn-icon.lg {
        width: 44px;
        height: 44px;
        border-radius: var(--radius-md, 12px);
    }
    
    .btn-icon.primary {
        color: var(--accent, #99A6F9);
        border-color: rgba(153, 166, 249, 0.2);
    }
    
    .btn-icon.primary:hover:not(:disabled) {
        color: var(--accent-hover, #8794F0);
        background: var(--accent-subtle, rgba(153, 166, 249, 0.15));
        border-color: rgba(153, 166, 249, 0.3);
    }

    .btn-icon.accent {
        color: var(--accent-secondary, #FF885C);
        border-color: rgba(255, 136, 92, 0.2);
    }

    .btn-icon.accent:hover:not(:disabled) {
        color: var(--accent-secondary-hover, #F2784A);
        background: var(--accent-secondary-subtle, rgba(255, 136, 92, 0.15));
        border-color: rgba(255, 136, 92, 0.3);
    }
    
    .btn-icon.danger {
        color: var(--error, #f43f5e);
        border-color: rgba(244, 63, 94, 0.2);
    }
    
    .btn-icon.danger:hover:not(:disabled) {
        color: #e11d48;
        background: rgba(244, 63, 94, 0.1);
        border-color: rgba(244, 63, 94, 0.3);
    }

    /* Light Theme */
    :host-context([data-theme="light"]) .btn-icon {
        color: rgba(15, 23, 42, 0.6);
        background: rgba(255, 255, 255, 0.6);
        border-color: rgba(15, 23, 42, 0.1);
    }

    :host-context([data-theme="light"]) .btn-icon:hover:not(:disabled) {
        color: rgba(15, 23, 42, 0.9);
        background: rgba(255, 255, 255, 0.9);
        border-color: rgba(15, 23, 42, 0.15);
    }
`;

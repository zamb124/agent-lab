/**
 * Shared Button Styles
 * Apple Vision Pro Glass Design (2025)
 * Поддержка темной и светлой темы
 */
import { css } from 'lit';

export const buttonStyles = css`
    .btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-2, 8px);
        padding: var(--space-3, 14px) var(--space-6, 24px);
        font-size: var(--text-base, 16px);
        font-weight: var(--font-semibold, 600);
        font-family: inherit;
        border-radius: var(--radius-lg, 14px);
        border: none;
        cursor: pointer;
        transition: all var(--duration-fast, 0.2s) ease;
        text-decoration: none;
        user-select: none;
        white-space: nowrap;
    }
    
    .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
        pointer-events: none;
    }
    
    /* Primary Button - Accent Gradient */
    .btn-primary,
    .btn.primary {
        color: var(--btn-primary-text, white);
        background: var(--btn-primary-bg, linear-gradient(135deg, #10b981 0%, #059669 100%));
        box-shadow: var(--btn-primary-shadow, 0 4px 12px rgba(16, 185, 129, 0.25));
    }
    
    .btn-primary:hover:not(:disabled),
    .btn.primary:hover:not(:disabled) {
        transform: translateY(-1px);
        background: var(--btn-primary-hover-bg, var(--btn-primary-bg, linear-gradient(135deg, #10b981 0%, #059669 100%)));
        box-shadow: var(--btn-primary-hover-shadow, 0 6px 20px rgba(16, 185, 129, 0.35));
    }

    .btn-primary:active:not(:disabled),
    .btn.primary:active:not(:disabled) {
        transform: translateY(0);
    }
    
    /* Secondary Button */
    .btn-secondary,
    .btn.secondary {
        color: var(--btn-secondary-text, var(--text-secondary, rgba(255, 255, 255, 0.65)));
        background: var(--btn-secondary-bg, var(--glass-tint-medium, rgba(255, 255, 255, 0.05)));
        border: 1px solid var(--btn-secondary-border, var(--border-default, rgba(255, 255, 255, 0.1)));
    }
    
    .btn-secondary:hover:not(:disabled),
    .btn.secondary:hover:not(:disabled) {
        background: var(--btn-secondary-hover-bg, var(--glass-tint-strong, rgba(255, 255, 255, 0.08)));
        border-color: var(--btn-secondary-hover-border, var(--border-strong, rgba(255, 255, 255, 0.15)));
        color: var(--btn-secondary-hover-text, var(--btn-secondary-text, var(--text-secondary, rgba(255, 255, 255, 0.65))));
    }
    
    /* Danger Button - Red Gradient */
    .btn-danger,
    .btn.danger {
        color: white;
        background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%);
        box-shadow: 0 4px 12px rgba(244, 63, 94, 0.25);
    }
    
    .btn-danger:hover:not(:disabled),
    .btn.danger:hover:not(:disabled) {
        transform: translateY(-1px);
        box-shadow: 0 6px 20px rgba(244, 63, 94, 0.35);
    }
    
    /* Ghost Button - Transparent */
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
        padding: var(--space-2, 10px) var(--space-4, 16px);
        font-size: var(--text-sm, 14px);
        border-radius: var(--radius-sm, 10px);
    }
    
    .btn.md {
        padding: var(--space-3, 14px) var(--space-6, 24px);
        font-size: var(--text-base, 16px);
    }
    
    .btn.lg {
        padding: var(--space-4, 16px) var(--space-8, 32px);
        font-size: var(--text-lg, 18px);
        border-radius: var(--radius-xl, 16px);
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
            padding: var(--space-3, 12px) var(--space-4, 16px);
            font-size: var(--text-sm, 14px);
        }
        
        .btn.lg {
            padding: var(--space-3, 14px) var(--space-6, 24px);
            font-size: var(--text-base, 16px);
        }
    }

    /* Light Theme */
    :host-context([data-theme="light"]) .btn-secondary,
    :host-context([data-theme="light"]) .btn.secondary {
        color: var(--btn-secondary-text, rgba(15, 23, 42, 0.7));
        background: var(--btn-secondary-bg, rgba(255, 255, 255, 0.6));
        border-color: var(--btn-secondary-border, rgba(15, 23, 42, 0.1));
    }

    :host-context([data-theme="light"]) .btn-secondary:hover:not(:disabled),
    :host-context([data-theme="light"]) .btn.secondary:hover:not(:disabled) {
        background: var(--btn-secondary-hover-bg, rgba(255, 255, 255, 0.9));
        border-color: var(--btn-secondary-hover-border, rgba(15, 23, 42, 0.15));
        color: var(--btn-secondary-hover-text, var(--btn-secondary-text, rgba(15, 23, 42, 0.7)));
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
        transition: all var(--duration-fast, 0.2s) ease;
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
        color: var(--accent, #10b981);
        border-color: rgba(16, 185, 129, 0.2);
    }
    
    .btn-icon.primary:hover:not(:disabled) {
        color: var(--accent-hover, #34d399);
        background: var(--accent-subtle, rgba(16, 185, 129, 0.15));
        border-color: rgba(16, 185, 129, 0.3);
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

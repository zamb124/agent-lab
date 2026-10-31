/**
 * Общие стили кнопок
 * Linnex UI Kit — фиолетовый primary, оранжевый accent, форма pill
 * Поддержка темной и светлой темы
 */
import { css } from 'lit';

export const buttonStyles = css`
    .btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: var(--space-2);
        padding: var(--btn-padding);
        font-size: var(--btn-font-size);
        font-weight: var(--btn-font-weight);
        font-family: inherit;
        line-height: var(--btn-line-height);
        border-radius: var(--btn-radius);
        border: none;
        cursor: pointer;
        transition: var(--motion-transition-interactive);
        text-decoration: none;
        user-select: none;
        white-space: nowrap;
    }
    
    .btn:disabled {
        opacity: 0.5;
        cursor: not-allowed;
        pointer-events: none;
    }
    
    /* Основная кнопка — фиолетовая */
    .btn-primary,
    .btn.primary,
    a.btn-primary:any-link,
    a.btn.primary:any-link {
        color: var(--platform-btn-primary-text);
        -webkit-text-fill-color: currentColor;
        background: var(--platform-btn-primary-bg);
        box-shadow: var(--platform-btn-primary-shadow);
    }
    
    .btn-primary:hover:not(:disabled),
    .btn.primary:hover:not(:disabled),
    a.btn-primary:any-link:hover,
    a.btn.primary:any-link:hover {
        color: var(--platform-btn-primary-text);
        background: var(--platform-btn-primary-bg-hover);
        box-shadow: var(--platform-btn-primary-shadow-hover);
    }

    .btn-primary:active:not(:disabled),
    .btn.primary:active:not(:disabled) {
        transform: translateY(0);
    }

    /* Акцентная кнопка — оранжевая */
    .btn-accent,
    .btn.accent {
        color: var(--platform-btn-accent-text);
        background: var(--platform-btn-accent-bg);
        box-shadow: var(--platform-btn-accent-shadow);
    }

    .btn-accent:hover:not(:disabled),
    .btn.accent:hover:not(:disabled) {
        background: var(--platform-btn-accent-bg-hover);
        box-shadow: var(--platform-btn-accent-shadow-hover);
    }

    .btn-accent:active:not(:disabled),
    .btn.accent:active:not(:disabled) {
        transform: translateY(0);
    }
    
    /* Вторичная кнопка — фиолетовый текст, прозрачный фон */
    .btn-secondary,
    .btn.secondary {
        color: var(--platform-btn-secondary-text);
        background: var(--platform-btn-secondary-bg);
        border: none;
    }
    
    .btn-secondary:hover:not(:disabled),
    .btn.secondary:hover:not(:disabled) {
        background: var(--platform-btn-secondary-bg-hover);
        box-shadow: var(--platform-btn-secondary-shadow-hover);
    }

    /* Accent Secondary — orange text, transparent bg */
    .btn-accent-secondary,
    .btn.accent-secondary {
        color: var(--platform-btn-accent-secondary-text);
        background: var(--platform-btn-accent-secondary-bg);
        border: none;
    }

    .btn-accent-secondary:hover:not(:disabled),
    .btn.accent-secondary:hover:not(:disabled) {
        background: var(--platform-btn-accent-secondary-bg-hover);
        box-shadow: var(--platform-btn-accent-secondary-shadow-hover);
    }
    
    /* Опасная кнопка */
    .btn-danger,
    .btn.danger {
        color: white;
        background: var(--error);
        box-shadow: 0 4px 12px rgba(244, 63, 94, 0.25);
    }
    
    .btn-danger:hover:not(:disabled),
    .btn.danger:hover:not(:disabled) {
        background: #e11d48;
        box-shadow: 0 0 10px rgba(244, 63, 94, 0.4);
    }
    
    /* Прозрачная кнопка */
    .btn-ghost,
    .btn.ghost {
        color: var(--text-secondary);
        background: transparent;
        padding: var(--space-3) var(--space-4);
    }
    
    .btn-ghost:hover:not(:disabled),
    .btn.ghost:hover:not(:disabled) {
        color: var(--text-primary);
        background: var(--glass-tint-subtle);
    }
    
    /* Sizes */
    .btn.sm {
        padding: 6px 16px;
        font-size: var(--text-sm);
    }
    
    .btn.md {
        padding: var(--btn-padding);
        font-size: var(--btn-font-size);
    }
    
    .btn.lg {
        padding: 10px 32px;
        font-size: var(--text-lg);
    }
    
    .btn.icon-only {
        padding: var(--space-3);
        aspect-ratio: 1;
    }
    
    /* Состояние загрузки */
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
        border-radius: var(--radius-full);
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
        gap: var(--space-3);
    }
    
    .btn-group.vertical {
        flex-direction: column;
    }
    
    /* Responsive - Mobile */
    @media (max-width: 480px) {
        .btn {
            padding: 6px 16px;
            font-size: var(--text-sm);
        }
        
        .btn.lg {
            padding: var(--btn-padding);
            font-size: var(--btn-font-size);
        }
    }

    /* Light Theme */
    :host-context([data-theme="light"]) .btn-secondary,
    :host-context([data-theme="light"]) .btn.secondary {
        color: var(--platform-btn-secondary-text);
        background: var(--platform-btn-secondary-bg);
    }

    :host-context([data-theme="light"]) .btn-secondary:hover:not(:disabled),
    :host-context([data-theme="light"]) .btn.secondary:hover:not(:disabled) {
        background: var(--platform-btn-secondary-bg-hover);
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
        border: 1px solid var(--border-default);
        border-radius: var(--radius-sm);
        color: var(--text-secondary);
        background: var(--glass-tint-subtle);
        cursor: pointer;
        transition: var(--motion-transition-interactive);
    }
    
    .btn-icon:hover:not(:disabled) {
        color: var(--text-primary);
        background: var(--glass-tint-medium);
        border-color: var(--border-strong);
    }
    
    .btn-icon:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    
    .btn-icon.sm {
        width: 28px;
        height: 28px;
        border-radius: var(--radius-sm);
    }
    
    .btn-icon.lg {
        width: 44px;
        height: 44px;
        border-radius: var(--radius-md);
    }
    
    .btn-icon.primary {
        color: var(--accent);
        border-color: rgba(153, 166, 249, 0.2);
    }
    
    .btn-icon.primary:hover:not(:disabled) {
        color: var(--accent-hover);
        background: var(--accent-subtle);
        border-color: rgba(153, 166, 249, 0.3);
    }

    .btn-icon.accent {
        color: var(--accent-secondary);
        border-color: rgba(255, 136, 92, 0.2);
    }

    .btn-icon.accent:hover:not(:disabled) {
        color: var(--accent-secondary-hover);
        background: var(--accent-secondary-subtle);
        border-color: rgba(255, 136, 92, 0.3);
    }
    
    .btn-icon.danger {
        color: var(--error);
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

/**
 * Shared Form Styles
 * Apple Vision Pro Glass Design (2025)
 * Поддержка темной и светлой темы
 */
import { css } from 'lit';

export const formStyles = css`
    .form-group {
        display: flex;
        flex-direction: column;
        margin-bottom: var(--space-5, 20px);
    }
    
    .form-group:last-child {
        margin-bottom: 0;
    }
    
    .form-label {
        display: block;
        font-size: var(--text-xs, 12px);
        font-weight: var(--font-semibold, 600);
        color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
        margin-bottom: var(--space-2, 8px);
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    
    .form-label-text {
        font-size: var(--text-sm, 14px);
        font-weight: var(--font-medium, 500);
        color: var(--text-primary, rgba(255, 255, 255, 0.95));
    }

    /* Лейбл и platform-help-hint в одну строку; «?» всегда справа от текста */
    .form-label.form-label-inline {
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        align-items: center;
        gap: var(--space-2, 8px);
    }

    .form-label-inline .form-label-inline-text {
        min-width: 0;
        flex: 1 1 auto;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }

    .form-label-inline platform-help-hint {
        flex-shrink: 0;
    }
    
    .form-label-hint {
        font-size: var(--text-xs, 12px);
        color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
        font-weight: var(--font-normal, 400);
        text-transform: none;
        letter-spacing: normal;
        margin-left: var(--space-2, 8px);
    }
    
    .form-hint {
        font-size: var(--text-xs, 12px);
        color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
        margin-top: var(--space-2, 6px);
    }
    
    .form-error {
        margin-top: var(--space-2, 6px);
        font-size: var(--text-sm, 13px);
        color: var(--error, #f43f5e);
    }
    
    .form-input,
    .form-select,
    .form-textarea {
        width: 100%;
        padding: var(--space-3, 14px) var(--space-4, 16px);
        font-size: var(--text-base, 15px);
        color: var(--text-primary, rgba(255, 255, 255, 0.95));
        background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.06) 0%, rgba(255, 255, 255, 0.02) 100%),
            var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
        border: 1px solid var(--border-default, rgba(255, 255, 255, 0.1));
        border-radius: var(--radius-lg, 16px);
        outline: none;
        transition: all var(--duration-fast, 0.2s) ease;
        font-family: inherit;
        box-sizing: border-box;
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.08),
            0 8px 24px rgba(0, 0, 0, 0.12);
        -webkit-backdrop-filter: blur(8px);
        backdrop-filter: blur(8px);
    }
    
    .form-input::placeholder,
    .form-textarea::placeholder {
        color: var(--text-disabled, rgba(255, 255, 255, 0.25));
    }
    
    .form-input:focus,
    .form-select:focus,
    .form-textarea:focus {
        background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0.04) 100%),
            var(--glass-tint-medium, rgba(255, 255, 255, 0.05));
        border-color: var(--border-focus, var(--accent));
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.16),
            0 0 0 3px color-mix(in srgb, var(--accent) 25%, transparent),
            0 10px 28px rgba(0, 0, 0, 0.16);
    }
    
    .form-input:disabled,
    .form-select:disabled,
    .form-textarea:disabled {
        opacity: 0.5;
        cursor: not-allowed;
    }
    
    .form-input.readonly {
        background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.02));
        color: var(--text-secondary, rgba(255, 255, 255, 0.65));
        cursor: default;
    }

    :host-context([data-theme="light"]) .form-input,
    :host-context([data-theme="light"]) .form-select,
    :host-context([data-theme="light"]) .form-textarea {
        color: #222222;
        background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.88) 0%, rgba(255, 255, 255, 0.72) 100%),
            rgba(34, 34, 34, 0.02);
        border: 1px solid rgba(34, 34, 34, 0.1);
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 0.95),
            0 6px 18px rgba(34, 34, 34, 0.08);
    }

    :host-context([data-theme="light"]) .form-input::placeholder,
    :host-context([data-theme="light"]) .form-textarea::placeholder {
        color: rgba(34, 34, 34, 0.35);
    }

    :host-context([data-theme="light"]) .form-input:focus,
    :host-context([data-theme="light"]) .form-select:focus,
    :host-context([data-theme="light"]) .form-textarea:focus {
        background:
            linear-gradient(180deg, rgba(255, 255, 255, 0.98) 0%, rgba(255, 255, 255, 0.86) 100%),
            rgba(153, 166, 249, 0.08);
        border-color: #99a6f9;
        box-shadow:
            inset 0 1px 0 rgba(255, 255, 255, 1),
            0 0 0 3px rgba(153, 166, 249, 0.2),
            0 8px 22px rgba(153, 166, 249, 0.18);
    }
    
    .form-select {
        appearance: none;
        cursor: pointer;
        padding-right: 40px;
        background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23999' d='M6 8L1 3h10z'/%3E%3C/svg%3E");
        background-repeat: no-repeat;
        background-position: right var(--space-4, 16px) center;
    }
    
    .form-textarea {
        min-height: 100px;
        resize: vertical;
        line-height: var(--leading-normal, 1.5);
    }
    
    .form-toggle {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--space-2, 8px) 0;
    }
    
    .toggle-switch {
        position: relative;
        width: 50px;
        height: 28px;
        background: var(--glass-tint-strong, rgba(255, 255, 255, 0.08));
        border-radius: var(--radius-full, 14px);
        cursor: pointer;
        transition: background var(--duration-fast, 0.2s) ease;
        flex-shrink: 0;
    }
    
    .toggle-switch.active {
        background: var(--accent-gradient);
    }
    
    .toggle-switch::after {
        content: '';
        position: absolute;
        top: 2px;
        left: 2px;
        width: 24px;
        height: 24px;
        background: white;
        border-radius: var(--radius-full, 50%);
        transition: transform var(--duration-fast, 0.2s) ease;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    }
    
    .toggle-switch.active::after {
        transform: translateX(22px);
    }
    
    .form-item {
        display: flex;
        align-items: center;
        gap: var(--space-3, 14px);
        padding: var(--space-3, 14px) var(--space-4, 16px);
        background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
        border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
        border-radius: var(--radius-md, 12px);
        cursor: pointer;
        transition: all var(--duration-fast, 0.2s) ease;
    }

    .form-item:hover {
        background: var(--glass-tint-medium, rgba(255, 255, 255, 0.05));
        border-color: var(--border-default, rgba(255, 255, 255, 0.1));
    }

    .form-item.selected {
        background: var(--accent-subtle, rgba(153, 166, 249, 0.15));
        border-color: rgba(153, 166, 249, 0.3);
    }

    .form-checkbox {
        width: 20px;
        height: 20px;
        border: 1.5px solid var(--border-default, rgba(255, 255, 255, 0.1));
        border-radius: var(--radius-sm, 6px);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all var(--duration-fast, 0.2s) ease;
        flex-shrink: 0;
        font-size: 11px;
        color: white;
        background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
    }

    .form-item.selected .form-checkbox {
        background: var(--accent);
        border-color: var(--accent);
    }

    .form-item-content {
        flex: 1;
    }

    .form-item-title {
        font-size: var(--text-base, 15px);
        font-weight: var(--font-medium, 500);
        color: var(--text-primary, rgba(255, 255, 255, 0.95));
        margin-bottom: 2px;
    }

    .form-item-description {
        font-size: var(--text-sm, 13px);
        color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
    }
    
    .form-section {
        padding: var(--space-4, 16px);
        background: var(--glass-tint-subtle, rgba(255, 255, 255, 0.03));
        border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
        border-radius: var(--radius-md, 12px);
        margin-bottom: var(--space-5, 20px);
    }
    
    .form-section-title {
        margin-bottom: var(--space-3, 12px);
        font-size: var(--text-xs, 12px);
        font-weight: var(--font-semibold, 600);
        color: var(--text-tertiary, rgba(255, 255, 255, 0.45));
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    
    .form-layout {
        display: grid;
        grid-template-columns: 280px 1fr;
        gap: var(--space-6, 24px);
        min-height: 400px;
    }

    .form-layout:has(code-editor.fullscreen),
    .form-layout:has(json-field-editor.fullscreen) {
        grid-template-columns: 1fr;
    }

    .form-layout:has(code-editor.fullscreen) .form-sidebar,
    .form-layout:has(json-field-editor.fullscreen) .form-sidebar {
        display: none;
    }
    
    /* Responsive - Tablet */
    @media (max-width: 900px) {
        .form-layout {
            grid-template-columns: 1fr;
        }
    }
    
    /* Responsive - Mobile */
    @media (max-width: 480px) {
        .form-input,
        .form-select,
        .form-textarea {
            padding: var(--space-3, 12px) var(--space-3, 14px);
            font-size: var(--text-sm, 14px);
        }
    }
    
    .form-sidebar {
        display: flex;
        flex-direction: column;
        gap: var(--space-4, 16px);
    }
    
    .form-main {
        display: flex;
        flex-direction: column;
        gap: var(--space-4, 16px);
    }
    
    .form-actions {
        display: flex;
        gap: var(--space-3, 12px);
        justify-content: flex-end;
        padding-top: var(--space-5, 20px);
        border-top: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.06));
        margin-top: var(--space-5, 20px);
    }
`;

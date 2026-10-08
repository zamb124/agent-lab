/**
 * Shared Form Styles — остательные паттерны форм (sections, toggle, layout).
 * Контентные поля: fieldPillStyles (классы .field-pill / .form-group / .form-input).
 */
import { css } from '../../../assets/js/lit/lit.min.js';
import { fieldPillStyles } from './field-pill.styles.js';

const formAuxStyles = css`
    .form-label-text {
        font-size: var(--text-sm);
        font-weight: var(--font-medium);
        color: var(--text-primary);
    }

    .form-label.form-label-inline {
        display: flex;
        flex-direction: row;
        flex-wrap: nowrap;
        align-items: center;
        gap: var(--space-2);
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
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        font-weight: var(--font-normal);
        text-transform: none;
        letter-spacing: normal;
        margin-left: var(--space-2);
    }

    .form-hint {
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        margin-top: var(--space-2);
    }

    .form-error {
        margin-top: var(--space-2);
        font-size: var(--text-sm);
        color: var(--error);
    }

    :host-context([data-theme="light"]) .field-pill-input::placeholder,
    :host-context([data-theme="light"]) .field-pill-textarea::placeholder,
    :host-context([data-theme="light"]) .form-input::placeholder,
    :host-context([data-theme="light"]) .form-textarea::placeholder {
        color: rgba(34, 34, 34, 0.35);
    }

    .form-toggle {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: var(--space-2) 0;
    }

    .toggle-switch {
        position: relative;
        width: 50px;
        height: 28px;
        background: var(--glass-tint-strong);
        border-radius: var(--radius-full);
        cursor: pointer;
        transition: background var(--duration-fast) ease;
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
        border-radius: var(--radius-full);
        transition: transform var(--duration-fast) ease;
        box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    }

    .toggle-switch.active::after {
        transform: translateX(22px);
    }

    .form-item {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        padding: var(--space-3) var(--space-4);
        background: var(--glass-tint-subtle);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        cursor: pointer;
        transition: var(--motion-transition-interactive);
    }

    .form-item:hover {
        background: var(--glass-tint-medium);
        border-color: var(--border-default);
    }

    .form-item.selected {
        background: var(--accent-subtle);
        border-color: rgba(153, 166, 249, 0.3);
    }

    .form-checkbox {
        width: 20px;
        height: 20px;
        border: 1.5px solid var(--border-default);
        border-radius: var(--radius-sm);
        display: flex;
        align-items: center;
        justify-content: center;
        transition: var(--motion-transition-interactive);
        flex-shrink: 0;
        font-size: 11px;
        color: white;
        background: var(--glass-tint-subtle);
    }

    .form-item.selected .form-checkbox {
        background: var(--accent);
        border-color: var(--accent);
    }

    .form-item-content {
        flex: 1;
    }

    .form-item-title {
        font-size: var(--text-base);
        font-weight: var(--font-medium);
        color: var(--text-primary);
        margin-bottom: 2px;
    }

    .form-item-description {
        font-size: var(--text-sm);
        color: var(--text-tertiary);
    }

    .form-section {
        padding: var(--space-4);
        background: var(--glass-tint-subtle);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        margin-bottom: var(--space-5);
    }

    .form-section-title {
        margin-bottom: var(--space-3);
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
        color: var(--text-tertiary);
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }

    .form-layout {
        display: grid;
        grid-template-columns: 280px 1fr;
        gap: var(--space-6);
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

    @media (max-width: 900px) {
        .form-layout {
            grid-template-columns: 1fr;
        }
    }

    .form-sidebar {
        display: flex;
        flex-direction: column;
        gap: var(--space-4);
    }

    .form-main {
        display: flex;
        flex-direction: column;
        gap: var(--space-4);
    }

    .form-actions {
        display: flex;
        gap: var(--space-3);
        justify-content: flex-end;
        padding-top: var(--space-5);
        border-top: 1px solid var(--border-subtle);
        margin-top: var(--space-5);
    }
`;

/** @type {readonly import('lit').CSSResult[]} */
export const formStyles = [fieldPillStyles, formAuxStyles];

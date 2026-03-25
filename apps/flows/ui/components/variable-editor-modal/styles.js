import { css } from 'lit';

export const variableEditorFormStyles = css`
    .form-group {
        margin-bottom: var(--space-4);
    }

    .form-group:last-child {
        margin-bottom: 0;
    }

    .form-label {
        display: block;
        font-size: var(--text-sm);
        font-weight: 500;
        color: var(--text-secondary);
        margin-bottom: var(--space-2);
    }

    .form-label-required::after {
        content: ' *';
        color: var(--error);
    }

    .form-input {
        width: 100%;
        padding: var(--space-2) var(--space-3);
        background: var(--bg-input);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        color: var(--text-primary);
        font-size: var(--text-sm);
        font-family: var(--font-mono);
    }

    .form-input:focus {
        outline: none;
        border-color: var(--accent);
        background: var(--bg-elevated);
    }

    .form-input[type='number'] {
        width: 120px;
    }

    .form-textarea {
        width: 100%;
        min-height: 200px;
        padding: var(--space-3);
        background: var(--bg-input);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-md);
        color: var(--text-primary);
        font-size: var(--text-sm);
        font-family: var(--font-mono);
        resize: vertical;
        white-space: pre;
        overflow-wrap: normal;
        overflow-x: auto;
    }

    .form-textarea:focus {
        outline: none;
        border-color: var(--accent);
        background: var(--bg-elevated);
    }

    .form-hint {
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        margin-top: var(--space-1);
        display: block;
    }

    .form-checkbox-group {
        display: flex;
        align-items: center;
        gap: var(--space-2);
    }

    .form-checkbox {
        width: 16px;
        height: 16px;
        cursor: pointer;
    }

    .form-checkbox-label {
        font-size: var(--text-sm);
        color: var(--text-secondary);
        cursor: pointer;
    }

    .mode-toggle {
        display: flex;
        gap: var(--space-1);
        margin-bottom: var(--space-2);
    }

    .mode-btn {
        padding: var(--space-1) var(--space-2);
        background: var(--bg-subtle);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-sm);
        color: var(--text-secondary);
        font-size: var(--text-xs);
        cursor: pointer;
        transition: all 0.15s ease;
    }

    .mode-btn:hover {
        background: var(--bg-hover);
        color: var(--text-primary);
    }

    .mode-btn.active {
        background: var(--accent);
        color: white;
        border-color: var(--accent);
    }

    .inherited-badge {
        display: inline-block;
        padding: var(--space-1) var(--space-2);
        background: var(--bg-subtle);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-sm);
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        margin-left: var(--space-2);
        font-weight: var(--font-normal, 400);
    }

    .modal-actions-inner {
        display: flex;
        gap: var(--space-2);
        justify-content: flex-end;
        width: 100%;
    }
`;

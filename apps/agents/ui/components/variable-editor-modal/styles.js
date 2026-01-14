import { css } from 'lit';

export const variableEditorModalStyles = css`
    .modal-overlay {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: var(--overlay-bg);
        backdrop-filter: blur(4px);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
        padding: var(--space-4);
    }

    .modal-container {
        background: var(--glass-solid);
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-lg);
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
        width: 100%;
        max-width: 600px;
        max-height: 90vh;
        display: flex;
        flex-direction: column;
    }

    .modal-header {
        padding: var(--space-4);
        border-bottom: 1px solid var(--border-subtle);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .modal-title {
        font-size: var(--text-lg);
        font-weight: 600;
        color: var(--text-primary);
    }

    .modal-close {
        background: none;
        border: none;
        color: var(--text-tertiary);
        cursor: pointer;
        padding: var(--space-1);
        border-radius: var(--radius-sm);
        display: flex;
        align-items: center;
        justify-content: center;
    }

    .modal-close:hover {
        background: var(--bg-hover);
        color: var(--text-primary);
    }

    .modal-body {
        padding: var(--space-4);
        overflow-y: auto;
        flex: 1;
    }

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

    .form-input[type="number"] {
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

    .modal-footer {
        padding: var(--space-4);
        border-top: 1px solid var(--border-subtle);
        display: flex;
        gap: var(--space-2);
        justify-content: flex-end;
    }

    .btn {
        padding: var(--space-2) var(--space-4);
        border-radius: var(--radius-md);
        font-size: var(--text-sm);
        font-weight: 500;
        cursor: pointer;
        transition: all 0.15s ease;
        border: none;
    }

    .btn-secondary {
        background: var(--bg-subtle);
        color: var(--text-secondary);
    }

    .btn-secondary:hover {
        background: var(--bg-hover);
        color: var(--text-primary);
    }

    .btn-primary {
        background: var(--accent);
        color: white;
    }

    .btn-primary:hover {
        background: var(--accent-hover);
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
    }
`;



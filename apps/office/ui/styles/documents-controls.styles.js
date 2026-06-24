/**
 * Unified explorer control sizing (toolbar + details panel).
 */
import { css } from 'lit';

export const documentsControlHostStyles = css`
    :host {
        --documents-explorer-control-height: 2.25rem;
        --documents-explorer-btn-radius: var(--radius-md);
        --documents-action-primary: #6284e8;
        --documents-action-primary-hover: #5678dc;
        --documents-action-primary-border: rgba(98, 132, 232, 0.45);
    }
`;

export const documentsToolbarControlStyles = css`
    .toolbar .btn {
        height: var(--documents-explorer-control-height);
        min-height: var(--documents-explorer-control-height);
        padding: 0 0.875rem;
        border-radius: var(--documents-explorer-btn-radius);
        font-size: var(--text-sm);
        font-weight: 500;
        line-height: 1;
        box-shadow: none;
    }

    .toolbar .btn-primary {
        background: var(--documents-action-primary);
        border: 1px solid var(--documents-action-primary-border);
        color: #ffffff;
    }

    .toolbar .btn-primary:hover:not(:disabled) {
        background: var(--documents-action-primary-hover);
        box-shadow: none;
    }

    .toolbar .btn:not(.btn-primary) {
        background: var(--glass-solid-subtle);
        border: 1px solid var(--glass-border-medium);
        color: var(--text-primary);
    }

    .toolbar .btn:not(.btn-primary):hover:not(:disabled) {
        background: var(--glass-solid-medium);
        border-color: var(--glass-border-strong);
        box-shadow: none;
    }

    .toolbar .btn-icon-only {
        width: var(--documents-explorer-control-height);
        min-width: var(--documents-explorer-control-height);
        padding: 0;
    }

    .search-wrap {
        flex: 1 1 12rem;
        min-width: 8rem;
        max-width: 28rem;
        height: var(--documents-explorer-control-height);
    }

    .search-wrap .search-field {
        display: block;
        width: 100%;
    }

    .search-wrap platform-field {
        display: block;
        width: 100%;
        --field-pill-gap: 0;
        --field-pill-dense-padding-y: 0;
        --field-pill-dense-padding-x: 0.75rem;
        --field-pill-dense-spin-height: calc(var(--documents-explorer-control-height) - 2px);
        --field-pill-compact-radius: var(--documents-explorer-btn-radius);
        --field-pill-input-size: var(--text-sm);
        --field-pill-input-weight: var(--font-medium);
    }

    .search-wrap .search-mode-segment {
        display: inline-flex;
        flex-shrink: 0;
        align-items: center;
        gap: 2px;
        height: calc(var(--documents-explorer-control-height) - 8px);
        margin-right: 2px;
        padding: 2px;
        border-radius: calc(var(--documents-explorer-btn-radius) - 2px);
        background: var(--glass-solid-subtle);
        border: 1px solid var(--glass-border-subtle);
    }

    .search-wrap .search-mode-btn {
        height: 100%;
        padding: 0 0.5rem;
        border: none;
        border-radius: calc(var(--documents-explorer-btn-radius) - 4px);
        background: transparent;
        color: var(--text-secondary);
        font-size: var(--text-xs);
        font-weight: 500;
        cursor: pointer;
        white-space: nowrap;
        line-height: 1;
    }

    .search-wrap .search-mode-btn.active {
        background: var(--glass-solid-strong);
        color: var(--text-primary);
        box-shadow: var(--glass-shadow-subtle);
    }

    .view-toggle {
        display: inline-flex;
        flex-shrink: 0;
        overflow: hidden;
        height: var(--documents-explorer-control-height);
        border-radius: var(--documents-explorer-btn-radius);
        border: 1px solid var(--glass-border-medium);
        background: var(--glass-solid-subtle);
    }

    .view-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: var(--documents-explorer-control-height);
        height: 100%;
        border: none;
        background: transparent;
        color: var(--text-secondary);
        cursor: pointer;
        transition: var(--motion-transition-interactive);
    }

    .view-btn.active {
        background: var(--documents-selected-bg, var(--accent-subtle));
        color: var(--documents-selected-text, var(--accent));
    }
`;

export const documentsPanelActionStyles = css`
    .actions {
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
        margin-top: auto;
        padding-top: var(--space-3);
        border-top: 1px solid var(--documents-explorer-divider, var(--glass-border-subtle));
    }

    .actions .btn {
        width: 100%;
        height: var(--documents-explorer-control-height);
        min-height: var(--documents-explorer-control-height);
        padding: 0 var(--space-3);
        border-radius: var(--documents-explorer-btn-radius);
        font-size: var(--text-sm);
        font-weight: 500;
        line-height: 1;
        box-shadow: none;
    }

    .actions .btn-primary {
        background: var(--documents-action-primary);
        border: 1px solid var(--documents-action-primary-border);
        color: #ffffff;
    }

    .actions .btn-primary:hover:not(:disabled) {
        background: var(--documents-action-primary-hover);
        box-shadow: none;
    }

    .actions .btn:not(.btn-primary):not(.btn-danger) {
        background: transparent;
        border: 1px solid var(--glass-border-medium);
        color: var(--text-primary);
    }

    .actions .btn:not(.btn-primary):not(.btn-danger):hover:not(:disabled) {
        background: var(--glass-solid-subtle);
        border-color: var(--glass-border-strong);
        box-shadow: none;
    }

    .actions .btn-danger {
        background: transparent;
        color: var(--error);
        border: 1px solid rgba(244, 63, 94, 0.35);
        box-shadow: none;
    }

    .actions .btn-danger:hover:not(:disabled) {
        background: rgba(244, 63, 94, 0.08);
        border-color: rgba(244, 63, 94, 0.5);
        box-shadow: none;
    }

    .link-btn {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        width: 100%;
        min-height: var(--documents-explorer-control-height);
        padding: 0 var(--space-3);
        border: 1px solid var(--glass-border-medium);
        border-radius: var(--documents-explorer-btn-radius);
        background: transparent;
        color: var(--text-primary);
        font-size: var(--text-sm);
        font-weight: 500;
        text-align: left;
        cursor: pointer;
        transition: var(--motion-transition-interactive);
    }

    .link-btn:hover {
        background: var(--glass-solid-subtle);
        border-color: var(--glass-border-strong);
        color: var(--text-primary);
    }
`;

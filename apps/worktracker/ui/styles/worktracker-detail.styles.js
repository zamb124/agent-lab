/**
 * Worktracker task detail — content, activity, composer (class-scoped only).
 */
import { css } from 'lit';

export const worktrackerDetailContentStyles = css`
    .wt-detail-main {
        min-width: 0;
        display: flex;
        flex-direction: column;
        gap: var(--space-3);
    }
    .wt-detail-main.layout-page {
        gap: var(--space-2);
    }
    .wt-state-header {
        display: flex;
        align-items: center;
        gap: var(--space-2);
    }
    .wt-title-block {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: var(--space-2);
        min-width: 0;
        width: 100%;
        padding-bottom: var(--space-1);
    }
    .wt-id-chip {
        font-size: var(--text-xs);
        font-family: var(--font-mono, monospace);
        color: var(--text-tertiary);
        padding: var(--space-1) var(--space-2);
        border-radius: var(--radius-md);
        background: var(--glass-tint-subtle);
        border: var(--worktracker-divider);
        cursor: pointer;
        line-height: 1.2;
    }
    .wt-id-chip:hover {
        color: var(--text-secondary);
        background: var(--glass-tint-medium);
    }
    .wt-title-field {
        width: 100%;
        --field-pill-bg: transparent;
        --field-pill-border: 1px solid transparent;
        --field-pill-padding-y: var(--space-1);
        --field-pill-padding-x: var(--space-2);
        --field-pill-input-size: var(--worktracker-detail-title-size);
        --field-pill-input-weight: var(--font-semibold);
        --field-pill-input-line: 1.2;
        border-radius: var(--radius-md);
        transition: var(--motion-transition-interactive);
    }
    .wt-title-field:hover {
        --field-pill-bg: var(--glass-tint-subtle);
        --field-pill-border: 1px solid var(--glass-border-subtle);
    }
    .wt-title-field:focus-within {
        --field-pill-border: 1px solid var(--accent);
        --field-pill-bg: var(--glass-tint-subtle);
        box-shadow: var(--focus-ring);
    }
    .layout-page .wt-title-field {
        --field-pill-input-size: var(--text-3xl);
        --field-pill-input-weight: var(--font-bold);
        --field-pill-padding-y: var(--space-2);
        --field-pill-padding-x: var(--space-3);
        --field-pill-number-spin-height: 40px;
    }
    .layout-panel .wt-title-field {
        --field-pill-number-spin-height: 32px;
    }
    .layout-page .wt-desc-editor {
        --editor-min-height: 160px;
    }
    .layout-panel .wt-desc-editor {
        --editor-min-height: 120px;
    }
    .wt-desc-editor {
        width: 100%;
        min-width: 0;
        color: var(--text-secondary);
        margin-top: var(--space-1);
    }
    .wt-resolution {
        padding: var(--space-3);
        border-radius: var(--radius-md);
        background: var(--glass-tint-subtle);
        border: var(--worktracker-divider);
    }
    .wt-resolution-label,
    .wt-section-label {
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        color: var(--text-secondary);
        margin-bottom: var(--space-2);
    }
    .wt-resolution-text {
        font-size: var(--text-sm);
        color: var(--text-primary);
        white-space: pre-wrap;
        line-height: 1.5;
    }
    .wt-activity {
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
        padding-top: var(--space-4);
        border-top: var(--worktracker-divider);
    }
    .wt-activity-title {
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        color: var(--text-secondary);
        margin: 0;
    }
    .wt-activity-empty {
        font-size: var(--text-sm);
        color: var(--text-tertiary);
    }
    .wt-comment-list {
        display: flex;
        flex-direction: column;
        gap: var(--space-3);
    }
    .wt-comment-row {
        display: flex;
        gap: var(--space-2);
        align-items: flex-start;
        min-width: 0;
    }
    .wt-comment-body {
        flex: 1;
        min-width: 0;
    }
    .wt-comment-meta {
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        margin-bottom: var(--space-1);
    }
    .wt-comment-text {
        font-size: var(--text-sm);
        color: var(--text-primary);
        white-space: pre-wrap;
        line-height: 1.5;
    }
    .wt-composer {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-1) var(--space-1) var(--space-1) var(--space-2);
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-md);
        background: var(--glass-tint-subtle);
    }
    .wt-composer-field {
        flex: 1;
        min-width: 0;
        --field-pill-bg: transparent;
        --field-pill-border: transparent;
        --field-pill-number-spin-height: var(--worktracker-composer-min-height);
        --field-pill-textarea-min-height: var(--worktracker-composer-min-height);
        --field-pill-textarea-resize: none;
    }
    .wt-composer-field:focus-within {
        --field-pill-border: transparent;
        --field-pill-bg: transparent;
    }
    .wt-composer-send {
        flex-shrink: 0;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 32px;
        height: 32px;
        border: none;
        border-radius: var(--radius-md);
        background: var(--accent);
        color: var(--text-on-accent, #fff);
        cursor: pointer;
        transition: background var(--duration-fast) ease;
    }
    .wt-composer-send:hover:not(:disabled) {
        background: var(--accent-hover);
    }
    .wt-composer-send:disabled {
        opacity: 0.4;
        cursor: default;
    }
    .wt-composer-hint {
        font-size: var(--text-xs);
        color: var(--text-tertiary);
    }
    .wt-loading {
        font-size: var(--text-sm);
        color: var(--text-tertiary);
    }
`;

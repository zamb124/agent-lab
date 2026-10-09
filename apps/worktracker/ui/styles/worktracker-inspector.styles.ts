/**
 * Worktracker inspector sidebar — compact property rows.
 */
import { css } from 'lit';

export const worktrackerInspectorStyles = css`
    .wt-inspector {
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
        min-width: 0;
        width: 100%;
    }
    .wt-inspector-title {
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
        color: var(--text-tertiary);
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin: 0 0 var(--space-2);
    }
    .wt-inspector-meta {
        display: flex;
        flex-direction: column;
        gap: var(--space-1);
        margin-top: var(--space-2);
        padding-top: var(--space-2);
        border-top: var(--worktracker-divider);
    }
    .wt-inspector-readonly {
        font-size: var(--text-sm);
        color: var(--text-primary);
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .wt-inspector-link {
        font-size: var(--text-sm);
        color: var(--accent);
        background: none;
        border: none;
        padding: 0;
        cursor: pointer;
        text-align: left;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .wt-inspector-link:hover {
        text-decoration: underline;
    }
    .wt-inspector platform-field {
        width: 100%;
        --field-pill-bg: transparent;
        --field-pill-border: transparent;
        --field-pill-padding-x: 0;
        --field-pill-input-size: var(--text-sm);
    }
    .wt-inspector platform-field:focus-within {
        --field-pill-bg: var(--glass-tint-subtle);
        --field-pill-border: 1px solid var(--glass-border-subtle);
        --field-pill-padding-x: var(--space-2);
    }
    worktracker-inspector-row platform-field {
        width: 100%;
        --field-pill-bg: transparent;
        --field-pill-border: transparent;
        --field-pill-padding-x: 0;
        --field-pill-input-size: var(--text-sm);
        --field-pill-number-spin-height: 32px;
    }
    worktracker-inspector-row platform-field:focus-within {
        --field-pill-bg: var(--glass-tint-subtle);
        --field-pill-border: 1px solid var(--glass-border-subtle);
        --field-pill-padding-x: var(--space-2);
    }
    .wt-inspector-toolbar {
        display: flex;
        justify-content: flex-end;
        align-items: center;
        gap: var(--space-1);
        margin-bottom: var(--space-3);
        padding-bottom: var(--space-2);
        border-bottom: var(--worktracker-divider);
    }
    .wt-inspector-section {
        margin-top: var(--space-3);
    }
    .wt-inspector-section-title {
        font-size: var(--text-xs);
        font-weight: var(--font-semibold);
        color: var(--text-tertiary);
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin: 0 0 var(--space-2);
    }
`;

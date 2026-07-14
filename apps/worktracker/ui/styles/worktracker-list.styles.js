/**
 * Worktracker flat list rows — inbox, my tasks, queue detail.
 * Строки — отдельные row-cards с gap (не «склеенный» divider-list).
 */
import { css } from 'lit';

export const worktrackerListStyles = css`
    .wt-list {
        display: flex;
        flex-direction: column;
        min-width: 0;
        gap: var(--space-2);
        overflow: visible;
        background: transparent;
        border: none;
    }
    .wt-list-row {
        display: block;
        min-width: 0;
        border: var(--worktracker-divider);
        border-radius: var(--radius-md);
        background: var(--bg-primary);
        overflow: visible;
    }
    .wt-list-row:hover {
        background: var(--glass-tint-subtle);
    }
    .wt-list-row[selected] {
        background: var(--glass-tint-medium);
        box-shadow: inset 2px 0 0 var(--work-item-state-in_progress);
    }
`;

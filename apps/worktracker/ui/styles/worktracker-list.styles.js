/**
 * Worktracker flat list rows — inbox, my tasks, queue detail.
 */
import { css } from 'lit';

export const worktrackerListStyles = css`
    .wt-list {
        display: flex;
        flex-direction: column;
        min-width: 0;
        gap: 0;
        border: var(--worktracker-divider);
        border-radius: var(--radius-lg);
        overflow: hidden;
        background: var(--bg-primary);
    }
    .wt-list-row {
        display: block;
        min-width: 0;
        border-bottom: var(--worktracker-divider);
    }
    .wt-list-row:last-child {
        border-bottom: none;
    }
    .wt-list-row:hover {
        background: var(--glass-tint-subtle);
    }
    .wt-list-row[selected] {
        background: var(--glass-tint-medium);
        box-shadow: inset 2px 0 0 var(--work-item-state-in_progress);
    }
`;

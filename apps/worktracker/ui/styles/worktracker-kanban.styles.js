/**
 * Worktracker kanban board — columns and cards.
 */
import { css } from 'lit';

export const worktrackerKanbanStyles = css`
    .wt-kanban {
        display: flex;
        gap: var(--space-3);
        overflow-x: auto;
        overflow-y: hidden;
        flex: 1;
        min-height: 0;
        padding-bottom: var(--space-2);
        align-items: flex-start;
    }
    .wt-kanban-column {
        flex: 0 0 300px;
        min-width: 300px;
        max-width: 300px;
        display: flex;
        flex-direction: column;
        max-height: 100%;
        min-height: 200px;
        border-radius: var(--radius-lg);
        background: var(--glass-tint-subtle);
        border: var(--worktracker-divider);
    }
    .wt-kanban-column-header {
        display: flex;
        align-items: center;
        gap: var(--space-2);
        padding: var(--space-3);
        flex-shrink: 0;
        position: sticky;
        top: 0;
        z-index: 1;
        background: inherit;
        border-bottom: var(--worktracker-divider);
    }
    .wt-kanban-column-title {
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        color: var(--text-primary);
        flex: 1;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .wt-kanban-column-count {
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        flex-shrink: 0;
    }
    .wt-kanban-column-body {
        display: flex;
        flex-direction: column;
        gap: var(--space-2);
        padding: var(--space-2);
        overflow-y: auto;
        flex: 1;
        min-height: 0;
    }
    .wt-kanban-add {
        display: flex;
        align-items: center;
        gap: var(--space-1);
        padding: var(--space-2);
        margin: 0 var(--space-2) var(--space-2);
        border: none;
        border-radius: var(--radius-md);
        background: transparent;
        color: var(--text-tertiary);
        font-size: var(--text-sm);
        cursor: pointer;
        text-align: left;
    }
    .wt-kanban-add:hover {
        background: var(--glass-tint-medium);
        color: var(--text-secondary);
    }
    .wt-board-toolbar {
        display: flex;
        align-items: center;
        gap: var(--space-3);
        min-height: 40px;
        flex-shrink: 0;
        margin-bottom: var(--space-4);
    }
    .wt-board-toolbar-spacer {
        flex: 1;
        min-width: 0;
    }
`;

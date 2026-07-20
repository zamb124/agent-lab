/**
 * Worktracker flat list rows — inbox, my tasks, queue detail.
 * Row-cards с gap (Linear-style): отдельные поверхности, не divider-list.
 *
 * `.wt-list-row` в pages попадает в slot list-section — стили через ::slotted.
 */
import { css } from 'lit';

export const worktrackerListStyles = css`
    .wt-list {
        display: flex;
        flex-direction: column;
        min-width: 0;
        gap: var(--worktracker-list-gap, var(--space-3));
        overflow: visible;
        background: transparent;
        border: none;
    }
    .wt-list-row,
    ::slotted(.wt-list-row) {
        display: block;
        min-width: 0;
        box-sizing: border-box;
        border: 1px solid var(--glass-border-subtle);
        border-radius: var(--radius-lg);
        background: var(--worktracker-surface-bg);
        box-shadow: var(--glass-shadow-subtle);
        overflow: hidden;
        transition:
            background var(--duration-fast, 120ms) ease,
            border-color var(--duration-fast, 120ms) ease,
            box-shadow var(--duration-fast, 120ms) ease;
    }
    .wt-list-row:hover,
    ::slotted(.wt-list-row:hover) {
        background: var(--glass-tint-subtle);
        border-color: var(--glass-border-medium);
        box-shadow: var(--glass-shadow-medium);
    }
    .wt-list-row[selected],
    ::slotted(.wt-list-row[selected]) {
        background: var(--accent-subtle);
        border-color: color-mix(in srgb, var(--accent) 45%, var(--glass-border-subtle));
        box-shadow:
            inset 3px 0 0 var(--accent),
            var(--glass-shadow-subtle);
    }
`;

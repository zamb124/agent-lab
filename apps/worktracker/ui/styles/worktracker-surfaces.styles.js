/**
 * Worktracker page surfaces — cards, sections, dividers, empty states.
 */
import { css } from 'lit';

export const worktrackerSurfacesStyles = css`
    .wt-page {
        display: flex;
        flex-direction: column;
        min-height: 0;
        flex: 1;
        width: 100%;
        gap: var(--worktracker-section-gap);
    }
    .wt-card {
        box-sizing: border-box;
        background: var(--worktracker-surface-bg);
        border: var(--worktracker-surface-border);
        border-radius: var(--worktracker-surface-radius);
        box-shadow: var(--worktracker-surface-shadow);
        min-width: 0;
        width: 100%;
    }
    .wt-card-section {
        padding: var(--worktracker-surface-padding);
        min-width: 0;
    }
    .wt-detail-card-inner {
        display: flex;
        flex-direction: column;
        gap: var(--worktracker-detail-inner-gap);
    }
    .wt-card-divider {
        border: none;
        border-top: var(--worktracker-divider);
        margin: 0;
    }
    .wt-card-divider-inset {
        margin: 0;
    }
            .wt-card-footer {
        display: flex;
        flex-wrap: wrap;
        gap: var(--space-2);
        padding: var(--space-2) 0 0;
        border-top: var(--worktracker-divider);
        margin-top: var(--space-1);
    }
    .wt-section {
        display: flex;
        flex-direction: column;
        min-width: 0;
        gap: var(--space-2);
    }
    .wt-section-title {
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        color: var(--text-secondary);
        margin: 0;
    }
    .wt-divider {
        border: none;
        border-top: var(--worktracker-divider);
        margin: 0;
    }
    .wt-empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: var(--space-2);
        padding: var(--space-6) var(--space-4);
        color: var(--text-tertiary);
        text-align: center;
    }
    .wt-empty-icon {
        color: var(--text-tertiary);
        opacity: 0.6;
    }
    .wt-empty-title {
        font-size: var(--text-sm);
        color: var(--text-secondary);
        margin: 0;
    }
    .wt-empty-hint {
        font-size: var(--text-xs);
        color: var(--text-tertiary);
        margin: 0;
    }
`;

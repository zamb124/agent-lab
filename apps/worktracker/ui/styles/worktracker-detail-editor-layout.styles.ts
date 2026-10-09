/**
 * Page detail layout — main column + inspector sidebar.
 */
import { css } from 'lit';

export const worktrackerDetailEditorLayoutStyles = css`
    :host([layout="page"]) {
        display: flex;
        flex-direction: row;
        align-items: flex-start;
        gap: var(--space-5);
        width: 100%;
        box-sizing: border-box;
    }
    :host([layout="page"]) .wt-page-main {
        flex: 1 1 0;
        min-width: 0;
        width: 100%;
    }
    :host([layout="page"]) .wt-inspector-sticky {
        flex: 0 0 var(--worktracker-inspector-width);
        width: var(--worktracker-inspector-width);
        min-width: 0;
    }
    :host([layout="page"]) .wt-properties-collapsible {
        flex: 0 0 var(--worktracker-inspector-width);
        width: var(--worktracker-inspector-width);
        min-width: 0;
    }
    .wt-inspector-sticky {
        position: sticky;
        top: var(--space-4);
        box-sizing: border-box;
        width: 100%;
    }
    .wt-properties-toggle {
        display: none;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        padding: var(--space-2) var(--space-3);
        border: var(--worktracker-divider);
        border-radius: var(--radius-md);
        background: var(--glass-tint-subtle);
        color: var(--text-secondary);
        font-size: var(--text-sm);
        font-weight: var(--font-semibold);
        cursor: pointer;
    }
    .wt-properties-collapsible {
        display: contents;
    }
    .wt-detail-actions {
        display: flex;
        flex-wrap: wrap;
        gap: var(--space-2);
        padding-top: var(--space-2);
    }
    :host([layout="panel"]) .wt-detail-actions {
        border-top: var(--worktracker-divider);
        margin-top: auto;
        padding: var(--space-3) 0 0;
    }
    @media (max-width: 767px) {
        :host([layout="page"]) {
            flex-direction: column;
        }
        :host([layout="page"]) .wt-properties-collapsible {
            flex: 1 1 auto;
            width: 100%;
        }
        .wt-inspector-sticky {
            position: static;
            width: 100%;
        }
        :host([layout="page"]) .wt-properties-toggle {
            display: flex;
        }
        :host([layout="page"]) .wt-properties-collapsible:not([data-expanded="true"]) {
            display: none;
        }
    }
`;

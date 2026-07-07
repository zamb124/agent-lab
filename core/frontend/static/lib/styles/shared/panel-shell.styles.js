/**
 * Content panel shell — island-style panel для evaluation/modals/trace viewers.
 */
import { css } from 'lit';

export const panelShellStyles = css`
    .content-panel {
        flex: 1;
        min-width: 0;
        min-height: 0;
        display: flex;
        flex-direction: column;
        border: 1px solid var(--border-subtle);
        border-radius: var(--radius-xl);
        background: var(--glass-solid-subtle);
        overflow: hidden;
    }

    .content-panel-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: var(--space-3);
        padding: var(--space-3) var(--space-4);
        border-bottom: 1px solid var(--border-subtle);
        background: linear-gradient(
            180deg,
            color-mix(in srgb, var(--glass-solid-medium), transparent 8%),
            transparent
        );
        flex-shrink: 0;
    }

    .content-panel-body {
        flex: 1;
        min-height: 0;
        overflow: auto;
    }

    .content-panel-empty {
        display: flex;
        align-items: center;
        justify-content: center;
        padding: var(--space-6);
        color: var(--text-tertiary);
        font-size: var(--text-sm);
        text-align: center;
    }
`;

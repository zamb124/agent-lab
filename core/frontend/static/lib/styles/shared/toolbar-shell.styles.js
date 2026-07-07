/**
 * Toolbar pill shell — chrome row для editor/evaluation/catalog toolbars.
 * Только layout + surface; контент — слоты компонентов.
 */
import { css } from 'lit';

export const toolbarShellStyles = css`
    .toolbar-shell {
        display: grid;
        grid-template-columns: minmax(220px, 1fr) auto auto auto;
        align-items: center;
        gap: var(--space-2);
        min-height: var(--flows-toolbar-shell-min-height);
        padding: 7px;
        border: 1px solid color-mix(in srgb, var(--border-subtle), transparent 8%);
        border-radius: 22px;
        background: color-mix(in srgb, var(--bg-surface), transparent 4%);
        box-shadow: 0 10px 30px color-mix(in srgb, var(--shadow-color), transparent 88%);
    }

    .toolbar-shell--flex {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: var(--space-2);
        width: 100%;
        min-width: 0;
        box-sizing: border-box;
    }
`;

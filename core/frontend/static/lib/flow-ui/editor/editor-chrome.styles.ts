/**
 * Токены хрома редактора Flow UI (рамка выделения, линия вставки) поверх Design Standard.
 */
import { css } from '../../lit-shim.js';

export const flowUIEditorChromeTokens = css`
    :host {
        --flow-ui-editor-select: var(--accent);
        --flow-ui-editor-select-fill: color-mix(in srgb, var(--accent) 10%, transparent);
        --flow-ui-editor-hover: color-mix(in srgb, var(--accent) 45%, transparent);
        --flow-ui-editor-insert: var(--success);
        --flow-ui-editor-insert-fill: color-mix(in srgb, var(--success) 16%, transparent);
        --flow-ui-editor-label-fg: var(--text-on-accent, #fff);
    }
    .selection .align { display: inline-flex; align-items: center; gap: 2px; pointer-events: auto; }
    .selection .align button {
        width: 18px; height: 16px; padding: 2px; border: 0; border-radius: 3px; background: transparent;
        color: inherit; cursor: pointer; display: grid; gap: 2px; align-content: center;
    }
    .selection .align button[aria-pressed='true'] { background: color-mix(in srgb, #fff 28%, transparent); }
    .selection .align button::before, .selection .align button::after {
        content: ''; height: 2px; background: currentColor; border-radius: 1px;
    }
    .selection .align button[data-align='start']::before,
    .selection .align button[data-align='start']::after { width: 10px; justify-self: start; }
    .selection .align button[data-align='center']::before,
    .selection .align button[data-align='center']::after { width: 10px; justify-self: center; }
    .selection .align button[data-align='end']::before,
    .selection .align button[data-align='end']::after { width: 10px; justify-self: end; }
    .selection .resize-e {
        position: absolute; top: 0; right: -4px; width: 8px; height: 100%;
        cursor: ew-resize; pointer-events: auto; touch-action: none;
    }
    .selection .resize-e::after {
        content: ''; position: absolute; top: 18%; bottom: 18%; left: 2px; width: 4px;
        border-radius: 2px; background: var(--flow-ui-editor-select);
        box-shadow: 0 0 0 1px var(--flow-ui-editor-label-fg);
    }
`;

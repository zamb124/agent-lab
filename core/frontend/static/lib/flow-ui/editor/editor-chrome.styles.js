/**
 * Shared Flow UI editor chrome tokens (Webflow/Framer-quiet).
 * Alias platform Design Standard tokens; no hardcoded neon hex.
 */
import { css } from '../../lit-shim.js';

export const flowUIEditorChromeTokens = css`
    :host {
        --flow-ui-editor-select: var(--accent);
        --flow-ui-editor-select-fill: color-mix(in srgb, var(--accent) 10%, transparent);
        --flow-ui-editor-select-label: var(--accent);
        --flow-ui-editor-hover: color-mix(in srgb, var(--accent) 45%, transparent);
        --flow-ui-editor-insert: var(--success);
        --flow-ui-editor-insert-fill: color-mix(in srgb, var(--success) 16%, transparent);
        --flow-ui-editor-reject: var(--error);
        --flow-ui-editor-reject-fill: color-mix(in srgb, var(--error) 14%, transparent);
        --flow-ui-editor-grid-col: color-mix(in srgb, var(--accent) 10%, transparent);
        --flow-ui-editor-grid-edge: color-mix(in srgb, var(--accent) 22%, transparent);
        --flow-ui-editor-grid-row-edge: color-mix(in srgb, var(--accent) 14%, transparent);
        --flow-ui-editor-handle-bg: var(--bg-surface, #fff);
        --flow-ui-editor-label-fg: var(--text-on-accent, #fff);
    }
`;

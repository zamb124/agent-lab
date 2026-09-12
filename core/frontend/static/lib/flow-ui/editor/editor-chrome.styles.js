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
`;
